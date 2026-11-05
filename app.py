#!/usr/bin/env python3
"""BillHQ, a terminal app for handling Swiss bills.

Navigation
----------
- mouse wheel / arrow keys : scroll & move selection
- Enter (also numpad)      : select / expand / confirm
- Esc                      : back / close dialog
- Ctrl+Q                   : quit

Structure: appdata/ = data layer (CSV, QR, i18n, logging), ui/ = screens,
userdata/ = user files.
"""
from ui.app import main

if __name__ == "__main__":
    main()
