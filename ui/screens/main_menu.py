"""The main menu."""
from __future__ import annotations

from appdata.languages import tr
from ui.screens.base import MenuItem, MenuScreen
from ui.screens.bills import BillsScreen
from ui.screens.new_bill import NewBillScreen
from ui.screens.scan import ScanBillScreen
from ui.screens.settings import SettingsScreen
from ui.screens.summary import SummaryScreen
from ui.screens.templates import ManageScreen

SCREENS = {
    "all": BillsScreen, "new": NewBillScreen, "scan": ScanBillScreen,
    "summary": SummaryScreen, "manage": ManageScreen, "settings": SettingsScreen,
}


class MainMenuScreen(MenuScreen):
    def menu_title(self) -> str:
        return tr("app_title")

    def menu_items(self) -> list[MenuItem]:
        return [
            MenuItem(tr("menu_all_bills"), "all"),
            MenuItem(tr("menu_new_bill"), "new"),
            MenuItem(tr("menu_scan_bill"), "scan"),
            MenuItem(tr("menu_summary"), "summary"),
            MenuItem(tr("menu_manage"), "manage"),
            MenuItem(tr("menu_settings"), "settings"),
        ]

    def hint(self) -> str:
        return f"{tr('hint_menu')}  ·  {tr('hint_nav')}"

    def menu_selected(self, key: str) -> None:
        self.app.push_screen(SCREENS[key]())

    def action_back(self) -> None:
        self.core.logger.info("app closed by user")
        self.app.exit()
