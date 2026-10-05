"""Pure payload rules: how outputs are assembled and how inputs are identified."""

import hashlib
import json
from collections.abc import Sequence

OUTPUT_SEPARATOR = ", "


def interleave(first: Sequence[str], second: Sequence[str]) -> list[str]:
    """Alternate items: first[0], second[0], first[1], second[1], ..."""
    # strict=True: unequal lengths are a caller bug, never silently truncate.
    return [item for pair in zip(first, second, strict=True) for item in pair]


def build_output(first: Sequence[str], second: Sequence[str]) -> str:
    return OUTPUT_SEPARATOR.join(interleave(first, second))


def payload_key(list_1: Sequence[str], list_2: Sequence[str]) -> str:
    """Deterministic identity of an input pair, used to reuse payload ids.

    JSON preserves list boundaries, ordering, and escaping, avoiding ambiguous
    representations such as ["a,b"], ["c"] versus ["a"], ["b,c"].
    """
    canonical = json.dumps(
        [list(list_1), list(list_2)], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
