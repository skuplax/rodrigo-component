"""Database connection and session management"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import os
import asyncio
import logging
import threading
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Global reference to the main event loop for cross-thread async operations
_main_loop: Optional[asyncio.AbstractEventLoop] = None
_main_loop_lock = threading.Lock()


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


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """
    Set the main event loop reference for cross-thread async operations.
    Should be called once during application startup from the main async context.
    
    Args:
        loop: The main asyncio event loop
    """
    global _main_loop
    with _main_loop_lock:
        _main_loop = loop
        logger.info("Main event loop registered for cross-thread database operations")


def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    """Get the main event loop reference"""
    with _main_loop_lock:
        return _main_loop


def _is_main_loop_thread() -> bool:
    """Check if we're running in the main event loop's thread"""
    main_loop = get_main_loop()
    if main_loop is None:
        return False
    try:
        # If the loop is running and we can get its thread, check if it's current
        return main_loop.is_running() and threading.current_thread() is threading.main_thread()
    except Exception:
        return False


def fire_and_forget_async(coro):
    """
    Schedule an async coroutine to run without waiting for the result.
    
    This is safe to call from any context (sync or async, main thread or background).
    Errors are logged but not raised.
    
    Args:
        coro: Coroutine to schedule
    """
    def handle_error(future):
        """Callback to log errors from the coroutine"""
        try:
            future.result()
        except Exception as e:
            logger.error(f"Error in fire-and-forget async operation: {e}")
    
    main_loop = get_main_loop()
    if main_loop is not None and main_loop.is_running():
        # Schedule on the main loop (works from any thread)
        future = asyncio.run_coroutine_threadsafe(coro, main_loop)
        future.add_done_callback(handle_error)
        return
    
    # No main loop - try to create a task or run directly
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context - create a task
        task = loop.create_task(coro)
        task.add_done_callback(lambda t: t.result() if not t.cancelled() else None)
        return
    except RuntimeError:
        pass
    
    # Last resort: run synchronously (during startup)
    try:
        asyncio.run(coro)
    except Exception as e:
        logger.error(f"Error running async operation: {e}")


def run_async(coro, allow_main_thread_block: bool = False):
    """
    Run async coroutine from sync context (for threading compatibility).
    
    Uses the registered main event loop when called from background threads
    to ensure database connections work correctly with asyncpg.
    
    WARNING: If called from the main thread while the event loop is running,
    this may cause issues. For non-critical operations (like saving state), 
    use fire_and_forget_async() instead.
    
    Args:
        coro: Coroutine to run
        allow_main_thread_block: If True, allow blocking the main thread (use with caution)
        
    Returns:
        Result of the coroutine
    """
    try:
        # Check if we have a main loop registered and it's still running
        main_loop = get_main_loop()
        
        if main_loop is not None and main_loop.is_running():
            # Check if we're in the main thread - this could deadlock
            if _is_main_loop_thread():
                if not allow_main_thread_block:
                    # Being called from main thread with running event loop
                    # This typically means we're in sync code called from async context
                    # Using run_coroutine_threadsafe here would deadlock
                    # Close the coroutine to avoid "coroutine was never awaited" warning
                    coro.close()
                    raise RuntimeError(
                        "run_async() called from main thread with running event loop. "
                        "Use fire_and_forget_async() for non-blocking operations, or "
                        "set allow_main_thread_block=True if you're certain this won't deadlock."
                    )
                else:
                    logger.warning(
                        "run_async() blocking main thread with running event loop. "
                        "This may cause issues."
                    )
            
            # Schedule on the main loop (works from background threads)
            future = asyncio.run_coroutine_threadsafe(coro, main_loop)
            # Wait for result with a timeout
            try:
                return future.result(timeout=30.0)
            except TimeoutError:
                future.cancel()
                raise TimeoutError("Database operation timed out after 30 seconds")
        
        # No main loop or it's not running - try to get/create a loop
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                return loop.run_until_complete(coro)
        except RuntimeError:
            pass
        
        # Last resort: create a new event loop
        # This is used during startup before the main loop is registered
        return asyncio.run(coro)
        
    except RuntimeError:
        # Re-raise RuntimeError without logging (expected for main thread detection)
        raise
    except Exception as e:
        logger.error(f"Error in run_async: {e}")
        raise


async def get_db_session() -> AsyncSession:
    """Get a database session (for direct use)"""
    return AsyncSessionLocal()

