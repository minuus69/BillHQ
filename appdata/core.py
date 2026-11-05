"""Application state: settings, bills, templates, logger and saving."""
from __future__ import annotations

from pathlib import Path

from appdata.csvparser import (
    CREDITOR_FIELDS, DEBITOR_FIELDS, Bill, bootstrap_files, load_bills, load_settings,
    read_rows, save_bills, save_settings, sort_bills,
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
        self.debitors = read_rows(self.userdata / "debitorList.csv", DEBITOR_FIELDS)
        self.creditors = read_rows(self.userdata / "creditorList.csv", CREDITOR_FIELDS)

        # Sorting cache: sorting is O(n log n) and only re-runs when the data
        # actually changed (version bump) or sort settings changed. This keeps
        # navigation instant even when data.csv grows large.
        self._version = 0
        self._sort_key: tuple | None = None
        self._sorted: list[Bill] = []

        self.logger.info(
            f"started: {len(self.bills)} bills, {len(self.debitors)} debitor templates, "
            f"{len(self.creditors)} creditor templates, language={self.settings.language}"
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

    def save_settings_file(self) -> None:
        save_settings(self.userdata / "settings.toml", self.settings)
