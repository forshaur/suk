"""
Auto-update checker.

Fetches the version string from the canonical pyproject.toml on GitHub
(raw content, no API auth required).  If the remote version is greater than
the locally installed version, upgrades via pip and prints a notice.

Runs in a background daemon thread so it never blocks startup.
"""

import re
import subprocess
import sys
import threading
from importlib.metadata import version as pkg_version, PackageNotFoundError
from typing import Optional

import requests as _requests

GITHUB_RAW_TOML = (
    "https://raw.githubusercontent.com/forshaur/suk/main/pyproject.toml"
)


def _current_version() -> Optional[str]:
    try:
        return pkg_version("suk")
    except PackageNotFoundError:
        return None


def _fetch_remote_version() -> Optional[str]:
    """Pull the raw pyproject.toml from GitHub and extract the version string."""
    try:
        r = _requests.get(GITHUB_RAW_TOML, timeout=5)
        r.raise_for_status()
        m = re.search(r'^version\s*=\s*"([^"]+)"', r.text, re.MULTILINE)
        return m.group(1) if m else None
    except Exception:
        return None


def _version_tuple(v: str):
    """Convert '1.2.3' → (1, 2, 3) for comparison."""
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def _do_upgrade():
    current = _current_version()
    remote  = _fetch_remote_version()

    if not current or not remote:
        return

    if _version_tuple(remote) <= _version_tuple(current):
        return

    # Remote is newer — upgrade silently, then print a one-line notice
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "suk"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Print after install so it appears below the startup header
        print(
            f"\n  ↑ Updated suk {current} → {remote}. "
            f"Restart to use the new version.\n"
        )
    except Exception:
        pass


def check_for_updates() -> threading.Thread:
    """Spawn a background thread that checks GitHub and upgrades if needed."""
    t = threading.Thread(target=_do_upgrade, daemon=True)
    t.start()
    return t