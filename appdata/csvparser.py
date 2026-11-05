"""Data layer: CSV files (data.csv, recipientList.csv, payerList.csv),
settings.toml handling, date helpers and sorting.

NOTE: dates are stored in the CSVs as ISO (yyyy-mm-dd) and only *displayed*
in the configured format — that keeps sorting/parsing unambiguous.
"""
from __future__ import annotations

import csv
import os
import re
import shutil
import tempfile
import tomllib
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator, TextIO

from appdata.languages import LANG_CODES

# --------------------------------------------------------------------------- #
# Field definitions
# --------------------------------------------------------------------------- #
# Field names in the code -> column names in the CSV files.
# Recipient (r*) gets the money, "Payable to" on a QR bill. Payer (p*) pays.
_RECIPIENT_COLUMNS = {
    "recipient_name": "rName", "recipient_street": "rStreet", "recipient_building_nr": "rBuildingNr",
    "recipient_postal_code": "rPostalCode", "recipient_city": "rCity", "recipient_country": "rCountry",
}
_PAYER_COLUMNS = {
    "payer_name": "pName", "payer_street": "pStreet", "payer_building_nr": "pBuildingNr",
    "payer_postal_code": "pPostalCode", "payer_city": "pCity", "payer_country": "pCountry",
}
BILL_COLUMNS = {
    "description": "description", "due_date": "dueDate", "paid_date": "paidDate",
    "paid_with": "paidWith", "paid_checked": "paidChecked", "amount": "bAmount",
    "currency": "bCurrency", "account": "bAccount", "reference": "bReference", "note": "note",
    **_RECIPIENT_COLUMNS, **_PAYER_COLUMNS, "private_note": "privateNote",
}
BILL_FIELDS = list(BILL_COLUMNS)

# Template rows use the same names as Bill, so a template can be applied field by field.
RECIPIENT_TEMPLATE_COLUMNS = {
    "description": "description", "amount": "amount", "currency": "currency",
    "account": "account", **_RECIPIENT_COLUMNS,
}
PAYER_TEMPLATE_COLUMNS = dict(_PAYER_COLUMNS)

# fields marked with * in the spec: must be non-empty to be saved
REQUIRED_FIELDS = [
    "description", "amount", "currency", "account",
    "recipient_name", "recipient_postal_code", "recipient_city", "recipient_country",
]

# Older versions called these d* and c*, in debitorList.csv and creditorList.csv.
LEGACY_COLUMNS = {old: new for new, old in (
    *((c, "d" + c[1:]) for c in _RECIPIENT_COLUMNS.values()),
    *((c, "c" + c[1:]) for c in _PAYER_COLUMNS.values()),
)}

# translation keys for field labels (used in validation errors)
FIELD_LABELS = {
    "description": "f_description", "due_date": "f_due_date", "paid_date": "f_paid_date",
    "paid_with": "f_paid_with", "paid_checked": "f_paid_checked", "amount": "f_amount",
    "currency": "f_currency", "account": "f_account", "reference": "f_reference",
    "note": "f_note", "recipient_name": "f_recipient_name", "recipient_street": "f_street",
    "recipient_building_nr": "f_building_nr", "recipient_postal_code": "f_postal_code", "recipient_city": "f_city",
    "recipient_country": "f_country", "payer_name": "f_payer_name", "payer_street": "f_street",
    "payer_building_nr": "f_building_nr", "payer_postal_code": "f_postal_code", "payer_city": "f_city",
    "payer_country": "f_country", "private_note": "f_private_note",
}

CURRENCIES = ["CHF", "EUR", "USD", "RSD", "JPY", "CNY"]
COUNTRIES = ["CH", "DE", "FR", "IT", "RS", "AT", "LI", "SI", "HR", "ES", "PT", "NL",
             "BE", "LU", "GB", "IE", "SE", "NO", "DK", "FI", "PL", "CZ", "SK", "HU",
             "RO", "BG", "GR", "TR", "UA", "US", "CA", "JP", "CN", "AU", "NZ", "IN",
             "BR", "MX", "ZA", "AE", "XX"]
DATE_FORMATS = ["dd.mm.yyyy", "dd.mm.yy", "dd/mm/yyyy", "mm/dd/yyyy", "mm/dd/yy", "yyyy-mm-dd"]


