# =============================================================================
# TWITTER-SPECIFIC EXCEPTIONS
# =============================================================================
# Error handling for Twitter API interactions

from .base_exceptions import APIError


class TwitterAPIError(APIError):
    """General Twitter API error"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, **kwargs)


class TwitterRateLimitError(TwitterAPIError):
    """Twitter API rate limit exceeded"""
    
    def __init__(
        self,
        message: str = "Twitter API rate limit exceeded",
        reset_time: int = None,
        remaining: int = 0,
        **kwargs
    ):
        kwargs.setdefault('retryable', True)
        kwargs.setdefault('error_code', 'RATE_LIMIT')
        super().__init__(message, **kwargs)
        self.reset_time = reset_time
        self.remaining = remaining
        
    def to_dict(self):
        result = super().to_dict()
        result.update({
            'reset_time': self.reset_time,
            'remaining': self.remaining
        })
        return result


class TwitterAuthError(TwitterAPIError):
    """Twitter authentication/authorization error"""
    
    def __init__(self, message: str = "Twitter authentication failed", **kwargs):
        kwargs.setdefault('error_code', 'AUTH_ERROR')
        super().__init__(message, **kwargs)


class TwitterConnectionError(TwitterAPIError):
    """Twitter API connection error"""
    
    def __init__(self, message: str = "Failed to connect to Twitter API", **kwargs):
        kwargs.setdefault('retryable', True)
        kwargs.setdefault('error_code', 'CONNECTION_ERROR')
        super().__init__(message, **kwargs)


class TwitterQuotaExceededError(TwitterAPIError):
    """Twitter API quota exceeded (daily/monthly limits)"""
    
    def __init__(
        self,
        message: str = "Twitter API quota exceeded",
        quota_type: str = "unknown",
        current_usage: int = 0,
        quota_limit: int = 0,
        **kwargs
    ):
        kwargs.setdefault('error_code', 'QUOTA_EXCEEDED')
        super().__init__(message, **kwargs)
        self.quota_type = quota_type
        self.current_usage = current_usage
        self.quota_limit = quota_limit
        
    def to_dict(self):
        result = super().to_dict()
        result.update({
            'quota_type': self.quota_type,
            'current_usage': self.current_usage,
            'quota_limit': self.quota_limit
        })
        return result
