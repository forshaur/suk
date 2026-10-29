import json

import pytest

from suk import client
from suk.exceptions import (
    MailboxExpiredError,
    NetworkError,
    WaitTimeoutError,
)
from suk.models import Message


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_create_mailbox(monkeypatch):
    monkeypatch.setattr(
        client.cffi_requests,
        "post",
        lambda *args, **kwargs: FakeResponse(200, {"token": "tok", "mailbox": "a@b.c"}),
    )
    inbox = client.Mailbox.create()
    assert inbox.token == "tok"
    assert inbox.address == "a@b.c"


def test_get_messages_parses_preview(monkeypatch):
    payload = {"messages": [{"_id": "m1", "from": "x@y.z", "subject": "Hi", "bodyPreview": "preview"}]}
    monkeypatch.setattr(client.cffi_requests, "get", lambda *args, **kwargs: FakeResponse(200, payload))
    inbox = client.Mailbox("tok", "a@b.c")
    messages = inbox.get_messages()
    assert messages == [Message(id="m1", sender="x@y.z", subject="Hi", body_text="preview")]


def test_expired_mailbox(monkeypatch):
    monkeypatch.setattr(client.cffi_requests, "get", lambda *args, **kwargs: FakeResponse(401, {}))
    inbox = client.Mailbox("tok", "a@b.c")
    with pytest.raises(MailboxExpiredError):
        inbox.get_messages()


def test_network_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(client.cffi_requests, "get", boom)
    inbox = client.Mailbox("tok", "a@b.c")
    with pytest.raises(NetworkError):
        inbox.get_messages()


def test_wait_for_message_reconsiders_rejected_message(monkeypatch):
    preview = {"messages": [{"_id": "m1", "from": "x@y.z", "subject": "Welcome", "bodyPreview": "hi"}]}
    detail = {"from": "x@y.z", "subject": "Welcome", "bodyText": "full body"}

    def fake_get(url, *args, **kwargs):
        if url.endswith("/messages/m1"):
            return FakeResponse(200, detail)
        return FakeResponse(200, preview)

    monkeypatch.setattr(client.cffi_requests, "get", fake_get)
    inbox = client.Mailbox("tok", "a@b.c")

    calls = {"count": 0}

    def predicate(message):
        calls["count"] += 1
        return calls["count"] >= 2

    message = inbox.wait_for_message(predicate=predicate, timeout=1, poll_interval=0.01)
    assert message.id == "m1"
    assert message.body_text == "full body"
    assert calls["count"] == 2


def test_wait_for_message_timeout(monkeypatch):
    monkeypatch.setattr(
        client.cffi_requests,
        "get",
        lambda *args, **kwargs: FakeResponse(200, {"messages": []}),
    )
    inbox = client.Mailbox("tok", "a@b.c")
    with pytest.raises(WaitTimeoutError):
        inbox.wait_for_message(timeout=0.05, poll_interval=0.01)


def test_contract_fixture(monkeypatch):
    from pathlib import Path

    fixture = json.loads((Path(__file__).parent / "fixtures" / "messages.json").read_text())
    monkeypatch.setattr(client.cffi_requests, "get", lambda *args, **kwargs: FakeResponse(200, fixture))
    inbox = client.Mailbox("tok", "a@b.c")
    messages = inbox.get_messages()
    assert len(messages) == 2
    assert messages[0].id == "m1"
    assert messages[0].sender == "no-reply@service.com"
    assert messages[1].subject == "Your code"
