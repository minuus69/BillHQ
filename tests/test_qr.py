"""QR bills: generating, reading back, and the optional fields."""
from dataclasses import replace

import pytest

from appdata import qr
from appdata.csvparser import REQUIRED_FIELDS, Bill, Settings

REGULAR_IBAN = "CH93 0076 2011 6238 5295 7"
QR_IBAN = "CH44 3199 9123 0008 8901 2"
QR_REF = "21 00000 00003 13947 14300 09017"

BILL = Bill(
    description="Abo", amount="79.90", currency="CHF", account=QR_IBAN, reference=QR_REF,
    payee_name="Swisscom AG", payee_street="Alte Tiefenaustrasse", payee_building_nr="6",
    payee_postal_code="3048", payee_city="Worblaufen", payee_country="CH",
    payer_name="Max Mustermann", payer_street="Musterweg", payer_building_nr="69",
    payer_postal_code="8000", payer_city="Zürich", payer_country="CH",
)
NO_DEBTOR = {f: "" for f in ("payer_name", "payer_street", "payer_building_nr", "payer_postal_code", "payer_city", "payer_country")}


def round_trip(bill, tmp_path):
    png = qr.generate_qr_bill(bill, Settings(), tmp_path, open_viewer=False)
    codes = qr.parse_qr_code(png)
    assert len(codes) == 1
    return qr.parse_swiss_qr_payload(codes[0])


def test_qr_reference_round_trip(tmp_path):
    data = round_trip(BILL, tmp_path)
    assert data["account"] == QR_IBAN
    assert data["reference"] == QR_REF
    assert data["amount"] == "79.90"
    assert data["payee_name"] == "Swisscom AG"
    assert data["payer_name"] == "Max Mustermann"


def test_creditor_reference(tmp_path):
    bill = replace(BILL, account=REGULAR_IBAN, reference="RF18 5390 0754 7034")
    assert round_trip(bill, tmp_path)["reference"] == "RF18 5390 0754 7034"


def test_no_reference(tmp_path):
    data = round_trip(replace(BILL, account=REGULAR_IBAN, reference=""), tmp_path)
    assert data["reference"] == ""


def test_no_debtor(tmp_path):
    data = round_trip(replace(BILL, **NO_DEBTOR), tmp_path)
    assert data["payer_name"] == ""
    assert data["payee_name"] == "Swisscom AG"


def test_svg_calc_is_resolved():
    assert qr._resolve_svg_calc('x="calc(52.6mm - 3mm - 0.3mm)"') == 'x="49.3000mm"'


def test_reference_is_not_required_to_save():
    assert "reference" not in REQUIRED_FIELDS


def test_pdf_scan(tmp_path):
    import pymupdf
    png = qr.generate_qr_bill(BILL, Settings(), tmp_path, open_viewer=False)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, filename=str(png))
    pdf = tmp_path / "bill.pdf"
    doc.save(pdf)
    doc.close()
    assert qr.parse_qr_from_file(str(pdf))["payee_name"] == "Swisscom AG"


@pytest.mark.parametrize("change, message", [
    ({"currency": "USD"}, "CHF/EUR"),
    ({"amount": "1,250"}, "invalid amount"),
])
def test_bad_bills_give_clear_errors(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        qr.generate_qr_bill(replace(BILL, **change), Settings(), tmp_path, open_viewer=False)


def test_non_swiss_payload_is_rejected():
    with pytest.raises(ValueError):
        qr.parse_swiss_qr_payload("https://example.com")
