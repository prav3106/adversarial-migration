#!/usr/bin/env python3
"""
dictionary/extract.py — Data dictionary extractor for COBOL source files.

Parses COBOL WORKING-STORAGE and LINKAGE SECTION to produce
data_dictionary.json entries for each field.

Usage:
    python -m dictionary.extract legacy_source/PAYROLL.cbl [--program PAYROLL]
    python -m dictionary.extract --all legacy_source/ --out dictionary/data_dictionary.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# PIC clause parser
# ---------------------------------------------------------------------------

_PIC_RE = re.compile(
    r"PIC\s+(?P<sign>S?)(?P<pic>[9AXZ()\.\,V]+)",
    re.IGNORECASE,
)
_REPEAT_RE = re.compile(r"(\d+)\((\d+)\)|([9AXZ])")

USAGE_RE = re.compile(r"\bCOMP-3\b|\bCOMPUTATIONAL-3\b|\bBINARY\b|\bCOMP\b", re.I)


def _expand_pic(pic_str: str) -> str:
    """Expand e.g. '9(3)' → '999', 'X(5)' → 'XXXXX'."""
    result = []
    i = 0
    while i < len(pic_str):
        ch = pic_str[i]
        if i + 1 < len(pic_str) and pic_str[i + 1] == "(":
            end = pic_str.index(")", i + 2)
            count = int(pic_str[i + 2 : end])
            result.append(ch * count)
            i = end + 1
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def parse_pic(pic_clause: str, signed: bool) -> dict[str, Any]:
    """Return digits_before, digits_after, length, python_type."""
    # Remove SIGN clause noise
    pic = pic_clause.strip().upper()
    v_pos = pic.find("V")
    if v_pos == -1:
        before_str = _expand_pic(pic.replace("S", "").replace("9", "9"))
        digits_before = before_str.count("9")
        digits_after = 0
    else:
        before_str = _expand_pic(pic[:v_pos].replace("S", ""))
        after_str = _expand_pic(pic[v_pos + 1 :])
        digits_before = before_str.count("9")
        digits_after = after_str.count("9")

    length = digits_before + digits_after
    python_type = "Decimal" if "9" in pic else "str"
    return {
        "digits_before": digits_before,
        "digits_after": digits_after,
        "length": length,
        "python_type": python_type,
    }


# ---------------------------------------------------------------------------
# COBOL line parser
# ---------------------------------------------------------------------------

FIELD_RE = re.compile(
    r"^\s*\d{2}\s+"                          # level number
    r"(?P<name>[A-Z0-9][-A-Z0-9]*)\s+"       # field name
    r"PIC\s+(?P<signed>S?)(?P<pic>[9AXZ()\.\,V]+)"
    r"(?:\s+USAGE\s+(?P<usage>\S+))?",
    re.IGNORECASE,
)

FILLER_RE = re.compile(r"^\s*\d{2}\s+FILLER", re.IGNORECASE)


def extract_fields(source: str, program: str) -> list[dict[str, Any]]:
    """Parse a COBOL source string and return data dictionary entries."""
    entries: list[dict[str, Any]] = []
    offset = 0
    in_ws = False

    for lineno, raw_line in enumerate(source.splitlines(), start=1):
        line = raw_line.rstrip()

        # Detect section boundaries
        upper = line.upper()
        if "WORKING-STORAGE SECTION" in upper or "LINKAGE SECTION" in upper:
            in_ws = True
            offset = 0
            continue
        if "PROCEDURE DIVISION" in upper:
            in_ws = False
            continue

        if not in_ws:
            continue

        # Skip FILLER lines (still advance offset)
        if FILLER_RE.match(line):
            m = FIELD_RE.search(line)
            if m:
                signed = bool(m.group("signed"))
                pic_info = parse_pic(m.group("pic"), signed)
                offset += pic_info["length"]
            continue

        m = FIELD_RE.match(line)
        if not m:
            continue

        name = m.group("name").upper()
        pic_raw = m.group("pic")
        signed = bool(m.group("signed"))
        usage_str = (m.group("usage") or "DISPLAY").upper()

        # Normalise usage
        if "COMP-3" in usage_str or "COMPUTATIONAL-3" in usage_str:
            usage = "COMP-3"
        elif "COMP" in usage_str or "BINARY" in usage_str:
            usage = "BINARY"
        else:
            usage = "DISPLAY"

        pic_info = parse_pic(pic_raw, signed)

        entry: dict[str, Any] = {
            "field_name": name,
            "programs": [program],
            "pic": ("S" if signed else "") + pic_raw,
            "usage": usage,
            "digits_before": pic_info["digits_before"],
            "digits_after": pic_info["digits_after"],
            "signed": signed,
            "offset": offset,
            "length": pic_info["length"],
            "python_type": pic_info["python_type"],
            "rounding": "truncate",
            "source_line": lineno,
        }
        entries.append(entry)
        offset += pic_info["length"]

    return entries


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extract data dictionary entries from COBOL source files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "sources",
        nargs="*",
        metavar="FILE",
        help="One or more COBOL source files (.cbl).",
    )
    p.add_argument(
        "--all",
        metavar="DIR",
        help="Process all *.cbl files in DIR.",
    )
    p.add_argument(
        "--program",
        help="Override program name (default: derived from filename).",
    )
    p.add_argument(
        "--out",
        default="-",
        help="Output JSON file (default: stdout).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    paths: list[Path] = []
    if args.all:
        paths = sorted(Path(args.all).glob("*.cbl"))
    for s in args.sources:
        paths.append(Path(s))

    if not paths:
        parser.error("Provide at least one .cbl file or use --all DIR.")

    all_entries: list[dict[str, Any]] = []
    for path in paths:
        program = args.program or path.stem.upper()
        source = path.read_text(encoding="utf-8", errors="replace")
        entries = extract_fields(source, program)
        all_entries.extend(entries)
        print(f"  {path}: {len(entries)} field(s) extracted.", file=sys.stderr)

    output = json.dumps(all_entries, indent=2)
    if args.out == "-":
        print(output)
    else:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Written to {args.out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
