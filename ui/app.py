"""The Textual application."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from appdata import paths
from appdata.core import Core
from appdata.languages import tr
from ui.screens.main_menu import MainMenuScreen
from ui.screens.splash import SplashScreen

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"


class BillApp(App):
    CSS_PATH = "styles.tcss"
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.core = Core(TEMPLATES_DIR, paths.config_dir())

    def on_mount(self) -> None:
        self.title = tr("app_title")
        self.push_screen(MainMenuScreen())
        self.push_screen(SplashScreen())

    def action_quit(self) -> None:
        self.core.logger.info("quit (ctrl+q)")
        self.exit()

    async def rebuild_ui(self) -> None:
        """Pop everything and rebuild the UI so all texts refresh after a language change."""
        self.title = tr("app_title")
        # Safely pop screens until we are back at the MainMenuScreen
        while self.screen_stack and not isinstance(self.screen, MainMenuScreen):
            self.pop_screen()
        # Switch to a fresh MainMenuScreen to apply new language translations
        await self.switch_screen(MainMenuScreen())


def main() -> None:
    try:
        app = BillApp()
    except (OSError, ValueError, csv.Error) as exc:
        settings = paths.config_dir() / "settings.toml"
        sys.exit(f"BillHQ can't open its data folder: {exc}\n"
                 f"You can change data_folder in {settings}")
    app.run()
