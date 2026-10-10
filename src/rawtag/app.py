"""GUI entry point."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from pathlib import Path

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import __version__
    from .ui.main_window import MainWindow

    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("RawTag")
    app.setOrganizationName("RawTag")
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
