from types import SimpleNamespace

from bot.audio.mpv_source import FRAME_SIZE, MPVPCMSource, _STRATEGIES


def test_frame_size_is_20ms_pcm() -> None:
    # 20 ms * 48000 * 2 channels * 2 bytes
    assert FRAME_SIZE == 3840


def test_strategies_prefer_mpv_ytdl_then_anon() -> None:
    assert _STRATEGIES[0].mode == "mpv_ytdl"
    pipe = [s for s in _STRATEGIES if s.mode == "ytdlp_pipe"]
    assert pipe[0].use_cookies is False
    assert any(s.use_cookies for s in pipe)


def test_mpv_command_pipe_reads_stdin_pcm() -> None:
    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    cmd = src._mpv_command(from_stdin=True)
    assert cmd[0] == "mpv"
    assert "--ao=pcm" in cmd
    assert "--ao-pcm-waveheader=no" in cmd
    assert "--ao-pcm-file=/dev/stdout" in cmd
    assert "--audio-samplerate=48000" in cmd
    assert "--ytdl=no" in cmd
    assert cmd[-1] == "-"


def test_mpv_command_direct_uses_ytdl_like_wagner() -> None:
    url = "https://www.youtube.com/watch?v=dQw4w9wgGcQ"
    src = MPVPCMSource(url)
    cmd = src._mpv_command(from_stdin=False)
    assert cmd[0] == "mpv"
    assert "--ao=pcm" in cmd
    assert "--ytdl=yes" in cmd
    assert "--ytdl=no" not in cmd
    assert cmd[-1] == url


def test_ytdlp_command_streams_stdout_with_cookies(monkeypatch) -> None:
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
    strategy = _StreamStrategy("cookies+mweb", "ytdlp_pipe", "mweb,tv,web_safari,web", True)
    cmd = src._ytdlp_command(strategy)
    assert cmd[1:3] == ["-m", "yt_dlp"]
    assert "-o" in cmd and cmd[cmd.index("-o") + 1] == "-"
    assert "--cookies" in cmd
    assert cmd[cmd.index("--cookies") + 1] == "/app/data/cookies.txt"
    assert "--js-runtimes" in cmd and "deno" in cmd
    assert "--remote-components" in cmd and "ejs:github" in cmd
    assert any("youtubepot-bgutilhttp" in a for a in cmd)
    assert any("player_client=mweb" in a for a in cmd)
    assert cmd[-1] == "https://www.youtube.com/watch?v=dQw4w9wgGcQ"


def test_ytdlp_command_anon_omits_cookies(monkeypatch) -> None:
    monkeypatch.setattr(
        "bot.audio.mpv_source.settings",
        SimpleNamespace(cookies_file="/app/data/cookies.txt", cookies_from_browser=None),
    )
    from bot.audio.mpv_source import _StreamStrategy

    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    strategy = _StreamStrategy("anon+android_vr", "ytdlp_pipe", "android_vr,tv,web_safari", False)
    cmd = src._ytdlp_command(strategy)
    assert "--cookies" not in cmd
    assert any("android_vr" in a for a in cmd)


def test_available_strategies_skip_cookies_when_unusable(monkeypatch) -> None:
    monkeypatch.setattr("bot.audio.mpv_source.cookies_look_usable", lambda: False)
    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    names = [s.name for s in src._available_strategies()]
    assert "mpv+ytdl" in names
    assert "anon+android_vr" in names
    assert not any(n.startswith("cookies+") for n in names)
