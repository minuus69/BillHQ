# Builds the single-file BillHQ executable: see packaging/build_linux.sh
import re
import subprocess
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent


def system_library(soname):
    """Libraries the Python packages only find while running, so PyInstaller can't see them."""
    found = re.search(rf"{re.escape(soname)} .*=> (\S+)", subprocess.check_output(["ldconfig", "-p"], text=True))
    if not found:
        raise SystemExit(f"{soname} is missing on the build machine")
    return found.group(1), "."


a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=[system_library("libzbar.so.0"), system_library("libcairo.so.2")],
    datas=[
        (str(ROOT / "templates"), "templates"),
        (str(ROOT / "appdata" / "languages.csv"), "appdata"),
        (str(ROOT / "ui" / "styles.tcss"), "ui"),
        *collect_data_files("cairosvg"),
        *collect_data_files("cairocffi"),
        *collect_data_files("textual"),
    ],
    # Textual and Rich import parts of themselves by name while running.
    hiddenimports=[*collect_submodules("textual"), *collect_submodules("rich")],
    runtime_hooks=[str(ROOT / "packaging" / "rthook_libraries.py")],
    excludes=["tkinter", "pytest", "PyInstaller"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="BillHQ", console=True, upx=False)
