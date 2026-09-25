#!/usr/bin/env python3
"""
golden_master/strategies.py — Input generation strategies for boundary testing.

Produces inputs covering every boundary class required by PROJECT_CONTEXT.md:
  zero · smallest_unit · max_value · max_minus_unit ·
  negative_max (signed only) · rounding_edge · overflow · random_mid_range

Usage (standalone):
    python -m golden_master.strategies --program PAYROLL --count 20
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

DICT_PATH = Path(__file__).parent.parent / "dictionary" / "data_dictionary.json"


def _load_dict(program: str) -> list[dict[str, Any]]:
    entries = json.loads(DICT_PATH.read_text())
    return [e for e in entries if program in e.get("programs", [])]


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
    """Return x.xx5 — the first value that would round up with ROUND_HALF_UP."""
    scale = entry["digits_after"]
    if scale == 0:
        return Decimal("0")
    unit = _smallest_unit(entry)
    return unit * Decimal("5") / Decimal("10")


# ---------------------------------------------------------------------------
# Boundary generators per field
# ---------------------------------------------------------------------------

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


def boundary_values(entry: dict[str, Any]) -> dict[str, Decimal]:
    """Return one sample value per boundary class for a single field."""
    mx = _field_max(entry)
    su = _smallest_unit(entry)
    re_ = _rounding_edge(entry)
    signed = entry.get("signed", False)
    python_type = entry.get("python_type", "Decimal")

    if python_type != "Decimal":
        # Non-numeric: boundary concept does not apply; return a filler string
        length = entry.get("length", 1)
        filler = " " * length
        return {cls: filler for cls in BOUNDARY_CLASSES}  # type: ignore[return-value]

    overflow_val = mx + su

    samples: dict[str, Decimal] = {
        "zero": Decimal("0"),
        "smallest_unit": su,
        "max_value": mx,
        "max_minus_unit": mx - su,
        "negative_max": -mx if signed else Decimal("0"),
        "rounding_edge": re_,
        "overflow": overflow_val,
        "random_mid_range": Decimal(str(round(random.uniform(0, float(mx / 2)), entry["digits_after"]))),
    }
    return samples


# ---------------------------------------------------------------------------
# Full record generator
# ---------------------------------------------------------------------------

def input_fields_for_program(program: str) -> list[dict[str, Any]]:
    """Return only the *input* fields (those at input offsets, not output)."""
    entries = _load_dict(program)
    # For simplicity, return all fields — callers filter as needed.
    return entries


def generate_inputs(
    program: str,
    count: int = 8,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """
    Generate `count` input records for `program`.

    The first 8 records are one per boundary class (deterministic).
    Remaining records are random mid-range draws.
    """
    if seed is not None:
        random.seed(seed)

    entries = input_fields_for_program(program)
    # Separate input fields from output fields by their usage intent.
    # Convention: if the field appears only in output (e.g. GROSS-PAY), skip.
    # We rely on offset ordering: lowest offsets = input side.
    # For now include all fields in the dict; run_legacy will map to bytes.
    input_only_names = {
        "EMP-ID", "HOURS-WORKED", "HOURLY-RATE", "TAX-RATE"
    }
    input_fields = [e for e in entries if e["field_name"] in input_only_names]

    records: list[dict[str, Any]] = []

    # One record per boundary class using the *first* numeric input field
    if input_fields:
        primary = next((f for f in input_fields if f["python_type"] == "Decimal"), input_fields[0])
        bvals = boundary_values(primary)
        for cls in BOUNDARY_CLASSES:
            rec: dict[str, Any] = {}
            for field in input_fields:
                if field["python_type"] == "Decimal":
                    bv = boundary_values(field)
                    if cls == "negative_max" and not field.get("signed"):
                        rec[field["field_name"]] = Decimal("0")
                    elif cls == "overflow":
                        rec[field["field_name"]] = _field_max(field) + _smallest_unit(field)
                    else:
                        rec[field["field_name"]] = bv.get(cls, Decimal("0"))
                else:
                    rec[field["field_name"]] = " " * field["length"]
            records.append(rec)

    # Fill up to `count` with random mid-range
    while len(records) < count:
        rec = {}
        for field in input_fields:
            if field["python_type"] == "Decimal":
                mx = _field_max(field)
                lo, hi = Decimal("0"), mx
                val = Decimal(str(round(random.uniform(float(lo), float(hi)), field["digits_after"])))
                rec[field["field_name"]] = val
            else:
                rec[field["field_name"]] = " " * field["length"]
        records.append(rec)

    return records[:count]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate boundary-class inputs for a COBOL program.")
    p.add_argument("--program", required=True, help="Program name, e.g. PAYROLL")
    p.add_argument("--count", type=int, default=8, help="Number of records to generate (min 8).")
    p.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
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
