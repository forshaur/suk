from suk import mail
from suk.history import get_history, save_message


def test_list_sessions_data_roundtrip():
    mail.save_session(0, "tok", "a@b.c")
    data = mail.list_sessions_data()
    assert data[0]["slot"] == 0
    assert data[0]["address"] == "a@b.c"


def test_delete_session_removes_history():
    mail.save_session(1, "tok", "a@b.c")
    save_message("a@b.c", "m1", "x@y.z", "Hi", "body")
    assert get_history("a@b.c")

    address = mail.delete_session(1)
    assert address == "a@b.c"
    assert get_history("a@b.c") == []
    assert mail.list_sessions_data() == []
