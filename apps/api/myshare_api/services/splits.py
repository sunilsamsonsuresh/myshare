"""Pure split math. No database, no I/O, so it's easy to test exhaustively.

Invariant (tested): sum(result.values()) == total, always.

Rounding policy: compute each person's exact share, floor it to whole minor
units, then hand out the leftover units one at a time to participants in the
order they were given. This is deterministic: the same input always gives the
same output, and the first-listed people absorb at most one extra paisa each.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class SplitType(StrEnum):
    EQUAL = "equal"
    EXACT = "exact"
    PERCENT = "percent"
    SHARES = "shares"


class SplitError(ValueError):
    """Invalid split input. The message is written for the end user (and for an LLM to self-correct)."""


@dataclass(frozen=True)
class Participant:
    user_id: int
    # equal: ignored · exact: minor units · percent: e.g. "33.33" · shares: e.g. "2"
    value: Decimal | None = None


def _distribute_remainder(floors: list[int], total: int) -> list[int]:
    leftover = total - sum(floors)
    # leftover is always 0 <= leftover < len(floors) for the floor-based methods.
    return [f + (1 if i < leftover else 0) for i, f in enumerate(floors)]


def _require_values(participants: list[Participant], kind: str) -> list[Decimal]:
    missing = [p.user_id for p in participants if p.value is None]
    if missing:
        raise SplitError(
            f"A {kind} split needs a value for every participant; missing for user ids {missing}."
        )
    return [p.value for p in participants]  # type: ignore[misc]


def compute_split(
    total: int, split_type: SplitType | str, participants: list[Participant]
) -> dict[int, int]:
    """Return {user_id: owed_minor_units}. Order of keys follows `participants`."""
    split_type = SplitType(split_type)
    if total <= 0:
        raise SplitError("The expense amount must be greater than zero.")
    if not participants:
        raise SplitError("A split needs at least one participant.")
    ids = [p.user_id for p in participants]
    if len(set(ids)) != len(ids):
        raise SplitError("Each person can appear only once in a split.")

    n = len(participants)

    if split_type is SplitType.EQUAL:
        owed = _distribute_remainder([total // n] * n, total)

    elif split_type is SplitType.EXACT:
        values = _require_values(participants, "exact")
        if any(v != v.to_integral_value() or v < 0 for v in values):
            raise SplitError("Exact split amounts must be non-negative whole minor units.")
        owed = [int(v) for v in values]
        if sum(owed) != total:
            diff = total - sum(owed)
            raise SplitError(
                f"Exact amounts add up to {sum(owed)} but the expense total is {total} "
                f"(minor units); they are {'short' if diff > 0 else 'over'} by {abs(diff)}."
            )

    elif split_type is SplitType.PERCENT:
        values = _require_values(participants, "percent")
        if any(v < 0 for v in values):
            raise SplitError("Percentages can't be negative.")
        if sum(values) != Decimal(100):
            raise SplitError(
                f"Percentages must add up to exactly 100; they add up to {sum(values)}."
            )
        owed = _weighted(total, values)

    else:  # SHARES
        values = _require_values(participants, "shares")
        if any(v < 0 for v in values):
            raise SplitError("Shares can't be negative.")
        total_shares = sum(values)
        if total_shares <= 0:
            raise SplitError("At least one participant needs a share greater than zero.")
        owed = _weighted(total, values)

    assert sum(owed) == total, "split invariant violated"
    return dict(zip(ids, owed, strict=True))


def _weighted(total: int, weights: list[Decimal]) -> list[int]:
    """Split `total` proportionally to `weights` (percentages or share counts).

    Floors each exact share, then hands leftover units to participants in input
    order, skipping anyone with weight 0 (0% / 0 shares must owe exactly 0).
    """
    weight_sum = sum(weights)
    floors = [int(total * w // weight_sum) for w in weights]
    eligible = [i for i, w in enumerate(weights) if w > 0]
    for k in range(total - sum(floors)):  # leftover < number of eligible participants
        floors[eligible[k % len(eligible)]] += 1
    return floors


def parse_value(raw: str | int | float | Decimal | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation as exc:
        raise SplitError(f"'{raw}' is not a number.") from exc
