#!/usr/bin/env python3
"""
golden_master/run_legacy.py — Run a compiled COBOL executable and capture golden output.

Encodes an input dict to a fixed-width 80-byte binary file, invokes the compiled
COBOL executable via subprocess passing file paths as positional arguments, reads
the 80-byte output file, decodes it, and writes a golden output JSON.

I/O contract (per PROJECT_CONTEXT.md rule 8):
  - Write input record to a temp file (exactly 80 bytes, SEQUENTIAL).
  - Pass input_path output_path as args 1 and 2 to the executable.
  - Read the output file; decode per data dictionary.
  - No ctypes. No shared objects. Pure subprocess + file I/O.

COMP-3 encoding (packed decimal):
  - Each decimal digit occupies one nibble (4 bits).
  - The low nibble of the last byte is the sign: 0xC = positive, 0xD = negative.
  - Total bytes = ceil((total_digits + 1) / 2).

Signed DISPLAY encoding (overpunch, GnuCOBOL default):
  - Sign is embedded as a zone in the last digit byte.
  - Positive last digit: 0x30-0x39 (standard ASCII '0'-'9').
  - Negative last digit: 0x70-0x79 (overpunch zone 7 for zone 3 → 0x30 → 0x70).

Usage:
    python -m golden_master.run_legacy --program GROSSPAY --generate --count 20
    python -m golden_master.run_legacy --program TAXCALC --input '{"TC-EMP-ID":"000001",...}'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
LEGACY_BIN_DIR = ROOT / "legacy_source" / "bin"
OUTPUT_BASE = ROOT / "golden_master" / "outputs"
DICT_PATH = ROOT / "dictionary" / "data_dictionary.json"

RECORD_LEN = 80


def _load_env() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


# ---------------------------------------------------------------------------
# Data dictionary
# ---------------------------------------------------------------------------

def load_dict(program: str) -> list[dict[str, Any]]:
    """Return all data dictionary entries for `program`."""
    entries = json.loads(DICT_PATH.read_text())
    return [e for e in entries if program in e.get("programs", [])]


def input_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in fields if f.get("record_type") == "input"]


def output_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in fields if f.get("record_type") == "output"]


# ---------------------------------------------------------------------------
# COMP-3 (packed decimal) encode / decode
# ---------------------------------------------------------------------------

def encode_comp3(value: Decimal, total_digits: int) -> bytes:
    """
    Encode a Decimal value to COMP-3 packed bytes.

    - `total_digits` = digits_before + digits_after (the total field capacity).
    - The value must already be scaled (caller passes the integer representation).
    - Sign nibble: 0xC = positive/zero, 0xD = negative.
    - Overflow: high-order truncation (modulo 10^total_digits).
    """
    n_bytes = math.ceil((total_digits + 1) / 2)
    # Work with the absolute integer (already shifted by scale by caller)
    negative = value < 0
    abs_val = abs(int(value))
    # High-order truncation
    modulus = 10 ** total_digits
    abs_val = abs_val % modulus
    # Sign nibble
    sign_nibble = 0xD if negative else 0xC
    # Build digit string (total_digits digits, zero-padded on left)
    digit_str = str(abs_val).zfill(total_digits)
    # Pack into bytes: even digit count → leading zero pair
    # We have total_digits digit nibbles + 1 sign nibble
    # Total nibbles = total_digits + 1
    # Bytes = ceil((total_digits + 1) / 2)
    # Arrange: if total_digits is odd → first nibble is 0 (padding)
    nibbles = [int(d) for d in digit_str] + [sign_nibble]
    if len(nibbles) % 2 == 1:
        nibbles = [0] + nibbles
    result = bytearray(n_bytes)
    for i in range(n_bytes):
        result[i] = (nibbles[2 * i] << 4) | nibbles[2 * i + 1]
    return bytes(result)


def decode_comp3(data: bytes, total_digits: int, digits_after: int) -> Decimal:
    """
    Decode COMP-3 packed bytes to a Decimal.

    - `total_digits` = digits_before + digits_after.
    - `digits_after` = scale for implied decimal point.
    """
    nibbles = []
    for b in data:
        nibbles.append((b >> 4) & 0xF)
        nibbles.append(b & 0xF)
    # Last nibble is sign
    sign_nibble = nibbles[-1]
    digit_nibbles = nibbles[:-1]
    # Take the last total_digits nibbles (may have leading zero padding)
    digit_nibbles = digit_nibbles[-total_digits:]
    integer_val = int("".join(str(n) for n in digit_nibbles))
    negative = sign_nibble == 0xD
    result = Decimal(integer_val)
    if digits_after:
        result = result / Decimal(10 ** digits_after)
    if negative:
        result = -result
    return result


# ---------------------------------------------------------------------------
# Signed DISPLAY encode / decode (overpunch, SIGN TRAILING)
# ---------------------------------------------------------------------------
# GnuCOBOL default: SIGN TRAILING SEPARATE is NOT the default.
# Default (SIGN TRAILING, NOT SEPARATE = overpunch):
#   Positive digits 0-9: ASCII 0x30-0x39 (unchanged).
#   Negative digits 0-9: 0x70-0x79 (zone nibble changed from 3 to 7).

def encode_signed_display(integer_val: int, total_digits: int) -> bytes:
    """
    Encode a signed integer (already scaled) to a DISPLAY field with overpunch.
    The sign is embedded in the last byte's zone nibble.
    Positive: standard ASCII digits. Negative: last byte zone = 0x7 instead of 0x3.
    """
    negative = integer_val < 0
    abs_val = abs(integer_val)
    # High-order truncation
    abs_val = abs_val % (10 ** total_digits)
    digit_str = str(abs_val).zfill(total_digits)
    raw = bytearray(digit_str.encode("ascii"))
    if negative:
        # Change zone nibble of last byte from 0x3 to 0x7
        raw[-1] = (raw[-1] & 0x0F) | 0x70
    return bytes(raw)


def decode_signed_display(data: bytes, total_digits: int, digits_after: int) -> Decimal:
    """
    Decode a signed DISPLAY field with overpunch.
    Negative if last byte zone nibble == 0x7.
    """
    if not data:
        return Decimal("0")
    last_byte = data[-1]
    negative = (last_byte & 0xF0) == 0x70
    # Restore last byte to standard ASCII digit
    clean = bytearray(data)
    if negative:
        clean[-1] = (last_byte & 0x0F) | 0x30
    try:
        integer_val = int(clean.decode("ascii", errors="replace"))
    except ValueError:
        integer_val = 0
    result = Decimal(integer_val)
    if digits_after:
        result = result / Decimal(10 ** digits_after)
    if negative:
        result = -result
    return result


# ---------------------------------------------------------------------------
# Encoding: input dict → 80-byte fixed-width record
# ---------------------------------------------------------------------------

def encode_input(record: dict[str, Any], fields: list[dict[str, Any]]) -> bytes:
    """
    Encode an input dict to a fixed-width 80-byte byte string.

    - Numeric DISPLAY fields: zero-padded integer representation (V not written).
      Signed fields: overpunch on last byte.
    - COMP-3 fields: packed decimal.
    - String (PIC X) fields: space-padded on right.
    - Record is zero-padded to RECORD_LEN.
    """
    buf = bytearray(b" " * RECORD_LEN)
    for field in fields:
        name = field["field_name"]
        if name not in record:
            continue
        offset = field["offset"]
        length = field["length"]
        value = record[name]
        usage = field.get("usage", "DISPLAY")
        digits_before = field["digits_before"]
        digits_after = field["digits_after"]
        total_digits = digits_before + digits_after
        signed = field.get("signed", False)
        python_type = field.get("python_type", "str")

        if python_type == "Decimal":
            d = Decimal(str(value)) if not isinstance(value, Decimal) else value
            scale = digits_after
            # Shift to integer representation (truncate, not round)
            shifted = int((d * Decimal(10 ** scale)).to_integral_value(rounding=ROUND_DOWN))
            if usage == "COMP-3":
                encoded = encode_comp3(Decimal(shifted) if d >= 0 else Decimal(-abs(shifted)), total_digits)
                buf[offset : offset + length] = encoded
            elif signed:
                encoded = encode_signed_display(shifted, total_digits)
                buf[offset : offset + length] = encoded
            else:
                # Unsigned DISPLAY: high-order truncation on abs value
                abs_shifted = abs(shifted) % (10 ** total_digits)
                encoded = str(abs_shifted).zfill(length).encode("ascii")
                buf[offset : offset + length] = encoded
        else:
            # Alphanumeric: space-padded
            s = str(value) if value is not None else ""
            s = s.ljust(length)[:length]
            buf[offset : offset + length] = s.encode("ascii", errors="replace")

    return bytes(buf)


# ---------------------------------------------------------------------------
# Decoding: 80-byte output → dict
# ---------------------------------------------------------------------------

def decode_output(raw: bytes, fields: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Decode a fixed-width output byte string into a dict of Decimal/str values.
    Handles COMP-3 and signed DISPLAY correctly.
    """
    result: dict[str, Any] = {}
    for field in fields:
        name = field["field_name"]
        offset = field["offset"]
        length = field["length"]
        usage = field.get("usage", "DISPLAY")
        digits_before = field["digits_before"]
        digits_after = field["digits_after"]
        total_digits = digits_before + digits_after
        signed = field.get("signed", False)
        python_type = field.get("python_type", "str")

        chunk = raw[offset : offset + length]

        if python_type == "Decimal":
            if usage == "COMP-3":
                result[name] = decode_comp3(chunk, total_digits, digits_after)
            elif signed:
                result[name] = decode_signed_display(chunk, total_digits, digits_after)
            else:
                try:
                    integer_val = int(chunk.decode("ascii", errors="replace"))
                except ValueError:
                    integer_val = 0
                val = Decimal(integer_val)
                if digits_after:
                    val = val / Decimal(10 ** digits_after)
                result[name] = val
        else:
            result[name] = chunk.decode("ascii", errors="replace")

    return result


# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------

def run_cobol(program: str, input_bytes: bytes) -> bytes:
    """
    Invoke the compiled COBOL executable via subprocess with file-based I/O.
    Writes input to a temp file, passes both paths as positional args, reads output.
    """
    _load_env()
    bin_dir = Path(os.environ.get("LEGACY_BIN_DIR", str(LEGACY_BIN_DIR)))
    exe = bin_dir / program.upper()
    if not exe.exists():
        raise FileNotFoundError(
            f"Compiled COBOL executable not found: {exe}\n"
            f"Run: bash legacy_source/build.sh"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = Path(tmpdir) / "input.dat"
        out_path = Path(tmpdir) / "output.dat"
        in_path.write_bytes(input_bytes)
        # Pre-create output file so COBOL OPEN OUTPUT doesn't need to create it
        out_path.write_bytes(b"\x00" * RECORD_LEN)

        result = subprocess.run(
            [str(exe), str(in_path), str(out_path)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"COBOL program {program} exited with code {result.returncode}:\n{stderr}"
            )
        return out_path.read_bytes()[:RECORD_LEN]


# ---------------------------------------------------------------------------
# Golden output writer
# ---------------------------------------------------------------------------

def _input_hash(record: dict[str, Any]) -> str:
    canonical = json.dumps(
        {k: str(v) for k, v in sorted(record.items())},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def run_and_save(
    program: str,
    record: dict[str, Any],
    fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Run the COBOL binary for one input record and persist the golden output.
    Returns the golden record dict.
    """
    if fields is None:
        fields = load_dict(program)
    in_fields = input_fields(fields)
    out_fields = output_fields(fields)

    input_bytes = encode_input(record, in_fields)
    output_bytes = run_cobol(program, input_bytes)
    decoded = decode_output(output_bytes, out_fields)
    h = _input_hash(record)

    golden: dict[str, Any] = {
        "input": {k: str(v) for k, v in record.items()},
        "output_hex": output_bytes.hex(),
        "output_decoded": {k: str(v) for k, v in decoded.items()},
        "program": program,
        "input_hash": h,
    }

    out_dir = OUTPUT_BASE / program
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{h}.json"
    out_file.write_text(json.dumps(golden, indent=2))
    return golden


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run COBOL binary and record golden outputs.")
    p.add_argument("--program", required=True, help="Program name (e.g. GROSSPAY).")
    p.add_argument("--input", help="JSON string of one input record.")
    p.add_argument("--batch", help="JSON file with a list of input records.")
    p.add_argument("--generate", action="store_true", help="Auto-generate boundary inputs.")
    p.add_argument("--count", type=int, default=8, help="Number of inputs (with --generate).")
    p.add_argument("--seed", type=int, default=42)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    fields = load_dict(args.program)

    records: list[dict[str, Any]] = []

    if args.input:
        raw = json.loads(args.input)
        records = [{k: Decimal(str(v)) for k, v in raw.items()}]

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

    written = 0
    for rec in records:
        try:
            golden = run_and_save(args.program, rec, fields)
            print(f"  {golden['input_hash']}  {golden['output_hex'][:24]}...")
            written += 1
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    print(f"\n{written} golden record(s) written to golden_master/outputs/{args.program}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
