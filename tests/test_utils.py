from bot.audio.track import LoopMode
from bot.utils import format_duration, is_http_url, progress_slider, truncate


def test_truncate_short() -> None:
    assert truncate("abc", 10) == "abc"


def test_truncate_long() -> None:
    assert truncate("abcdefghij", 6) == "abcde…"
    assert len(truncate("abcdefghij", 6)) == 6


def test_format_duration() -> None:
    assert format_duration(None) == "?:??"
    assert format_duration(0) == "0:00"
    assert format_duration(65) == "1:05"
    assert format_duration(3723) == "1:02:03"


def test_progress_slider_bounds() -> None:
    bar = progress_slider(0, 100, width=10)
    assert bar.startswith("●")
    assert len(bar) == 10
    end = progress_slider(100, 100, width=10)
    assert end.endswith("●")
    empty = progress_slider(0, None, width=8)
    assert empty == "────────"


def test_is_http_url() -> None:
    assert is_http_url("https://youtube.com/watch?v=1")
    assert not is_http_url("never gonna give you up")


def test_loop_mode_cycle() -> None:
    assert LoopMode.OFF.next() is LoopMode.ALL
    assert LoopMode.ALL.next() is LoopMode.ONE
    assert LoopMode.ONE.next() is LoopMode.OFF
    assert LoopMode.ALL.label() == "kolejka"
    assert LoopMode.ONE.emoji() == "🔂"
