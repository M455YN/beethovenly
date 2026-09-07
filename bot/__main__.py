from __future__ import annotations

import logging
import shutil
import sys

from bot.bot import create_bot
from bot.config import settings


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.player").setLevel(logging.INFO)
    logging.getLogger("yt_dlp").setLevel(logging.WARNING)


def main() -> None:
    configure_logging()
    log = logging.getLogger("beethovenly")
    if not settings.token:
        log.error(
            "Brak DISCORD_TOKEN. Skopiuj .env.example do .env i wklej token bota.\n"
            "Developer Portal → Applications → Bot → Reset Token. "
            "Wystarczą domyślne intenty + Voice (Connect / Speak)."
        )
        sys.exit(1)
    missing = [name for name in ("mpv", "yt-dlp") if shutil.which(name) is None]
    if missing:
        log.error("Brak programów w PATH: %s. W Dockerze są w obrazie, lokalnie doinstaluj je sam.", ", ".join(missing))
        sys.exit(1)
    bot = create_bot()
    bot.run(settings.token, log_handler=None)


if __name__ == "__main__":
    main()
