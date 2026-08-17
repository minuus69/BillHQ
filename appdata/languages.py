"""Dynamic i18n. All UI strings are fetched with tr(key) at render time.

Translations live in languages.csv: first column = key, each further column =
one language code. To add a language, just add a column (empty cells fall back
to English, then to the key itself). Currently implemented: en, de.
"""
from __future__ import annotations

import csv
from pathlib import Path

CSV_PATH = Path(__file__).with_name("languages.csv")

# order shown in menus/settings; add new codes here + in languages.csv
LANG_CODES = ["en", "de", "ch", "it", "fr", "rm", "sr", "ru", "jp", "cn", "fn"]
LANG_NAMES = {
    "en": "English", "de": "Deutsch", "ch": "Schwiizerdütsch", "it": "Italiano",
    "fr": "Français", "rm": "Rumantsch", "sr": "Српски", "ru": "Русский",
    "jp": "日本語", "cn": "中文", "fn": "Fortnite",
}
_FALLBACK = "en"


class Translator:
    def __init__(self) -> None:
        self._table: dict[str, dict[str, str]] = {}
        self._code = _FALLBACK
        self.reload()

    def reload(self) -> None:
        self._table = {}
        try:
            with open(CSV_PATH, newline="", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                header = next(reader, [])
                langs = [h.strip() for h in header[1:]]
                for row in reader:
                    if not row or not row[0].strip():
                        continue
                    self._table[row[0].strip()] = {
                        langs[i]: (row[i + 1] if i + 1 < len(row) else "")
                        for i in range(len(langs))
                    }
        except OSError:
            self._table = {}

    def set_language(self, code: str) -> None:
        self._code = code or _FALLBACK

    def t(self, key: str) -> str:
        row = self._table.get(key)
        if not row:
            return key
        for code in (self._code, _FALLBACK):
            value = (row.get(code) or "").strip()
            if value:
                return value
        return key


_TRANSLATOR = Translator()


def tr(key: str) -> str:
    return _TRANSLATOR.t(key)


def set_language(code: str) -> None:
    _TRANSLATOR.set_language(code)
