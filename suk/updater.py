"""Update checker.

Fetches the version string from the canonical pyproject.toml on GitHub and
prints a notice when a newer release exists.  It never installs anything:
running ``pip install`` from a background thread mutates the user's
environment and executes unpinned code.
"""

import re
import sys
import threading
import urllib.request
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Optional

GITHUB_RAW_VERSION = (
    "https://raw.githubusercontent.com/forshaur/suk/main/suk/__init__.py"
)
GITHUB_RAW_TOML = (
    "https://raw.githubusercontent.com/forshaur/suk/main/pyproject.toml"
)


def _current_version() -> Optional[str]:
    try:
        return pkg_version("suk")
    except PackageNotFoundError:
        try:
            from suk import __version__

            return __version__
        except Exception:
            return None


def _read(url: str) -> Optional[str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.read().decode("utf-8", "replace")
    except Exception:
        return None


def _fetch_remote_version() -> Optional[str]:
    """Read the remote version from ``suk/__init__.py`` or ``pyproject.toml``."""
    text = _read(GITHUB_RAW_VERSION)
    if text:
        match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if match:
            return match.group(1)

    text = _read(GITHUB_RAW_TOML)
    if text:
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if match:
            return match.group(1)
    return None


def _version_tuple(value: str):
    """Convert '1.2.3' -> (1, 2, 3) for comparison."""
    try:
        return tuple(int(part) for part in value.split("."))
    except Exception:
        return (0,)


def check_now() -> dict:
    """Return the current version, remote version, and whether an update exists."""
    current = _current_version()
    remote = _fetch_remote_version()
    newer = bool(
        current and remote and _version_tuple(remote) > _version_tuple(current)
    )
    return {"current": current, "remote": remote, "newer": newer}


def check_for_updates() -> threading.Thread:
    """Spawn a background thread that checks GitHub and prints a notice."""

    def _check():
        result = check_now()
        if result["newer"]:
            print(
                f"\n  ↑ suk {result['current']} → {result['remote']} is available. "
                f"Upgrade with: pip install --upgrade suk\n",
                file=sys.stderr,
            )

    thread = threading.Thread(target=_check, daemon=True)
    thread.start()
    return thread
