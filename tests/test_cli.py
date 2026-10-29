import json

from suk import mail
from suk.cli import main
from suk.client import Mailbox
from suk.models import Message


def test_list_json_empty(capsys):
    code = main(["--list", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["items"] == []
    assert payload["data"]["total"] == 0


def test_new_json(monkeypatch, capsys):
    monkeypatch.setattr(
        mail.Mailbox,
        "create",
        classmethod(lambda cls: Mailbox("tok", "a@b.c")),
    )
    code = main(["--new", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["address"] == "a@b.c"


def test_messages_json(monkeypatch, capsys):
    mail.save_session(0, "tok", "a@b.c")
    monkeypatch.setattr(
        mail.Mailbox,
        "get_messages",
        lambda self: [Message(id="m1", sender="x@y.z", subject="Hi", body_text="preview")],
    )
    code = main(["messages", "--slot", "0", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["items"][0]["id"] == "m1"


def test_open_non_interactive_json(monkeypatch, capsys):
    mail.save_session(0, "tok", "a@b.c")
    monkeypatch.setattr(mail.Mailbox, "get_messages", lambda self: [])
    code = main(["--open", "0", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["slot"] == 0


def test_open_multi_json(monkeypatch, capsys):
    mail.save_session(0, "tok0", "a@b.c")
    mail.save_session(1, "tok1", "d@e.f")
    monkeypatch.setattr(mail.Mailbox, "get_messages", lambda self: [])
    code = main(["--open", "0", "1", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["total"] == 2
    assert [item["slot"] for item in payload["data"]["items"]] == [0, 1]


def test_subcommand_list_json(capsys):
    code = main(["list", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


def test_shred_requires_yes(capsys):
    code = main(["--shred", "all", "--json"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"


def test_delete_requires_yes(capsys):
    code = main(["delete", "--slot", "0", "--json"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "USAGE"


def test_missing_slot_is_not_found(capsys):
    code = main(["messages", "--slot", "0", "--json"])
    assert code == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "NOT_FOUND"


def test_version(capsys):
    code = main(["--version"])
    assert code == 0
    assert "suk" in capsys.readouterr().out


def test_version_json(capsys):
    code = main(["--version", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["version"]


def test_schema(capsys):
    code = main(["schema"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "exit_codes" in payload["data"]


def test_parse_error_is_json(capsys):
    code = main(["--json", "--nope"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "USAGE"


def test_shred_all_yes_removes_state():
    from suk import paths

    mail.save_session(0, "tok", "a@b.c")
    assert paths.sessions_file().exists()
    code = main(["--shred", "all", "--yes", "--json"])
    assert code == 0
    assert not paths.sessions_file().exists()
    assert not paths.history_file().exists()
