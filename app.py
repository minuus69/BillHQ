#!/usr/bin/env python3
"""
Bill Manager – terminal UI for handling bills.

Navigation
----------
- mouse wheel / arrow keys : scroll & move selection
- Enter (also numpad)      : select / expand / confirm
- Esc                      : back / close dialog
- Ctrl+Q                   : quit

Structure: appdata/ = data layer (CSV, QR, i18n, logging), userdata/ = user files.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from rich.table import Table
from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Middle, Vertical, VerticalScroll, Grid
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual import work
from textual.widgets import (
    Button, Checkbox, Header, Input, Label, ListItem, ListView, Select, Static, TextArea,
)

from appdata import qr
from appdata.csvparser import (
    COUNTRIES, CURRENCIES, DATA_FIELDS, DATE_FORMATS, DEBITOR_FIELDS, CREDITOR_FIELDS,
    FIELD_LABELS, PAY_METHODS, REQUIRED_FIELDS, Bill, Settings, amount_decimal,
    bootstrap_files, bill_state, format_date, load_bills, load_settings, parse_date,
    read_rows, save_bills, save_settings, sort_bills, today_iso, write_rows,
)
from appdata.languages import LANG_CODES, LANG_NAMES, set_language, tr
from appdata.logger import Logger

BASE_DIR = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
# Core state
# --------------------------------------------------------------------------- #
class Core:
    """Holds settings, bills, templates, logger and persistence."""

    def __init__(self, base_dir: Path):
        self.appdata = base_dir / "appdata"
        self.userdata = base_dir / "userdata"
        bootstrap_files(self.userdata, self.appdata)

        self.settings = load_settings(self.userdata / "settings.toml")
        set_language(self.settings.language)
        self.logger = Logger(self.appdata / "log", self.settings.loglevel, self.settings.logsize)

        self.bills = load_bills(self.userdata / "data.csv")
        self.debitors = read_rows(self.userdata / "debitorList.csv", DEBITOR_FIELDS)
        self.creditors = read_rows(self.userdata / "creditorList.csv", CREDITOR_FIELDS)

        # Sorting cache: sorting is O(n log n) and only re-runs when the data
        # actually changed (version bump) or sort settings changed. This keeps
        # navigation instant even when data.csv grows large.
        self._version = 0
        self._sort_key: tuple | None = None
        self._sorted: list[Bill] = []

        self.logger.info(
            f"started: {len(self.bills)} bills, {len(self.debitors)} debitor templates, "
            f"{len(self.creditors)} creditor templates, language={self.settings.language}"
        )

    def sorted_bills(self) -> list[Bill]:
        key = (self.settings.sort_by, self.settings.sort_order, self._version)
        if key != self._sort_key:
            self._sorted = sort_bills(self.bills, self.settings.sort_by, self.settings.sort_order)
            self._sort_key = key
        return self._sort_key and self._sorted

    def persist(self) -> None:
        save_bills(self.userdata / "data.csv", self.bills)
        self._version += 1
        self.logger.info(f"data.csv saved ({len(self.bills)} bills)")

    def save_settings_file(self) -> None:
        save_settings(self.userdata / "settings.toml", self.settings)


def format_amount(value) -> str:
    """1234.5 -> 1'234.50"""
    return f"{value:,.2f}".replace(",", "'")

# --------------------------------------------------------------------------- #
# Rich renderables (one-line summary + expanded detail)
# --------------------------------------------------------------------------- #
def detail_text(bill: Bill, settings: Settings) -> str:
    """Plain-text version of bill details (for selectable TextArea)."""
    fmt = settings.date_format
    W = 17  # label column width

    def row(label: str, value: str) -> str:
        return f"{label:<{W}} {value or '–'}"

    lines = [
        row(tr("f_description"), bill.description),
        row(tr("f_due_date"), format_date(bill.dueDate, fmt)),
        row(tr("f_amount"), f"{format_amount(amount_decimal(bill.bAmount))} {bill.bCurrency}"),
        "",
        f"── {tr('payment_section')} ──",
        row(tr("f_paid_date"), format_date(bill.paidDate, fmt)),
        row(tr("f_paid_with"), bill.paidWith),
        row(tr("f_paid_checked"), "✓" if bill.is_checked else "–"),
        row(tr("f_account"), bill.bAccount),
        row(tr("f_reference"), bill.bReference),
        row(tr("f_note"), bill.note),
        "",
        f"── {tr('debtor_section')} ──",
        row(tr("f_dname"), bill.dName),
        row(tr("f_street"), (bill.dStreet + " " + bill.dBuildingNr).strip()),
        row(tr("f_city"), (bill.dPostalCode + " " + bill.dCity).strip()),
        row(tr("f_country"), bill.dCountry),
        "",
        f"── {tr('creditor_section')} ──",
        row(tr("f_cname"), bill.cName),
        row(tr("f_street"), (bill.cStreet + " " + bill.cBuildingNr).strip()),
        row(tr("f_city"), (bill.cPostalCode + " " + bill.cCity).strip()),
        row(tr("f_country"), bill.cCountry),
        "",
        row(tr("f_private_note"), bill.privateNote),
    ]
    return "\n".join(lines)

