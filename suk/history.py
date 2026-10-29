"""
Local email history store.

Emails are persisted in ``$SUK_HOME/.suk_history.json`` (``$HOME`` by
default), keyed by mailbox address.  Each entry is a list of message dicts
(most-recent-first).
"""

import json
import time
from typing import Optional

from suk import paths


def _load() -> dict:
    path = paths.history_file()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}


def _save(data: dict):
    paths.atomic_write(
        paths.history_file(),
        json.dumps(data, indent=2, ensure_ascii=False),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def get_history(mailbox: str) -> list:
    """Return the stored messages for *mailbox* (oldest-first)."""
    data = _load()
    bucket = data.get(mailbox, [])
    if not isinstance(bucket, list):
        return []
    return [message for message in reversed(bucket) if isinstance(message, dict)]


def save_message(mailbox: str, msg_id: str, sender: str,
                 subject: str, body: str, html: Optional[str] = None):
    """Persist a single message for *mailbox*. Skip duplicate ids."""
    data = _load()
    bucket = data.setdefault(mailbox, [])
    if not isinstance(bucket, list):
        bucket = []
        data[mailbox] = bucket
    if any(isinstance(m, dict) and m.get("id") == msg_id for m in bucket):
        return
    msg_entry = {          # most-recent-first
        "id":          msg_id,
        "from":        sender,
        "subject":     subject,
        "body":        body,
        "received_at": time.time(),
    }
    if html is not None:
        msg_entry["html"] = html
    bucket.insert(0, msg_entry)
    _save(data)


def shred_history(mailbox: Optional[str] = None):
    """Delete history for all mailboxes, or only *mailbox*."""
    if mailbox is None:
        _save({})
    else:
        data = _load()
        data.pop(mailbox, None)
        _save(data)


def shred_all():
    """Delete the history file entirely."""
    path = paths.history_file()
    if path.exists():
        path.unlink()
