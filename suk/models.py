"""
Data models for the suk package.

These are plain dataclasses with no dependencies on Rich, curl-cffi,
or any I/O — safe to import and serialise anywhere.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Message:
    """A single email received in a temporary inbox.

    Attributes:
        id:          Unique message identifier from the upstream API.
        sender:      The `From:` address.
        subject:     The `Subject:` line.
        body_text:   Plain-text body (may be empty if only HTML was sent).
        body_html:   Raw HTML body (`None` when not fetched).
        received_at: Unix timestamp when the message was first seen locally.
    """

    id: str
    sender: str = ""
    subject: str = ""
    body_text: str = ""
    body_html: Optional[str] = None
    received_at: Optional[float] = None

    # -- convenience helpers --------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise to a plain dict (useful for JSON output)."""
        return {
            "id": self.id,
            "from": self.sender,
            "subject": self.subject,
            "body_text": self.body_text,
            "body_html": self.body_html,
            "received_at": self.received_at,
        }