# --------------------------------------------------------------------------- #
# Bill model
# --------------------------------------------------------------------------- #
@dataclass
class Bill:
    description: str = ""
    due_date: str = ""          # ISO yyyy-mm-dd in the CSV
    paid_date: str = ""         # empty = unpaid
    paid_with: str = ""
    paid_checked: str = ""      # "True" / "False"
    amount: str = ""
    currency: str = ""
    account: str = ""
    reference: str = ""
    note: str = ""
    recipient_name: str = ""
    recipient_street: str = ""
    recipient_building_nr: str = ""
    recipient_postal_code: str = ""
    recipient_city: str = ""
    recipient_country: str = ""
    payer_name: str = ""
    payer_street: str = ""
    payer_building_nr: str = ""
    payer_postal_code: str = ""
    payer_city: str = ""
    payer_country: str = ""
    private_note: str = ""

    @property
    def is_paid(self) -> bool:
        return bool(self.paid_date.strip())

    @property
    def is_checked(self) -> bool:
        return self.paid_checked.strip().lower() in ("true", "1", "yes", "x")

    def to_row(self) -> dict[str, str]:
        return {column: str(getattr(self, field)) for field, column in BILL_COLUMNS.items()}

    @classmethod
    def from_row(cls, row: dict) -> "Bill":
        return cls(**{field: (row.get(column) or "").strip()
                      for field, column in BILL_COLUMNS.items()})


def bill_state(bill: Bill, today: date | None = None) -> str:
    """Returns 'paid', 'overdue', or 'open'."""
    if bill.is_paid:
        return "paid"
    try:
        due = parse_date(bill.due_date)
    except ValueError:
        return "open"
    return "overdue" if due < (today or date.today()) else "open"


_AMOUNT_RE = re.compile(r"\d+(?:[.,]\d{1,2})?")


def parse_amount(text: str) -> Decimal:
    """Strictly parse a typed amount: 12.50, 12,50, 1'250.50 or 1 250.

    Raises ValueError for anything else. That includes 1,250 and 1.250, where the
    separator could mean thousands or decimals, so we never guess a wrong amount.
    """
    cleaned = re.sub(r"['\u2019\s]", "", str(text))
    if not _AMOUNT_RE.fullmatch(cleaned):
        raise ValueError(f"invalid amount: {text!r}")
    return Decimal(cleaned.replace(",", "."))


def amount_decimal(text: str) -> Decimal:
    """Lenient version for display and totals: unreadable stored values count as 0."""
    try:
        value = Decimal(str(text).replace("'", "").replace(" ", "").replace(",", ".") or "0")
    except InvalidOperation:
        return Decimal("0")
    return value if value.is_finite() else Decimal("0")


def today_iso() -> str:
    return date.today().isoformat()


# --------------------------------------------------------------------------- #
# Date helpers (display format comes from settings; parsing is lenient)
# --------------------------------------------------------------------------- #
def format_to_strftime(fmt: str) -> str:
    return (fmt.replace("yyyy", "%Y").replace("yy", "%y")
               .replace("mm", "%m").replace("dd", "%d"))


def parse_date(text: str, preferred: str | None = None) -> date:
    """Parse a date string. Tries the user's display format first, then common ones."""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty date")
    patterns: list[str] = []
    if preferred:
        patterns.append(format_to_strftime(preferred))
    patterns += ["%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y",
                 "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"]
    for p in patterns:
        try:
            return datetime.strptime(text, p).date()
        except ValueError:
            continue
    raise ValueError(f"unparseable date: {text!r}")


def format_date(iso: str, fmt: str) -> str:
    iso = (iso or "").strip()
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso).strftime(format_to_strftime(fmt))
    except ValueError:
        return iso


# --------------------------------------------------------------------------- #
# Sorting (unpaid always first; stable two-phase sort; result is cached by Core)
# --------------------------------------------------------------------------- #
def sort_bills(bills: list[Bill], sort_by: str = "dueDate", order: str = "asc") -> list[Bill]:
    rev = str(order).lower().startswith("desc")
    if sort_by == "description":
        ordered = sorted(bills, key=lambda b: b.description.casefold(), reverse=rev)
    else:
        field = "paid_date" if sort_by == "paidDate" else "due_date"
        dated = [b for b in bills if getattr(b, field).strip()]
        undated = [b for b in bills if not getattr(b, field).strip()]
        ordered = sorted(dated, key=lambda b: getattr(b, field), reverse=rev) + undated
    # stable second pass keeps field order inside the groups, unpaid on top
    return sorted(ordered, key=lambda b: b.is_paid)


