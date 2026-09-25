"""
translation/b/GROSSPAY.py — Structural translation of GROSSPAY.cbl
Mirror of COBOL WORKING-STORAGE and PROCEDURE DIVISION paragraphs.

Input record (80 bytes):
  GP-EMP-ID        PIC 9(6)        offset  0  len  6
  GP-HOURS-WORKED  PIC 9(3)V9(2)   offset  6  len  5
  GP-HOURLY-RATE   PIC 9(4)V9(2)   offset 11  len  6
  FILLER           PIC X(63)       offset 17  len 63

Output record (80 bytes):
  GP-OUT-EMP-ID    PIC 9(6)        offset  0  len  6
  GP-REGULAR-PAY   COMP-3 9(7)V9(2) offset  6  len  5
  GP-OVERTIME-PAY  COMP-3 9(7)V9(2) offset 11  len  5
  GP-GROSS-PAY     COMP-3 9(7)V9(2) offset 16  len  5
  FILLER           PIC X(59)       offset 21  len 59
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP


# ---------------------------------------------------------------------------
# Encoding helpers (independent implementation)
# ---------------------------------------------------------------------------

def _trunc(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """COBOL COMPUTE without ROUNDED: truncate toward zero to digits_after places."""
    if digits_after == 0:
        quantize_exp = Decimal(1)
    else:
        quantize_exp = Decimal(10) ** -digits_after
    return value.quantize(quantize_exp, rounding=ROUND_DOWN)


def _overflow(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """High-order truncation: wrap at 10**digits_before."""
    modulus = Decimal(10) ** digits_before
    if digits_after > 0:
        scale = Decimal(10) ** digits_after
        int_val = int(value * scale)
        int_val = int_val % int(modulus * scale)
        return Decimal(int_val) / scale
    else:
        return Decimal(int(value) % int(modulus))


def _store_truncate(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """Truncate then high-order overflow for a DISPLAY/COMP-3 numeric field."""
    v = _trunc(abs(value), digits_before + digits_after + 4, digits_after)  # extra room
    return _overflow(v, digits_before, digits_after)


def _encode_display_numeric(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """Encode PIC 9(d)V9(s) as ASCII digits, no decimal point (implied V)."""
    total_digits = digits_before + digits_after
    n = int(abs(value) * (Decimal(10) ** digits_after))
    n = n % (10 ** total_digits)
    return str(n).zfill(total_digits).encode("ascii")


def _encode_comp3(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """
    Encode COMP-3 (packed decimal) unsigned.
    PIC 9(d)V9(s): total_digits = d + s.
    Packed length = ceil((total_digits + 1) / 2) bytes.
    Sign nibble: 0xC (positive/unsigned), 0xD (negative).
    Last nibble is sign.
    """
    total_digits = digits_before + digits_after
    byte_len = (total_digits + 2) // 2  # ceil((total_digits+1)/2)

    # Absolute integer value (value already has implied decimal applied)
    abs_val = abs(value)
    int_val = int(abs_val * (Decimal(10) ** digits_after))
    # High-order overflow
    int_val = int_val % (10 ** total_digits)

    # Build digit string padded to total_digits
    digit_str = str(int_val).zfill(total_digits)

    # Pad to even total chars to form nibble pairs before sign nibble
    # Total nibbles = total_digits + 1 (for sign); pad to even
    all_nibbles = list(int(d) for d in digit_str) + [0xC]  # 0xC = positive/unsigned

    # If total nibbles is odd (total_digits+1 is odd), left-pad with 0 nibble
    if len(all_nibbles) % 2 != 0:
        all_nibbles = [0] + all_nibbles

    # Pack nibble pairs into bytes
    result = bytearray()
    for i in range(0, len(all_nibbles), 2):
        result.append((all_nibbles[i] << 4) | all_nibbles[i + 1])

    # Result must be exactly byte_len bytes
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
        self.GP_EMP_ID:        Decimal = Decimal(0)  # PIC 9(6)
        self.GP_HOURS_WORKED:  Decimal = Decimal(0)  # PIC 9(3)V9(2)
        self.GP_HOURLY_RATE:   Decimal = Decimal(0)  # PIC 9(4)V9(2)
        # WS-OUTPUT-RECORD
        self.GP_OUT_EMP_ID:    Decimal = Decimal(0)  # PIC 9(6)
        self.GP_REGULAR_PAY:   Decimal = Decimal(0)  # COMP-3 9(7)V9(2)
        self.GP_OVERTIME_PAY:  Decimal = Decimal(0)  # COMP-3 9(7)V9(2)
        self.GP_GROSS_PAY:     Decimal = Decimal(0)  # COMP-3 9(7)V9(2)
        # WS-WORK
        self.WS_REG_HOURS:     Decimal = Decimal(0)  # PIC 9(3)V9(2)
        self.WS_OT_HOURS:      Decimal = Decimal(0)  # PIC 9(3)V9(2)
        self.WS_OT_RATE:       Decimal = Decimal(0)  # PIC 9(4)V9(2)
        self.WS_WORK_PAY:      Decimal = Decimal(0)  # PIC 9(9)V9(4)


# ---------------------------------------------------------------------------
# Paragraph implementations
# ---------------------------------------------------------------------------

def _calc_grosspay(ws: _WS) -> None:
    """Mirror of CALC-GROSSPAY paragraph."""
    ws.GP_OUT_EMP_ID = _store_truncate(ws.GP_EMP_ID, 6, 0)

    # Regular hours capped at 40.00
    if ws.GP_HOURS_WORKED > Decimal("40.00"):
        ws.WS_REG_HOURS = Decimal("40.00")
        # SUBTRACT 40.00 FROM GP-HOURS-WORKED GIVING WS-OT-HOURS
        # The GIVING form does not modify GP_HOURS_WORKED, stores into WS_OT_HOURS
        ws.WS_OT_HOURS = _store_truncate(ws.GP_HOURS_WORKED - Decimal("40.00"), 3, 2)
    else:
        ws.WS_REG_HOURS = _store_truncate(ws.GP_HOURS_WORKED, 3, 2)
        ws.WS_OT_HOURS = Decimal("0.00")

    # TRAP: COMPUTE without ROUNDED — fractional cents truncated toward zero
    #       e.g. 40.00 * 12.555 = 502.20 not 502.21
    ws.WS_WORK_PAY = _trunc(ws.WS_REG_HOURS * ws.GP_HOURLY_RATE, 9, 4)
    ws.GP_REGULAR_PAY = _store_truncate(ws.WS_WORK_PAY, 7, 2)

    # Overtime at 1.5x rate — COMPUTE truncates (no ROUNDED)
    ws.WS_OT_RATE = _trunc(ws.GP_HOURLY_RATE * Decimal("1.5"), 4, 2)

    # TRAP: overtime COMPUTE can overflow GP-OVERTIME-PAY at field max
    #       9(7)V9(2) max = 9999999.99; WS-OT-HOURS * WS-OT-RATE may exceed it
    #       High-order digits are silently dropped.
    raw_ot = _trunc(ws.WS_OT_HOURS * ws.WS_OT_RATE, 9, 4)
    ws.GP_OVERTIME_PAY = _store_truncate(raw_ot, 7, 2)

    raw_gross = _trunc(ws.GP_REGULAR_PAY + ws.GP_OVERTIME_PAY, 9, 4)
    ws.GP_GROSS_PAY = _store_truncate(raw_gross, 7, 2)


def _build_output(ws: _WS) -> bytes:
    """Assemble WS-OUTPUT-RECORD into 80 bytes."""
    out  = _encode_display_numeric(ws.GP_OUT_EMP_ID,   6, 0)   # 6
    out += _encode_comp3(ws.GP_REGULAR_PAY,  7, 2)              # 5
    out += _encode_comp3(ws.GP_OVERTIME_PAY, 7, 2)              # 5
    out += _encode_comp3(ws.GP_GROSS_PAY,    7, 2)              # 5
    out += b' ' * 59                                             # 59 filler
    assert len(out) == 80, f"Output length {len(out)} != 80"
    return out


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run(record: dict) -> bytes:
    """run(record: dict) -> bytes  — matches verify/run_candidate.py interface."""
    ws = _WS()
    ws.GP_EMP_ID       = Decimal(str(record["GP-EMP-ID"]))
    ws.GP_HOURS_WORKED = Decimal(str(record["GP-HOURS-WORKED"]))
    ws.GP_HOURLY_RATE  = Decimal(str(record["GP-HOURLY-RATE"]))
    _calc_grosspay(ws)
    return _build_output(ws)
