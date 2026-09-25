#!/usr/bin/env python3
"""
golden_master/run_legacy.py — Run a compiled COBOL module and capture golden output.

Encodes an input dict to a fixed-width record, calls the compiled COBOL shared
object via ctypes, captures the output record, and writes a golden output JSON.

Usage:
    python -m golden_master.run_legacy --program PAYROLL --input '{"EMP-ID":"000001",...}'
    python -m golden_master.run_legacy --program PAYROLL --batch inputs.json
    python -m golden_master.run_legacy --program PAYROLL --generate --count 20

Output schema (one file per input under golden_master/outputs/<PROGRAM>/):
  {
    "input": { <field>: <value>, ... },
    "output_hex": "...",
    "output_decoded": { <field>: <value>, ... },
    "program": "PAYROLL",
    "input_hash": "<sha256>"
  }
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config from environment (loaded lazily so tests can override)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
LEGACY_BIN_DIR = ROOT / "legacy_source" / "bin"
OUTPUT_BASE = ROOT / "golden_master" / "outputs"
DICT_PATH = ROOT / "dictionary" / "data_dictionary.json"


def _load_env() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


# ---------------------------------------------------------------------------
# Data dictionary helpers
# ---------------------------------------------------------------------------

def load_dict(program: str) -> list[dict[str, Any]]:
    entries = json.loads(DICT_PATH.read_text())
    return [e for e in entries if program in e.get("programs", [])]


# ---------------------------------------------------------------------------
# Encoding: input dict → fixed-width bytes
# ---------------------------------------------------------------------------

INPUT_FIELD_NAMES = {"EMP-ID", "HOURS-WORKED", "HOURLY-RATE", "TAX-RATE"}
OUTPUT_FIELD_NAMES = {"GROSS-PAY", "TAX-AMOUNT", "NET-PAY"}
INPUT_RECORD_LEN = 80
OUTPUT_RECORD_LEN = 80


def encode_input(record: dict[str, Any], fields: list[dict[str, Any]]) -> bytes:
    """
    Encode an input dict to a fixed-width byte string.
    Numeric fields are zero-padded; the V (implied decimal) is NOT written.
    String fields are space-padded on the right.
    Filler bytes are spaces.
    """
    buf = bytearray(b" " * INPUT_RECORD_LEN)
    for field in fields:
        if field["field_name"] not in INPUT_FIELD_NAMES:
            continue
        offset = field["offset"]
        length = field["length"]
        value = record.get(field["field_name"])
        if field["python_type"] == "Decimal":
            # Clamp to field size (high-order truncation)
            d = Decimal(str(value)) if not isinstance(value, Decimal) else value
            scale = field["digits_after"]
            total = field["digits_before"] + scale
            # Shift to integer representation
            shifted = int(d * (10 ** scale))
            # Truncate to field width (high-order truncation)
            shifted = shifted % (10 ** total)
            encoded = str(abs(shifted)).zfill(length)
            buf[offset : offset + length] = encoded.encode("ascii")
        else:
            s = str(value) if value is not None else ""
            s = s.ljust(length)[:length]
            buf[offset : offset + length] = s.encode("ascii")
    return bytes(buf)


def decode_output(raw: bytes, fields: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Decode a fixed-width output byte string into a dict of Decimal/str values.
    """
    result: dict[str, Any] = {}
    for field in fields:
        if field["field_name"] not in OUTPUT_FIELD_NAMES:
            continue
        offset = field["offset"]
        length = field["length"]
        chunk = raw[offset : offset + length].decode("ascii", errors="replace")
        if field["python_type"] == "Decimal":
            scale = field["digits_after"]
            try:
                integer_val = int(chunk)
            except ValueError:
                integer_val = 0
            result[field["field_name"]] = Decimal(integer_val) / Decimal(10 ** scale)
        else:
            result[field["field_name"]] = chunk
    return result


# ---------------------------------------------------------------------------
# COBOL runner via ctypes
# ---------------------------------------------------------------------------

def run_cobol(program: str, input_bytes: bytes) -> bytes:
    """
    Call the compiled COBOL shared object.
    The module is expected at legacy_source/bin/<PROGRAM>.so.
    It must accept two PIC X(80) LINKAGE SECTION arguments: input and output.
    """
    _load_env()
    so_path = Path(os.environ.get("LEGACY_SOURCE_DIR", str(ROOT / "legacy_source"))) / "bin" / f"{program}.so"

    if not so_path.exists():
        raise FileNotFoundError(
            f"Compiled COBOL module not found: {so_path}\n"
            f"Run: cd legacy_source && ./build.sh"
        )

    lib = ctypes.CDLL(str(so_path))

    # GnuCOBOL module entry: void <PROGRAM>(void*, void*)
    func = getattr(lib, program.upper())
    func.restype = None
    func.argtypes = [ctypes.c_char_p, ctypes.c_char_p]

    in_buf = ctypes.create_string_buffer(input_bytes, OUTPUT_RECORD_LEN)
    out_buf = ctypes.create_string_buffer(b" " * OUTPUT_RECORD_LEN, OUTPUT_RECORD_LEN)

    func(in_buf, out_buf)
    return bytes(out_buf.raw)


# ---------------------------------------------------------------------------
# Golden output writer
# ---------------------------------------------------------------------------

def _input_hash(record: dict[str, Any]) -> str:
    canonical = json.dumps(
        {k: str(v) for k, v in sorted(record.items())},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def run_and_save(program: str, record: dict[str, Any], fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the COBOL binary for one input record and persist the golden output."""
    input_bytes = encode_input(record, fields)
    output_bytes = run_cobol(program, input_bytes)
    output_decoded = decode_output(output_bytes, fields)
    h = _input_hash(record)

    finding: dict[str, Any] = {
        "input": {k: str(v) for k, v in record.items()},
        "output_hex": output_bytes.hex(),
        "output_decoded": {k: str(v) for k, v in output_decoded.items()},
        "program": program,
        "input_hash": h,
    }

    out_dir = OUTPUT_BASE / program
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{h}.json"
    out_file.write_text(json.dumps(finding, indent=2))
    return finding


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run COBOL binary and record golden outputs.")
    p.add_argument("--program", required=True)
    p.add_argument("--input", help="JSON string of one input record.")
    p.add_argument("--batch", help="JSON file with a list of input records.")
    p.add_argument("--generate", action="store_true", help="Auto-generate boundary inputs.")
    p.add_argument("--count", type=int, default=8, help="Number of inputs to generate (with --generate).")
    p.add_argument("--seed", type=int, default=42)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    fields = load_dict(args.program)

    records: list[dict[str, Any]] = []

    if args.input:
        raw = json.loads(args.input)
        records = [{k: Decimal(str(v)) if isinstance(v, (int, float, str)) else v for k, v in raw.items()}]

    elif args.batch:
        raw_list = json.loads(Path(args.batch).read_text())
        for raw in raw_list:
            records.append({k: Decimal(str(v)) for k, v in raw.items()})

    elif args.generate:
        from golden_master.strategies import generate_inputs
        records = generate_inputs(args.program, args.count, args.seed)

    else:
        print("Provide --input, --batch, or --generate.", file=sys.stderr)
        return 1

    for rec in records:
        try:
            finding = run_and_save(args.program, rec, fields)
            print(f"  {finding['input_hash']}  {finding['output_hex'][:20]}...")
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    print(f"\n{len(records)} golden record(s) written to golden_master/outputs/{args.program}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
