"""Albumnesia: ten points per album, declining by two per guessing second."""
from decimal import Decimal, ROUND_HALF_UP


def album_score(remaining_ms: int, correct: bool) -> Decimal:
    remaining = max(0, min(5000, remaining_ms)) if correct else 0
    return (Decimal(remaining) * Decimal("2.00") / Decimal(1000)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
