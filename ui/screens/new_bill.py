"""Creating a bill, optionally starting from templates."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Select

from appdata.csvparser import Bill
from appdata.languages import tr
from ui.screens.base import BillFormScreen
from ui.screens.bills import BillsScreen


class NewBillScreen(BillFormScreen):
    title_key = "new_bill_title"

    def initial_bill(self) -> Bill:
        settings = self.core.settings
        return Bill(currency=settings.default_currency, payee_country=settings.default_country,
                    payer_country=settings.default_country)

    def compose_above_form(self) -> ComposeResult:
        with Horizontal(classes="tpl-row"):
            with Vertical(classes="tpl-cell"):
                yield Label(tr("tpl_payee"))
                yield Select(self._options(self.core.payee_templates, payee=True), allow_blank=True,
                             prompt=tr("tpl_none"), id="tpl-payee")
            with Vertical(classes="tpl-cell"):
                yield Label(tr("tpl_payer"))
                yield Select(self._options(self.core.payer_templates, payee=False), allow_blank=True,
                             prompt=tr("tpl_none"), id="tpl-payer")

    @staticmethod
    def _options(rows: list[dict], payee: bool) -> list[tuple[str, int]]:
        opts = []
        for i, r in enumerate(rows):
            if payee:
                label = " · ".join(p for p in (r.get("description", ""), r.get("payee_name", ""))
                                   if p.strip())
            else:
                label = (r.get("payer_name") or "").strip()
            opts.append((label or f"#{i + 1}", i))
        return opts

    def on_select_changed(self, event: Select.Changed) -> None:
        if not isinstance(event.value, int):      # dropdown cleared
            return
        if event.select.id == "tpl-payee":
            template = self.core.payee_templates[event.value]
        elif event.select.id == "tpl-payer":
            template = self.core.payer_templates[event.value]
        else:
            return
        for field, value in template.items():
            if value.strip():
                self.form.set_value(field, value.strip())
        self.core.logger.info(f"template applied ({event.select.id})")

    def apply(self, bill: Bill) -> None:
        self.core.bills.append(bill)

    def leave(self) -> None:
        # Don't await this: it waits for this screen to close, which can't happen
        # while this screen is still busy handling the save, and the app freezes.
        self.app.switch_screen(BillsScreen())
