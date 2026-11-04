"""Half-up rounding on integers: ties go away from zero, so -2.5 becomes -3 at 0 places."""

from decimal import Decimal
from fractions import Fraction


def round_half_up(value: Fraction, places: int) -> Fraction:
    scale = 10**places
    magnitude = abs(value) * scale
    rounded = (2 * magnitude.numerator + magnitude.denominator) // (2 * magnitude.denominator)
    return Fraction(rounded if value >= 0 else -rounded, scale)


def truncate(value: Fraction, places: int) -> Fraction:
    scale = 10**places
    magnitude = abs(value) * scale
    kept = magnitude.numerator // magnitude.denominator
    return Fraction(kept if value >= 0 else -kept, scale)


def as_decimal(value: Fraction, places: int) -> Decimal:
    """Exact presentation of a value that is already rounded to `places`."""
    scaled = value * 10**places
    if scaled.denominator != 1:
        raise ValueError("the value has more decimal places than requested")
    digits = tuple(int(digit) for digit in str(abs(scaled.numerator)))
    return Decimal((1 if scaled < 0 else 0, digits, -places))
