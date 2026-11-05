"""Headless UI tests. Each one runs against its own temporary data folder."""
import asyncio

import pytest
from textual.widgets import Button, Input, Select

from ui import app as bill_app
from ui.dialogs import ConfirmDeleteModal, PayModal
from ui.screens.bills import BillRow, BillsScreen, EditBillScreen, RowButton
from ui.screens.main_menu import MainMenuScreen
from ui.screens.splash import SplashScreen
from ui.screens.new_bill import NewBillScreen
from ui.screens.scan import ScanBillScreen
from ui.screens.settings import SettingsScreen
from ui.screens.summary import SummaryScreen
from ui.screens.scan import ScanEditScreen
from ui.screens.templates import (
    AddPayerTemplateScreen, AddRecipientTemplateScreen, ManageEntryItem, ManageListScreen, ManageScreen,
)
from appdata.csvparser import (
    PAYER_TEMPLATE_COLUMNS, RECIPIENT_TEMPLATE_COLUMNS, Bill, load_bills, load_settings, read_rows, save_bills,
    write_rows,
)
from appdata.languages import set_language


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bill_app, "BASE_DIR", tmp_path)
    yield tmp_path
    set_language("en")


def run(test):
    """Start the app, skip the splash screen and run `test(app, pilot)`."""
    async def runner():
        app = bill_app.BillApp()
        async with app.run_test(size=(120, 50)) as pilot:
            await pilot.pause(0.1)
            while isinstance(app.screen, SplashScreen):
                app.screen.dismiss()
                await pilot.pause(0.05)
            await test(app, pilot)
            await pilot.pause(0.1)
    asyncio.run(runner())


@pytest.mark.parametrize("screen", [
    BillsScreen, NewBillScreen, ScanBillScreen, SummaryScreen, ManageScreen, SettingsScreen,
])
def test_every_screen_opens(data_dir, screen):
    async def test(app, pilot):
        app.push_screen(screen())
        await pilot.pause(0.2)
        assert type(app.screen) is screen
    run(test)


def test_arrow_keys_work_after_opening_bill_list(data_dir):
    async def test(app, pilot):
        app.push_screen(BillsScreen())
        await pilot.pause(0.3)
        screen = app.screen
        assert isinstance(screen.focused, Input)      # can type to search straight away
        await pilot.press("down")                     # leaves the search box
        await pilot.press("down")
        await pilot.pause(0.1)
        assert screen.selected == 1
        await pilot.press("up")
        await pilot.pause(0.1)
        assert screen.selected == 0
    run(test)


def test_enter_in_search_moves_to_the_list(data_dir):
    async def test(app, pilot):
        app.push_screen(BillsScreen())
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.press("enter")                    # now expands the selected row
        await pilot.pause(0.2)
        assert app.screen.rows[0].is_expanded
    run(test)


def test_manage_list_keyboard_selection(data_dir):
    async def test(app, pilot):
        app.push_screen(ManageListScreen("recipient"))
        await pilot.pause(0.3)
        await pilot.press("down")
        await pilot.pause(0.1)
        assert app.screen.selected == 1
    run(test)


def test_clearing_a_form_dropdown_reports_missing_field(data_dir):
    async def test(app, pilot):
        app.push_screen(NewBillScreen())
        await pilot.pause(0.2)
        form = app.screen.form
        form.w_currency.clear()
        await pilot.pause(0.1)
        bill, error = form.collect()
        assert bill is None
        assert "Currency" in error
    run(test)


def test_clearing_a_template_selection_is_safe(data_dir):
    async def test(app, pilot):
        app.push_screen(NewBillScreen())
        await pilot.pause(0.2)
        template = app.screen.query_one("#tpl-recipient", Select)
        template.value = 0
        await pilot.pause(0.2)
        form = app.screen.form
        assert form.w_description.value == "Steuerrechnung"
        assert form.w_recipient_name.value == "Finanzamt Zürich"
        assert form.w_amount.value == "1250.00"
        assert form.w_currency.value == "CHF"
        app.screen.query_one("#tpl-payer", Select).value = 0
        await pilot.pause(0.2)
        assert form.w_payer_name.value == "Max Muster"
        template.clear()
        await pilot.pause(0.2)
    run(test)


def test_untouched_dropdown_saves_as_empty(data_dir):
    async def test(app, pilot):
        app.push_screen(AddPayerTemplateScreen())
        await pilot.pause(0.2)
        app.screen.query_one("#template-payer_name", Input).value = "Test"
        app.screen.query_one("#btn-template-save").press()
        await pilot.pause(0.3)
    run(test)
    rows = read_rows(data_dir / "userdata" / "payerList.csv", PAYER_TEMPLATE_COLUMNS)
    assert rows[-1]["payer_name"] == "Test"
    assert rows[-1]["payer_country"] == ""


