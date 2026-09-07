from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.audio.track import Track

PLAYLISTS_ROOT = Path("data/playlists")
MAX_PLAYLISTS_PER_GUILD = 25
MAX_NAME_LENGTH = 32
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class PlaylistError(Exception):
    pass


@dataclass(slots=True)
class SavedPlaylist:
    guild_id: int
    owner_id: int
    name: str
    updated_at: str
    tracks: list[dict[str, Any]]

    @property
    def track_count(self) -> int:
        return len(self.tracks)


def slugify(name: str) -> str:
    cleaned = name.strip().lower()
    slug = _SLUG_RE.sub("-", cleaned).strip("-")
    return slug[:MAX_NAME_LENGTH]


def _guild_dir(guild_id: int) -> Path:
    return PLAYLISTS_ROOT / str(guild_id)


def _playlist_path(guild_id: int, slug: str) -> Path:
    return _guild_dir(guild_id) / f"{slug}.json"


def _validate_name(name: str) -> tuple[str, str]:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise PlaylistError("Podaj nazwę playlisty.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise PlaylistError(f"Nazwa może mieć max {MAX_NAME_LENGTH} znaków.")
    slug = slugify(cleaned)
    if not slug:
        raise PlaylistError("Nazwa musi zawierać litery lub cyfry.")
    return cleaned, slug


def list_playlists(guild_id: int) -> list[SavedPlaylist]:
    folder = _guild_dir(guild_id)
    if not folder.is_dir():
        return []
    items: list[SavedPlaylist] = []
    for path in sorted(folder.glob("*.json")):
        try:
            items.append(load_playlist(guild_id, path.stem))
        except PlaylistError:
            continue
    return items


def load_playlist(guild_id: int, name_or_slug: str) -> SavedPlaylist:
    slug = slugify(name_or_slug)
    path = _playlist_path(guild_id, slug)
    if not path.is_file():
        raise PlaylistError(f"Nie ma playlisty `{name_or_slug}`.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlaylistError("Nie udało się odczytać playlisty.") from exc
    tracks = data.get("tracks") or []
    if not isinstance(tracks, list):
        raise PlaylistError("Uszkodzony plik playlisty.")
    return SavedPlaylist(
        guild_id=int(data.get("guild_id") or guild_id),
        owner_id=int(data.get("owner_id") or 0),
        name=str(data.get("name") or slug),
        updated_at=str(data.get("updated_at") or ""),
        tracks=[t for t in tracks if isinstance(t, dict) and t.get("webpage_url")],
    )


def save_playlist(
    *,
    guild_id: int,
    owner_id: int,
    name: str,
    tracks: list[Track],
    overwrite: bool = True,
) -> SavedPlaylist:
    cleaned, slug = _validate_name(name)
    path = _playlist_path(guild_id, slug)
    folder = _guild_dir(guild_id)
    folder.mkdir(parents=True, exist_ok=True)

    if path.exists() and not overwrite:
        raise PlaylistError(f"Playlista `{cleaned}` już istnieje. Użyj `/playlist save`, żeby nadpisać.")

    existing = [p for p in folder.glob("*.json") if p != path]
    if not path.exists() and len(existing) >= MAX_PLAYLISTS_PER_GUILD:
        raise PlaylistError(f"Limit playlist na serwerze: {MAX_PLAYLISTS_PER_GUILD}.")

    if not tracks:
        raise PlaylistError("Nie ma czego zapisać — kolejka jest pusta.")

    payload = {
        "guild_id": guild_id,
        "owner_id": owner_id,
        "name": cleaned,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tracks": [t.to_dict() for t in tracks],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return SavedPlaylist(
        guild_id=guild_id,
        owner_id=owner_id,
        name=cleaned,
        updated_at=payload["updated_at"],
        tracks=payload["tracks"],
    )


def create_playlist(*, guild_id: int, owner_id: int, name: str) -> SavedPlaylist:
    cleaned, slug = _validate_name(name)
    path = _playlist_path(guild_id, slug)
    folder = _guild_dir(guild_id)
    folder.mkdir(parents=True, exist_ok=True)

    if path.exists():
        raise PlaylistError(f"Playlista `{cleaned}` już istnieje.")

    existing = list(folder.glob("*.json"))
    if len(existing) >= MAX_PLAYLISTS_PER_GUILD:
        raise PlaylistError(f"Limit playlist na serwerze: {MAX_PLAYLISTS_PER_GUILD}.")

    payload = {
        "guild_id": guild_id,
        "owner_id": owner_id,
        "name": cleaned,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tracks": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return SavedPlaylist(
        guild_id=guild_id,
        owner_id=owner_id,
        name=cleaned,
        updated_at=payload["updated_at"],
        tracks=[],
    )


def append_tracks(guild_id: int, name: str, tracks: list[Track], *, max_tracks: int) -> SavedPlaylist:
    if not tracks:
        raise PlaylistError("Brak utworów do dodania.")
    saved = load_playlist(guild_id, name)
    existing_urls = {str(t.get("webpage_url")) for t in saved.tracks}
    added = 0
    for track in tracks:
        if len(saved.tracks) >= max_tracks:
            break
        if track.webpage_url in existing_urls:
            continue
        saved.tracks.append(track.to_dict())
        existing_urls.add(track.webpage_url)
        added += 1
    if added == 0:
        raise PlaylistError("Nic nie dodałem (duplikaty albo limit utworów).")

    payload = {
        "guild_id": saved.guild_id,
        "owner_id": saved.owner_id,
        "name": saved.name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tracks": saved.tracks,
    }
    path = _playlist_path(guild_id, slugify(saved.name))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    saved.updated_at = payload["updated_at"]
    return saved


def delete_playlist(guild_id: int, name: str) -> str:
    saved = load_playlist(guild_id, name)
    path = _playlist_path(guild_id, slugify(saved.name))
    try:
        path.unlink()
    except OSError as exc:
        raise PlaylistError("Nie udało się usunąć playlisty.") from exc
    return saved.name
