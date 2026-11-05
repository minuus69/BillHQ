"""The main menu."""
from __future__ import annotations

import csv

from textual.app import ComposeResult
from textual.widgets import Header, Static

from appdata.languages import tr
from appdata.version import VERSION
from ui.dialogs import ConfirmModal
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

# Opening these needs the data files, so they ask to create any that are missing.
BILL_SCREENS = {"all", "new", "scan"}


class VersionHeader(Header):
    """The top bar with the app version on the right."""

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Static(f"v{VERSION}", id="header-version")


class MainMenuScreen(MenuScreen):
    def compose_header(self) -> Header:
        return VersionHeader()

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
        if key == "settings":                    # has to stay reachable to fix a bad folder
            self.app.push_screen(SCREENS[key]())
        elif self._try(self.core.reload):
            if key in BILL_SCREENS and self.core.missing_files():
                self._ask_to_create_files(key)
            else:
                self.app.push_screen(SCREENS[key]())

    def _ask_to_create_files(self, key: str) -> None:
        def answered(create: bool) -> None:
            if create and self._try(self.core.create_missing_files):
                self.app.push_screen(SCREENS[key]())

        message = tr("create_files_msg").format(folder=self.core.data_folder)
        self.app.push_screen(ConfirmModal(tr("create_files_title"), message), answered)

    def _try(self, step) -> bool:
        """Run a step on the data folder, showing the error if it fails."""
        try:
            step()
        except (OSError, ValueError, csv.Error) as exc:
            self.core.logger.error(f"data folder failed: {exc}")
            self.notify(tr("err_data_folder").format(err=exc), severity="error", timeout=10,
                        markup=False)
            return False
        return True

    def action_back(self) -> None:
        self.core.logger.info("app closed by user")
        self.app.exit()
