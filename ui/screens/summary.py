"""Totals and upcoming bills."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Header, Static

from appdata.csvparser import Bill, amount_decimal, format_date
from appdata.languages import tr
from ui.helpers import format_amount
from ui.screens.base import BackScreen


class SummaryScreen(BackScreen):
    def compose(self) -> ComposeResult:
        core = self.core
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
                    t2.add_row(Text(cur, style="bold"), Text(format_amount(sums2[cur]), style="bold #2ecc71"))
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
