from __future__ import annotations

import httpx

from app.engine.utils import concentration_label
from app.storage.models import SignalEvent, TopicFlow


def validate_webhook_url(url: str) -> str | None:
    if not url:
        return "Discord webhook URL is empty"
    if not (url.startswith("https://discord.com/api/webhooks/") or url.startswith("https://discordapp.com/api/webhooks/")):
        return "Discord webhook URL format is invalid"
    return None


def format_discord_message(signal: SignalEvent, topic: TopicFlow | None) -> str:
    color = "RED" if signal.direction == "INFLOW" else "GREEN"
    direction = "inflow" if signal.direction == "INFLOW" else "outflow"
    lines = [
        f"[{signal.signal_level} topic] {signal.target_id} {color} estimated_flow_{direction} score={signal.score}",
        f"time: {signal.timestamp:%H:%M}",
        f"estimated_flow_net: {signal.net_yi:+.2f} yi",
        f"delta: {signal.delta_from_previous_yi:+.2f} yi",
    ]
    if topic:
        lines += [
            f"estimated_inflow: {topic.inflow_yi:.2f} yi | estimated_outflow: {topic.outflow_yi:.2f} yi",
            f"concentration: {topic.concentration_pct:.0f}% ({concentration_label(topic.concentration_pct)})",
        ]
        if topic.net_near_zero:
            lines.append("warning: long/short offset; net is unstable")
    lines.append("")
    lines.append("top 5 impacts:")
    for idx, stock in enumerate(signal.related_stocks[:5], 1):
        flow_word = "inflow" if stock.direction == "INFLOW" else "outflow"
        lines.append(f"{idx}. {stock.code} {stock.name} {stock.change_pct:+.2f}% {stock.price}")
        lines.append(f"   estimated_{flow_word} {abs(stock.display_signed_flow_yi):.2f} yi | share {stock.impact_pct:.0f}%")
    lines += [
        "",
        f"data_quality: {signal.data_quality_bucket}",
        f"formal_grade: {signal.formal_grade}",
        f"formal_tuning: {'allowed' if signal.formal_grade else 'blocked_not_for_formal_tuning'}",
        f"blocked_reason: {signal.blocked_reason or 'none'}",
        "notice: estimated_flow is derived from public market data; not real main-force order flow or investment advice.",
    ]
    return "\n".join(lines)


async def send_discord(webhook_url: str, content: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json={"content": content})
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise TimeoutError("Discord webhook request timed out") from exc
