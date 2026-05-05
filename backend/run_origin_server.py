from __future__ import annotations

import os
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
token_file = ROOT / "public_access_token.txt"
if token_file.exists() and not os.getenv("SMART_MONEY_ACCESS_TOKEN"):
    os.environ["SMART_MONEY_ACCESS_TOKEN"] = token_file.read_text(encoding="utf-8-sig").strip()

uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")
