"""Keeps the repo root importable, and keeps tests away from your real files."""
import pytest

from appdata.languages import set_language


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, tmp_path_factory, monkeypatch):
    """Point every location at a temporary home, for every test."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setattr("ui.app.LEGACY_DIR", tmp_path / "no-legacy-folder")
    yield home
    set_language("en")
