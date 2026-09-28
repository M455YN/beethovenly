from __future__ import annotations

import logging
import os
from typing import Any

from bot.config import settings

log = logging.getLogger("beethovenly.youtube")

# Prefer anon clients that work with bgutil pot-provider / HLS.
# android_vr often needs GVS PO now; web_safari HLS frequently does not.
_PLAYER_CLIENTS_WITH_COOKIES = ["mweb", "tv", "web_safari", "web"]
_PLAYER_CLIENTS_ANON = ["web_safari", "android_vr", "mweb", "tv"]

DEFAULT_POT_URL = "http://127.0.0.1:4416"


def has_youtube_cookies() -> bool:
    return bool(settings.cookies_file or settings.cookies_from_browser)


def cookies_look_usable() -> bool:
    """True only when cookies are explicitly enabled and look like a real session.

    Bad/rotated dumps make yt-dlp return *Sign in to confirm you're not a bot*.
    Default is off — set ``YOUTUBE_USE_COOKIES=1`` plus a good ``COOKIES_FILE``.
    pot-provider (``YOUTUBE_POT_BASE_URL``) is the normal path for server IPs.
    """
    if os.getenv("YOUTUBE_USE_COOKIES", "").strip() not in ("1", "true", "yes", "on"):
        return False
    path = settings.cookies_file
    if not path or not os.path.isfile(path):
        return bool(settings.cookies_from_browser and not settings.cookies_file)
    try:
        raw = open(path, encoding="utf-8", errors="replace").read().lower()
    except OSError:
        return False
    if "youtube.com" not in raw:
        return False
    return "login_info" in raw or "__secure-1psid" in raw or "sapisid" in raw


def pot_provider_base_url() -> str:
    return (os.getenv("YOUTUBE_POT_BASE_URL") or DEFAULT_POT_URL).strip().rstrip("/")


def youtube_player_clients(*, cookies: bool | None = None) -> list[str]:
    if cookies is None:
        use_cookies = cookies_look_usable()
    else:
        use_cookies = cookies
    if use_cookies:
        return list(_PLAYER_CLIENTS_WITH_COOKIES)
    return list(_PLAYER_CLIENTS_ANON)


def ytdlp_extractor_args_cli(*, player_clients: str | None = None, cookies: bool | None = None) -> list[str]:
    """Return ``[--extractor-args, ..., --extractor-args, ...]`` for yt-dlp CLI."""
    clients = player_clients or ",".join(youtube_player_clients(cookies=cookies))
    args = [
        "--extractor-args",
        f"youtube:player_client={clients}",
    ]
    # POT plugin is harmless if the HTTP sidecar is down; skip when unused.
    pot = pot_provider_base_url()
    if pot:
        args.extend(
            [
                "--extractor-args",
                f"youtubepot-bgutilhttp:base_url={pot}",
            ]
        )
    return args


def ytdlp_js_opts() -> dict[str, Any]:
    """Enable Deno + allow fetching EJS scripts if the pip package is missing/outdated."""
    return {
        "js_runtimes": {"deno": {}},
        "remote_components": ["ejs:github"],
    }


def apply_youtube_opts(opts: dict[str, Any], *, force_cookies: bool | None = None) -> dict[str, Any]:
    use_cookies = cookies_look_usable() if force_cookies is None else force_cookies
    opts.update(ytdlp_js_opts())
    extractor_args: dict[str, Any] = {
        "youtube": {"player_client": youtube_player_clients(cookies=use_cookies)},
    }
    pot = pot_provider_base_url()
    if pot:
        extractor_args["youtubepot-bgutilhttp"] = {"base_url": [pot]}
    opts["extractor_args"] = extractor_args
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
        log.info("Deno missing — only needed for cookie/web YouTube clients")

    try:
        import yt_dlp_ejs  # type: ignore

        log.info("yt-dlp-ejs: %s", getattr(yt_dlp_ejs, "__version__", "ok"))
    except ImportError:
        log.info("yt-dlp-ejs not installed — optional (pip install 'yt-dlp[default]')")

    try:
        from importlib.metadata import version

        pot_ver = version("bgutil-ytdlp-pot-provider")
        log.info(
            "PO token plugin: bgutil-ytdlp-pot-provider %s (base %s)",
            pot_ver,
            pot_provider_base_url(),
        )
    except Exception:  # noqa: BLE001
        log.info("bgutil-ytdlp-pot-provider not installed — optional fallback")

    # Probe POT HTTP sidecar (optional compose service).
    try:
        import urllib.request

        url = pot_provider_base_url().rstrip("/") + "/"
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
            log.info("PO token HTTP OK: %s → %s", url, resp.status)
    except Exception as exc:  # noqa: BLE001
        log.info(
            "PO token HTTP not running (%s): %s — fine for mpv+ytdl / anon path",
            pot_provider_base_url(),
            exc,
        )

    if cookies_look_usable():
        log.info("YouTube cookies: ENABLED (YOUTUBE_USE_COOKIES=1)")
    elif settings.cookies_file:
        log.info(
            "YouTube cookies file present but unused — set YOUTUBE_USE_COOKIES=1 only after a valid robots.txt export"
        )
    else:
        log.info("YouTube cookies: off — using pot-provider / anon clients")
