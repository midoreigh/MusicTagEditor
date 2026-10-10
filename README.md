# Music Tag Editor (mte)

A cross-platform (macOS, Linux, Windows) desktop editor that shows and edits **every raw tag**
stored in audio files. Unlike Picard, nothing is mapped or hidden: podcast frames, `PRIV`,
`TXXX`, iTunes freeform atoms, and frames mutagen can't even parse all show up.

| Tag system | Files | What you see |
|---|---|---|
| ID3v2.3 / v2.4 | MP3, WAV, AIFF, DSF, TTA | Every frame exactly as stored, with no v2.3→v2.4 translation. Full frame-level fields: encoding, language, description, owner, picture type, MIME, raw data. Unparseable frames are shown read-only and survive saves. |
| ID3v1 / v1.1 | MP3, TTA | Shown separately, not merged into v2. Mutagen's v1 rewrite is undone, so v1 only changes when you edit it. |
| APEv2 | MP3, APE, WavPack, Musepack, OptimFROG, TAK | Every item: text (multi-value), binary, external. |
| MP4 atoms | M4A, M4B, MP4 | `©nam`…, `pcst`/`catg`/`purl`/`egid`, `----:mean:name` freeform, `covr` images, plus unparseable atoms. |
| Vorbis comments | FLAC, Ogg Vorbis/Opus/FLAC/Speex | Original key case and order, multi-values, vendor string, `METADATA_BLOCK_PICTURE`. |
| FLAC pictures | FLAC | Picture blocks with type, MIME, description, size and depth. |
| ASF | WMA | Attributes with their value type. |

## Features
- Open a folder (recursive) or files, or drag and drop them in. Loading runs in the background.
- Multi-select files to see the union of their tags. Rows show `<n different values>` and `[in n/m files]`.
- Edit inline (F2 / click) or in the full frame editor (double-click / Enter / Ctrl+E). In batch mode only the fields you change are written to each file.
- Add any frame/atom/field (Ctrl+T), delete tags (Del), and **Find & Remove** tags whose key or value contains some text (Ctrl+Shift+F). Find & Remove is a GUI version of `clean_audio_tags.py`.
- Nothing touches disk until **Save** (Ctrl+S). Modified rows and files are highlighted, and Revert discards changes. Failed files keep their pending edits.
- Picture and binary data: preview, hex dump, import and export.

## Run from source
Requires [uv](https://docs.astral.sh/uv/).
```bash
uv sync
uv run mte                 # GUI (optionally: uv run mte /path/to/music)
uv run mte-cli dump FILE_OR_FOLDER
uv run mte-cli clean FOLDER songs.pk --dry-run
uv run pytest
```
Ubuntu needs Qt's xcb libraries: `sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1`.

## Installers
`.github/workflows/build.yml` tests on all three OSes and builds:
- **macOS**: `MusicTagEditor-x.y.z-macos-{arm64,x86_64}.dmg`. It's ad-hoc signed, not notarized, so the first launch needs right-click → Open, or `xattr -dr com.apple.quarantine "/Applications/Music Tag Editor.app"`.
- **Windows**: an Inno Setup installer plus a portable zip.
- **Linux**: an AppImage and a `.deb` (installs to `/opt/mte`, launched with `mte`), built on Ubuntu 22.04.

Push a `v*` tag to publish them as a GitHub release. To build locally:
```bash
uv run pyinstaller packaging/mte.spec --noconfirm
packaging/macos/build_dmg.sh 0.1.0       # macOS
packaging/linux/build_linux.sh 0.1.0     # Linux (PYTHON="uv run python")
```

## Layout
```
src/mte/core/      Qt-free model, format adapters (formats/), session, batch save, cleaner
src/mte/ui/        PySide6 main window, tag table, file list, editors, dialogs
src/mte/cli.py     dump / clean command line
packaging/         PyInstaller spec, Inno Setup, AppImage/.deb, DMG scripts, icon
tests/             round-trip tests per format + headless GUI smoke tests
```

## Known limitations (v1)
- ID3v2.2 files are converted to v2.4 when saved, because v2.2 can't be written.
- Complex ID3 structures (CHAP/CTOC sub-frames, SYLT, RVA2, ETCO…) are shown read-only, but they are preserved and can be deleted.
- Raw ADTS `.aac` and Matroska/WebM aren't supported. WMA isn't covered by automated tests yet (there's no fixture).
- No online lookup (MusicBrainz etc.) yet.
