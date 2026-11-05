"""Swiss QR bill generation (SVG -> PNG) and QR code parsing.

generate_qr_bill() writes userdata/qrbill.svg + userdata/qrbill.png and opens
the PNG in the system image viewer.
parse_qr_code() decodes a QR image (needs pyzbar+Pillow or opencv-python).
parse_swiss_qr_payload() converts an SPC payload into bill fields.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
import tempfile

from appdata.csvparser import parse_amount


# --------------------------------------------------------------------------- #
# File dialog, PDF support, and webcam scanning
# --------------------------------------------------------------------------- #
def open_file_dialog() -> str | None:
    """Open a native file picker. Returns the selected path or None."""
    # Try zenity (GNOME/GTK)
    try:
        r = subprocess.run(
            ["zenity", "--file-selection", "--title=Select QR bill",
             "--file-filter=QR Bills | *.png *.jpg *.jpeg *.bmp *.pdf",
             "--file-filter=All files | *"],
            capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # Try kdialog (KDE)
    try:
        r = subprocess.run(
            ["kdialog", "--getopenfilename", ".",
             "*.png *.jpg *.jpeg *.bmp *.pdf | QR Bills"],
            capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # Fallback: tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Select QR bill",
            filetypes=[("QR Bills", "*.png *.jpg *.jpeg *.bmp *.pdf"),
                       ("All files", "*.*")])
        root.destroy()
        return path if path else None
    except Exception as exc:
        raise RuntimeError("No file dialog available (install zenity)") from exc


def parse_qr_from_file(file_path: str) -> dict:
    """Parse a Swiss QR bill from an image or PDF. Returns bill field dict."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return _parse_qr_from_pdf(file_path)
    codes = parse_qr_code(file_path)
    if not codes:
        raise ValueError("No QR code found in image")
    return parse_swiss_qr_payload(codes[0])


def _parse_qr_from_pdf(pdf_path: str) -> dict:
    """Render each PDF page to an image and look for a Swiss QR bill."""
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("PDF support needs PyMuPDF: pip install PyMuPDF") from exc

    doc = pymupdf.open(pdf_path)
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                img_path = tmp.name
            pix.save(img_path)
            try:
                for code in parse_qr_code(img_path):
                    try:
                        return parse_swiss_qr_payload(code)
                    except ValueError:
                        continue
            finally:
                if os.path.exists(img_path):
                    os.remove(img_path)
    finally:
        doc.close()
    raise ValueError("No Swiss QR bill found in PDF")


def scan_qr_webcam() -> dict | None:
    """Open webcam with live QR scanning. Auto-detects Swiss QR bills."""

    try:
        result = subprocess.run(
            [sys.executable, "-m", "appdata.qr_webcam"],
            capture_output=True, text=True, timeout=180,
            cwd=Path(__file__).resolve().parent.parent,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Webcam scan timed out")

    if result.returncode == 2:
        raise RuntimeError("No camera found. Check that your webcam is connected.")

    if result.returncode != 0 or not result.stdout.strip():
        return None  # ESC pressed

    payload = result.stdout.strip()
    return parse_swiss_qr_payload(payload)

def _qr_language(app_language: str) -> str:
    """chqr supports de/fr/it/en on the payment part."""
    return {"de": "de", "ch": "de", "fr": "fr", "it": "it"}.get(
        (app_language or "").lower(), "en")


def open_in_viewer(path: Path) -> bool:
    """Open an image in the default image viewer (non-blocking)."""
    target = str(path)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
        elif sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", target],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def _resolve_svg_calc(svg: str) -> str:
    """Turn calc(52.6mm - 3mm - 0.3mm) into 49.3mm.

    chqr uses these for the corner marks of empty address boxes (a bill with no
    payer), and cairosvg can't read calc().
    """
    def resolve(match: re.Match) -> str:
        first, *rest = re.findall(r"[\d.]+", match.group(1))
        return f"{float(first) - sum(map(float, rest)):.4f}mm"

    return re.sub(r"calc\(([\d.]+mm(?: - [\d.]+mm)+)\)", resolve, svg)


def generate_qr_bill(bill, settings, out_dir: Path, open_viewer: bool = True) -> Path:
    """Build the Swiss QR bill for `bill`, write SVG+PNG into out_dir, open the
    PNG in an image viewer and return the PNG path."""
    try:
        from chqr import Creditor, QRBill, UltimateDebtor
    except ImportError as exc:
        raise RuntimeError("package 'chqr' is missing - run: pip install chqr") from exc
    try:
        import cairosvg
    except ImportError as exc:
        raise RuntimeError("package 'cairosvg' is missing - run: pip install cairosvg") from exc

    currency = (bill.currency or "").strip().upper()
    if currency not in ("CHF", "EUR"):
        raise ValueError(f"Swiss QR bills only support CHF/EUR (bill has {currency!r})")

    amount = parse_amount(bill.amount)

    # per spec: ALL SPACES MUST BE REMOVED from account and reference
    account = (bill.account or "").replace(" ", "")
    reference = (bill.reference or "").replace(" ", "")
    if not reference:
        reference_type = "NON"
    elif reference.upper().startswith("RF"):
        reference_type = "SCOR"
    else:
        reference_type = "QRR"

    creditor = Creditor(
        name=bill.recipient_name, street=bill.recipient_street, building_number=bill.recipient_building_nr,
        postal_code=bill.recipient_postal_code, city=bill.recipient_city, country=bill.recipient_country,
    )
    # the person paying is optional on a QR bill
    debtor = None
    if (bill.payer_name or "").strip():
        debtor = UltimateDebtor(
            name=bill.payer_name, street=bill.payer_street, building_number=bill.payer_building_nr,
            postal_code=bill.payer_postal_code, city=bill.payer_city, country=bill.payer_country,
        )
    qrbill = QRBill(
        account=account,
        creditor=creditor,
        debtor=debtor,
        amount=amount,
        currency=currency,
        reference_type=reference_type,
        reference=reference or None,
        additional_information=(bill.note or "")[:140] or None,
    )
    svg = _resolve_svg_calc(
        qrbill.generate_svg(language=_qr_language(getattr(settings, "language", "en"))))

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / "qrbill.svg"
    png_path = out_dir / "qrbill.png"
    svg_path.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path), dpi=300)

    if open_viewer:
        open_in_viewer(png_path)
    return png_path


