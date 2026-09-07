from __future__ import annotations

import json
from pathlib import Path

import pytest

from bot.audio.track import Track
from bot.storage import playlists as store


class DummyUser:
    id = 7
    display_name = "Tester"


@pytest.fixture()
def playlist_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "playlists"
    monkeypatch.setattr(store, "PLAYLISTS_ROOT", root)
    return root


def _track(title: str, url: str) -> Track:
    return Track(
        title=title,
        webpage_url=url,
        webpage_id="id",
        uploader="Uploader",
        duration=120.0,
        thumbnail=None,
        extractor="Youtube",
        is_live=False,
        requester_id=7,
        requester_name="Tester",
        source_query=url,
    )


def test_create_save_load_delete(playlist_root: Path) -> None:
    created = store.create_playlist(guild_id=1, owner_id=7, name="Chill Mix")
    assert created.track_count == 0
    assert (playlist_root / "1" / "chill-mix.json").is_file()

    tracks = [_track("A", "https://youtu.be/a"), _track("B", "https://youtu.be/b")]
    saved = store.save_playlist(guild_id=1, owner_id=7, name="Chill Mix", tracks=tracks)
    assert saved.track_count == 2

    loaded = store.load_playlist(1, "chill mix")
    assert loaded.name == "Chill Mix"
    assert len(loaded.tracks) == 2

    restored = [Track.from_dict(t, requester=DummyUser()) for t in loaded.tracks]  # type: ignore[arg-type]
    assert restored[0].title == "A"
    assert restored[1].webpage_url.endswith("/b")

    names = [p.name for p in store.list_playlists(1)]
    assert names == ["Chill Mix"]

    deleted = store.delete_playlist(1, "Chill Mix")
    assert deleted == "Chill Mix"
    assert store.list_playlists(1) == []


def test_append_skips_duplicates(playlist_root: Path) -> None:
    store.create_playlist(guild_id=2, owner_id=7, name="gym")
    t1 = _track("One", "https://youtu.be/1")
    store.append_tracks(2, "gym", [t1], max_tracks=50)
    saved = store.append_tracks(2, "gym", [t1, _track("Two", "https://youtu.be/2")], max_tracks=50)
    assert saved.track_count == 2
    data = json.loads((playlist_root / "2" / "gym.json").read_text(encoding="utf-8"))
    assert len(data["tracks"]) == 2


def test_track_roundtrip() -> None:
    original = _track("Nightcall", "https://www.youtube.com/watch?v=abc")
    again = Track.from_dict(original.to_dict(), requester=DummyUser())  # type: ignore[arg-type]
    assert again.title == original.title
    assert again.webpage_url == original.webpage_url
    assert again.requester_id == 7
