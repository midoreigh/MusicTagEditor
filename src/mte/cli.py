"""Command line companion: dump raw tags, or clean them like the original script.

    mte-cli dump FILE_OR_FOLDER...
    mte-cli clean FOLDER TERM [--dry-run] [--keys-only]
"""

from __future__ import annotations

import argparse
import os
import sys

from .core.cleaner import matching_entries, removal_ops
from .core.model import details
from .core.scanner import find_audio_files, has_audio_ext
from .core.tagfile import apply_and_save, load


def _iter_paths(paths):
    for p in paths:
        if os.path.isdir(p):
            yield from find_audio_files(p)
        elif has_audio_ext(p) or os.path.isfile(p):
            yield p


def cmd_dump(args) -> int:
    for path in _iter_paths(args.paths):
        ft = load(path)
        print(path)
        if ft.error:
            print(f"    ERROR: {ft.error}")
            continue
        print("    " + ", ".join(f"{k}={v}" for k, v in ft.info.items()))
        for e in ft.entries:
            extra = details(e)
            print(f"    [{e.system}] {e.key} = {e.summary()!r}" + (f"  ({extra})" if extra else ""))
    return 0


def cmd_clean(args) -> int:
    files_changed = removed = 0
    errors = []
    for path in _iter_paths([args.folder]):
        ft = load(path)
        if ft.error:
            errors.append((path, ft.error))
            continue
        hits = matching_entries(ft, args.term, args.keys_only)
        if not hits:
            continue
        print(path)
        for e in hits:
            print(f"    removing [{e.system}] {e.key} = {e.summary()!r}")
        if not args.dry_run:
            try:
                apply_and_save(path, removal_ops(ft, args.term, args.keys_only))
            except Exception as ex:
                errors.append((path, f"failed to save ({ex})"))
                continue
        files_changed += 1
        removed += len(hits)
    verb = "would be " if args.dry_run else ""
    print("-" * 60)
    print(f"Files {verb}changed: {files_changed}\nTags {verb}removed: {removed}")
    for path, err in errors:
        print(f"  {path}: {err}")
    return 1 if errors else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="mte-cli", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="print every raw tag")
    d.add_argument("paths", nargs="+")
    d.set_defaults(func=cmd_dump)
    c = sub.add_parser("clean", help="remove tags whose key/value contains TERM")
    c.add_argument("folder")
    c.add_argument("term")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--keys-only", action="store_true", help="match tag keys only")
    c.set_defaults(func=cmd_clean)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
