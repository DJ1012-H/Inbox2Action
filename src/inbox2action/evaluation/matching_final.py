"""Field-aware argument matching for the converged stage-two candidate."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher

from pydantic import JsonValue

_NATURAL_LANGUAGE_FIELDS = frozenset(
    {
        "body",
        "description",
        "question",
        "subject",
        "summary",
        "title",
    }
)
_SPACE_OR_PUNCTUATION = re.compile(r"[\W_]+", flags=re.UNICODE)


def arguments_satisfy_final(
    assertions: Mapping[str, Mapping[str, JsonValue]],
    observed: Sequence[tuple[int, str, Mapping[str, JsonValue]]],
) -> bool:
    """Match structured values strictly and natural-language wording semantically."""

    return all(
        any(
            tool_name == expected_tool
            and _json_subset(expected, actual, field_name=None)
            for _, tool_name, actual in observed
        )
        for expected_tool, expected in assertions.items()
    )


def _json_subset(
    expected: object,
    actual: object,
    *,
    field_name: str | None,
) -> bool:
    if isinstance(expected, dict) and set(expected) == {"$contains_all"}:
        raw_fragments = expected["$contains_all"]
        fragments = (
            [raw_fragments] if isinstance(raw_fragments, str) else raw_fragments
        )
        return (
            isinstance(actual, str)
            and isinstance(fragments, list)
            and bool(fragments)
            and all(
                isinstance(fragment, str)
                and bool(fragment)
                and _normalize_text(fragment) in _normalize_text(actual)
                for fragment in fragments
            )
        )
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual
            and _json_subset(value, actual[key], field_name=str(key))
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(
            _json_subset(left, right, field_name=field_name)
            for left, right in zip(expected, actual, strict=True)
        )
    if (
        isinstance(expected, str)
        and isinstance(actual, str)
        and field_name in _NATURAL_LANGUAGE_FIELDS
    ):
        return _natural_language_equivalent(expected, actual)
    return expected == actual


def _natural_language_equivalent(expected: str, actual: str) -> bool:
    left = _normalize_text(expected)
    right = _normalize_text(actual)
    if not left or not right:
        return left == right
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) >= 4 and shorter in longer:
        return True
    return SequenceMatcher(a=left, b=right, autojunk=False).ratio() >= 0.78


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _SPACE_OR_PUNCTUATION.sub("", normalized)
