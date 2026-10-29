"""State paths and safe file writes.

State lives in ``$HOME`` by default.  Set ``SUK_HOME`` to isolate sessions,
history, and legacy state in another directory (useful for tests and agents).
"""

import os
import tempfile
from pathlib import Path


def state_dir() -> Path:
    """Return the directory that holds suk state."""
    root = os.environ.get("SUK_HOME")
    if root:
        return Path(root).expanduser()
    return Path.home()


def ensure_state_dir() -> Path:
    """Create ``SUK_HOME`` when set and make it owner-only."""
    root = os.environ.get("SUK_HOME")
    if not root:
        return Path.home()
    directory = Path(root).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory


def sessions_file() -> Path:
    return state_dir() / ".suk_sessions.json"


def history_file() -> Path:
    return state_dir() / ".suk_history.json"


def legacy_file() -> Path:
    return state_dir() / ".otp_mailbox.json"


def atomic_write(path: Path, text: str) -> None:
    """Write *text* to *path* atomically with mode 0600.

    A sibling temp file is flushed, fsynced, chmodded, then replaced.  This
    prevents partial JSON on crash and keeps tokens owner-only.
    """
    path = Path(path)
    if path.is_symlink():
        raise OSError(f"refusing to write through symlink: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
