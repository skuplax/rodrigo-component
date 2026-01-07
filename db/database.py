"""Database connection and session management"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import os
import asyncio
import logging
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_database_url() -> Tuple[str, Dict[str, Any]]:
    """
    Get database URL from environment variables.
    Supports both single DATABASE_URL and individual components (for Supabase).
    Returns tuple of (database_url, connect_args) where connect_args includes SSL config for asyncpg.
    """
    # Try single DATABASE_URL first
    database_url = os.getenv("DATABASE_URL")
    is_supabase = False
    
    if database_url:
        # Check if this is a Supabase connection
        is_supabase = "supabase.co" in database_url or "supabase" in database_url.lower() or "pooler.supabase.com" in database_url
        
        # Convert postgresql:// to postgresql+asyncpg:// for async SQLAlchemy
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif database_url.startswith("postgresql+psycopg2://"):
            # Convert psycopg2 to asyncpg if needed
            database_url = database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        
        # Remove sslmode from URL if present (asyncpg doesn't use it in URL)
        parsed = urlparse(database_url)
        query_params = parse_qs(parsed.query)
        if "sslmode" in query_params:
            del query_params["sslmode"]
        
        # Reconstruct URL without sslmode
        new_query = urlencode(query_params, doseq=True)
        database_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        # Configure SSL for asyncpg via connect_args
        connect_args = {}
        if is_supabase:
            connect_args["ssl"] = "require"
        
        return database_url, connect_args
    
    # Fallback: construct from individual environment variables (Supabase style)
    user = os.getenv("user") or os.getenv("DB_USER") or os.getenv("POSTGRES_USER")
    password = os.getenv("password") or os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("host") or os.getenv("DB_HOST") or os.getenv("POSTGRES_HOST")
    port = os.getenv("port") or os.getenv("DB_PORT") or os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("dbname") or os.getenv("DB_NAME") or os.getenv("POSTGRES_DB", "postgres")
    
    if all([user, password, host]):
        database_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"
        is_supabase = "supabase.co" in host or "supabase" in host.lower()
        
        connect_args = {}
        if is_supabase:
            connect_args["ssl"] = "require"
        
        logger.info("Constructed DATABASE_URL from individual environment variables")
        return database_url, connect_args
    
    raise ValueError(
        "DATABASE_URL or individual database credentials (user, password, host) must be set. "
        "For Supabase, either set DATABASE_URL or set: user, password, host, port, dbname"
    )


# Get database URL and SSL configuration
DATABASE_URL, CONNECT_ARGS = get_database_url()

# Create async engine with SSL support for Supabase
# asyncpg uses connect_args['ssl'] instead of URL parameters
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL logging during development
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,  # Recycle connections after 1 hour to prevent stale connections
    pool_reset_on_return='commit',  # Reset connection state on return to pool
    connect_args=CONNECT_ARGS,  # SSL configuration for asyncpg
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncSession:
    """Dependency for getting database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def run_async(coro):
    """
    Run async coroutine from sync context (for threading compatibility)
    
    Args:
        coro: Coroutine to run
        
    Returns:
        Result of the coroutine
    """
    try:
        # Try to get existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, we need to use a different approach
            # Create a new task or use asyncio.run_coroutine_threadsafe
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop exists, create a new one
        return asyncio.run(coro)


async def get_db_session() -> AsyncSession:
    """Get a database session (for direct use)"""
    return AsyncSessionLocal()

