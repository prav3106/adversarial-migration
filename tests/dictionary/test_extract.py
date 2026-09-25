"""
tests/dictionary/test_extract.py — Tests for dictionary/extract.py

Covers:
 - All 5 programs extract with correct field counts
 - Expected fields appear with correct pic, offset, length, usage, digits_before/after
 - No field has python_type == "float"
 - GROSSPAY has at least one COMP-3 field
 - VALIDATE has at least one unsigned field and at least one signed field
 - dependency_graph.json has correct wave assignments
 - rounding is "half_up" for fields in COMPUTE ... ROUNDED; else "truncate"
 - record_type is "input" or "output" for every field
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dictionary.extract import extract_fields, parse_pic, _expand_pic, _comp3_byte_len

ROOT = Path(__file__).parent.parent.parent
LEGACY_DIR = ROOT / "legacy_source"
DICT_PATH = ROOT / "dictionary" / "data_dictionary.json"
DEP_PATH = ROOT / "dictionary" / "dependency_graph.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_dict() -> list[dict]:
    return json.loads(DICT_PATH.read_text())


def _fields_for(program: str, record_type: str | None = None) -> list[dict]:
    entries = _load_dict()
    result = [e for e in entries if program in e.get("programs", [])]
    if record_type:
        result = [e for e in result if e.get("record_type") == record_type]
    return result


# ---------------------------------------------------------------------------
# _expand_pic
# ---------------------------------------------------------------------------

def test_expand_pic_single():
    assert _expand_pic("9") == "9"


def test_expand_pic_repeat():
    assert _expand_pic("9(3)") == "999"
    assert _expand_pic("X(5)") == "XXXXX"
    assert _expand_pic("9(7)") == "9999999"


def test_expand_pic_with_decimal():
    expanded = _expand_pic("9(4)")
    assert len(expanded) == 4


# ---------------------------------------------------------------------------
# parse_pic
# ---------------------------------------------------------------------------

def test_parse_pic_display_integer():
    info = parse_pic("9(6)", "DISPLAY")
    assert info["digits_before"] == 6
    assert info["digits_after"] == 0
    assert info["length"] == 6
    assert info["python_type"] == "Decimal"


def test_parse_pic_display_with_v():
    info = parse_pic("9(3)V9(2)", "DISPLAY")
    assert info["digits_before"] == 3
    assert info["digits_after"] == 2
    assert info["length"] == 5
    assert info["python_type"] == "Decimal"


def test_parse_pic_signed():
    info = parse_pic("S9(3)V9(2)", "DISPLAY")
    assert info["digits_before"] == 3
    assert info["digits_after"] == 2
    # Signed DISPLAY: sign is overpunch, same byte count as unsigned
    assert info["length"] == 5


def test_parse_pic_comp3():
    # PIC 9(7)V9(2) COMP-3: total 9 digits → ceil((9+1)/2) = 5 bytes
    info = parse_pic("9(7)V9(2)", "COMP-3")
    assert info["length"] == 5
    assert info["digits_before"] == 7
    assert info["digits_after"] == 2


def test_parse_pic_alphanumeric():
    info = parse_pic("X(20)", "DISPLAY")
    assert info["length"] == 20
    assert info["python_type"] == "str"
    assert info["digits_before"] == 0
    assert info["digits_after"] == 0


def test_parse_pic_x1():
    info = parse_pic("X(1)", "DISPLAY")
    assert info["length"] == 1
    assert info["python_type"] == "str"


# ---------------------------------------------------------------------------
# _comp3_byte_len
# ---------------------------------------------------------------------------

def test_comp3_byte_len():
    assert _comp3_byte_len(9) == 5   # 9 digits + 1 sign = 10 nibbles = 5 bytes
    assert _comp3_byte_len(7) == 4   # 7 + 1 = 8 = 4 bytes
    assert _comp3_byte_len(5) == 3   # 5 + 1 = 6 = 3 bytes


# ---------------------------------------------------------------------------
# extract_fields — unit tests per program
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("program,expected_field_count", [
    ("VALIDATE", 9),
    ("GROSSPAY", 7),
    ("TAXCALC",  7),
    ("DEDUCT",   9),
    ("PAYSLIP",  10),
])
def test_field_count(program, expected_field_count):
    entries = _fields_for(program)
    assert len(entries) == expected_field_count, (
        f"{program}: expected {expected_field_count} fields, got {len(entries)}"
    )


def test_no_float_python_type():
    """No field should ever have python_type == 'float'."""
    for entry in _load_dict():
        assert entry["python_type"] != "float", (
            f"Field {entry['field_name']} in {entry['programs']} has python_type=float"
        )


def test_grosspay_has_comp3():
    """GROSSPAY output must have at least one COMP-3 field."""
    out = _fields_for("GROSSPAY", "output")
    comp3 = [f for f in out if f["usage"] == "COMP-3"]
    assert len(comp3) >= 1, "GROSSPAY output has no COMP-3 fields"


def test_validate_has_unsigned_and_signed():
    """VALIDATE input has both an unsigned field and a signed field."""
    in_fields = _fields_for("VALIDATE", "input")
    numeric = [f for f in in_fields if f["python_type"] == "Decimal"]
    unsigned = [f for f in numeric if not f["signed"]]
    signed = [f for f in numeric if f["signed"]]
    assert len(unsigned) >= 1, "VALIDATE has no unsigned numeric field"
    assert len(signed) >= 1, "VALIDATE has no signed numeric field"


def test_validate_hours_worked_signed():
    fields = _fields_for("VALIDATE", "input")
    hw = next(f for f in fields if f["field_name"] == "VL-HOURS-WORKED")
    assert hw["signed"] is True
    assert hw["usage"] == "DISPLAY"


def test_validate_hours_clean_unsigned():
    fields = _fields_for("VALIDATE", "output")
    hc = next(f for f in fields if f["field_name"] == "VL-HOURS-CLEAN")
    assert hc["signed"] is False


def test_taxcalc_rounded_field():
    fields = _fields_for("TAXCALC", "output")
    tax = next(f for f in fields if f["field_name"] == "TC-TAX-AMOUNT")
    assert tax["rounding"] == "half_up"


def test_taxcalc_bracket_not_rounded():
    fields = _fields_for("TAXCALC", "output")
    bracket = next(f for f in fields if f["field_name"] == "TC-BRACKET-TAX")
    assert bracket["rounding"] == "truncate"


def test_deduct_health_rounded():
    fields = _fields_for("DEDUCT", "output")
    health = next(f for f in fields if f["field_name"] == "DD-HEALTH-DED")
    assert health["rounding"] == "half_up"


def test_deduct_retire_not_rounded():
    fields = _fields_for("DEDUCT", "output")
    retire = next(f for f in fields if f["field_name"] == "DD-RETIRE-DED")
    assert retire["rounding"] == "truncate"


def test_payslip_net_pay_signed():
    fields = _fields_for("PAYSLIP", "output")
    net = next(f for f in fields if f["field_name"] == "PS-NET-PAY")
    assert net["signed"] is True


def test_payslip_net_unsigned_field():
    fields = _fields_for("PAYSLIP", "output")
    net_u = next(f for f in fields if f["field_name"] == "PS-NET-UNSIGNED")
    assert net_u["signed"] is False


# ---------------------------------------------------------------------------
# Offset / length sanity checks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("program,field_name,expected_offset,expected_length,rt", [
    # GROSSPAY input
    ("GROSSPAY", "GP-EMP-ID",        0,  6, "input"),
    ("GROSSPAY", "GP-HOURS-WORKED",  6,  5, "input"),
    ("GROSSPAY", "GP-HOURLY-RATE",  11,  6, "input"),
    # GROSSPAY output
    ("GROSSPAY", "GP-OUT-EMP-ID",    0,  6, "output"),
    ("GROSSPAY", "GP-REGULAR-PAY",   6,  5, "output"),   # COMP-3
    ("GROSSPAY", "GP-OVERTIME-PAY", 11,  5, "output"),   # COMP-3
    ("GROSSPAY", "GP-GROSS-PAY",    16,  5, "output"),   # COMP-3
    # TAXCALC input
    ("TAXCALC", "TC-EMP-ID",         0,  6, "input"),
    ("TAXCALC", "TC-GROSS-PAY",      6,  9, "input"),
    ("TAXCALC", "TC-TAX-RATE",      15,  6, "input"),
    # DEDUCT output
    ("DEDUCT", "DD-OUT-EMP-ID",      0,  6, "output"),
    ("DEDUCT", "DD-HEALTH-DED",      6,  7, "output"),
    ("DEDUCT", "DD-RETIRE-DED",     13,  7, "output"),
    ("DEDUCT", "DD-TOTAL-DEDUCT",   20,  7, "output"),
    ("DEDUCT", "DD-AFTER-DEDUCT",   27,  9, "output"),
    # PAYSLIP output
    ("PAYSLIP", "PS-NET-PAY",       31,  9, "output"),
    ("PAYSLIP", "PS-NET-UNSIGNED",  40,  9, "output"),
    # VALIDATE input
    ("VALIDATE", "VL-EMP-ID",        0,  6, "input"),
    ("VALIDATE", "VL-EMP-NAME",      6, 20, "input"),
    ("VALIDATE", "VL-HOURS-WORKED", 26,  5, "input"),
    ("VALIDATE", "VL-HOURLY-RATE",  31,  6, "input"),
])
def test_field_offset_and_length(program, field_name, expected_offset, expected_length, rt):
    fields = _fields_for(program, rt)
    field = next((f for f in fields if f["field_name"] == field_name), None)
    assert field is not None, f"{field_name} not found in {program} {rt}"
    assert field["offset"] == expected_offset, (
        f"{field_name} offset: expected {expected_offset}, got {field['offset']}"
    )
    assert field["length"] == expected_length, (
        f"{field_name} length: expected {expected_length}, got {field['length']}"
    )


# ---------------------------------------------------------------------------
# record_type is always "input" or "output"
# ---------------------------------------------------------------------------

def test_all_fields_have_record_type():
    for e in _load_dict():
        assert e.get("record_type") in ("input", "output"), (
            f"Field {e['field_name']} missing valid record_type"
        )


# ---------------------------------------------------------------------------
# dependency_graph.json
# ---------------------------------------------------------------------------

def test_dependency_graph_waves():
    dep = json.loads(DEP_PATH.read_text())
    assert dep["VALIDATE"]["wave"] == 0
    assert dep["GROSSPAY"]["wave"] == 0
    assert dep["TAXCALC"]["wave"] == 1
    assert dep["DEDUCT"]["wave"] == 1
    assert dep["PAYSLIP"]["wave"] == 2


def test_dependency_graph_deps():
    dep = json.loads(DEP_PATH.read_text())
    assert dep["VALIDATE"]["depends_on"] == []
    assert dep["GROSSPAY"]["depends_on"] == []
    assert "GROSSPAY" in dep["TAXCALC"]["depends_on"]
    assert "GROSSPAY" in dep["DEDUCT"]["depends_on"]
    assert "TAXCALC" in dep["PAYSLIP"]["depends_on"]
    assert "DEDUCT" in dep["PAYSLIP"]["depends_on"]
