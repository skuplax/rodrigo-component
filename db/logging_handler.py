"""Database logging handler for Supabase"""

import logging
import threading
from queue import Queue, Empty
from typing import Optional
import traceback

from db.database import get_sync_session
from db.models import Log


class SupabaseLogHandler(logging.Handler):
    """
    Async-safe logging handler that writes to Supabase.
    
    Uses a background thread and queue to avoid blocking the main thread
    and to prevent database writes during async operations.
    """
    
    def __init__(self, level: int = logging.INFO, batch_size: int = 10, flush_interval: float = 5.0):
        """
        Initialize the Supabase log handler.
        
        Args:
            level: Minimum log level to capture
            batch_size: Number of logs to batch before writing
            flush_interval: Seconds to wait before flushing partial batch
        """
        super().__init__(level)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        
        self._queue: Queue = Queue()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        
        # Loggers to exclude to prevent infinite recursion
        self._excluded_loggers = {
            'sqlalchemy.engine',
            'sqlalchemy.pool',
            'sqlalchemy.orm',
            'asyncpg',
            'httpx',
            'httpcore',
        }
    
    def start(self):
        """Start the background worker thread"""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="SupabaseLogWorker",
                daemon=True
            )
            self._worker_thread.start()
    
    def stop(self):
        """Stop the background worker thread"""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)
    
    def emit(self, record: logging.LogRecord):
        """Queue a log record for async writing"""
        # Skip excluded loggers to prevent recursion
        if any(record.name.startswith(excluded) for excluded in self._excluded_loggers):
            return
        
        try:
            # Format the log record
            log_entry = {
                'level': record.levelname,
                'logger_name': record.name,
                'message': self.format(record) if self.formatter else record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line_number': record.lineno,
                'exception_info': None,
                'extra_data': None,
            }
            
            # Capture exception info if present
            if record.exc_info:
                log_entry['exception_info'] = ''.join(traceback.format_exception(*record.exc_info))
            
            # Capture extra data if present
            extra = {}
            for key, value in record.__dict__.items():
                if key not in ('name', 'msg', 'args', 'created', 'filename', 'funcName',
                              'levelname', 'levelno', 'lineno', 'module', 'msecs',
                              'pathname', 'process', 'processName', 'relativeCreated',
                              'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
                              'message', 'taskName'):
                    try:
                        # Only include JSON-serializable values
                        import json
                        json.dumps(value)
                        extra[key] = value
                    except (TypeError, ValueError):
                        pass
            
            if extra:
                log_entry['extra_data'] = extra
            
            self._queue.put(log_entry)
            
        except Exception:
            # Don't raise exceptions from logging
            self.handleError(record)
    
    def _worker_loop(self):
        """Background thread that writes logs to database"""
        batch = []
        
        while not self._stop_event.is_set():
            try:
                # Get log entry with timeout for periodic flushing
                try:
                    entry = self._queue.get(timeout=self.flush_interval)
                    batch.append(entry)
                except Empty:
                    pass
                
                # Flush when batch is full or on timeout with partial batch
                if len(batch) >= self.batch_size or (batch and self._queue.empty()):
                    self._flush_batch(batch)
                    batch = []
                    
            except Exception as e:
                # Log to stderr since we can't use logging here
                import sys
                print(f"SupabaseLogHandler worker error: {e}", file=sys.stderr)
        
        # Final flush on shutdown
        if batch:
            self._flush_batch(batch)
        
        # Drain remaining queue
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except Empty:
                break
        
        if batch:
            self._flush_batch(batch)
    
    def _flush_batch(self, batch: list):
        """Write a batch of logs to database"""
        if not batch:
            return
        
        try:
            with get_sync_session() as session:
                logs = [Log(**entry) for entry in batch]
                session.add_all(logs)
                session.commit()
        except Exception as e:
            import sys
            print(f"SupabaseLogHandler flush error: {e}", file=sys.stderr)


def setup_supabase_logging(
    level: int = logging.INFO,
    batch_size: int = 10,
    flush_interval: float = 5.0
) -> SupabaseLogHandler:
    """
    Set up Supabase logging handler on the root logger.
    
    Args:
        level: Minimum log level to capture
        batch_size: Number of logs to batch before writing
        flush_interval: Seconds to wait before flushing partial batch
        
    Returns:
        The configured SupabaseLogHandler instance
    """
    handler = SupabaseLogHandler(
        level=level,
        batch_size=batch_size,
        flush_interval=flush_interval
    )
    
    # Use a simple format since we're storing structured data
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    # Start the worker thread
    handler.start()
    
    return handler

