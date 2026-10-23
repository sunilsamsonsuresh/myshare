"""HTTP-level tests: auth, permissions, expenses, balances, settlements, activity."""

from tests.conftest import signup


def expense(client, who, group_id, amount, payer, participants, kind="equal", params=None, **kw):
    body = {
        "group_id": group_id,
        "description": kw.pop("description", "Dinner"),
        "amount": amount,
        "payer_id": payer.id,
        "split": {"type": kind, "participants": participants},
        **kw,
    }
    return client.post("/expenses", json=body, headers=who.h, params=params)


# ---------- auth ----------
def test_signup_login_me(client):
    me = signup(client, "Zed")
    assert client.get("/users/me", headers=me.h).json()["email"] == "zed@test.dev"
    r = client.post("/auth/login", json={"email": "ZED@test.dev", "password": "password123"})
    assert r.status_code == 200
    bad = client.post("/auth/login", json={"email": "zed@test.dev", "password": "nope-nope"})
    assert bad.status_code == 401
    assert (
        client.post(
            "/auth/signup", json={"email": "zed@test.dev", "name": "Z", "password": "password123"}
        ).status_code
        == 409
    )


def test_requires_token(client):
    assert client.get("/groups").status_code == 401
    assert client.get("/groups", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_passwords_are_hashed(api_app, client):
    signup(client, "Hashy")
    from myshare_api.db import get_db
    from myshare_api.models import User

    db = next(api_app.dependency_overrides[get_db]())
    u = db.query(User).filter_by(email="hashy@test.dev").one()
    assert u.password_hash.startswith("$argon2")


# ---------- permissions ----------
def test_non_member_cannot_read_group(client, people, trip):
    mallory = people["mallory"]
    for path in (
        f"/groups/{trip}",
        f"/expenses?group_id={trip}",
        f"/groups/{trip}/simplified-debts",
        f"/activity?group_id={trip}",
        f"/balances?scope=group&id={trip}",
    ):
        r = client.get(path, headers=mallory.h)
        assert r.status_code == 404, path
        assert "not a member" in r.json()["detail"]


def test_non_member_cannot_see_or_edit_expense(client, people, trip):
    me, priya, mallory = people["me"], people["priya"], people["mallory"]
    eid = expense(client, me, trip, 900, me, [{"user_id": me.id}, {"user_id": priya.id}]).json()[
        "id"
    ]
    assert client.get(f"/expenses/{eid}", headers=mallory.h).status_code == 404
    assert (
        client.patch(f"/expenses/{eid}", json={"amount": 1}, headers=mallory.h).status_code == 404
    )
    assert client.delete(f"/expenses/{eid}", headers=mallory.h).status_code == 404
    assert all(e["id"] != eid for e in client.get("/expenses", headers=mallory.h).json())


def test_cannot_split_with_non_member_and_error_lists_members(client, people, trip):
    me, ananya = people["me"], people["ananya"]
    r = expense(client, me, trip, 900, me, [{"user_id": me.id}, {"user_id": ananya.id}])
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert f"[{ananya.id}]" in detail and "Priya" in detail and "Rahul" in detail


def test_resolve_only_finds_known_people(client, people, trip):
    me = people["me"]  # mallory exists but shares no group or friendship with me
    r = client.get("/people/resolve?name=pri", headers=me.h).json()
    assert [m["name"] for m in r["matches"]] == ["Priya"]
    # Mallory isn't connected to me, so she's not discoverable by name.
    assert client.get("/people/resolve?name=mallory", headers=me.h).json()["matches"] == []
    assert client.get("/people/resolve?name=me", headers=me.h).json()["matches"][0]["via"] == "you"


# ---------- balances ----------
def test_balances_are_derived_and_consistent(client, people, trip):
    me, priya, rahul = people["me"], people["priya"], people["rahul"]
    trio = [{"user_id": u.id} for u in (me, priya, rahul)]
    assert expense(client, me, trip, 3000, me, trio).status_code == 201  # each owes 1000
    assert expense(client, priya, trip, 600, priya, trio).status_code == 201  # each owes 200

    g = client.get(f"/groups/{trip}", headers=me.h).json()
    bal = {m["name"]: m["balance"] for m in g["members"]}
    assert bal == {"Me": 2000 - 200, "Priya": 400 - 1000, "Rahul": -1200}
    assert sum(bal.values()) == 0
    assert g["total_spent"] == 3600 and g["my_balance"] == 1800

    friends = {f["name"]: f["balances"] for f in client.get("/friends", headers=me.h).json()}
    assert friends["Priya"] == [{"currency": "INR", "amount": 800}]
    assert friends["Rahul"] == [{"currency": "INR", "amount": 1000}]

    s = client.get("/users/me/summary", headers=me.h).json()
    assert s["balances"] == [{"currency": "INR", "owed_to_you": 1800, "you_owe": 0, "net": 1800}]

    pr = client.get("/users/me/summary", headers=priya.h).json()["balances"][0]
    assert (pr["owed_to_you"], pr["you_owe"]) == (200, 800)  # rahul owes her 200, she owes me 800


def test_settlement_reduces_balance_and_simplify(client, people, trip):
    me, priya, rahul = people["me"], people["priya"], people["rahul"]
    trio = [{"user_id": u.id} for u in (me, priya, rahul)]
    expense(client, me, trip, 3000, me, trio)
    r = client.post(
        "/settlements",
        json={"group_id": trip, "from_user_id": rahul.id, "to_user_id": me.id, "amount": 400},
        headers=rahul.h,
    )
    assert r.status_code == 201
    bal = {
        m["name"]: m["balance"]
        for m in client.get(f"/groups/{trip}", headers=me.h).json()["members"]
    }
    assert bal == {"Me": 1600, "Priya": -1000, "Rahul": -600}

    s = client.get(f"/groups/{trip}/simplified-debts", headers=me.h).json()
    assert {
        (t["from_user"]["name"], t["to_user"]["name"], t["amount"]) for t in s["transfers"]
    } == {
        ("Priya", "Me", 1000),
        ("Rahul", "Me", 600),
    }


def test_settlement_requires_members(client, people, trip):
    me, ananya = people["me"], people["ananya"]
    r = client.post(
        "/settlements",
        json={"group_id": trip, "from_user_id": ananya.id, "to_user_id": me.id, "amount": 1},
        headers=me.h,
    )
    assert r.status_code == 422 and "must be members" in r.json()["detail"]


# ---------- expenses: edit / delete / friend expenses ----------
def test_update_amount_recomputes_split_and_logs(client, people, trip):
    me, priya = people["me"], people["priya"]
    eid = expense(
        client,
        me,
        trip,
        1000,
        me,
        [{"user_id": me.id, "value": 1}, {"user_id": priya.id, "value": 3}],
        kind="shares",
    ).json()["id"]
    r = client.patch(
        f"/expenses/{eid}", json={"amount": 2000, "description": "Big dinner"}, headers=priya.h
    )
    assert r.status_code == 200, r.text
    e = r.json()
    assert {s["user"]["name"]: s["owed_amount"] for s in e["splits"]} == {"Me": 500, "Priya": 1500}
    assert e["description"] == "Big dinner"
    act = client.get("/activity", headers=me.h).json()[0]
    assert act["verb"] == "expense_updated" and "amount" in act["data"]["changes"]


def test_soft_delete_removes_from_balances_and_logs(client, people, trip):
    me, priya = people["me"], people["priya"]
    eid = expense(client, me, trip, 1000, me, [{"user_id": me.id}, {"user_id": priya.id}]).json()[
        "id"
    ]
    assert client.get(f"/groups/{trip}", headers=me.h).json()["my_balance"] == 500
    assert client.delete(f"/expenses/{eid}", headers=priya.h).status_code == 200
    assert client.get(f"/groups/{trip}", headers=me.h).json()["my_balance"] == 0
    assert client.get(f"/expenses/{eid}", headers=me.h).status_code == 404
    assert client.get("/activity", headers=me.h).json()[0]["verb"] == "expense_deleted"


def test_friend_expense_and_breakdown(client, people):
    me, ananya = people["me"], people["ananya"]
    assert client.post("/friends", json={"email": ananya.email}, headers=me.h).status_code == 201
    r = client.post(
        "/expenses",
        headers=me.h,
        json={
            "friend_id": ananya.id,
            "description": "Cab",
            "amount": 500,
            "payer_id": ananya.id,
            "split": {
                "type": "equal",
                "participants": [{"user_id": me.id}, {"user_id": ananya.id}],
            },
        },
    )
    assert r.status_code == 201, r.text
    d = client.get(f"/balances?scope=friend&id={ananya.id}", headers=me.h).json()["friend"]
    assert d["balances"] == [{"currency": "INR", "amount": -250}]
    assert d["breakdown"][0]["group_name"] == "Non-group expenses"


def test_add_friend_unknown_email_is_actionable(client, people):
    r = client.post("/friends", json={"email": "ghost@nowhere.dev"}, headers=people["me"].h)
    assert r.status_code == 404 and "sign up first" in r.json()["detail"]


def test_expense_needs_exactly_one_target(client, people, trip):
    me = people["me"]
    r = client.post(
        "/expenses",
        headers=me.h,
        json={
            "description": "x",
            "amount": 1,
            "payer_id": me.id,
            "split": {"type": "equal", "participants": [{"user_id": me.id}]},
        },
    )
    assert r.status_code == 422 and "exactly one" in r.json()["detail"]


def test_list_filters_and_search(client, people, trip):
    me, priya = people["me"], people["priya"]
    pair = [{"user_id": me.id}, {"user_id": priya.id}]
    expense(client, me, trip, 100, me, pair, description="Pizza", date="2026-01-05")
    expense(client, me, trip, 100, me, pair, description="Petrol", date="2026-02-05")
    names = lambda r: [e["description"] for e in r.json()]  # noqa: E731
    assert names(client.get("/expenses?q=piz", headers=me.h)) == ["Pizza"]
    assert names(client.get("/expenses?since=2026-02-01", headers=me.h)) == ["Petrol"]
    assert names(client.get(f"/expenses?friend_id={priya.id}&limit=1", headers=me.h)) == ["Petrol"]


def test_remove_member_blocked_with_balance(client, people, trip):
    me, priya, rahul = people["me"], people["priya"], people["rahul"]
    expense(client, me, trip, 1000, me, [{"user_id": me.id}, {"user_id": priya.id}])
    r = client.delete(f"/groups/{trip}/members/{priya.id}", headers=me.h)
    assert r.status_code == 409 and "Settle up first" in r.json()["detail"]
    assert client.delete(f"/groups/{trip}/members/{rahul.id}", headers=me.h).status_code == 200


# ---------- dry run (used by the MCP host to render approval cards) ----------
def test_dry_run_previews_without_saving(client, people, trip):
    me, priya = people["me"], people["priya"]
    pair = [{"user_id": me.id}, {"user_id": priya.id}]
    r = expense(
        client, me, trip, 1001, me, pair, description="Preview me", params={"dry_run": True}
    )
    assert r.status_code == 201
    assert {s["user"]["name"]: s["owed_amount"] for s in r.json()["splits"]} == {
        "Me": 501,
        "Priya": 500,
    }
    assert client.get(f"/expenses?group_id={trip}", headers=me.h).json() == []
    assert client.get("/activity", headers=me.h).json()[0]["verb"] == "group_created"

    eid = expense(client, me, trip, 1000, me, pair).json()["id"]
    r = client.delete(f"/expenses/{eid}", params={"dry_run": True}, headers=me.h)
    assert r.status_code == 200
    assert client.get(f"/expenses/{eid}", headers=me.h).status_code == 200  # still there

    r = client.patch(
        f"/expenses/{eid}", params={"dry_run": True}, json={"payer_id": priya.id}, headers=me.h
    )
    assert r.json()["payer"]["name"] == "Priya"
    assert client.get(f"/expenses/{eid}", headers=me.h).json()["payer"]["name"] == "Me"


def test_dry_run_still_validates(client, people, trip):
    me, ananya = people["me"], people["ananya"]
    r = expense(client, me, trip, 100, me, [{"user_id": ananya.id}], params={"dry_run": True})
    assert r.status_code == 422


def test_timestamps_are_sent_as_utc(client, people, trip):
    # SQLite drops timezones; without UTCDateTime the API sent naive times that
    # browsers read as local time ("6 hours ago" for something done just now in IST).
    me = people["me"]
    e = client.post(
        "/expenses",
        headers=me.h,
        json={
            "group_id": trip,
            "description": "Chai",
            "amount": 100,
            "payer_id": me.id,
            "split": {"type": "equal", "participants": [{"user_id": me.id}]},
        },
    ).json()
    fetched = client.get(f"/expenses/{e['id']}", headers=me.h).json()
    activity = client.get("/activity", headers=me.h).json()[0]
    for stamp in (fetched["created_at"], fetched["updated_at"], activity["created_at"]):
        assert stamp.endswith(("Z", "+00:00")), stamp


# ---------- delete group ----------
def test_delete_group_blocked_until_settled_then_removes_everything(client, people, trip):
    me, priya = people["me"], people["priya"]
    pair = [{"user_id": me.id}, {"user_id": priya.id}]
    expense(client, me, trip, 1000, me, pair)

    r = client.delete(f"/groups/{trip}", headers=priya.h)
    assert r.status_code == 409
    assert "settled up" in r.json()["detail"] and "Priya owes ₹5.00" in r.json()["detail"]

    client.post(
        "/settlements",
        json={"group_id": trip, "from_user_id": priya.id, "to_user_id": me.id, "amount": 500},
        headers=priya.h,
    )
    preview = client.delete(f"/groups/{trip}", headers=priya.h, params={"dry_run": True})
    assert preview.status_code == 200 and preview.json()["name"] == "Goa Trip"
    assert client.get(f"/groups/{trip}", headers=me.h).status_code == 200  # dry run kept it

    assert client.delete(f"/groups/{trip}", headers=priya.h).status_code == 200  # any member may
    assert client.get(f"/groups/{trip}", headers=me.h).status_code == 404
    assert client.get("/groups", headers=me.h).json() == []
    assert client.get("/expenses", headers=me.h).json() == []
    assert client.get("/balances", headers=me.h).json()["overall"] == []
    feed = client.get("/activity", headers=me.h).json()
    assert feed[0]["verb"] == "group_deleted" and "Goa Trip" in feed[0]["summary"]
    assert all(a["group_id"] is None and a["expense_id"] is None for a in feed)  # history kept


def test_non_member_cannot_delete_group(client, people, trip):
    assert client.delete(f"/groups/{trip}", headers=people["mallory"].h).status_code == 404
    assert client.get(f"/groups/{trip}", headers=people["me"].h).status_code == 200
