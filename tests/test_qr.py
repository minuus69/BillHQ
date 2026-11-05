"""QR bills: generating, reading back, and the optional fields."""
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from appdata import qr, selfcheck
from appdata.csvparser import REQUIRED_FIELDS, Bill, Settings

REGULAR_IBAN = "CH93 0076 2011 6238 5295 7"
QR_IBAN = "CH44 3199 9123 0008 8901 2"
QR_REF = "21 00000 00003 13947 14300 09017"

BILL = Bill(
    description="Abo", amount="79.90", currency="CHF", account=QR_IBAN, reference=QR_REF,
    recipient_name="Swisscom AG", recipient_street="Alte Tiefenaustrasse", recipient_building_nr="6",
    recipient_postal_code="3048", recipient_city="Worblaufen", recipient_country="CH",
    payer_name="Max Mustermann", payer_street="Musterweg", payer_building_nr="69",
    payer_postal_code="8000", payer_city="Zürich", payer_country="CH",
)
NO_PAYER = {f: "" for f in ("payer_name", "payer_street", "payer_building_nr", "payer_postal_code", "payer_city", "payer_country")}


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
    assert data["recipient_name"] == "Swisscom AG"
    assert data["payer_name"] == "Max Mustermann"


def test_creditor_reference(tmp_path):
    bill = replace(BILL, account=REGULAR_IBAN, reference="RF18 5390 0754 7034")
    assert round_trip(bill, tmp_path)["reference"] == "RF18 5390 0754 7034"


def test_no_reference(tmp_path):
    data = round_trip(replace(BILL, account=REGULAR_IBAN, reference=""), tmp_path)
    assert data["reference"] == ""


def test_no_payer(tmp_path):
    data = round_trip(replace(BILL, **NO_PAYER), tmp_path)
    assert data["payer_name"] == ""
    assert data["recipient_name"] == "Swisscom AG"


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
    assert qr.parse_qr_from_file(str(pdf))["recipient_name"] == "Swisscom AG"


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


PAYLOAD = "\n".join(["SPC", "0200", "1", "CH9300762011623852957", "S", "Firma", "", "", "8000",
                     "Zürich", "CH", "", "", "", "", "", "", "", "12.50", "CHF", "", "", "", "",
                     "", "", "", "NON", "", "", "EPD"])


def fake_run(monkeypatch, returncode, stdout=""):
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(qr.subprocess, "run", run)
    return calls


def test_webcam_scan_parses_found_payload(monkeypatch):
    calls = fake_run(monkeypatch, 0, PAYLOAD)
    assert qr.scan_qr_webcam()["recipient_name"] == "Firma"
    cmd, kwargs = calls[0]
    assert cmd[1:] == ["-m", "appdata.qr_webcam"]
    assert (Path(kwargs["cwd"]) / "appdata" / "qr_webcam.py").exists()


def test_webcam_scan_cancelled(monkeypatch):
    fake_run(monkeypatch, 1)
    assert qr.scan_qr_webcam() is None


def test_webcam_scan_no_camera(monkeypatch):
    fake_run(monkeypatch, 2)
    with pytest.raises(RuntimeError, match="camera"):
        qr.scan_qr_webcam()


def test_webcam_module_reports_missing_camera(monkeypatch):
    """Without touching a real camera: every device fails to open, so it exits 2."""
    from appdata import qr_webcam

    class NoCamera:
        def __init__(self, index):
            pass

        def isOpened(self):
            return False

        def release(self):
            pass

    monkeypatch.setattr(qr_webcam.cv2, "VideoCapture", NoCamera)
    with pytest.raises(SystemExit) as exit_info:
        qr_webcam.main()
    assert exit_info.value.code == 2


def test_webcam_module_loads_as_its_own_process():
    root = Path(qr.__file__).resolve().parent.parent
    subprocess.run([sys.executable, "-c", "import appdata.qr_webcam"], cwd=root, check=True)


def test_webcam_detector_finds_a_generated_bill(tmp_path):
    import cv2
    from appdata import qr_webcam
    png = qr.generate_qr_bill(BILL, Settings(), tmp_path, open_viewer=False)
    found = qr_webcam.try_detect(cv2.imread(str(png)), cv2.QRCodeDetector())
    assert found.startswith("SPC")


# ---- the single-file build ----
def test_webcam_runs_through_python_normally():
    assert qr._webcam_command() == [sys.executable, "-m", "appdata.qr_webcam"]


def test_webcam_restarts_the_program_in_a_build(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/BillHQ")
    assert qr._webcam_command() == ["/opt/BillHQ", "--webcam-scan"]


def test_other_programs_dont_get_the_bundled_libraries(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIxxx")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    assert "LD_LIBRARY_PATH" not in qr._system_env()
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib")
    assert qr._system_env()["LD_LIBRARY_PATH"] == "/usr/local/lib"


def test_self_check_passes(tmp_path):
    selfcheck.main(str(tmp_path))


def test_library_messages_stay_off_the_terminal(capfd):
    with qr._silence_libraries():
        os.write(2, b"Fontconfig warning")
    os.write(2, b"after")
    assert capfd.readouterr().err == "after"


def test_silencing_restores_the_terminal_after_an_error(capfd):
    with pytest.raises(ValueError):
        with qr._silence_libraries():
            raise ValueError
    os.write(2, b"after")
    assert capfd.readouterr().err == "after"
