"""Physical unit conversion; this module does not assign treatment actions.

3% Sodium Chloride Injection labels specify sodium 513 mEq/L (0.513 mEq/mL).
Source: DailyMed setid f2475fa3-ab1d-4b81-8127-b58cd0790a54, DESCRIPTION,
verified 2026-10-11. This rounded label concentration is the declared basis.
Callers must independently establish solution identity and administered volume.
An order quantity, bag capacity or diagnostic rate integral is not established
actual volume merely because it can be passed to this arithmetic function.
"""
from decimal import Decimal
import math


SODIUM_MEQ_PER_ML_3PCT_NACL = Decimal("0.513")


def sodium_meq_from_3pct_saline_ml(volume_ml: int | float) -> float:
    """Convert nonnegative mL of verified 3% NaCl to sodium mEq; no binning.

    Zero is valid arithmetic, not evidence that an untreated decision exists.
    Strings, booleans, nonfinite and negative values are rejected rather than
    silently parsing ambiguous source fields or clipping impossible amounts.
    """
    if isinstance(volume_ml, bool) or not isinstance(volume_ml, (int, float)):
        raise ValueError("volume_ml must be a finite nonnegative number")
    try:
        finite = math.isfinite(volume_ml)
    except OverflowError:
        finite = False
    if not finite or volume_ml < 0:
        raise ValueError("volume_ml must be a finite nonnegative number")
    return float(Decimal(str(volume_ml)) * SODIUM_MEQ_PER_ML_3PCT_NACL)
