from decimal import Decimal

import pytest

from backend.app.core.album_scoring import album_score


@pytest.mark.parametrize("remaining, expected", [
    (5000, "10.00"), (4000, "8.00"), (3000, "6.00"), (2000, "4.00"),
    (1000, "2.00"), (0, "0.00"), (3250, "6.50"), (1234, "2.47"),
    (2, "0.00"), (3, "0.01"), (-100, "0.00"), (6000, "10.00"),
])
def test_time_remaining_score(remaining, expected):
    result = album_score(remaining, True)
    assert result == Decimal(expected)
    assert result.as_tuple().exponent == -2


def test_wrong_answer_has_no_score():
    assert album_score(5000, False) == Decimal("0.00")
