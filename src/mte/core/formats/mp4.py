"""MP4/M4A/M4B ``ilst`` atoms, including freeform ``----`` atoms and atoms
mutagen could not parse (kept as raw bytes)."""

from __future__ import annotations

from mutagen.mp4 import AtomDataType, MP4Cover, MP4FreeForm, MP4Tags

from ..model import Field, FieldType, Kind, Picture, TagEntry
from .base import Adapter, TagError, sniff_mime

DESCRIPTIONS = {
    "©nam": "Title", "©alb": "Album", "©ART": "Artist", "aART": "Album artist",
    "©wrt": "Composer", "©day": "Year", "©cmt": "Comment", "desc": "Description",
    "ldes": "Long description", "purd": "Purchase date", "©grp": "Grouping",
    "©gen": "Genre", "©lyr": "Lyrics", "catg": "Podcast category",
    "keyw": "Podcast keywords", "©too": "Encoded by", "cprt": "Copyright",
    "soal": "Sort album", "soaa": "Sort album artist", "soar": "Sort artist",
    "sonm": "Sort title", "soco": "Sort composer", "sosn": "Sort show",
    "tvsh": "TV show", "tven": "TV episode id", "tvnn": "TV network",
    "trkn": "Track number/total", "disk": "Disc number/total", "tmpo": "BPM",
    "cpil": "Compilation", "pgap": "Gapless playback", "pcst": "Podcast flag",
    "purl": "Podcast URL", "egid": "Podcast episode GUID", "covr": "Cover art",
    "stik": "Media kind", "rtng": "Content rating", "hdvd": "HD video",
    "shwm": "Show movement", "©mvi": "Movement index", "©mvc": "Movement count",
    "©mvn": "Movement name", "©wrk": "Work", "plID": "iTunes playlist id",
    "cnID": "iTunes catalog id", "geID": "iTunes genre id", "atID": "iTunes artist id",
    "sfID": "iTunes store front id", "cmID": "iTunes composer id",
    "akID": "iTunes account kind", "tvsn": "TV season", "tves": "TV episode",
    "apID": "iTunes account", "ownr": "Owner", "xid ": "Vendor id",
    "----": "Freeform (reverse-DNS) atom",
}

DATAFORMAT_CHOICES = sorted(
    (int(v), f"{int(v)}: {name}") for name, v in vars(AtomDataType).items()
    if name.isupper() and isinstance(v, int))

_INT_ATOMS = {"plID", "cnID", "geID", "atID", "sfID", "cmID", "akID", "tvsn", "tves",
              "tmpo", "©mvi", "©mvc", "shwm", "stik", "hdvd", "rtng"}
_BOOL_ATOMS = {"cpil", "pgap", "pcst"}
_PAIR_ATOMS = {"trkn", "disk"}
_TEXTUAL_FREEFORM = {AtomDataType.UTF8, AtomDataType.UTF16}

FAILED_PREFIX = "<unparsed>"


def _atom_id(key: str) -> str:
    return "----" if key.startswith("----:") else key


def _freeform_entry(key: str, values) -> TagEntry:
    fmts = {getattr(v, "dataformat", AtomDataType.UTF8) for v in values}
    textual = fmts <= _TEXTUAL_FREEFORM
    if textual:
        try:
            texts = [bytes(v).decode("utf-16" if v.dataformat == AtomDataType.UTF16 else "utf-8")
                     for v in values]
        except UnicodeDecodeError:
            textual = False
    fmt = int(next(iter(fmts))) if len(fmts) == 1 else int(AtomDataType.UTF8)
    fields = [Field("key", FieldType.TEXT, key, "Atom key (----:mean:name)")]
    readonly = False
    if textual:
        fields.append(Field("values", FieldType.TEXT_LIST, texts, "Values"))
    elif len(values) == 1:
        fields.append(Field("data", FieldType.BYTES, bytes(values[0]), "Data"))
    else:
        fields.append(Field("data", FieldType.OPAQUE, [bytes(v) for v in values], readonly=True))
        readonly = True
    fields.append(Field("dataformat", FieldType.CHOICE, fmt, "Data type", DATAFORMAT_CHOICES))
    return TagEntry(MP4Adapter.system, key, "----", Kind.TEXT if textual else Kind.BINARY,
                    fields, description=key.split(":", 2)[-1] + " (freeform)",
                    readonly=readonly, editable_key=True)


def entry_for(key: str, value) -> TagEntry:
    aid = _atom_id(key)
    desc = DESCRIPTIONS.get(aid, "")
    if aid == "----":
        return _freeform_entry(key, value)
    if aid == "covr":
        pics = [Picture(bytes(c), "image/png" if c.imageformat == MP4Cover.FORMAT_PNG
                        else "image/jpeg") for c in value]
        return TagEntry(MP4Adapter.system, key, aid, Kind.PICTURE,
                        [Field("images", FieldType.PICTURES, pics, "Images")], desc)
    if isinstance(value, bool) or aid in _BOOL_ATOMS:
        return TagEntry(MP4Adapter.system, key, aid, Kind.NUMBER,
                        [Field("value", FieldType.BOOL, bool(value), "Value")], desc)
    if aid in _PAIR_ATOMS or (isinstance(value, list) and value and isinstance(value[0], tuple)):
        return TagEntry(MP4Adapter.system, key, aid, Kind.NUMBER,
                        [Field("values", FieldType.PAIR_LIST,
                               [tuple(int(x) for x in v) for v in value], "Number / Total")], desc)
    if aid in _INT_ATOMS or (isinstance(value, list) and value and isinstance(value[0], int)):
        return TagEntry(MP4Adapter.system, key, aid, Kind.NUMBER,
                        [Field("values", FieldType.INT_LIST, [int(v) for v in value], "Values")],
                        desc)
    multiline = aid in ("©lyr", "ldes", "desc", "©cmt")
    return TagEntry(MP4Adapter.system, key, aid, Kind.TEXT,
                    [Field("values", FieldType.TEXT_LIST, [str(v) for v in value],
                           "Values" + (" (multi-line)" if multiline else ""))], desc,
                    editable_key=aid not in DESCRIPTIONS)


