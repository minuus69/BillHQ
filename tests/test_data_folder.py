"""Where data lives: the private app storage, the data folder and the templates."""
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from appdata import paths, qr
from appdata.core import Core
from appdata.csvparser import (
    BILL_COLUMNS, PAYER_TEMPLATE_COLUMNS, RECIPIENT_TEMPLATE_COLUMNS, REQUIRED_FIELDS, Bill,
    Settings, load_bills, load_settings, parse_amount, parse_date, prepare_data_folder,
    read_rows, save_bills, save_settings,
)

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
TEMPLATE_FILES = {"data.csv", "recipientList.csv", "payerList.csv"}


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def names(folder):
    return {p.name for p in folder.iterdir()}


def start(legacy=None):
    return Core(TEMPLATES, paths.config_dir(), legacy)


def test_default_locations(isolated_home):
    assert paths.default_data_dir() == isolated_home / "Documents" / "BillHQ"
    assert paths.config_dir() == isolated_home / ".config" / "BillHQ"


@pytest.mark.parametrize("text, expected", [
    ("", "Documents/BillHQ"), ("   ", "Documents/BillHQ"),
    ("~/Nextcloud/bills", "Nextcloud/bills"), ("$HOME/x", "x"),
])
def test_resolving_the_folder_setting(isolated_home, text, expected):
    assert paths.resolve_data_folder(text) == isolated_home / expected


def test_relative_folder_is_rejected():
    with pytest.raises(ValueError):
        paths.resolve_data_folder("some/relative/path")


def test_first_start_creates_private_storage_and_default_folder(isolated_home):
    core = start()
    assert core.data_folder == isolated_home / "Documents" / "BillHQ"
    assert names(core.data_folder) == TEMPLATE_FILES
    assert len(core.bills) == 3
    assert mode(paths.config_dir()) == 0o700
    assert mode(paths.config_dir() / "settings.toml") == 0o600
    assert mode(core.data_folder) == 0o700
    assert mode(core.data_folder / "data.csv") == 0o600
    assert (paths.config_dir() / "log").exists()


def test_existing_empty_folder_gets_templates(tmp_path):
    prepare_data_folder(tmp_path, TEMPLATES)
    assert names(tmp_path) == TEMPLATE_FILES


def test_folder_with_anything_in_it_is_left_alone(tmp_path):
    (tmp_path / "taxes.pdf").write_text("x", encoding="utf-8")
    prepare_data_folder(tmp_path, TEMPLATES)
    assert names(tmp_path) == {"taxes.pdf"}


def test_user_edits_survive_a_restart():
    core = start()
    core.bills.clear()
    core.persist()
    assert start().bills == []


def test_templates_never_touch_the_repo_copy(isolated_home):
    before = {p.name: p.read_bytes() for p in TEMPLATES.iterdir()}
    core = start()
    core.bills.clear()
    core.persist()
    assert {p.name: p.read_bytes() for p in TEMPLATES.iterdir()} == before


# ---- changing the folder ----
def test_changing_folder_loads_it_and_is_remembered(isolated_home):
    core = start()
    old = core.data_folder
    core.bills.clear()
    core.persist()

    target = isolated_home / "Nextcloud" / "bills"
    core.set_data_folder(str(target))
    assert core.data_folder == target
    assert len(core.bills) == 3
    assert load_bills(old / "data.csv") == []     # the old folder is untouched

    core.bills.clear()
    core.persist()
    assert load_bills(target / "data.csv") == []

    again = start()
    assert again.data_folder == target
    assert again.bills == []


def test_changing_to_a_folder_with_bills_uses_them(tmp_path):
    save_bills(tmp_path / "data.csv", [Bill(description="mine")])
    core = start()
    core.set_data_folder(str(tmp_path))
    assert [b.description for b in core.sorted_bills()] == ["mine"]
    assert names(tmp_path) == {"data.csv"}


def test_empty_setting_goes_back_to_default(tmp_path, isolated_home):
    core = start()
    core.set_data_folder(str(tmp_path))
    core.set_data_folder("")
    assert core.data_folder == isolated_home / "Documents" / "BillHQ"
    assert load_settings(core.settings_path).data_folder == ""


def test_failed_change_changes_nothing(tmp_path):
    core = start()
    before = (core.data_folder, list(core.bills), core.settings.data_folder)
    blocker = tmp_path / "a-file"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    with pytest.raises(OSError):
        core.set_data_folder(str(blocker))
    assert (core.data_folder, core.bills, core.settings.data_folder) == before


def test_folder_with_unreadable_bills_is_rejected(tmp_path):
    (tmp_path / "data.csv").write_bytes(b"description\n\xff\xfe\xff\n")
    core = start()
    before = core.data_folder
    with pytest.raises(ValueError):
        core.set_data_folder(str(tmp_path))
    assert core.data_folder == before


