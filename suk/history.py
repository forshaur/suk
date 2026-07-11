"""
Local email history store.

Emails are persisted in ~/.suk_history.json, keyed by mailbox address.
Each entry is a list of message dicts (most-recent-first).

Layout:
    {
      "abc@domain.com": [
        {
          "id":          "<message _id from API>",
          "from":        "sender@example.com",
          "subject":     "Hello",
          "body":        "Plain-text body ...",
          "received_at": 1720700000.0   (Unix timestamp)
        },
        ...
      ],
      ...
    }
"""

import json
import time
from pathlib import Path
from typing import Optional

HISTORY_FILE = Path.home() / ".suk_history.json"


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            pass
    return {}


def _save(data: dict):
    HISTORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ── Public API ────────────────────────────────────────────────────────────────

def get_history(mailbox: str) -> list:
    """Return the stored messages for *mailbox* (oldest-first)."""
    data = _load()
    # Stored most-recent-first; reverse for chronological display
    return list(reversed(data.get(mailbox, [])))


def save_message(mailbox: str, msg_id: str, sender: str,
                 subject: str, body: str):
    """
    Persist a single message for *mailbox*.
    Silently skips if the message id is already stored.
    """
    data = _load()
    bucket = data.setdefault(mailbox, [])
    # Deduplicate by id
    if any(m["id"] == msg_id for m in bucket):
        return
    bucket.insert(0, {          # most-recent-first
        "id":          msg_id,
        "from":        sender,
        "subject":     subject,
        "body":        body,
        "received_at": time.time(),
    })
    _save(data)


def shred_history(mailbox: Optional[str] = None):
    """
    Delete history.

    mailbox=None  → wipe history for ALL mailboxes (keeps file, empties it)
    mailbox=str   → wipe only that mailbox's history
    """
    if mailbox is None:
        _save({})
    else:
        data = _load()
        data.pop(mailbox, None)
        _save(data)


def shred_all():
    """Delete the history file entirely."""
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
