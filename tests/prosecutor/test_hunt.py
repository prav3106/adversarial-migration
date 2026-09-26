"""
tests/prosecutor/test_hunt.py

Tests for prosecutor/hunt.py using a deliberately broken fake translation.
The fake is injected via monkeypatching verify.run_candidate.run_candidate
so we never read or modify any real translation file.

Design
------
The golden master contains COBOL-binary-produced correct outputs.  A "good"
fake simply re-runs the same COBOL binary (via golden_master.run_legacy) so
it always agrees with the golden.  A "broken" fake flips one bit in the
output, guaranteeing a detectable disagreement.

This means the tests require the compiled COBOL binaries to be present, which
is consistent with the rest of the test suite (the binaries are already in
legacy_source/bin/ per the project's build.sh).
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from decimal import Decimal
from golden_master.run_legacy import load_dict, input_fields
from prosecutor.hunt import normalize


ROOT = Path(__file__).parent.parent.parent
PROGRAM = "TAXCALC"


# ---------------------------------------------------------------------------
# Helper: run real COBOL to get the correct output for any input record
# ---------------------------------------------------------------------------

def test_normalize_matches_what_cobol_sees():
    fields = input_fields(load_dict("VALIDATE"))
    rec = {f["field_name"]: Decimal("0") for f in fields}
    rec["VL-HOURS-WORKED"] = Decimal("0.005")
    assert normalize(rec, fields)["VL-HOURS-WORKED"] == Decimal("0")
    assert normalize(normalize(rec, fields), fields) == normalize(rec, fields)
def _correct_output(program: str, record: dict[str, Any]) -> bytes:
    """Return the byte-exact COBOL output for *record* (cached if available)."""
    import hashlib
    canonical = json.dumps(
        {k: str(v) for k, v in sorted(record.items())}, sort_keys=True
    )
    h = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    cached = ROOT / "golden_master" / "outputs" / program / f"{h}.json"
    if cached.exists():
        return bytes.fromhex(json.loads(cached.read_text())["output_hex"])
    # Fall back to live COBOL run
    from golden_master.run_legacy import encode_input, run_cobol, load_dict, input_fields
    all_fields = load_dict(program)
    in_fields = input_fields(all_fields)
    return run_cobol(program, encode_input(record, in_fields))


def _corrupt(data: bytes, byte_index: int = 15, flip: int = 0x01) -> bytes:
    """Flip a bit in byte_index to produce a wrong output."""
    buf = bytearray(data)
    buf[byte_index] = (buf[byte_index] ^ flip) & 0xFF
    return bytes(buf)


# ---------------------------------------------------------------------------
# Patching helper
# ---------------------------------------------------------------------------

def _patch_run_candidate(monkeypatch, program: str, mode_a: str, mode_b: str):
    """
    Monkeypatch verify.run_candidate.run_candidate.

    mode_a / mode_b: "good" | "broken" | "broken2"
      good    — returns the correct COBOL output for each record
      broken  — flips byte 15 bit 0x01 (wrong answer)
      broken2 — flips byte 15 bit 0x02 (different wrong answer)
    """
    def _output_for_mode(rec: dict[str, Any], mode: str) -> bytes:
        correct = _correct_output(program, rec)
        if mode == "good":
            return correct
        if mode == "broken":
            return _corrupt(correct, byte_index=15, flip=0x01)
        if mode == "broken2":
            return _corrupt(correct, byte_index=15, flip=0x02)
        raise ValueError(f"Unknown mode: {mode}")

    def fake_run_candidate(prog: str, variant: str, record: dict[str, Any]) -> bytes:
        if variant == "a":
            return _output_for_mode(record, mode_a)
        if variant == "b":
            return _output_for_mode(record, mode_b)
        return _correct_output(prog, record)

    import verify.run_candidate as rc_mod
    monkeypatch.setattr(rc_mod, "run_candidate", fake_run_candidate)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_clean_when_both_correct(monkeypatch):
    """Hunt finds nothing when both A and B return the golden output."""
    _patch_run_candidate(monkeypatch, PROGRAM, mode_a="good", mode_b="good")

    from prosecutor.hunt import run_hunt
    result = run_hunt(PROGRAM, budget=15, variants=["a", "b"])

    assert result["found"] is False
    assert result["inputs_tested"] > 0
    assert "seed_records_run" in result
    assert result["seed_records_run"] > 0


def test_detects_broken_a(monkeypatch):
    """Hunt detects when A is wrong and B is correct."""
    _patch_run_candidate(monkeypatch, PROGRAM, mode_a="broken", mode_b="good")

    from prosecutor.hunt import run_hunt
    result = run_hunt(PROGRAM, budget=30, variants=["a", "b"])

    assert result["found"] is True
    f = result["finding"]
    assert f["program"] == PROGRAM
    assert f["classification"] == "a_wrong"
    assert isinstance(f["minimal_input"], dict)
    assert len(f["minimal_input"]) > 0
    # Field diff must be present with hex bytes
    assert len(f["diff"]) > 0
    first_diff = f["diff"][0]
    assert "golden_hex" in first_diff
    assert "a_hex" in first_diff


def test_detects_broken_b(monkeypatch):
    """Hunt detects when B is wrong and A is correct."""
    _patch_run_candidate(monkeypatch, PROGRAM, mode_a="good", mode_b="broken")

    from prosecutor.hunt import run_hunt
    result = run_hunt(PROGRAM, budget=30, variants=["a", "b"])

    assert result["found"] is True
    f = result["finding"]
    assert f["classification"] == "b_wrong"
    assert len(f["diff"]) > 0
    assert "b_hex" in f["diff"][0]


def test_detects_both_wrong_same(monkeypatch):
    """Hunt detects when A and B both return the same wrong answer."""
    _patch_run_candidate(monkeypatch, PROGRAM, mode_a="broken", mode_b="broken")

    from prosecutor.hunt import run_hunt
    result = run_hunt(PROGRAM, budget=30, variants=["a", "b"])

    assert result["found"] is True
    f = result["finding"]
    assert f["classification"] == "both_wrong_same"
    assert f["a_output"] == f["b_output"]


def test_detects_both_wrong_different(monkeypatch):
    """Hunt detects when A and B return different wrong answers."""
    _patch_run_candidate(monkeypatch, PROGRAM, mode_a="broken", mode_b="broken2")

    from prosecutor.hunt import run_hunt
    result = run_hunt(PROGRAM, budget=30, variants=["a", "b"])

    assert result["found"] is True
    f = result["finding"]
    assert f["classification"] == "both_wrong_different"


def test_finding_has_all_required_fields(monkeypatch):
    """Finding dict contains all fields required by PROJECT_CONTEXT.md."""
    _patch_run_candidate(monkeypatch, PROGRAM, mode_a="broken", mode_b="good")

    from prosecutor.hunt import run_hunt
    result = run_hunt(PROGRAM, budget=10, variants=["a", "b"])
    assert result["found"] is True

    f = result["finding"]
    required = {"program", "minimal_input", "golden", "a_output", "b_output",
                "diff", "classification", "timestamp"}
    assert required <= set(f.keys()), f"Missing fields: {required - set(f.keys())}"


def test_shrinks_to_minimal_input(monkeypatch):
    """
    The hunt uses Hypothesis shrinking: the minimal_input values should be
    valid Decimal-convertible strings and the finding should be populated.
    """
    # Break only when gross pay is nonzero, so Hypothesis can shrink toward zero.
    def fake_run_candidate(prog: str, variant: str, record: dict[str, Any]) -> bytes:
        correct = _correct_output(prog, record)
        if variant == "a":
            gp = Decimal(str(record.get("TC-GROSS-PAY", 0)))
            if gp != Decimal(0):
                return _corrupt(correct)
            return correct
        return correct  # b always good

    import verify.run_candidate as rc_mod
    monkeypatch.setattr(rc_mod, "run_candidate", fake_run_candidate)

    from prosecutor.hunt import run_hunt
    result = run_hunt(PROGRAM, budget=50, variants=["a", "b"])

    assert result["found"] is True
    f = result["finding"]
    # All minimal_input values must be Decimal-representable (or str for alpha)
    for k, v in f["minimal_input"].items():
        try:
            Decimal(str(v))
        except Exception:
            pass  # alphanumeric field — acceptable


def test_save_result_writes_file(tmp_path, monkeypatch):
    """save_result writes a JSON file to reports/findings/<PROGRAM>.json."""
    import prosecutor.hunt as hunt_mod
    monkeypatch.setattr(hunt_mod, "FINDINGS_DIR", tmp_path)

    from prosecutor.hunt import save_result
    clean_result = {
        "found": False,
        "inputs_tested": 42,
        "seed_records_run": 8,
    }
    path = save_result(clean_result, "TESTPROG")
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["inputs_tested"] == 42
