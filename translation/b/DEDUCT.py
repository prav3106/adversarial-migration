"""
translation/b/DEDUCT.py — Structural translation of DEDUCT.cbl
Mirror of COBOL WORKING-STORAGE and PROCEDURE DIVISION paragraphs.

Input record (80 bytes):
  DD-EMP-ID           PIC 9(6)        offset  0  len  6
  DD-GROSS-PAY        PIC 9(7)V9(2)   offset  6  len  9
  DD-HEALTH-RATE      PIC 9(2)V9(4)   offset 15  len  6
  DD-RETIREMENT-RATE  PIC 9(2)V9(4)   offset 21  len  6
  FILLER              PIC X(53)       offset 27  len 53

Output record (80 bytes):
  DD-OUT-EMP-ID       PIC 9(6)        offset  0  len  6
  DD-HEALTH-DED       PIC 9(5)V9(2)   offset  6  len  7
  DD-RETIRE-DED       PIC 9(5)V9(2)   offset 13  len  7
  DD-TOTAL-DEDUCT     PIC 9(5)V9(2)   offset 20  len  7
  DD-AFTER-DEDUCT     PIC 9(7)V9(2)   offset 27  len  9
  FILLER              PIC X(44)       offset 36  len 44
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
    """Truncate then high-order overflow for unsigned DISPLAY field."""
    v = _trunc(abs(value), digits_after)
    return _overflow(v, digits_before, digits_after)


def _store_rounded_unsigned(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """ROUNDED then high-order overflow for unsigned DISPLAY field."""
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
        self.DD_EMP_ID:           Decimal = Decimal(0)  # PIC 9(6)
        self.DD_GROSS_PAY:        Decimal = Decimal(0)  # PIC 9(7)V9(2)
        self.DD_HEALTH_RATE:      Decimal = Decimal(0)  # PIC 9(2)V9(4)
        self.DD_RETIREMENT_RATE:  Decimal = Decimal(0)  # PIC 9(2)V9(4)
        # WS-OUTPUT-RECORD
        self.DD_OUT_EMP_ID:       Decimal = Decimal(0)  # PIC 9(6)
        self.DD_HEALTH_DED:       Decimal = Decimal(0)  # PIC 9(5)V9(2)
        self.DD_RETIRE_DED:       Decimal = Decimal(0)  # PIC 9(5)V9(2)
        self.DD_TOTAL_DEDUCT:     Decimal = Decimal(0)  # PIC 9(5)V9(2)
        self.DD_AFTER_DEDUCT:     Decimal = Decimal(0)  # PIC 9(7)V9(2)
        # WS-WORK
        self.WS_HEALTH_WORK:      Decimal = Decimal(0)  # PIC 9(9)V9(4)
        self.WS_RETIRE_WORK:      Decimal = Decimal(0)  # PIC 9(9)V9(4)


# ---------------------------------------------------------------------------
# Paragraph implementations
# ---------------------------------------------------------------------------

def _calc_deduct(ws: _WS) -> None:
    """Mirror of CALC-DEDUCT paragraph."""
    ws.DD_OUT_EMP_ID = _store_display_unsigned(ws.DD_EMP_ID, 6, 0)

    # TRAP: COMPUTE ROUNDED used for health — rounds half-up
    raw_health = ws.DD_GROSS_PAY * ws.DD_HEALTH_RATE
    ws.DD_HEALTH_DED = _store_rounded_unsigned(raw_health, 5, 2)

    # TRAP: mixed ROUNDED/non-ROUNDED sequence in same paragraph
    #       retirement uses plain COMPUTE (truncates) immediately after ROUNDED
    ws.WS_RETIRE_WORK = _trunc(ws.DD_GROSS_PAY * ws.DD_RETIREMENT_RATE, 4)
    ws.DD_RETIRE_DED  = _store_display_unsigned(ws.WS_RETIRE_WORK, 5, 2)

    # TRAP: DD-TOTAL-DEDUCT is PIC 9(5)V9(2) max 99999.99
    #       overflow silently drops high-order digits (high-order truncation)
    raw_total = _trunc(ws.DD_HEALTH_DED + ws.DD_RETIRE_DED, 2)
    ws.DD_TOTAL_DEDUCT = _overflow(raw_total, 5, 2)

    raw_after = _trunc(ws.DD_GROSS_PAY - ws.DD_TOTAL_DEDUCT, 2)
    ws.DD_AFTER_DEDUCT = _store_display_unsigned(raw_after, 7, 2)


def _build_output(ws: _WS) -> bytes:
    """Assemble WS-OUTPUT-RECORD into 80 bytes."""
    out  = _encode_display_numeric(ws.DD_OUT_EMP_ID,   6, 0)   # 6
    out += _encode_display_numeric(ws.DD_HEALTH_DED,   5, 2)   # 7
    out += _encode_display_numeric(ws.DD_RETIRE_DED,   5, 2)   # 7
    out += _encode_display_numeric(ws.DD_TOTAL_DEDUCT, 5, 2)   # 7
    out += _encode_display_numeric(ws.DD_AFTER_DEDUCT, 7, 2)   # 9
    out += b' ' * 44                                             # 44 filler
    assert len(out) == 80, f"Output length {len(out)} != 80"
    return out


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run(record: dict) -> bytes:
    """run(record: dict) -> bytes  — matches verify/run_candidate.py interface."""
    ws = _WS()
    ws.DD_EMP_ID          = Decimal(str(record["DD-EMP-ID"]))
    ws.DD_GROSS_PAY       = Decimal(str(record["DD-GROSS-PAY"]))
    ws.DD_HEALTH_RATE     = Decimal(str(record["DD-HEALTH-RATE"]))
    ws.DD_RETIREMENT_RATE = Decimal(str(record["DD-RETIREMENT-RATE"]))
    _calc_deduct(ws)
    return _build_output(ws)
