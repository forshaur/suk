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
    $ suk --html       # return emails in raw html
    $ suk --list       # show saved sessions
"""

from importlib.metadata import version as _pkg_version, PackageNotFoundError

# Version -------------------------------------------------------------------
try:
    __version__ = _pkg_version("suk")
except PackageNotFoundError:
    __version__ = "0.0.0"

# Public API ----------------------------------------------------------------
from suk.client import Mailbox
from suk.models import Message
from suk.exceptions import SukError, APIError, MailboxExpiredError, WaitTimeoutError

__all__ = [
    "Mailbox",
    "Message",
    "SukError",
    "APIError",
    "MailboxExpiredError",
    "WaitTimeoutError",
    "__version__",
]