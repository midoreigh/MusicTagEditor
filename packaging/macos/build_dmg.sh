#!/usr/bin/env bash
# Wrap dist/RawTag.app into a compressed DMG (uses only built-in hdiutil).
# Usage: packaging/macos/build_dmg.sh VERSION
set -euo pipefail
VERSION="${1:?version}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ARCH="$(uname -m)"   # arm64 / x86_64
STAGE="$ROOT/build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$ROOT/dist/RawTag.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
# ad-hoc signature so Apple Silicon will run it (not notarized)
codesign --force --deep --sign - "$STAGE/RawTag.app"
OUT="$ROOT/dist/RawTag-${VERSION}-macos-${ARCH}.dmg"
rm -f "$OUT"
hdiutil create -volname "RawTag" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
echo "Built: $OUT"