def parse_qr_code(image_path) -> list[str]:
    """Decode QR code(s) from an image. Tries multiple approaches."""
    image_path = str(image_path)
    results = []

    # Attempt 1: pyzbar on original
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode
        results = [item.data.decode("utf-8", "replace")
                   for item in decode(Image.open(image_path))]
        if results:
            return results
    except Exception:
        pass

    # Attempt 2: OpenCV on original
    try:
        import cv2
        img = cv2.imread(image_path)
        if img is not None:
            data, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
            if data:
                return [data]
    except Exception:
        pass

    # Attempt 3: OpenCV with preprocessing (grayscale + upscale + threshold)
    try:
        import cv2
        img = cv2.imread(image_path)
        if img is not None:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Upscale 2x for better detection
            gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            # Sharpen
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
            data, _, _ = cv2.QRCodeDetector().detectAndDecode(gray)
            if data:
                return [data]
            # Try binary threshold
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            data, _, _ = cv2.QRCodeDetector().detectAndDecode(binary)
            if data:
                return [data]
    except Exception:
        pass

    # Attempt 4: pyzbar with preprocessing
    try:
        import cv2
        from PIL import Image
        from pyzbar.pyzbar import decode
        img = cv2.imread(image_path)
        if img is not None:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            pil_img = Image.fromarray(binary)
            results = [item.data.decode("utf-8", "replace") for item in decode(pil_img)]
            if results:
                return results
    except Exception:
        pass

    return []


def format_iban(iban: str) -> str:
    """CH4431999123000889012 -> CH44 3199 9123 0008 8901 2"""
    iban = iban.replace(" ", "")
    return " ".join(iban[i:i+4] for i in range(0, len(iban), 4))


def format_reference(ref: str) -> str:
    """Format QR reference with proper spacing."""
    ref = ref.replace(" ", "")
    if not ref:
        return ""
    if ref.upper().startswith("RF"):
        # SCOR/ISO 11649: groups of 4
        return " ".join(ref[i:i+4] for i in range(0, len(ref), 4))
    # QRR: first 2 digits, then groups of 5
    parts = [ref[:2]]
    for i in range(2, len(ref), 5):
        parts.append(ref[i:i+5])
    return " ".join(parts)


def parse_swiss_qr_payload(text: str) -> dict:
    """Parse a Swiss QR bill payload (SPC) into bill field names.

    The QR standard's creditor is our recipient, its ultimate debtor is our payer.
    """
    lines = (text or "").replace("\r", "").split("\n")
    if len(lines) < 31 or lines[0].strip() != "SPC":
        raise ValueError("not a Swiss QR bill payload")

    def g(i: int) -> str:
        return lines[i].strip() if i < len(lines) else ""

    return {
        "account": format_iban(g(3)),
        # QR creditor (lines 4-10)
        "recipient_name": g(5), "recipient_street": g(6), "recipient_building_nr": g(7),
        "recipient_postal_code": g(8), "recipient_city": g(9), "recipient_country": g(10),
        "amount": g(18), "currency": g(19),
        # QR ultimate debtor (lines 20-26)
        "payer_name": g(21), "payer_street": g(22), "payer_building_nr": g(23),
        "payer_postal_code": g(24), "payer_city": g(25), "payer_country": g(26),
        "reference": format_reference(g(28)),
        "note": g(29),
    }
