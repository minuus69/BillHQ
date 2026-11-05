"""The Textual application."""
from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding

from appdata.core import Core
from appdata.languages import tr
from ui.screens.main_menu import MainMenuScreen
from ui.screens.splash import SplashScreen

BASE_DIR = Path(__file__).resolve().parent.parent


class BillApp(App):
    CSS_PATH = "styles.tcss"
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.core = Core(BASE_DIR)

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
    BillApp().run()
