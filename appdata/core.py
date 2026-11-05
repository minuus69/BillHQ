"""Application state: settings, bills, templates, logger and saving."""
from __future__ import annotations

from pathlib import Path

from appdata.csvparser import (
    PAYER_TEMPLATE_COLUMNS, RECIPIENT_TEMPLATE_COLUMNS, Bill, bootstrap_files, load_bills, load_settings,
    read_rows, save_bills, save_settings, sort_bills, write_rows,
)
from appdata.languages import set_language
from appdata.logger import Logger


class Core:
    """Holds settings, bills, templates, logger and persistence."""

    def __init__(self, base_dir: Path):
        self.appdata = base_dir / "appdata"
        self.userdata = base_dir / "userdata"
        bootstrap_files(self.userdata, self.appdata)

        self.settings = load_settings(self.userdata / "settings.toml")
        set_language(self.settings.language)
        self.logger = Logger(self.appdata / "log", self.settings.loglevel, self.settings.logsize)

        self.bills = load_bills(self.userdata / "data.csv")
        self.recipient_templates = read_rows(self.userdata / "recipientList.csv", RECIPIENT_TEMPLATE_COLUMNS)
        self.payer_templates = read_rows(self.userdata / "payerList.csv", PAYER_TEMPLATE_COLUMNS)

        # Sorting cache: sorting is O(n log n) and only re-runs when the data
        # actually changed (version bump) or sort settings changed. This keeps
        # navigation instant even when data.csv grows large.
        self._version = 0
        self._sort_key: tuple | None = None
        self._sorted: list[Bill] = []

        self.logger.info(
            f"started: {len(self.bills)} bills, {len(self.recipient_templates)} recipient templates, "
            f"{len(self.payer_templates)} payer templates, language={self.settings.language}"
        )

    def sorted_bills(self) -> list[Bill]:
        key = (self.settings.sort_by, self.settings.sort_order, self._version)
        if key != self._sort_key:
            self._sorted = sort_bills(self.bills, self.settings.sort_by, self.settings.sort_order)
            self._sort_key = key
        return self._sorted

    def persist(self) -> None:
        save_bills(self.userdata / "data.csv", self.bills)
        self._version += 1
        self.logger.info(f"data.csv saved ({len(self.bills)} bills)")

    def templates(self, kind: str) -> list[dict]:
        return self.recipient_templates if kind == "recipient" else self.payer_templates

    def save_templates(self, kind: str) -> None:
        name, fields = (("recipientList.csv", RECIPIENT_TEMPLATE_COLUMNS) if kind == "recipient"
                        else ("payerList.csv", PAYER_TEMPLATE_COLUMNS))
        write_rows(self.userdata / name, fields, self.templates(kind))
        self.logger.info(f"{kind} templates saved ({len(self.templates(kind))} entries)")

    def save_settings_file(self) -> None:
        save_settings(self.userdata / "settings.toml", self.settings)
