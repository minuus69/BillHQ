"""The editable bill form used by the new, edit and scan screens."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.widget import Widget
from textual.widgets import Checkbox, Input, Label, Select

from appdata.csvparser import (
    COUNTRIES, CURRENCIES, DATA_FIELDS, FIELD_LABELS, REQUIRED_FIELDS, Bill, Settings,
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
        self.w_due = self._inp("dueDate", format_date(b.dueDate, fmt), placeholder=fmt)
        self.w_paid_date = self._inp("paidDate", format_date(b.paidDate, fmt), placeholder=fmt)
        self.w_paid_with = self._inp("paidWith", b.paidWith,
                                     placeholder="ZKB / TWINT / Post …")
        self.w_checked = Checkbox(tr("f_paid_checked"), value=b.is_checked,
                                  id="form-paidChecked")
        self.w_amount = self._inp("bAmount", b.bAmount, placeholder="0.00")

        self.w_currency = self._choice("bCurrency", CURRENCIES, b.bCurrency)
        self.w_account = self._inp("bAccount", b.bAccount,
                                   placeholder="CH12 1234 1234 1234 1234 4")
        self.w_reference = self._inp("bReference", b.bReference,
                                     placeholder="21 00000 00000 …")
        self.w_note = self._inp("note", b.note)
        self.w_dname = self._inp("dName", b.dName)
        self.w_dstreet = self._inp("dStreet", b.dStreet)
        self.w_dnr = self._inp("dBuildingNr", b.dBuildingNr)
        self.w_dpc = self._inp("dPostalCode", b.dPostalCode)
        self.w_dcity = self._inp("dCity", b.dCity)

        self.w_dcountry = self._choice("dCountry", COUNTRIES, b.dCountry)
        self.w_cname = self._inp("cName", b.cName)
        self.w_cstreet = self._inp("cStreet", b.cStreet)
        self.w_cnr = self._inp("cBuildingNr", b.cBuildingNr)
        self.w_cpc = self._inp("cPostalCode", b.cPostalCode)
        self.w_ccity = self._inp("cCity", b.cCity)

        self.w_ccountry = self._choice("cCountry", COUNTRIES, b.cCountry)
        self.w_pnote = self._inp("privateNote", b.privateNote)

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
            yield Label(f"── {tr('debtor_section')} ──", classes="form-section")
            with Grid(classes="form-grid"):
                yield cell("f_dname", self.w_dname)
                yield cell("f_street", self.w_dstreet)
                yield cell("f_building_nr", self.w_dnr)
                yield cell("f_postal_code", self.w_dpc)
                yield cell("f_city", self.w_dcity)
                yield cell("f_country", self.w_dcountry)
            yield Label(f"── {tr('creditor_section')} ──", classes="form-section")
            with Grid(classes="form-grid"):
                yield cell("f_cname", self.w_cname)
                yield cell("f_street", self.w_cstreet)
                yield cell("f_building_nr", self.w_cnr)
                yield cell("f_postal_code", self.w_cpc)
                yield cell("f_city", self.w_ccity)
                yield cell("f_country", self.w_ccountry)
            yield Label(f"── {tr('f_private_note')} ──", classes="form-section")
            yield self.w_pnote

    # -- programmatic access -------------------------------------------------
    def set_value(self, field: str, value: str) -> None:
        if field == "paidChecked":
            self.w_checked.value = str(value).strip().lower() in ("true", "1", "yes")
        elif field == "bCurrency":
            if value in CURRENCIES:
                self.w_currency.value = value
        elif field == "dCountry":
            if value in COUNTRIES:
                self.w_dcountry.value = value
        elif field == "cCountry":
            if value in COUNTRIES:
                self.w_ccountry.value = value
        elif field in self.inputs:
            if field in ("dueDate", "paidDate") and value:
                value = format_date(value, self.settings.date_format)
            self.inputs[field].value = value

    def focus_first_field(self) -> None:
        self.w_description.focus()

    # -- validation + collect -------------------------------------------------
    def collect(self) -> tuple[Bill | None, str | None]:
        """Returns (bill, None) on success or (None, error_message)."""
        vals = {f: w.value.strip() for f, w in self.inputs.items()}
        vals["bCurrency"] = select_text(self.w_currency)
        vals["dCountry"] = select_text(self.w_dcountry)
        vals["cCountry"] = select_text(self.w_ccountry)
        vals["paidChecked"] = "True" if self.w_checked.value else "False"

        errors: list[str] = []
        missing = [f for f in REQUIRED_FIELDS if not vals.get(f)]
        if missing:
            names = ", ".join(tr(FIELD_LABELS[f]) for f in missing)
            errors.append(tr("msg_missing_required").format(fields=names))

        raw = vals.get("bAmount", "")
        if raw:
            try:
                vals["bAmount"] = f"{parse_amount(raw):.2f}"
            except ValueError:
                errors.append(tr("msg_invalid_amount"))

        for f in ("dueDate", "paidDate"):
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
        return Bill(**{f: vals.get(f, "") for f in DATA_FIELDS}), None
