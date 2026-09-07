from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import discord


class LoopMode(str, Enum):
    OFF = "off"
    ONE = "one"
    ALL = "all"

    def label(self) -> str:
        return {
            LoopMode.OFF: "wyłączona",
            LoopMode.ONE: "utwór",
            LoopMode.ALL: "kolejka",
        }[self]

    def emoji(self) -> str:
        return {
            LoopMode.OFF: "➡️",
            LoopMode.ONE: "🔂",
            LoopMode.ALL: "🔁",
        }[self]

    def next(self) -> LoopMode:
        order = [LoopMode.OFF, LoopMode.ALL, LoopMode.ONE]
        return order[(order.index(self) + 1) % len(order)]


@dataclass(slots=True)
class Track:
    title: str
    webpage_url: str
    webpage_id: str
    uploader: str
    duration: float | None
    thumbnail: str | None
    extractor: str
    is_live: bool
    requester_id: int
    requester_name: str
    source_query: str

    @property
    def display_title(self) -> str:
        return self.title or "Nieznany utwór"

    def to_choice_label(self, index: int) -> str:
        prefix = f"{index}. "
        rest = 100 - len(prefix)
        title = self.display_title
        if len(title) > rest:
            title = title[: rest - 1] + "…"
        return prefix + title


def track_from_info(info: dict[str, Any], *, requester: discord.abc.User, query: str) -> Track:
    duration = info.get("duration")
    try:
        duration_val = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_val = None

    thumbnail = info.get("thumbnail")
    thumbnails = info.get("thumbnails") or []
    if not thumbnail and thumbnails:
        thumbnail = thumbnails[-1].get("url")

    webpage_url = info.get("webpage_url") or info.get("url") or query
    title = info.get("title") or info.get("alt_title") or "Nieznany utwór"
    uploader = info.get("uploader") or info.get("channel") or info.get("artist") or "Nieznany autor"

    return Track(
        title=str(title),
        webpage_url=str(webpage_url),
        webpage_id=str(info.get("id") or ""),
        uploader=str(uploader),
        duration=duration_val,
        thumbnail=str(thumbnail) if thumbnail else None,
        extractor=str(info.get("extractor_key") or info.get("extractor") or "generic"),
        is_live=bool(info.get("is_live") or info.get("live_status") == "is_live"),
        requester_id=requester.id,
        requester_name=requester.display_name,
        source_query=query,
    )
