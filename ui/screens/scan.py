"""Reading a bill from a QR image, PDF or webcam."""
from __future__ import annotations

from typing import Callable

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.widgets import Static

from appdata import qr
from appdata.csvparser import DATA_FIELDS, Bill
from appdata.languages import tr
from ui.screens.base import BillFormScreen, MenuItem, MenuScreen


class ScanBillScreen(MenuScreen):
    def menu_title(self) -> str:
        return tr("scan_bill_title")

    def menu_items(self) -> list[MenuItem]:
        return [MenuItem(tr("btn_load_qr"), "load"), MenuItem(tr("btn_scan_qr"), "scan")]

    def compose_below_menu(self) -> ComposeResult:
        yield Static("", id="scan-status")

    def menu_selected(self, key: str) -> None:
        self.query_one("#scan-status", Static).update(f"[dim]{tr('scan_processing')}[/dim]")
        self._read_bill(self._read_file if key == "load" else qr.scan_qr_webcam)

    @staticmethod
    def _read_file() -> dict | None:
        path = qr.open_file_dialog()
        return qr.parse_qr_from_file(path) if path else None

    @work(thread=True, exclusive=True)
    def _read_bill(self, read: Callable[[], dict | None]) -> None:
        try:
            data = read()
        except ValueError:
            self.app.call_from_thread(self._fail, tr("scan_no_qr"))
        except Exception as exc:
            self.app.call_from_thread(self._fail, str(exc))
        else:
            if data is None:                       # cancelled
                self.app.call_from_thread(self._clear_status)
            else:
                self.app.call_from_thread(self._open_form, data)

    def _open_form(self, data: dict) -> None:
        self.app.push_screen(ScanEditScreen(Bill(**{f: data.get(f, "") for f in DATA_FIELDS})))

    def _fail(self, msg: str) -> None:
        self.query_one("#scan-status", Static).update(Text(msg, style="red"))
        self.notify(msg, severity="error", markup=False)

    def _clear_status(self) -> None:
        self.query_one("#scan-status", Static).update("")


class ScanEditScreen(BillFormScreen):
    title_key = "scan_bill_title"

    def __init__(self, bill: Bill):
        super().__init__()
        self.bill = bill

    def initial_bill(self) -> Bill:
        return self.bill

    def apply(self, bill: Bill) -> None:
        self.core.bills.append(bill)

    def leave(self) -> None:
        self.app.pop_screen()          # this screen
        self.app.pop_screen()          # the scan menu
