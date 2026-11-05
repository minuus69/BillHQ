"""The bill list with expandable rows, and editing a bill."""
from __future__ import annotations

from uuid import uuid4

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Header, Input, Select, Static, TextArea

from appdata import qr
from appdata.core import Core
from appdata.csvparser import DATA_FIELDS, Bill, Settings, amount_decimal, bill_state, format_date
from appdata.languages import tr
from ui.bill_form import BillEditForm
from ui.dialogs import ConfirmDeleteModal, PayModal
from ui.helpers import detail_text, format_amount


class RowHead(Static):
    def __init__(self, row: "BillRow", settings: Settings):
        self._row = row
        super().__init__(self._build_table(row.bill, settings), classes="row-head")

    def _build_table(self, bill: Bill, settings: Settings):
        state = bill_state(bill)
        if state == "paid":
            mark = " ✓" if bill.is_checked else ""
            status = Text(f"{tr('status_paid')}{mark}", style="bold #2ecc71")
        elif state == "overdue":
            status = Text(tr("status_overdue"), style="bold #ff4d4f")
        else:
            status = Text(tr("status_open"), style="bold #f5a623")

        due = format_date(bill.dueDate, settings.date_format) or "–"
        due_style = "bold #ff4d4f" if state == "overdue" else None
        amount = f"{format_amount(amount_decimal(bill.bAmount))} {bill.bCurrency}"

        t = Table(box=None, pad_edge=False, padding=(0, 0), expand=True)
        t.add_column(width=11, no_wrap=True)
        t.add_column(width=12, no_wrap=True)
        t.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        t.add_column(width=18, justify="right", no_wrap=True)
        t.add_row(status, Text(due, style=due_style),
                  Text(bill.description or "–"), Text(amount, style="bold"))
        return t

    def on_click(self) -> None:
        self._row.screen_ref.row_clicked(self._row.index)


class BillRow(Vertical):
    def __init__(self, screen: "BillsScreen", index: int, bill: Bill, settings: Settings):
        super().__init__()
        self.screen_ref = screen
        self.index = index
        self.bill = bill
        self.settings = settings
        self._expanded = False
        self._detail_mounted = False

    def compose(self) -> ComposeResult:
        yield RowHead(self, self.settings)
        yield Vertical(classes="row-detail")

    def on_mount(self) -> None:
        self.query_one(".row-detail").display = False

    def _button(self, label: str, kind: str, variant: str) -> Button:
        btn = Button(label, variant=variant, classes=f"b-{kind}")
        btn.row = self
        btn.kind = kind
        return btn

    def expand(self) -> None:
        self._expanded = True
        self.add_class("expanded")
        self.query_one(".row-detail").display = True
        if not self._detail_mounted:
            self.run_worker(self._mount_detail(), exclusive=False)
        self.refresh()

    async def _mount_detail(self) -> None:
        detail = self.query_one(".row-detail")
        await detail.mount(
            TextArea(detail_text(self.bill, self.settings),
                     read_only=True, classes="detail-view"),
            Horizontal(
                self._button(tr("btn_show_qr"), "qr", "primary"),
                self._button(tr("btn_pay"), "pay", "success"),
                self._button(tr("btn_edit"), "edit", "warning"),
                self._button(tr("btn_delete"), "delete", "error"),
                classes="row-buttons view-buttons",
            ),
        )
        self._detail_mounted = True

    def collapse(self) -> None:
        self._expanded = False
        self.remove_class("expanded")
        self.query_one(".row-detail").display = False
        self.refresh()

    @property
    def is_expanded(self) -> bool:
        return self._expanded


