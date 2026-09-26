"""
Custom exceptions for the suk package.

All exceptions inherit from SukError so callers can catch
everything with a single `except suk.SukError`.
"""


class SukError(Exception):
    """Base exception for all suk errors."""


class APIError(SukError):
    """Raised when the temp-mail upstream API returns a non-200 response."""

    def __init__(self, message: str, status_code: int = 0):
        self.status_code = status_code
        super().__init__(message)


class MailboxExpiredError(SukError):
    """Raised when the mailbox token has expired (HTTP 401/403)."""


class WaitTimeoutError(SukError):
    """Raised when `Mailbox.wait_for_message()` exceeds *timeout* seconds."""
