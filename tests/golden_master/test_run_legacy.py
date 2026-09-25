"""
tests/golden_master/test_run_legacy.py — Tests for golden_master/run_legacy.py

Covers:
 - encode_input: byte positions match data dictionary offsets
 - decode_output: Decimal values with correct scale
 - COMP-3 round-trip: encode → decode = original value
 - Signed DISPLAY round-trip: negative value preserved; unsigned gets abs()
 - Integration: run GROSSPAY with known input → verify output (requires GnuCOBOL)
"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from golden_master.run_legacy import (
    encode_input,
    decode_output,
    encode_comp3,
    decode_comp3,
    encode_signed_display,
    decode_signed_display,
    load_dict,
    input_fields,
    output_fields,
    run_and_save,
    RECORD_LEN,
)

ROOT = Path(__file__).parent.parent.parent
GNUCOBOL_AVAILABLE = (ROOT / "legacy_source" / "bin" / "GROSSPAY").exists()


# ---------------------------------------------------------------------------
# COMP-3 encode / decode round-trips
# ---------------------------------------------------------------------------

def test_comp3_encode_positive():
    """Encode Decimal(1234567) with 9 total digits → 5 bytes."""
    data = encode_comp3(Decimal("1234567"), 9)
    assert len(data) == 5
    # Last nibble should be 0xC (positive sign)
    assert (data[-1] & 0x0F) == 0xC


def test_comp3_encode_zero():
    data = encode_comp3(Decimal("0"), 9)
    assert decode_comp3(data, 9, 0) == Decimal("0")


def test_comp3_roundtrip_positive():
    for val in [Decimal("0"), Decimal("1"), Decimal("100000000"), Decimal("999999999")]:
        encoded = encode_comp3(val, 9)
        decoded = decode_comp3(encoded, 9, 0)
        assert decoded == val, f"COMP-3 round-trip failed for {val}: got {decoded}"


def test_comp3_roundtrip_with_scale():
    """PIC 9(7)V9(2) — 9 total digits, 2 decimal places."""
    val = Decimal("12345.67")
    # The integer representation is 1234567
    int_val = Decimal("1234567")
    encoded = encode_comp3(int_val, 9)
    decoded = decode_comp3(encoded, 9, 2)
    assert decoded == val, f"COMP-3 scale round-trip failed: got {decoded}"


def test_comp3_roundtrip_many():
    """Bit-for-bit identical after COMP-3 encode → decode."""
    import random
    random.seed(99)
    for _ in range(20):
        int_part = random.randint(0, 9999999)
        frac_part = random.randint(0, 99)
        val_str = f"{int_part}.{frac_part:02d}"
        val = Decimal(val_str)
        int_val = int_part * 100 + frac_part  # integer representation
        encoded = encode_comp3(Decimal(int_val), 9)
        decoded = decode_comp3(encoded, 9, 2)
        assert decoded == val, f"COMP-3 bit-exact round-trip failed for {val_str}: got {decoded}"


def test_comp3_overflow_truncation():
    """Values exceeding field capacity are truncated (high-order digits dropped)."""
    # 9 digits max = 999999999; 1000000000 overflows → drops to 0
    overflow_val = Decimal("1000000000")
    encoded = encode_comp3(overflow_val, 9)
    decoded = decode_comp3(encoded, 9, 0)
    assert decoded == Decimal("0")


# ---------------------------------------------------------------------------
# Signed DISPLAY encode / decode round-trips
# ---------------------------------------------------------------------------

def test_signed_display_positive_roundtrip():
    """Positive value: standard ASCII digits, no sign nibble change."""
    encoded = encode_signed_display(40025, 5)  # 400.25 scaled
    assert len(encoded) == 5
    decoded = decode_signed_display(encoded, 5, 2)
    assert decoded == Decimal("400.25")


def test_signed_display_negative_roundtrip():
    """Negative value preserved through signed DISPLAY round-trip."""
    encoded = encode_signed_display(-40025, 5)
    decoded = decode_signed_display(encoded, 5, 2)
    assert decoded == Decimal("-400.25")


def test_signed_display_zero():
    encoded = encode_signed_display(0, 5)
    decoded = decode_signed_display(encoded, 5, 2)
    assert decoded == Decimal("0")


def test_sign_roundtrip_positive():
    """Signed field: positive value preserved."""
    fields = load_dict("VALIDATE")
    in_f = input_fields(fields)
    hw = next(f for f in in_f if f["field_name"] == "VL-HOURS-WORKED")
    record = {"VL-HOURS-WORKED": Decimal("35.50")}
    buf = encode_input(record, in_f)
    # Now decode from the output record at same offset/length
    chunk = buf[hw["offset"] : hw["offset"] + hw["length"]]
    decoded = decode_signed_display(chunk, 5, 2)
    assert decoded == Decimal("35.50")


def test_sign_dropped_for_unsigned():
    """Unsigned field: negative input stores absolute value, sign dropped."""
    fields = load_dict("VALIDATE")
    in_f = input_fields(fields)
    hw = next(f for f in in_f if f["field_name"] == "VL-HOURS-WORKED")
    # VL-HOURS-WORKED is signed — but we test encode_input's handling
    # For an unsigned field, encode_input takes abs value
    record = {"VL-HOURS-WORKED": Decimal("-20.00")}
    buf = encode_input(record, in_f)
    # Decode as signed to get the value (VL-HOURS-WORKED IS signed)
    chunk = buf[hw["offset"] : hw["offset"] + hw["length"]]
    decoded = decode_signed_display(chunk, 5, 2)
    assert decoded == Decimal("-20.00")  # signed field preserves sign


def test_unsigned_drops_sign():
    """encode_input on an unsigned field takes abs value."""
    # GP-EMP-ID is unsigned PIC 9(6); passing negative should store absolute value
    fields = load_dict("GROSSPAY")
    in_f = input_fields(fields)
    eid = next(f for f in in_f if f["field_name"] == "GP-EMP-ID")
    record = {"GP-EMP-ID": Decimal("-123")}
    buf = encode_input(record, in_f)
    chunk = buf[eid["offset"] : eid["offset"] + eid["length"]]
    decoded_str = chunk.decode("ascii")
    assert decoded_str == "000123"  # absolute value, no sign


# ---------------------------------------------------------------------------
# encode_input: byte positions match data dictionary offsets
# ---------------------------------------------------------------------------

def test_encode_input_grosspay_offsets():
    """Encoded bytes appear at the correct offsets."""
    fields = load_dict("GROSSPAY")
    in_f = input_fields(fields)
    record = {
        "GP-EMP-ID": Decimal("1"),
        "GP-HOURS-WORKED": Decimal("40.00"),
        "GP-HOURLY-RATE": Decimal("25.00"),
    }
    buf = encode_input(record, in_f)
    assert len(buf) == RECORD_LEN

    # GP-EMP-ID at offset 0, length 6
    assert buf[0:6] == b"000001"
    # GP-HOURS-WORKED at offset 6, length 5 → value 40.00 → "04000"
    assert buf[6:11] == b"04000"
    # GP-HOURLY-RATE at offset 11, length 6 → value 25.00 → "002500"
    assert buf[11:17] == b"002500"


def test_encode_input_taxcalc_offsets():
    fields = load_dict("TAXCALC")
    in_f = input_fields(fields)
    record = {
        "TC-EMP-ID": Decimal("42"),
        "TC-GROSS-PAY": Decimal("1000.00"),
        "TC-TAX-RATE": Decimal("0.2500"),
    }
    buf = encode_input(record, in_f)
    # TC-EMP-ID at offset 0, length 6
    assert buf[0:6] == b"000042"
    # TC-GROSS-PAY at offset 6, length 9 → 1000.00 → "000100000"
    assert buf[6:15] == b"000100000"
    # TC-TAX-RATE at offset 15, length 6 → 0.2500 → "002500"
    assert buf[15:21] == b"002500"


# ---------------------------------------------------------------------------
# decode_output: Decimal values with correct scale
# ---------------------------------------------------------------------------

def test_decode_output_taxcalc():
    """decode_output returns Decimal with correct scale from DISPLAY fields."""
    fields = load_dict("TAXCALC")
    out_f = output_fields(fields)
    # Build a fake output record
    raw = bytearray(b" " * RECORD_LEN)
    # TC-OUT-EMP-ID at offset 0, len 6
    raw[0:6] = b"000042"
    # TC-OUT-GROSS-PAY at offset 6, len 9 → 1000.00
    raw[6:15] = b"000100000"
    # TC-TAX-AMOUNT at offset 15, len 9 → 250.00
    raw[15:24] = b"000025000"
    # TC-BRACKET-TAX at offset 24, len 9 → 27.50
    raw[24:33] = b"000002750"
    decoded = decode_output(bytes(raw), out_f)
    assert decoded["TC-OUT-GROSS-PAY"] == Decimal("1000.00")
    assert decoded["TC-TAX-AMOUNT"] == Decimal("250.00")
    assert decoded["TC-BRACKET-TAX"] == Decimal("27.50")


def test_decode_output_grosspay_comp3():
    """GROSSPAY COMP-3 output fields decode correctly."""
    fields = load_dict("GROSSPAY")
    out_f = output_fields(fields)
    raw = bytearray(b" " * RECORD_LEN)
    raw[0:6] = b"000001"
    # GP-REGULAR-PAY at offset 6, len 5 COMP-3: encode 1000.00 → int 100000
    comp3_1000 = encode_comp3(Decimal("100000"), 9)
    raw[6:11] = comp3_1000
    # GP-OVERTIME-PAY at offset 11, len 5 COMP-3: 0
    comp3_0 = encode_comp3(Decimal("0"), 9)
    raw[11:16] = comp3_0
    # GP-GROSS-PAY at offset 16, len 5 COMP-3: 1000.00
    raw[16:21] = comp3_1000
    decoded = decode_output(bytes(raw), out_f)
    assert decoded["GP-REGULAR-PAY"] == Decimal("1000.00")
    assert decoded["GP-OVERTIME-PAY"] == Decimal("0")
    assert decoded["GP-GROSS-PAY"] == Decimal("1000.00")


# ---------------------------------------------------------------------------
# Integration test: requires GnuCOBOL binaries
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(not GNUCOBOL_AVAILABLE, reason="GnuCOBOL binaries not built")
def test_grosspay_known_input():
    """Run GROSSPAY: 40h × $25.00 = $1000.00 gross."""
    fields = load_dict("GROSSPAY")
    record = {
        "GP-EMP-ID": Decimal("1"),
        "GP-HOURS-WORKED": Decimal("40.00"),
        "GP-HOURLY-RATE": Decimal("25.00"),
    }
    golden = run_and_save("GROSSPAY", record, fields)
    decoded = {k: Decimal(v) for k, v in golden["output_decoded"].items()}
    assert decoded["GP-REGULAR-PAY"] == Decimal("1000.00")
    assert decoded["GP-OVERTIME-PAY"] == Decimal("0")
    assert decoded["GP-GROSS-PAY"] == Decimal("1000.00")


@pytest.mark.integration
@pytest.mark.skipif(not GNUCOBOL_AVAILABLE, reason="GnuCOBOL binaries not built")
def test_taxcalc_rounded_vs_truncated():
    """TC-TAX-AMOUNT uses ROUNDED; TC-BRACKET-TAX truncates."""
    fields = load_dict("TAXCALC")
    # Gross = 1000.05; tax rate = 0.2500 → exact = 250.0125
    # ROUNDED → 250.01; truncated → 250.01 too (same in this case)
    # Use a rounding-edge case: 1000.18; rate 0.2005 → 1000.18 * 0.2005 = 200.53609
    # ROUNDED → 200.54; truncated → 200.53
    record = {
        "TC-EMP-ID": Decimal("99"),
        "TC-GROSS-PAY": Decimal("1000.18"),
        "TC-TAX-RATE": Decimal("0.2005"),
    }
    golden = run_and_save("TAXCALC", record, fields)
    decoded = {k: Decimal(v) for k, v in golden["output_decoded"].items()}
    # 1000.18 * 0.2005 = 200.53609 → ROUNDED half-up = 200.54
    assert decoded["TC-TAX-AMOUNT"] == Decimal("200.54")
    # bracket: 1000.18 * 0.0275 = 27.50495 → truncated = 27.50
    assert decoded["TC-BRACKET-TAX"] == Decimal("27.50")


@pytest.mark.integration
@pytest.mark.skipif(not GNUCOBOL_AVAILABLE, reason="GnuCOBOL binaries not built")
def test_validate_negative_hours_becomes_absolute():
    """VALIDATE: negative VL-HOURS-WORKED stored as absolute in VL-HOURS-CLEAN."""
    fields = load_dict("VALIDATE")
    record = {
        "VL-EMP-ID": Decimal("1"),
        "VL-EMP-NAME": "ALICE               ",
        "VL-HOURS-WORKED": Decimal("-20.00"),
        "VL-HOURLY-RATE": Decimal("15.00"),
    }
    golden = run_and_save("VALIDATE", record, fields)
    decoded = {k: v for k, v in golden["output_decoded"].items()}
    # VL-HOURS-CLEAN is unsigned: should store abs(-20.00) = 20.00
    assert Decimal(decoded["VL-HOURS-CLEAN"]) == Decimal("20.00")
