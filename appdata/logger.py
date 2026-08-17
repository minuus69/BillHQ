"""File logger writing '[YYYY-mm-dd HH:MM:SS] [LEVEL] message' lines to appdata/log.

Level and maximum line count come from settings and can be changed at runtime
(settings screen). The file is trimmed to the configured line count.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}


class Logger:
    def __init__(self, path: Path | str, level: str = "info", max_lines: int = 2048):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._writes = 0
        self.level_name = "INFO"
        self._threshold = LEVELS["INFO"]
        self.max_lines = 2048
        self.set_level(level)
        self.set_max_lines(max_lines)

    def set_level(self, level) -> None:
        name = str(level).strip().upper()
        if name not in LEVELS:
            name = "INFO"
        self.level_name = name
        self._threshold = LEVELS[name]

    def set_max_lines(self, max_lines) -> None:
        try:
            self.max_lines = max(100, int(max_lines))
        except (TypeError, ValueError):
            pass

    def _emit(self, level: str, message: str) -> None:
        if LEVELS[level] < self._threshold:
            return
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] [{level}] {message}"
        with self._lock:
            try:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                self._writes += 1
                if self._writes % 50 == 0:      # trim only every 50 writes (cheap)
                    self._trim()
            except OSError:
                pass                            # logging must never crash the app

    def _trim(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            if len(lines) > self.max_lines:
                with open(self.path, "w", encoding="utf-8") as fh:
                    fh.writelines(lines[-self.max_lines:])
        except OSError:
            pass

    def debug(self, msg: str) -> None:
        self._emit("DEBUG", msg)

    def info(self, msg: str) -> None:
        self._emit("INFO", msg)

    def warning(self, msg: str) -> None:
        self._emit("WARNING", msg)

    def error(self, msg: str) -> None:
        self._emit("ERROR", msg)
