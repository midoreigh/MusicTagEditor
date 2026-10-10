#!/usr/bin/env bash
# Package dist/MusicTagEditor (PyInstaller one-dir) as an AppImage and a .deb.
# Usage: packaging/linux/build_linux.sh VERSION
set -euo pipefail
VERSION="${1:?version}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$ROOT/dist"
HERE="$ROOT/packaging/linux"
ARCH="$(uname -m)"          # x86_64 / aarch64
DEB_ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"

# ---------------- AppImage
APPDIR="$ROOT/build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a "$DIST/MusicTagEditor" "$APPDIR/usr/lib/mte"
cp "$HERE/mte.desktop" "$APPDIR/mte.desktop"
cp "$HERE/mte.desktop" "$APPDIR/usr/share/applications/"
${PYTHON:-python3} - "$ROOT/packaging/icon.png" "$APPDIR/mte.png" <<'PY'
import sys
from PIL import Image
Image.open(sys.argv[1]).resize((512, 512)).save(sys.argv[2])
PY
cp "$APPDIR/mte.png" "$APPDIR/usr/share/icons/hicolor/512x512/apps/mte.png"
cat > "$APPDIR/AppRun" <<'SH'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/mte/mte" "$@"
SH
chmod +x "$APPDIR/AppRun"
TOOL="$ROOT/build/appimagetool"
if [ ! -x "$TOOL" ]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
  chmod +x "$TOOL"
fi
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$DIST/MusicTagEditor-${VERSION}-linux-${ARCH}.AppImage"

# ---------------- .deb (installs to /opt/mte)
PKG="$ROOT/build/deb/mte_${VERSION}_${DEB_ARCH}"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/512x512/apps"
cp -a "$DIST/MusicTagEditor" "$PKG/opt/mte"
ln -s /opt/mte/mte "$PKG/usr/bin/mte"
cp "$HERE/mte.desktop" "$PKG/usr/share/applications/"
cp "$APPDIR/mte.png" "$PKG/usr/share/icons/hicolor/512x512/apps/mte.png"
cat > "$PKG/DEBIAN/control" <<CTRL
Package: mte
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${DEB_ARCH}
Depends: libxcb-cursor0, libxkbcommon-x11-0, libegl1, libfontconfig1, libdbus-1-3
Maintainer: Mido Reigh <midoreigh@gmail.com>
Description: View and edit every raw tag in audio files
 Shows all ID3v2/ID3v1 frames, MP4 atoms, Vorbis comments, FLAC pictures,
 APEv2 items and ASF attributes, including podcast and private frames.
CTRL
dpkg-deb --build --root-owner-group "$PKG" "$DIST/mte_${VERSION}_${DEB_ARCH}.deb"
echo "Built: $(ls "$DIST"/*.AppImage "$DIST"/*.deb)"
