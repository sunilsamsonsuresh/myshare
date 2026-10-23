"""Debt simplification: turn net balances into the fewest transfers we can find quickly.

Input: {user_id: net} where net > 0 means "is owed money" and net < 0 means "owes".
The nets must sum to zero (they always do when derived from expenses + settlements).

Greedy algorithm: repeatedly match the largest creditor with the largest debtor and
transfer min(credit, debt). Each step zeroes out at least one person, so there are
at most (people with non-zero balance - 1) transfers. Finding the true minimum is
NP-hard (it's a subset-sum style problem); greedy is what Splitwise-style apps use
and is optimal or near-optimal in practice.

Ties are broken by user_id so the output is deterministic (and testable).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transfer:
    from_user_id: int  # debtor: pays
    to_user_id: int  # creditor: receives
    amount: int  # minor units, > 0


def simplify_debts(nets: dict[int, int]) -> list[Transfer]:
    if sum(nets.values()) != 0:
        raise ValueError(f"Net balances must sum to zero, got {sum(nets.values())}")

    creditors = {u: n for u, n in nets.items() if n > 0}
    debtors = {u: -n for u, n in nets.items() if n < 0}
    transfers: list[Transfer] = []

    while creditors and debtors:
        # Largest amount first; lowest id wins a tie.
        c = min(creditors, key=lambda u: (-creditors[u], u))
        d = min(debtors, key=lambda u: (-debtors[u], u))
        amount = min(creditors[c], debtors[d])
        transfers.append(Transfer(from_user_id=d, to_user_id=c, amount=amount))
        creditors[c] -= amount
        debtors[d] -= amount
        if creditors[c] == 0:
            del creditors[c]
        if debtors[d] == 0:
            del debtors[d]

    return transfers
