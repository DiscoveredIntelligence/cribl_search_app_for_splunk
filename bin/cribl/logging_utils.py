"""
Enhanced logging utilities with timing and progress tracking.

Provides:
- TimingContext: Context manager for timing operations
- ProgressLogger: Log progress for long-running operations
- mask_sensitive: Mask sensitive values for safe logging
- Logging filter and formatter classes
"""

import logging
import time
import random
from typing import Optional, Callable


def generate_invocation_id() -> str:
    """
    Generate a unique identifier for this invocation.
    
    Returns:
        String in format "timestamp:random_number"
    """
    return f"{time.time()}:{random.randint(0, 100000)}"


def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive values for logging.
    
    Args:
        value: The sensitive value to mask
        visible_chars: Number of characters to keep visible at the start
        
    Returns:
        Masked string, e.g., 'secret123' -> 'secr****'
        
    Examples:
        >>> mask_sensitive('my_secret_key')
        'my_s****'
        >>> mask_sensitive('ab', visible_chars=4)
        '****'
        >>> mask_sensitive('', visible_chars=4)
        '****'
    """
    if not value:
        return "****"
    if len(value) <= visible_chars:
        return "****"
    return value[:visible_chars] + "****"


class CriblLogFilter(logging.Filter):
    """
    Logging filter that adds invocation_id and job_id to log records.
    
    This allows tracking all log messages related to a single
    criblsearch invocation and correlating them with Cribl job IDs.
    """
    
    def __init__(self, invocation_id: str):
        super().__init__()
        self.invocation_id = invocation_id
        self.job_id = None  # Will be set once job is created
    
    def set_job_id(self, job_id: str):
        """Set the Cribl job ID for inclusion in all subsequent log records."""
        self.job_id = job_id
    
    def filter(self, record):
        record.invocation_id = self.invocation_id
        record.job_id = self.job_id or "-"
        return True


class CriblLogFormatter(logging.Formatter):
    """
    Custom log formatter that outputs timestamps in UTC with milliseconds.
    """
    
    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        if datefmt:
            s = time.strftime(datefmt, ct)
        else:
            t = time.strftime("%Y-%m-%d %H:%M:%S", ct)
            s = "%s,%03d+0000" % (t, record.msecs)
        return s


class TimingContext:
    """
    Context manager for timing operations with automatic logging.
    
    Usage:
        with TimingContext(logger, "Authentication") as timer:
            # do authentication
            pass
        # Logs: "Authentication completed in 0.45s"
        
    Attributes:
        elapsed: Time elapsed in seconds (available after exiting context)
    """
    
    def __init__(self, logger: logging.Logger, operation_name: str, 
                 log_start: bool = True, log_level: int = logging.INFO):
        """
        Initialize the timing context.
        
        Args:
            logger: Logger instance to use
            operation_name: Name of the operation being timed
            log_start: Whether to log when starting the operation
            log_level: Logging level for messages
        """
        self.logger = logger
        self.operation_name = operation_name
        self.log_start = log_start
        self.log_level = log_level
        self.start_time: float = 0
        self.elapsed: float = 0
    
    def __enter__(self) -> 'TimingContext':
        self.start_time = time.time()
        if self.log_start:
            self.logger.log(logging.DEBUG, f"Starting {self.operation_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.time() - self.start_time
        if exc_type is None:
            self.logger.log(self.log_level, 
                          f"{self.operation_name} completed in {self.elapsed:.2f}s")
        else:
            self.logger.log(logging.ERROR, 
                          f"{self.operation_name} failed after {self.elapsed:.2f}s: {exc_val}")
        return False  # Don't suppress exceptions


class ProgressLogger:
    """
    Log progress for long-running operations like results retrieval.
    
    Usage:
        progress = ProgressLogger(logger, "Results retrieval", total=50000)
        for batch in batches:
            progress.update(len(batch))
        progress.complete()
    """
    
    def __init__(self, logger: logging.Logger, operation_name: str, 
                 total: int = 0, log_interval_pct: float = 10.0):
        """
        Initialize the progress logger.
        
        Args:
            logger: Logger instance to use
            operation_name: Name of the operation being tracked
            total: Total expected count (0 if unknown)
            log_interval_pct: Log every N percent of progress
        """
        self.logger = logger
        self.operation_name = operation_name
        self.total = total
        self.log_interval_pct = log_interval_pct
        self.current = 0
        self.last_logged_pct = 0
        self.start_time = time.time()
    
    def set_total(self, total: int):
        """Update the total count (useful when total is discovered during processing)."""
        self.total = total
    
    def update(self, count: int):
        """
        Update progress by adding count to current.
        
        Args:
            count: Number of items processed in this update
        """
        self.current += count
        
        if self.total > 0:
            current_pct = (self.current / self.total) * 100
            if current_pct >= self.last_logged_pct + self.log_interval_pct:
                self.logger.info(
                    f"{self.operation_name}: {self.current:,}/{self.total:,} "
                    f"({current_pct:.1f}%)"
                )
                self.last_logged_pct = int(current_pct / self.log_interval_pct) * self.log_interval_pct
    
    def complete(self, final_count: Optional[int] = None):
        """
        Mark the operation as complete and log final statistics.
        
        Args:
            final_count: Override the final count (uses current if not provided)
        """
        if final_count is not None:
            self.current = final_count
        
        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        
        self.logger.info(
            f"{self.operation_name} completed: {self.current:,} items "
            f"in {elapsed:.2f}s ({rate:,.0f} items/sec)"
        )


def sanitize_url_for_logging(url: str) -> str:
    """
    Remove potentially sensitive query parameters from URLs for logging.
    
    Args:
        url: The URL to sanitize
        
    Returns:
        URL with query parameters replaced by [REDACTED] if present
    """
    if '?' in url:
        base_url = url.split('?')[0]
        return f"{base_url}?[REDACTED]"
    return url


def format_bytes(size_bytes: int) -> str:
    """
    Format bytes as human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string like "1.5 MB" or "500 KB"
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
