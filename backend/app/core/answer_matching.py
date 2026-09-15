"""Dependency-free title matching shared by repositories and services."""
from collections.abc import Iterable
import unicodedata


def normalized_answer(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in value if character.isalnum())


def matches_answer(submitted: str, title: str, aliases: Iterable[str] = ()) -> bool:
    supplied = normalized_answer(submitted)
    return bool(supplied) and any(
        supplied == normalized_answer(answer) for answer in (title, *aliases)
    )
