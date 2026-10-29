import os
import stat

import pytest

from suk import paths


def test_atomic_write_sets_owner_only_mode(tmp_path):
    target = tmp_path / "state.json"
    paths.atomic_write(target, '{"ok": true}')
    assert target.read_text() == '{"ok": true}'
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


def test_suk_home_directory_is_owner_only(isolate_suk_home):
    directory = paths.ensure_state_dir()
    assert directory == isolate_suk_home
    assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700


def test_atomic_write_refuses_symlink(tmp_path):
    real = tmp_path / "real.json"
    real.write_text("keep")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(OSError):
        paths.atomic_write(link, "replace")
    assert real.read_text() == "keep"
