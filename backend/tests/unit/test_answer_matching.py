import pytest

from backend.app.core.answer_matching import matches_answer


@pytest.mark.parametrize("guess", [
    "the lion king", "THE LION KING", "tHe LiOn KiNg",
    "  the   lion king  ", "the\tlion\nking", "The Lion King!",
])
def test_title_formatting_is_ignored(guess):
    assert matches_answer(guess, "The Lion King")


def test_aliases_and_accents():
    assert matches_answer("amELIE", "Amélie")
    assert matches_answer("  TLK! ", "The Lion King", ["Tlk"])


@pytest.mark.parametrize("guess", ["", "  ", "!!!", "Lion", "The Lion Queen", "The Lion King 2"])
def test_empty_partial_and_different_titles_are_rejected(guess):
    assert not matches_answer(guess, "The Lion King")
