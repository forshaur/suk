"""
client.py - Pure SDK layer for suk.

This module is designed for **programmatic usage** — automation scripts,
bots, test suites, and external tools.  It has:

* No Rich / terminal UI calls
* No ``sys.exit()``
* No file I/O (sessions, history)

All errors are communicated through exceptions defined in ``suk.exceptions``.

Quick start::

    from suk import Mailbox

    inbox = Mailbox.create()
    print(f"Send mail to: {inbox.address}")

    msg = inbox.wait_for_message(timeout=120)
    print(msg.subject, msg.body_text)
"""

import re
import time
from typing import Callable, List, Optional

from curl_cffi import requests as cffi_requests

from suk.exceptions import (
    APIError,
    MailboxExpiredError,
    NetworkError,
    WaitTimeoutError,
)
from suk.models import Message

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://web2.temp-mail.org"
REQUEST_TIMEOUT = (5, 15)

_HEADERS_BASE = {
    "User-Agent":      "Mozilla/5.0 (X11; Linux x86_64; rv:149.0) Gecko/20100101 Firefox/149.0",
    "Accept":          "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer":         "https://temp-mail.org/",
    "Origin":          "https://temp-mail.org",
    "Connection":      "keep-alive",
    "Sec-Fetch-Dest":  "empty",
    "Sec-Fetch-Mode":  "cors",
    "Sec-Fetch-Site":  "same-site",
    "Priority":        "u=4",
    "TE":              "trailers",
}


