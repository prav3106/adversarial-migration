"""
translation/a/_cobol_codec.py — shared COBOL encoding helpers for Translator A.

Rules (from PROJECT_CONTEXT.md):
- All numeric values use decimal.Decimal. Never use float.
- COMPUTE truncates unless ROUNDED present; ROUNDED = ROUND_HALF_UP.
- Overflow = high-order truncation (keep rightmost digits to fit the field).
- Moving a negative value into an unsigned field stores the absolute value.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP


# ---------------------------------------------------------------------------
# Arithmetic helpers
# ---------------------------------------------------------------------------

def trunc(value: Decimal, digits_after: int) -> Decimal:
    """Truncate value to digits_after decimal places (COMPUTE without ROUNDED)."""
    if digits_after == 0:
        return value.to_integral_value(rounding=ROUND_DOWN)
    scale = Decimal(10) ** -digits_after
    # Truncate toward zero
    if value >= 0:
        return (value * (Decimal(10) ** digits_after)).to_integral_value(
            rounding=ROUND_DOWN
        ) * scale
    else:
        return -((-value * (Decimal(10) ** digits_after)).to_integral_value(
            rounding=ROUND_DOWN
        ) * scale)


def round_half_up(value: Decimal, digits_after: int) -> Decimal:
    """Round to digits_after decimal places using ROUND_HALF_UP (COMPUTE ROUNDED)."""
    scale = Decimal(10) ** -digits_after
    return value.quantize(scale, rounding=ROUND_HALF_UP)


def cobol_trunc_unsigned(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """
    Apply COBOL high-order truncation to fit value into a 9(digits_before)V9(digits_after) field.
    Value is assumed non-negative (sign already stripped if needed).
    Truncates fractional digits first, then masks to field width.
    """
    value = trunc(value, digits_after)
    total_digits = digits_before + digits_after
    scale = Decimal(10) ** -digits_after
    # Convert to integer representation, apply modulo, convert back
    int_repr = int(abs(value) * (Decimal(10) ** digits_after))
    int_repr = int_repr % (10 ** total_digits)
    return Decimal(int_repr) * scale


def cobol_trunc_signed(value: Decimal, digits_before: int, digits_after: int) -> Decimal:
    """
    Apply COBOL high-order truncation for a signed field S9(digits_before)V9(digits_after).
    Sign is preserved; magnitude is truncated to field width.
    """
    value = trunc(value, digits_after)
    total_digits = digits_before + digits_after
    scale = Decimal(10) ** -digits_after
    int_repr = int(abs(value) * (Decimal(10) ** digits_after))
    int_repr = int_repr % (10 ** total_digits)
    result = Decimal(int_repr) * scale
    if value < 0:
        result = -result
    return result


# ---------------------------------------------------------------------------
# DISPLAY encoding
# ---------------------------------------------------------------------------

# Overpunch table for COBOL DISPLAY signed (GnuCOBOL / ASCII):
#   positive (not used — GnuCOBOL emits plain ASCII digits for non-negative):
#     0->{, 1->A, 2->B, 3->C, 4->D, 5->E, 6->F, 7->G, 8->H, 9->I
#   negative: GnuCOBOL stores last digit as (0x70 | digit):
#     0->p, 1->q, 2->r, 3->s, 4->t, 5->u, 6->v, 7->w, 8->x, 9->y
_OVERPUNCH_POS = b"{ABCDEFGHI"
_OVERPUNCH_NEG = bytes(0x70 | d for d in range(10))


def enc_unsigned_display(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """
    Encode a non-negative Decimal as COBOL DISPLAY 9(digits_before)V9(digits_after).
    Byte length = digits_before + digits_after. Implied decimal point (V) — not stored.
    Overflow: high-order truncation.
    Input value must already be non-negative (caller strips sign per COBOL MOVE rule).
    """
    total_digits = digits_before + digits_after
    # Scale to integer, truncate, then mask
    int_repr = int((abs(value) * (Decimal(10) ** digits_after)).to_integral_value(rounding=ROUND_DOWN))
    int_repr = int_repr % (10 ** total_digits)
    return str(int_repr).zfill(total_digits).encode("ascii")


def enc_signed_display(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """
    Encode a signed Decimal as COBOL DISPLAY S9(digits_before)V9(digits_after).
    Byte length = digits_before + digits_after (sign encoded in last byte via overpunch).
    Overflow: high-order truncation of magnitude.

    GnuCOBOL DISPLAY signed encoding:
      - Negative values: last digit is replaced by overpunch character (}JKLMNOPQR).
      - Positive (and zero) values: all digits are plain ASCII — no overpunch applied.
    """
    total_digits = digits_before + digits_after
    int_repr = int((abs(value) * (Decimal(10) ** digits_after)).to_integral_value(rounding=ROUND_DOWN))
    int_repr = int_repr % (10 ** total_digits)
    digits_str = str(int_repr).zfill(total_digits)
    if value < 0:
        last_digit = int(digits_str[-1])
        body = digits_str[:-1].encode("ascii")
        last_byte = bytes([_OVERPUNCH_NEG[last_digit]])
        return body + last_byte
    else:
        return digits_str.encode("ascii")


# ---------------------------------------------------------------------------
# COMP-3 (packed decimal) encoding
# ---------------------------------------------------------------------------

def enc_comp3(value: Decimal, digits_before: int, digits_after: int) -> bytes:
    """
    Encode a non-negative Decimal as COBOL COMP-3 (packed decimal).
    Format: each digit in one nibble, last nibble is sign (C=positive, F=unsigned).
    Byte length = ceil((digits_before + digits_after + 1) / 2).
    Overflow: high-order truncation of magnitude.
    """
    total_digits = digits_before + digits_after
    byte_length = (total_digits + 1 + 1) // 2  # ceil((total_digits + sign_nibble) / 2)

    int_repr = int((abs(value) * (Decimal(10) ** digits_after)).to_integral_value(rounding=ROUND_DOWN))
    # High-order truncation
    int_repr = int_repr % (10 ** total_digits)

    # Build nibble list: total_digits data nibbles + 1 sign nibble (F = unsigned positive)
    digits_str = str(int_repr).zfill(total_digits)
    nibbles = [int(d) for d in digits_str] + [0xF]  # 0xF = unsigned/positive
    # Pad to even count
    if len(nibbles) % 2 != 0:
        nibbles = [0] + nibbles
    result = bytearray()
    for i in range(0, len(nibbles), 2):
        result.append((nibbles[i] << 4) | nibbles[i + 1])
    assert len(result) == byte_length, f"COMP-3 length mismatch: {len(result)} vs {byte_length}"
    return bytes(result)