def detail_table(bill: Bill, settings: Settings) -> Table:
    t = Table(box=None, pad_edge=False, padding=(0, 1))
    t.add_column(width=24, style="bold #7aa2f7", no_wrap=True)
    t.add_column(ratio=1)

    def add(label_key: str, value: str) -> None:
        t.add_row(tr(label_key), value.strip() if value and value.strip() else "–")

    def section(label_key: str) -> None:
        t.add_row(Text(tr(label_key), style="bold underline #8ab4f8"), "")

    add("f_description", bill.description)
    add("f_due_date", format_date(bill.dueDate, settings.date_format))
    add("f_amount", f"{amount_decimal(bill.bAmount):,.2f} {bill.bCurrency}")
    section("payment_section")
    add("f_paid_date", format_date(bill.paidDate, settings.date_format))
    add("f_paid_with", bill.paidWith)
    add("f_paid_checked", "✓" if bill.is_checked else "–")
    add("f_account", bill.bAccount)
    add("f_reference", bill.bReference)
    add("f_note", bill.note)
    section("debtor_section")
    add("f_dname", bill.dName)
    add("f_street", f"{bill.dStreet} {bill.dBuildingNr}".strip())
    add("f_city", f"{bill.dPostalCode} {bill.dCity}".strip())
    add("f_country", bill.dCountry)
    section("creditor_section")
    add("f_cname", bill.cName)
    add("f_street", f"{bill.cStreet} {bill.cBuildingNr}".strip())
    add("f_city", f"{bill.cPostalCode} {bill.cCity}".strip())
    add("f_country", bill.cCountry)
    add("f_private_note", bill.privateNote)
    return t


# --------------------------------------------------------------------------- #
# Bill row (collapsible / expandable, with edit form)
# --------------------------------------------------------------------------- #
class RowHead(Static):
    def __init__(self, row: "BillRow", settings: Settings):
        self._row = row
        super().__init__(self._build_table(row.bill, settings), classes="row-head")

    def _build_table(self, bill: Bill, settings: Settings):
        from rich.table import Table
        from rich.text import Text as RichText

        state = bill_state(bill)
        if state == "paid":
            mark = " ✓" if bill.is_checked else ""
            status = RichText(f"{tr('status_paid')}{mark}", style="bold #2ecc71")
        elif state == "overdue":
            status = RichText(tr("status_overdue"), style="bold #ff4d4f")
        else:
            status = RichText(tr("status_open"), style="bold #f5a623")

        due = format_date(bill.dueDate, settings.date_format) or "–"
        due_style = "bold #ff4d4f" if state == "overdue" else None
        amount = f"{format_amount(amount_decimal(bill.bAmount))} {bill.bCurrency}"

        t = Table(box=None, pad_edge=False, padding=(0, 0), expand=True)
        t.add_column(width=11, no_wrap=True)
        t.add_column(width=12, no_wrap=True)
        t.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        t.add_column(width=18, justify="right", no_wrap=True)
        t.add_row(status, RichText(due, style=due_style),
                  RichText(bill.description or "–"), RichText(amount, style="bold"))
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


