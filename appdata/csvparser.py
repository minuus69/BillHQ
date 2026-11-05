"""Data layer: CSV files (data.csv, debitorList.csv, creditorList.csv),
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
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator, TextIO

from appdata.languages import LANG_CODES

# --------------------------------------------------------------------------- #
# Field definitions
# --------------------------------------------------------------------------- #
DATA_FIELDS = [
    "description", "dueDate", "paidDate", "paidWith", "paidChecked",
    "bAmount", "bCurrency", "bAccount", "bReference", "note",
    "dName", "dStreet", "dBuildingNr", "dPostalCode", "dCity", "dCountry",
    "cName", "cStreet", "cBuildingNr", "cPostalCode", "cCity", "cCountry",
    "privateNote",
]

# fields marked with * in the spec: must be non-empty to be saved
REQUIRED_FIELDS = [
    "description", "bAmount", "bCurrency", "bAccount",
    "dName", "dPostalCode", "dCity", "dCountry",
]

DEBITOR_FIELDS = ["description", "amount", "currency", "account", "dName", "dStreet",
                  "dBuildingNr", "dPostalCode", "dCity", "dCountry"]
CREDITOR_FIELDS = ["cName", "cStreet", "cBuildingNr", "cPostalCode", "cCity", "cCountry"]

# translation keys for field labels (used in validation errors)
FIELD_LABELS = {
    "description": "f_description", "dueDate": "f_due_date", "paidDate": "f_paid_date",
    "paidWith": "f_paid_with", "paidChecked": "f_paid_checked", "bAmount": "f_amount",
    "bCurrency": "f_currency", "bAccount": "f_account", "bReference": "f_reference",
    "note": "f_note", "dName": "f_dname", "dStreet": "f_street",
    "dBuildingNr": "f_building_nr", "dPostalCode": "f_postal_code", "dCity": "f_city",
    "dCountry": "f_country", "cName": "f_cname", "cStreet": "f_street",
    "cBuildingNr": "f_building_nr", "cPostalCode": "f_postal_code", "cCity": "f_city",
    "cCountry": "f_country", "privateNote": "f_private_note",
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
    dueDate: str = ""          # ISO yyyy-mm-dd in the CSV
    paidDate: str = ""         # empty = unpaid
    paidWith: str = ""
    paidChecked: str = ""      # "True" / "False"
    bAmount: str = ""
    bCurrency: str = ""
    bAccount: str = ""
    bReference: str = ""
    note: str = ""
    dName: str = ""
    dStreet: str = ""
    dBuildingNr: str = ""
    dPostalCode: str = ""
    dCity: str = ""
    dCountry: str = ""
    cName: str = ""
    cStreet: str = ""
    cBuildingNr: str = ""
    cPostalCode: str = ""
    cCity: str = ""
    cCountry: str = ""
    privateNote: str = ""

    @property
    def is_paid(self) -> bool:
        return bool(self.paidDate.strip())

    @property
    def is_checked(self) -> bool:
        return self.paidChecked.strip().lower() in ("true", "1", "yes", "x")

    def to_row(self) -> dict[str, str]:
        return {f: str(getattr(self, f)) for f in DATA_FIELDS}

    @classmethod
    def from_row(cls, row: dict) -> "Bill":
        return cls(**{f: (row.get(f) or "").strip() for f in DATA_FIELDS})


def bill_state(bill: Bill, today: date | None = None) -> str:
    """Returns 'paid', 'overdue', or 'open'."""
    if bill.is_paid:
        return "paid"
    try:
        due = parse_date(bill.dueDate)
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
        field = sort_by if sort_by in ("dueDate", "paidDate") else "dueDate"
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
        writer = csv.DictWriter(fh, fieldnames=DATA_FIELDS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for b in bills:
            writer.writerow(b.to_row())


def _clean_cell(value: str | None) -> str:
    """Older versions could store an untouched dropdown as this text."""
    value = (value or "").strip()
    return "" if value in ("Select.NULL", "Select.BLANK") else value


def read_rows(path: Path, fields: list[str]) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [{k: _clean_cell(row.get(k)) for k in fields} for row in csv.DictReader(fh)]


def write_rows(path: Path, fields: list[str], rows: list[dict]) -> None:
    with _atomic_open(path, backup=True) as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fields})


# --------------------------------------------------------------------------- #
# Settings (TOML)
# --------------------------------------------------------------------------- #
@dataclass
class Settings:
    language: str = "en"
    date_format: str = "dd.mm.yyyy"
    default_currency: str = "CHF"
    default_country: str = "CH"
    sort_by: str = "dueDate"          # dueDate | paidDate | description
    sort_order: str = "asc"           # asc | desc
    loglevel: str = "info"            # debug | info | error
    logsize: int = 2048               # max lines kept in appdata/log


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
            lines.append(f'{key} = "{value}"')
    with _atomic_open(path) as fh:
        fh.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# First-run bootstrap (creates userdata files with demo content)
# --------------------------------------------------------------------------- #
def _sample_bills() -> list[Bill]:
    today = date.today()
    return [
        Bill(
            description="Steueramt: Finanzamt Steuerbestätigung",
            dueDate=(today + timedelta(days=8)).isoformat(),
            bAmount="1250.00", bCurrency="CHF",
            bAccount="CH93 0076 2011 6238 5295 7",
            bReference="21 00000 00003 13947 14300 09017",
            note="Steuerrechnung",
            dName="Finanzamt Zürich", dStreet="Sihlstrasse", dBuildingNr="23",
            dPostalCode="8001", dCity="Zürich", dCountry="CH",
            cName="Max Muster", cStreet="Musterweg", cBuildingNr="12",
            cPostalCode="8000", cCity="Zürich", cCountry="CH",
        ),
        Bill(
            description="Online Shop: Bestellung #4711",
            dueDate=(today + timedelta(days=40)).isoformat(),
            bAmount="89.99", bCurrency="EUR",
            bAccount="CH12 1234 1234 1234 1234 4",
            bReference="RF18 5390 0754 7018 5",
            dName="Beispiel Handel AG", dStreet="Bahnhofstrasse", dBuildingNr="1",
            dPostalCode="3000", dCity="Bern", dCountry="CH",
            cName="Max Muster", cStreet="Musterweg", cBuildingNr="12",
            cPostalCode="8000", cCity="Zürich", cCountry="CH",
        ),
        Bill(
            description="Swisscom: Abo",
            dueDate=(today - timedelta(days=20)).isoformat(),
            paidDate=(today - timedelta(days=19)).isoformat(),
            paidWith="TWINT", paidChecked="True",
            bAmount="79.90", bCurrency="CHF",
            bAccount="CH93 0076 2011 6238 5295 7",
            bReference="21 00000 00003 13947 14300 09017",
            dName="Swisscom AG", dStreet="Alte Tiefenaustrasse", dBuildingNr="6",
            dPostalCode="3048", dCity="Worblaufen", dCountry="CH",
            cName="Max Muster", cStreet="Musterweg", cBuildingNr="12",
            cPostalCode="8000", cCity="Zürich", cCountry="CH",
        ),
    ]


def bootstrap_files(userdata: Path, appdata: Path) -> None:
    userdata.mkdir(parents=True, exist_ok=True)
    appdata.mkdir(parents=True, exist_ok=True)

    log_path = appdata / "log"
    if not log_path.exists():
        log_path.touch()

    settings_path = userdata / "settings.toml"
    if not settings_path.exists():
        save_settings(settings_path, Settings())

    deb_path = userdata / "debitorList.csv"
    if not deb_path.exists():
        write_rows(deb_path, DEBITOR_FIELDS, [
            {"description": "Steuerrechnung", "amount": "1250.00", "currency": "CHF",
             "dName": "Finanzamt Zürich", "dStreet": "Sihlstrasse", "dBuildingNr": "23",
             "dPostalCode": "8001", "dCity": "Zürich", "dCountry": "CH"},
            {"description": "Stromrechnung", "amount": "85.40", "currency": "CHF",
             "dName": "EWZ", "dStreet": "Technoparkstrasse", "dBuildingNr": "1",
             "dPostalCode": "8005", "dCity": "Zürich", "dCountry": "CH"},
        ])

    cred_path = userdata / "creditorList.csv"
    if not cred_path.exists():
        write_rows(cred_path, CREDITOR_FIELDS, [
            {"cName": "Max Muster", "cStreet": "Musterweg", "cBuildingNr": "12",
             "cPostalCode": "8000", "cCity": "Zürich", "cCountry": "CH"},
        ])

    data_path = userdata / "data.csv"
    if not data_path.exists():
        save_bills(data_path, _sample_bills())
