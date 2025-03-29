"""
Retry Utility Module
Provides functionality for retrying operations with exponential backoff
"""
import random
import time
import logging
from functools import wraps
from typing import Callable, Type, List, Optional, Union, TypeVar, Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Type variable for the return type of the function being retried
T = TypeVar('T')


def retry_with_backoff(
    max_retries: int = 5,
    initial_backoff: float = 1.0,
    max_backoff: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions_to_retry: Optional[List[Type[Exception]]] = None,
    exceptions_to_ignore: Optional[List[Type[Exception]]] = None,
    should_retry_fn: Optional[Callable[[Exception], bool]] = None,
    on_retry_callback: Optional[Callable[[int, Exception, float], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying a function with exponential backoff
    
    Args:
        max_retries: Maximum number of retries
        initial_backoff: Initial backoff time in seconds
        max_backoff: Maximum backoff time in seconds
        backoff_factor: Multiplier for backoff time after each retry
        jitter: Whether to add randomness to backoff time
        exceptions_to_retry: List of exception types to retry on (default: all exceptions)
        exceptions_to_ignore: List of exception types to ignore (not retry)
        should_retry_fn: Function to determine if retry should be attempted based on exception
        on_retry_callback: Function to call before each retry
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            retries = 0
            backoff = initial_backoff
            
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    
                    # Check if we've exceeded max retries
                    if retries > max_retries:
                        logger.error(f"Failed after {max_retries} retries: {str(e)}")
                        raise
                    
                    # Check if this exception should be retried
                    should_retry = True
                    
                    # If specific exceptions to retry are provided, check if this is one of them
                    if exceptions_to_retry is not None and not any(isinstance(e, exc) for exc in exceptions_to_retry):
                        should_retry = False
                    
                    # If specific exceptions to ignore are provided, check if this is one of them
                    if exceptions_to_ignore is not None and any(isinstance(e, exc) for exc in exceptions_to_ignore):
                        should_retry = False
                    
                    # If a custom retry function is provided, use it
                    if should_retry_fn is not None:
                        should_retry = should_retry_fn(e)
                    
                    if not should_retry:
                        logger.warning(f"Not retrying exception: {str(e)}")
                        raise
                    
                    # Calculate backoff time with jitter if enabled
                    wait_time = backoff
                    if jitter:
                        wait_time = backoff * (0.5 + random.random())
                    
                    # Call the retry callback if provided
                    if on_retry_callback is not None:
                        on_retry_callback(retries, e, wait_time)
                    
                    logger.warning(
                        f"Retry {retries}/{max_retries} after {wait_time:.2f}s due to: {str(e)}"
                    )
                    
                    # Wait before retrying
                    time.sleep(wait_time)
                    
                    # Increase backoff for next retry, but don't exceed max_backoff
                    backoff = min(backoff * backoff_factor, max_backoff)
        
        return wrapper
    
    return decorator


def is_rate_limit_error(exception: Exception) -> bool:
    """
    Check if an exception is due to rate limiting
    
    Args:
        exception: The exception to check
        
    Returns:
        bool: True if the exception is due to rate limiting
    """
    # Check for Slack API rate limit errors
    if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
        if exception.response.status_code == 429:
            return True
    
    # Check for error message containing rate limit indicators
    error_str = str(exception).lower()
    rate_limit_indicators = ['rate limit', 'ratelimit', 'too many requests', '429']
    return any(indicator in error_str for indicator in rate_limit_indicators)


def is_connection_error(exception: Exception) -> bool:
    """
    Check if an exception is due to connection issues
    
    Args:
        exception: The exception to check
        
    Returns:
        bool: True if the exception is due to connection issues
    """
    error_str = str(exception).lower()
    connection_indicators = [
        'connection', 'timeout', 'timed out', 'network', 'unreachable',
        'connection reset', 'connection refused', 'no route to host'
    ]
    return any(indicator in error_str for indicator in connection_indicators)


def is_temporary_error(exception: Exception) -> bool:
    """
    Check if an exception is likely temporary and worth retrying
    
    Args:
        exception: The exception to check
        
    Returns:
        bool: True if the exception is likely temporary
    """
    # Check for rate limit errors
    if is_rate_limit_error(exception):
        return True
    
    # Check for connection errors
    if is_connection_error(exception):
        return True
    
    # Check for HTTP 5xx errors
    if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
        if 500 <= exception.response.status_code < 600:
            return True
    
    # Check for error message containing temporary error indicators
    error_str = str(exception).lower()
    temporary_indicators = [
        'temporary', 'retry', 'try again', 'timeout', 'overloaded',
        'server error', 'internal server error', 'service unavailable'
    ]
    return any(indicator in error_str for indicator in temporary_indicators)