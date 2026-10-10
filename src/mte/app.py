"""GUI entry point."""

from __future__ import annotations

import sys

APP_NAME = "Music Tag Editor"


def _set_macos_app_name(name: str) -> None:
    """Name shown in the macOS menu bar / app menu ("About …", "Quit …").

    Packaged builds get it from the .app's Info.plist, but when running from
    source the process is the Python interpreter, so macOS shows "python".
    Patching CFBundleName in the main bundle's info dictionary before Qt
    creates NSApplication fixes that. Uses the Objective-C runtime via ctypes
    to avoid a pyobjc dependency; any failure just leaves the default name.
    """
    if sys.platform != "darwin":
        return
    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary(ctypes.util.find_library("Foundation"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.restype = ctypes.c_void_p
        send_addr = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        vp = ctypes.c_void_p

        def sender(*argtypes):  # one typed objc_msgSend per call signature
            return ctypes.CFUNCTYPE(vp, vp, vp, *argtypes)(send_addr)

        send0, send1, send2 = sender(), sender(vp), sender(vp, vp)
        send_str = sender(ctypes.c_char_p)
        sel, cls = objc.sel_registerName, objc.objc_getClass

        def nsstring(text: str):
            return send_str(cls(b"NSString"), sel(b"stringWithUTF8String:"), text.encode())

        bundle = send0(cls(b"NSBundle"), sel(b"mainBundle"))
        for getter in (b"localizedInfoDictionary", b"infoDictionary"):
            info = send0(bundle, sel(getter))
            if info and send1(info, sel(b"respondsToSelector:"), sel(b"setObject:forKey:")):
                send2(info, sel(b"setObject:forKey:"), nsstring(name), nsstring("CFBundleName"))
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    from pathlib import Path

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import __version__
    from .ui.main_window import MainWindow

    argv = sys.argv if argv is None else argv
    _set_macos_app_name(APP_NAME)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(__version__)
    icon = Path(__file__).with_name("resources") / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    win = MainWindow()
    win.show()
    if "--smoke-test" in argv:  # used by CI to check a packaged build starts
        QTimer.singleShot(1500, app.quit)
    paths = [a for a in argv[1:] if not a.startswith("-")]
    if paths:
        win.load_paths(paths)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
