from bot.audio.mpv_source import FRAME_SIZE, MPVPCMSource


def test_frame_size_is_20ms_pcm() -> None:
    # 20 ms * 48000 * 2 channels * 2 bytes
    assert FRAME_SIZE == 3840


def test_mpv_command_is_pcm_stdout() -> None:
    src = MPVPCMSource("https://www.youtube.com/watch?v=dQw4w9wgGcQ")
    cmd = src._command()
    assert cmd[0] == "mpv"
    assert "--ao=pcm" in cmd
    assert "--ao-pcm-waveheader=no" in cmd
    assert "--ao-pcm-file=/dev/stdout" in cmd
    assert "--audio-samplerate=48000" in cmd
    assert "--ytdl=yes" in cmd
    assert cmd[-1].startswith("https://")
