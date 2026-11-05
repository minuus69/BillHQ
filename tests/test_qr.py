"""QR bills: generating, reading back, and the optional fields."""
from dataclasses import replace

import pytest

from appdata import qr
from appdata.csvparser import REQUIRED_FIELDS, Bill, Settings

REGULAR_IBAN = "CH93 0076 2011 6238 5295 7"
QR_IBAN = "CH44 3199 9123 0008 8901 2"
QR_REF = "21 00000 00003 13947 14300 09017"

BILL = Bill(
    description="Abo", bAmount="79.90", bCurrency="CHF", bAccount=QR_IBAN, bReference=QR_REF,
    dName="Swisscom AG", dStreet="Alte Tiefenaustrasse", dBuildingNr="6",
    dPostalCode="3048", dCity="Worblaufen", dCountry="CH",
    cName="Max Mustermann", cStreet="Musterweg", cBuildingNr="69",
    cPostalCode="8000", cCity="Zürich", cCountry="CH",
)
NO_DEBTOR = {f: "" for f in ("cName", "cStreet", "cBuildingNr", "cPostalCode", "cCity", "cCountry")}


def round_trip(bill, tmp_path):
    png = qr.generate_qr_bill(bill, Settings(), tmp_path, open_viewer=False)
    codes = qr.parse_qr_code(png)
    assert len(codes) == 1
    return qr.parse_swiss_qr_payload(codes[0])


def test_qr_reference_round_trip(tmp_path):
    data = round_trip(BILL, tmp_path)
    assert data["bAccount"] == QR_IBAN
    assert data["bReference"] == QR_REF
    assert data["bAmount"] == "79.90"
    assert data["dName"] == "Swisscom AG"
    assert data["cName"] == "Max Mustermann"


def test_creditor_reference(tmp_path):
    bill = replace(BILL, bAccount=REGULAR_IBAN, bReference="RF18 5390 0754 7034")
    assert round_trip(bill, tmp_path)["bReference"] == "RF18 5390 0754 7034"


def test_no_reference(tmp_path):
    data = round_trip(replace(BILL, bAccount=REGULAR_IBAN, bReference=""), tmp_path)
    assert data["bReference"] == ""


def test_no_debtor(tmp_path):
    data = round_trip(replace(BILL, **NO_DEBTOR), tmp_path)
    assert data["cName"] == ""
    assert data["dName"] == "Swisscom AG"


def test_svg_calc_is_resolved():
    assert qr._resolve_svg_calc('x="calc(52.6mm - 3mm - 0.3mm)"') == 'x="49.3000mm"'


def test_reference_is_not_required_to_save():
    assert "bReference" not in REQUIRED_FIELDS


def test_pdf_scan(tmp_path):
    import pymupdf
    png = qr.generate_qr_bill(BILL, Settings(), tmp_path, open_viewer=False)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, filename=str(png))
    pdf = tmp_path / "bill.pdf"
    doc.save(pdf)
    doc.close()
    assert qr.parse_qr_from_file(str(pdf))["dName"] == "Swisscom AG"


@pytest.mark.parametrize("change, message", [
    ({"bCurrency": "USD"}, "CHF/EUR"),
    ({"bAmount": "1,250"}, "invalid amount"),
])
def test_bad_bills_give_clear_errors(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        qr.generate_qr_bill(replace(BILL, **change), Settings(), tmp_path, open_viewer=False)


def test_non_swiss_payload_is_rejected():
    with pytest.raises(ValueError):
        qr.parse_swiss_qr_payload("https://example.com")
