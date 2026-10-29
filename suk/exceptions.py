"""
Custom exceptions for the suk package.

All exceptions inherit from SukError so callers can catch everything with a
single ``except suk.SukError``.  ``exit_code`` maps to the CLI contract.
"""


class SukError(Exception):
    """Base exception for all suk errors."""

    exit_code = 1


class UsageError(SukError):
    """Raised for invalid arguments or missing consent."""

    exit_code = 2


class APIError(SukError):
    """Raised when the temp-mail upstream API returns a non-200 response."""

    exit_code = 7

    def __init__(self, message: str, status_code: int = 0):
        self.status_code = status_code
        if status_code == 429:
            self.exit_code = 5
        elif status_code in (401, 403):
            self.exit_code = 3
        elif status_code == 404:
            self.exit_code = 4
        super().__init__(message)


class NetworkError(APIError):
    """Raised when the network request itself fails."""

    exit_code = 6


class MailboxExpiredError(SukError):
    """Raised when the mailbox token has expired (HTTP 401/403)."""

    exit_code = 3


class WaitTimeoutError(SukError):
    """Raised when ``Mailbox.wait_for_message()`` exceeds *timeout* seconds."""

    exit_code = 4


class NotFoundError(SukError):
    """Raised when a slot, mailbox, or message does not exist."""

    exit_code = 4