def test_old_select_null_cells_are_cleaned_on_load(tmp_path):
    path = tmp_path / "payerList.csv"
    write_rows(path, PAYER_TEMPLATE_COLUMNS, [{"payer_name": "Old", "payer_country": "Select.NULL"}])
    assert read_rows(path, PAYER_TEMPLATE_COLUMNS)[0]["payer_country"] == ""


def test_editing_keeps_unusual_and_empty_values(data_dir):
    bill = Bill(description="x", amount="1.00", currency="GBP", account="a",
                recipient_name="n", recipient_postal_code="1", recipient_city="c", recipient_country="EE", payer_country="")

    async def test(app, pilot):
        app.push_screen(EditBillScreen(bill))
        await pilot.pause(0.2)
        saved, error = app.screen.form.collect()
        assert error is None
        assert (saved.currency, saved.recipient_country, saved.payer_country) == ("GBP", "EE", "")
    run(test)


@pytest.mark.parametrize("name", ["Foo [/bar] AG", "Foo [bar] AG"])
def test_brackets_in_names_render(data_dir, name):
    async def test(app, pilot):
        app.core.payer_templates.append({"payer_name": name, "payer_country": "CH"})
        app.core.recipient_templates.append({"description": name, "recipient_name": name})
        app.core.bills.append(Bill(description=name, due_date="2030-01-01", amount="1",
                                   currency="CHF", recipient_name=name, payer_name=name))
        for screen in (ManageListScreen("payer"), NewBillScreen(),
                       BillsScreen(), SummaryScreen()):
            app.push_screen(screen)
            await pilot.pause(0.3)
            app.pop_screen()
            await pilot.pause(0.1)
    run(test)


def test_qr_error_with_brackets_is_shown_not_crashed(data_dir):
    async def test(app, pilot):
        screen = ScanBillScreen()
        app.push_screen(screen)
        await pilot.pause(0.2)
        screen._fail("bad [/path] value")
        await pilot.pause(0.2)
    run(test)


def test_unknown_settings_fall_back_and_screen_opens(data_dir):
    userdata = data_dir / "userdata"
    userdata.mkdir()
    (userdata / "settings.toml").write_text(
        '[settings]\nlanguage = "xx"\ndefault_currency = "GBP"\ndefault_country = "ZZ"\n',
        encoding="utf-8")
    settings = load_settings(userdata / "settings.toml")
    assert (settings.language, settings.default_currency, settings.default_country) == \
        ("en", "CHF", "CH")

    async def test(app, pilot):
        app.push_screen(SettingsScreen())
        await pilot.pause(0.3)
    run(test)


def test_paying_a_bill_is_saved(data_dir):
    userdata = data_dir / "userdata"
    save_bills(userdata / "data.csv", [Bill(description="a", due_date="2030-01-01",
                                            amount="1.00", currency="CHF")])

    async def test(app, pilot):
        app.push_screen(BillsScreen())
        await pilot.pause(0.3)
        screen = app.screen
        screen._pay(screen.rows[0])
        await pilot.pause(0.2)
        await app.screen._ok()
        await pilot.pause(0.4)
        assert len(list(screen.query(BillRow))) == 1
        assert app.core.bills[0].is_paid
    run(test)
    assert "a," in (userdata / "data.csv").read_text(encoding="utf-8")


def test_language_switch_returns_to_translated_menu(data_dir):
    async def test(app, pilot):
        app.push_screen(SettingsScreen())
        await pilot.pause(0.3)
        app.screen.query_one("#set-language", Select).value = "de"
        await pilot.pause(0.5)
        assert isinstance(app.screen, MainMenuScreen)
        assert app.title == "Rechnungsverwaltung"
        await pilot.press("enter")    # the app must still respond after switching
        await pilot.pause(0.3)
        assert isinstance(app.screen, BillsScreen)
    run(test)


MENU_ROUTES = [(0, BillsScreen), (1, NewBillScreen), (2, ScanBillScreen),
               (3, SummaryScreen), (4, ManageScreen), (5, SettingsScreen)]


@pytest.mark.parametrize("position, screen", MENU_ROUTES)
def test_main_menu_opens_screens_with_keyboard(data_dir, position, screen):
    async def test(app, pilot):
        for _ in range(position):
            await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert type(app.screen) is screen
        await pilot.press("tab")
        app.set_focus(None)
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert isinstance(app.screen, MainMenuScreen)
    run(test)


def seed(data_dir, *descriptions):
    save_bills(data_dir / "userdata" / "data.csv", [
        Bill(description=d, due_date="2030-01-01", amount="1.00", currency="CHF", account="a",
             recipient_name="n", recipient_postal_code="1", recipient_city="c", recipient_country="CH")
        for d in descriptions])


