"""
tests/verify/test_compare.py — Tests for verify/compare.py

Covers:
 - classify: all 5 result cases
 - compare: field-level diff with correct field names and values
 - No float arithmetic
"""
from __future__ import annotations

import pytest

from verify.compare import (
    classify,
    compare,
    AGREE_CORRECT,
    A_WRONG,
    B_WRONG,
    BOTH_WRONG_SAME,
    BOTH_WRONG_DIFFERENT,
)

GOLDEN = b"0" * 80
A_CORRECT = b"0" * 80
A_WRONG_BYTES = b"1" + b"0" * 79
B_CORRECT = b"0" * 80
B_WRONG_BYTES = b"2" + b"0" * 79


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------

def test_classify_agree_correct_two():
    assert classify(GOLDEN, A_CORRECT) == AGREE_CORRECT


def test_classify_agree_correct_three():
    assert classify(GOLDEN, A_CORRECT, B_CORRECT) == AGREE_CORRECT


def test_classify_a_wrong():
    assert classify(GOLDEN, A_WRONG_BYTES, B_CORRECT) == A_WRONG


def test_classify_b_wrong():
    assert classify(GOLDEN, A_CORRECT, B_WRONG_BYTES) == B_WRONG


def test_classify_both_wrong_same():
    same = b"X" * 80
    assert classify(GOLDEN, same, same) == BOTH_WRONG_SAME


def test_classify_both_wrong_different():
    assert classify(GOLDEN, A_WRONG_BYTES, B_WRONG_BYTES) == BOTH_WRONG_DIFFERENT


def test_classify_a_wrong_no_b():
    assert classify(GOLDEN, A_WRONG_BYTES) == A_WRONG


# ---------------------------------------------------------------------------
# compare — structure
# ---------------------------------------------------------------------------

def test_compare_agree_returns_agree_true():
    result = compare("TAXCALC", GOLDEN, A_CORRECT, B_CORRECT)
    assert result["agree"] is True
    assert result["classification"] == AGREE_CORRECT
    assert result["diff"] == []


def test_compare_a_wrong_returns_agree_false():
    result = compare("TAXCALC", GOLDEN, A_WRONG_BYTES, B_CORRECT)
    assert result["agree"] is False
    assert result["classification"] == A_WRONG


def test_compare_contains_hex():
    result = compare("TAXCALC", GOLDEN, A_CORRECT, B_CORRECT)
    assert "golden_hex" in result
    assert "a_hex" in result
    assert result["golden_hex"] == GOLDEN.hex()


def test_compare_no_b_output():
    result = compare("TAXCALC", GOLDEN, A_CORRECT)
    assert result["b_hex"] is None
    assert result["agree"] is True


# ---------------------------------------------------------------------------
# field diff — real data
# ---------------------------------------------------------------------------

def test_field_diff_taxcalc():
    """Field diff identifies the differing field with decoded Decimal values."""
    from decimal import Decimal
    from golden_master.run_legacy import encode_comp3

    # Build a 'golden' TAXCALC output: TC-OUT-EMP-ID=1, TC-OUT-GROSS=1000.00,
    # TC-TAX-AMOUNT=200.00, TC-BRACKET-TAX=27.50
    golden = bytearray(b" " * 80)
    golden[0:6] = b"000001"
    golden[6:15] = b"000100000"    # 1000.00
    golden[15:24] = b"000020000"   # 200.00
    golden[24:33] = b"000002750"   # 27.50

    # Candidate A: same except TC-TAX-AMOUNT is different
    a_out = bytearray(golden)
    a_out[15:24] = b"000019900"   # 199.00 (wrong)

    result = compare("TAXCALC", bytes(golden), bytes(a_out))
    assert result["agree"] is False
    diff = result["diff"]
    assert len(diff) >= 1
    field_names = [d["field"] for d in diff]
    assert "TC-TAX-AMOUNT" in field_names
    tax_diff = next(d for d in diff if d["field"] == "TC-TAX-AMOUNT")
    assert Decimal(tax_diff["golden"]) == Decimal("200.00")
    assert Decimal(tax_diff["a"]) == Decimal("199.00")
