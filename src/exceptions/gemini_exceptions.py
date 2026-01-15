# =============================================================================
# GEMINI-SPECIFIC EXCEPTIONS
# =============================================================================
# Error handling for Google Gemini API interactions

from .base_exceptions import APIError


class GeminiAPIError(APIError):
    """General Gemini API error"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, **kwargs)


class GeminiQuotaError(GeminiAPIError):
    """Gemini API quota exceeded"""
    
    def __init__(
        self,
        message: str = "Gemini API quota exceeded",
        quota_type: str = "unknown",
        **kwargs
    ):
        kwargs.setdefault('error_code', 'QUOTA_EXCEEDED')
        super().__init__(message, **kwargs)
        self.quota_type = quota_type
        
    def to_dict(self):
        result = super().to_dict()
        result['quota_type'] = self.quota_type
        return result


class GeminiUnavailableError(GeminiAPIError):
    """Gemini API service unavailable"""
    
    def __init__(self, message: str = "Gemini API service unavailable", **kwargs):
        kwargs.setdefault('retryable', True)
        kwargs.setdefault('error_code', 'SERVICE_UNAVAILABLE')
        super().__init__(message, **kwargs)


class GeminiRateLimitError(GeminiAPIError):
    """Gemini API rate limit exceeded"""
    
    def __init__(
        self,
        message: str = "Gemini API rate limit exceeded",
        reset_time: int = None,
        **kwargs
    ):
        kwargs.setdefault('retryable', True)
        kwargs.setdefault('error_code', 'RATE_LIMIT')
        super().__init__(message, **kwargs)
        self.reset_time = reset_time
        
    def to_dict(self):
        result = super().to_dict()
        result['reset_time'] = self.reset_time
        return result


class GeminiAuthError(GeminiAPIError):
    """Gemini API authentication error"""
    
    def __init__(self, message: str = "Gemini API authentication failed", **kwargs):
        kwargs.setdefault('error_code', 'AUTH_ERROR')
        super().__init__(message, **kwargs)
