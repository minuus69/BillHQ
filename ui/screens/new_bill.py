"""Creating a bill, optionally starting from templates."""
from __future__ import annotations

from uuid import uuid4

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Header, Label, Select, Static

from appdata.core import Core
from appdata.csvparser import CREDITOR_FIELDS, Bill
from appdata.languages import tr
from ui.bill_form import BillEditForm
from ui.screens.bills import BillsScreen


class NewBillScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        core: Core = self.app.core
        blank = Bill(
            bCurrency=core.settings.default_currency,
            dCountry=core.settings.default_country,
            cCountry=core.settings.default_country,
        )
        self.form = BillEditForm(blank, core.settings, f"new{uuid4().hex[:6]}")
        yield Header()
        with VerticalScroll(id="newbill-scroll"):
            yield Static(tr("new_bill_title"), classes="screen-title")
            with Horizontal(classes="tpl-row"):
                with Vertical(classes="tpl-cell"):
                    yield Label(tr("tpl_debtor"))
                    yield Select(self._options(core.debitors, debtor=True), allow_blank=True,
                                 prompt=tr("tpl_none"), id="tpl-debtor")
                with Vertical(classes="tpl-cell"):
                    yield Label(tr("tpl_creditor"))
                    yield Select(self._options(core.creditors, debtor=False), allow_blank=True,
                                 prompt=tr("tpl_none"), id="tpl-creditor")
            yield self.form
            with Horizontal(classes="newbill-buttons"):
                yield Button(tr("btn_save"), variant="success", id="btn-new-save")
                yield Button(tr("btn_cancel"), id="btn-new-cancel")
        yield Static(tr("hint_nav"), id="footer-hint")

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
        core: Core = self.app.core
        if event.select.id == "tpl-debtor" and event.value < len(core.debitors):
            tpl = core.debitors[event.value]
            mapping = {"description": "description", "bAmount": "amount",
                       "bCurrency": "currency", "bAccount": "account",
                       "dName": "dName", "dStreet": "dStreet",
                       "dBuildingNr": "dBuildingNr", "dPostalCode": "dPostalCode",
                       "dCity": "dCity", "dCountry": "dCountry"}
        elif event.select.id == "tpl-creditor" and event.value < len(core.creditors):
            tpl = core.creditors[event.value]
            mapping = {f: f for f in CREDITOR_FIELDS}
        else:
            return
        for target, source in mapping.items():
            value = (tpl.get(source) or "").strip()
            if value:
                self.form.set_value(target, value)
        core.logger.info(f"template applied ({event.select.id})")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-new-save":
            core: Core = self.app.core
            bill, err = self.form.collect()
            if err:
                core.logger.warning(f"new bill rejected: {err}")
                self.notify(err, severity="error", timeout=10)
                return
            core.bills.append(bill)
            core.persist()
            core.logger.info(f"new bill saved: {bill.description!r}")
            self.notify(tr("msg_bill_saved"))
            await self.app.switch_screen(BillsScreen())

    def action_back(self) -> None:
        self.app.pop_screen()
