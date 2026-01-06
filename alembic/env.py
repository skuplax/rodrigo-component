from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import models and Base for autogenerate support
from db.models import Base
target_metadata = Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Get DATABASE_URL from environment and convert to async format
# Use the same logic as db.database to ensure consistency
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

database_url = os.getenv("DATABASE_URL")
is_supabase = False

if database_url:
    # Check if this is a Supabase connection
    is_supabase = "supabase.co" in database_url or "supabase" in database_url.lower() or "pooler.supabase.com" in database_url
    
    # Convert postgresql:// to postgresql+asyncpg:// for async SQLAlchemy
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    
    # Remove sslmode from URL (asyncpg doesn't use it in URL, we'll use connect_args)
    parsed = urlparse(database_url)
    query_params = parse_qs(parsed.query)
    if "sslmode" in query_params:
        del query_params["sslmode"]
    
    new_query = urlencode(query_params, doseq=True)
    database_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))
    
    config.set_main_option("sqlalchemy.url", database_url)
    
    # Store SSL requirement for use in engine creation
    if is_supabase:
        # We'll configure SSL via connect_args in the engine creation
        # Store this in config for later use
        config.attributes["ssl_required"] = True
else:
    # Fallback: construct from individual environment variables
    user = os.getenv("user") or os.getenv("DB_USER") or os.getenv("POSTGRES_USER")
    password = os.getenv("password") or os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("host") or os.getenv("DB_HOST") or os.getenv("POSTGRES_HOST")
    port = os.getenv("port") or os.getenv("DB_PORT") or os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("dbname") or os.getenv("DB_NAME") or os.getenv("POSTGRES_DB", "postgres")
    
    if all([user, password, host]):
        is_supabase = "supabase.co" in host or "supabase" in host.lower()
        database_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"
        config.set_main_option("sqlalchemy.url", database_url)
        if is_supabase:
            config.attributes["ssl_required"] = True
    else:
        raise ValueError("DATABASE_URL or individual database credentials must be set")

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

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


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    # Configure SSL for Supabase if needed
    connect_args = {}
    if config.attributes.get("ssl_required", False):
        connect_args["ssl"] = "require"
    
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a synchronous connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with async support."""
    import asyncio
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
