"""Application state: settings, bills, templates, logger and saving."""
from __future__ import annotations

from pathlib import Path

from appdata.csvparser import (
    PAYER_TEMPLATE_COLUMNS, RECIPIENT_TEMPLATE_COLUMNS, Bill, create_missing_files, load_bills,
    load_settings, migrate_old_files, missing_data_files, read_rows, save_bills, save_settings,
    sort_bills, write_rows,
)
from appdata.languages import set_language
from appdata.logger import Logger
from appdata.paths import private_dir, resolve_data_folder


class Core:
    """Holds settings, bills, templates, logger and persistence.

    templates_dir holds the starter CSV files, config_dir is the app's private storage.
    """

    def __init__(self, templates_dir: Path, config_dir: Path):
        self.templates_dir = templates_dir
        self.settings_path = private_dir(config_dir) / "settings.toml"

        first_run = not self.settings_path.exists()
        self.settings = load_settings(self.settings_path)
        set_language(self.settings.language)
        self.logger = Logger(config_dir / "log", self.settings.loglevel, self.settings.logsize)

        # Sorting cache: sorting is O(n log n) and only re-runs when the data
        # actually changed (version bump) or sort settings changed. This keeps
        # navigation instant even when data.csv grows large.
        self._version = 0
        self._sort_key: tuple | None = None
        self._sorted: list[Bill] = []

        self._open_data_folder(resolve_data_folder(self.settings.data_folder))
        if first_run:
            self.save_settings_file()

        self.logger.info(
            f"started: {len(self.bills)} bills, {len(self.recipient_templates)} recipient templates, "
            f"{len(self.payer_templates)} payer templates, language={self.settings.language}"
        )

    def _open_data_folder(self, folder: Path) -> None:
        """Load a folder, changing nothing in the app's state if that fails.
        Missing files count as empty, and nothing new gets created here."""
        if folder.exists() and not folder.is_dir():
            raise NotADirectoryError(f"not a folder: {folder}")
        migrate_old_files(folder)
        bills = load_bills(folder / "data.csv")
        recipients = read_rows(folder / "recipientList.csv", RECIPIENT_TEMPLATE_COLUMNS)
        payers = read_rows(folder / "payerList.csv", PAYER_TEMPLATE_COLUMNS)
        self.data_folder = folder
        self.bills = bills
        self.recipient_templates = recipients
        self.payer_templates = payers
        self._version += 1

    def reload(self) -> None:
        """Read the data folder again, so files put there by hand are picked up
        instead of being overwritten by the next save."""
        self._open_data_folder(self.data_folder)

    def missing_files(self) -> list[str]:
        return missing_data_files(self.data_folder, self.templates_dir)

    def create_missing_files(self) -> None:
        """Fill the gaps in the data folder from the templates, then load it."""
        create_missing_files(self.data_folder, self.templates_dir)
        self.logger.info(f"data files created in {self.data_folder}")
        self.reload()

    def set_data_folder(self, text: str) -> None:
        """Switch to another data folder. Empty text means the default one. The old
        folder stays as it is. Raises OSError, ValueError or csv.Error if it can't be used."""
        self._open_data_folder(resolve_data_folder(text))
        self.settings.data_folder = str(self.data_folder) if text.strip() else ""
        self.save_settings_file()
        self.logger.info(f"data folder changed: {self.data_folder}")

    def sorted_bills(self) -> list[Bill]:
        key = (self.settings.sort_by, self.settings.sort_order, self._version)
        if key != self._sort_key:
            self._sorted = sort_bills(self.bills, self.settings.sort_by, self.settings.sort_order)
            self._sort_key = key
        return self._sorted

    def persist(self) -> None:
        save_bills(self.data_folder / "data.csv", self.bills)
        self._version += 1
        self.logger.info(f"data.csv saved ({len(self.bills)} bills)")

    def templates(self, kind: str) -> list[dict]:
        return self.recipient_templates if kind == "recipient" else self.payer_templates

    def save_templates(self, kind: str) -> None:
        name, fields = (("recipientList.csv", RECIPIENT_TEMPLATE_COLUMNS) if kind == "recipient"
                        else ("payerList.csv", PAYER_TEMPLATE_COLUMNS))
        self.data_folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_rows(self.data_folder / name, fields, self.templates(kind))
        self.logger.info(f"{kind} templates saved ({len(self.templates(kind))} entries)")

    def save_settings_file(self) -> None:
        save_settings(self.settings_path, self.settings)
