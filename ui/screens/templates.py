"""Managing the debitor and creditor template lists."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Middle, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, Header, Input, Label, ListView, Select, Static

from appdata.core import Core
from appdata.csvparser import (
    COUNTRIES, CREDITOR_FIELDS, CURRENCIES, DEBITOR_FIELDS, parse_amount, write_rows,
)
from appdata.languages import tr
from ui.dialogs import ConfirmDeleteModal
from ui.helpers import select_text
from ui.screens.menus import MenuItem


class ManageScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle(id="menu-wrap"):
            with Vertical(id="menu-panel"):
                yield Static(tr("menu_manage"), id="menu-title")
                yield ListView(
                    MenuItem(tr("manage_debitors"), "debitors"),
                    MenuItem(tr("manage_creditors"), "creditors"),
                    id="menu-list",
                )
        yield Static(tr("hint_nav"), id="footer-hint")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = getattr(event.item, "menu_key", None)
        if key == "debitors":
            self.app.push_screen(ManageListScreen("debitor"))
        elif key == "creditors":
            self.app.push_screen(ManageListScreen("creditor"))

    def action_back(self) -> None:
        self.app.pop_screen()


class ManageListScreen(Screen):
    BINDINGS = [
        Binding("up", "nav_up", "Up"),
        Binding("down", "nav_down", "Down"),
        Binding("escape", "back", "Back"),
        Binding("delete", "delete_entry", "Delete"),
    ]

    def __init__(self, list_type: str):
        super().__init__()
        self.list_type = list_type  # "debitor" or "creditor"
        self.selected = 0

    @property
    def core(self) -> Core:
        return self.app.core

    @property
    def entries(self) -> list[dict]:
        return self.core.debitors if self.list_type == "debitor" else self.core.creditors

    def compose(self) -> ComposeResult:
        title = tr("manage_debitors") if self.list_type == "debitor" else tr("manage_creditors")
        yield Header()
        with VerticalScroll(id="manage-scroll"):
            yield Static(title, classes="screen-title")
            with Horizontal(classes="manage-buttons"):
                add = Button(tr("btn_add"), variant="success", id="btn-manage-add")
                delete = Button(tr("btn_delete"), variant="error", id="btn-manage-delete")
                add.kind = "add"
                delete.kind = "delete"
                yield add
                yield delete
            yield Static("", id="manage-count", classes="muted")
            yield Vertical(id="manage-entries")
        yield Static(tr("hint_nav"), id="footer-hint")

    async def on_mount(self) -> None:
        await self.rebuild()

    async def rebuild(self) -> None:
        container = self.query_one("#manage-entries", Vertical)
        await container.remove_children()
        entries = self.entries
        self.query_one("#manage-count", Static).update(
            tr("entries_count").format(n=len(entries)))
        self.selected = max(0, min(self.selected, len(entries) - 1))
        for i, entry in enumerate(entries):
            label = self._entry_label(entry)
            item = ManageEntryItem(label, i)
            item.set_class(i == self.selected, "selected")
            await container.mount(item)

    def _entry_label(self, entry: dict) -> str:
        if self.list_type == "debitor":
            parts = [entry.get("description", ""), entry.get("dName", "")]
        else:
            parts = [entry.get("cName", "")]
        return " · ".join(p for p in parts if p.strip()) or "–"

    def _highlight(self) -> None:
        items = self.query(ManageEntryItem)
        for i, item in enumerate(items):
            item.set_class(i == self.selected, "selected")
            if i == self.selected:
                item.scroll_visible()

    def action_nav_up(self) -> None:
        self._move(-1)

    def action_nav_down(self) -> None:
        self._move(1)

    def _move(self, delta: int) -> None:
        if self.entries:
            self.selected = max(0, min(len(self.entries) - 1, self.selected + delta))
            self._highlight()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        kind = getattr(event.button, "kind", None)
        if kind == "add":
            if self.list_type == "debitor":
                self.app.push_screen(AddDebitorScreen())
            else:
                self.app.push_screen(AddCreditorScreen())
        elif kind == "delete":
            if 0 <= self.selected < len(self.entries):
                async def on_confirm(result: bool) -> None:
                    if result:
                        self.entries.pop(self.selected)
                        self._save_list()
                        self.notify(tr("entry_deleted"))
                        await self.rebuild()
                self.app.push_screen(ConfirmDeleteModal(tr("confirm_delete_entry")), on_confirm)

    def action_delete_entry(self) -> None:
        if 0 <= self.selected < len(self.entries):
            async def on_confirm(result: bool) -> None:
                if result:
                    self.entries.pop(self.selected)
                    self._save_list()
                    self.notify(tr("entry_deleted"))
                    await self.rebuild()
            self.app.push_screen(ConfirmDeleteModal(tr("confirm_delete_entry")), on_confirm)

    def _save_list(self) -> None:
        if self.list_type == "debitor":
            write_rows(self.core.userdata / "debitorList.csv", DEBITOR_FIELDS, self.core.debitors)
        else:
            write_rows(self.core.userdata / "creditorList.csv", CREDITOR_FIELDS, self.core.creditors)
        self.core.logger.info(f"{self.list_type} list saved ({len(self.entries)} entries)")

    async def on_screen_resume(self) -> None:
        await self.rebuild()

    def action_back(self) -> None:
        self.app.pop_screen()


class ManageEntryItem(Static):
    def __init__(self, label: str, index: int):
        super().__init__(f" {label}", classes="manage-entry", markup=False)
        self.entry_index = index

    def on_click(self) -> None:
        screen = self.screen
        if isinstance(screen, ManageListScreen):
            screen.selected = self.entry_index
            screen._highlight()


class AddDebitorScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="newbill-scroll"):
            yield Static(tr("add_debitor_title"), classes="screen-title")
            with Grid(classes="form-grid"):
                yield self._cell("f_description", Input(id="deb-description"))
                yield self._cell("f_amount", Input(id="deb-amount", placeholder="0.00"))
                yield self._cell("f_currency", Select([(c, c) for c in CURRENCIES],
                             allow_blank=True, prompt="–", id="deb-currency"))
                yield self._cell("f_account_iban", Input(id="deb-account",
                             placeholder="CH12 1234 1234 1234 1234 4"))
                yield self._cell("f_dname", Input(id="deb-dname"))
                yield self._cell("f_street", Input(id="deb-dstreet"))
                yield self._cell("f_building_nr", Input(id="deb-dnr"))
                yield self._cell("f_postal_code", Input(id="deb-dpc"))
                yield self._cell("f_city", Input(id="deb-dcity"))
                yield self._cell("f_country", Select([(c, c) for c in COUNTRIES],
                             allow_blank=True, prompt="–", id="deb-dcountry"))
            with Horizontal(classes="newbill-buttons"):
                yield Button(tr("btn_save"), variant="success", id="btn-deb-save")
                yield Button(tr("btn_cancel"), id="btn-deb-cancel")
        yield Static(tr("hint_nav"), id="footer-hint")

    def _cell(self, label_key: str, control: Widget) -> Vertical:
        return Vertical(Label(tr(label_key)), control, classes="form-cell")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-deb-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-deb-save":
            entry = {
                "description": self.query_one("#deb-description", Input).value.strip(),
                "amount": self.query_one("#deb-amount", Input).value.strip(),
                "currency": select_text(self.query_one("#deb-currency", Select)),
                "account": self.query_one("#deb-account", Input).value.strip(),
                "dName": self.query_one("#deb-dname", Input).value.strip(),
                "dStreet": self.query_one("#deb-dstreet", Input).value.strip(),
                "dBuildingNr": self.query_one("#deb-dnr", Input).value.strip(),
                "dPostalCode": self.query_one("#deb-dpc", Input).value.strip(),
                "dCity": self.query_one("#deb-dcity", Input).value.strip(),
                "dCountry": select_text(self.query_one("#deb-dcountry", Select)),
            }
            if entry["amount"]:
                try:
                    entry["amount"] = f"{parse_amount(entry['amount']):.2f}"
                except ValueError:
                    self.notify(tr("msg_invalid_amount"), severity="error")
                    return
            if not entry["dName"]:
                self.notify(tr("msg_missing_required").format(fields=tr("f_dname")),
                            severity="error")
                return
            self.app.core.debitors.append(entry)
            write_rows(self.app.core.userdata / "debitorList.csv",
                       DEBITOR_FIELDS, self.app.core.debitors)
            self.app.core.logger.info(f"debitor template added: {entry['dName']!r}")
            self.notify(tr("entry_added"))
            self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()


class AddCreditorScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="newbill-scroll"):
            yield Static(tr("add_creditor_title"), classes="screen-title")
            with Grid(classes="form-grid"):
                yield self._cell("f_cname", Input(id="cred-cname"))
                yield self._cell("f_street", Input(id="cred-cstreet"))
                yield self._cell("f_building_nr", Input(id="cred-cnr"))
                yield self._cell("f_postal_code", Input(id="cred-cpc"))
                yield self._cell("f_city", Input(id="cred-ccity"))
                yield self._cell("f_country", Select([(c, c) for c in COUNTRIES],
                             allow_blank=True, prompt="–", id="cred-ccountry"))
            with Horizontal(classes="newbill-buttons"):
                yield Button(tr("btn_save"), variant="success", id="btn-cred-save")
                yield Button(tr("btn_cancel"), id="btn-cred-cancel")
        yield Static(tr("hint_nav"), id="footer-hint")

    def _cell(self, label_key: str, control: Widget) -> Vertical:
        return Vertical(Label(tr(label_key)), control, classes="form-cell")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cred-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-cred-save":
            entry = {
                "cName": self.query_one("#cred-cname", Input).value.strip(),
                "cStreet": self.query_one("#cred-cstreet", Input).value.strip(),
                "cBuildingNr": self.query_one("#cred-cnr", Input).value.strip(),
                "cPostalCode": self.query_one("#cred-cpc", Input).value.strip(),
                "cCity": self.query_one("#cred-ccity", Input).value.strip(),
                "cCountry": select_text(self.query_one("#cred-ccountry", Select)),
            }
            if not entry["cName"]:
                self.notify(tr("msg_missing_required").format(fields=tr("f_cname")),
                            severity="error")
                return
            self.app.core.creditors.append(entry)
            write_rows(self.app.core.userdata / "creditorList.csv",
                       CREDITOR_FIELDS, self.app.core.creditors)
            self.app.core.logger.info(f"creditor template added: {entry['cName']!r}")
            self.notify(tr("entry_added"))
            self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()
