"""Creating a bill, optionally starting from templates."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Select

from appdata.csvparser import CREDITOR_FIELDS, Bill
from appdata.languages import tr
from ui.screens.base import BillFormScreen
from ui.screens.bills import BillsScreen

DEBITOR_TEMPLATE_TO_BILL = {
    "description": "description", "bAmount": "amount", "bCurrency": "currency",
    "bAccount": "account", "dName": "dName", "dStreet": "dStreet",
    "dBuildingNr": "dBuildingNr", "dPostalCode": "dPostalCode", "dCity": "dCity",
    "dCountry": "dCountry",
}
CREDITOR_TEMPLATE_TO_BILL = {f: f for f in CREDITOR_FIELDS}


class NewBillScreen(BillFormScreen):
    title_key = "new_bill_title"

    def initial_bill(self) -> Bill:
        settings = self.core.settings
        return Bill(bCurrency=settings.default_currency, dCountry=settings.default_country,
                    cCountry=settings.default_country)

    def compose_above_form(self) -> ComposeResult:
        with Horizontal(classes="tpl-row"):
            with Vertical(classes="tpl-cell"):
                yield Label(tr("tpl_debtor"))
                yield Select(self._options(self.core.debitors, debtor=True), allow_blank=True,
                             prompt=tr("tpl_none"), id="tpl-debtor")
            with Vertical(classes="tpl-cell"):
                yield Label(tr("tpl_creditor"))
                yield Select(self._options(self.core.creditors, debtor=False), allow_blank=True,
                             prompt=tr("tpl_none"), id="tpl-creditor")

    @staticmethod
    def _options(rows: list[dict], debtor: bool) -> list[tuple[str, int]]:
        opts = []
        for i, r in enumerate(rows):
            if debtor:
                label = " · ".join(p for p in (r.get("description", ""), r.get("dName", ""))
                                   if p.strip())
            else:
                label = (r.get("cName") or "").strip()
            opts.append((label or f"#{i + 1}", i))
        return opts

    def on_select_changed(self, event: Select.Changed) -> None:
        if not isinstance(event.value, int):      # dropdown cleared
            return
        if event.select.id == "tpl-debtor":
            template, mapping = self.core.debitors[event.value], DEBITOR_TEMPLATE_TO_BILL
        elif event.select.id == "tpl-creditor":
            template, mapping = self.core.creditors[event.value], CREDITOR_TEMPLATE_TO_BILL
        else:
            return
        for target, source in mapping.items():
            value = (template.get(source) or "").strip()
            if value:
                self.form.set_value(target, value)
        self.core.logger.info(f"template applied ({event.select.id})")

    def apply(self, bill: Bill) -> None:
        self.core.bills.append(bill)

    def leave(self) -> None:
        # Don't await this: it waits for this screen to close, which can't happen
        # while this screen is still busy handling the save, and the app freezes.
        self.app.switch_screen(BillsScreen())
