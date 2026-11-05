"""Managing the payee and payer template lists."""
from __future__ import annotations

from typing import NamedTuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Header, Input, Label, Select, Static

from appdata.csvparser import COUNTRIES, CURRENCIES, parse_amount
from appdata.languages import tr
from ui.dialogs import ConfirmDeleteModal
from ui.helpers import select_text
from ui.screens.base import BackScreen, MenuItem, MenuScreen


class ManageScreen(MenuScreen):
    def menu_title(self) -> str:
        return tr("menu_manage")

    def menu_items(self) -> list[MenuItem]:
        return [MenuItem(tr("manage_payees"), "payee"),
                MenuItem(tr("manage_payers"), "payer")]

    def menu_selected(self, key: str) -> None:
        self.app.push_screen(ManageListScreen(key))


class ManageListScreen(BackScreen):
    BINDINGS = [
        Binding("up", "nav_up", "Up"),
        Binding("down", "nav_down", "Down"),
        Binding("delete", "delete_entry", "Delete"),
    ]

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind  # "payee" or "payer"
        self.selected = 0

    @property
    def entries(self) -> list[dict]:
        return self.core.templates(self.kind)

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="manage-scroll"):
            yield Static(tr(f"manage_{self.kind}s"), classes="screen-title")
            with Horizontal(classes="manage-buttons"):
                yield Button(tr("btn_add"), variant="success", id="btn-manage-add")
                yield Button(tr("btn_delete"), variant="error", id="btn-manage-delete")
            yield Static("", id="manage-count", classes="muted")
            yield Vertical(id="manage-entries")
        yield Static(tr("hint_nav"), id="footer-hint")

    async def on_screen_resume(self) -> None:
        await self.rebuild()

    async def rebuild(self) -> None:
        container = self.query_one("#manage-entries", Vertical)
        await container.remove_children()
        entries = self.entries
        self.query_one("#manage-count", Static).update(
            tr("entries_count").format(n=len(entries)))
        self.selected = max(0, min(self.selected, len(entries) - 1))
        for i, entry in enumerate(entries):
            item = ManageEntryItem(self._entry_label(entry), i)
            item.set_class(i == self.selected, "selected")
            await container.mount(item)

    def _entry_label(self, entry: dict) -> str:
        if self.kind == "payee":
            parts = [entry.get("description", ""), entry.get("payee_name", "")]
        else:
            parts = [entry.get("payer_name", "")]
        return " · ".join(p for p in parts if p.strip()) or "–"

    def select_entry(self, index: int) -> None:
        self.selected = index
        for i, item in enumerate(self.query(ManageEntryItem)):
            item.set_class(i == self.selected, "selected")
            if i == self.selected:
                item.scroll_visible()

    def action_nav_up(self) -> None:
        self._move(-1)

    def action_nav_down(self) -> None:
        self._move(1)

    def _move(self, delta: int) -> None:
        if self.entries:
            self.select_entry(max(0, min(len(self.entries) - 1, self.selected + delta)))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-manage-add":
            self.app.push_screen(TEMPLATE_FORMS[self.kind]())
        elif event.button.id == "btn-manage-delete":
            self.action_delete_entry()

    def action_delete_entry(self) -> None:
        if not 0 <= self.selected < len(self.entries):
            return

        async def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self.entries.pop(self.selected)
                self.core.save_templates(self.kind)
                self.notify(tr("entry_deleted"))
                await self.rebuild()

        self.app.push_screen(ConfirmDeleteModal(tr("confirm_delete_entry")), on_confirm)


class ManageEntryItem(Static):
    def __init__(self, label: str, index: int):
        super().__init__(f" {label}", classes="manage-entry", markup=False)
        self.entry_index = index

    def on_click(self) -> None:
        if isinstance(self.screen, ManageListScreen):
            self.screen.select_entry(self.entry_index)


class TemplateField(NamedTuple):
    key: str
    label_key: str
    options: list[str] | None = None     # a dropdown when set, otherwise a text input
    placeholder: str = ""


class TemplateFormScreen(BackScreen):
    """Adding a template. Subclasses list the fields; the name field is required."""

    kind = ""
    title_key = ""
    name_field = ""
    name_label_key = ""
    fields: list[TemplateField] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="newbill-scroll"):
            yield Static(tr(self.title_key), classes="screen-title")
            with Grid(classes="form-grid"):
                for field in self.fields:
                    yield Vertical(Label(tr(field.label_key)), self._control(field),
                                   classes="form-cell")
            with Horizontal(classes="newbill-buttons"):
                yield Button(tr("btn_save"), variant="success", id="btn-template-save")
                yield Button(tr("btn_cancel"), id="btn-template-cancel")
        yield Static(tr("hint_nav"), id="footer-hint")

    @staticmethod
    def _control(field: TemplateField) -> Input | Select:
        if field.options is not None:
            return Select([(o, o) for o in field.options], allow_blank=True, prompt="–",
                          id=f"template-{field.key}")
        return Input(id=f"template-{field.key}", placeholder=field.placeholder)

    def _value(self, field: TemplateField) -> str:
        control = self.query_one(f"#template-{field.key}")
        return select_text(control) if isinstance(control, Select) else control.value.strip()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-template-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-template-save":
            self._save()

    def _save(self) -> None:
        entry = {field.key: self._value(field) for field in self.fields}
        if not entry[self.name_field]:
            self.notify(tr("msg_missing_required").format(fields=tr(self.name_label_key)),
                        severity="error")
            return
        if entry.get("amount"):
            try:
                entry["amount"] = f"{parse_amount(entry['amount']):.2f}"
            except ValueError:
                self.notify(tr("msg_invalid_amount"), severity="error")
                return
        self.core.templates(self.kind).append(entry)
        self.core.save_templates(self.kind)
        self.notify(tr("entry_added"))
        self.app.pop_screen()


class AddPayeeTemplateScreen(TemplateFormScreen):
    kind = "payee"
    title_key = "add_payee_title"
    name_field = "payee_name"
    name_label_key = "f_payee_name"
    fields = [
        TemplateField("description", "f_description"),
        TemplateField("amount", "f_amount", placeholder="0.00"),
        TemplateField("currency", "f_currency", CURRENCIES),
        TemplateField("account", "f_account_iban", placeholder="CH12 1234 1234 1234 1234 4"),
        TemplateField("payee_name", "f_payee_name"),
        TemplateField("payee_street", "f_street"),
        TemplateField("payee_building_nr", "f_building_nr"),
        TemplateField("payee_postal_code", "f_postal_code"),
        TemplateField("payee_city", "f_city"),
        TemplateField("payee_country", "f_country", COUNTRIES),
    ]


class AddPayerTemplateScreen(TemplateFormScreen):
    kind = "payer"
    title_key = "add_payer_title"
    name_field = "payer_name"
    name_label_key = "f_payer_name"
    fields = [
        TemplateField("payer_name", "f_payer_name"),
        TemplateField("payer_street", "f_street"),
        TemplateField("payer_building_nr", "f_building_nr"),
        TemplateField("payer_postal_code", "f_postal_code"),
        TemplateField("payer_city", "f_city"),
        TemplateField("payer_country", "f_country", COUNTRIES),
    ]


TEMPLATE_FORMS = {"payee": AddPayeeTemplateScreen, "payer": AddPayerTemplateScreen}
