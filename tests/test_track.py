from bot.audio.track import track_from_info
from bot.audio.ytdlp import _absolute_url


class DummyUser:
    id = 42
    display_name = "Ania"


def test_track_from_info() -> None:
    track = track_from_info(
        {
            "title": "Nightcall",
            "webpage_url": "https://www.youtube.com/watch?v=abc",
            "id": "abc",
            "uploader": "Kavinsky",
            "duration": 255,
            "thumbnail": "https://i.ytimg.com/vi/abc/hqdefault.jpg",
            "extractor_key": "Youtube",
        },
        requester=DummyUser(),  # type: ignore[arg-type]
        query="nightcall",
    )
    assert track.display_title == "Nightcall"
    assert track.requester_id == 42
    assert track.duration == 255
    assert track.to_choice_label(1).startswith("1. ")


def test_absolute_youtube_id() -> None:
    url = _absolute_url({"id": "dQw4w9wgGcQ", "ie_key": "Youtube", "url": "dQw4w9wgGcQ"})
    assert url == "https://www.youtube.com/watch?v=dQw4w9wgGcQ"


def test_absolute_keeps_https() -> None:
    src = "https://soundcloud.com/artist/track"
    assert _absolute_url({"webpage_url": src}) == src
