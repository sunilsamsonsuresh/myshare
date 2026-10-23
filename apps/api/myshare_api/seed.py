"""Reset the database and load demo data.

    uv run python -m myshare_api.seed        (or: make seed)

Data is created THROUGH the API (an in-process TestClient), not by inserting rows,
so the seed obeys exactly the same validation and business rules as real usage.
"""

from __future__ import annotations

import datetime as dt
import sys

from fastapi.testclient import TestClient
from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .main import app
from .models import Activity, Expense, Settlement

PASSWORD = "password123"
PEOPLE = {
    "me": ("Sunil", "demo@myshare.app"),
    "priya": ("Priya Sharma", "priya@myshare.app"),
    "rahul": ("Rahul Verma", "rahul@myshare.app"),
    "ananya": ("Ananya Iyer", "ananya@myshare.app"),
}

TODAY = dt.date.today()


def days_ago(n: int) -> str:
    return (TODAY - dt.timedelta(days=n)).isoformat()


def main() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    c = TestClient(app)
    tokens: dict[str, str] = {}
    ids: dict[str, int] = {}
    for key, (name, email) in PEOPLE.items():
        r = c.post("/auth/signup", json={"email": email, "name": name, "password": PASSWORD})
        r.raise_for_status()
        tokens[key] = r.json()["access_token"]
        ids[key] = r.json()["user"]["id"]

    def as_(who: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[who]}"}

    def post(who: str, path: str, body: dict) -> dict:
        r = c.post(path, json=body, headers=as_(who))
        if r.status_code >= 400:
            sys.exit(f"seed failed: {path} {body} -> {r.status_code} {r.text}")
        return r.json()

    goa = post(
        "me",
        "/groups",
        {
            "name": "Goa Trip",
            "kind": "trip",
            "currency": "INR",
            "member_emails": [PEOPLE[k][1] for k in ("priya", "rahul", "ananya")],
        },
    )["id"]
    flat = post(
        "me",
        "/groups",
        {
            "name": "Flat 402",
            "kind": "home",
            "currency": "INR",
            "member_emails": [PEOPLE[k][1] for k in ("priya", "ananya")],
        },
    )["id"]

    everyone = [ids[k] for k in ("me", "priya", "rahul", "ananya")]
    flatmates = [ids[k] for k in ("me", "priya", "ananya")]

    def equal(people: list[int]) -> dict:
        return {"type": "equal", "participants": [{"user_id": u} for u in people]}

    def weighted(kind: str, pairs: list[tuple[str, str | int]]) -> dict:
        return {"type": kind, "participants": [{"user_id": ids[k], "value": v} for k, v in pairs]}

    # (who adds, group, description, rupees, payer, split, category, days ago)
    goa_expenses = [
        ("me", "Flights BLR to GOI", 24800, "me", equal(everyone), "travel", 34),
        ("priya", "Villa booking (3 nights)", 18000, "priya", equal(everyone), "lodging", 33),
        ("rahul", "Scooter rentals", 2400, "rahul", equal(everyone), "transport", 31),
        ("ananya", "Dinner at Thalassa", 6200, "ananya", equal(everyone), "food", 31),
        (
            "me",
            "Petrol",
            1200,
            "me",
            weighted("shares", [("me", 1), ("rahul", 1)]),
            "transport",
            30,
        ),
        ("priya", "Beach shack lunch", 2850, "priya", equal(everyone), "food", 30),
        (
            "rahul",
            "Parasailing",
            7000,
            "rahul",
            weighted("exact", [("rahul", 175000), ("priya", 175000), ("ananya", 350000)]),
            "entertainment",
            30,
        ),
        ("me", "Fish thali at Ritz Classic", 1960, "me", equal(everyone), "food", 29),
        (
            "ananya",
            "Cashew + feni souvenirs",
            3100,
            "ananya",
            weighted("percent", [("ananya", "50"), ("priya", "25"), ("me", "25")]),
            "shopping",
            29,
        ),
        ("priya", "Club entry, Tito's", 4000, "priya", equal(everyone), "entertainment", 29),
        ("me", "Breakfast at Artjuna", 1480, "me", equal(everyone), "food", 28),
        ("rahul", "Cab to airport", 1800, "rahul", equal(everyone), "transport", 28),
    ]
    flat_expenses = [
        ("me", "Rent: September", 54000, "me", equal(flatmates), "rent", 40),
        ("priya", "Electricity bill", 2340, "priya", equal(flatmates), "utilities", 37),
        ("ananya", "Wi-Fi (Airtel)", 1179, "ananya", equal(flatmates), "utilities", 36),
        ("me", "Groceries: BigBasket", 3215.5, "me", equal(flatmates), "groceries", 26),
        (
            "priya",
            "Maid salary",
            6000,
            "priya",
            weighted("shares", [("me", 1), ("priya", 1), ("ananya", 1)]),
            "utilities",
            21,
        ),
        ("ananya", "Cooking gas cylinder", 1105, "ananya", equal(flatmates), "utilities", 18),
        (
            "priya",
            "Rent: October",
            54000,
            "priya",
            weighted("percent", [("me", "40"), ("priya", "30"), ("ananya", "30")]),
            "rent",
            10,
        ),
        ("priya", "Groceries: Zepto", 1876.4, "priya", equal(flatmates), "groceries", 8),
        ("me", "Water cans", 360, "me", equal(flatmates), "utilities", 5),
        ("ananya", "Pizza night", 1640, "ananya", equal(flatmates), "food", 2),
    ]

    for who, desc, rupees, payer, split, cat, ago in goa_expenses:
        post(
            who,
            "/expenses",
            {
                "group_id": goa,
                "description": desc,
                "amount": round(rupees * 100),
                "payer_id": ids[payer],
                "split": split,
                "category": cat,
                "date": days_ago(ago),
            },
        )
    for who, desc, rupees, payer, split, cat, ago in flat_expenses:
        post(
            who,
            "/expenses",
            {
                "group_id": flat,
                "description": desc,
                "amount": round(rupees * 100),
                "payer_id": ids[payer],
                "split": split,
                "category": cat,
                "date": days_ago(ago),
            },
        )

    # Non-group expenses between friends
    post(
        "me",
        "/expenses",
        {
            "friend_id": ids["rahul"],
            "description": "Movie tickets: Dune 3",
            "amount": 98000,
            "payer_id": ids["me"],
            "split": equal([ids["me"], ids["rahul"]]),
            "category": "entertainment",
            "date": days_ago(15),
        },
    )
    post(
        "rahul",
        "/expenses",
        {
            "friend_id": ids["me"],
            "description": "Coffee at Third Wave",
            "amount": 64000,
            "payer_id": ids["rahul"],
            "split": equal([ids["me"], ids["rahul"]]),
            "category": "food",
            "date": days_ago(6),
        },
    )
    post(
        "priya",
        "/expenses",
        {
            "friend_id": ids["me"],
            "description": "Birthday gift for Ananya",
            "amount": 300000,
            "payer_id": ids["priya"],
            "split": equal([ids["me"], ids["priya"]]),
            "category": "shopping",
            "date": days_ago(3),
        },
    )

    # A couple of settlements
    post(
        "rahul",
        "/settlements",
        {
            "group_id": goa,
            "from_user_id": ids["rahul"],
            "to_user_id": ids["me"],
            "amount": 300000,
            "date": days_ago(20),
            "note": "UPI",
        },
    )
    post(
        "ananya",
        "/settlements",
        {
            "group_id": flat,
            "from_user_id": ids["ananya"],
            "to_user_id": ids["me"],
            "amount": 1500000,
            "date": days_ago(9),
            "note": "Rent share",
        },
    )

    # Make the activity feed look historical: stamp each entry with its expense/settlement date.
    with SessionLocal() as db:
        for act in db.scalars(select(Activity)):
            when: dt.date | None = None
            if act.expense_id:
                when = db.get(Expense, act.expense_id).date  # type: ignore[union-attr]
            elif act.settlement_id:
                when = db.get(Settlement, act.settlement_id).date  # type: ignore[union-attr]
            else:
                when = TODAY - dt.timedelta(days=45)
            act.created_at = dt.datetime.combine(when, dt.time(12, 0), dt.UTC) + dt.timedelta(
                minutes=act.id
            )
        db.commit()

    n = len(goa_expenses) + len(flat_expenses) + 3
    print(f"Seeded {len(PEOPLE)} users, 2 groups, {n} expenses, 2 settlements.")
    print(
        f"Log in as {PEOPLE['me'][1]} / {PASSWORD}  (others: priya@, rahul@, ananya@myshare.app, same password)"
    )


if __name__ == "__main__":
    main()