async def open_first_row(app, pilot):
    app.push_screen(BillsScreen())
    await pilot.pause(0.3)
    app.screen.row_clicked(0)
    await pilot.pause(0.3)
    return app.screen


def row_button(screen, command):
    return next(b for b in screen.query(RowButton) if b.command == command)


def test_row_pay_button_opens_dialog_and_saves(data_dir):
    seed(data_dir, "a")

    async def test(app, pilot):
        screen = await open_first_row(app, pilot)
        row_button(screen, "pay").press()
        await pilot.pause(0.3)
        assert isinstance(app.screen, PayModal)
        app.screen.query_one("#pay-ok", Button).press()
        await pilot.pause(0.5)
        assert app.screen is screen
    run(test)
    assert load_bills(data_dir / "userdata" / "data.csv")[0].is_paid


def test_row_pay_cancel_changes_nothing(data_dir):
    seed(data_dir, "a")

    async def test(app, pilot):
        screen = await open_first_row(app, pilot)
        row_button(screen, "pay").press()
        await pilot.pause(0.3)
        app.screen.query_one("#pay-cancel", Button).press()
        await pilot.pause(0.3)
        assert app.screen is screen
    run(test)
    assert not load_bills(data_dir / "userdata" / "data.csv")[0].is_paid


def test_row_delete_button_needs_confirmation(data_dir):
    seed(data_dir, "a", "b")

    async def test(app, pilot):
        screen = await open_first_row(app, pilot)
        row_button(screen, "delete").press()
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmDeleteModal)
        app.screen.query_one("#confirm-no", Button).press()
        await pilot.pause(0.3)
        assert len(app.core.bills) == 2
        screen.row_clicked(0)         # the list rebuilds after a dialog, so reopen the row
        await pilot.pause(0.3)
        row_button(screen, "delete").press()
        await pilot.pause(0.3)
        app.screen.query_one("#confirm-yes", Button).press()
        await pilot.pause(0.5)
        assert len(screen.rows) == 1
    run(test)
    assert len(load_bills(data_dir / "userdata" / "data.csv")) == 1


def test_row_edit_button_saves_the_right_bill(data_dir):
    seed(data_dir, "a", "b")

    async def test(app, pilot):
        screen = await open_first_row(app, pilot)
        target = screen.rows[0].bill.description
        row_button(screen, "edit").press()
        await pilot.pause(0.3)
        assert isinstance(app.screen, EditBillScreen)
        app.screen.form.w_description.value = target + " edited"
        app.screen.query_one("#btn-form-save", Button).press()
        await pilot.pause(0.5)
        assert app.screen is screen
        assert any(r.bill.description == target + " edited" for r in screen.rows)
    run(test)
    names = [b.description for b in load_bills(data_dir / "userdata" / "data.csv")]
    assert sorted(names) == ["a edited", "b"]


def test_row_qr_button_reports_a_failure(data_dir):
    seed(data_dir, "a")           # account "a" isn't a valid IBAN

    async def test(app, pilot):
        screen = await open_first_row(app, pilot)
        row_button(screen, "qr").press()
        await pilot.pause(0.3)
        assert app.screen is screen
    run(test)
    assert not (data_dir / "userdata" / "qrbill.png").exists()


def fill_required(form):
    form.w_description.value = "Neu"
    form.w_amount.value = "12,50"
    form.w_account.value = "CH93 0076 2011 6238 5295 7"
    form.w_recipient_name.value = "Firma"
    form.w_recipient_postal_code.value = "8000"
    form.w_recipient_city.value = "Zürich"


def test_new_bill_saves_and_goes_to_list(data_dir):
    seed(data_dir)

    async def test(app, pilot):
        app.push_screen(NewBillScreen())
        await pilot.pause(0.3)
        fill_required(app.screen.form)
        app.screen.query_one("#btn-form-save", Button).press()
        await pilot.pause(0.5)
        assert isinstance(app.screen, BillsScreen)
        app.set_focus(None)
        await pilot.press("escape")   # the app must still respond after saving
        await pilot.pause(0.3)
        assert isinstance(app.screen, MainMenuScreen)
    run(test)
    bill = load_bills(data_dir / "userdata" / "data.csv")[0]
    assert (bill.description, bill.amount, bill.reference) == ("Neu", "12.50", "")


def test_new_bill_with_bad_amount_stays_on_form(data_dir):
    seed(data_dir)

    async def test(app, pilot):
        app.push_screen(NewBillScreen())
        await pilot.pause(0.3)
        fill_required(app.screen.form)
        app.screen.form.w_amount.value = "1,250"
        app.screen.query_one("#btn-form-save", Button).press()
        await pilot.pause(0.3)
        assert isinstance(app.screen, NewBillScreen)
    run(test)
    assert load_bills(data_dir / "userdata" / "data.csv") == []


