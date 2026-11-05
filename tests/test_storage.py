"""Saving must never lose or truncate the user's existing data."""
import csv
import stat
import subprocess
from pathlib import Path

import pytest

from appdata import csvparser
from appdata.csvparser import (
    CREDITOR_FIELDS, Bill, Settings, load_bills, load_settings, read_rows,
    save_bills, save_settings, write_rows,
)

REPO = Path(__file__).resolve().parent.parent


def bill(description: str) -> Bill:
    return Bill(description=description, bAmount="1.00", bCurrency="CHF")


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "data.csv"
    save_bills(path, [bill("Zürich, \"quoted\""), bill("two")])
    assert [b.description for b in load_bills(path)] == ['Zürich, "quoted"', "two"]


def test_save_keeps_previous_version_as_backup(tmp_path):
    path = tmp_path / "data.csv"
    save_bills(path, [bill("old")])
    assert not (tmp_path / "data.csv.bak").exists()
    save_bills(path, [bill("new")])
    assert [b.description for b in load_bills(path)] == ["new"]
    assert [b.description for b in load_bills(tmp_path / "data.csv.bak")] == ["old"]


def test_failed_save_leaves_file_untouched(tmp_path, monkeypatch):
    path = tmp_path / "data.csv"
    save_bills(path, [bill("precious")])
    before = path.read_bytes()

    def explode(self, row):
        raise OSError("disk full")

    monkeypatch.setattr(csv.DictWriter, "writerow", explode)
    with pytest.raises(OSError):
        save_bills(path, [bill("new")])

    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["data.csv"]


def test_failed_swap_leaves_file_untouched(tmp_path, monkeypatch):
    path = tmp_path / "creditors.csv"
    row = {"cName": "Old"}
    write_rows(path, CREDITOR_FIELDS, [row])

    def explode(src, dst):
        raise OSError("nope")

    monkeypatch.setattr(csvparser.os, "replace", explode)
    with pytest.raises(OSError):
        write_rows(path, CREDITOR_FIELDS, [{"cName": "New"}])

    assert read_rows(path, CREDITOR_FIELDS)[0]["cName"] == "Old"
    assert not list(tmp_path.glob("*.tmp"))


def test_save_keeps_file_permissions(tmp_path):
    path = tmp_path / "data.csv"
    save_bills(path, [bill("a")])
    path.chmod(0o640)
    save_bills(path, [bill("b")])
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.toml"
    save_settings(path, Settings(language="de", logsize=500))
    loaded = load_settings(path)
    assert (loaded.language, loaded.logsize) == ("de", 500)


@pytest.mark.parametrize("name", [
    "userdata/data.csv", "userdata/debitorList.csv", "userdata/creditorList.csv",
    "userdata/data.csv.bak", "userdata/.data.csv.abc.tmp",
    "userdata/qrbill.png", "userdata/qrbill.svg", "appdata/log",
])
def test_personal_files_are_git_ignored(name):
    result = subprocess.run(["git", "check-ignore", "-q", name], cwd=REPO)
    assert result.returncode == 0, f"{name} is not ignored"
