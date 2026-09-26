"""
translation/a/validate.py — VALIDATE: Employee record validation.

Input dict keys  (COBOL field names as strings):
    VL-EMP-ID        Decimal   9(6)        6 bytes
    VL-EMP-NAME      str       X(20)      20 bytes
    VL-HOURS-WORKED  Decimal   S9(3)V9(2)  5 bytes  (signed DISPLAY, may be negative)
    VL-HOURLY-RATE   Decimal   9(4)V9(2)   6 bytes

Output: 80-byte fixed-width record.

Layout:
    offset  0  len  6  VL-OUT-EMP-ID    9(6)
    offset  6  len 20  VL-OUT-EMP-NAME  X(20)
    offset 26  len  5  VL-HOURS-CLEAN   9(3)V9(2)   (unsigned)
    offset 31  len  6  VL-HOURLY-CLEAN  9(4)V9(2)
    offset 37  len  1  VL-VALID-FLAG    X(1)
    offset 38  len 42  FILLER           X(42)

TRAP reproduced:
    MOVE VL-HOURS-WORKED TO VL-HOURS-CLEAN — signed S9(3)V9(2) moved into
    unsigned 9(3)V9(2).  COBOL drops the sign; negative hours become their
    absolute value.  Implemented: hours_clean = abs(hours_worked).
"""
from __future__ import annotations

from decimal import Decimal

from translation.a._cobol_codec import enc_unsigned_display


def run(record: dict) -> bytes:
    emp_id: Decimal = record["VL-EMP-ID"]
    emp_name: str = record["VL-EMP-NAME"]
    hours_worked: Decimal = record["VL-HOURS-WORKED"]
    hourly_rate: Decimal = record["VL-HOURLY-RATE"]

    # MOVE VL-EMP-ID TO VL-OUT-EMP-ID
    out_emp_id = enc_unsigned_display(emp_id, 6, 0)

    # MOVE VL-EMP-NAME TO VL-OUT-EMP-NAME  (X(20): pad right with spaces)
    name_bytes = emp_name.encode("ascii")[:20].ljust(20, b" ")

    # TRAP: MOVE signed -> unsigned drops sign; negative -> absolute value
    hours_clean = abs(hours_worked)
    out_hours_clean = enc_unsigned_display(hours_clean, 3, 2)

    # MOVE VL-HOURLY-RATE TO VL-HOURLY-CLEAN
    out_hourly_clean = enc_unsigned_display(hourly_rate, 4, 2)

    # IF VL-HOURLY-RATE > ZEROS AND VL-HOURS-CLEAN > ZEROS
    valid_flag = b"Y" if (hourly_rate > 0 and hours_clean > 0) else b"N"

    # FILLER X(42)
    filler = b" " * 42

    output = (
        out_emp_id          # 6
        + name_bytes        # 20
        + out_hours_clean   # 5
        + out_hourly_clean  # 6
        + valid_flag        # 1
        + filler            # 42
    )                       # = 80
    assert len(output) == 80
    return output
