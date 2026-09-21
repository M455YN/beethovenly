from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from bot.cookies import parse_cookies_from_browser

load_dotenv()

log = logging.getLogger("beethovenly")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    token: str
    command_guild_id: int | None
    bot_status: str
    idle_disconnect_seconds: int
    playlist_limit: int
    cookies_file: str | None
    cookies_from_browser: str | None
    cookies_from_browser_tuple: tuple[str, str | None, str | None, str | None] | None

    @classmethod
    def load(cls) -> Settings:
        token = os.getenv("DISCORD_TOKEN", "").strip()
        guild_raw = os.getenv("COMMAND_GUILD_ID", "").strip()
        cookies_raw = os.getenv("COOKIES_FILE", "").strip() or None
        cookies: str | None = cookies_raw
        if cookies_raw and not os.path.isfile(cookies_raw):
            log.warning(
                "COOKIES_FILE is set to %r but the file is missing or unreadable — "
                "YouTube may block extraction. Mount cookies at that path inside the container.",
                cookies_raw,
            )
            cookies = None

        browser_raw = os.getenv("COOKIES_FROM_BROWSER", "").strip() or None
        browser_tuple = None
        if browser_raw:
            try:
                browser_tuple = parse_cookies_from_browser(browser_raw)
            except ValueError as exc:
                log.warning("%s — ignoring COOKIES_FROM_BROWSER", exc)
                browser_raw = None

        return cls(
            token=token,
            command_guild_id=int(guild_raw) if guild_raw else None,
            bot_status=os.getenv("BOT_STATUS", "/play • beethovenly").strip() or "/play • beethovenly",
            idle_disconnect_seconds=max(0, _int_env("IDLE_DISCONNECT_SECONDS", 300)),
            playlist_limit=max(1, min(_int_env("PLAYLIST_LIMIT", 50), 200)),
            cookies_file=cookies,
            cookies_from_browser=browser_raw,
            cookies_from_browser_tuple=browser_tuple,
        )


settings = Settings.load()
