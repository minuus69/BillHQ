"""Headless UI tests. Each one runs against its own temporary data folder."""
import asyncio

import pytest
from textual.widgets import Input, Select

from ui import app as bill_app
from ui.screens.bills import BillRow, BillsScreen, EditBillScreen
from ui.screens.main_menu import MainMenuScreen
from ui.screens.menus import SplashScreen
from ui.screens.new_bill import NewBillScreen
from ui.screens.scan import ScanBillScreen
from ui.screens.settings import SettingsScreen
from ui.screens.summary import SummaryScreen
from ui.screens.templates import AddCreditorScreen, ManageListScreen, ManageScreen
from appdata.csvparser import (
    CREDITOR_FIELDS, Bill, load_settings, read_rows, save_bills, write_rows,
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
        app.push_screen(ManageListScreen("debitor"))
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
        template = app.screen.query_one("#tpl-debtor", Select)
        template.value = 0
        await pilot.pause(0.2)
        assert app.screen.form.w_description.value == "Steuerrechnung"
        template.clear()
        await pilot.pause(0.2)
    run(test)


def test_untouched_dropdown_saves_as_empty(data_dir):
    async def test(app, pilot):
        app.push_screen(AddCreditorScreen())
        await pilot.pause(0.2)
        app.screen.query_one("#cred-cname", Input).value = "Test"
        app.screen.query_one("#btn-cred-save").press()
        await pilot.pause(0.3)
    run(test)
    rows = read_rows(data_dir / "userdata" / "creditorList.csv", CREDITOR_FIELDS)
    assert rows[-1]["cName"] == "Test"
    assert rows[-1]["cCountry"] == ""


def test_old_select_null_cells_are_cleaned_on_load(tmp_path):
    path = tmp_path / "creditorList.csv"
    write_rows(path, CREDITOR_FIELDS, [{"cName": "Old", "cCountry": "Select.NULL"}])
    assert read_rows(path, CREDITOR_FIELDS)[0]["cCountry"] == ""


def test_editing_keeps_unusual_and_empty_values(data_dir):
    bill = Bill(description="x", bAmount="1.00", bCurrency="GBP", bAccount="a",
                dName="n", dPostalCode="1", dCity="c", dCountry="EE", cCountry="")

    async def test(app, pilot):
        app.push_screen(EditBillScreen(bill, 0))
        await pilot.pause(0.2)
        saved, error = app.screen.form.collect()
        assert error is None
        assert (saved.bCurrency, saved.dCountry, saved.cCountry) == ("GBP", "EE", "")
    run(test)


@pytest.mark.parametrize("name", ["Foo [/bar] AG", "Foo [bar] AG"])
def test_brackets_in_names_render(data_dir, name):
    async def test(app, pilot):
        app.core.creditors.append({"cName": name, "cCountry": "CH"})
        app.core.debitors.append({"description": name, "dName": name})
        app.core.bills.append(Bill(description=name, dueDate="2030-01-01", bAmount="1",
                                   bCurrency="CHF", dName=name, cName=name))
        for screen in (ManageListScreen("creditor"), NewBillScreen(),
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
    save_bills(userdata / "data.csv", [Bill(description="a", dueDate="2030-01-01",
                                            bAmount="1.00", bCurrency="CHF")])

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
    run(test)