def value_for(entry: TagEntry):
    aid = entry.frame_id
    if aid == "----":
        fmt = AtomDataType(int(entry.get("dataformat", AtomDataType.UTF8)))
        if entry.field("values") is not None:
            enc = "utf-16" if fmt == AtomDataType.UTF16 else "utf-8"
            return [MP4FreeForm(s.encode(enc), dataformat=fmt) for s in entry.get("values")]
        return [MP4FreeForm(entry.get("data"), dataformat=fmt)]
    f = entry.fields[0]
    if f.ftype == FieldType.PICTURES:
        return [MP4Cover(p.data, MP4Cover.FORMAT_PNG if sniff_mime(p.data) == "image/png"
                         else MP4Cover.FORMAT_JPEG) for p in f.value]
    if f.ftype == FieldType.BOOL:
        return bool(f.value)
    if f.ftype == FieldType.PAIR_LIST:
        return [tuple(int(x) for x in p) for p in f.value]
    if f.ftype == FieldType.INT_LIST:
        return [int(x) for x in f.value]
    return [str(x) for x in f.value]


class MP4Adapter(Adapter):
    system = "MP4"
    label = "MP4 (iTunes atoms)"

    def __init__(self, audio) -> None:
        super().__init__()
        self.audio = audio

    @property
    def tags(self) -> MP4Tags:
        if self.audio.tags is None:
            self.audio.add_tags()
        return self.audio.tags

    def read(self) -> list[TagEntry]:
        tags = self.audio.tags
        if tags is None:
            return []
        entries = [entry_for(k, v) for k, v in tags.items()]
        for key, blobs in getattr(tags, "_failed_atoms", {}).items():
            for i, data in enumerate(blobs):
                entries.append(TagEntry(
                    self.system, f"{FAILED_PREFIX}{key}#{i}", _atom_id(key), Kind.BINARY,
                    [Field("data", FieldType.BYTES, bytes(data), "Raw atom data", readonly=True)],
                    description=f"{key}: atom mutagen couldn't parse (kept as-is)",
                    readonly=True))
        return entries

    @staticmethod
    def key_of(entry: TagEntry) -> str:
        if entry.frame_id == "----":
            key = entry.get("key", entry.key)
            if not key.startswith("----:") or key.count(":") < 2:
                raise TagError("Freeform keys look like ----:com.apple.iTunes:NAME")
            return key
        return entry.key

    def delete(self, key: str, missing_ok: bool = False) -> None:
        tags = self.audio.tags
        if key.startswith(FAILED_PREFIX):
            name, idx = key[len(FAILED_PREFIX):].rsplit("#", 1)
            blobs = tags._failed_atoms.get(name, [])
            if int(idx) < len(blobs):
                blobs[int(idx)] = None
            return
        if tags is None or key not in tags:
            if missing_ok:
                return
            raise TagError(f"No atom {key!r}")
        del tags[key]

    @classmethod
    def validate(cls, entry: TagEntry) -> str:
        key = cls.key_of(entry)
        if entry.frame_id != "----" and len(key.encode("latin-1", "replace")) != 4:
            raise TagError(f"MP4 atom names are 4 characters, got {key!r}")
        try:
            value_for(entry)
        except (TypeError, ValueError) as e:
            raise TagError(f"{key}: {e}") from e
        return key

    def set(self, entry: TagEntry) -> None:
        key = self.validate(entry)
        try:
            self.tags[key] = value_for(entry)
        except (TypeError, ValueError) as e:
            raise TagError(f"{key}: {e}") from e

    def save(self) -> None:
        tags = self.audio.tags
        if tags is None:
            return
        failed = getattr(tags, "_failed_atoms", {})
        for name in list(failed):
            failed[name] = [b for b in failed[name] if b is not None]
            if not failed[name]:
                del failed[name]
        self.audio.save()

    def templates(self) -> list[TagEntry]:
        out = []
        for aid in sorted(DESCRIPTIONS):
            if aid == "----":
                e = entry_for("----:com.apple.iTunes:NAME",
                              [MP4FreeForm(b"", dataformat=AtomDataType.UTF8)])
                e.set("values", [])
            elif aid == "covr":
                e = entry_for(aid, [])
            elif aid in _BOOL_ATOMS:
                e = entry_for(aid, False)
            elif aid in _PAIR_ATOMS:
                e = entry_for(aid, [(0, 0)])
            elif aid in _INT_ATOMS:
                e = entry_for(aid, [0])
            else:
                e = entry_for(aid, [])
            out.append(e)
        return out