# --------------------------------------------------------------------------- #
# Editable bill form (used by EDIT and by NEW BILL)
# --------------------------------------------------------------------------- #
class BillEditForm(Widget):
    def __init__(self, bill: Bill, settings: Settings, prefix: str):
        super().__init__()
        self.bill = bill
        self.settings = settings
        self.prefix = prefix
        self.inputs: dict[str, Input] = {}
        self._build()

    # -- construction -------------------------------------------------------
    def _inp(self, field: str, value: str, placeholder: str = "") -> Input:
        widget = Input(value=value or "", placeholder=placeholder, id=f"{self.prefix}-{field}")
        self.inputs[field] = widget
        return widget

    def _build(self) -> None:
        b, fmt = self.bill, self.settings.date_format
        self.w_description = self._inp("description", b.description)
        self.w_due = self._inp("dueDate", format_date(b.dueDate, fmt), placeholder=fmt)
        self.w_paid_date = self._inp("paidDate", format_date(b.paidDate, fmt), placeholder=fmt)
        self.w_paid_with = self._inp("paidWith", b.paidWith,
                                     placeholder="ZKB / TWINT / Post …")
        self.w_checked = Checkbox(tr("f_paid_checked"), value=b.is_checked,
                                  id=f"{self.prefix}-paidChecked")
        self.w_amount = self._inp("bAmount", b.bAmount, placeholder="0.00")

        cur_val = b.bCurrency if b.bCurrency in CURRENCIES else CURRENCIES[0]
        self.w_currency = Select([(c, c) for c in CURRENCIES],
                                 value=cur_val, allow_blank=True, prompt="–",
                                 id=f"{self.prefix}-bCurrency")

        self.w_account = self._inp("bAccount", b.bAccount,
                                   placeholder="CH12 1234 1234 1234 1234 4")
        self.w_reference = self._inp("bReference", b.bReference,
                                     placeholder="21 00000 00000 …")
        self.w_note = self._inp("note", b.note)
        self.w_dname = self._inp("dName", b.dName)
        self.w_dstreet = self._inp("dStreet", b.dStreet)
        self.w_dnr = self._inp("dBuildingNr", b.dBuildingNr)
        self.w_dpc = self._inp("dPostalCode", b.dPostalCode)
        self.w_dcity = self._inp("dCity", b.dCity)

        dc_val = b.dCountry if b.dCountry in COUNTRIES else COUNTRIES[0]
        self.w_dcountry = Select([(c, c) for c in COUNTRIES],
                                 value=dc_val, allow_blank=True, prompt="–",
                                 id=f"{self.prefix}-dCountry")

        self.w_cname = self._inp("cName", b.cName)
        self.w_cstreet = self._inp("cStreet", b.cStreet)
        self.w_cnr = self._inp("cBuildingNr", b.cBuildingNr)
        self.w_cpc = self._inp("cPostalCode", b.cPostalCode)
        self.w_ccity = self._inp("cCity", b.cCity)

        cc_val = b.cCountry if b.cCountry in COUNTRIES else COUNTRIES[0]
        self.w_ccountry = Select([(c, c) for c in COUNTRIES],
                                 value=cc_val, allow_blank=True, prompt="–",
                                 id=f"{self.prefix}-cCountry")

        self.w_pnote = self._inp("privateNote", b.privateNote)

    def compose(self) -> ComposeResult:
        def cell(label_key: str, control: Widget) -> Vertical:
            return Vertical(Label(tr(label_key)), control, classes="form-cell")

        with Vertical(classes="edit-form"):
            yield Label(f"── {tr('bill_section')} ──", classes="form-section")
            with Grid(classes="form-grid"):  # <--- CHANGED from Vertical to Grid
                yield cell("f_description", self.w_description)
                yield cell("f_due_date", self.w_due)
                yield cell("f_amount", self.w_amount)
                yield cell("f_currency", self.w_currency)
                yield cell("f_account", self.w_account)
                yield cell("f_reference", self.w_reference)
                yield cell("f_note", self.w_note)
                yield cell("f_paid_date", self.w_paid_date)
                yield cell("f_paid_with", self.w_paid_with)
                yield Vertical(self.w_checked, classes="form-cell")
            yield Label(f"── {tr('debtor_section')} ──", classes="form-section")
            with Grid(classes="form-grid"):  # <--- CHANGED from Vertical to Grid
                yield cell("f_dname", self.w_dname)
                yield cell("f_street", self.w_dstreet)
                yield cell("f_building_nr", self.w_dnr)
                yield cell("f_postal_code", self.w_dpc)
                yield cell("f_city", self.w_dcity)
                yield cell("f_country", self.w_dcountry)
            yield Label(f"── {tr('creditor_section')} ──", classes="form-section")
            with Grid(classes="form-grid"):  # <--- CHANGED from Vertical to Grid
                yield cell("f_cname", self.w_cname)
                yield cell("f_street", self.w_cstreet)
                yield cell("f_building_nr", self.w_cnr)
                yield cell("f_postal_code", self.w_cpc)
                yield cell("f_city", self.w_ccity)
                yield cell("f_country", self.w_ccountry)
            yield Label(f"── {tr('f_private_note')} ──", classes="form-section")
            yield self.w_pnote

    # -- programmatic access -------------------------------------------------
    def set_value(self, field: str, value: str) -> None:
        if field == "paidChecked":
            self.w_checked.value = str(value).strip().lower() in ("true", "1", "yes")
        elif field == "bCurrency":
            if value in CURRENCIES:
                self.w_currency.value = value
        elif field == "dCountry":
            if value in COUNTRIES:
                self.w_dcountry.value = value
        elif field == "cCountry":
            if value in COUNTRIES:
                self.w_ccountry.value = value
        elif field in self.inputs:
            if field in ("dueDate", "paidDate") and value:
                value = format_date(value, self.settings.date_format)
            self.inputs[field].value = value

    def focus_first_field(self) -> None:
        self.w_description.focus()

    # -- validation + collect -------------------------------------------------
    def collect(self) -> tuple[Bill | None, str | None]:
        """Returns (bill, None) on success or (None, error_message)."""
        vals = {f: w.value.strip() for f, w in self.inputs.items()}
        vals["bCurrency"] = (self.w_currency.value or "").strip()
        vals["dCountry"] = (self.w_dcountry.value or "").strip()
        vals["cCountry"] = (self.w_ccountry.value or "").strip()
        vals["paidChecked"] = "True" if self.w_checked.value else "False"

        errors: list[str] = []
        missing = [f for f in REQUIRED_FIELDS if not vals.get(f)]
        if missing:
            names = ", ".join(tr(FIELD_LABELS[f]) for f in missing)
            errors.append(tr("msg_missing_required").format(fields=names))

        raw = vals.get("bAmount", "")
        if raw:
            try:
                amt = Decimal(raw.replace("'", "").replace(" ", "").replace(",", "."))
                vals["bAmount"] = f"{amt:.2f}"
            except InvalidOperation:
                errors.append(tr("msg_invalid_amount"))

        for f in ("dueDate", "paidDate"):
            txt = vals.get(f, "")
            if not txt:
                vals[f] = ""
                continue
            try:
                vals[f] = parse_date(txt, self.settings.date_format).isoformat()
            except ValueError:
                errors.append(f"{tr(FIELD_LABELS[f])}: {tr('msg_invalid_date')}")

        if errors:
            return None, " · ".join(errors)
        return Bill(**{f: vals.get(f, "") for f in DATA_FIELDS}), None


# --------------------------------------------------------------------------- #
# PAY dialog
# --------------------------------------------------------------------------- #
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
                ok = Button(tr("btn_ok"), variant="success", classes="b-ok")
                cancel = Button(tr("btn_cancel"), classes="b-cancel")
                ok.kind = "ok"                # type: ignore[attr-defined]
                cancel.kind = "cancel"        # type: ignore[attr-defined]
                yield ok
                yield cancel

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
        kind = getattr(event.button, "kind", None)
        if kind == "cancel":
            self.dismiss(None)
        elif kind == "ok":
            await self._ok()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._ok()


# --------------------------------------------------------------------------- #
# Screens
# --------------------------------------------------------------------------- #
class MenuItem(ListItem):
    def __init__(self, label: str, menu_key: str):
        super().__init__(Label(label))
        self.menu_key = menu_key

