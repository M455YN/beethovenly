from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import aiohttp
import discord
import yt_dlp

from bot.audio.track import Track, track_from_info
from bot.config import settings
from bot.utils import is_http_url

log = logging.getLogger("beethovenly.ytdlp")

SPOTIFY_RE = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-z]+/)?(track|album|playlist)/([A-Za-z0-9]+)",
    re.IGNORECASE,
)

_BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "ignoreerrors": True,
    "nocheckcertificate": True,
    "skip_download": True,
    "extract_flat": "in_playlist",
    "format": "bestaudio/best",
    "source_address": "0.0.0.0",
    "cachedir": False,
    "noplaylist": False,
}


class ExtractionError(RuntimeError):
    pass


def _opts(*, search: bool = False, playlist: bool = True) -> dict[str, Any]:
    opts = dict(_BASE_OPTS)
    if settings.cookies_file:
        opts["cookiefile"] = settings.cookies_file
    if search:
        opts["default_search"] = "ytsearch"
        opts["noplaylist"] = True
    if not playlist:
        opts["noplaylist"] = True
        opts["extract_flat"] = False
    return opts


def _entries_from_info(info: dict[str, Any]) -> list[dict[str, Any]]:
    if not info:
        return []
    entries = info.get("entries")
    if entries is None:
        return [info]
    return [entry for entry in entries if entry]


def _absolute_url(entry: dict[str, Any]) -> str | None:
    url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
    if not url:
        return None
    url = str(url)
    if url.startswith("http://") or url.startswith("https://"):
        return url
    ie = str(entry.get("ie_key") or entry.get("extractor_key") or entry.get("extractor") or "").lower()
    vid = str(entry.get("id") or url)
    if "youtube" in ie:
        return f"https://www.youtube.com/watch?v={vid}"
    if "soundcloud" in ie and url.startswith("/"):
        return f"https://soundcloud.com{url}"
    return None


def extract_sync(query: str, *, requester: discord.abc.User, search_count: int = 1) -> list[Track]:
    query = query.strip()
    if not query:
        raise ExtractionError("Puste zapytanie.")

    ydl_query = query
    playlist = True
    search = False

    if not is_http_url(query):
        ydl_query = f"ytsearch{search_count}:{query}"
        playlist = False
        search = True
    elif SPOTIFY_RE.search(query):
        # Rozwiązywane wcześniej asynchronicznie; tu tylko zabezpieczenie.
        ydl_query = f"ytsearch1:{query}"
        playlist = False
        search = True

    opts = _opts(search=search, playlist=playlist)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(ydl_query, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise ExtractionError(f"yt-dlp nie ogarnął tego źródła: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("Nieoczekiwany błąd yt-dlp")
        raise ExtractionError(f"Nie udało się pobrać informacji o utworze: {exc}") from exc

    raw_entries = _entries_from_info(info or {})
    tracks: list[Track] = []
    for entry in raw_entries:
        if entry.get("_type") == "playlist":
            continue
        url = _absolute_url(entry)
        if not url:
            continue
        entry = dict(entry)
        entry["webpage_url"] = url
        if not entry.get("title") or entry.get("title") == url:
            try:
                with yt_dlp.YoutubeDL(_opts(playlist=False)) as ydl:
                    entry = ydl.extract_info(url, download=False) or entry
            except Exception:  # noqa: BLE001
                log.debug("Nie udało się dociągnąć metadanych dla %s", url)
        tracks.append(track_from_info(entry, requester=requester, query=query))
        if len(tracks) >= (search_count if search else settings.playlist_limit):
            break

    if not tracks:
        raise ExtractionError("Nic nie znalazłem dla tego zapytania.")
    return tracks


async def resolve_spotify_query(url: str) -> str | None:
    match = SPOTIFY_RE.search(url)
    if not match:
        return None
    kind = match.group(1)
    oembed = f"https://open.spotify.com/oembed?url={url}"
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(oembed, headers={"User-Agent": "Beethovenly/1.0"}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except Exception:  # noqa: BLE001
        log.warning("Spotify oEmbed nie zadziałał dla %s", url)
        return None

    title = (data.get("title") or "").strip()
    author = (data.get("author_name") or "").strip()
    if not title:
        return None
    if kind == "track":
        return f"{title} {author}".strip()
    return f"{title} {author}".strip()


async def extract_tracks(
    query: str,
    *,
    requester: discord.abc.User,
    search_count: int = 1,
) -> list[Track]:
    query = query.strip()
    spotify = await resolve_spotify_query(query)
    if spotify:
        query = spotify
    return await asyncio.to_thread(extract_sync, query, requester=requester, search_count=search_count)
