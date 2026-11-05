#!/usr/bin/env python3
"""BillHQ, a terminal app for handling Swiss bills.

Navigation
----------
- mouse wheel / arrow keys : scroll & move selection
- Enter (also numpad)      : select / expand / confirm
- Esc                      : back / close dialog
- Ctrl+Q                   : quit

Structure: appdata/ = data layer (CSV, QR, i18n, logging), ui/ = screens,
templates/ = starter files for a new data folder.
"""
import sys


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["--version"]:
        from appdata.version import VERSION
        print(f"BillHQ v{VERSION}")
    elif args[:1] == ["--webcam-scan"]:      # how the single-file build starts its scanner
        from appdata.qr_webcam import main as scan
        scan()
    elif args[:1] == ["--self-check"]:
        from appdata.selfcheck import main as check
        check(args[1])
    else:
        from ui.app import main as run
        run()


if __name__ == "__main__":
    main()