class SplashScreen(ModalScreen):
    FOX_FRAMES = [
        "",
        "  /\\_/\\",
        "  /\\_/\\\n ( . . )",
        "  /\\_/\\\n ( o.o )\n  > ^ <",
        "  /\\_/\\\n ( o.o )\n  > ^ <\n /|   |\\\n (_|   |_)",
        "  /\\_/\\\n ( o.o )\n  > ^ <\n /|   |\\\n (_|   |_)",
        "  /\\_/\\\n ( -.o )\n  > ^ <\n /|   |\\\n (_|   |_)",
        "  /\\_/\\\n ( o.o )\n  > ^ <\n /|   |\\\n (_|   |_)",
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-box"):
            yield Static(" ", id="splash-fox")
            yield Static(" ", id="splash-title")
            yield Static(" ", id="splash-tagline")

    def on_mount(self) -> None:
        self._title = tr("splash_title")
        self._tagline = tr("splash_tagline")
        self._step = 0
        self._fox_len = len(self.FOX_FRAMES)
        self._title_len = len(self._title)
        self._total = self._fox_len + self._title_len + 12
        self.set_interval(0.10, self._tick)

    def _tick(self) -> None:
        self._step += 1
        s = self._step

        try:
            fox = self.query_one("#splash-fox", Static)
            title = self.query_one("#splash-title", Static)
            tagline = self.query_one("#splash-tagline", Static)
        except Exception:
            return

        if s <= self._fox_len:
            fox.update(self.FOX_FRAMES[s - 1] or " ")

        elif s <= self._fox_len + self._title_len:
            chars = s - self._fox_len
            shown = self._title[:chars]
            cursor = "█" if chars < self._title_len else ""
            title.update(f"[bold #4f6df5]{shown}[/][dim]{cursor}[/]")

        elif s == self._fox_len + self._title_len + 2:
            title.update(f"[bold #4f6df5]{self._title}[/]")
            tagline.update(f"[dim italic]{self._tagline}[/]")

        elif s >= self._total:
            self.dismiss()

class MainMenuScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle(id="menu-wrap"):
            with Vertical(id="menu-panel"):
                yield Static(tr("app_title"), id="menu-title")
                yield ListView(
                    MenuItem(tr("menu_all_bills"), "all"),
                    MenuItem(tr("menu_new_bill"), "new"),
                    MenuItem(tr("menu_scan_bill"), "scan"),
                    MenuItem(tr("menu_summary"), "summary"),
                    MenuItem(tr("menu_manage"), "manage"),
                    MenuItem(tr("menu_settings"), "settings"),
                    id="menu-list",
                )
        yield Static(f"{tr('hint_menu')}  ·  {tr('hint_nav')}", id="footer-hint")

    def on_mount(self) -> None:
        self.query_one("#menu-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = getattr(event.item, "menu_key", None)
        screens = {"all": BillsScreen, "new": NewBillScreen, "scan": ScanBillScreen,
                   "summary": SummaryScreen, "manage": ManageScreen, "settings": SettingsScreen}
        cls = screens.get(key)
        if cls is not None:
            self.app.push_screen(cls())

    def action_back(self) -> None:
        self.app.core.logger.info("app closed by user")
        self.app.exit()

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
                yes = Button(tr("btn_yes"), variant="error", classes="b-yes")
                no = Button(tr("btn_no"), variant="default", classes="b-no")
                yes.kind = "yes"
                no.kind = "no"
                yield yes
                yield no

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        kind = getattr(event.button, "kind", None)
        self.dismiss(kind == "yes")

class ManageScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle(id="menu-wrap"):
            with Vertical(id="menu-panel"):
                yield Static(tr("menu_manage"), id="menu-title")
                yield ListView(
                    MenuItem(tr("manage_debitors"), "debitors"),
                    MenuItem(tr("manage_creditors"), "creditors"),
                    id="menu-list",
                )
        yield Static(tr("hint_nav"), id="footer-hint")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = getattr(event.item, "menu_key", None)
        if key == "debitors":
            self.app.push_screen(ManageListScreen("debitor"))
        elif key == "creditors":
            self.app.push_screen(ManageListScreen("creditor"))

    def action_back(self) -> None:
        self.app.pop_screen()


class ManageListScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("delete", "delete_entry", "Delete"),
    ]

    def __init__(self, list_type: str):
        super().__init__()
        self.list_type = list_type  # "debitor" or "creditor"
        self.selected = 0

    @property
    def core(self) -> Core:
        return self.app.core

    @property
    def entries(self) -> list[dict]:
        return self.core.debitors if self.list_type == "debitor" else self.core.creditors

    def compose(self) -> ComposeResult:
        title = tr("manage_debitors") if self.list_type == "debitor" else tr("manage_creditors")
        yield Header()
        with VerticalScroll(id="manage-scroll"):
            yield Static(title, classes="screen-title")
            with Horizontal(classes="manage-buttons"):
                add = Button(tr("btn_add"), variant="success", id="btn-manage-add")
                delete = Button(tr("btn_delete"), variant="error", id="btn-manage-delete")
                add.kind = "add"
                delete.kind = "delete"
                yield add
                yield delete
            yield Static("", id="manage-count", classes="muted")
            yield Vertical(id="manage-entries")
        yield Static(tr("hint_nav"), id="footer-hint")

    async def on_mount(self) -> None:
        await self.rebuild()

    async def rebuild(self) -> None:
        container = self.query_one("#manage-entries", Vertical)
        await container.remove_children()
        entries = self.entries
        self.query_one("#manage-count", Static).update(
            tr("entries_count").format(n=len(entries)))
        self.selected = max(0, min(self.selected, len(entries) - 1))
        for i, entry in enumerate(entries):
            label = self._entry_label(entry)
            item = ManageEntryItem(label, i)
            item.set_class(i == self.selected, "selected")
            await container.mount(item)

    def _entry_label(self, entry: dict) -> str:
        if self.list_type == "debitor":
            parts = [entry.get("description", ""), entry.get("dName", "")]
        else:
            parts = [entry.get("cName", "")]
        return " · ".join(p for p in parts if p.strip()) or "–"

    def _highlight(self) -> None:
        items = self.query(ManageEntryItem)
        for i, item in enumerate(items):
            item.set_class(i == self.selected, "selected")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        kind = getattr(event.button, "kind", None)
        if kind == "add":
            if self.list_type == "debitor":
                self.app.push_screen(AddDebitorScreen())
            else:
                self.app.push_screen(AddCreditorScreen())
        elif kind == "delete":
            if 0 <= self.selected < len(self.entries):
                entry = self.entries[self.selected]
                async def on_confirm(result: bool) -> None:
                    if result:
                        self.entries.pop(self.selected)
                        self._save_list()
                        self.notify(tr("entry_deleted"))
                        await self.rebuild()
                self.app.push_screen(ConfirmDeleteModal(tr("confirm_delete_entry")), on_confirm)

    def action_delete_entry(self) -> None:
        if 0 <= self.selected < len(self.entries):
            entry = self.entries[self.selected]
            async def on_confirm(result: bool) -> None:
                if result:
                    self.entries.pop(self.selected)
                    self._save_list()
                    self.notify(tr("entry_deleted"))
                    await self.rebuild()
            self.app.push_screen(ConfirmDeleteModal(tr("confirm_delete_entry")), on_confirm)

    def _save_list(self) -> None:
        if self.list_type == "debitor":
            write_rows(self.core.userdata / "debitorList.csv", DEBITOR_FIELDS, self.core.debitors)
        else:
            write_rows(self.core.userdata / "creditorList.csv", CREDITOR_FIELDS, self.core.creditors)
        self.core.logger.info(f"{self.list_type} list saved ({len(self.entries)} entries)")

    async def on_screen_resume(self) -> None:
        await self.rebuild()

    def action_back(self) -> None:
        self.app.pop_screen()


class ManageEntryItem(Static):
    def __init__(self, label: str, index: int):
        super().__init__(f" {label}", classes="manage-entry")
        self.entry_index = index

    def on_click(self) -> None:
        screen = self.screen
        if isinstance(screen, ManageListScreen):
            screen.selected = self.entry_index
            screen._highlight()


class AddDebitorScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="newbill-scroll"):
            yield Static(tr("add_debitor_title"), classes="screen-title")
            with Grid(classes="form-grid"):
                yield self._cell("f_description", Input(id="deb-description"))
                yield self._cell("f_amount", Input(id="deb-amount", placeholder="0.00"))
                yield self._cell("f_currency", Select([(c, c) for c in CURRENCIES],
                             allow_blank=True, prompt="–", id="deb-currency"))
                yield self._cell("f_account_iban", Input(id="deb-account",
                             placeholder="CH12 1234 1234 1234 1234 4"))
                yield self._cell("f_dname", Input(id="deb-dname"))
                yield self._cell("f_street", Input(id="deb-dstreet"))
                yield self._cell("f_building_nr", Input(id="deb-dnr"))
                yield self._cell("f_postal_code", Input(id="deb-dpc"))
                yield self._cell("f_city", Input(id="deb-dcity"))
                yield self._cell("f_country", Select([(c, c) for c in COUNTRIES],
                             allow_blank=True, prompt="–", id="deb-dcountry"))
            with Horizontal(classes="newbill-buttons"):
                yield Button(tr("btn_save"), variant="success", id="btn-deb-save")
                yield Button(tr("btn_cancel"), id="btn-deb-cancel")
        yield Static(tr("hint_nav"), id="footer-hint")

    def _cell(self, label_key: str, control: Widget) -> Vertical:
        return Vertical(Label(tr(label_key)), control, classes="form-cell")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-deb-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-deb-save":
            entry = {
                "description": self.query_one("#deb-description", Input).value.strip(),
                "amount": self.query_one("#deb-amount", Input).value.strip(),
                "currency": self.query_one("#deb-currency", Select).value or "",
                "account": self.query_one("#deb-account", Input).value.strip(),
                "dName": self.query_one("#deb-dname", Input).value.strip(),
                "dStreet": self.query_one("#deb-dstreet", Input).value.strip(),
                "dBuildingNr": self.query_one("#deb-dnr", Input).value.strip(),
                "dPostalCode": self.query_one("#deb-dpc", Input).value.strip(),
                "dCity": self.query_one("#deb-dcity", Input).value.strip(),
                "dCountry": self.query_one("#deb-dcountry", Select).value or "",
            }
            if not entry["dName"]:
                self.notify(tr("msg_missing_required").format(fields=tr("f_dname")),
                            severity="error")
                return
            self.app.core.debitors.append(entry)
            write_rows(self.app.core.userdata / "debitorList.csv",
                       DEBITOR_FIELDS, self.app.core.debitors)
            self.app.core.logger.info(f"debitor template added: {entry['dName']!r}")
            self.notify(tr("entry_added"))
            self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()


class AddCreditorScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="newbill-scroll"):
            yield Static(tr("add_creditor_title"), classes="screen-title")
            with Grid(classes="form-grid"):
                yield self._cell("f_cname", Input(id="cred-cname"))
                yield self._cell("f_street", Input(id="cred-cstreet"))
                yield self._cell("f_building_nr", Input(id="cred-cnr"))
                yield self._cell("f_postal_code", Input(id="cred-cpc"))
                yield self._cell("f_city", Input(id="cred-ccity"))
                yield self._cell("f_country", Select([(c, c) for c in COUNTRIES],
                             allow_blank=True, prompt="–", id="cred-ccountry"))
            with Horizontal(classes="newbill-buttons"):
                yield Button(tr("btn_save"), variant="success", id="btn-cred-save")
                yield Button(tr("btn_cancel"), id="btn-cred-cancel")
        yield Static(tr("hint_nav"), id="footer-hint")

    def _cell(self, label_key: str, control: Widget) -> Vertical:
        return Vertical(Label(tr(label_key)), control, classes="form-cell")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cred-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-cred-save":
            entry = {
                "cName": self.query_one("#cred-cname", Input).value.strip(),
                "cStreet": self.query_one("#cred-cstreet", Input).value.strip(),
                "cBuildingNr": self.query_one("#cred-cnr", Input).value.strip(),
                "cPostalCode": self.query_one("#cred-cpc", Input).value.strip(),
                "cCity": self.query_one("#cred-ccity", Input).value.strip(),
                "cCountry": self.query_one("#cred-ccountry", Select).value or "",
            }
            if not entry["cName"]:
                self.notify(tr("msg_missing_required").format(fields=tr("f_cname")),
                            severity="error")
                return
            self.app.core.creditors.append(entry)
            write_rows(self.app.core.userdata / "creditorList.csv",
                       CREDITOR_FIELDS, self.app.core.creditors)
            self.app.core.logger.info(f"creditor template added: {entry['cName']!r}")
            self.notify(tr("entry_added"))
            self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()

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
        self.query_one("#scan-status", Static).update(f"[red]{msg}[/red]")
        self.notify(msg, severity="error")

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
        await self.rebuild()

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
        if not self.rows or self._form_focused():
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
            self.notify(tr("err_qr_failed").format(err=exc), severity="error", timeout=10)

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


class NewBillScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        core: Core = self.app.core
        blank = Bill(
            bCurrency=core.settings.default_currency,
            dCountry=core.settings.default_country,
            cCountry=core.settings.default_country,
        )
        self.form = BillEditForm(blank, core.settings, f"new{uuid4().hex[:6]}")
        yield Header()
        with VerticalScroll(id="newbill-scroll"):
            yield Static(tr("new_bill_title"), classes="screen-title")
            with Horizontal(classes="tpl-row"):
                with Vertical(classes="tpl-cell"):
                    yield Label(tr("tpl_debtor"))
                    yield Select(self._options(core.debitors, debtor=True), allow_blank=True,
                                 prompt=tr("tpl_none"), id="tpl-debtor")
                with Vertical(classes="tpl-cell"):
                    yield Label(tr("tpl_creditor"))
                    yield Select(self._options(core.creditors, debtor=False), allow_blank=True,
                                 prompt=tr("tpl_none"), id="tpl-creditor")
            yield self.form
            with Horizontal(classes="newbill-buttons"):
                yield Button(tr("btn_save"), variant="success", id="btn-new-save")
                yield Button(tr("btn_cancel"), id="btn-new-cancel")
        yield Static(tr("hint_nav"), id="footer-hint")

    @staticmethod
    def _options(rows: list[dict], debtor: bool) -> list[tuple[str, int]]:
        opts = []
        for i, r in enumerate(rows):
            if debtor:
                label = " · ".join(p for p in (r.get("description", ""), r.get("dName", ""))
                                   if p.strip())
            else:
                label = (r.get("cName") or "").strip()
            opts.append((label or f"#{i + 1}", i))
        return opts

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is None:
            return
        core: Core = self.app.core
        if event.select.id == "tpl-debtor" and event.value < len(core.debitors):
            tpl = core.debitors[event.value]
            mapping = {"description": "description", "bAmount": "amount",
                       "bCurrency": "currency", "bAccount": "account",
                       "dName": "dName", "dStreet": "dStreet",
                       "dBuildingNr": "dBuildingNr", "dPostalCode": "dPostalCode",
                       "dCity": "dCity", "dCountry": "dCountry"}
        elif event.select.id == "tpl-creditor" and event.value < len(core.creditors):
            tpl = core.creditors[event.value]
            mapping = {f: f for f in CREDITOR_FIELDS}
        else:
            return
        for target, source in mapping.items():
            value = (tpl.get(source) or "").strip()
            if value:
                self.form.set_value(target, value)
        core.logger.info(f"template applied ({event.select.id})")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-new-save":
            core: Core = self.app.core
            bill, err = self.form.collect()
            if err:
                core.logger.warning(f"new bill rejected: {err}")
                self.notify(err, severity="error", timeout=10)
                return
            core.bills.append(bill)
            core.persist()
            core.logger.info(f"new bill saved: {bill.description!r}")
            self.notify(tr("msg_bill_saved"))
            await self.app.switch_screen(BillsScreen())

    def action_back(self) -> None:
        self.app.pop_screen()

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


class SearchResultItem(Static):
    def __init__(self, bill: Bill, settings: Settings):
        self.bill = bill
        super().__init__(self._build_text(bill, settings), classes="search-result")

    def _build_text(self, bill: Bill, settings: Settings):
        from rich.text import Text as RichText
        state = bill_state(bill)
        text = RichText()
        if state == "paid":
            text.append(f" {tr('status_paid'):<12}", style="bold #2ecc71")
        elif state == "overdue":
            text.append(f" {tr('status_overdue'):<12}", style="bold #ff4d4f")
        else:
            text.append(f" {tr('status_open'):<12}", style="bold #f5a623")
        due = format_date(bill.dueDate, settings.date_format) or "–"
        text.append(f" {due:<12}")
        text.append(f" {bill.description or '–'}")
        amount = f"{amount_decimal(bill.bAmount):,.2f} {bill.bCurrency}"
        text.append(f"  {amount:>16}", style="bold")
        return text

    def on_click(self) -> None:
        # Push a BillsScreen focused on this bill (simple approach: just notify)
        self.notify(f"{self.bill.description}")

class SummaryScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        core: Core = self.app.core
        fmt = core.settings.date_format
        today = date.today()
        open_bills = [b for b in core.bills if not b.is_paid]

        yield Header()
        with VerticalScroll(id="summary-scroll"):
            yield Static(tr("menu_summary"), classes="screen-title")

            # open totals per currency
            yield Static(tr("summary_open_total"), classes="summary-head")
            if open_bills:
                sums: dict[str, Decimal] = defaultdict(Decimal)
                for b in open_bills:
                    sums[b.bCurrency or "?"] += amount_decimal(b.bAmount)
                t = Table(box=None, pad_edge=False, padding=(0, 2))
                t.add_column(width=10)
                t.add_column(justify="right", width=18)
                for cur in sorted(sums):
                    t.add_row(Text(cur, style="bold"), Text(format_amount(sums[cur]), style="bold #f5a623"))
                yield Static(t, classes="summary-block")
                yield Static(tr("summary_count").format(n=len(open_bills)),
                             classes="summary-block muted")
            else:
                yield Static(tr("summary_no_open"), classes="summary-block muted")

            yield Static(tr("summary_due14"), classes="summary-head")
            yield self._due_block(open_bills, today, today + timedelta(days=14), fmt,
                                  include_overdue=True)

            yield Static(tr("summary_due30"), classes="summary-head")
            yield self._due_block(open_bills, today + timedelta(days=14),
                                  today + timedelta(days=30), fmt, include_overdue=False)

            paid = [b for b in core.bills
                    if b.is_paid and (b.paidDate or "")[:4] == str(today.year)]
            yield Static(tr("summary_paid_year"), classes="summary-head")
            if paid:
                sums2: dict[str, Decimal] = defaultdict(Decimal)
                for b in paid:
                    sums2[b.bCurrency or "?"] += amount_decimal(b.bAmount)
                t2 = Table(box=None, pad_edge=False, padding=(0, 2))
                t2.add_column(width=10)
                t2.add_column(justify="right", width=18)
                for cur in sorted(sums2):
                    t2.add_row(Text(cur, style="bold"), Text(f"{sums2[cur]:,.2f}", style="bold #2ecc71"))
                yield Static(t2, classes="summary-block")
                yield Static(tr("summary_count").format(n=len(paid)), classes="muted")
            else:
                yield Static("–", classes="summary-block muted")

        yield Static(tr("hint_nav"), id="footer-hint")

    def _due_block(self, open_bills: list[Bill], lo: date, hi: date, fmt: str,
                   include_overdue: bool) -> Static:
        today = date.today()
        picked: list[tuple[date, Bill]] = []
        for b in open_bills:
            iso = (b.dueDate or "").strip()
            if not iso:
                continue
            try:
                d = date.fromisoformat(iso)
            except ValueError:
                continue
            if (include_overdue and d <= hi) or (not include_overdue and lo < d <= hi):
                picked.append((d, b))
        if not picked:
            return Static("–", classes="summary-block muted")
        picked.sort(key=lambda x: x[0])
        t = Table(box=None, pad_edge=False, padding=(0, 2))
        t.add_column(width=12)
        t.add_column(ratio=1, overflow="ellipsis")
        t.add_column(justify="right", width=18)
        for d, b in picked:
            style = "#ff4d4f bold" if d < today else None
            t.add_row(Text(format_date(b.dueDate, fmt), style=style), b.description or "–",
                          f"{format_amount(amount_decimal(b.bAmount))} {b.bCurrency}")
        return Static(t, classes="summary-block")

    def action_back(self) -> None:
        self.app.pop_screen()


