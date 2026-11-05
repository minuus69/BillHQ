"""The main menu."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Middle, Vertical
from textual.screen import Screen
from textual.widgets import Header, ListView, Static

from appdata.languages import tr
from ui.screens.bills import BillsScreen
from ui.screens.menus import MenuItem
from ui.screens.new_bill import NewBillScreen
from ui.screens.scan import ScanBillScreen
from ui.screens.settings import SettingsScreen
from ui.screens.summary import SummaryScreen
from ui.screens.templates import ManageScreen


class MainMenuScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle(id="menu-wrap"):
            with Vertical(id="menu-panel"):
                yield Static(tr("app_title"), id="menu-title")
                yield ListView(
                    MenuItem(tr("menu_all_bills"), "all"),
                    MenuItem(tr("menu_new_bill"), "new"),
                    MenuItem(tr("menu_scan_bill"), "scan"),
                    MenuItem(tr("menu_summary"), "summary"),
                    MenuItem(tr("menu_manage"), "manage"),
                    MenuItem(tr("menu_settings"), "settings"),
                    id="menu-list",
                )
        yield Static(f"{tr('hint_menu')}  ·  {tr('hint_nav')}", id="footer-hint")

    def on_mount(self) -> None:
        self.query_one("#menu-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = getattr(event.item, "menu_key", None)
        screens = {"all": BillsScreen, "new": NewBillScreen, "scan": ScanBillScreen,
                   "summary": SummaryScreen, "manage": ManageScreen, "settings": SettingsScreen}
        cls = screens.get(key)
        if cls is not None:
            self.app.push_screen(cls())

    def action_back(self) -> None:
        self.app.core.logger.info("app closed by user")
        self.app.exit()
