#!/usr/bin/env python3
"""
dictionary/extract.py — Data dictionary extractor for COBOL source files.

Parses COBOL WORKING-STORAGE section to produce data_dictionary.json entries.
Only fields inside named 01-level records (WS-INPUT-RECORD, WS-OUTPUT-RECORD)
are included; control fields (WS-INPUT-PATH, WS-EOF-FLAG, etc.) and working
area fields (WS-WORK.*) are excluded.

Usage:
    python -m dictionary.extract legacy_source/VALIDATE.cbl [--program VALIDATE]
    python -m dictionary.extract --all legacy_source/ --out dictionary/data_dictionary.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# PIC clause helpers
# ---------------------------------------------------------------------------


def _expand_pic(pic_str: str) -> str:
    """Expand e.g. '9(3)' → '999', 'X(20)' → 'XXXXXXXXXXXXXXXXXXXX'."""
    result = []
    i = 0
    s = pic_str.upper()
    while i < len(s):
        ch = s[i]
        if i + 1 < len(s) and s[i + 1] == "(":
            end = s.index(")", i + 2)
            count = int(s[i + 2 : end])
            result.append(ch * count)
            i = end + 1
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def _comp3_byte_len(total_digits: int) -> int:
    """Bytes for a COMP-3 field: ceil((digits + 1) / 2)."""
    return math.ceil((total_digits + 1) / 2)


def parse_pic(pic_clause: str, usage: str) -> dict[str, Any]:
    """
    Return digits_before, digits_after, display_length, python_type.
    display_length: number of bytes in the DISPLAY representation (no implicit V).
    """
    pic = pic_clause.strip().upper().rstrip(".")
    # Strip leading S (sign)
    pic_no_sign = pic.lstrip("S")
    # Find V (implied decimal point — not written to file)
    v_pos = pic_no_sign.find("V")
    if v_pos == -1:
        before_expanded = _expand_pic(pic_no_sign)
        after_expanded = ""
    else:
        before_expanded = _expand_pic(pic_no_sign[:v_pos])
        after_expanded = _expand_pic(pic_no_sign[v_pos + 1 :])

    digits_before = before_expanded.count("9")
    digits_after = after_expanded.count("9")
    total_digits = digits_before + digits_after

    # Alphanumeric characters (X, A, Z) count toward display length
    alpha_before = before_expanded.count("X") + before_expanded.count("A") + before_expanded.count("Z")
    # 'has_numeric' means it is a numeric field (Decimal)
    has_numeric = total_digits > 0

    python_type = "Decimal" if has_numeric else "str"

    if usage == "COMP-3":
        length = _comp3_byte_len(total_digits)
    else:
        # DISPLAY: each digit/alpha = 1 byte; sign is overpunched (no extra byte)
        length = total_digits + alpha_before

    return {
        "digits_before": digits_before,
        "digits_after": digits_after,
        "length": length,
        "python_type": python_type,
    }


# ---------------------------------------------------------------------------
# COBOL line regexes
# ---------------------------------------------------------------------------

# Matches a field declaration (any level) with a PIC clause
FIELD_RE = re.compile(
    r"^\s*(?P<level>\d{2})\s+"
    r"(?P<name>[A-Z0-9][-A-Z0-9]*)\s+"
    r"PIC\s+(?P<signed>S?)(?P<pic>[0-9AXZ()\.\,V]+)",
    re.IGNORECASE,
)

FILLER_RE = re.compile(r"^\s*\d{2}\s+FILLER\b", re.IGNORECASE)

# Matches a 01-level group header (no PIC)
GROUP_01_RE = re.compile(
    r"^\s*01\s+(?P<name>[A-Z0-9][-A-Z0-9]*)\s*\.",
    re.IGNORECASE,
)

USAGE_RE = re.compile(r"\bUSAGE\s+(?P<usage>[A-Z0-9-]+)", re.IGNORECASE)

# Detect COMPUTE ROUNDED — used to set rounding metadata
COMPUTE_ROUNDED_RE = re.compile(
    r"\bCOMPUTE\s+(?P<target>[A-Z0-9][-A-Z0-9]*)\s+ROUNDED\b",
    re.IGNORECASE,
)

# Records we care about: input and output 01-groups for each program
# Pattern: names that start with a meaningful 2-char prefix, not WS-control or WS-WORK
_INTERESTING_01_PREFIXES = {
    # VALIDATE
    "WS-INPUT-RECORD", "WS-OUTPUT-RECORD",
    # (same names used by GROSSPAY, TAXCALC, DEDUCT, PAYSLIP)
}


def _parse_usage(line: str) -> str:
    m = USAGE_RE.search(line)
    if m:
        val = m.group("usage").upper().rstrip(".")
        if "COMP-3" in val or "COMPUTATIONAL-3" in val:
            return "COMP-3"
        if re.match(r"^(COMP|BINARY)$", val):
            return "BINARY"
    return "DISPLAY"


def _find_rounded_fields(source: str) -> set[str]:
    """Return field names that appear in COMPUTE ... ROUNDED statements."""
    rounded: set[str] = set()
    in_proc = False
    for line in source.splitlines():
        if "PROCEDURE DIVISION" in line.upper():
            in_proc = True
        if not in_proc:
            continue
        for m in COMPUTE_ROUNDED_RE.finditer(line):
            rounded.add(m.group("target").upper())
    return rounded


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

# Which 01-level record names to extract per program
# (input record is WS-INPUT-RECORD; output is WS-OUTPUT-RECORD)
_RECORD_NAMES = {"WS-INPUT-RECORD", "WS-OUTPUT-RECORD"}
_RECORD_TYPE = {
    "WS-INPUT-RECORD": "input",
    "WS-OUTPUT-RECORD": "output",
}


def extract_fields(source: str, program: str) -> list[dict[str, Any]]:
    """
    Parse a COBOL source string and return data dictionary entries for
    the input and output records only (WS-INPUT-RECORD and WS-OUTPUT-RECORD).
    Working-storage control variables and WS-WORK fields are excluded.
    """
    rounded_fields = _find_rounded_fields(source)
    entries: list[dict[str, Any]] = []

    in_ws = False
    current_record: str | None = None  # name of the active 01-group
    offset = 0

    for lineno, raw_line in enumerate(source.splitlines(), start=1):
        line = raw_line.rstrip()
        upper = line.upper()

        # Section boundary tracking
        if "WORKING-STORAGE SECTION" in upper:
            in_ws = True
            current_record = None
            continue
        if "FILE SECTION" in upper or "LINKAGE SECTION" in upper:
            in_ws = False
            continue
        if "PROCEDURE DIVISION" in upper:
            in_ws = False
            continue

        if not in_ws:
            continue

        # Detect 01-level group header (e.g. "01  WS-INPUT-RECORD.")
        gm = GROUP_01_RE.match(line)
        if gm:
            name = gm.group("name").upper()
            if name in _RECORD_NAMES:
                current_record = name
                offset = 0
            else:
                current_record = None
            continue


        # If we are inside an interesting 01-group, parse field lines
        if current_record is None:
            continue

        # Handle FILLER (advance offset but don't emit entry)
        if FILLER_RE.match(line):
            fm = FIELD_RE.search(line)
            if fm:
                usage = _parse_usage(line)
                pic_info = parse_pic(fm.group("pic"), usage)
                offset += pic_info["length"]
            continue

        m = FIELD_RE.match(line)
        if not m:
            continue

        name = m.group("name").upper()
        pic_raw = m.group("pic")
        signed = bool(m.group("signed"))
        usage = _parse_usage(line)
        pic_info = parse_pic(pic_raw, usage)

        rounding = "half_up" if name in rounded_fields else "truncate"

        record_type = _RECORD_TYPE.get(current_record, "input")
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
            "rounding": rounding,
            "record_type": record_type,
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
    p.add_argument("sources", nargs="*", metavar="FILE")
    p.add_argument("--all", metavar="DIR", help="Process all *.cbl files in DIR.")
    p.add_argument("--program", help="Override program name (default: filename stem).")
    p.add_argument("--out", default="-", help="Output JSON file (default: stdout).")
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
