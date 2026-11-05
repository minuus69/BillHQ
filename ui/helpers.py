"""Small helpers shared by the screens."""
from __future__ import annotations

from textual.widgets import Select

from appdata.csvparser import Bill, Settings, amount_decimal, format_date
from appdata.languages import tr


def format_amount(value) -> str:
    """1234.5 -> 1'234.50"""
    return f"{value:,.2f}".replace(",", "'")


def select_text(select: Select) -> str:
    """The chosen option, or "" when a dropdown is blank (its value isn't a string then)."""
    return select.value if isinstance(select.value, str) else ""


def detail_text(bill: Bill, settings: Settings) -> str:
    """Plain-text version of bill details (for selectable TextArea)."""
    fmt = settings.date_format
    W = 17  # label column width

    def row(label: str, value: str) -> str:
        return f"{label:<{W}} {value or '–'}"

    lines = [
        row(tr("f_description"), bill.description),
        row(tr("f_due_date"), format_date(bill.dueDate, fmt)),
        row(tr("f_amount"), f"{format_amount(amount_decimal(bill.bAmount))} {bill.bCurrency}"),
        "",
        f"── {tr('payment_section')} ──",
        row(tr("f_paid_date"), format_date(bill.paidDate, fmt)),
        row(tr("f_paid_with"), bill.paidWith),
        row(tr("f_paid_checked"), "✓" if bill.is_checked else "–"),
        row(tr("f_account"), bill.bAccount),
        row(tr("f_reference"), bill.bReference),
        row(tr("f_note"), bill.note),
        "",
        f"── {tr('debtor_section')} ──",
        row(tr("f_dname"), bill.dName),
        row(tr("f_street"), (bill.dStreet + " " + bill.dBuildingNr).strip()),
        row(tr("f_city"), (bill.dPostalCode + " " + bill.dCity).strip()),
        row(tr("f_country"), bill.dCountry),
        "",
        f"── {tr('creditor_section')} ──",
        row(tr("f_cname"), bill.cName),
        row(tr("f_street"), (bill.cStreet + " " + bill.cBuildingNr).strip()),
        row(tr("f_city"), (bill.cPostalCode + " " + bill.cCity).strip()),
        row(tr("f_country"), bill.cCountry),
        "",
        row(tr("f_private_note"), bill.privateNote),
    ]
    return "\n".join(lines)
