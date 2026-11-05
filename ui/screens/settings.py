"""The settings screen."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Header, Input, Select, Static

from appdata.csvparser import COUNTRIES, CURRENCIES, DATE_FORMATS
from appdata.languages import LANG_CODES, LANG_NAMES, set_language, tr
from ui.screens.base import BackScreen


class SettingsScreen(BackScreen):
    def compose(self) -> ComposeResult:
        s = self.core.settings
        yield Header()
        with VerticalScroll(id="settings-scroll"):
            yield Static(tr("menu_settings"), classes="screen-title")
            with Vertical(id="settings-panel"):
                yield self._row(tr("set_language"), Select(
                    [(f"{LANG_NAMES.get(c, c)} ({c})", c) for c in LANG_CODES],
                    value=s.language, id="set-language"))
                yield self._row(tr("set_date_format"), Select(
                    [(f, f) for f in DATE_FORMATS], value=s.date_format, id="set-date-format"))
                yield self._row(tr("set_currency"), Select(
                    [(c, c) for c in CURRENCIES],
                    value=s.default_currency,
                    id="set-currency"))
                yield self._row(tr("set_country"), Select(
                    [(c, c) for c in COUNTRIES],
                    value=s.default_country,
                    id="set-country"))
                yield self._row(tr("set_sort_by"), Select(
                    [(tr("sort_due_date"), "dueDate"), (tr("sort_paid_date"), "paidDate"),
                     (tr("sort_description"), "description")],
                    value=s.sort_by, id="set-sort-by"))
                yield self._row(tr("set_sort_order"), Select(
                    [(tr("sort_asc"), "asc"), (tr("sort_desc"), "desc")],
                    value=s.sort_order, id="set-sort-order"))
                yield self._row(tr("set_loglevel"), Select(
                    [("DEBUG", "debug"), ("INFO", "info"), ("ERROR", "error")],
                    value=s.loglevel.lower(), id="set-loglevel"))
                yield self._row(tr("set_logsize"), Input(value=str(s.logsize), id="set-logsize"))
        yield Static(tr("hint_nav"), id="footer-hint")

    @staticmethod
    def _row(label: str, control: Widget) -> Horizontal:
        return Horizontal(Static(label, classes="set-label"), control, classes="set-row")

    async def on_select_changed(self, event: Select.Changed) -> None:
        mapping = {
            "set-language": "language",
            "set-date-format": "date_format",
            "set-currency": "default_currency",
            "set-country": "default_country",
            "set-sort-by": "sort_by",
            "set-sort-order": "sort_order",
            "set-loglevel": "loglevel",
        }
        key = mapping.get(event.select.id or "")
        if key is None or not isinstance(event.value, str):
            return

        core = self.core

        if getattr(core.settings, key) == event.value:   # fired while mounting
            return

        setattr(core.settings, key, event.value)
        core.save_settings_file()
        core.logger.info(f"settings: {key} = {event.value}")
        if key == "loglevel":
            core.logger.set_level(event.value)
        self.notify(tr("msg_settings_saved"))
        if key == "language":
            set_language(event.value)
            await self.app.rebuild_ui()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "set-logsize":
            return
        try:
            n = max(100, int(event.value.strip()))
        except ValueError:
            self.notify(f"{tr('set_logsize')}: 100 … 1000000", severity="error")
            return
        core = self.core
        core.settings.logsize = n
        core.save_settings_file()
        core.logger.set_max_lines(n)
        core.logger.info(f"settings: logsize = {n}")
        self.notify(tr("msg_settings_saved"))
