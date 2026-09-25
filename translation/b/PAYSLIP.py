"""
translation/b/PAYSLIP.py — Structural translation of PAYSLIP.cbl
Mirror of COBOL WORKING-STORAGE and PROCEDURE DIVISION paragraphs.

Input record (80 bytes):
  PS-EMP-ID        PIC 9(6)        offset  0  len  6
  PS-GROSS-PAY     PIC 9(7)V9(2)   offset  6  len  9
  PS-TAX-AMOUNT    PIC 9(7)V9(2)   offset 15  len  9
  PS-DEDUCTIONS    PIC 9(5)V9(2)   offset 24  len  7
  FILLER           PIC X(49)       offset 31  len 49

Output record (80 bytes):
  PS-OUT-EMP-ID    PIC 9(6)        offset  0  len  6
  PS-OUT-GROSS     PIC 9(7)V9(2)   offset  6  len  9
  PS-OUT-TAX       PIC 9(7)V9(2)   offset 15  len  9
  PS-OUT-DEDUCT    PIC 9(5)V9(2)   offset 24  len  7
  PS-NET-PAY       PIC S9(7)V9(2)  offset 31  len  9  (signed DISPLAY)
  PS-NET-UNSIGNED  PIC 9(7)V9(2)   offset 40  len  9  (unsigned copy)
  FILLER           PIC X(31)       offset 49  len 31
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


def _trunc_signed(value: Decimal, digits_after: int) -> Decimal:
    """Signed truncation (preserves sign direction) to digits_after places."""
    if digits_after == 0:
        quantize_exp = Decimal(1)
    else:
        quantize_exp = Decimal(10) ** -digits_after
    # Python Decimal ROUND_DOWN truncates toward zero for both signs
    return value.quantize(quantize_exp, rounding=ROUND_DOWN)


def _overflow(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """High-order truncation: wrap at 10**digits_before (unsigned)."""
    if digits_after > 0:
        scale = Decimal(10) ** digits_after
        int_val = int(abs(value) * scale)
        int_val = int_val % int(Decimal(10) ** digits_before * scale)
        return Decimal(int_val) / scale
    else:
        return Decimal(int(abs(value)) % int(Decimal(10) ** digits_before))


def _overflow_signed(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """High-order truncation for signed field: preserves sign, wraps magnitude."""
    sign = Decimal(-1) if value < 0 else Decimal(1)
    return sign * _overflow(value, digits_before, digits_after)


def _store_display_unsigned(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """Truncate (abs) then overflow for unsigned DISPLAY field."""
    v = _trunc(abs(value), digits_after)
    return _overflow(v, digits_before, digits_after)


def _store_display_signed(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """Truncate then overflow for signed DISPLAY field (preserves sign)."""
    v = _trunc_signed(value, digits_after)
    return _overflow_signed(v, digits_before, digits_after)


def _encode_display_numeric(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """Encode PIC 9(d)V9(s) as ASCII digits, no decimal point (implied V)."""
    total_digits = digits_before + digits_after
    n = int(abs(value) * (Decimal(10) ** digits_after))
    n = n % (10 ** total_digits)
    return str(n).zfill(total_digits).encode("ascii")


def _encode_display_signed(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """
    Encode PIC S9(d)V9(s) DISPLAY — COBOL sign-in-last-digit (overpunch) convention.
    Positive: normal ASCII digits (zones 3x).
    Negative: last digit uses 7x overpunch table:
      0→p(0x70), 1→q(0x71), 2→r(0x72), 3→s(0x73), 4→t(0x74),
      5→u(0x75), 6→v(0x76), 7→w(0x77), 8→x(0x78), 9→y(0x79)
    """
    total_digits = digits_before + digits_after
    abs_val = abs(value)
    n = int(abs_val * (Decimal(10) ** digits_after))
    n = n % (10 ** total_digits)
    digits = list(str(n).zfill(total_digits).encode("ascii"))
    if value < 0:
        last = digits[-1] - ord('0')
        digits[-1] = 0x70 + last
    return bytes(digits)


def _encode_comp3(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """
    Encode COMP-3 packed decimal unsigned.
    Packed length = ceil((total_digits + 1) / 2).
    Sign nibble 0xC = positive/unsigned.
    """
    total_digits = digits_before + digits_after
    byte_len = (total_digits + 2) // 2

    abs_val = abs(value)
    int_val = int(abs_val * (Decimal(10) ** digits_after))
    int_val = int_val % (10 ** total_digits)

    digit_str = str(int_val).zfill(total_digits)
    all_nibbles = [int(d) for d in digit_str] + [0xC]

    if len(all_nibbles) % 2 != 0:
        all_nibbles = [0] + all_nibbles

    result = bytearray()
    for i in range(0, len(all_nibbles), 2):
        result.append((all_nibbles[i] << 4) | all_nibbles[i + 1])

    result_bytes = bytes(result)
    if len(result_bytes) < byte_len:
        result_bytes = b'\x00' * (byte_len - len(result_bytes)) + result_bytes
    return result_bytes[-byte_len:]


# ---------------------------------------------------------------------------
# WORKING-STORAGE state object
# ---------------------------------------------------------------------------

class _WS:
    """Mirror of COBOL WORKING-STORAGE SECTION."""
    def __init__(self) -> None:
        # WS-INPUT-RECORD
        self.PS_EMP_ID:        Decimal = Decimal(0)  # PIC 9(6)
        self.PS_GROSS_PAY:     Decimal = Decimal(0)  # PIC 9(7)V9(2)
        self.PS_TAX_AMOUNT:    Decimal = Decimal(0)  # PIC 9(7)V9(2)
        self.PS_DEDUCTIONS:    Decimal = Decimal(0)  # PIC 9(5)V9(2)
        # WS-OUTPUT-RECORD
        self.PS_OUT_EMP_ID:    Decimal = Decimal(0)  # PIC 9(6)
        self.PS_OUT_GROSS:     Decimal = Decimal(0)  # PIC 9(7)V9(2)
        self.PS_OUT_TAX:       Decimal = Decimal(0)  # PIC 9(7)V9(2)
        self.PS_OUT_DEDUCT:    Decimal = Decimal(0)  # PIC 9(5)V9(2)
        self.PS_NET_PAY:       Decimal = Decimal(0)  # PIC S9(7)V9(2) signed
        self.PS_NET_UNSIGNED:  Decimal = Decimal(0)  # PIC 9(7)V9(2) unsigned copy
        # WS-WORK
        self.WS_NET_WORK:      Decimal = Decimal(0)  # PIC S9(9)V9(4) signed
        self.WS_COMP3_STORE:   Decimal = Decimal(0)  # COMP-3 9(7)V9(2)


# ---------------------------------------------------------------------------
# Paragraph implementations
# ---------------------------------------------------------------------------

def _calc_payslip(ws: _WS) -> None:
    """Mirror of CALC-PAYSLIP paragraph."""
    ws.PS_OUT_EMP_ID = _store_display_unsigned(ws.PS_EMP_ID, 6, 0)

    # TRAP: WS-NET-WORK is signed; net pay can go negative when
    #       deductions+tax exceed gross — PS-NET-PAY is signed so stores sign
    ws.WS_NET_WORK = _trunc_signed(
        ws.PS_GROSS_PAY - ws.PS_TAX_AMOUNT - ws.PS_DEDUCTIONS, 4
    )
    ws.PS_NET_PAY  = _store_display_signed(ws.WS_NET_WORK, 7, 2)

    # Intermediate COMP-3 store and reload preserves implied decimal (V)
    ws.WS_COMP3_STORE = _store_display_unsigned(ws.PS_GROSS_PAY, 7, 2)
    ws.PS_OUT_GROSS   = _store_display_unsigned(ws.WS_COMP3_STORE, 7, 2)

    ws.PS_OUT_TAX    = _store_display_unsigned(ws.PS_TAX_AMOUNT,  7, 2)
    ws.PS_OUT_DEDUCT = _store_display_unsigned(ws.PS_DEDUCTIONS,  5, 2)

    # TRAP: MOVE of signed PS-NET-PAY to unsigned PS-NET-UNSIGNED drops sign;
    #       absolute value stored, not clamped to zero
    ws.PS_NET_UNSIGNED = _store_display_unsigned(ws.PS_NET_PAY, 7, 2)


def _build_output(ws: _WS) -> bytes:
    """Assemble WS-OUTPUT-RECORD into 80 bytes."""
    out  = _encode_display_numeric(ws.PS_OUT_EMP_ID,   6, 0)    # 6
    out += _encode_display_numeric(ws.PS_OUT_GROSS,    7, 2)    # 9
    out += _encode_display_numeric(ws.PS_OUT_TAX,      7, 2)    # 9
    out += _encode_display_numeric(ws.PS_OUT_DEDUCT,   5, 2)    # 7
    out += _encode_display_signed(ws.PS_NET_PAY,       7, 2)    # 9
    out += _encode_display_numeric(ws.PS_NET_UNSIGNED, 7, 2)    # 9
    out += b' ' * 31                                              # 31 filler
    assert len(out) == 80, f"Output length {len(out)} != 80"
    return out


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run(record: dict) -> bytes:
    """run(record: dict) -> bytes  — matches verify/run_candidate.py interface."""
    ws = _WS()
    ws.PS_EMP_ID     = Decimal(str(record["PS-EMP-ID"]))
    ws.PS_GROSS_PAY  = Decimal(str(record["PS-GROSS-PAY"]))
    ws.PS_TAX_AMOUNT = Decimal(str(record["PS-TAX-AMOUNT"]))
    ws.PS_DEDUCTIONS = Decimal(str(record["PS-DEDUCTIONS"]))
    _calc_payslip(ws)
    return _build_output(ws)
