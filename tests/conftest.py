import pytest


@pytest.fixture(autouse=True)
def isolate_suk_home(tmp_path, monkeypatch):
    home = tmp_path / "suk-home"
    monkeypatch.setenv("SUK_HOME", str(home))
    return home
