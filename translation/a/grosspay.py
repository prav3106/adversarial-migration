"""
translation/a/grosspay.py — GROSSPAY: Gross pay calculation with overtime.

Input dict keys  (COBOL field names as strings):
    GP-EMP-ID        Decimal   9(6)       6 bytes
    GP-HOURS-WORKED  Decimal   9(3)V9(2)  5 bytes
    GP-HOURLY-RATE   Decimal   9(4)V9(2)  6 bytes

Output: 80-byte fixed-width record.

Layout:
    offset  0  len  6  GP-OUT-EMP-ID   9(6)         DISPLAY
    offset  6  len  5  GP-REGULAR-PAY  9(7)V9(2)    COMP-3
    offset 11  len  5  GP-OVERTIME-PAY 9(7)V9(2)    COMP-3
    offset 16  len  5  GP-GROSS-PAY    9(7)V9(2)    COMP-3
    offset 21  len 59  FILLER          X(59)

TRAPs reproduced:
  1. COMPUTE WS-WORK-PAY = WS-REG-HOURS * GP-HOURLY-RATE  (no ROUNDED)
     WS-WORK-PAY is 9(9)V9(4); result truncated at 4 decimal places.
     MOVE WS-WORK-PAY TO GP-REGULAR-PAY (9(7)V9(2) COMP-3) truncates to 2 d.p.
     Two-step truncation: first at V9(4) for WS-WORK-PAY, then at V9(2) for output.

  2. COMPUTE WS-OT-RATE = GP-HOURLY-RATE * 1.5  (no ROUNDED)
     WS-OT-RATE is 9(4)V9(2); result truncated to 2 decimal places.

  3. COMPUTE GP-OVERTIME-PAY = WS-OT-HOURS * WS-OT-RATE  (no ROUNDED)
     GP-OVERTIME-PAY is 9(7)V9(2) COMP-3; overflow truncates high-order digits.

  4. COMPUTE GP-GROSS-PAY = GP-REGULAR-PAY + GP-OVERTIME-PAY  (no ROUNDED)
     GP-GROSS-PAY is 9(7)V9(2) COMP-3; overflow truncates high-order digits.
"""
from __future__ import annotations

from decimal import Decimal

from translation.a._cobol_codec import (
    enc_unsigned_display,
    enc_comp3,
    trunc,
    cobol_trunc_unsigned,
)


def run(record: dict) -> bytes:
    emp_id: Decimal = record["GP-EMP-ID"]
    hours_worked: Decimal = record["GP-HOURS-WORKED"]
    hourly_rate: Decimal = record["GP-HOURLY-RATE"]

    # MOVE GP-EMP-ID TO GP-OUT-EMP-ID
    out_emp_id = enc_unsigned_display(emp_id, 6, 0)

    # IF GP-HOURS-WORKED > 40.00
    if hours_worked > Decimal("40.00"):
        ws_reg_hours = Decimal("40.00")
        ws_ot_hours = trunc(hours_worked - Decimal("40.00"), 2)  # SUBTRACT GIVING
    else:
        ws_reg_hours = trunc(hours_worked, 2)   # MOVE into 9(3)V9(2)
        ws_ot_hours = Decimal("0")

    # TRAP 1: COMPUTE WS-WORK-PAY = WS-REG-HOURS * GP-HOURLY-RATE  (no ROUNDED)
    # WS-WORK-PAY is 9(9)V9(4) — truncate to 4 d.p. then field-width
    ws_work_pay = cobol_trunc_unsigned(ws_reg_hours * hourly_rate, 9, 4)

    # MOVE WS-WORK-PAY TO GP-REGULAR-PAY  (9(7)V9(2) COMP-3 — truncate to 2 d.p.)
    gp_regular_pay = cobol_trunc_unsigned(ws_work_pay, 7, 2)

    # TRAP 2: COMPUTE WS-OT-RATE = GP-HOURLY-RATE * 1.5  (no ROUNDED)
    # WS-OT-RATE is 9(4)V9(2) — truncate to 2 d.p.
    ws_ot_rate = cobol_trunc_unsigned(hourly_rate * Decimal("1.5"), 4, 2)

    # TRAP 3: COMPUTE GP-OVERTIME-PAY = WS-OT-HOURS * WS-OT-RATE  (no ROUNDED)
    # GP-OVERTIME-PAY is 9(7)V9(2) COMP-3 — truncate + overflow truncation
    gp_overtime_pay = cobol_trunc_unsigned(ws_ot_hours * ws_ot_rate, 7, 2)

    # TRAP 4: COMPUTE GP-GROSS-PAY = GP-REGULAR-PAY + GP-OVERTIME-PAY  (no ROUNDED)
    gp_gross_pay = cobol_trunc_unsigned(gp_regular_pay + gp_overtime_pay, 7, 2)

    out_regular = enc_comp3(gp_regular_pay, 7, 2)    # 5 bytes
    out_overtime = enc_comp3(gp_overtime_pay, 7, 2)  # 5 bytes
    out_gross = enc_comp3(gp_gross_pay, 7, 2)        # 5 bytes

    filler = b" " * 59

    output = (
        out_emp_id    # 6
        + out_regular  # 5
        + out_overtime # 5
        + out_gross    # 5
        + filler       # 59
    )                  # = 80
    assert len(output) == 80
    return output