@pytest.mark.parametrize("folder", ['/data/my "bills"', r"C:\Users\me\bills", "/data/Zürich bills"])
def test_unusual_paths_survive_the_settings_file(tmp_path, folder):
    path = tmp_path / "settings.toml"
    save_settings(path, Settings(data_folder=folder, language="de"))
    loaded = load_settings(path)
    assert (loaded.data_folder, loaded.language) == (folder, "de")


# ---- importing from the old userdata folder ----
def make_legacy(tmp_path):
    legacy = tmp_path / "userdata"
    legacy.mkdir()
    save_bills(legacy / "data.csv", [Bill(description="real bill")])
    save_settings(legacy / "settings.toml", Settings(language="de"))
    return legacy


def test_first_start_imports_old_userdata_and_keeps_it(tmp_path):
    legacy = make_legacy(tmp_path)
    core = start(legacy)
    assert [b.description for b in core.bills] == ["real bill"]
    assert core.settings.language == "de"
    assert mode(core.settings_path) == 0o600
    assert (legacy / "data.csv").exists()


def test_old_files_with_old_columns_convert_during_import(tmp_path):
    legacy = tmp_path / "userdata"
    legacy.mkdir()
    (legacy / "data.csv").write_text("description,dName,cName\nAbo,Swisscom,Max\n", encoding="utf-8")
    (legacy / "creditorList.csv").write_text("cName\nMax\n", encoding="utf-8")
    core = start(legacy)
    assert (core.bills[0].recipient_name, core.bills[0].payer_name) == ("Swisscom", "Max")
    assert core.payer_templates[0]["payer_name"] == "Max"


def test_import_only_happens_on_the_first_start(tmp_path):
    legacy = make_legacy(tmp_path)
    core = start(legacy)
    core.bills.clear()
    core.persist()
    assert start(legacy).bills == []


def test_import_doesnt_touch_a_folder_already_in_use(tmp_path, isolated_home):
    legacy = make_legacy(tmp_path)
    save_bills(isolated_home / "Documents" / "BillHQ" / "data.csv", [Bill(description="newer")])
    assert [b.description for b in start(legacy).bills] == ["newer"]


def test_old_folder_without_csv_files_falls_back_to_templates(tmp_path):
    legacy = tmp_path / "userdata"
    legacy.mkdir()
    save_settings(legacy / "settings.toml", Settings(language="fr"))
    core = start(legacy)
    assert core.settings.language == "fr"
    assert len(core.bills) == 3


# ---- the template files themselves ----
TEMPLATE_BILLS = load_bills(TEMPLATES / "data.csv")
RECIPIENTS = read_rows(TEMPLATES / "recipientList.csv", RECIPIENT_TEMPLATE_COLUMNS)
PAYERS = read_rows(TEMPLATES / "payerList.csv", PAYER_TEMPLATE_COLUMNS)


def header(name):
    return (TEMPLATES / name).read_text(encoding="utf-8").splitlines()[0].split(",")


def test_template_headers_match_the_code():
    assert header("data.csv") == list(BILL_COLUMNS.values())
    assert header("recipientList.csv") == list(RECIPIENT_TEMPLATE_COLUMNS.values())
    assert header("payerList.csv") == list(PAYER_TEMPLATE_COLUMNS.values())


def test_template_folder_holds_exactly_the_starter_files():
    assert names(TEMPLATES) == TEMPLATE_FILES


@pytest.mark.parametrize("bill", TEMPLATE_BILLS, ids=lambda b: b.description)
def test_template_bills_are_complete_and_make_real_qr_bills(bill, tmp_path):
    assert all(getattr(bill, field) for field in REQUIRED_FIELDS)
    parse_amount(bill.amount)
    parse_date(bill.due_date)
    assert f"{parse_amount(bill.amount):.2f}" == bill.amount
    data = qr.parse_swiss_qr_payload(qr.parse_qr_code(
        qr.generate_qr_bill(bill, Settings(), tmp_path, open_viewer=False))[0])
    assert data["recipient_name"] == bill.recipient_name
    assert data["reference"] == bill.reference


@pytest.mark.parametrize("row", RECIPIENTS, ids=lambda r: r["description"])
def test_recipient_templates_have_valid_accounts(row, tmp_path):
    assert f"{parse_amount(row['amount']):.2f}" == row["amount"]
    bill = replace(TEMPLATE_BILLS[0], account=row["account"], reference="")
    if "3199" in row["account"]:           # a QR-IBAN needs a QR reference
        bill = replace(bill, reference=TEMPLATE_BILLS[0].reference)
    qr.generate_qr_bill(bill, Settings(), tmp_path, open_viewer=False)


def test_payer_templates_are_complete():
    assert PAYERS and all(all(row.values()) for row in PAYERS)
