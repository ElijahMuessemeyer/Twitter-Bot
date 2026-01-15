# =============================================================================
# RETRY LOGIC WITH EXPONENTIAL BACKOFF
# =============================================================================
# Robust retry mechanism with configurable strategies

import time
import random
import functools
from typing import Type, Tuple, Callable, Any, Optional, Dict, List
from ..exceptions import (
    TwitterBotError, 
    TwitterRateLimitError, 
    GeminiRateLimitError,
    NetworkError,
    TwitterConnectionError,
    GeminiUnavailableError
)
from ..utils.logger import logger
from ..utils.structured_logger import structured_logger


class RetryConfig:
    """Configuration for retry behavior"""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        jitter_range: float = 0.1
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.jitter_range = jitter_range


class RetryStrategy:
    """Define which exceptions should trigger retries and with what config"""
    
    # Default retry configurations for different error types
    STRATEGIES: Dict[Type[Exception], RetryConfig] = {
        # Network errors - aggressive retry
        NetworkError: RetryConfig(
            max_attempts=5,
            base_delay=1.0,
            max_delay=30.0,
            exponential_base=2.0
        ),
        
        # Twitter connection errors - moderate retry  
        TwitterConnectionError: RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            max_delay=60.0,
            exponential_base=2.0
        ),
        
        # Rate limit errors - wait and retry
        TwitterRateLimitError: RetryConfig(
            max_attempts=2,
            base_delay=60.0,  # Start with 1 minute wait
            max_delay=900.0,  # Max 15 minutes
            exponential_base=1.5
        ),
        
        # Gemini rate limits - shorter delays
        GeminiRateLimitError: RetryConfig(
            max_attempts=3,
            base_delay=5.0,
            max_delay=120.0,
            exponential_base=2.0
        ),
        
        # Gemini service unavailable - moderate retry
        GeminiUnavailableError: RetryConfig(
            max_attempts=3,
            base_delay=10.0,
            max_delay=180.0,
            exponential_base=2.0
        )
    }
    
    @classmethod
    def get_config_for_exception(cls, exc: Exception) -> Optional[RetryConfig]:
        """Get retry configuration for a specific exception"""
        for exc_type, config in cls.STRATEGIES.items():
            if isinstance(exc, exc_type):
                return config
        
        # Check if it's a retryable TwitterBotError
        if isinstance(exc, TwitterBotError) and exc.retryable:
            return RetryConfig(max_attempts=2, base_delay=2.0, max_delay=30.0)
        
        return None


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for a given attempt with exponential backoff and jitter"""
    # Exponential backoff
    delay = config.base_delay * (config.exponential_base ** (attempt - 1))
    
    # Cap at max delay
    delay = min(delay, config.max_delay)
    
    # Add jitter to prevent thundering herd
    if config.jitter:
        jitter_amount = delay * config.jitter_range
        jitter_offset = random.uniform(-jitter_amount, jitter_amount)
        delay = max(0, delay + jitter_offset)
    
    return delay


def retry_with_backoff(
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None
):
    """
    Decorator for retrying functions with exponential backoff
    
    Args:
        retryable_exceptions: Tuple of exception types to retry on
        config: Custom retry configuration
        on_retry: Callback function called on each retry attempt
    """
    
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            max_attempts = config.max_attempts if config else 3
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    
                    # Log success if we had previous failures
                    if attempt > 1:
                        structured_logger.info(
                            f"Function {func.__name__} succeeded on attempt {attempt}",
                            event="retry_success",
                            function=func.__name__,
                            attempt=attempt,
                            total_attempts=attempt
                        )
                    
                    return result
                    
                except Exception as exc:
                    last_exception = exc
                    
                    # Determine if we should retry this exception
                    retry_config = config
                    if not retry_config:
                        retry_config = RetryStrategy.get_config_for_exception(exc)
                    
                    # Check custom retryable exceptions
                    should_retry = False
                    if retryable_exceptions and isinstance(exc, retryable_exceptions):
                        should_retry = True
                    elif retry_config:
                        should_retry = True
                    
                    # Don't retry if we've reached max attempts
                    max_attempts = retry_config.max_attempts if retry_config else 3
                    if attempt >= max_attempts:
                        should_retry = False
                    
                    if not should_retry:
                        # Log final failure
                        structured_logger.error(
                            f"Function {func.__name__} failed permanently",
                            event="retry_failed_permanently",
                            function=func.__name__,
                            attempt=attempt,
                            error_type=exc.__class__.__name__,
                            error_message=str(exc)
                        )
                        raise exc
                    
                    # Calculate delay for next attempt
                    delay = calculate_delay(attempt, retry_config)
                    
                    # Log retry attempt
                    structured_logger.warning(
                        f"Function {func.__name__} failed on attempt {attempt}, retrying in {delay:.1f}s",
                        event="retry_attempt",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay_seconds=delay,
                        error_type=exc.__class__.__name__,
                        error_message=str(exc)
                    )
                    
                    # Call retry callback if provided
                    if on_retry:
                        try:
                            on_retry(attempt, exc)
                        except Exception as callback_exc:
                            logger.warning(f"Retry callback failed: {callback_exc}")
                    
                    # Wait before next attempt
                    time.sleep(delay)
            
            # If we get here, all attempts failed
            structured_logger.error(
                f"Function {func.__name__} failed after all retry attempts",
                event="retry_exhausted",
                function=func.__name__,
                max_attempts=max_attempts,
                final_error_type=last_exception.__class__.__name__ if last_exception else "Unknown",
                final_error_message=str(last_exception) if last_exception else "Unknown error"
            )
            
            raise last_exception
        
        return wrapper
    return decorator


def retry_async_with_backoff(
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None
):
    """
    Async version of retry decorator
    """
    import asyncio
    
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            max_attempts = config.max_attempts if config else 3
            for attempt in range(1, max_attempts + 1):
                try:
                    result = await func(*args, **kwargs)
                    
                    # Log success if we had previous failures
                    if attempt > 1:
                        structured_logger.info(
                            f"Async function {func.__name__} succeeded on attempt {attempt}",
                            event="async_retry_success",
                            function=func.__name__,
                            attempt=attempt,
                            total_attempts=attempt
                        )
                    
                    return result
                    
                except Exception as exc:
                    last_exception = exc
                    
                    # Determine if we should retry this exception
                    retry_config = config
                    if not retry_config:
                        retry_config = RetryStrategy.get_config_for_exception(exc)
                    
                    # Check custom retryable exceptions
                    should_retry = False
                    if retryable_exceptions and isinstance(exc, retryable_exceptions):
                        should_retry = True
                    elif retry_config:
                        should_retry = True
                    
                    # Don't retry if we've reached max attempts
                    max_attempts = retry_config.max_attempts if retry_config else 3
                    if attempt >= max_attempts:
                        should_retry = False
                    
                    if not should_retry:
                        # Log final failure
                        structured_logger.error(
                            f"Async function {func.__name__} failed permanently",
                            event="async_retry_failed_permanently",
                            function=func.__name__,
                            attempt=attempt,
                            error_type=exc.__class__.__name__,
                            error_message=str(exc)
                        )
                        raise exc
                    
                    # Calculate delay for next attempt
                    delay = calculate_delay(attempt, retry_config)
                    
                    # Log retry attempt
                    structured_logger.warning(
                        f"Async function {func.__name__} failed on attempt {attempt}, retrying in {delay:.1f}s",
                        event="async_retry_attempt",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay_seconds=delay,
                        error_type=exc.__class__.__name__,
                        error_message=str(exc)
                    )
                    
                    # Call retry callback if provided
                    if on_retry:
                        try:
                            on_retry(attempt, exc)
                        except Exception as callback_exc:
                            logger.warning(f"Async retry callback failed: {callback_exc}")
                    
                    # Wait before next attempt
                    await asyncio.sleep(delay)
            
            # If we get here, all attempts failed
            structured_logger.error(
                f"Async function {func.__name__} failed after all retry attempts",
                event="async_retry_exhausted",
                function=func.__name__,
                max_attempts=max_attempts,
                final_error_type=last_exception.__class__.__name__ if last_exception else "Unknown",
                final_error_message=str(last_exception) if last_exception else "Unknown error"
            )
            
            raise last_exception
        
        return wrapper
    return decorator


# Convenience function for manual retries
def execute_with_retry(
    func: Callable[..., Any],
    *args,
    config: Optional[RetryConfig] = None,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    **kwargs
) -> Any:
    """
    Execute a function with retry logic
    
    Example:
        result = execute_with_retry(
            risky_function,
            arg1, arg2,
            config=RetryConfig(max_attempts=5),
            retryable_exceptions=(ConnectionError, TimeoutError),
            kwarg1="value"
        )
    """
    decorated_func = retry_with_backoff(
        retryable_exceptions=retryable_exceptions,
        config=config
    )(func)
    
    return decorated_func(*args, **kwargs)
