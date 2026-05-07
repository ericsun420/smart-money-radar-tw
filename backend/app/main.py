from __future__ import annotations

import asyncio
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_alerts import router as alerts_router
from app.api.routes_market import router as market_router
from app.api.routes_rankings import router as rankings_router
from app.api.routes_settings import router as settings_router
from app.api.routes_stock import router as stock_router
from app.api.routes_topics import router as topics_router
from app.notifier.discord import validate_webhook_url
from app.scheduler import configure_discord_queue_job, configure_scan_job, scheduler
from app.storage.repository import repo


FORMAL_SOURCE_STATUSES = {"official_full", "official_intraday"}


async def run_startup_scan() -> None:
    try:
        await asyncio.to_thread(repo.scan)
    except Exception as exc:
        print(f"startup scan failed: {type(exc).__name__}: {exc}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_scan_job(repo.scan, repo.settings.scan_interval_minutes)
    def flush_due_discord_queue() -> None:
        if repo.latest_scan_debug() and repo.latest_scan_debug().source_status not in FORMAL_SOURCE_STATUSES:
            return
        webhook_url = repo.settings.discord_webhook_url
        if not repo.settings.push_enabled or not webhook_url or validate_webhook_url(webhook_url):
            return
        asyncio.run(repo.notifications.flush_discord(webhook_url, repo.mark_discord_sent, lambda target_id: repo.topic_flows.get(target_id)))

    configure_discord_queue_job(flush_due_discord_queue)
    if not scheduler.running:
        scheduler.start()
    if repo.last_scan_at is None:
        asyncio.create_task(run_startup_scan())
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(title="Smart Money Radar API", version="0.1.0", lifespan=lifespan)

def cors_origins() -> list[str]:
    origins = os.getenv("SMART_MONEY_CORS_ORIGINS", "*").strip()
    if origins == "*":
        if os.getenv("SMART_MONEY_ACCESS_TOKEN", "").strip():
            return [
                "http://127.0.0.1:8000",
                "http://localhost:8000",
            ]
        return ["*"]
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)
app.include_router(alerts_router)
app.include_router(market_router)
app.include_router(rankings_router)
app.include_router(stock_router)
app.include_router(topics_router)
app.include_router(settings_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


ACCESS_COOKIE_NAME = "smart_money_access"
ADMIN_COOKIE_NAME = "smart_money_admin"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
RATE_LIMIT_RULES = {
    "/api/stocks/search/": (30, 60),
    "/api/stocks/": (60, 60),
    "/api/scan/run": (5, 60),
    "/api/settings": (10, 60),
    "/api/alert-rules": (20, 60),
}
_rate_limit_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def configured_access_token() -> str:
    return os.getenv("SMART_MONEY_ACCESS_TOKEN", "").strip().lstrip("\ufeff")


def configured_admin_token() -> str:
    return os.getenv("SMART_MONEY_ADMIN_TOKEN", "").strip().lstrip("\ufeff")


def request_has_token(request: Request, token: str, *, cookie_name: str, header_name: str, query_name: str | None = None) -> bool:
    candidates = [
        request.headers.get(header_name, ""),
        request.cookies.get(cookie_name, ""),
    ]
    if query_name:
        candidates.append(request.query_params.get(query_name, ""))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            if secrets.compare_digest(candidate.encode("utf-8"), token.encode("utf-8")):
                return True
        except UnicodeError:
            continue
    return False


def request_has_access(request: Request, token: str) -> bool:
    return request_has_token(
        request,
        token,
        cookie_name=ACCESS_COOKIE_NAME,
        header_name="x-smart-money-token",
        query_name="token",
    )


def request_has_admin(request: Request) -> bool:
    admin_token = configured_admin_token()
    if not admin_token:
        return False
    return request_has_token(
        request,
        admin_token,
        cookie_name=ADMIN_COOKIE_NAME,
        header_name="x-smart-money-admin-token",
    )


def has_forwarded_public_headers(request: Request) -> bool:
    return bool(
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for")
        or request.headers.get("x-real-ip")
    )


def is_local_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost", "testclient"} and not has_forwarded_public_headers(request)


def can_write(request: Request) -> bool:
    return is_local_request(request) or request_has_admin(request)


def cookie_should_be_secure(request: Request) -> bool:
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
        or '"scheme":"https"' in request.headers.get("cf-visitor", "").replace(" ", "").lower()
    )


def client_identity(request: Request) -> str:
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


def rate_limit_rule(path: str) -> tuple[int, int] | None:
    for prefix, rule in RATE_LIMIT_RULES.items():
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return rule
    return None


def is_rate_limited(request: Request) -> bool:
    rule = rate_limit_rule(request.url.path)
    if not rule:
        return False
    limit, window_seconds = rule
    now = time.monotonic()
    key = (client_identity(request), request.url.path)
    hits = _rate_limit_hits[key]
    while hits and now - hits[0] > window_seconds:
        hits.popleft()
    if len(hits) >= limit:
        return True
    hits.append(now)
    return False


def unauthorized_response(request: Request) -> HTMLResponse | JSONResponse:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Smart Money Radar access token required"}, status_code=401)
    return HTMLResponse(
        """
        <!doctype html>
        <html lang="zh-Hant">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>Smart Money Radar</title>
          <style>
            body{margin:0;background:#080b10;color:#edf3fb;font-family:"Microsoft JhengHei",system-ui,sans-serif}
            main{max-width:420px;margin:12vh auto;padding:24px}
            h1{font-size:26px;margin:0 0 10px}
            p{color:#9fb0c5;line-height:1.7}
            code{background:#111b29;border:1px solid #26364d;border-radius:6px;padding:2px 6px}
          </style>
        </head>
        <body>
          <main>
            <h1>Smart Money Radar</h1>
            <p>此公開入口需要存取 token。</p>
            <p>請使用管理者提供的網址，例如：<br><code>https://你的網域/?token=你的token</code></p>
          </main>
        </body>
        </html>
        """,
        status_code=401,
    )


@app.middleware("http")
async def smart_money_access_guard(request: Request, call_next):
    if request.url.path == "/render-health":
        return await call_next(request)
    token = configured_access_token()
    if not token:
        if request.method in WRITE_METHODS and request.url.path.startswith("/api/") and not can_write(request):
            return JSONResponse({"detail": "Smart Money Radar admin token required"}, status_code=403)
        if is_rate_limited(request):
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
        return await call_next(request)
    if not request_has_access(request, token):
        return unauthorized_response(request)
    if request.method in WRITE_METHODS and request.url.path.startswith("/api/") and not can_write(request):
        return JSONResponse({"detail": "Smart Money Radar admin token required"}, status_code=403)
    if is_rate_limited(request):
        return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
    query_token = request.query_params.get("token")
    if query_token and not request.url.path.startswith("/api/"):
        clean_params = [(key, value) for key, value in request.query_params.multi_items() if key != "token"]
        clean_url = request.url.replace(query=urlencode(clean_params, doseq=True))
        response = RedirectResponse(str(clean_url), status_code=303)
        response.set_cookie(
            ACCESS_COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            secure=cookie_should_be_secure(request),
            max_age=60 * 60 * 24 * 30,
        )
        return response
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    if query_token:
        response.set_cookie(
            ACCESS_COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            secure=cookie_should_be_secure(request),
            max_age=60 * 60 * 24 * 30,
        )
    return response


@app.get("/")
def index() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/render-health")
def render_health() -> dict[str, str]:
    return {"ok": "true"}
