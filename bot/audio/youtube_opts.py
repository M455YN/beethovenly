from __future__ import annotations

import logging
import os
from typing import Any

from bot.config import settings

log = logging.getLogger("beethovenly.youtube")

# Cookies + android_vr → "The page needs to be reloaded".
# With cookies use web/mweb + Deno/EJS + PO token provider.
_PLAYER_CLIENTS_WITH_COOKIES = ["mweb", "tv", "web_safari", "web"]
_PLAYER_CLIENTS_ANON = ["android_vr", "tv", "web_safari"]

DEFAULT_POT_URL = "http://127.0.0.1:4416"


def has_youtube_cookies() -> bool:
    return bool(settings.cookies_file or settings.cookies_from_browser)


def pot_provider_base_url() -> str:
    return (os.getenv("YOUTUBE_POT_BASE_URL") or DEFAULT_POT_URL).strip().rstrip("/")


def youtube_player_clients(*, cookies: bool | None = None) -> list[str]:
    use_cookies = has_youtube_cookies() if cookies is None else cookies
    if use_cookies:
        return list(_PLAYER_CLIENTS_WITH_COOKIES)
    return list(_PLAYER_CLIENTS_ANON)


def ytdlp_extractor_args_cli(*, player_clients: str | None = None, cookies: bool | None = None) -> list[str]:
    """Return ``[--extractor-args, ..., --extractor-args, ...]`` for yt-dlp CLI."""
    clients = player_clients or ",".join(youtube_player_clients(cookies=cookies))
    return [
        "--extractor-args",
        f"youtube:player_client={clients}",
        "--extractor-args",
        f"youtubepot-bgutilhttp:base_url={pot_provider_base_url()}",
    ]


def ytdlp_js_opts() -> dict[str, Any]:
    """Enable Deno + allow fetching EJS scripts if the pip package is missing/outdated."""
    return {
        "js_runtimes": {"deno": {}},
        "remote_components": ["ejs:github"],
    }


def apply_youtube_opts(opts: dict[str, Any]) -> dict[str, Any]:
    opts.update(ytdlp_js_opts())
    opts["extractor_args"] = {
        "youtube": {"player_client": youtube_player_clients()},
        "youtubepot-bgutilhttp": {"base_url": [pot_provider_base_url()]},
    }
    return opts


def log_youtube_runtime_status() -> None:
    """Emit one-shot diagnostics for Deno / EJS / cookies quality."""
    import shutil
    import subprocess

    deno = shutil.which("deno")
    if deno:
        try:
            ver = subprocess.check_output([deno, "--version"], text=True, timeout=5).splitlines()[0]
            log.info("Deno: %s (%s)", ver, deno)
        except Exception as exc:  # noqa: BLE001
            log.warning("Deno found but failed to run: %s", exc)
    else:
        log.warning("Deno missing — YouTube EJS challenges will fail")

    try:
        import yt_dlp_ejs  # type: ignore

        log.info("yt-dlp-ejs: %s", getattr(yt_dlp_ejs, "__version__", "ok"))
    except ImportError:
        log.warning("yt-dlp-ejs not installed — pip install 'yt-dlp[default]'")

    try:
        import bgutil_ytdlp_pot_provider  # type: ignore  # noqa: F401

        log.info("PO token plugin: bgutil-ytdlp-pot-provider (base %s)", pot_provider_base_url())
    except ImportError:
        log.warning("bgutil-ytdlp-pot-provider not installed — bot-check more likely on server IPs")

    if settings.cookies_file and os.path.isfile(settings.cookies_file):
        try:
            raw = open(settings.cookies_file, encoding="utf-8", errors="replace").read().lower()
        except OSError:
            return
        markers = ("login_info", "__secure-1psid", "sapisid", "sid")
        present = [m for m in markers if m in raw]
        missing = [m for m in markers if m not in present]
        log.info("cookie markers present=%s missing=%s", present or "none", missing or "none")
        if "login_info" not in present and "__secure-1psid" not in present:
            log.warning(
                "cookies look anonymous — open Chromium UI, log into YouTube, restart beethovenly"
            )
