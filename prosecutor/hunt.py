#!/usr/bin/env python3
"""
prosecutor/hunt.py — Adversarial input search using Hypothesis.

Searches for inputs where translator A, translator B, and the golden master
disagree. Pinned boundary cases always run first (via generate_inputs seed),
then Hypothesis generates and shrinks. On a finding, writes a Finding JSON to
reports/findings/<PROGRAM>.json. On a clean run, writes a clean result.

Every input is normalized before use: it is encoded into the fixed-width
record layout and decoded back, so the golden master and both translators
receive exactly the values the COBOL program actually sees.

Usage:
    python -m prosecutor.hunt TAXCALC --budget 200
    python -m prosecutor.hunt TAXCALC --budget 1000 --variants a b
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
FINDINGS_DIR = ROOT / "reports" / "findings"

try:
    from hypothesis import given, settings, HealthCheck, Phase
    from hypothesis import strategies as st
    from hypothesis.database import InMemoryExampleDatabase
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Input field loading and normalization
# ---------------------------------------------------------------------------

def _load_input_fields(program: str) -> list[dict[str, Any]]:
    dict_path = ROOT / "dictionary" / "data_dictionary.json"
    entries = json.loads(dict_path.read_text())
    return [e for e in entries if program in e.get("programs", []) and e.get("record_type") == "input"]


def normalize(record: dict[str, Any], in_fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Return exactly what the COBOL program sees after the record is laid out.

    Values that cannot exist in the record (e.g. 0.005 in a V9(2) field, or a
    value above the field's max) are squeezed the same way the COBOL program
    would receive them, so translators are never judged on impossible inputs.
    """
    from golden_master.run_legacy import encode_input, decode_output
    decoded = decode_output(encode_input(record, in_fields), in_fields)
    return {**record, **decoded}


# ---------------------------------------------------------------------------
# Hypothesis strategy builder — driven by data dictionary
# ---------------------------------------------------------------------------

def _strategy_for_field(field: dict[str, Any]) -> Any:
    if not HYPOTHESIS_AVAILABLE:
        raise RuntimeError("hypothesis is not installed. Run: pip install hypothesis")

    if field["python_type"] != "Decimal":
        return st.just(" " * field["length"])

    total_digits = field["digits_before"] + field["digits_after"]
    scale = field["digits_after"]
    signed = field.get("signed", False)
    max_int = 10 ** total_digits - 1
    lo = -max_int if signed else 0

    return st.integers(min_value=lo, max_value=max_int).map(
        lambda n: Decimal(n) / Decimal(10 ** scale) if scale else Decimal(n)
    )


def build_record_strategy(fields: list[dict[str, Any]]) -> Any:
    if not HYPOTHESIS_AVAILABLE:
        raise RuntimeError("hypothesis is not installed.")
    return st.fixed_dictionaries({f["field_name"]: _strategy_for_field(f) for f in fields})


# ---------------------------------------------------------------------------
# Golden master helpers
# ---------------------------------------------------------------------------

