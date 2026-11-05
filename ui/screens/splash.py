"""The splash screen shown at startup."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from appdata.languages import tr


class SplashScreen(ModalScreen):
    FOX_FRAMES = [
        "",
        "  /\\_/\\",
        "  /\\_/\\\n ( . . )",
        "  /\\_/\\\n ( o.o )\n  > ^ <",
        "  /\\_/\\\n ( o.o )\n  > ^ <\n /|   |\\\n (_|   |_)",
        "  /\\_/\\\n ( o.o )\n  > ^ <\n /|   |\\\n (_|   |_)",
        "  /\\_/\\\n ( -.o )\n  > ^ <\n /|   |\\\n (_|   |_)",
        "  /\\_/\\\n ( o.o )\n  > ^ <\n /|   |\\\n (_|   |_)",
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-box"):
            yield Static(" ", id="splash-fox")
            yield Static(" ", id="splash-title")
            yield Static(" ", id="splash-tagline")

    def on_mount(self) -> None:
        self._title = tr("splash_title")
        self._tagline = tr("splash_tagline")
        self._step = 0
        self._fox_len = len(self.FOX_FRAMES)
        self._title_len = len(self._title)
        self._total = self._fox_len + self._title_len + 12
        self.set_interval(0.10, self._tick)

    def _tick(self) -> None:
        self._step += 1
        s = self._step

        try:
            fox = self.query_one("#splash-fox", Static)
            title = self.query_one("#splash-title", Static)
            tagline = self.query_one("#splash-tagline", Static)
        except Exception:
            return

        if s <= self._fox_len:
            fox.update(self.FOX_FRAMES[s - 1] or " ")

        elif s <= self._fox_len + self._title_len:
            chars = s - self._fox_len
            shown = self._title[:chars]
            cursor = "█" if chars < self._title_len else ""
            title.update(f"[bold #4f6df5]{shown}[/][dim]{cursor}[/]")

        elif s == self._fox_len + self._title_len + 2:
            title.update(f"[bold #4f6df5]{self._title}[/]")
            tagline.update(f"[dim italic]{self._tagline}[/]")

        elif s >= self._total:
            self.dismiss()