def test_saving_a_scanned_bill_returns_past_scan_menu(data_dir):
    seed(data_dir)

    async def test(app, pilot):
        app.push_screen(ScanBillScreen())
        await pilot.pause(0.2)
        app.screen._open_form({"description": "Scan", "amount": "5.00", "currency": "CHF",
                               "account": "a", "recipient_name": "n", "recipient_postal_code": "1", "recipient_city": "c",
                               "recipient_country": "CH"})
        await pilot.pause(0.3)
        assert isinstance(app.screen, ScanEditScreen)
        app.screen.query_one("#btn-form-save", Button).press()
        await pilot.pause(0.5)
        assert isinstance(app.screen, MainMenuScreen)
        await pilot.press("enter")    # the app must still respond after saving
        await pilot.pause(0.3)
        assert isinstance(app.screen, BillsScreen)
    run(test)
    assert load_bills(data_dir / "userdata" / "data.csv")[0].description == "Scan"


def test_recipient_template_add_validates_amount(data_dir):
    async def test(app, pilot):
        app.push_screen(AddRecipientTemplateScreen())
        await pilot.pause(0.2)
        app.screen.query_one("#template-recipient_name", Input).value = "Firma"
        app.screen.query_one("#template-amount", Input).value = "1,250"
        app.screen.query_one("#btn-template-save", Button).press()
        await pilot.pause(0.3)
        assert isinstance(app.screen, AddRecipientTemplateScreen)
        app.screen.query_one("#template-amount", Input).value = "12,50"
        app.screen.query_one("#btn-template-save", Button).press()
        await pilot.pause(0.3)
        assert not isinstance(app.screen, AddRecipientTemplateScreen)
    run(test)
    rows = read_rows(data_dir / "userdata" / "recipientList.csv", RECIPIENT_TEMPLATE_COLUMNS)
    assert (rows[-1]["recipient_name"], rows[-1]["amount"]) == ("Firma", "12.50")


def test_template_without_name_is_rejected(data_dir):
    async def test(app, pilot):
        app.push_screen(AddPayerTemplateScreen())
        await pilot.pause(0.2)
        app.screen.query_one("#btn-template-save", Button).press()
        await pilot.pause(0.3)
        assert isinstance(app.screen, AddPayerTemplateScreen)
    run(test)


def test_manage_list_add_and_delete_with_buttons(data_dir):
    async def test(app, pilot):
        app.push_screen(ManageListScreen("payer"))
        await pilot.pause(0.3)
        screen = app.screen
        before = len(screen.entries)
        screen.query_one("#btn-manage-add", Button).press()
        await pilot.pause(0.3)
        assert isinstance(app.screen, AddPayerTemplateScreen)
        app.screen.query_one("#template-payer_name", Input).value = "Neu"
        app.screen.query_one("#btn-template-save", Button).press()
        await pilot.pause(0.5)
        assert app.screen is screen
        assert len(screen.query(ManageEntryItem)) == before + 1
        screen.select_entry(before)
        screen.query_one("#btn-manage-delete", Button).press()
        await pilot.pause(0.3)
        app.screen.query_one("#confirm-yes", Button).press()
        await pilot.pause(0.5)
        assert len(screen.query(ManageEntryItem)) == before
    run(test)
    names = [r["payer_name"] for r in read_rows(data_dir / "userdata" / "payerList.csv",
                                           PAYER_TEMPLATE_COLUMNS)]
    assert "Neu" not in names


@pytest.mark.parametrize("size", [(120, 50), (80, 24), (200, 30)])
def test_whole_bill_form_can_be_reached(data_dir, size):
    """The form used to be cut off at the window height, hiding the payer fields."""
    async def runner():
        app = bill_app.BillApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause(0.1)
            while isinstance(app.screen, SplashScreen):
                app.screen.dismiss()
                await pilot.pause(0.05)
            app.push_screen(NewBillScreen())
            await pilot.pause(0.4)
            form = app.screen.form
            for field in ("w_payer_name", "w_payer_city", "w_payer_country", "w_private_note"):
                widget = getattr(form, field)
                assert widget.region.bottom <= form.region.bottom, field
            save = app.screen.query_one("#btn-form-save", Button)
            assert save.region.y >= form.region.bottom
            scroller = app.screen.query_one("#newbill-scroll")
            scroller.scroll_end(animate=False)
            await pilot.pause(0.2)
            assert save.region.bottom <= scroller.region.bottom
            assert form.w_payer_name.region.height == 3
    asyncio.run(runner())
