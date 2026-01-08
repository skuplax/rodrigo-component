"""Database connection and session management

Two engines are provided:
- Async engine (asyncpg) for FastAPI endpoints
- Sync engine (psycopg2) for background threads
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import os
import logging
from typing import Tuple, Dict, Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_database_urls() -> Tuple[str, str, Dict[str, Any]]:
    """
    Get database URLs for both async and sync engines.
    
    Returns:
        Tuple of (async_url, sync_url, ssl_connect_args)
    """
    database_url = os.getenv("DATABASE_URL")
    is_supabase = False
    
    if database_url:
        is_supabase = "supabase.co" in database_url or "pooler.supabase.com" in database_url
        
        # Parse and clean URL
        parsed = urlparse(database_url)
        query_params = parse_qs(parsed.query)
        
        # Remove sslmode from URL (handled via connect_args)
        if "sslmode" in query_params:
            del query_params["sslmode"]
        
        new_query = urlencode(query_params, doseq=True)
        clean_url = urlunparse((
            "postgresql",  # Use base scheme, we'll add driver below
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        # Create driver-specific URLs
        async_url = clean_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        sync_url = clean_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        
        # SSL config
        ssl_args = {}
        if is_supabase:
            ssl_args["ssl"] = "require"
        
        return async_url, sync_url, ssl_args
    
    # Fallback: construct from individual environment variables
    user = os.getenv("user") or os.getenv("DB_USER") or os.getenv("POSTGRES_USER")
    password = os.getenv("password") or os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("host") or os.getenv("DB_HOST") or os.getenv("POSTGRES_HOST")
    port = os.getenv("port") or os.getenv("DB_PORT") or os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("dbname") or os.getenv("DB_NAME") or os.getenv("POSTGRES_DB", "postgres")
    
    if all([user, password, host]):
        async_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"
        sync_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
        is_supabase = "supabase.co" in host
        
        ssl_args = {}
        if is_supabase:
            ssl_args["ssl"] = "require"
        
        logger.info("Constructed DATABASE_URL from individual environment variables")
        return async_url, sync_url, ssl_args
    
    raise ValueError(
        "DATABASE_URL or individual database credentials (user, password, host) must be set."
    )


# Get database URLs
ASYNC_DATABASE_URL, SYNC_DATABASE_URL, SSL_ARGS = get_database_urls()


# =============================================================================
# ASYNC ENGINE - For FastAPI endpoints (non-blocking)
# =============================================================================

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    connect_args=SSL_ARGS,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncSession:
    """FastAPI dependency for async database access"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# =============================================================================
# SYNC ENGINE - For background threads (blocking is OK)
# =============================================================================

# For psycopg2, SSL is configured differently
sync_connect_args = {}
if SSL_ARGS.get("ssl") == "require":
    sync_connect_args["sslmode"] = "require"

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=5,
    pool_recycle=3600,
    connect_args=sync_connect_args,
)

SyncSessionLocal = sessionmaker(
    sync_engine,
    expire_on_commit=False
)


def get_sync_session() -> Session:
    """Get a sync database session for background threads"""
    return SyncSessionLocal()
