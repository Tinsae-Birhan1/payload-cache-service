import hashlib
import json
from collections.abc import Sequence

# Matches the sample output in the spec. Note the format is lossy: a string that itself
# contains ", " cannot be told apart from two strings. Kept because it is the contract.
OUTPUT_SEPARATOR = ", "


def interleave(first: Sequence[str], second: Sequence[str]) -> list[str]:
    """Return ``[first[0], second[0], first[1], second[1], ...]``.

    Raises ``ValueError`` on length mismatch instead of silently truncating (``zip``
    default) - dropping user data without an error would be a bug, not a feature.
    """
    if len(first) != len(second):
        raise ValueError(f"lists must have equal length, got {len(first)} and {len(second)}")
    return [item for pair in zip(first, second, strict=True) for item in pair]


def render_output(first: Sequence[str], second: Sequence[str]) -> str:
    return OUTPUT_SEPARATOR.join(interleave(first, second))


def payload_fingerprint(first: Sequence[str], second: Sequence[str]) -> str:
    """Stable identity of a payload request, used to reuse previously generated payloads.

    JSON-encoding the two lists (rather than joining strings) keeps the encoding
    unambiguous: ``(["a, b"], ["c"])`` and ``(["a"], ["b, c"])`` hash differently.
    """
    canonical = json.dumps([list(first), list(second)], ensure_ascii=False, separators=(",", ":"))
    return _sha256(canonical)


def transformation_key(value: str) -> str:
    """Cache key for one transformer input. Exact match: no case or whitespace folding,
    because the transformer may treat ``"a"`` and ``"A "`` differently."""
    return _sha256(value)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
