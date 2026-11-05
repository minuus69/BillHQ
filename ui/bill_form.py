"""The editable bill form used by the new, edit and scan screens."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.widget import Widget
from textual.widgets import Checkbox, Input, Label, Select

from appdata.csvparser import (
    COUNTRIES, CURRENCIES, BILL_FIELDS, FIELD_LABELS, REQUIRED_FIELDS, Bill, Settings,
    format_date, parse_amount, parse_date,
)
from appdata.languages import tr
from ui.helpers import select_text


class BillEditForm(Widget):
    def __init__(self, bill: Bill, settings: Settings):
        super().__init__()
        self.bill = bill
        self.settings = settings
        self.inputs: dict[str, Input] = {}
        self._build()

    # -- construction -------------------------------------------------------
    def _inp(self, field: str, value: str, placeholder: str = "") -> Input:
        widget = Input(value=value or "", placeholder=placeholder, id=f"form-{field}")
        self.inputs[field] = widget
        return widget

    def _choice(self, field: str, options: list[str], value: str) -> Select:
        """Dropdown showing the bill's current value, even if it isn't a standard
        option, so editing a bill never silently changes it."""
        choices = options if not value or value in options else [*options, value]
        preset = {"value": value} if value else {}
        return Select([(c, c) for c in choices], allow_blank=True, prompt="–",
                      id=f"form-{field}", **preset)

    def _build(self) -> None:
        b, fmt = self.bill, self.settings.date_format
        self.w_description = self._inp("description", b.description)
        self.w_due = self._inp("due_date", format_date(b.due_date, fmt), placeholder=fmt)
        self.w_paid_date = self._inp("paid_date", format_date(b.paid_date, fmt), placeholder=fmt)
        self.w_paid_with = self._inp("paid_with", b.paid_with,
                                     placeholder="ZKB / TWINT / Post …")
        self.w_checked = Checkbox(tr("f_paid_checked"), value=b.is_checked,
                                  id="form-paid_checked")
        self.w_amount = self._inp("amount", b.amount, placeholder="0.00")

        self.w_currency = self._choice("currency", CURRENCIES, b.currency)
        self.w_account = self._inp("account", b.account,
                                   placeholder="CH12 1234 1234 1234 1234 4")
        self.w_reference = self._inp("reference", b.reference,
                                     placeholder="21 00000 00000 …")
        self.w_note = self._inp("note", b.note)
        self.w_recipient_name = self._inp("recipient_name", b.recipient_name)
        self.w_recipient_street = self._inp("recipient_street", b.recipient_street)
        self.w_recipient_building_nr = self._inp("recipient_building_nr", b.recipient_building_nr)
        self.w_recipient_postal_code = self._inp("recipient_postal_code", b.recipient_postal_code)
        self.w_recipient_city = self._inp("recipient_city", b.recipient_city)

        self.w_recipient_country = self._choice("recipient_country", COUNTRIES, b.recipient_country)
        self.w_payer_name = self._inp("payer_name", b.payer_name)
        self.w_payer_street = self._inp("payer_street", b.payer_street)
        self.w_payer_building_nr = self._inp("payer_building_nr", b.payer_building_nr)
        self.w_payer_postal_code = self._inp("payer_postal_code", b.payer_postal_code)
        self.w_payer_city = self._inp("payer_city", b.payer_city)

        self.w_payer_country = self._choice("payer_country", COUNTRIES, b.payer_country)
        self.w_private_note = self._inp("private_note", b.private_note)

    def compose(self) -> ComposeResult:
        def cell(label_key: str, control: Widget) -> Vertical:
            return Vertical(Label(tr(label_key)), control, classes="form-cell")

        with Vertical(classes="edit-form"):
            yield Label(f"── {tr('bill_section')} ──", classes="form-section")
            with Grid(classes="form-grid"):
                yield cell("f_description", self.w_description)
                yield cell("f_due_date", self.w_due)
                yield cell("f_amount", self.w_amount)
                yield cell("f_currency", self.w_currency)
                yield cell("f_account", self.w_account)
                yield cell("f_reference", self.w_reference)
                yield cell("f_note", self.w_note)
                yield cell("f_paid_date", self.w_paid_date)
                yield cell("f_paid_with", self.w_paid_with)
                yield Vertical(self.w_checked, classes="form-cell")
            yield Label(f"── {tr('recipient_section')} ──", classes="form-section")
            with Grid(classes="form-grid"):
                yield cell("f_recipient_name", self.w_recipient_name)
                yield cell("f_street", self.w_recipient_street)
                yield cell("f_building_nr", self.w_recipient_building_nr)
                yield cell("f_postal_code", self.w_recipient_postal_code)
                yield cell("f_city", self.w_recipient_city)
                yield cell("f_country", self.w_recipient_country)
            yield Label(f"── {tr('payer_section')} ──", classes="form-section")
            with Grid(classes="form-grid"):
                yield cell("f_payer_name", self.w_payer_name)
                yield cell("f_street", self.w_payer_street)
                yield cell("f_building_nr", self.w_payer_building_nr)
                yield cell("f_postal_code", self.w_payer_postal_code)
                yield cell("f_city", self.w_payer_city)
                yield cell("f_country", self.w_payer_country)
            yield Label(f"── {tr('f_private_note')} ──", classes="form-section")
            yield self.w_private_note

    # -- programmatic access -------------------------------------------------
    def set_value(self, field: str, value: str) -> None:
        if field == "paid_checked":
            self.w_checked.value = str(value).strip().lower() in ("true", "1", "yes")
        elif field == "currency":
            if value in CURRENCIES:
                self.w_currency.value = value
        elif field == "recipient_country":
            if value in COUNTRIES:
                self.w_recipient_country.value = value
        elif field == "payer_country":
            if value in COUNTRIES:
                self.w_payer_country.value = value
        elif field in self.inputs:
            if field in ("due_date", "paid_date") and value:
                value = format_date(value, self.settings.date_format)
            self.inputs[field].value = value

    def focus_first_field(self) -> None:
        self.w_description.focus()

    # -- validation + collect -------------------------------------------------
    def collect(self) -> tuple[Bill | None, str | None]:
        """Returns (bill, None) on success or (None, error_message)."""
        vals = {f: w.value.strip() for f, w in self.inputs.items()}
        vals["currency"] = select_text(self.w_currency)
        vals["recipient_country"] = select_text(self.w_recipient_country)
        vals["payer_country"] = select_text(self.w_payer_country)
        vals["paid_checked"] = "True" if self.w_checked.value else "False"

        errors: list[str] = []
        missing = [f for f in REQUIRED_FIELDS if not vals.get(f)]
        if missing:
            names = ", ".join(tr(FIELD_LABELS[f]) for f in missing)
            errors.append(tr("msg_missing_required").format(fields=names))

        raw = vals.get("amount", "")
        if raw:
            try:
                vals["amount"] = f"{parse_amount(raw):.2f}"
            except ValueError:
                errors.append(tr("msg_invalid_amount"))

        for f in ("due_date", "paid_date"):
            txt = vals.get(f, "")
            if not txt:
                vals[f] = ""
                continue
            try:
                vals[f] = parse_date(txt, self.settings.date_format).isoformat()
            except ValueError:
                errors.append(f"{tr(FIELD_LABELS[f])}: {tr('msg_invalid_date')}")

        if errors:
            return None, " · ".join(errors)
        return Bill(**{f: vals.get(f, "") for f in BILL_FIELDS}), None
