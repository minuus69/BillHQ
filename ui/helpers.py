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
        row(tr("f_due_date"), format_date(bill.due_date, fmt)),
        row(tr("f_amount"), f"{format_amount(amount_decimal(bill.amount))} {bill.currency}"),
        "",
        f"── {tr('payment_section')} ──",
        row(tr("f_paid_date"), format_date(bill.paid_date, fmt)),
        row(tr("f_paid_with"), bill.paid_with),
        row(tr("f_paid_checked"), "✓" if bill.is_checked else "–"),
        row(tr("f_account"), bill.account),
        row(tr("f_reference"), bill.reference),
        row(tr("f_note"), bill.note),
        "",
        f"── {tr('recipient_section')} ──",
        row(tr("f_recipient_name"), bill.recipient_name),
        row(tr("f_street"), (bill.recipient_street + " " + bill.recipient_building_nr).strip()),
        row(tr("f_city"), (bill.recipient_postal_code + " " + bill.recipient_city).strip()),
        row(tr("f_country"), bill.recipient_country),
        "",
        f"── {tr('payer_section')} ──",
        row(tr("f_payer_name"), bill.payer_name),
        row(tr("f_street"), (bill.payer_street + " " + bill.payer_building_nr).strip()),
        row(tr("f_city"), (bill.payer_postal_code + " " + bill.payer_city).strip()),
        row(tr("f_country"), bill.payer_country),
        "",
        row(tr("f_private_note"), bill.private_note),
    ]
    return "\n".join(lines)
