from types import SimpleNamespace

from bot.audio.mpv_source import FRAME_SIZE, MPVPCMSource


def test_frame_size_is_20ms_pcm() -> None:
    # 20 ms * 48000 * 2 channels * 2 bytes
    assert FRAME_SIZE == 3840


def test_mpv_command_reads_stdin_pcm() -> None:
    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    cmd = src._mpv_command()
    assert cmd[0] == "mpv"
    assert "--ao=pcm" in cmd
    assert "--ao-pcm-waveheader=no" in cmd
    assert "--ao-pcm-file=/dev/stdout" in cmd
    assert "--audio-samplerate=48000" in cmd
    assert "--ytdl=no" in cmd
    assert cmd[-1] == "-"


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
    strategy = _StreamStrategy("cookies+mweb", "mweb,tv,web_safari,web", True)
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
    strategy = _StreamStrategy("anon+android_vr", "android_vr,tv,web_safari", False)
    cmd = src._ytdlp_command(strategy)
    assert "--cookies" not in cmd
    assert any("android_vr" in a for a in cmd)
