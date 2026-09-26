#!/usr/bin/env python3
"""
golden_master/strategies.py — Input generation strategies for boundary testing.

Produces inputs covering every boundary class required by PROJECT_CONTEXT.md:
  zero · smallest_unit · max_value · max_minus_unit ·
  negative_max (signed only) · rounding_edge · overflow · random_mid_range

Usage (standalone):
    python -m golden_master.strategies --program GROSSPAY --count 20
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any
from decimal import Decimal

PINNED_CASES = {
    "TAXCALC": [
        # Exact tie: HALF_UP -> 5.01, HALF_EVEN (banker's) -> 5.00
        {"TC-GROSS-PAY": Decimal("100.10"), "TC-TAX-RATE": Decimal("0.0500")},
        # Two-stage truncation: 190.00 * 0.0275 = 5.225 -> COBOL stores 5.22
        {"TC-GROSS-PAY": Decimal("190.00"), "TC-TAX-RATE": Decimal("0.0275")},
    ],
    "DEDUCT": [
        # Health tie 5.005 -> 5.01 (HALF_UP); retirement 5.5055 truncated -> 5.50
        {"DD-GROSS-PAY": Decimal("100.10"), "DD-HEALTH-RATE": Decimal("0.0500"),
        "DD-RETIREMENT-RATE": Decimal("0.0550")},
        # Odd-digit tie 5.025 -> 5.03 (HALF_UP); banker's would give 5.02
        {"DD-GROSS-PAY": Decimal("100.50"), "DD-HEALTH-RATE": Decimal("0.0500"),
        "DD-RETIREMENT-RATE": Decimal("0.0000")},
    ],
}


def with_pinned(program, records):
    """Append pinned cases, filling other fields from a generated record."""
    cases = PINNED_CASES.get(program, [])
    if not cases or not records:
        return records
    base = records[0]
    return records + [{**base, **case} for case in cases]
DICT_PATH = Path(__file__).parent.parent / "dictionary" / "data_dictionary.json"

BOUNDARY_CLASSES = [
    "zero",
    "smallest_unit",
    "max_value",
    "max_minus_unit",
    "negative_max",
    "rounding_edge",
    "overflow",
    "random_mid_range",
]


def _load_dict(program: str) -> list[dict[str, Any]]:
    entries = json.loads(DICT_PATH.read_text())
    return [e for e in entries if program in e.get("programs", [])]


def _input_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in fields if f.get("record_type") == "input"]


def _field_max(entry: dict[str, Any]) -> Decimal:
    """Largest value a field can hold without overflow."""
    total_digits = entry["digits_before"] + entry["digits_after"]
    scale = entry["digits_after"]
    raw_max = Decimal(10 ** total_digits - 1)
    if scale:
        raw_max = raw_max / Decimal(10 ** scale)
    return raw_max


def _smallest_unit(entry: dict[str, Any]) -> Decimal:
    scale = entry["digits_after"]
    if scale == 0:
        return Decimal("1")
    return Decimal("1") / Decimal(10 ** scale)


def _rounding_edge(entry: dict[str, Any]) -> Decimal:
    """Return the value x.xx5 — first value that rounds up with ROUND_HALF_UP."""
    scale = entry["digits_after"]
    if scale == 0:
        return Decimal("0")
    # One sub-unit below the rounding threshold: 0.005 for scale=2
    return Decimal("5") / Decimal(10 ** (scale + 1))


def boundary_values(entry: dict[str, Any]) -> dict[str, Any]:
    """Return one sample value per boundary class for a single field."""
    python_type = entry.get("python_type", "Decimal")
    signed = entry.get("signed", False)

    if python_type != "Decimal":
        length = entry.get("length", 1)
        filler = " " * length
        return {cls: filler for cls in BOUNDARY_CLASSES}  # type: ignore[return-value]

    mx = _field_max(entry)
    su = _smallest_unit(entry)
    re_ = _rounding_edge(entry)

    samples: dict[str, Any] = {
        "zero": Decimal("0"),
        "smallest_unit": su,
        "max_value": mx,
        "max_minus_unit": mx - su,
        "negative_max": -mx if signed else Decimal("0"),
        "rounding_edge": re_,
        "overflow": mx + su,
        "random_mid_range": Decimal(
            str(round(random.uniform(0, float(mx / 2)), entry["digits_after"]))
        ),
    }
    return samples


def generate_inputs(
    program: str,
    count: int = 8,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """
    Generate `count` input records for `program`.

    The first 8 records are one per boundary class (deterministic once seeded).
    Remaining records are random mid-range draws.

    All numeric values are Decimal instances — never float.
    """
    if seed is not None:
        random.seed(seed)

    all_fields = _load_dict(program)
    in_fields = _input_fields(all_fields)

    # Separate numeric from string fields
    numeric_fields = [f for f in in_fields if f["python_type"] == "Decimal"]
    string_fields = [f for f in in_fields if f["python_type"] != "Decimal"]

    # Select the primary numeric field (first numeric) for driving boundary class
    # For negative_max class: use the first signed field if available; else EMP-ID
    signed_fields = [f for f in numeric_fields if f.get("signed")]

    records: list[dict[str, Any]] = []

    # Produce one record per boundary class
    for cls in BOUNDARY_CLASSES:
        rec: dict[str, Any] = {}

        # String fields: always use a fixed placeholder
        for f in string_fields:
            rec[f["field_name"]] = " " * f["length"]

        # Numeric fields: pick boundary value per field
        for f in numeric_fields:
            bv = boundary_values(f)
            val = bv.get(cls, Decimal("0"))

            # negative_max on unsigned field → use 0 (negative_max class is for signed)
            if cls == "negative_max" and not f.get("signed"):
                val = Decimal("0")

            # For rounding_edge: keep the sub-unit value that triggers rounding
            # (the COBOL COMPUTE without ROUNDED will truncate it)
            rec[f["field_name"]] = val

        records.append(rec)

    # Fill up to `count` with random mid-range records
    while len(records) < count:
        rec = {}
        for f in string_fields:
            rec[f["field_name"]] = " " * f["length"]
        for f in numeric_fields:
            mx = _field_max(f)
            lo, hi = Decimal("0"), mx
            val = Decimal(
                str(round(random.uniform(float(lo), float(hi)), f["digits_after"]))
            )
            rec[f["field_name"]] = val
        records.append(rec)

    return with_pinned(program, records[:count])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate boundary-class inputs for a COBOL program."
    )
    p.add_argument("--program", required=True, help="Program name, e.g. GROSSPAY")
    p.add_argument("--count", type=int, default=8, help="Number of records (min 8).")
    p.add_argument("--seed", type=int, default=None, help="Random seed.")
    p.add_argument("--out", default="-", help="Output JSON file (default: stdout).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    records = generate_inputs(args.program, max(8, args.count), args.seed)

    def _default(obj: Any) -> str:
        if isinstance(obj, Decimal):
            return str(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    output = json.dumps(records, indent=2, default=_default)
    if args.out == "-":
        print(output)
    else:
        Path(args.out).write_text(output)
        print(f"Written {len(records)} records to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
