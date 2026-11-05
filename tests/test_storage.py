"""Saving must never lose or truncate the user's existing data."""
import csv
import stat
import subprocess
from pathlib import Path

import pytest

from appdata import csvparser
from appdata.csvparser import (
    RECIPIENT_TEMPLATE_COLUMNS, PAYER_TEMPLATE_COLUMNS, Bill, Settings, load_bills, load_settings,
    migrate_old_files, read_rows, save_bills, save_settings, sort_bills,
    write_rows,
)

REPO = Path(__file__).resolve().parent.parent


def bill(description: str) -> Bill:
    return Bill(description=description, amount="1.00", currency="CHF")


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
    path = tmp_path / "payer_templates.csv"
    row = {"payer_name": "Old"}
    write_rows(path, PAYER_TEMPLATE_COLUMNS, [row])

    def explode(src, dst):
        raise OSError("nope")

    monkeypatch.setattr(csvparser.os, "replace", explode)
    with pytest.raises(OSError):
        write_rows(path, PAYER_TEMPLATE_COLUMNS, [{"payer_name": "New"}])

    assert read_rows(path, PAYER_TEMPLATE_COLUMNS)[0]["payer_name"] == "Old"
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


def test_old_log_is_git_ignored():
    result = subprocess.run(["git", "check-ignore", "-q", "appdata/log"], cwd=REPO)
    assert result.returncode == 0


def test_csv_file_format_is_unchanged(tmp_path):
    path = tmp_path / "data.csv"
    save_bills(path, [Bill(description="a", recipient_name="Firma", payer_name="Ich")])
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header == ("description,dueDate,paidDate,paidWith,paidChecked,bAmount,bCurrency,"
                      "bAccount,bReference,note,rName,rStreet,rBuildingNr,rPostalCode,rCity,"
                      "rCountry,pName,pStreet,pBuildingNr,pPostalCode,pCity,pCountry,privateNote")


def test_existing_files_still_load_and_save_identically(tmp_path):
    templates = REPO / "templates"
    bills = load_bills(templates / "data.csv")
    swisscom = next(b for b in bills if b.description == "Swisscom: Abo")
    assert swisscom.recipient_name == "Swisscom AG"
    assert swisscom.payer_name == "Max Mustermann"
    assert swisscom.amount == "79.90"
    assert swisscom.due_date == "2026-07-22"

    copy = tmp_path / "data.csv"
    save_bills(copy, bills)
    assert load_bills(copy) == bills
    assert csv_rows(copy) == csv_rows(templates / "data.csv")

    recipients = read_rows(templates / "recipientList.csv", RECIPIENT_TEMPLATE_COLUMNS)
    assert recipients[0]["recipient_name"] == "Steueramt Zürich"
    payers = read_rows(templates / "payerList.csv", PAYER_TEMPLATE_COLUMNS)
    assert payers[0]["payer_name"] == "Max Mustermann"
    for name, columns, rows in (("recipientList.csv", RECIPIENT_TEMPLATE_COLUMNS, recipients),
                                ("payerList.csv", PAYER_TEMPLATE_COLUMNS, payers)):
        write_rows(tmp_path / name, columns, rows)
        assert csv_rows(tmp_path / name) == csv_rows(templates / name)


def csv_rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


@pytest.mark.parametrize("stored, expected", [
    ("dueDate", ["b", "a"]), ("paidDate", ["a", "b"]), ("description", ["a", "b"]),
])
def test_stored_sort_settings_still_work(tmp_path, stored, expected):
    path = tmp_path / "settings.toml"
    path.write_text(f'[settings]\nsort_by = "{stored}"\n', encoding="utf-8")
    settings = load_settings(path)
    assert settings.sort_by == stored
    bills = [Bill(description="a", due_date="2030-02-01", paid_date="2030-01-01"),
             Bill(description="b", due_date="2030-01-01", paid_date="2030-02-01")]
    assert [b.description for b in sort_bills(bills, settings.sort_by)] == expected


