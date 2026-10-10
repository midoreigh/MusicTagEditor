#!/usr/bin/env bash
# Wrap dist/Music Tag Editor.app into a compressed DMG (uses only built-in hdiutil).
# Usage: packaging/macos/build_dmg.sh VERSION
set -euo pipefail
VERSION="${1:?version}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ARCH="$(uname -m)"   # arm64 / x86_64
STAGE="$ROOT/build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$ROOT/dist/Music Tag Editor.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
# ad-hoc signature so Apple Silicon will run it (not notarized)
codesign --force --deep --sign - "$STAGE/Music Tag Editor.app"
OUT="$ROOT/dist/MusicTagEditor-${VERSION}-macos-${ARCH}.dmg"
rm -f "$OUT"
hdiutil create -volname "Music Tag Editor" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
echo "Built: $OUT"
