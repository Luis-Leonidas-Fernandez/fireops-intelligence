"""Build public application links from an explicitly configured origin."""

import ipaddress
import re
from urllib.parse import urlsplit

from app.config.settings import Settings
from app.modules.auth.invitations.errors import PublicBaseURLConfigurationError


def _valid_hostname(hostname: str) -> bool:
    if not hostname.isascii() or len(hostname) > 253:
        return False
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if ":" in hostname or re.fullmatch(r"[0-9.]+", hostname):
        return False
    if hostname == "localhost":
        return True
    labels = hostname.split(".")
    return len(labels) > 1 and all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    )


def public_link(settings: Settings, path: str) -> str:
    """Return a link without deriving its origin from an OAuth callback."""
    raw = settings.public_base_url
    if not raw:
        raise PublicBaseURLConfigurationError("PUBLIC_BASE_URL is missing or invalid.")
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname or ""
        port = parsed.port
        authority_host = f"[{hostname}]" if ":" in hostname else hostname
        authority = f"{authority_host}:{port}" if port is not None else authority_host
        valid = (
            parsed.scheme in {"http", "https"}
            and _valid_hostname(hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.netloc == authority
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and "?" not in raw
            and "#" not in raw
            and raw == f"{parsed.scheme}://{parsed.netloc}"
            and not any(ord(character) < 33 or ord(character) == 127 for character in raw)
            and not any(character in raw for character in ("\\", "%", "@"))
            and (port is None or 1 <= port <= 65535)
            and (
                parsed.scheme == "https"
                or (
                    hostname in {"localhost", "127.0.0.1", "::1"}
                    and settings.environment.lower() in {"development", "test", "testing"}
                )
            )
        )
    except ValueError:
        valid = False
    if not valid:
        raise PublicBaseURLConfigurationError("PUBLIC_BASE_URL is missing or invalid.")
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Public link path must be relative to the configured origin.")
    return f"{raw}{path}"
