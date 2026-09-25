#!/usr/bin/env python3
"""
verify/compare.py — Byte-exact comparison of golden, A, and B outputs.

Comparison result classifications (per PROJECT_CONTEXT.md):
  agree_correct         — A == B == golden
  a_wrong               — A != golden, B == golden
  b_wrong               — B != golden, A == golden
  both_wrong_same       — A == B != golden
  both_wrong_different  — A != golden, B != golden, A != B

Each comparison also yields a field-level diff if a data dictionary is
available for the program.

Usage:
    python -m verify.compare --program PAYROLL \\
        --golden golden_master/outputs/PAYROLL/abc123.json \\
        --a-output <hex> --b-output <hex>
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
DICT_PATH = ROOT / "dictionary" / "data_dictionary.json"

# Comparison result literals
AGREE_CORRECT = "agree_correct"
A_WRONG = "a_wrong"
B_WRONG = "b_wrong"
BOTH_WRONG_SAME = "both_wrong_same"
BOTH_WRONG_DIFFERENT = "both_wrong_different"

OUTPUT_FIELD_NAMES = {"GROSS-PAY", "TAX-AMOUNT", "NET-PAY"}


# ---------------------------------------------------------------------------
# Field-level diff helpers
# ---------------------------------------------------------------------------

def _load_output_fields(program: str) -> list[dict[str, Any]]:
    try:
        entries = json.loads(DICT_PATH.read_text())
    except FileNotFoundError:
        return []
    return [e for e in entries if program in e.get("programs", []) and e["field_name"] in OUTPUT_FIELD_NAMES]


def _decode_field(raw: bytes, field: dict[str, Any]) -> str:
    offset = field["offset"]
    length = field["length"]
    chunk = raw[offset : offset + length].decode("ascii", errors="replace")
    if field["python_type"] == "Decimal":
        scale = field["digits_after"]
        try:
            integer_val = int(chunk)
        except ValueError:
            return chunk
        val = Decimal(integer_val) / Decimal(10 ** scale)
        return str(val)
    return chunk


def field_diff(
    golden_bytes: bytes,
    a_bytes: bytes,
    b_bytes: bytes | None,
    fields: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Return per-field differences between golden and candidate outputs."""
    diffs = []
    for field in fields:
        g = _decode_field(golden_bytes, field)
        a = _decode_field(a_bytes, field)
        b = _decode_field(b_bytes, field) if b_bytes is not None else None
        if a != g or (b is not None and b != g):
            entry: dict[str, str] = {"field": field["field_name"], "golden": g, "a": a}
            if b is not None:
                entry["b"] = b
            diffs.append(entry)
    return diffs


# ---------------------------------------------------------------------------
# Main comparison logic
# ---------------------------------------------------------------------------

def classify(
    golden: bytes,
    a_output: bytes,
    b_output: bytes | None = None,
) -> str:
    """Classify the comparison result."""
    a_ok = a_output == golden
    b_ok = b_output == golden if b_output is not None else None

    if b_ok is None:
        return AGREE_CORRECT if a_ok else A_WRONG

    if a_ok and b_ok:
        return AGREE_CORRECT
    if a_ok and not b_ok:
        return B_WRONG
    if not a_ok and b_ok:
        return A_WRONG
    # Both wrong
    if a_output == b_output:
        return BOTH_WRONG_SAME
    return BOTH_WRONG_DIFFERENT


def compare(
    program: str,
    golden_bytes: bytes,
    a_bytes: bytes,
    b_bytes: bytes | None = None,
) -> dict[str, Any]:
    """
    Full comparison returning a result dict with classification and field diffs.
    """
    classification = classify(golden_bytes, a_bytes, b_bytes)
    fields = _load_output_fields(program)
    diff = field_diff(golden_bytes, a_bytes, b_bytes, fields)

    return {
        "classification": classification,
        "agree": classification == AGREE_CORRECT,
        "diff": diff,
        "golden_hex": golden_bytes.hex(),
        "a_hex": a_bytes.hex(),
        "b_hex": b_bytes.hex() if b_bytes is not None else None,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compare golden and candidate outputs byte-exactly.")
    p.add_argument("--program", required=True)
    p.add_argument("--golden", required=True,
                   help="Path to golden JSON file OR a hex string.")
    p.add_argument("--a-output", required=True, dest="a_output",
                   help="Hex string of translator A output.")
    p.add_argument("--b-output", dest="b_output", default=None,
                   help="Hex string of translator B output (optional).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Load golden bytes
    golden_path = Path(args.golden)
    if golden_path.exists():
        golden_data = json.loads(golden_path.read_text())
        golden_bytes = bytes.fromhex(golden_data["output_hex"])
    else:
        golden_bytes = bytes.fromhex(args.golden)

    a_bytes = bytes.fromhex(args.a_output)
    b_bytes = bytes.fromhex(args.b_output) if args.b_output else None

    result = compare(args.program, golden_bytes, a_bytes, b_bytes)
    print(json.dumps(result, indent=2))

    return 0 if result["agree"] else 1


if __name__ == "__main__":
    sys.exit(main())