def _strip_html(html: str) -> str:
    """Minimal HTML-to-text conversion (no external dependency)."""
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<(br|p|div|tr|li|h[1-6])\b[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    for ent, ch in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                    ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'")]:
        html = html.replace(ent, ch)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html


# ---------------------------------------------------------------------------
# Mailbox
# ---------------------------------------------------------------------------

class Mailbox:
    """A disposable temporary email inbox.

    Use the class method :meth:`create` to generate a new address, or
    instantiate directly if you already have a *token* and *address*
    (e.g. restored from persistent storage).

    Parameters:
        token:   Bearer token returned by the temp-mail API.
        address: The temporary email address string.

    Example::

        inbox = Mailbox.create()
        print(inbox.address)          # e.g. "a1b2c3@decabg.com"
        msgs = inbox.get_messages()   # list[Message]
    """

    def __init__(self, token: str, address: str):
        self.token: str = token
        self.address: str = address

    def __repr__(self) -> str:
        return f"Mailbox(address={self.address!r})"

    # -- factory --------------------------------------------------------------

    @classmethod
    def create(cls) -> "Mailbox":
        """Create a brand-new temporary email address.

        Returns:
            A :class:`Mailbox` instance ready to receive mail.

        Raises:
            NetworkError: If the request fails at the transport level.
            APIError: If the upstream API returns a non-200 status.
        """
        headers = {**_HEADERS_BASE, "Content-Type": "application/json", "Content-Length": "0"}
        try:
            r = cffi_requests.post(
                f"{API_BASE}/mailbox",
                headers=headers,
                impersonate="firefox",
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as exc:
            raise NetworkError(f"Network error while creating mailbox: {exc}") from exc

        if r.status_code != 200:
            raise APIError(
                f"Failed to create mailbox (HTTP {r.status_code})",
                status_code=r.status_code,
            )
        data = r.json()
        return cls(token=data["token"], address=data["mailbox"])

    # -- message fetching -----------------------------------------------------

    def _auth_headers(self) -> dict:
        return {**_HEADERS_BASE, "Authorization": f"Bearer {self.token}"}

    def get_messages(self) -> List[Message]:
        """Fetch the current list of messages in the inbox.

        Returns:
            A list of :class:`Message` objects.  The ``body_text`` field
            contains only the preview; call :meth:`get_message_detail` for
            the full body.

        Raises:
            MailboxExpiredError: If the token has expired (HTTP 401/403).
            NetworkError: If the request fails at the transport level.
            APIError: On other HTTP errors.
        """
        try:
            r = cffi_requests.get(
                f"{API_BASE}/messages",
                headers=self._auth_headers(),
                impersonate="firefox",
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as exc:
            raise NetworkError(f"Network error fetching messages: {exc}") from exc

        if r.status_code in (401, 403):
            raise MailboxExpiredError(
                f"Mailbox token expired or invalid (HTTP {r.status_code})"
            )
        if r.status_code != 200:
            raise APIError(
                f"Failed to fetch messages (HTTP {r.status_code})",
                status_code=r.status_code,
            )

        messages = []
        for m in r.json().get("messages", []):
            messages.append(Message(
                id=m.get("_id", ""),
                sender=m.get("from", ""),
                subject=m.get("subject", ""),
                body_text=m.get("bodyPreview", ""),
            ))
        return messages

    def get_message_detail(self, message_id: str) -> Message:
        """Fetch the full body of a specific message.

        Parameters:
            message_id: The ``_id`` field from a message returned by
                :meth:`get_messages`.

        Returns:
            A :class:`Message` with ``body_text`` and ``body_html`` populated.

        Raises:
            NetworkError: If the request fails at the transport level.
            APIError: On HTTP errors.
        """
        try:
            r = cffi_requests.get(
                f"{API_BASE}/messages/{message_id}",
                headers=self._auth_headers(),
                impersonate="firefox",
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as exc:
            raise NetworkError(f"Network error fetching message detail: {exc}") from exc

        if r.status_code in (401, 403):
            raise MailboxExpiredError(
                f"Mailbox token expired or invalid (HTTP {r.status_code})"
            )
        if r.status_code != 200:
            raise APIError(
                f"Failed to fetch message {message_id} (HTTP {r.status_code})",
                status_code=r.status_code,
            )

        data = r.json()
        body_text = data.get("bodyText", "").strip()
        body_html = data.get("bodyHtml", "")
        if not body_text and body_html:
            body_text = _strip_html(body_html).strip()

        return Message(
            id=message_id,
            sender=data.get("from", ""),
            subject=data.get("subject", ""),
            body_text=body_text,
            body_html=body_html or None,
        )

    # -- convenience: wait for a message --------------------------------------

    def wait_for_message(
        self,
        predicate: Optional[Callable[[Message], bool]] = None,
        timeout: int = 60,
        poll_interval: float = 3,
    ) -> Message:
        """Block until a *new* message matching *predicate* arrives.

        Parameters:
            predicate:     Optional callable that receives a :class:`Message`
                           and returns ``True`` to accept it.  ``None`` means
                           accept the first unseen message.
            timeout:       Maximum seconds to wait before raising.
            poll_interval: Seconds between polling attempts.

        Returns:
            The matching :class:`Message` with full body fetched.

        Raises:
            WaitTimeoutError: If no matching message arrives within *timeout*.
            MailboxExpiredError: If the token expires while polling.
            NetworkError: If the request fails at the transport level.
            APIError: On other HTTP errors.

        Example::

            # Wait for any email whose subject contains "OTP"
            msg = inbox.wait_for_message(
                predicate=lambda m: "OTP" in m.subject,
                timeout=120,
            )
            print(msg.body_text)
        """
        deadline = time.time() + timeout
        seen_ids: set = set()
        interval = max(float(poll_interval), 0.1)

        while time.time() < deadline:
            messages = self.get_messages()
            for msg in messages:
                if msg.id in seen_ids:
                    continue
                if predicate is None or predicate(msg):
                    # Mark accepted messages only.  A rejected message stays
                    # eligible so a later predicate can accept it.
                    seen_ids.add(msg.id)
                    detail = self.get_message_detail(msg.id)
                    if not detail.sender:
                        detail.sender = msg.sender
                    if not detail.subject:
                        detail.subject = msg.subject
                    return detail

            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))

        raise WaitTimeoutError(
            f"No matching message arrived within {timeout}s on {self.address}"
        )
