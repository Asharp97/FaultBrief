import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.database import database_engine
from backend.app.models import Base

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def postgres_engine():
    value = os.environ.get("FAULTBRIEF_TEST_DATABASE_URL")
    if not value:
        if os.environ.get("CI"):
            pytest.fail("CI must configure its disposable PostgreSQL test database.")
        pytest.skip("Set FAULTBRIEF_TEST_DATABASE_URL to a disposable loopback *_test database.")
    url = make_url(value)
    if url.host not in {"localhost", "127.0.0.1", "::1"} or not (url.database or "").endswith(
        "_test"
    ):
        pytest.fail("Refusing migration tests outside a disposable loopback *_test database.")
    engine = database_engine(value)
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS migration_guard"))
        connection.execute(
            text("CREATE TABLE IF NOT EXISTS migration_guard.sentinel (id int PRIMARY KEY)")
        )
        connection.execute(
            text("INSERT INTO migration_guard.sentinel VALUES (1) ON CONFLICT DO NOTHING")
        )
        command.upgrade(config, "head")
        command.check(config)
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names(schema="faultbrief")) == {"alembic_version"}
        command.upgrade(config, "head")
        command.upgrade(config, "head")  # Idempotent replay must preserve the final schema.
        command.check(config)
        assert set(inspect(connection).get_table_names(schema="faultbrief")) == {
            table.name for table in Base.metadata.tables.values()
        } | {"alembic_version"}
        assert connection.scalar(text("SELECT count(*) FROM migration_guard.sentinel")) == 1
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(postgres_engine):
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        transaction.rollback()
