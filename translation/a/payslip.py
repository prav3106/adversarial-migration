"""
translation/a/payslip.py — PAYSLIP: Final payslip assembly.

Input dict keys  (COBOL field names as strings):
    PS-EMP-ID      Decimal   9(6)       6 bytes
    PS-GROSS-PAY   Decimal   9(7)V9(2)  9 bytes
    PS-TAX-AMOUNT  Decimal   9(7)V9(2)  9 bytes
    PS-DEDUCTIONS  Decimal   9(5)V9(2)  7 bytes

Output: 80-byte fixed-width record.

Layout:
    offset  0  len  6  PS-OUT-EMP-ID    9(6)        DISPLAY
    offset  6  len  9  PS-OUT-GROSS     9(7)V9(2)   DISPLAY
    offset 15  len  9  PS-OUT-TAX       9(7)V9(2)   DISPLAY
    offset 24  len  7  PS-OUT-DEDUCT    9(5)V9(2)   DISPLAY
    offset 31  len  9  PS-NET-PAY       S9(7)V9(2)  DISPLAY (signed overpunch)
    offset 40  len  9  PS-NET-UNSIGNED  9(7)V9(2)   DISPLAY
    offset 49  len 31  FILLER           X(31)

TRAPs reproduced:
  1. COMPUTE WS-NET-WORK = PS-GROSS-PAY - PS-TAX-AMOUNT - PS-DEDUCTIONS
     WS-NET-WORK is S9(9)V9(4) (signed); result truncated to 4 d.p.
     Net pay can go negative when deductions+tax exceed gross.

  2. MOVE WS-NET-WORK TO PS-NET-PAY  (S9(7)V9(2) DISPLAY)
     Signed value stored with overpunch on last byte; truncated to 7+2 digits.

  3. Intermediate COMP-3 store:
     MOVE PS-GROSS-PAY TO WS-COMP3-STORE  (9(7)V9(2) COMP-3)
     MOVE WS-COMP3-STORE TO PS-OUT-GROSS
     The COMP-3 store truncates the value to 9(7)V9(2); MOVE back to DISPLAY
     preserves that truncated value.  (With well-formed input the gross is already
     within range so the round-trip is identity, but overflow would truncate.)

  4. TRAP: MOVE PS-NET-PAY TO PS-NET-UNSIGNED  (unsigned 9(7)V9(2))
     Drops the sign; absolute value stored.  Negative net becomes positive.
"""
from __future__ import annotations

from decimal import Decimal

from translation.a._cobol_codec import (
    enc_unsigned_display,
    enc_signed_display,
    enc_comp3,
    cobol_trunc_unsigned,
    cobol_trunc_signed,
)


def run(record: dict) -> bytes:
    emp_id: Decimal = record["PS-EMP-ID"]
    gross_pay: Decimal = record["PS-GROSS-PAY"]
    tax_amount: Decimal = record["PS-TAX-AMOUNT"]
    deductions: Decimal = record["PS-DEDUCTIONS"]

    # MOVE PS-EMP-ID TO PS-OUT-EMP-ID
    out_emp_id = enc_unsigned_display(emp_id, 6, 0)

    # TRAP 1 & 2: COMPUTE WS-NET-WORK = PS-GROSS-PAY - PS-TAX-AMOUNT - PS-DEDUCTIONS
    # WS-NET-WORK is S9(9)V9(4) — truncate to 4 d.p., signed
    ws_net_work = cobol_trunc_signed(gross_pay - tax_amount - deductions, 9, 4)

    # MOVE WS-NET-WORK TO PS-NET-PAY  (S9(7)V9(2) — signed DISPLAY, truncate to 2 d.p.)
    ps_net_pay = cobol_trunc_signed(ws_net_work, 7, 2)
    out_net_pay = enc_signed_display(ps_net_pay, 7, 2)

    # TRAP 3: MOVE PS-GROSS-PAY TO WS-COMP3-STORE (9(7)V9(2) COMP-3)
    # COMP-3 store truncates to 7+2 digits.
    ws_comp3_store = cobol_trunc_unsigned(gross_pay, 7, 2)
    # MOVE WS-COMP3-STORE TO PS-OUT-GROSS — back to DISPLAY (same value, no further truncation)
    out_gross = enc_unsigned_display(ws_comp3_store, 7, 2)

    # MOVE PS-TAX-AMOUNT TO PS-OUT-TAX
    out_tax = enc_unsigned_display(cobol_trunc_unsigned(tax_amount, 7, 2), 7, 2)

    # MOVE PS-DEDUCTIONS TO PS-OUT-DEDUCT
    out_deduct = enc_unsigned_display(cobol_trunc_unsigned(deductions, 5, 2), 5, 2)

    # TRAP 4: MOVE PS-NET-PAY TO PS-NET-UNSIGNED — drops sign, stores abs value
    ps_net_unsigned = abs(ps_net_pay)
    out_net_unsigned = enc_unsigned_display(ps_net_unsigned, 7, 2)

    filler = b" " * 31

    output = (
        out_emp_id        # 6
        + out_gross       # 9
        + out_tax         # 9
        + out_deduct      # 7
        + out_net_pay     # 9
        + out_net_unsigned # 9
        + filler          # 31
    )                     # = 80
    assert len(output) == 80
    return output
