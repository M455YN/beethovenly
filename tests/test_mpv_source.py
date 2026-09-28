from types import SimpleNamespace

from bot.audio.mpv_source import FRAME_SIZE, MPVPCMSource, _STRATEGIES


def test_frame_size_is_20ms_pcm() -> None:
    assert FRAME_SIZE == 3840


def test_strategies_prefer_anon_web_safari() -> None:
    assert _STRATEGIES[0].name == "anon+web_safari"
    assert _STRATEGIES[0].use_cookies is False
    assert not any(s.name == "cookies+android_vr" for s in _STRATEGIES)


def test_mpv_command_plays_resolved_url() -> None:
    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    media = "https://googlevideo.com/videoplayback?id=1"
    cmd = src._mpv_command(media)
    assert cmd[0] == "mpv"
    assert "--ao=pcm" in cmd
    assert "--ytdl=no" in cmd
    assert cmd[-1] == media


def test_ytdlp_base_with_cookies(monkeypatch) -> None:
    monkeypatch.setattr(
        "bot.audio.mpv_source.settings",
        SimpleNamespace(cookies_file="/app/data/cookies.txt", cookies_from_browser=None),
    )
    monkeypatch.setattr(
        "bot.audio.youtube_opts.settings",
        SimpleNamespace(cookies_file="/app/data/cookies.txt", cookies_from_browser=None),
    )
    from bot.audio.mpv_source import _StreamStrategy

    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    strategy = _StreamStrategy("cookies+mweb", "mweb,web_safari,web", True)
    cmd = src._ytdlp_base(strategy)
    assert cmd[1:3] == ["-m", "yt_dlp"]
    assert "--cookies" in cmd
    assert cmd[cmd.index("--cookies") + 1] == "/app/data/cookies.txt"
    assert any("player_client=mweb" in a for a in cmd)


def test_ytdlp_base_anon_omits_cookies(monkeypatch) -> None:
    monkeypatch.setattr(
        "bot.audio.mpv_source.settings",
        SimpleNamespace(cookies_file="/app/data/cookies.txt", cookies_from_browser=None),
    )
    from bot.audio.mpv_source import _StreamStrategy

    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    strategy = _StreamStrategy("anon+android_vr", "android_vr,tv", False)
    cmd = src._ytdlp_base(strategy)
    assert "--cookies" not in cmd
    assert any("android_vr" in a for a in cmd)


def test_available_strategies_skip_cookies_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr("bot.audio.mpv_source.cookies_look_usable", lambda: False)
    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    names = [s.name for s in src._available_strategies()]
    assert "anon+web_safari" in names
    assert not any(n.startswith("cookies+") for n in names)
