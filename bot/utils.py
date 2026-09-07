from __future__ import annotations

import os
from datetime import timedelta


def truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"
    return text[: limit - 1].rstrip() + "…"


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "?:??"
    try:
        total = int(max(0, seconds))
    except (TypeError, ValueError):
        return "?:??"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_eta(seconds: float | int | None) -> str:
    if not seconds:
        return format_duration(seconds)
    return str(timedelta(seconds=int(seconds)))


def progress_slider(position: float, duration: float | None, width: int = 18) -> str:
    if not duration or duration <= 0:
        return "─" * width
    ratio = min(max(position / duration, 0.0), 1.0)
    idx = min(int(round(ratio * (width - 1))), width - 1)
    return "─" * idx + "●" + "─" * (width - idx - 1)


def is_http_url(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def cookies_available(path: str | None) -> bool:
    return bool(path) and os.path.isfile(path)
