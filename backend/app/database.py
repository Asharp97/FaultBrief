from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def database_engine(value: str) -> Engine:
    url = make_url(value)
    if url.get_backend_name() not in ("postgresql", "postgres"):
        raise ValueError("A PostgreSQL database URL is required.")
    url = url.set(drivername="postgresql+psycopg")
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )


def get_session(request: Request) -> Iterator[Session]:
    engine = request.app.state.database_engine
    if engine is None:
        raise HTTPException(503, "Database is not configured.")
    with Session(engine, expire_on_commit=False) as session:
        yield session
