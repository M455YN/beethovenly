from __future__ import annotations

from typing import Any

from bot.config import settings

# Cookies + android_vr currently triggers YouTube "The page needs to be reloaded".
# With cookies we rely on web/mweb clients + Deno/EJS nsig solve instead.
_PLAYER_CLIENTS_WITH_COOKIES = ["mweb", "web_safari", "tv", "web"]
_PLAYER_CLIENTS_ANON = ["android_vr", "tv", "web_safari"]


def has_youtube_cookies() -> bool:
    return bool(settings.cookies_file or settings.cookies_from_browser)


def youtube_player_clients() -> list[str]:
    if has_youtube_cookies():
        return list(_PLAYER_CLIENTS_WITH_COOKIES)
    return list(_PLAYER_CLIENTS_ANON)


def youtube_extractor_args_cli() -> str:
    clients = ",".join(youtube_player_clients())
    return f"youtube:player_client={clients}"


def ytdlp_js_opts() -> dict[str, Any]:
    """Enable Deno + allow fetching EJS scripts if the pip package is missing/outdated."""
    return {
        "js_runtimes": {"deno": {}},
        "remote_components": ["ejs:github"],
    }


def apply_youtube_opts(opts: dict[str, Any]) -> dict[str, Any]:
    opts.update(ytdlp_js_opts())
    opts["extractor_args"] = {"youtube": {"player_client": youtube_player_clients()}}
    return opts
