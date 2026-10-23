"""MyShare REST API: the single source of truth for data, business rules and authorization.

Every other component (the MCP server, the web app) is a client of this API.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, engine
from .routers import activity, auth, balances, expenses, groups, settlements, users


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Simple schema bootstrap (no Alembic for this learning project).
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="MyShare API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, users, groups, expenses, settlements, balances, activity):
    app.include_router(r.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
