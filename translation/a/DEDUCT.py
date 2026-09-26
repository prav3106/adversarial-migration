"""
translation/a/deduct.py — DEDUCT: Payroll deductions (health, retirement).

Input dict keys  (COBOL field names as strings):
    DD-EMP-ID           Decimal   9(6)       6 bytes
    DD-GROSS-PAY        Decimal   9(7)V9(2)  9 bytes
    DD-HEALTH-RATE      Decimal   9(2)V9(4)  6 bytes
    DD-RETIREMENT-RATE  Decimal   9(2)V9(4)  6 bytes

Output: 80-byte fixed-width record.

Layout:
    offset  0  len  6  DD-OUT-EMP-ID   9(6)       DISPLAY
    offset  6  len  7  DD-HEALTH-DED   9(5)V9(2)  DISPLAY
    offset 13  len  7  DD-RETIRE-DED   9(5)V9(2)  DISPLAY
    offset 20  len  7  DD-TOTAL-DEDUCT 9(5)V9(2)  DISPLAY
    offset 27  len  9  DD-AFTER-DEDUCT 9(7)V9(2)  DISPLAY
    offset 36  len 44  FILLER          X(44)

TRAPs reproduced:
  1. COMPUTE DD-HEALTH-DED ROUNDED = DD-GROSS-PAY * DD-HEALTH-RATE
     ROUNDED -> ROUND_HALF_UP to 2 d.p.; then fit into 9(5)V9(2) (overflow truncates).

  2. COMPUTE WS-RETIRE-WORK = DD-GROSS-PAY * DD-RETIREMENT-RATE  (no ROUNDED)
     WS-RETIRE-WORK is 9(9)V9(4) — truncated to 4 d.p.
     MOVE WS-RETIRE-WORK TO DD-RETIRE-DED (9(5)V9(2)) — truncated to 2 d.p.
     Mixed ROUNDED/non-ROUNDED in same paragraph.

  3. COMPUTE DD-TOTAL-DEDUCT = DD-HEALTH-DED + DD-RETIRE-DED  (no ROUNDED)
     DD-TOTAL-DEDUCT is 9(5)V9(2); max 99999.99; overflow silently drops high-order digits.

  4. COMPUTE DD-AFTER-DEDUCT = DD-GROSS-PAY - DD-TOTAL-DEDUCT  (no ROUNDED)
     DD-AFTER-DEDUCT is 9(7)V9(2); result is always non-negative in practice,
     but if subtraction goes negative the high-order truncation still applies
     (unsigned field stores abs of truncated result via modulo).
"""
from __future__ import annotations

from decimal import Decimal

from translation.a._cobol_codec import (
    enc_unsigned_display,
    round_half_up,
    cobol_trunc_unsigned,
)


def run(record: dict) -> bytes:
    emp_id: Decimal = record["DD-EMP-ID"]
    gross_pay: Decimal = record["DD-GROSS-PAY"]
    health_rate: Decimal = record["DD-HEALTH-RATE"]
    retire_rate: Decimal = record["DD-RETIREMENT-RATE"]

    # MOVE DD-EMP-ID TO DD-OUT-EMP-ID
    out_emp_id = enc_unsigned_display(emp_id, 6, 0)

    # TRAP 1: COMPUTE DD-HEALTH-DED ROUNDED = DD-GROSS-PAY * DD-HEALTH-RATE
    health_raw = round_half_up(gross_pay * health_rate, 2)
    dd_health_ded = cobol_trunc_unsigned(health_raw, 5, 2)

    # TRAP 2: COMPUTE WS-RETIRE-WORK = DD-GROSS-PAY * DD-RETIREMENT-RATE (no ROUNDED)
    ws_retire_work = cobol_trunc_unsigned(gross_pay * retire_rate, 9, 4)
    # MOVE WS-RETIRE-WORK TO DD-RETIRE-DED (9(5)V9(2)) — truncate to 2 d.p.
    dd_retire_ded = cobol_trunc_unsigned(ws_retire_work, 5, 2)

    # TRAP 3: COMPUTE DD-TOTAL-DEDUCT = DD-HEALTH-DED + DD-RETIRE-DED (no ROUNDED)
    # 9(5)V9(2): overflow wraps high-order digits
    dd_total_deduct = cobol_trunc_unsigned(dd_health_ded + dd_retire_ded, 5, 2)

    # COMPUTE DD-AFTER-DEDUCT = DD-GROSS-PAY - DD-TOTAL-DEDUCT (no ROUNDED)
    # 9(7)V9(2): unsigned; if result goes negative, abs+overflow truncation applies
    after_raw = gross_pay - dd_total_deduct
    dd_after_deduct = cobol_trunc_unsigned(after_raw, 7, 2)

    out_health = enc_unsigned_display(dd_health_ded, 5, 2)   # 7
    out_retire = enc_unsigned_display(dd_retire_ded, 5, 2)   # 7
    out_total = enc_unsigned_display(dd_total_deduct, 5, 2)  # 7
    out_after = enc_unsigned_display(dd_after_deduct, 7, 2)  # 9

    filler = b" " * 44

    output = (
        out_emp_id   # 6
        + out_health # 7
        + out_retire # 7
        + out_total  # 7
        + out_after  # 9
        + filler     # 44
    )                # = 80
    assert len(output) == 80
    return output