# --------------------------------------------------------------------------- #
# Safe writes
# --------------------------------------------------------------------------- #
@contextmanager
def _atomic_open(path: Path, backup: bool = False) -> Iterator[TextIO]:
    """Write to a temp file, then swap it in, so a crash can't leave a partial file.

    With backup=True the previous version is kept next to it as <name>.bak.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
            yield fh
            fh.flush()
            os.fsync(fh.fileno())
        if path.exists():
            shutil.copymode(path, tmp)
            if backup:
                shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- #
# CSV IO
# --------------------------------------------------------------------------- #
def load_bills(path: Path) -> list[Bill]:
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [Bill.from_row(row) for row in csv.DictReader(fh)]


def save_bills(path: Path, bills: list[Bill]) -> None:
    with _atomic_open(path, backup=True) as fh:
        writer = csv.DictWriter(fh, fieldnames=list(BILL_COLUMNS.values()), quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for b in bills:
            writer.writerow(b.to_row())


def _clean_cell(value: str | None) -> str:
    """Older versions could store an untouched dropdown as this text."""
    value = (value or "").strip()
    return "" if value in ("Select.NULL", "Select.BLANK") else value


def read_rows(path: Path, columns: dict[str, str]) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [{field: _clean_cell(row.get(column)) for field, column in columns.items()}
                for row in csv.DictReader(fh)]


def write_rows(path: Path, columns: dict[str, str], rows: list[dict]) -> None:
    with _atomic_open(path, backup=True) as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns.values()), quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in rows:
            writer.writerow({column: r.get(field, "") for field, column in columns.items()})


# --------------------------------------------------------------------------- #
# Settings (TOML)
# --------------------------------------------------------------------------- #
@dataclass
class Settings:
    language: str = "en"
    date_format: str = "dd.mm.yyyy"
    default_currency: str = "CHF"
    default_country: str = "CH"
    sort_by: str = "dueDate"          # dueDate | paidDate | description (as stored in the file)
    sort_order: str = "asc"           # asc | desc
    loglevel: str = "info"            # debug | info | error
    logsize: int = 2048               # max lines kept in the log
    data_folder: str = ""             # where bills are stored, empty = ~/Documents/BillHQ


def load_settings(path: Path) -> Settings:
    s = Settings()
    data: dict[str, Any] = {}
    if Path(path).exists():
        text = Path(path).read_text(encoding="utf-8")
        try:
            data = tomllib.loads(text).get("settings", {})
        except tomllib.TOMLDecodeError:
            data = {}
    try:
        if str(data.get("language", "")).strip() in LANG_CODES:
            s.language = str(data["language"]).strip()
        if data.get("date_format") in DATE_FORMATS:
            s.date_format = data["date_format"]
        if str(data.get("default_currency", "")).strip().upper() in CURRENCIES:
            s.default_currency = str(data["default_currency"]).strip().upper()
        if str(data.get("default_country", "")).strip().upper() in COUNTRIES:
            s.default_country = str(data["default_country"]).strip().upper()
        if data.get("sort_by") in ("dueDate", "paidDate", "description"):
            s.sort_by = data["sort_by"]
        if data.get("sort_order") in ("asc", "desc"):
            s.sort_order = data["sort_order"]
        if str(data.get("loglevel", "")).strip().lower() in ("debug", "info", "error"):
            s.loglevel = str(data["loglevel"]).strip().lower()
        s.data_folder = str(data.get("data_folder", "")).strip()
        s.logsize = max(100, min(1_000_000, int(data.get("logsize", s.logsize))))
    except (TypeError, ValueError):
        pass
    return s


def save_settings(path: Path, s: Settings) -> None:
    lines = ["[settings]"]
    for key, value in asdict(s).items():
        if isinstance(value, int):
            lines.append(f"{key} = {value}")
        else:
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    with _atomic_open(path) as fh:
        fh.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# Data folder setup
# --------------------------------------------------------------------------- #
def _migrate_csv(old: Path, new: Path) -> None:
    """Convert a file with the old d*/c* columns, keeping the original as a backup."""
    if not old.exists() or (old != new and new.exists()):
        return
    with open(old, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows or not LEGACY_COLUMNS.keys() & set(rows[0]):
        return
    shutil.copy2(old, old.with_name(old.name + ".pre-rename.bak"))
    rows[0] = [LEGACY_COLUMNS.get(column, column) for column in rows[0]]
    with _atomic_open(new) as fh:
        csv.writer(fh, lineterminator="\r\n").writerows(rows)
    if old != new:
        old.unlink()


def migrate_old_files(userdata: Path) -> None:
    _migrate_csv(userdata / "data.csv", userdata / "data.csv")
    _migrate_csv(userdata / "debitorList.csv", userdata / "recipientList.csv")
    _migrate_csv(userdata / "creditorList.csv", userdata / "payerList.csv")


def missing_data_files(folder: Path, templates: Path) -> list[str]:
    """The starter files that the data folder doesn't have (yet)."""
    return sorted(file.name for file in templates.glob("*.csv") if not (folder / file.name).exists())


def create_missing_files(folder: Path, templates: Path) -> None:
    """Create the folder if needed and copy in the missing starter files.
    Files that are already there are never overwritten."""
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in missing_data_files(folder, templates):
        shutil.copyfile(templates / name, folder / name)
        (folder / name).chmod(0o600)