class BillsScreen(Screen):
    BINDINGS = [
        Binding("up", "nav_up", "Up"),
        Binding("down", "nav_down", "Down"),
        Binding("enter", "select", "Select"),
        Binding("escape", "back", "Back"),
        Binding("delete", "delete_bill", "Delete"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[BillRow] = []
        self.selected = 0
        self._search_query = ""
        self._search_timer = None

    @property
    def core(self) -> Core:
        return self.app.core

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder=tr("bills_search_placeholder"), id="bills-search")
        yield VerticalScroll(id="bill-list")
        yield Static(tr("hint_nav"), id="footer-hint")

    async def on_mount(self) -> None:
        # Tab should land on the rows' buttons; the list itself would swallow arrow keys
        self.query_one("#bill-list", VerticalScroll).can_focus = False
        await self.rebuild()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "bills-search":
            self.app.set_focus(None)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "bills-search":
            self._search_query = event.value.strip().lower()
            self.selected = 0
            # Cancel previous timer so rapid typing only triggers ONE rebuild
            if self._search_timer is not None:
                self._search_timer.stop()
            self._search_timer = self.set_timer(0.2, self._search_debounce)

    def _search_debounce(self) -> None:
        """Called after 200ms of no typing. Safe to rebuild on main thread."""
        self.call_later(self.rebuild)

    def _get_filtered_bills(self) -> list[Bill]:
        bills = self.core.sorted_bills()
        if not self._search_query:
            return bills
        results = []
        for bill in bills:
            searchable = (
                f"{bill.description} {bill.note} {bill.dName} {bill.cName} "
                f"{bill.privateNote} {bill.bReference} {bill.bAccount}"
            ).lower()
            if self._search_query in searchable:
                results.append(bill)
                if len(results) >= 200:
                    break
        return results

    async def rebuild(self, select: int | None = None) -> None:
        box = self.query_one("#bill-list", VerticalScroll)
        await box.remove_children()
        filtered = self._get_filtered_bills()
        self.rows = [BillRow(self, i, b, self.core.settings)
                     for i, b in enumerate(filtered)]

        # Mount in batches of 50 to avoid UI freeze
        BATCH = 50
        for i in range(0, len(self.rows), BATCH):
            await box.mount(*self.rows[i:i + BATCH])

        if not self.rows:
            msg = tr("bills_empty") if not self._search_query else tr("search_no_results")
            await box.mount(Static(msg, classes="empty-hint"))

        target = self.selected if select is None else select
        self.selected = max(0, min(target, len(self.rows) - 1))
        self._highlight()

    def _highlight(self) -> None:
        for i, row in enumerate(self.rows):
            row.set_class(i == self.selected, "selected")
        if self.rows:
            self.rows[self.selected].scroll_visible()

    def _form_focused(self) -> bool:
        return isinstance(self.focused, (Input, Checkbox, Select, Button))

    def action_nav_up(self) -> None:
        self._move(-1)

    def action_nav_down(self) -> None:
        self._move(1)

    def _move(self, delta: int) -> None:
        if not self.rows:
            return
        if isinstance(self.focused, Input):       # arrow keys leave the search box
            self.app.set_focus(None)
            return
        if self._form_focused():
            return
        self.selected = max(0, min(len(self.rows) - 1, self.selected + delta))
        self._highlight()

    def action_select(self) -> None:
        if not self.rows or self._form_focused():
            return
        self.row_clicked(self.selected)

    def action_back(self) -> None:
        if isinstance(self.focused, Input):
            self.app.set_focus(None)
            return
        self.app.pop_screen()

    def action_delete_bill(self) -> None:
        if not self.rows or self._form_focused():
            return
        self._confirm_delete(self.rows[self.selected])

    def row_clicked(self, index: int) -> None:
        if not (0 <= index < len(self.rows)):
            return
        row = self.rows[index]
        if row.is_expanded:
            row.collapse()
        else:
            for other in self.rows:
                if other is not row:
                    other.collapse()
            row.expand()
            row.scroll_visible()
        self.selected = index
        self._highlight()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        row: BillRow | None = getattr(event.button, "row", None)
        kind: str | None = getattr(event.button, "kind", None)
        if row is None or kind is None:
            return
        if kind == "qr":
            self._show_qr(row)
        elif kind == "pay":
            self._pay(row)
        elif kind == "edit":
            self._edit(row)
        elif kind == "delete":
            self._confirm_delete(row)
        self.app.set_focus(None)

    def _show_qr(self, row: BillRow) -> None:
        try:
            png = qr.generate_qr_bill(row.bill, self.core.settings, self.core.userdata)
            self.core.logger.info(f"QR bill generated -> {png}")
            self.notify(tr("msg_qr_created"))
        except Exception as exc:
            self.core.logger.error(f"QR generation failed: {exc}")
            self.notify(tr("err_qr_failed").format(err=exc), severity="error", timeout=10,
                        markup=False)

    def _pay(self, row: BillRow) -> None:
        async def confirm(result: dict) -> None:
            row.bill.paidDate = result["paidDate"]
            row.bill.paidWith = result["paidWith"]
            row.bill.paidChecked = result["paidChecked"]
            self.core.persist()
            self.core.logger.info(
                f"bill paid: {row.bill.description!r} on {result['paidDate']}")
            self.notify(tr("msg_paid"))
            await self.rebuild()
        self.app.push_screen(PayModal(row.bill, self.core.settings, confirm))

    def _edit(self, row: BillRow) -> None:
        try:
            real_index = self.core.bills.index(row.bill)
        except ValueError:
            real_index = row.index
        self.app.push_screen(EditBillScreen(row.bill, real_index))

    def _confirm_delete(self, row: BillRow) -> None:
        async def on_confirm(result: bool) -> None:
            if result:
                try:
                    self.core.bills.remove(row.bill)
                except ValueError:
                    pass
                self.core.persist()
                self.core.logger.info(f"bill deleted: {row.bill.description!r}")
                self.notify(tr("msg_deleted"))
                await self.rebuild()
        self.app.push_screen(ConfirmDeleteModal(), on_confirm)

    async def on_screen_resume(self) -> None:
        await self.rebuild()


class EditBillScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, bill: Bill, index: int):
        super().__init__()
        self.bill = bill
        self.bill_index = index

    def compose(self) -> ComposeResult:
        core: Core = self.app.core
        self.form = BillEditForm(self.bill, core.settings, f"edit{uuid4().hex[:6]}")
        yield Header()
        with VerticalScroll(id="newbill-scroll"):
            yield Static(tr("edit_bill_title"), classes="screen-title")
            yield self.form
            with Horizontal(classes="newbill-buttons"):
                yield Button(tr("btn_save"), variant="success", id="btn-edit-save")
                yield Button(tr("btn_cancel"), id="btn-edit-cancel")
        yield Static(tr("hint_nav"), id="footer-hint")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-edit-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-edit-save":
            core: Core = self.app.core
            bill, err = self.form.collect()
            if err:
                core.logger.warning(f"bill edit rejected: {err}")
                self.notify(err, severity="error", timeout=10)
                return
            # Update the existing bill in-place
            for f in DATA_FIELDS:
                setattr(core.bills[self.bill_index], f, getattr(bill, f))
            core.persist()
            core.logger.info(f"bill edited: {bill.description!r}")
            self.notify(tr("msg_bill_saved"))
            self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()
