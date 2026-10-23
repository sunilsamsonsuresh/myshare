import datetime as dt
from collections.abc import Iterator

from sqlalchemy import DateTime, Dialect, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import get_settings


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[dt.datetime]):
    """A timestamp that always comes back from the database as timezone-aware UTC.

    SQLite has no timezone type, so `DateTime(timezone=True)` loses the "+00:00" and
    returns naive datetimes. The API would then send "2026-10-23T10:42:40" without a
    "Z", and browsers read that as LOCAL time (in IST, everything showed "6 hours ago").
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: dt.datetime | None, dialect: Dialect) -> dt.datetime | None:
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(dt.UTC)
        return value

    def process_result_value(
        self, value: dt.datetime | None, dialect: Dialect
    ) -> dt.datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=dt.UTC)
        return value


def make_engine(url: str) -> Engine:
    engine = create_engine(
        url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite ignores foreign keys unless asked
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request. Tests override this."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
