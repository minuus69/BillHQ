"""Swiss QR bill generation (SVG -> PNG) and QR code parsing.

generate_qr_bill() writes userdata/qrbill.svg + userdata/qrbill.png and opens
the PNG in the system image viewer.
parse_qr_code() decodes a QR image (needs pyzbar+Pillow or opencv-python).
parse_swiss_qr_payload() converts an SPC payload into bill fields.
"""
from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
import tempfile


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
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PDF support needs PyMuPDF: pip install PyMuPDF") from exc

    doc = fitz.open(pdf_path)
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

    script_content = '''\
import cv2, sys, time

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False

cap = None
for idx in range(4):
    cap = cv2.VideoCapture(idx)
    if cap.isOpened():
        break
    cap.release()

if cap is None or not cap.isOpened():
    print("ERROR: Could not open any camera", file=sys.stderr)
    sys.exit(2)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

for _ in range(20):
    cap.read()
    time.sleep(0.03)

cv2_detector = cv2.QRCodeDetector()
frame_count = 0

def try_detect(frame):
    """Try multiple detection strategies. Returns SPC payload or None."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Strategy 1: pyzbar on grayscale (best detector)
    if HAS_PYZBAR:
        for r in pyzbar_decode(gray):
            text = r.data.decode("utf-8", "replace")
            if text.startswith("SPC"):
                return text

    # Strategy 2: pyzbar on upscaled
    if HAS_PYZBAR:
        upscaled = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        for r in pyzbar_decode(upscaled):
            text = r.data.decode("utf-8", "replace")
            if text.startswith("SPC"):
                return text

    # Strategy 3: OpenCV detectAndDecodeMulti
    try:
        retval, decoded_info, points, straight = cv2_detector.detectAndDecodeMulti(gray)
        if retval:
            for data in decoded_info:
                if data and data.startswith("SPC"):
                    return data
    except Exception:
        pass

    # Strategy 4: pyzbar on thresholded
    if HAS_PYZBAR:
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for r in pyzbar_decode(binary):
            text = r.data.decode("utf-8", "replace")
            if text.startswith("SPC"):
                return text

    return None

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    found = None

    # Try detection every frame (pyzbar is fast enough)
    if frame_count % 2 == 0:
        found = try_detect(frame)

    if found:
        cv2.putText(frame, "QR BILL DETECTED!", (10, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 0), 3)
        cv2.imshow("BillHQ - QR Scanner", frame)
        cv2.waitKey(700)
        cap.release()
        cv2.destroyAllWindows()
        print(found)
        sys.exit(0)

    cv2.putText(frame, "PRESS ESC TO EXIT", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
    cv2.putText(frame, "Scanning for Swiss QR bill...", (10, 62),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 1)
    cv2.imshow("BillHQ - QR Scanner", frame)

    k = cv2.waitKey(1) & 0xFF
    if k == 27:
        break

cap.release()
cv2.destroyAllWindows()
sys.exit(1)
'''

    try:
        result = subprocess.run(
            [sys.executable, "-c", script_content],
            capture_output=True, text=True, timeout=180,
            env={**os.environ},
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

    currency = (bill.bCurrency or "").strip().upper()
    if currency not in ("CHF", "EUR"):
        raise ValueError(f"Swiss QR bills only support CHF/EUR (bill has {currency!r})")
    if not (bill.cName or "").strip():
        raise ValueError("QR bill needs creditor data (cName ...) - EDIT the bill first")

    try:
        amount = Decimal(str(bill.bAmount).replace("'", "").replace(" ", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount: {bill.bAmount!r}") from exc

    # per spec: ALL SPACES MUST BE REMOVED from account and reference
    account = (bill.bAccount or "").replace(" ", "")
    reference = (bill.bReference or "").replace(" ", "")
    reference_type = "SCOR" if reference.upper().startswith("RF") else "QRR"

    creditor = Creditor(
        name=bill.dName, street=bill.dStreet, building_number=bill.dBuildingNr,
        postal_code=bill.dPostalCode, city=bill.dCity, country=bill.dCountry,
    )
    debtor = UltimateDebtor(
        name=bill.cName, street=bill.cStreet, building_number=bill.cBuildingNr,
        postal_code=bill.cPostalCode, city=bill.cCity, country=bill.cCountry,
    )
    qrbill = QRBill(
        account=account,
        creditor=creditor,
        debtor=debtor,
        amount=amount,
        currency=currency,
        reference_type=reference_type,
        reference=reference,
        additional_information=(bill.note or "")[:140] or None,
    )
    svg = qrbill.generate_svg(language=_qr_language(getattr(settings, "language", "en")))

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

    Mapping: QR Creditor (receives money) -> d* fields (the company)
             QR Ultimate Debtor (pays)    -> c* fields (the user)
    """
    lines = (text or "").replace("\r", "").split("\n")
    if len(lines) < 31 or lines[0].strip() != "SPC":
        raise ValueError("not a Swiss QR bill payload")

    def g(i: int) -> str:
        return lines[i].strip() if i < len(lines) else ""

    return {
        "bAccount": format_iban(g(3)),
        # QR Creditor (lines 4-10) = the company = d* in this app
        "dName": g(5), "dStreet": g(6), "dBuildingNr": g(7),
        "dPostalCode": g(8), "dCity": g(9), "dCountry": g(10),
        "bAmount": g(18), "bCurrency": g(19),
        # QR Ultimate Debtor (lines 20-26) = the user = c* in this app
        "cName": g(21), "cStreet": g(22), "cBuildingNr": g(23),
        "cPostalCode": g(24), "cCity": g(25), "cCountry": g(26),
        "bReference": format_reference(g(28)),
        "note": g(29),
    }
