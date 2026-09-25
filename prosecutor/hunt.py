#!/usr/bin/env python3
"""
prosecutor/hunt.py — Adversarial input search using Hypothesis.

Searches for inputs where translator A, translator B, and the golden master
disagree. On any failure, Hypothesis automatically shrinks to a minimal input.

Each confirmed finding is written to reports/findings/<program>/<timestamp>.json.

Usage:
    python -m prosecutor.hunt --program PAYROLL
    python -m prosecutor.hunt --program PAYROLL --budget 1000 --variants a b

The module can also be imported and called programmatically:
    from prosecutor.hunt import run_hunt
    findings = run_hunt("PAYROLL", budget=500)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
DICT_PATH = ROOT / "dictionary" / "data_dictionary.json"
FINDINGS_DIR = ROOT / "reports" / "findings"

try:
    from hypothesis import given, settings, HealthCheck
    from hypothesis import strategies as st
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

INPUT_FIELD_NAMES = {"EMP-ID", "HOURS-WORKED", "HOURLY-RATE", "TAX-RATE"}


def _load_input_fields(program: str) -> list[dict[str, Any]]:
    entries = json.loads(DICT_PATH.read_text())
    return [e for e in entries if program in e.get("programs", []) and e["field_name"] in INPUT_FIELD_NAMES]


def _field_max_int(field: dict[str, Any]) -> int:
    total = field["digits_before"] + field["digits_after"]
    return 10 ** total - 1


# ---------------------------------------------------------------------------
# Hypothesis strategy builder
# ---------------------------------------------------------------------------

def _strategy_for_field(field: dict[str, Any]) -> Any:
    """Return a Hypothesis strategy that draws values for one input field."""
    if not HYPOTHESIS_AVAILABLE:
        raise RuntimeError("hypothesis is not installed. Run: pip install hypothesis")

    if field["python_type"] != "Decimal":
        return st.just(" " * field["length"])

    max_int = _field_max_int(field)
    scale = field["digits_after"]
    signed = field.get("signed", False)
    lo = -max_int if signed else 0

    return st.integers(min_value=lo, max_value=max_int).map(
        lambda n: Decimal(n) / Decimal(10 ** scale) if scale else Decimal(n)
    )


def build_record_strategy(fields: list[dict[str, Any]]) -> Any:
    """Build a Hypothesis strategy that draws a full input record dict."""
    if not HYPOTHESIS_AVAILABLE:
        raise RuntimeError("hypothesis is not installed.")

    field_strategies = {f["field_name"]: _strategy_for_field(f) for f in fields}
    return st.fixed_dictionaries(field_strategies)


# ---------------------------------------------------------------------------
# Core hunt logic
# ---------------------------------------------------------------------------

def run_hunt(
    program: str,
    budget: int = 500,
    min_per_class: int = 5,
    variants: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Run the adversarial hunt for `program`.
    Returns a list of Finding dicts (possibly empty if all agree).

    Requires:
      - hypothesis installed
      - translated modules present under translation/a/ and translation/b/
      - golden master outputs under golden_master/outputs/<program>/
        OR the COBOL binary present (for on-the-fly golden lookup)

    Finding schema:
      program, minimal_input, golden, a_output, b_output,
      diff, classification, timestamp
    """
    if not HYPOTHESIS_AVAILABLE:
        raise RuntimeError("hypothesis is not installed. Run: pip install hypothesis")

    if variants is None:
        variants = ["a", "b"]

    from verify.run_candidate import run_candidate
    from verify.compare import compare, AGREE_CORRECT
    from golden_master.run_legacy import encode_input, load_dict, run_cobol

    fields = _load_input_fields(program)
    all_fields = load_dict(program)
    findings: list[dict[str, Any]] = []

    def _get_golden(record: dict[str, Any]) -> bytes:
        """Try to find a cached golden; fall back to live COBOL run."""
        import hashlib
        canonical = json.dumps(
            {k: str(v) for k, v in sorted(record.items())}, sort_keys=True
        )
        h = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        cached = ROOT / "golden_master" / "outputs" / program / f"{h}.json"
        if cached.exists():
            return bytes.fromhex(json.loads(cached.read_text())["output_hex"])
        # Live run
        input_bytes = encode_input(record, all_fields)
        return run_cobol(program, input_bytes)

    def _check_record(record: dict[str, Any]) -> None:
        golden_bytes = _get_golden(record)
        a_bytes = run_candidate(program, "a", record) if "a" in variants else golden_bytes
        b_bytes = run_candidate(program, "b", record) if "b" in variants else None

        result = compare(program, golden_bytes, a_bytes, b_bytes)
        if result["classification"] != AGREE_CORRECT:
            findings.append({
                "program": program,
                "minimal_input": {k: str(v) for k, v in record.items()},
                "golden": golden_bytes.hex(),
                "a_output": a_bytes.hex() if a_bytes else None,
                "b_output": b_bytes.hex() if b_bytes else None,
                "diff": result["diff"],
                "classification": result["classification"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            # Raise to let Hypothesis know this example fails (and shrink)
            raise AssertionError(f"Disagreement found: {result['classification']}")

    # Build and run Hypothesis test
    record_strategy = build_record_strategy(fields)

    @given(record=record_strategy)
    @settings(
        max_examples=budget,
        suppress_health_check=[HealthCheck.too_slow],
        deriving=(),  # type: ignore[call-arg]
    )
    def _test(record: dict[str, Any]) -> None:
        _check_record(record)

    try:
        _test()
    except AssertionError:
        pass  # Hypothesis re-raises; findings are already recorded.

    return findings


def save_findings(findings: list[dict[str, Any]], program: str) -> list[Path]:
    """Persist each finding to reports/findings/<program>/."""
    FINDINGS_DIR.mkdir(parents=True, exist_ok=True)
    prog_dir = FINDINGS_DIR / program
    prog_dir.mkdir(exist_ok=True)
    saved = []
    for finding in findings:
        ts = finding["timestamp"].replace(":", "-")
        path = prog_dir / f"{ts}.json"
        path.write_text(json.dumps(finding, indent=2))
        saved.append(path)
    return saved


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Adversarial hunt: find inputs where A, B, and golden disagree.")
    p.add_argument("--program", required=True)
    p.add_argument("--budget", type=int, default=500,
                   help="Total inputs to try per run.")
    p.add_argument("--min-per-class", type=int, default=5, dest="min_per_class")
    p.add_argument("--variants", nargs="+", default=["a", "b"],
                   choices=["a", "b", "naive"])
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not HYPOTHESIS_AVAILABLE:
        print("ERROR: hypothesis not installed. Run: pip install hypothesis", file=sys.stderr)
        return 2

    print(f"Hunting on {args.program} (budget={args.budget}, variants={args.variants})...")
    findings = run_hunt(
        args.program,
        budget=args.budget,
        min_per_class=args.min_per_class,
        variants=args.variants,
    )

    if findings:
        saved = save_findings(findings, args.program)
        print(f"\n{len(findings)} finding(s) saved:")
        for p in saved:
            print(f"  {p}")
        return 1  # Signal findings exist

    print("No disagreements found within budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
