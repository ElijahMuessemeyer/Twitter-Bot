# =============================================================================
# TRANSLATION-SPECIFIC EXCEPTIONS
# =============================================================================
# Error handling for translation operations

from .base_exceptions import TwitterBotError


class TranslationError(TwitterBotError):
    """General translation error"""
    
    def __init__(
        self,
        message: str,
        tweet_id: str = None,
        target_language: str = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.tweet_id = tweet_id
        self.target_language = target_language
        
    def to_dict(self):
        result = super().to_dict()
        result.update({
            'tweet_id': self.tweet_id,
            'target_language': self.target_language
        })
        return result


class TranslationTimeoutError(TranslationError):
    """Translation operation timed out"""
    
    def __init__(
        self,
        message: str = "Translation operation timed out",
        timeout_duration: float = None,
        **kwargs
    ):
        kwargs.setdefault('retryable', True)
        kwargs.setdefault('error_code', 'TRANSLATION_TIMEOUT')
        super().__init__(message, **kwargs)
        self.timeout_duration = timeout_duration
        
    def to_dict(self):
        result = super().to_dict()
        result['timeout_duration'] = self.timeout_duration
        return result


class TranslationValidationError(TranslationError):
    """Translation result validation failed"""
    
    def __init__(
        self,
        message: str = "Translation validation failed",
        validation_type: str = None,
        **kwargs
    ):
        kwargs.setdefault('error_code', 'VALIDATION_ERROR')
        super().__init__(message, **kwargs)
        self.validation_type = validation_type
        
    def to_dict(self):
        result = super().to_dict()
        result['validation_type'] = self.validation_type
        return result


class TranslationCacheError(TranslationError):
    """Translation cache operation error"""
    
    def __init__(
        self,
        message: str = "Translation cache error",
        operation: str = None,
        **kwargs
    ):
        kwargs.setdefault('error_code', 'CACHE_ERROR')
        super().__init__(message, **kwargs)
        self.operation = operation
        
    def to_dict(self):
        result = super().to_dict()
        result['operation'] = self.operation
        return result
