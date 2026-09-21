from __future__ import annotations

import re

# Same shape as yt-dlp's --cookies-from-browser parser.
_BROWSER_SPEC_RE = re.compile(
    r"""(?x)
    (?P<name>[^+:]+)
    (?:\s*\+\s*(?P<keyring>[^:]+))?
    (?:\s*:\s*(?!:)(?P<profile>.+?))?
    (?:\s*::\s*(?P<container>.+))?
    """
)


def parse_cookies_from_browser(
    spec: str,
) -> tuple[str, str | None, str | None, str | None]:
    """Parse ``BROWSER[+KEYRING][:PROFILE][::CONTAINER]`` into a yt-dlp tuple."""
    mobj = _BROWSER_SPEC_RE.fullmatch(spec.strip())
    if mobj is None:
        raise ValueError(f"invalid COOKIES_FROM_BROWSER: {spec!r}")
    browser_name, keyring, profile, container = mobj.group(
        "name", "keyring", "profile", "container"
    )
    browser_name = browser_name.lower()
    if keyring is not None:
        keyring = keyring.upper()
    return browser_name, profile, keyring, container
