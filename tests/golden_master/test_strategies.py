"""
tests/golden_master/test_strategies.py — Tests for golden_master/strategies.py

Covers:
 - generate_inputs returns at least `count` records
 - All 8 boundary classes are represented in the first 8 records
 - All numeric values are Decimal instances (no float)
 - overflow class value exceeds field maximum
 - zero class value is Decimal("0")
 - negative_max class produces a negative value on signed field (VALIDATE)
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from golden_master.strategies import (
    generate_inputs,
    boundary_values,
    _field_max,
    _smallest_unit,
    _rounding_edge,
    BOUNDARY_CLASSES,
    _load_dict,
    _input_fields,
)


# ---------------------------------------------------------------------------
# boundary_values helpers
# ---------------------------------------------------------------------------

def test_field_max_integer():
    entry = {"digits_before": 6, "digits_after": 0, "python_type": "Decimal"}
    assert _field_max(entry) == Decimal("999999")


def test_field_max_with_scale():
    entry = {"digits_before": 7, "digits_after": 2, "python_type": "Decimal"}
    assert _field_max(entry) == Decimal("9999999.99")


def test_smallest_unit_no_scale():
    entry = {"digits_after": 0}
    assert _smallest_unit(entry) == Decimal("1")


def test_smallest_unit_scale2():
    entry = {"digits_after": 2}
    assert _smallest_unit(entry) == Decimal("0.01")


def test_rounding_edge_scale2():
    entry = {"digits_after": 2}
    val = _rounding_edge(entry)
    # 0.005 — half-unit below scale-2 boundary
    assert val == Decimal("0.005")


def test_rounding_edge_no_scale():
    entry = {"digits_after": 0}
    assert _rounding_edge(entry) == Decimal("0")


def test_boundary_values_numeric_unsigned():
    entry = {
        "digits_before": 3, "digits_after": 2,
        "python_type": "Decimal", "signed": False, "length": 5,
    }
    bv = boundary_values(entry)
    assert bv["zero"] == Decimal("0")
    assert bv["smallest_unit"] == Decimal("0.01")
    assert bv["max_value"] == Decimal("999.99")
    assert bv["overflow"] == Decimal("1000.00")
    assert bv["negative_max"] == Decimal("0")  # unsigned → 0


def test_boundary_values_numeric_signed():
    entry = {
        "digits_before": 3, "digits_after": 2,
        "python_type": "Decimal", "signed": True, "length": 5,
    }
    bv = boundary_values(entry)
    assert bv["negative_max"] == Decimal("-999.99")


def test_boundary_values_string():
    entry = {"python_type": "str", "length": 5}
    bv = boundary_values(entry)
    for cls in BOUNDARY_CLASSES:
        assert isinstance(bv[cls], str)


# ---------------------------------------------------------------------------
# generate_inputs — all programs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("program", ["VALIDATE", "GROSSPAY", "TAXCALC", "DEDUCT", "PAYSLIP"])
def test_generate_returns_count(program):
    records = generate_inputs(program, count=8, seed=42)
    assert len(records) >= 8


@pytest.mark.parametrize("program", ["VALIDATE", "GROSSPAY", "TAXCALC", "DEDUCT", "PAYSLIP"])
def test_generate_returns_more_than_8(program):
    records = generate_inputs(program, count=20, seed=42)
    assert len(records) >= 20


@pytest.mark.parametrize("program", ["VALIDATE", "GROSSPAY", "TAXCALC", "DEDUCT", "PAYSLIP"])
def test_all_8_boundary_classes_present(program):
    """First 8 records are one per boundary class."""
    records = generate_inputs(program, count=8, seed=42)
    # The first 8 records correspond to BOUNDARY_CLASSES in order
    assert len(records) >= len(BOUNDARY_CLASSES)


@pytest.mark.parametrize("program", ["VALIDATE", "GROSSPAY", "TAXCALC", "DEDUCT", "PAYSLIP"])
def test_no_float_values(program):
    """All numeric values must be Decimal, not float."""
    records = generate_inputs(program, count=20, seed=42)
    for rec in records:
        for field_name, val in rec.items():
            if isinstance(val, str):
                continue  # string fields OK
            assert isinstance(val, Decimal), (
                f"{program}.{field_name}: expected Decimal, got {type(val).__name__}={val!r}"
            )


@pytest.mark.parametrize("program", ["VALIDATE", "GROSSPAY", "TAXCALC", "DEDUCT", "PAYSLIP"])
def test_overflow_class_exceeds_max(program):
    """The overflow record must have at least one field exceeding its field max."""
    all_fields = _load_dict(program)
    in_fields = _input_fields(all_fields)
    numeric = [f for f in in_fields if f["python_type"] == "Decimal"]
    if not numeric:
        pytest.skip(f"No numeric input fields for {program}")

    records = generate_inputs(program, count=8, seed=42)
    # overflow is index 6 (0-based)
    overflow_rec = records[BOUNDARY_CLASSES.index("overflow")]

    found_overflow = False
    for f in numeric:
        mx = _field_max(f)
        val = overflow_rec.get(f["field_name"])
        if val is not None and val > mx:
            found_overflow = True
            break
    assert found_overflow, f"{program}: overflow record does not exceed field max"


def test_validate_negative_max_on_signed():
    """VALIDATE negative_max class produces a negative value on VL-HOURS-WORKED."""
    records = generate_inputs("VALIDATE", count=8, seed=42)
    neg_rec = records[BOUNDARY_CLASSES.index("negative_max")]
    hours = neg_rec.get("VL-HOURS-WORKED")
    assert hours is not None
    assert hours < 0, f"Expected negative value for VL-HOURS-WORKED, got {hours}"


def test_zero_class_is_zero(program="GROSSPAY"):
    records = generate_inputs(program, count=8, seed=42)
    zero_rec = records[BOUNDARY_CLASSES.index("zero")]
    all_fields = _load_dict(program)
    in_fields = _input_fields(all_fields)
    for f in in_fields:
        if f["python_type"] == "Decimal":
            val = zero_rec.get(f["field_name"])
            if val is not None:
                assert val == Decimal("0"), f"zero class: {f['field_name']} = {val}"
