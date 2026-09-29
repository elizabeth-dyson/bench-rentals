"""Pure validation for the reusable public inquiry URL; no I/O or UI state."""

import re
from ipaddress import ip_address
from urllib.parse import urlsplit


def validate_public_inquiry_url(value: str | None) -> str | None:
    """Trim and validate a full HTTPS URL; missing configuration returns None.

    Invalid configuration raises ValueError without including the supplied value.
    Validation does not check reachability or whether the public form is ready.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("The public inquiry URL must be text.")
    url = value.strip()
    if not url:
        return None
    if (
        any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in url)
        or any(character in url for character in ("?", "#", "\\"))
        or re.search(r"%(?![0-9a-fA-F]{2})", url)
    ):
        raise ValueError("The public inquiry URL must not contain whitespace, queries, or fragments.")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port  # Access validates malformed or out-of-range ports.
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.netloc.endswith(":")
            or port == 0
        ):
            raise ValueError
        try:
            ip_address(host)
        except ValueError:
            hostname = host.encode("idna").decode("ascii").rstrip(".")
            if len(hostname) > 253 or not all(
                re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                for label in hostname.split(".")
            ):
                raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError("Enter an absolute HTTPS inquiry URL without credentials.") from None
    return url
