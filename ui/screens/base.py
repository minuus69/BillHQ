"""Base classes for screens: going back, menus and the bill form."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Middle, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Header, Label, ListItem, ListView, Static

from appdata.core import Core
from appdata.csvparser import Bill
from appdata.languages import tr
from ui.bill_form import BillEditForm


class BackScreen(Screen):
    """A screen you leave with Esc."""

    BINDINGS = [Binding("escape", "back", "Back")]

    @property
    def core(self) -> Core:
        return self.app.core

    def action_back(self) -> None:
        self.app.pop_screen()


class MenuItem(ListItem):
    def __init__(self, label: str, menu_key: str):
        super().__init__(Label(label))
        self.menu_key = menu_key


class MenuScreen(BackScreen):
    """A centered list of choices. Subclasses say what's in it and what each does."""

    def menu_title(self) -> str:
        raise NotImplementedError

    def menu_items(self) -> list[MenuItem]:
        raise NotImplementedError

    def menu_selected(self, key: str) -> None:
        raise NotImplementedError

    def hint(self) -> str:
        return tr("hint_nav")

    def compose_below_menu(self) -> ComposeResult:
        return ()

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle(id="menu-wrap"):
            with Vertical(id="menu-panel"):
                yield Static(self.menu_title(), id="menu-title")
                yield ListView(*self.menu_items(), id="menu-list")
                yield from self.compose_below_menu()
        yield Static(self.hint(), id="footer-hint")

    def on_mount(self) -> None:
        self.query_one("#menu-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.menu_selected(event.item.menu_key)


class BillFormScreen(BackScreen):
    """The bill form with save and cancel. Subclasses say which bill and what saving does."""

    title_key = ""

    def initial_bill(self) -> Bill:
        raise NotImplementedError

    def apply(self, bill: Bill) -> None:
        """Put the validated bill into the app's data."""
        raise NotImplementedError

    def leave(self) -> None:
        """Where to go after saving."""
        self.app.pop_screen()

    def compose_above_form(self) -> ComposeResult:
        return ()

    def compose(self) -> ComposeResult:
        self.form = BillEditForm(self.initial_bill(), self.core.settings)
        yield Header()
        with VerticalScroll(id="newbill-scroll"):
            yield Static(tr(self.title_key), classes="screen-title")
            yield from self.compose_above_form()
            yield self.form
            with Horizontal(classes="newbill-buttons"):
                yield Button(tr("btn_save"), variant="success", id="btn-form-save")
                yield Button(tr("btn_cancel"), id="btn-form-cancel")
        yield Static(tr("hint_nav"), id="footer-hint")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-form-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-form-save":
            bill, error = self.form.collect()
            if error:
                self.core.logger.warning(f"bill rejected: {error}")
                self.notify(error, severity="error", timeout=10)
                return
            self.apply(bill)
            self.core.persist()
            self.core.logger.info(f"bill saved: {bill.description!r}")
            self.notify(tr("msg_bill_saved"))
            self.leave()
