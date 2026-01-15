# =============================================================================
# CUSTOM EXCEPTION HIERARCHY
# =============================================================================
# Comprehensive error handling for Twitter translation bot

from .base_exceptions import (
    TwitterBotError,
    APIError,
    NetworkError,
    ValidationError,
    ConfigurationError
)

from .twitter_exceptions import (
    TwitterAPIError,
    TwitterRateLimitError,
    TwitterAuthError,
    TwitterConnectionError,
    TwitterQuotaExceededError
)

from .gemini_exceptions import (
    GeminiAPIError,
    GeminiQuotaError,
    GeminiUnavailableError,
    GeminiRateLimitError,
    GeminiAuthError
)

from .translation_exceptions import (
    TranslationError,
    TranslationTimeoutError,
    TranslationValidationError,
    TranslationCacheError
)

__all__ = [
    # Base exceptions
    'TwitterBotError',
    'APIError', 
    'NetworkError',
    'ValidationError',
    'ConfigurationError',
    
    # Twitter-specific exceptions
    'TwitterAPIError',
    'TwitterRateLimitError', 
    'TwitterAuthError',
    'TwitterConnectionError',
    'TwitterQuotaExceededError',
    
    # Gemini-specific exceptions
    'GeminiAPIError',
    'GeminiQuotaError',
    'GeminiUnavailableError', 
    'GeminiRateLimitError',
    'GeminiAuthError',
    
    # Translation-specific exceptions
    'TranslationError',
    'TranslationTimeoutError',
    'TranslationValidationError',
    'TranslationCacheError'
]
