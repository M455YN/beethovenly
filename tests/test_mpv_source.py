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
    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    cmd = src._ytdlp_command()
    assert cmd[1:3] == ["-m", "yt_dlp"]
    assert "-o" in cmd and cmd[cmd.index("-o") + 1] == "-"
    assert "--cookies" in cmd
    assert cmd[cmd.index("--cookies") + 1] == "/app/data/cookies.txt"
    assert "--js-runtimes" in cmd and "deno" in cmd
    assert "--remote-components" in cmd and "ejs:github" in cmd
    assert "--extractor-args" in cmd
    args = cmd[cmd.index("--extractor-args") + 1]
    assert "mweb" in args
    assert "android_vr" not in args
    assert cmd[-1] == "https://www.youtube.com/watch?v=dQw4w9wgGcQ"


def test_ytdlp_command_anon_uses_android_vr(monkeypatch) -> None:
    monkeypatch.setattr(
        "bot.audio.mpv_source.settings",
        SimpleNamespace(cookies_file=None, cookies_from_browser=None),
    )
    monkeypatch.setattr(
        "bot.audio.youtube_opts.settings",
        SimpleNamespace(cookies_file=None, cookies_from_browser=None),
    )
    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    cmd = src._ytdlp_command()
    args = cmd[cmd.index("--extractor-args") + 1]
    assert "android_vr" in args
