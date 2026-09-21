from __future__ import annotations

import pytest

from bot.cookies import parse_cookies_from_browser


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("chrome", ("chrome", None, None, None)),
        ("firefox", ("firefox", None, None, None)),
        (
            "chrome:~/.var/app/com.google.Chrome/",
            ("chrome", "~/.var/app/com.google.Chrome/", None, None),
        ),
        ("chrome+gnomekeyring:/chrome-profile", ("chrome", "/chrome-profile", "GNOMEKEYRING", None)),
        ("firefox:abcd.default-release", ("firefox", "abcd.default-release", None, None)),
    ],
)
def test_parse_cookies_from_browser(spec: str, expected: tuple) -> None:
    assert parse_cookies_from_browser(spec) == expected


def test_parse_cookies_from_browser_invalid() -> None:
    with pytest.raises(ValueError):
        parse_cookies_from_browser("")
    with pytest.raises(ValueError):
        parse_cookies_from_browser("+++")
