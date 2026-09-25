"""
translation/b/TAXCALC.py — Structural translation of TAXCALC.cbl
Mirror of COBOL WORKING-STORAGE and PROCEDURE DIVISION paragraphs.

Input record (80 bytes):
  TC-EMP-ID        PIC 9(6)        offset  0  len  6
  TC-GROSS-PAY     PIC 9(7)V9(2)   offset  6  len  9
  TC-TAX-RATE      PIC 9(2)V9(4)   offset 15  len  6
  FILLER           PIC X(59)       offset 21  len 59

Output record (80 bytes):
  TC-OUT-EMP-ID    PIC 9(6)        offset  0  len  6
  TC-OUT-GROSS-PAY PIC 9(7)V9(2)   offset  6  len  9
  TC-TAX-AMOUNT    PIC 9(7)V9(2)   offset 15  len  9
  TC-BRACKET-TAX   PIC 9(7)V9(2)   offset 24  len  9
  FILLER           PIC X(47)       offset 33  len 47
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP


# ---------------------------------------------------------------------------
# Encoding helpers (independent implementation)
# ---------------------------------------------------------------------------

def _trunc(value: Decimal, digits_after: int) -> Decimal:
    """COBOL COMPUTE without ROUNDED: truncate toward zero to digits_after places."""
    if digits_after == 0:
        quantize_exp = Decimal(1)
    else:
        quantize_exp = Decimal(10) ** -digits_after
    return value.quantize(quantize_exp, rounding=ROUND_DOWN)


def _round_half_up(value: Decimal, digits_after: int) -> Decimal:
    """COBOL COMPUTE ROUNDED: ROUND_HALF_UP to digits_after places."""
    if digits_after == 0:
        quantize_exp = Decimal(1)
    else:
        quantize_exp = Decimal(10) ** -digits_after
    return value.quantize(quantize_exp, rounding=ROUND_HALF_UP)


def _overflow(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """High-order truncation: wrap at 10**digits_before."""
    if digits_after > 0:
        scale = Decimal(10) ** digits_after
        int_val = int(abs(value) * scale)
        int_val = int_val % int(Decimal(10) ** digits_before * scale)
        return Decimal(int_val) / scale
    else:
        return Decimal(int(abs(value)) % int(Decimal(10) ** digits_before))


def _store_display_unsigned(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """Store into unsigned DISPLAY field: apply truncation + overflow."""
    v = _trunc(abs(value), digits_after)
    return _overflow(v, digits_before, digits_after)


def _store_rounded_unsigned(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """Store into unsigned DISPLAY field with ROUNDED (HALF_UP) then overflow."""
    v = _round_half_up(abs(value), digits_after)
    return _overflow(v, digits_before, digits_after)


def _encode_display_numeric(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """Encode PIC 9(d)V9(s) as ASCII digits, no decimal point (implied V)."""
    total_digits = digits_before + digits_after
    n = int(abs(value) * (Decimal(10) ** digits_after))
    n = n % (10 ** total_digits)
    return str(n).zfill(total_digits).encode("ascii")


# ---------------------------------------------------------------------------
# WORKING-STORAGE state object
# ---------------------------------------------------------------------------

class _WS:
    """Mirror of COBOL WORKING-STORAGE SECTION."""
    def __init__(self) -> None:
        # WS-INPUT-RECORD
        self.TC_EMP_ID:          Decimal = Decimal(0)  # PIC 9(6)
        self.TC_GROSS_PAY:       Decimal = Decimal(0)  # PIC 9(7)V9(2)
        self.TC_TAX_RATE:        Decimal = Decimal(0)  # PIC 9(2)V9(4)
        # WS-OUTPUT-RECORD
        self.TC_OUT_EMP_ID:      Decimal = Decimal(0)  # PIC 9(6)
        self.TC_OUT_GROSS_PAY:   Decimal = Decimal(0)  # PIC 9(7)V9(2)
        self.TC_TAX_AMOUNT:      Decimal = Decimal(0)  # PIC 9(7)V9(2)
        self.TC_BRACKET_TAX:     Decimal = Decimal(0)  # PIC 9(7)V9(2)
        # WS-WORK
        self.WS_TAX_WORK:        Decimal = Decimal(0)  # PIC 9(9)V9(4)
        self.WS_BRACKET_WORK:    Decimal = Decimal(0)  # PIC 9(9)V9(4)


# ---------------------------------------------------------------------------
# Paragraph implementations
# ---------------------------------------------------------------------------

def _calc_tax(ws: _WS) -> None:
    """Mirror of CALC-TAX paragraph."""
    ws.TC_OUT_EMP_ID    = _store_display_unsigned(ws.TC_EMP_ID,    6, 0)
    ws.TC_OUT_GROSS_PAY = _store_display_unsigned(ws.TC_GROSS_PAY, 7, 2)

    # TRAP: COMPUTE ROUNDED uses ROUND_HALF_UP (not truncation)
    #       TC-TAX-RATE has 4 decimal places so half-cent rounding fires frequently
    raw_tax = ws.TC_GROSS_PAY * ws.TC_TAX_RATE
    ws.TC_TAX_AMOUNT = _store_rounded_unsigned(raw_tax, 7, 2)

    # TRAP: bracketed tax via COMPUTE without ROUNDED — truncation only
    #       bracket rate hardcoded 0.0275; result truncated not rounded
    ws.WS_BRACKET_WORK = _trunc(ws.TC_GROSS_PAY * Decimal("0.0275"), 4)
    ws.TC_BRACKET_TAX  = _store_display_unsigned(ws.WS_BRACKET_WORK, 7, 2)


def _build_output(ws: _WS) -> bytes:
    """Assemble WS-OUTPUT-RECORD into 80 bytes."""
    out  = _encode_display_numeric(ws.TC_OUT_EMP_ID,    6, 0)   # 6
    out += _encode_display_numeric(ws.TC_OUT_GROSS_PAY, 7, 2)   # 9
    out += _encode_display_numeric(ws.TC_TAX_AMOUNT,    7, 2)   # 9
    out += _encode_display_numeric(ws.TC_BRACKET_TAX,   7, 2)   # 9
    out += b' ' * 47                                              # 47 filler
    assert len(out) == 80, f"Output length {len(out)} != 80"
    return out


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run(record: dict) -> bytes:
    """run(record: dict) -> bytes  — matches verify/run_candidate.py interface."""
    ws = _WS()
    ws.TC_EMP_ID    = Decimal(str(record["TC-EMP-ID"]))
    ws.TC_GROSS_PAY = Decimal(str(record["TC-GROSS-PAY"]))
    ws.TC_TAX_RATE  = Decimal(str(record["TC-TAX-RATE"]))
    _calc_tax(ws)
    return _build_output(ws)
