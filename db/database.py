"""Database connection and session management

Single sync engine (psycopg2) for all database operations.
This simplifies connection management for Supabase's session mode pooler.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import os
import logging
from typing import Tuple, Dict, Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_database_url() -> Tuple[str, Dict[str, Any]]:
    """
    Get database URL for sync engine.
    
    Returns:
        Tuple of (sync_url, ssl_connect_args)
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
            "postgresql+psycopg2",
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        # SSL config for psycopg2
        ssl_args = {}
        if is_supabase:
            ssl_args["sslmode"] = "require"
        
        return clean_url, ssl_args
    
    # Fallback: construct from individual environment variables
    user = os.getenv("user") or os.getenv("DB_USER") or os.getenv("POSTGRES_USER")
    password = os.getenv("password") or os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("host") or os.getenv("DB_HOST") or os.getenv("POSTGRES_HOST")
    port = os.getenv("port") or os.getenv("DB_PORT") or os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("dbname") or os.getenv("DB_NAME") or os.getenv("POSTGRES_DB", "postgres")
    
    if all([user, password, host]):
        sync_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
        is_supabase = "supabase.co" in host
        
        ssl_args = {}
        if is_supabase:
            ssl_args["sslmode"] = "require"
        
        logger.info("Constructed DATABASE_URL from individual environment variables")
        return sync_url, ssl_args
    
    raise ValueError(
        "DATABASE_URL or individual database credentials (user, password, host) must be set."
    )


# Get database URL
DATABASE_URL, SSL_ARGS = get_database_url()


# =============================================================================
# SYNC ENGINE - Single connection pool for all database operations
# =============================================================================

sync_engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=3,          # Small pool for Supabase session mode
    max_overflow=2,       # Max 5 total connections
    pool_recycle=300,     # Recycle every 5 min
    pool_timeout=30,      # Wait up to 30s for a connection
    connect_args=SSL_ARGS,
)

SyncSessionLocal = sessionmaker(
    sync_engine,
    expire_on_commit=False
)


@contextmanager
def get_sync_session():
    """Get a sync database session with automatic cleanup"""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
