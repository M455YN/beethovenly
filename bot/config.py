from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


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

    @classmethod
    def load(cls) -> Settings:
        token = os.getenv("DISCORD_TOKEN", "").strip()
        guild_raw = os.getenv("COMMAND_GUILD_ID", "").strip()
        cookies = os.getenv("COOKIES_FILE", "").strip() or None
        if cookies and not os.path.isfile(cookies):
            cookies = None
        return cls(
            token=token,
            command_guild_id=int(guild_raw) if guild_raw else None,
            bot_status=os.getenv("BOT_STATUS", "/play • beethovenly").strip() or "/play • beethovenly",
            idle_disconnect_seconds=max(0, _int_env("IDLE_DISCONNECT_SECONDS", 300)),
            playlist_limit=max(1, min(_int_env("PLAYLIST_LIMIT", 50), 200)),
            cookies_file=cookies,
        )


settings = Settings.load()
