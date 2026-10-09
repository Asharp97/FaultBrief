from logging.config import fileConfig

from alembic import context
from sqlalchemy import text

from backend.app.config import Settings
from backend.app.database import database_engine
from backend.app.models import SCHEMA, Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == SCHEMA
    return parent_names.get("schema_name") == SCHEMA


def migration_url() -> str:
    settings = Settings()
    value = settings.migration_database_url or settings.database_url
    if value is None:
        raise RuntimeError("A database URL is required to apply migrations.")
    return value.get_secret_value()


def configure(connection=None, url=None):
    context.configure(
        connection=connection,
        url=url,
        target_metadata=Base.metadata,
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
        version_table_schema=SCHEMA,
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"},
    )


def run_online(connection):
    # Schema exists before Alembic creates its own version table. No other schema is managed.
    connection.execute(text("CREATE SCHEMA IF NOT EXISTS faultbrief"))
    configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    configure(url="postgresql+psycopg://offline/offline")
    with context.begin_transaction():
        context.execute("CREATE SCHEMA IF NOT EXISTS faultbrief")
        context.run_migrations()
else:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        run_online(supplied)
    else:
        engine = database_engine(migration_url())
        try:
            with engine.begin() as connection:
                run_online(connection)
        finally:
            engine.dispose()
