# PyInstaller spec: `uv run pyinstaller packaging/mte.spec --noconfirm`
# Produces dist/MusicTagEditor/ (one-dir) and, on macOS, dist/Music Tag Editor.app.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "src"))
from mte import __version__  # noqa: E402

ICON = str(ROOT / "packaging" / "icon.png")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "src" / "mte" / "resources"), "mte/resources")],
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
    name="MusicTagEditor" if sys.platform != "linux" else "mte",
    console=False,
    icon=ICON,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="MusicTagEditor", strip=False, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Music Tag Editor.app",
        icon=ICON,
        bundle_identifier="io.github.midoreigh.mte",
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
