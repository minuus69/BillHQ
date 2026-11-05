"""Where BillHQ keeps things outside of the code.

- App storage (settings and log) is private to your user account, in
  ~/.config/BillHQ on Linux. It also remembers where the data folder is.
- The data folder holds your bills and templates. It can be anywhere and
  defaults to ~/Documents/BillHQ.
"""
from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_path

APP_NAME = "BillHQ"


def config_dir() -> Path:
    return user_config_path(APP_NAME, appauthor=False)


def default_data_dir() -> Path:
    return Path.home() / "Documents" / APP_NAME


def resolve_data_folder(text: str) -> Path:
    """Turn the data folder setting into a path. Empty means the default folder."""
    text = (text or "").strip()
    if not text:
        return default_data_dir()
    folder = Path(os.path.expandvars(text)).expanduser()
    if not folder.is_absolute():
        raise ValueError(f"not a full path: {text}")
    return folder


def private_dir(path: Path) -> Path:
    """Create a folder only your user account can open."""
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path
