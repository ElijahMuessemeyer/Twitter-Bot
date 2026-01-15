# =============================================================================
# BASE EXCEPTIONS
# =============================================================================
# Foundation exception classes for the Twitter bot error hierarchy

from typing import Optional, Dict, Any
import time


class TwitterBotError(Exception):
    """Base exception for all Twitter bot errors"""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        retryable: bool = False
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.retryable = retryable
        self.timestamp = time.time()
        
    def __str__(self) -> str:
        parts = [self.message]
        if self.error_code:
            parts.append(f"[{self.error_code}]")
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"({context_str})")
        return " ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging"""
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'error_code': self.error_code,
            'context': self.context,
            'retryable': self.retryable,
            'timestamp': self.timestamp
        }


class APIError(TwitterBotError):
    """Base class for all API-related errors"""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.status_code = status_code
        self.response_body = response_body
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            'status_code': self.status_code,
            'response_body': self.response_body
        })
        return result


class NetworkError(TwitterBotError):
    """Network connectivity and timeout errors"""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('retryable', True)
        super().__init__(message, **kwargs)


class ValidationError(TwitterBotError):
    """Data validation and format errors"""
    
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.field = field
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result['field'] = self.field
        return result


class ConfigurationError(TwitterBotError):
    """Configuration and setup errors"""
    
    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.config_key = config_key
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result['config_key'] = self.config_key
        return result
