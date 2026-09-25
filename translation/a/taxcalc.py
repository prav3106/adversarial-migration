"""
translation/a/taxcalc.py — TAXCALC: Federal income tax calculation.

Input dict keys  (COBOL field names as strings):
    TC-EMP-ID     Decimal   9(6)       6 bytes
    TC-GROSS-PAY  Decimal   9(7)V9(2)  9 bytes
    TC-TAX-RATE   Decimal   9(2)V9(4)  6 bytes

Output: 80-byte fixed-width record.

Layout:
    offset  0  len  6  TC-OUT-EMP-ID    9(6)       DISPLAY
    offset  6  len  9  TC-OUT-GROSS-PAY 9(7)V9(2)  DISPLAY
    offset 15  len  9  TC-TAX-AMOUNT    9(7)V9(2)  DISPLAY
    offset 24  len  9  TC-BRACKET-TAX   9(7)V9(2)  DISPLAY
    offset 33  len 47  FILLER           X(47)

TRAPs reproduced:
  1. COMPUTE TC-TAX-AMOUNT ROUNDED = TC-GROSS-PAY * TC-TAX-RATE
     Uses ROUNDED (ROUND_HALF_UP). TC-TAX-AMOUNT is 9(7)V9(2); rounded to 2 d.p.

  2. COMPUTE WS-BRACKET-WORK = TC-GROSS-PAY * 0.0275  (no ROUNDED)
     WS-BRACKET-WORK is 9(9)V9(4); truncated to 4 d.p.
     MOVE WS-BRACKET-WORK TO TC-BRACKET-TAX  (9(7)V9(2)); truncated to 2 d.p.
     Two-step truncation: at 4 d.p. then at 2 d.p.
"""
from __future__ import annotations

from decimal import Decimal

from translation.a._cobol_codec import (
    enc_unsigned_display,
    round_half_up,
    cobol_trunc_unsigned,
)


def run(record: dict) -> bytes:
    emp_id: Decimal = record["TC-EMP-ID"]
    gross_pay: Decimal = record["TC-GROSS-PAY"]
    tax_rate: Decimal = record["TC-TAX-RATE"]

    # MOVE TC-EMP-ID TO TC-OUT-EMP-ID
    out_emp_id = enc_unsigned_display(emp_id, 6, 0)

    # MOVE TC-GROSS-PAY TO TC-OUT-GROSS-PAY
    out_gross = enc_unsigned_display(gross_pay, 7, 2)

    # TRAP 1: COMPUTE TC-TAX-AMOUNT ROUNDED = TC-GROSS-PAY * TC-TAX-RATE
    # ROUNDED -> ROUND_HALF_UP; then truncate to 9(7)V9(2) field width
    tax_raw = round_half_up(gross_pay * tax_rate, 2)
    tc_tax_amount = cobol_trunc_unsigned(tax_raw, 7, 2)
    out_tax = enc_unsigned_display(tc_tax_amount, 7, 2)

    # TRAP 2: COMPUTE WS-BRACKET-WORK = TC-GROSS-PAY * 0.0275  (no ROUNDED)
    # WS-BRACKET-WORK is 9(9)V9(4) — truncate to 4 d.p. first
    ws_bracket_work = cobol_trunc_unsigned(gross_pay * Decimal("0.0275"), 9, 4)
    # MOVE WS-BRACKET-WORK TO TC-BRACKET-TAX (9(7)V9(2)) — truncate to 2 d.p.
    tc_bracket_tax = cobol_trunc_unsigned(ws_bracket_work, 7, 2)
    out_bracket = enc_unsigned_display(tc_bracket_tax, 7, 2)

    filler = b" " * 47

    output = (
        out_emp_id    # 6
        + out_gross   # 9
        + out_tax     # 9
        + out_bracket # 9
        + filler      # 47
    )                 # = 80
    assert len(output) == 80
    return output