def _input_hash(record: dict[str, Any]) -> str:
    canonical = json.dumps(
        {k: str(v) for k, v in sorted(record.items())}, sort_keys=True
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _get_golden(program: str, record: dict[str, Any], all_fields: list[dict[str, Any]]) -> bytes:
    """Return cached golden bytes, running COBOL live if not cached."""
    from golden_master.run_legacy import encode_input, run_cobol, input_fields as _in_fields
    h = _input_hash(record)
    cached = ROOT / "golden_master" / "outputs" / program / f"{h}.json"
    if cached.exists():
        return bytes.fromhex(json.loads(cached.read_text())["output_hex"])
    in_fields = _in_fields(all_fields)
    input_bytes = encode_input(record, in_fields)
    return run_cobol(program, input_bytes)


# ---------------------------------------------------------------------------
# Field diff with raw hex
# ---------------------------------------------------------------------------

def _hex_diff(
    program: str,
    golden_bytes: bytes,
    a_bytes: bytes,
    b_bytes: bytes | None,
) -> list[dict[str, str]]:
    """
    Field-level diff including raw hex for any field that differs.
    Falls back to whole-record hex diff if no output fields are in the dictionary.
    """
    from verify.compare import _load_output_fields

    fields = _load_output_fields(program)
    if not fields:
        # No dictionary entries — produce a single byte-level entry
        diffs = []
        if a_bytes != golden_bytes:
            entry: dict[str, str] = {
                "field": "<record>",
                "golden": golden_bytes.hex(),
                "golden_hex": golden_bytes.hex(),
                "a": a_bytes.hex(),
                "a_hex": a_bytes.hex(),
            }
            if b_bytes is not None:
                entry["b"] = b_bytes.hex()
                entry["b_hex"] = b_bytes.hex()
            diffs.append(entry)
        return diffs

    # Build field-level diff based on raw bytes (byte-exact, not decoded values).
    # This catches encoding differences (e.g. sign nibble 0xF vs 0xC) that
    # decode to the same numeric value.
    from verify.compare import _decode_field

    enriched = []
    for f in fields:
        fname = f["field_name"]
        off, length = f["offset"], f["length"]
        g_chunk = golden_bytes[off:off + length]
        a_chunk = a_bytes[off:off + length]
        b_chunk = b_bytes[off:off + length] if b_bytes is not None else None
        if a_chunk == g_chunk and (b_chunk is None or b_chunk == g_chunk):
            continue
        entry = {
            "field": fname,
            "golden": _decode_field(golden_bytes, f),
            "golden_hex": g_chunk.hex(),
            "a": _decode_field(a_bytes, f),
            "a_hex": a_chunk.hex(),
        }
        if b_bytes is not None:
            entry["b"] = _decode_field(b_bytes, f)
            entry["b_hex"] = b_chunk.hex()  # type: ignore[union-attr]
        enriched.append(entry)
    return enriched


# ---------------------------------------------------------------------------
# Core hunt logic
# ---------------------------------------------------------------------------

def run_hunt(
    program: str,
    budget: int = 200,
    variants: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run the adversarial hunt for `program`.

    Returns a result dict:
      - On finding:  {found: True, finding: <Finding dict>}
      - On clean:    {found: False, inputs_tested: N, boundary_classes_covered: [...]}
    """
    if not HYPOTHESIS_AVAILABLE:
        raise RuntimeError("hypothesis is not installed. Run: pip install hypothesis")

    if variants is None:
        variants = ["a", "b"]

    from verify.run_candidate import run_candidate
    from verify.compare import compare, AGREE_CORRECT
    from golden_master.run_legacy import load_dict
    from golden_master.strategies import generate_inputs, BOUNDARY_CLASSES

    all_fields = load_dict(program)
    in_fields = _load_input_fields(program)

    # Generate pinned + boundary seed records so they always run first
    seed_records = generate_inputs(program, count=max(8, len(BOUNDARY_CLASSES)), seed=42)

    finding_box: list[dict[str, Any]] = []
    inputs_tested_box: list[int] = [0]

    def _check_record(record: dict[str, Any]) -> None:
        # Judge everyone on exactly what the COBOL program sees.
        record = normalize(record, in_fields)
        inputs_tested_box[0] += 1

        golden_bytes = _get_golden(program, record, all_fields)
        a_bytes = run_candidate(program, "a", record) if "a" in variants else golden_bytes
        b_bytes = run_candidate(program, "b", record) if "b" in variants else None

        result = compare(program, golden_bytes, a_bytes, b_bytes)
        if result["classification"] != AGREE_CORRECT:
            diff_with_hex = _hex_diff(program, golden_bytes, a_bytes, b_bytes)
            finding_box.append({
                "program": program,
                "minimal_input": {k: str(v) for k, v in record.items()},
                "golden": golden_bytes.hex(),
                "a_output": a_bytes.hex() if a_bytes is not None else None,
                "b_output": b_bytes.hex() if b_bytes is not None else None,
                "diff": diff_with_hex,
                "classification": result["classification"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            raise AssertionError(result["classification"])

    record_strategy = build_record_strategy(in_fields)

    @given(record=record_strategy)
    @settings(
        max_examples=budget,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        database=InMemoryExampleDatabase(),
        phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    )
    def _test(record: dict[str, Any]) -> None:
        _check_record(record)

    # Pinned/boundary cases run first. Stop at the first failure: seeds are
    # already minimal boundary values, so they need no shrinking.
    for seed_record in seed_records:
        try:
            _check_record(seed_record)
        except AssertionError:
            break

    # Run the main Hypothesis search (with shrinking) only if seeds were clean.
    if not finding_box:
        try:
            _test()
        except AssertionError:
            pass  # Finding is captured in finding_box

    if finding_box:
        # Hypothesis replays the minimal failing example last, so the final
        # entry is the shrunk one. For a seed failure there is only one entry.
        return {"found": True, "finding": finding_box[-1]}

    return {
        "found": False,
        "inputs_tested": inputs_tested_box[0],
        "seed_records_run": len(seed_records),
    }


# ---------------------------------------------------------------------------
# Result persistence
# ---------------------------------------------------------------------------

def save_result(result: dict[str, Any], program: str) -> Path:
    """Write finding or clean result to reports/findings/<PROGRAM>.json."""
    FINDINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = FINDINGS_DIR / f"{program}.json"
    path.write_text(json.dumps(result, indent=2))
    return path


# ---------------------------------------------------------------------------
# CLI  —  python -m prosecutor.hunt <PROGRAM> --budget <N>
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Adversarial hunt: find inputs where A, B, and golden disagree."
    )
    p.add_argument("program", help="Program name, e.g. TAXCALC")
    p.add_argument("--budget", type=int, default=200, help="Total Hypothesis examples.")
    p.add_argument("--variants", nargs="+", default=["a", "b"], choices=["a", "b"])
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not HYPOTHESIS_AVAILABLE:
        print("ERROR: hypothesis not installed. Run: pip install hypothesis", file=sys.stderr)
        return 2

    program = args.program.upper()
    print(f"Hunting {program}  budget={args.budget}  variants={args.variants}", flush=True)

    result = run_hunt(program, budget=args.budget, variants=args.variants)
    path = save_result(result, program)

    if result["found"]:
        f = result["finding"]
        print(f"\nFINDING  [{f['classification']}]")
        print(f"  minimal input : {f['minimal_input']}")
        print(f"  golden        : {f['golden']}")
        print(f"  a_output      : {f['a_output']}")
        print(f"  b_output      : {f['b_output']}")
        if f["diff"]:
            print("  field diff:")
            for d in f["diff"]:
                print(f"    {d['field']}")
                print(f"      golden_hex={d.get('golden_hex','?')}  golden={d.get('golden','?')}")
                print(f"      a_hex     ={d.get('a_hex','?')}  a={d.get('a','?')}")
                if "b_hex" in d:
                    print(f"      b_hex     ={d.get('b_hex','?')}  b={d.get('b','?')}")
        print(f"\nSaved → {path}")
        return 1

    print(f"\nCLEAN  inputs_tested={result['inputs_tested']}  "
          f"seed_records_run={result['seed_records_run']}")
    print(f"Saved → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())