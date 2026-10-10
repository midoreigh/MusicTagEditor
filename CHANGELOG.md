# Changelog

All notable changes to Music Tag Editor are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-10-10

### Fixed
- An edit that can't be written (for example an ID3v1 album longer than 30 bytes)
  is now rejected as soon as you make it, with an explanation. It used to be
  accepted and then fail on every Save, even after the tag was deleted or edited
  back.
- Save now writes only the difference between the file and your edits, not every
  intermediate edit you made. Deleting or reverting a change really undoes it.
- The Linux `.deb` now installs with plain `sudo dpkg -i`. It used to list libraries
  that are already bundled inside it (such as `libxcb-cursor0`) as dependencies, so
  `dpkg -i` failed on systems without them. It now declares only the system
  libraries (and font configuration) it really needs, which every desktop
  Ubuntu/Debian already has.
- Every release build now installs the `.deb` on a clean Ubuntu 22.04 to check this.

## [0.1.0] - 2026-10-10

First public release.

### Added
- See and edit **every raw tag**, including the podcast, private and custom tags other
  editors hide: ID3v2.3/2.4 frames exactly as stored (unknown frames are kept), ID3v1
  shown separately, APEv2, MP4/iTunes atoms (freeform `----` atoms too), Vorbis
  comments, FLAC pictures and ASF/WMA attributes.
- Full frame-level editor: encoding, language, description, multiple values, picture
  type, and binary/image data with preview, hex view, import and export.
- Folder tree: selecting a folder edits all files below it at once. Tags that differ
  between files, or are missing from some, are marked.
- Nothing is written until **Save**: changed rows are highlighted, Revert discards
  edits, and files that fail to save keep their pending edits.
- In the tag editor, **Previous/Next tag** and **Previous/Next file** buttons. Next
  file keeps the same tag, so you can edit the artist of each file in turn.
- **Find & Remove**: remove every tag whose key or value contains some text (for
  example a website watermark), across many files.
- **File naming** like Picard: a Picard-compatible script (`%artist%`, `$if`, `$num`,
  …) renames and optionally moves files when saving, with a live before/after preview.
- **Rename Folder…** from the tree. Loaded files inside it keep their unsaved edits.
- `mte-cli dump` and `mte-cli clean` for the command line.
- Installers: macOS DMG (Apple Silicon and Intel), Windows installer and portable
  zip, Linux AppImage and `.deb`.

### Known limitations
- The installers aren't code-signed. macOS asks you to confirm the first launch
  (right-click → Open), and Windows SmartScreen may warn.
- ID3v2.2 tags are converted to v2.4 when saved.
- Complex ID3 frames (chapters, synced lyrics, RVA2, …) are read-only, but they are
  kept and can be deleted.

[Unreleased]: https://github.com/midoreigh/MusicTagEditor/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/midoreigh/MusicTagEditor/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/midoreigh/MusicTagEditor/releases/tag/v0.1.0
