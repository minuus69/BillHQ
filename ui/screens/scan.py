"""Reading a bill from a QR image, PDF or webcam."""
from __future__ import annotations

from uuid import uuid4

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Middle, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Header, ListView, Static

from appdata import qr
from appdata.core import Core
from appdata.csvparser import DATA_FIELDS, Bill
from appdata.languages import tr
from ui.bill_form import BillEditForm
from ui.screens.menus import MenuItem


class ScanBillScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle(id="menu-wrap"):
            with Vertical(id="menu-panel"):
                yield Static(tr("scan_bill_title"), id="menu-title")
                yield ListView(
                    MenuItem(tr("btn_load_qr"), "load"),
                    MenuItem(tr("btn_scan_qr"), "scan"),
                    id="menu-list",
                )
                yield Static("", id="scan-status")
        yield Static(tr("hint_nav"), id="footer-hint")

    def on_mount(self) -> None:
        self.query_one("#menu-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = getattr(event.item, "menu_key", None)
        status = self.query_one("#scan-status", Static)
        if key == "load":
            status.update(f"[dim]{tr('scan_processing')}[/dim]")
            self._load_qr()
        elif key == "scan":
            status.update(f"[dim]{tr('scan_processing')}[/dim]")
            self._scan_qr()

    @work(thread=True, exclusive=True)
    def _load_qr(self) -> None:
        try:
            path = qr.open_file_dialog()
            if not path:
                self.app.call_from_thread(self._clear_status)
                return
            data = qr.parse_qr_from_file(path)
            self.app.call_from_thread(self._open_form, data)
        except ValueError:
            self.app.call_from_thread(self._fail, tr("scan_no_qr"))
        except Exception as exc:
            self.app.call_from_thread(self._fail, str(exc))

    @work(thread=True, exclusive=True)
    def _scan_qr(self) -> None:
        try:
            data = qr.scan_qr_webcam()
            if data is None:
                self.app.call_from_thread(self._clear_status)
                return
            self.app.call_from_thread(self._open_form, data)
        except ValueError:
            self.app.call_from_thread(self._fail, tr("scan_no_qr"))
        except Exception as exc:
            self.app.call_from_thread(self._fail, str(exc))

    def _open_form(self, data: dict) -> None:
        bill = Bill(**{f: data.get(f, "") for f in DATA_FIELDS})
        self.app.push_screen(ScanEditScreen(bill))

    def _fail(self, msg: str) -> None:
        self.query_one("#scan-status", Static).update(Text(msg, style="red"))
        self.notify(msg, severity="error", markup=False)

    def _clear_status(self) -> None:
        self.query_one("#scan-status", Static).update("")

    def action_back(self) -> None:
        self.app.pop_screen()


class ScanEditScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, bill: Bill):
        super().__init__()
        self.bill = bill

    def compose(self) -> ComposeResult:
        core: Core = self.app.core
        self.form = BillEditForm(self.bill, core.settings, f"scan{uuid4().hex[:6]}")
        yield Header()
        with VerticalScroll(id="newbill-scroll"):
            yield Static(tr("scan_bill_title"), classes="screen-title")
            yield self.form
            with Horizontal(classes="newbill-buttons"):
                yield Button(tr("btn_save"), variant="success", id="btn-scan-save")
                yield Button(tr("btn_cancel"), id="btn-scan-cancel")
        yield Static(tr("hint_nav"), id="footer-hint")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-scan-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-scan-save":
            core: Core = self.app.core
            bill, err = self.form.collect()
            if err:
                self.notify(err, severity="error", timeout=10)
                return
            core.bills.append(bill)
            core.persist()
            core.logger.info(f"bill scanned+saved: {bill.description!r}")
            self.notify(tr("msg_bill_saved"))
            self.app.pop_screen()          # pop ScanEditScreen
            self.app.pop_screen()          # pop ScanBillScreen

    def action_back(self) -> None:
        self.app.pop_screen()
