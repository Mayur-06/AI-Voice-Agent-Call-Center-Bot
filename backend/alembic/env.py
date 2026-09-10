from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

sys.path.append(os.getcwd())

from app.database import Base
from app.models.database import Persona, Session, Message, Voice, Document, DocumentChunk, SentimentRecord, CallMetric, Recording

config = context.config
target_metadata = Base.metadata

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.config import settings

db_url = settings.database_url
if "+asyncpg" in db_url:
    db_url = db_url.replace("+asyncpg", "+psycopg2")

config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    context.configure(url=db_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
