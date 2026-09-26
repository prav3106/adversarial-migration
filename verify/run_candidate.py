#!/usr/bin/env python3
"""
verify/run_candidate.py — Run a translated Python module against an input record.

Each translated module exposes:
    run(record: dict) -> bytes

This runner imports the module, calls run(), and returns the raw output bytes
together with structured metadata for downstream comparison.

Usage:
    python -m verify.run_candidate --program PAYROLL --variant a \
        --input '{"EMP-ID":"000001","HOURS-WORKED":"4000","HOURLY-RATE":"002500","TAX-RATE":"020000"}'
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent


def load_module(program: str, variant: str):
    """
    Dynamically import translation/<variant>/<program>.py.
    variant: 'a', 'b'
    """
    module_path = ROOT / "translation" / variant / f"{program}.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Translated module not found: {module_path}")

    spec_name = f"translation.{variant}.{program}"
    import importlib.util
    spec = importlib.util.spec_from_file_location(spec_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {module_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def run_candidate(program: str, variant: str, record: dict[str, Any]) -> bytes:
    """
    Import and run translation/<variant>/<program>.py.
    Returns raw output bytes.
    """
    mod = load_module(program, variant)
    if not hasattr(mod, "run"):
        raise AttributeError(f"Module translation/{variant}/{program}.py must expose run(record) -> bytes")
    result = mod.run(record)
    if not isinstance(result, bytes):
        raise TypeError(f"run() must return bytes, got {type(result).__name__}")
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a translated Python module on an input record.")
    p.add_argument("--program", required=True)
    p.add_argument("--variant", required=True, choices=["a", "b"],
                   help="Translation variant to run.")
    p.add_argument("--input", required=True,
                   help="JSON object of field_name -> value.")
    p.add_argument("--out", default="-", help="Output JSON file (default: stdout).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    raw = json.loads(args.input)
    record: dict[str, Any] = {k: Decimal(str(v)) for k, v in raw.items()}

    try:
        output = run_candidate(args.program, args.variant, record)
    except (FileNotFoundError, ImportError, AttributeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = {
        "program": args.program,
        "variant": args.variant,
        "input": {k: str(v) for k, v in record.items()},
        "output_hex": output.hex(),
    }
    out = json.dumps(result, indent=2)
    if args.out == "-":
        print(out)
    else:
        Path(args.out).write_text(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
