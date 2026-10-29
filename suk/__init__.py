"""
suk - disposable temporary email, as a Python library and CLI tool.

Quick start (programmatic)::

    from suk import Mailbox

    inbox = Mailbox.create()
    print(f"Send mail to: {inbox.address}")

    msg = inbox.wait_for_message(timeout=120)
    print(msg.subject, msg.body_text)

CLI::

    $ suk              # open or create an inbox
    $ suk --new        # fresh inbox
    $ suk --json       # machine-readable output
    $ suk --list       # show saved sessions
"""

__version__ = "4.1.0"

# Public API ----------------------------------------------------------------
from suk.client import Mailbox
from suk.models import Message
from suk.exceptions import (
    APIError,
    MailboxExpiredError,
    NetworkError,
    NotFoundError,
    SukError,
    UsageError,
    WaitTimeoutError,
)

__all__ = [
    "APIError",
    "Mailbox",
    "MailboxExpiredError",
    "Message",
    "NetworkError",
    "NotFoundError",
    "SukError",
    "UsageError",
    "WaitTimeoutError",
    "__version__",
]
