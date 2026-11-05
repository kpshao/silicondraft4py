"""Compile a gettext ``.po`` catalog into a ``.mo`` file with the standard library.

The development environments may not have GNU gettext installed, so this keeps
``make translations`` self-contained. Only the subset of the PO format used by
this repository is supported: ``msgid``/``msgstr`` pairs with quoted strings,
optional comments, and no contexts or plurals.
"""

from __future__ import annotations

import argparse
import ast
import struct
from pathlib import Path

_MAGIC = 0x950412DE
_HEADER_SIZE = 7 * 4


def parse_po(text: str) -> dict[str, str]:
    """Parse the PO text into a ``msgid -> msgstr`` mapping."""
    entries: dict[str, str] = {}
    msgid: list[str] | None = None
    msgstr: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            if msgid is not None:
                entries["".join(msgid)] = "".join(msgstr)
            msgid = [_unquote(line[6:])]
            msgstr = []
            current = "id"
        elif line.startswith("msgstr "):
            msgstr = [_unquote(line[7:])]
            current = "str"
        elif line.startswith('"'):
            if current == "id" and msgid is not None:
                msgid.append(_unquote(line))
            elif current == "str":
                msgstr.append(_unquote(line))
    if msgid is not None:
        entries["".join(msgid)] = "".join(msgstr)
    return entries


def compile_catalog(entries: dict[str, str]) -> bytes:
    """Return the binary ``.mo`` representation of ``entries``."""
    messages = sorted(entries.items())
    originals = [msgid.encode("utf-8") for msgid, _ in messages]
    translations = [msgstr.encode("utf-8") for _, msgstr in messages]
    count = len(messages)

    originals_table = _HEADER_SIZE
    translations_table = originals_table + 8 * count
    data_offset = translations_table + 8 * count

    original_offsets: list[tuple[int, int]] = []
    blob = bytearray()
    for value in originals:
        original_offsets.append((len(value), data_offset + len(blob)))
        blob.extend(value)
        blob.append(0)

    translation_offsets: list[tuple[int, int]] = []
    for value in translations:
        translation_offsets.append((len(value), data_offset + len(blob)))
        blob.extend(value)
        blob.append(0)

    output = bytearray(
        struct.pack(
            "<7I",
            _MAGIC,
            0,
            count,
            originals_table,
            translations_table,
            0,
            0,
        )
    )
    for length, offset in original_offsets:
        output.extend(struct.pack("<2I", length, offset))
    for length, offset in translation_offsets:
        output.extend(struct.pack("<2I", length, offset))
    output.extend(blob)
    return bytes(output)


def _unquote(line: str) -> str:
    value = ast.literal_eval(line)
    if not isinstance(value, str):
        raise ValueError(f"expected a quoted string, got {line!r}")
    return value


def main() -> int:
    """Compile one catalog, writing ``.mo`` next to the ``.po`` by default."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="path to the .po file")
    parser.add_argument("-o", "--output", type=Path, help="path for the .mo file")
    args = parser.parse_args()
    output = args.output if args.output is not None else args.catalog.with_suffix(".mo")
    entries = parse_po(args.catalog.read_text(encoding="utf-8"))
    if "" not in entries:
        entries[""] = "Content-Type: text/plain; charset=UTF-8\nContent-Transfer-Encoding: 8bit\n"
    output.write_bytes(compile_catalog(entries))
    print(f"compiled {len(entries)} message(s) to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