OLD_BILLS = """description,dueDate,paidDate,paidWith,paidChecked,bAmount,bCurrency,bAccount,\
bReference,note,dName,dStreet,dBuildingNr,dPostalCode,dCity,dCountry,cName,cStreet,cBuildingNr,\
cPostalCode,cCity,cCountry,privateNote
"Abo, Monat",2030-01-01,,,False,79.90,CHF,CH93,,,Swisscom AG,Weg,6,3048,Worblaufen,CH,\
Max Müller,Musterweg,69,8000,Zürich,CH,geheim
"""
OLD_RECIPIENTS = """description,amount,currency,account,dName,dStreet,dBuildingNr,dPostalCode,\
dCity,dCountry
Strom,85.40,CHF,,EWZ,Technoparkstrasse,1,8005,Zürich,CH
"""
OLD_PAYERS = "cName,cStreet,cBuildingNr,cPostalCode,cCity,cCountry\nMax Müller,Weg,1,8000,Zürich,CH\n"


def write_old_files(folder):
    folder.mkdir(exist_ok=True)
    (folder / "data.csv").write_text(OLD_BILLS, encoding="utf-8")
    (folder / "debitorList.csv").write_text(OLD_RECIPIENTS, encoding="utf-8")
    (folder / "creditorList.csv").write_text(OLD_PAYERS, encoding="utf-8")


def test_old_files_are_converted_with_backups(tmp_path):
    write_old_files(tmp_path)
    migrate_old_files(tmp_path)

    bill = load_bills(tmp_path / "data.csv")[0]
    assert bill.description == "Abo, Monat"
    assert bill.recipient_name == "Swisscom AG"
    assert bill.payer_name == "Max Müller"
    assert bill.private_note == "geheim"
    assert read_rows(tmp_path / "recipientList.csv",
                     RECIPIENT_TEMPLATE_COLUMNS)[0]["recipient_name"] == "EWZ"
    assert read_rows(tmp_path / "payerList.csv",
                     PAYER_TEMPLATE_COLUMNS)[0]["payer_name"] == "Max Müller"

    assert not (tmp_path / "debitorList.csv").exists()
    assert not (tmp_path / "creditorList.csv").exists()
    assert (tmp_path / "data.csv.pre-rename.bak").read_text(encoding="utf-8") == OLD_BILLS
    assert (tmp_path / "debitorList.csv.pre-rename.bak").read_text(
        encoding="utf-8") == OLD_RECIPIENTS
    assert (tmp_path / "creditorList.csv.pre-rename.bak").read_text(
        encoding="utf-8") == OLD_PAYERS


def test_conversion_only_happens_once(tmp_path):
    write_old_files(tmp_path)
    migrate_old_files(tmp_path)
    save_bills(tmp_path / "data.csv", [bill("changed later")])
    migrate_old_files(tmp_path)
    assert load_bills(tmp_path / "data.csv")[0].description == "changed later"
    assert (tmp_path / "data.csv.pre-rename.bak").read_text(encoding="utf-8") == OLD_BILLS


def test_old_list_is_left_alone_when_new_one_exists(tmp_path):
    write_old_files(tmp_path)
    write_rows(tmp_path / "payerList.csv", PAYER_TEMPLATE_COLUMNS, [{"payer_name": "Neu"}])
    migrate_old_files(tmp_path)
    assert (tmp_path / "creditorList.csv").read_text(encoding="utf-8") == OLD_PAYERS
    assert read_rows(tmp_path / "payerList.csv",
                     PAYER_TEMPLATE_COLUMNS)[0]["payer_name"] == "Neu"


def test_failed_conversion_keeps_the_original(tmp_path, monkeypatch):
    write_old_files(tmp_path)

    def explode(src, dst):
        raise OSError("nope")

    monkeypatch.setattr(csvparser.os, "replace", explode)
    with pytest.raises(OSError):
        migrate_old_files(tmp_path)
    assert (tmp_path / "data.csv").read_text(encoding="utf-8") == OLD_BILLS
