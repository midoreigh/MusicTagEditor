# PyInstaller spec: `uv run pyinstaller packaging/rawtag.spec --noconfirm`
# Produces dist/RawTag/ (one-dir) and, on macOS, dist/RawTag.app.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "src"))
from rawtag import __version__  # noqa: E402

ICON = str(ROOT / "packaging" / "icon.png")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "src" / "rawtag" / "resources"), "rawtag/resources")],
    hiddenimports=[],
    excludes=["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDBus", "PySide6.QtOpenGL",
              "PySide6.QtPdf", "PySide6.QtMultimedia", "PySide6.QtWebEngineCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="RawTag" if sys.platform != "linux" else "rawtag",
    console=False,
    icon=ICON,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="RawTag", strip=False, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="RawTag.app",
        icon=ICON,
        bundle_identifier="io.github.rawtag",
        version=__version__,
        info_plist={
            "CFBundleShortVersionString": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Audio file",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": ["public.audio"],
            }],
        },
    )
