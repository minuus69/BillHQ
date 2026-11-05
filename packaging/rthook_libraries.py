"""pyzbar and cairocffi look their libraries up through the system, which can't
see the ones inside the executable and might not have them at all."""
import ctypes.util
import os
import sys

_BUNDLED = {"zbar": "libzbar.so.0", "cairo": "libcairo.so.2", "cairo-2": "libcairo.so.2"}
_find_library = ctypes.util.find_library


def _find_bundled_first(name):
    path = os.path.join(sys._MEIPASS, _BUNDLED.get(name, ""))
    return path if name in _BUNDLED and os.path.exists(path) else _find_library(name)


ctypes.util.find_library = _find_bundled_first
