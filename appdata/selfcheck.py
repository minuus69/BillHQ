"""Checks that a build has everything it needs: python app.py --self-check <folder>.

Makes a real QR bill from the bundled templates into the folder and reads it back.
"""
from __future__ import annotations

from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def main(out_dir: str) -> None:
    import cv2
    import pymupdf
    from pyzbar.pyzbar import decode

    from appdata import qr
    from appdata.csvparser import Settings, load_bills
    from appdata.languages import tr
    from ui import app as ui_app

    bill = load_bills(TEMPLATES / "data.csv")[0]
    png = qr.generate_qr_bill(bill, Settings(), Path(out_dir), open_viewer=False)
    data = qr.parse_swiss_qr_payload(qr.parse_qr_code(png)[0])
    assert data["recipient_name"] == bill.recipient_name, "QR bill doesn't read back"
    assert cv2.imread(str(png)) is not None, "OpenCV can't read the QR bill"
    decode(cv2.imread(str(png)))             # importing and calling it proves zbar loaded
    assert tr("app_title") != "app_title", "translations are missing"
    assert Path(ui_app.__file__).with_name(ui_app.BillApp.CSS_PATH).is_file(), "styles are missing"

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_image(page.rect, filename=str(png))
    pdf.save(png.with_suffix(".pdf"))
    data = qr.parse_qr_from_file(str(png.with_suffix(".pdf")))
    assert data["recipient_name"] == bill.recipient_name, "QR bill in a PDF doesn't read back"
    print("self-check ok")
