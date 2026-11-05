"""Live webcam QR scanner, run as its own process by qr.scan_qr_webcam().

It has its own process because OpenCV's windows can't share a terminal with the
TUI. It prints the Swiss QR payload and exits 0, exits 1 when closed with Esc,
and exits 2 when there's no camera.
"""
import sys
import time

import cv2

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False


def try_detect(frame, detector):
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
        retval, decoded_info, points, straight = detector.detectAndDecodeMulti(gray)
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


def main() -> None:
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

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        found = None

        # Try detection every frame (pyzbar is fast enough)
        if frame_count % 2 == 0:
            found = try_detect(frame, cv2_detector)

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


if __name__ == "__main__":
    main()
