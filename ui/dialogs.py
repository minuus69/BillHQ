"""Modal dialogs."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static

from appdata.csvparser import Bill, Settings, format_date, parse_date, today_iso
from appdata.languages import tr


class PayModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, bill: Bill, settings: Settings, on_confirm) -> None:
        super().__init__()
        self.bill = bill
        self.settings = settings
        self.on_confirm = on_confirm          # async callback(result_dict)

    def compose(self) -> ComposeResult:
        fmt = self.settings.date_format
        with Vertical(id="pay-dialog"):
            yield Static(tr("pay_title"), classes="dlg-title")
            yield Label(tr("f_paid_date"))
            yield Input(value=format_date(today_iso(), fmt), placeholder=fmt, id="pay-date")
            yield Label(tr("f_paid_with"))
            yield Input(value=self.bill.paidWith, placeholder="ZKB / TWINT / Post …",
                        id="pay-with")
            yield Checkbox(tr("f_paid_checked"), value=self.bill.is_checked, id="pay-checked")
            with Horizontal(classes="dlg-buttons"):
                yield Button(tr("btn_ok"), variant="success", id="pay-ok")
                yield Button(tr("btn_cancel"), id="pay-cancel")

    def on_mount(self) -> None:
        self.query_one("#pay-date", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    async def _ok(self) -> None:
        date_txt = self.query_one("#pay-date", Input).value.strip()
        try:
            paid_iso = parse_date(date_txt, self.settings.date_format).isoformat()
        except ValueError:
            self.notify(tr("msg_invalid_date"), severity="error")
            return
        result = {
            "paidDate": paid_iso,
            "paidWith": self.query_one("#pay-with", Input).value.strip(),
            "paidChecked": "True" if self.query_one("#pay-checked", Checkbox).value else "False",
        }
        await self.on_confirm(result)
        self.dismiss(None)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pay-cancel":
            self.dismiss(None)
        elif event.button.id == "pay-ok":
            await self._ok()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._ok()


class ConfirmDeleteModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, message: str | None = None):
        super().__init__()
        self.message = message or tr("confirm_delete_msg")

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(tr("confirm_delete_title"), classes="dlg-title")
            yield Static(self.message, classes="dlg-msg")
            with Horizontal(classes="dlg-buttons"):
                yield Button(tr("btn_yes"), variant="error", id="confirm-yes")
                yield Button(tr("btn_no"), variant="default", id="confirm-no")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")
