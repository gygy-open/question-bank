from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

import asyncio
import sys
import os
sys.path.append(os.getcwd())

import app.models  # noqa: F401, E402 - registers every model for autogenerate
from app.models import Base  # noqa: E402
from app.core.config import settings, get_db_url

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url. Precedence: an explicit URL set by the programmatic
# runner (config.set_main_option) > resolved runtime URL (env/.env/config.json).
_url = config.get_main_option("sqlalchemy.url") or get_db_url() or settings.DB_URL
config.set_main_option("sqlalchemy.url", _url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# 迁移内联建的无 FK 归档表,不进 ORM;autogenerate / command.check 必须忽略它,
# 否则会误报 "应 DROP" 的漂移。仅精确匹配该表名,不宽泛忽略其它对象。
_MIGRATION_ONLY_TABLES = {"questions_content_archive_v1"}


def _include_object(object, name, type_, reflected, compare_to):
    return not (type_ == "table" and name in _MIGRATION_ONLY_TABLES)


def do_run_migrations(connection):
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        render_as_batch=True,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