class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        s: Settings = self.app.core.settings
        yield Header()
        with VerticalScroll(id="settings-scroll"):
            yield Static(tr("menu_settings"), classes="screen-title")
            with Vertical(id="settings-panel"):
                yield self._row(tr("set_language"), Select(
                    [(f"{LANG_NAMES.get(c, c)} ({c})", c) for c in LANG_CODES],
                    value=s.language, id="set-language"))
                yield self._row(tr("set_date_format"), Select(
                    [(f, f) for f in DATE_FORMATS], value=s.date_format, id="set-date-format"))
                yield self._row(tr("set_currency"), Select(
                    [(c, c) for c in CURRENCIES],
                    value=s.default_currency if s.default_currency in CURRENCIES else None,
                    id="set-currency"))
                yield self._row(tr("set_country"), Select(
                    [(c, c) for c in COUNTRIES],
                    value=s.default_country if s.default_country in COUNTRIES else None,
                    id="set-country"))
                yield self._row(tr("set_sort_by"), Select(
                    [(tr("sort_due_date"), "dueDate"), (tr("sort_paid_date"), "paidDate"),
                     (tr("sort_description"), "description")],
                    value=s.sort_by, id="set-sort-by"))
                yield self._row(tr("set_sort_order"), Select(
                    [(tr("sort_asc"), "asc"), (tr("sort_desc"), "desc")],
                    value=s.sort_order, id="set-sort-order"))
                yield self._row(tr("set_loglevel"), Select(
                    [("DEBUG", "debug"), ("INFO", "info"), ("ERROR", "error")],
                    value=s.loglevel.lower(), id="set-loglevel"))
                yield self._row(tr("set_logsize"), Input(value=str(s.logsize), id="set-logsize"))
        yield Static(tr("hint_nav"), id="footer-hint")

    @staticmethod
    def _row(label: str, control: Widget) -> Horizontal:
        return Horizontal(Static(label, classes="set-label"), control, classes="set-row")

    async def on_select_changed(self, event: Select.Changed) -> None:
        mapping = {
            "set-language": "language",
            "set-date-format": "date_format",
            "set-currency": "default_currency",
            "set-country": "default_country",
            "set-sort-by": "sort_by",
            "set-sort-order": "sort_order",
            "set-loglevel": "loglevel",
        }
        key = mapping.get(event.select.id or "")
        if key is None or event.value is None:
            return

        core: Core = self.app.core

        # --- ADD THIS CHECK ---
        # Ignore events fired during initial widget mounting
        if getattr(core.settings, key) == event.value:
            return
        # ----------------------

        setattr(core.settings, key, event.value)
        core.save_settings_file()
        core.logger.info(f"settings: {key} = {event.value}")
        if key == "loglevel":
            core.logger.set_level(event.value)
        self.notify(tr("msg_settings_saved"))
        if key == "language":
            set_language(event.value)
            await self.app.rebuild_ui()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "set-logsize":
            return
        try:
            n = max(100, int(event.value.strip()))
        except ValueError:
            self.notify(f"{tr('set_logsize')}: 100 … 1000000", severity="error")
            return
        core: Core = self.app.core
        core.settings.logsize = n
        core.save_settings_file()
        core.logger.set_max_lines(n)
        core.logger.info(f"settings: logsize = {n}")
        self.notify(tr("msg_settings_saved"))

    def action_back(self) -> None:
        self.app.pop_screen()


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
APP_CSS = """
Screen { background: #101318; }
Header { background: #151a23; color: #9db4ff; }
#footer-hint { dock: bottom; height: 1; background: #151a23; color: #707a8c; padding: 0 1; }
.screen-title { text-style: bold; color: #dfe6ff; margin: 0 0 1 0; }

/* main menu */
#menu-wrap { width: 100%; height: 100%; align: center middle; }
#menu-panel { width: 68; height: auto; border: heavy #4f6df5; background: #151a23; padding: 1 3 2 3; }
#menu-title { width: 100%; text-align: center; text-style: bold; color: #dfe6ff; padding: 1 0 2 0; }
#menu-list { height: auto; background: #151a23; }
#menu-list MenuItem { padding: 1 2; height: 3; }

/* bill list */
#bill-list { height: 1fr; padding: 0 1 2 1; }
BillRow { height: auto; margin: 0; background: #151a23; border-left: thick #333d55; }
BillRow.expanded { height: auto; }
BillRow.selected { border-left: thick #4f6df5; background: #1a2130; }
BillRow .row-head { height: 1; width: 100%; padding: -1 0 0 1; }
BillRow .row-head:hover { background: #212a3c; }
BillRow .row-detail { height: auto; padding: 0 2 1 5; }
.row-buttons { height: auto; margin-top: 1; }
.row-buttons Button { margin-right: 2; min-width: 14; }
.edit-box { height: auto; }
.empty-hint { color: #707a8c; margin: 1; }
#bills-search { margin: 1 2; height: 3; }

BillRow .detail-view {
    height: auto;
    background: transparent;
    border: none;
    padding: 1 1;
}

/* bill form */
.edit-form { height: auto; width: 100%; }
.form-section { color: #8ab4f8; text-style: bold; margin-top: 1; }
.form-grid { grid-size: 2; grid-gutter: 1 3; height: auto; margin-top: 1; width: 100%; }
.form-cell { height: auto; width: 100%; }
.form-cell Label { color: #8590a6; height: 1; }

/* new bill */
#newbill-scroll { height: 1fr; padding: 1 2; width: 100%; }

/* confirm delete dialog */
ConfirmDeleteModal { align: center middle; }
#confirm-dialog { width: 60; height: auto; border: heavy #ff4d4f; background: #151a23; padding: 1 3 2 3; }
.dlg-msg { margin: 1 0; color: #c3cbd9; }

/* pay dialog */
PayModal { align: center middle; }
#pay-dialog { width: 76; height: auto; border: heavy #4f6df5; background: #151a23; padding: 1 3 2 3; }
.dlg-title { text-style: bold; color: #dfe6ff; margin-bottom: 1; }
#pay-dialog Label { margin-top: 1; color: #8590a6; }
.dlg-buttons { margin-top: 1; height: auto; align-horizontal: right; }
.dlg-buttons Button { margin-left: 2; min-width: 12; }

/* summary */
#summary-scroll { height: 1fr; padding: 1 2; }
.summary-head { text-style: bold; color: #8ab4f8; margin-top: 1; }
.summary-block { height: auto; margin: 0 0 1 0; }
.muted { color: #707a8c; }

/* settings */
#settings-scroll { height: 1fr; padding: 1 2; }
#settings-panel { height: auto; border: heavy #333d55; background: #151a23; padding: 1 2; }
.set-row { height: auto; margin: 0 0 1 0; }
.set-label { width: 32; color: #c3cbd9; padding: 1 0; }
.set-row Select { width: 44; }
.set-row Input { width: 44; }

/* new bill */
#newbill-scroll { height: 1fr; padding: 1 2; }
.tpl-row { height: auto; margin: 0 0 1 0; }
.tpl-cell { width: 1fr; margin-right: 3; height: auto; }
.tpl-cell Label { color: #8590a6; height: 1; }
.newbill-buttons { margin-top: 1; height: auto; }
.newbill-buttons Button { margin-right: 2; min-width: 14; }

/* manage */
#manage-scroll { height: 1fr; padding: 1 2; }
.manage-buttons { height: auto; margin-bottom: 1; }
.manage-buttons Button { margin-right: 2; min-width: 14; }
.manage-entry { height: 1; padding: 0 1; }
.manage-entry:hover { background: #212a3c; }
.manage-entry.selected { background: #2b3650; color: #ffffff; }


/* splash screen */
SplashScreen { align: center middle; background: #101318; }
#splash-box { width: 30; height: 12; align: center middle; background: #101318; }
#splash-fox { color: #f5a623; text-align: center; width: 100%; height: 5; content-align: center middle; }
#splash-title { text-align: center; width: 100%; height: 1; content-align: center middle; }
#splash-tagline { text-align: center; width: 100%; height: 1; color: #707a8c; content-align: center middle; }

/* scan bill */
#menu-panel Button { margin: 1 4; min-width: 20; }
#scan-status { text-align: center; height: 1; margin-top: 1; }
"""


class BillApp(App):
    CSS = APP_CSS
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.core = Core(BASE_DIR)

    def on_mount(self) -> None:
        self.title = tr("app_title")
        self.push_screen(MainMenuScreen())
        self.push_screen(SplashScreen())

    def action_quit(self) -> None:
        self.core.logger.info("quit (ctrl+q)")
        self.exit()

    async def rebuild_ui(self) -> None:
        """Pop everything and rebuild the UI so all texts refresh after a language change."""
        self.title = tr("app_title")
        # Safely pop screens until we are back at the MainMenuScreen
        while self.screen_stack and not isinstance(self.screen, MainMenuScreen):
            self.pop_screen()
        # Switch to a fresh MainMenuScreen to apply new language translations
        await self.switch_screen(MainMenuScreen())


def main() -> None:
    BillApp().run()


if __name__ == "__main__":
    main()
