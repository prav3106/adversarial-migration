"""
translation/b/VALIDATE.py — Structural translation of VALIDATE.cbl
Mirror of COBOL WORKING-STORAGE and PROCEDURE DIVISION paragraphs.

Input record (80 bytes):
  VL-EMP-ID        PIC 9(6)        offset  0  len  6
  VL-EMP-NAME      PIC X(20)       offset  6  len 20
  VL-HOURS-WORKED  PIC S9(3)V9(2)  offset 26  len  5  (signed DISPLAY)
  VL-HOURLY-RATE   PIC 9(4)V9(2)   offset 31  len  6
  FILLER           PIC X(43)       offset 37  len 43

Output record (80 bytes):
  VL-OUT-EMP-ID    PIC 9(6)        offset  0  len  6
  VL-OUT-EMP-NAME  PIC X(20)       offset  6  len 20
  VL-HOURS-CLEAN   PIC 9(3)V9(2)   offset 26  len  5  (unsigned)
  VL-HOURLY-CLEAN  PIC 9(4)V9(2)   offset 31  len  6
  VL-VALID-FLAG    PIC X(1)        offset 37  len  1
  FILLER           PIC X(42)       offset 38  len 42
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP


# ---------------------------------------------------------------------------
# Encoding helpers (independent implementation — no imports from other modules)
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
    # Shift to integer domain, mod, shift back
    if digits_after > 0:
        scale = Decimal(10) ** digits_after
        int_val = int(value * scale)
        int_val = int_val % int(modulus * scale)
        return Decimal(int_val) / scale
    else:
        return Decimal(int(value) % int(modulus))


def _store_display_unsigned(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """Store into unsigned DISPLAY field: truncate then overflow-wrap."""
    v = _trunc(abs(value), digits_before, digits_after)
    return _overflow(v, digits_before, digits_after)


def _encode_display_numeric(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """Encode PIC 9(d)V9(s) as ASCII digits, no decimal point, implied V."""
    total_digits = digits_before + digits_after
    n = int(abs(value) * (Decimal(10) ** digits_after))
    n = n % (10 ** total_digits)
    return str(n).zfill(total_digits).encode("ascii")


def _encode_display_signed(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """Encode PIC S9(d)V9(s) DISPLAY — COBOL sign-in-last-digit (overpunch) convention.
    Positive: zones 3x (normal ASCII digits).
    Negative: last digit uses 7x overpunch (0→p,1→q,...,9→y).
    """
    total_digits = digits_before + digits_after
    abs_val = abs(value)
    n = int(abs_val * (Decimal(10) ** digits_after))
    n = n % (10 ** total_digits)
    digits = list(str(n).zfill(total_digits).encode("ascii"))
    if value < 0:
        last = digits[-1] - ord('0')
        # overpunch table: digit -> ascii code  0→p(0x70)..9→y(0x79)
        digits[-1] = 0x70 + last
    return bytes(digits)


def _encode_alpha(value: str, length: int) -> bytes:
    """Encode PIC X(n): left-justify, space-pad to length, truncate if over."""
    s = value[:length].ljust(length, ' ')
    return s.encode("ascii")


# ---------------------------------------------------------------------------
# WORKING-STORAGE state object
# ---------------------------------------------------------------------------

class _WS:
    """Mirror of COBOL WORKING-STORAGE SECTION."""
    def __init__(self) -> None:
        # WS-INPUT-RECORD
        self.VL_EMP_ID:       Decimal = Decimal(0)   # PIC 9(6)
        self.VL_EMP_NAME:     str     = " " * 20     # PIC X(20)
        self.VL_HOURS_WORKED: Decimal = Decimal(0)   # PIC S9(3)V9(2)
        self.VL_HOURLY_RATE:  Decimal = Decimal(0)   # PIC 9(4)V9(2)
        # WS-OUTPUT-RECORD
        self.VL_OUT_EMP_ID:   Decimal = Decimal(0)   # PIC 9(6)
        self.VL_OUT_EMP_NAME: str     = " " * 20     # PIC X(20)
        self.VL_HOURS_CLEAN:  Decimal = Decimal(0)   # PIC 9(3)V9(2)
        self.VL_HOURLY_CLEAN: Decimal = Decimal(0)   # PIC 9(4)V9(2)
        self.VL_VALID_FLAG:   str     = " "          # PIC X(1)


# ---------------------------------------------------------------------------
# Paragraph implementations
# ---------------------------------------------------------------------------

def _validate_record(ws: _WS) -> None:
    """Mirror of VALIDATE-RECORD paragraph."""
    ws.VL_OUT_EMP_ID   = _store_display_unsigned(ws.VL_EMP_ID, 6, 0)
    ws.VL_OUT_EMP_NAME = ws.VL_EMP_NAME[:20]
    # TRAP: MOVE signed VL-HOURS-WORKED into unsigned VL-HOURS-CLEAN
    #       sign dropped; negative hours become their absolute value.
    ws.VL_HOURS_CLEAN  = _store_display_unsigned(ws.VL_HOURS_WORKED, 3, 2)
    ws.VL_HOURLY_CLEAN = _store_display_unsigned(ws.VL_HOURLY_RATE,  4, 2)
    if ws.VL_HOURLY_RATE > Decimal(0) and ws.VL_HOURS_CLEAN > Decimal(0):
        ws.VL_VALID_FLAG = 'Y'
    else:
        ws.VL_VALID_FLAG = 'N'


def _build_output(ws: _WS) -> bytes:
    """Assemble WS-OUTPUT-RECORD into 80 bytes."""
    out  = _encode_display_numeric(ws.VL_OUT_EMP_ID,   6, 0)   # 6
    out += _encode_alpha(ws.VL_OUT_EMP_NAME, 20)                # 20
    out += _encode_display_numeric(ws.VL_HOURS_CLEAN,  3, 2)    # 5
    out += _encode_display_numeric(ws.VL_HOURLY_CLEAN, 4, 2)    # 6
    out += ws.VL_VALID_FLAG.encode("ascii")                     # 1
    out += b' ' * 42                                             # 42 filler
    assert len(out) == 80, f"Output length {len(out)} != 80"
    return out


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run(record: dict) -> bytes:
    """run(record: dict) -> bytes  — matches verify/run_candidate.py interface."""
    ws = _WS()
    ws.VL_EMP_ID       = Decimal(str(record["VL-EMP-ID"]))
    ws.VL_EMP_NAME     = str(record.get("VL-EMP-NAME", "")).ljust(20)[:20]
    ws.VL_HOURS_WORKED = Decimal(str(record["VL-HOURS-WORKED"]))
    ws.VL_HOURLY_RATE  = Decimal(str(record["VL-HOURLY-RATE"]))
    _validate_record(ws)
    return _build_output(ws)
