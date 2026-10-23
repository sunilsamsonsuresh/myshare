"""Shared fixtures: an isolated in-memory API for every test.

The MCP server tests reuse `api_app` too: they point the MCP server's HTTP client
at this in-process API instead of a real network port.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from myshare_api.db import Base, get_db
from myshare_api.main import app


@pytest.fixture
def anyio_backend() -> str:
    # Async tests use AnyIO's pytest plugin (the MCP SDK is built on AnyIO). It runs an
    # async fixture's setup and teardown in the same task, which MCP client sessions need.
    return "asyncio"


@pytest.fixture
def api_app() -> Iterator:
    # StaticPool + in-memory SQLite = one shared connection, so every request sees the same DB.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield app
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def client(api_app) -> TestClient:
    return TestClient(api_app)


@dataclass
class Person:
    id: int
    name: str
    email: str
    token: str

    @property
    def h(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def signup(client: TestClient, name: str) -> Person:
    email = f"{name.lower()}@test.dev"
    r = client.post("/auth/signup", json={"email": email, "name": name, "password": "password123"})
    assert r.status_code == 201, r.text
    body = r.json()
    return Person(body["user"]["id"], name, email, body["access_token"])


@pytest.fixture
def people(client) -> dict[str, Person]:
    return {n.lower(): signup(client, n) for n in ("Me", "Priya", "Rahul", "Ananya", "Mallory")}


@pytest.fixture
def trip(client, people) -> int:
    """A group with me, priya, rahul (not ananya, not mallory)."""
    r = client.post(
        "/groups",
        json={
            "name": "Goa Trip",
            "kind": "trip",
            "member_emails": [people["priya"].email, people["rahul"].email],
        },
        headers=people["me"].h,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]
