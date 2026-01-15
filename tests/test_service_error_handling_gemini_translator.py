# =============================================================================
# GEMINI TRANSLATOR SERVICE ERROR HANDLING TESTS
# =============================================================================

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import google.generativeai as genai

from src.services.gemini_translator import GeminiTranslator, gemini_translator
from src.models.tweet import Tweet, Translation
from src.exceptions import (
    GeminiAPIError,
    GeminiQuotaError,
    GeminiUnavailableError,
    GeminiRateLimitError,
    GeminiAuthError,
    TranslationError,
    TranslationTimeoutError,
    TranslationValidationError,
    TranslationCacheError,
    NetworkError,
    ConfigurationError
)
from src.utils.circuit_breaker import CircuitState, CircuitBreakerOpenError


class TestGeminiTranslatorInitialization:
    """Test Gemini Translator initialization and configuration"""
    
    @patch('src.services.gemini_translator.settings')
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_initialization_success(self, mock_model, mock_configure, mock_settings):
        """Test successful initialization with valid API key"""
        mock_settings.GOOGLE_API_KEY = "valid_api_key"
        mock_settings.GEMINI_MODEL = "gemini-pro"
        
        translator = GeminiTranslator()
        
        assert translator.client_initialized is True
        mock_configure.assert_called_once_with(api_key="valid_api_key")
        mock_model.assert_called_once_with("gemini-pro")
    
    @patch('src.services.gemini_translator.settings')
    def test_initialization_no_api_key(self, mock_settings):
        """Test initialization without API key"""
        mock_settings.GOOGLE_API_KEY = None
        
        translator = GeminiTranslator()
        
        assert translator.client_initialized is False
        assert translator.model is None
    
    @patch('src.services.gemini_translator.settings')
    def test_initialization_placeholder_api_key(self, mock_settings):
        """Test initialization with placeholder API key"""
        mock_settings.GOOGLE_API_KEY = "your_api_key_here"
        
        translator = GeminiTranslator()
        
        assert translator.client_initialized is False
        assert translator.model is None
    
    @patch('src.services.gemini_translator.settings')
    @patch('google.generativeai.configure')
    def test_initialization_api_error(self, mock_configure, mock_settings):
        """Test initialization with API configuration error"""
        mock_settings.GOOGLE_API_KEY = "invalid_key"
        mock_settings.GEMINI_MODEL = "gemini-pro"
        mock_configure.side_effect = Exception("API configuration failed")
        
        translator = GeminiTranslator()
        
        assert translator.client_initialized is False
        assert translator.model is None
    
    @patch('src.services.gemini_translator.translation_cache')
    @patch('src.services.gemini_translator.settings')
    def test_initialization_cache_error(self, mock_settings, mock_cache):
        """Test initialization with cache system error"""
        mock_settings.GOOGLE_API_KEY = "valid_key"
        mock_cache.side_effect = Exception("Cache initialization failed")
        
        translator = GeminiTranslator()
        
        assert translator.cache is None


class TestGeminiTranslatorCaching:
    """Test translation caching mechanisms and error handling"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.gemini_translator.settings') as mock_settings:
            mock_settings.GOOGLE_API_KEY = "test_key"
            mock_settings.GEMINI_MODEL = "gemini-pro"
            
            with patch('google.generativeai.configure'), \
                 patch('google.generativeai.GenerativeModel') as mock_model:
                
                self.translator = GeminiTranslator()
                self.translator.model = mock_model.return_value
                self.translator.client_initialized = True
    
    def test_cache_hit_successful(self):
        """Test successful cache hit"""
        # Create test tweet
        tweet = Tweet(
            id="123",
            text="Hello world",
            created_at=datetime.now(),
            author_username="test",
            author_id="456"
        )
        
        # Mock cached translation
        cached_translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="こんにちは世界",
            translation_timestamp=datetime.now(),
            character_count=6,
            status='completed'
        )
        
        with patch.object(self.translator.cache, 'get', return_value=cached_translation), \
             patch.object(self.translator.cache, 'get_cache_info', return_value={'top_entries': []}):
            
            result = self.translator.translate_tweet(tweet, "Japanese")
            
            assert result is not None
            assert result.translated_text == "こんにちは世界"
            assert result.original_tweet == tweet
    
    def test_cache_error_fallback_to_api(self):
        """Test fallback to API when cache fails"""
        tweet = Tweet(
            id="123",
            text="Hello world",
            created_at=datetime.now(),
            author_username="test",
            author_id="456"
        )
        
        # Mock cache error
        with patch.object(self.translator.cache, 'get', side_effect=TranslationCacheError("Cache lookup failed")), \
             patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            # Setup text processor mocks
            mock_processor.extract_preservable_elements.return_value = ("Hello world", {})
            mock_processor.restore_preservable_elements.return_value = "こんにちは世界"
            mock_processor.get_character_count.return_value = 6
            mock_processor.is_within_twitter_limit.return_value = True
            
            # Setup prompt builder mock
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello world"
            
            # Mock API response
            mock_response = Mock()
            mock_response.text = "こんにちは世界"
            self.translator.model.generate_content.return_value = mock_response
            
            result = self.translator.translate_tweet(tweet, "Japanese")
            
            assert result is not None
            assert result.translated_text == "こんにちは世界"
    
    def test_cache_put_error_continues(self):
        """Test that cache put errors don't prevent translation"""
        tweet = Tweet(
            id="123",
            text="Hello world",
            created_at=datetime.now(),
            author_username="test",
            author_id="456"
        )
        
        with patch.object(self.translator.cache, 'get', return_value=None), \
             patch.object(self.translator.cache, 'put', side_effect=TranslationCacheError("Cache store failed")), \
             patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            # Setup mocks
            mock_processor.extract_preservable_elements.return_value = ("Hello world", {})
            mock_processor.restore_preservable_elements.return_value = "こんにちは世界"
            mock_processor.get_character_count.return_value = 6
            mock_processor.is_within_twitter_limit.return_value = True
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello world"
            
            # Mock API response
            mock_response = Mock()
            mock_response.text = "こんにちは世界"
            self.translator.model.generate_content.return_value = mock_response
            
            result = self.translator.translate_tweet(tweet, "Japanese")
            
            # Should succeed despite cache error
            assert result is not None
            assert result.translated_text == "こんにちは世界"


class TestGeminiAPIErrorHandling:
    """Test Gemini API error scenarios"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.gemini_translator.settings') as mock_settings:
            mock_settings.GOOGLE_API_KEY = "test_key"
            mock_settings.GEMINI_MODEL = "gemini-pro"
            
            with patch('google.generativeai.configure'), \
                 patch('google.generativeai.GenerativeModel') as mock_model:
                
                self.translator = GeminiTranslator()
                self.translator.model = mock_model.return_value
                self.translator.client_initialized = True
                
                # Mock cache
                self.translator.cache = Mock()
                self.translator.cache.get.return_value = None
    
    def test_translate_not_initialized(self):
        """Test translation when Gemini is not initialized"""
        self.translator.client_initialized = False
        
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(), 
                     author_username="test", author_id="456")
        
        with pytest.raises(ConfigurationError):
            self.translator.translate_tweet(tweet, "Japanese")
    
    def test_gemini_quota_error(self):
        """Test Gemini API quota exceeded error"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            # Mock quota error
            self.translator.model.generate_content.side_effect = Exception("quota exceeded for billing account")
            
            with pytest.raises(GeminiQuotaError) as exc_info:
                self.translator.translate_tweet(tweet, "Japanese")
            
            assert "quota exceeded" in str(exc_info.value).lower()
    
    def test_gemini_rate_limit_error(self):
        """Test Gemini API rate limit error"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            # Mock rate limit error
            self.translator.model.generate_content.side_effect = Exception("rate limit exceeded")
            
            with pytest.raises(GeminiRateLimitError) as exc_info:
                self.translator.translate_tweet(tweet, "Japanese")
            
            assert "rate limit" in str(exc_info.value).lower()
    
    def test_gemini_auth_error(self):
        """Test Gemini API authentication error"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            # Mock auth error
            self.translator.model.generate_content.side_effect = Exception("invalid api key provided")
            
            with pytest.raises(GeminiAuthError) as exc_info:
                self.translator.translate_tweet(tweet, "Japanese")
            
            assert "authentication error" in str(exc_info.value).lower()
    
    def test_gemini_service_unavailable_error(self):
        """Test Gemini API service unavailable error"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            # Mock service unavailable error
            self.translator.model.generate_content.side_effect = Exception("service unavailable")
            
            with pytest.raises(GeminiUnavailableError) as exc_info:
                self.translator.translate_tweet(tweet, "Japanese")
            
            assert "unavailable" in str(exc_info.value).lower()
    
    def test_gemini_timeout_error(self):
        """Test Gemini API timeout error"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            # Mock timeout error
            self.translator.model.generate_content.side_effect = Exception("timeout occurred")
            
            with pytest.raises(GeminiUnavailableError) as exc_info:
                self.translator.translate_tweet(tweet, "Japanese")
            
            assert "timeout" in str(exc_info.value).lower()
    
    def test_gemini_empty_response_error(self):
        """Test handling empty response from Gemini"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            # Mock empty response
            mock_response = Mock()
            mock_response.text = None
            self.translator.model.generate_content.return_value = mock_response
            
            with pytest.raises(GeminiAPIError) as exc_info:
                self.translator.translate_tweet(tweet, "Japanese")
            
            assert "empty response" in str(exc_info.value).lower()
    
    def test_gemini_no_response_error(self):
        """Test handling no response from Gemini"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            # Mock no response
            self.translator.model.generate_content.return_value = None
            
            with pytest.raises(GeminiAPIError) as exc_info:
                self.translator.translate_tweet(tweet, "Japanese")
            
            assert "empty response" in str(exc_info.value).lower()


class TestTranslationValidation:
    """Test translation validation and character limit handling"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.gemini_translator.settings') as mock_settings:
            mock_settings.GOOGLE_API_KEY = "test_key"
            mock_settings.GEMINI_MODEL = "gemini-pro"
            
            with patch('google.generativeai.configure'), \
                 patch('google.generativeai.GenerativeModel') as mock_model:
                
                self.translator = GeminiTranslator()
                self.translator.model = mock_model.return_value
                self.translator.client_initialized = True
                
                # Mock cache
                self.translator.cache = Mock()
                self.translator.cache.get.return_value = None
    
    def test_translation_exceeds_character_limit(self):
        """Test handling translation that exceeds Twitter character limit"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_processor.restore_preservable_elements.return_value = "Very long translation " * 20
            mock_processor.get_character_count.return_value = 300  # Exceeds limit
            mock_processor.is_within_twitter_limit.return_value = False
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            # Mock API response for initial translation
            mock_response = Mock()
            mock_response.text = "Very long translation " * 20
            
            # Mock API response for shortening
            mock_response_short = Mock()
            mock_response_short.text = "Short translation"
            
            self.translator.model.generate_content.side_effect = [mock_response, mock_response_short]
            
            with patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
                mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
                mock_prompt_builder.build_shortening_prompt.return_value = "Shorten: Very long..."
                
                result = self.translator.translate_tweet(tweet, "Japanese")
                
                assert result is not None
                # Should call shortening logic
                assert self.translator.model.generate_content.call_count == 2
    
    def test_shortening_api_error_fallback(self):
        """Test fallback when shortening API call fails"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        original_translation = "Very long translation " * 20
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_processor.restore_preservable_elements.return_value = original_translation
            mock_processor.get_character_count.return_value = 300
            mock_processor.is_within_twitter_limit.return_value = False
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            mock_prompt_builder.build_shortening_prompt.return_value = "Shorten: Very long..."
            
            # Mock API response for initial translation
            mock_response = Mock()
            mock_response.text = original_translation
            
            # First call succeeds, second call (shortening) fails
            self.translator.model.generate_content.side_effect = [
                mock_response,
                Exception("API error during shortening")
            ]
            
            result = self.translator.translate_tweet(tweet, "Japanese")
            
            assert result is not None
            # Should return original translation even if shortening fails
            assert result.translated_text == original_translation
    
    def test_shortening_empty_response_fallback(self):
        """Test fallback when shortening returns empty response"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        original_translation = "Very long translation " * 20
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_processor.restore_preservable_elements.return_value = original_translation
            mock_processor.get_character_count.return_value = 300
            mock_processor.is_within_twitter_limit.return_value = False
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            mock_prompt_builder.build_shortening_prompt.return_value = "Shorten: Very long..."
            
            # Mock API responses
            mock_response = Mock()
            mock_response.text = original_translation
            
            mock_response_short = Mock()
            mock_response_short.text = None  # Empty response
            
            self.translator.model.generate_content.side_effect = [mock_response, mock_response_short]
            
            result = self.translator.translate_tweet(tweet, "Japanese")
            
            assert result is not None
            # Should return original translation when shortening returns empty
            assert result.translated_text == original_translation


class TestGeminiCircuitBreaker:
    """Test circuit breaker integration with Gemini Translator"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.gemini_translator.settings') as mock_settings:
            mock_settings.GOOGLE_API_KEY = "test_key"
            mock_settings.GEMINI_MODEL = "gemini-pro"
            
            with patch('google.generativeai.configure'), \
                 patch('google.generativeai.GenerativeModel') as mock_model:
                
                self.translator = GeminiTranslator()
                self.translator.model = mock_model.return_value
                self.translator.client_initialized = True
                
                # Mock cache
                self.translator.cache = Mock()
                self.translator.cache.get.return_value = None
    
    @patch('src.services.gemini_translator.circuit_breaker_protection')
    def test_circuit_breaker_protection_applied(self, mock_cb_decorator):
        """Test that circuit breaker decorator is applied"""
        mock_cb_decorator.return_value = lambda func: func
        
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_processor.restore_preservable_elements.return_value = "こんにちは"
            mock_processor.get_character_count.return_value = 5
            mock_processor.is_within_twitter_limit.return_value = True
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            mock_response = Mock()
            mock_response.text = "こんにちは"
            self.translator.model.generate_content.return_value = mock_response
            
            self.translator.translate_tweet(tweet, "Japanese")
        
        # Verify circuit breaker was configured for "gemini_api"
        mock_cb_decorator.assert_called()
    
    def test_circuit_breaker_opens_on_repeated_failures(self):
        """Test circuit breaker opens after repeated Gemini API failures"""
        from src.utils.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig
        
        cb_manager = CircuitBreakerManager()
        test_config = CircuitBreakerConfig(
            failure_threshold=2,
            min_requests=1,
            timeout=0.1
        )
        cb = cb_manager.get_circuit_breaker("gemini_api_test", test_config)
        
        # Simulate failures
        for _ in range(3):
            try:
                cb.call(lambda: (_ for _ in ()).throw(GeminiUnavailableError("Service down")))
            except GeminiUnavailableError:
                pass
        
        # Circuit should now be open
        cb._update_state()
        assert cb.state == CircuitState.OPEN
        
        # Next call should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should be blocked")


class TestGeminiRetryMechanism:
    """Test retry mechanism integration with Gemini Translator"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.gemini_translator.settings') as mock_settings:
            mock_settings.GOOGLE_API_KEY = "test_key"
            mock_settings.GEMINI_MODEL = "gemini-pro"
            
            with patch('google.generativeai.configure'), \
                 patch('google.generativeai.GenerativeModel') as mock_model:
                
                self.translator = GeminiTranslator()
                self.translator.model = mock_model.return_value
                self.translator.client_initialized = True
                
                # Mock cache
                self.translator.cache = Mock()
                self.translator.cache.get.return_value = None
    
    def test_retry_on_service_unavailable(self):
        """Test retry mechanism on service unavailable errors"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        call_count = 0
        
        def failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise GeminiUnavailableError("Service temporarily unavailable")
            
            mock_response = Mock()
            mock_response.text = "こんにちは"
            return mock_response
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_processor.restore_preservable_elements.return_value = "こんにちは"
            mock_processor.get_character_count.return_value = 5
            mock_processor.is_within_twitter_limit.return_value = True
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            self.translator.model.generate_content = failing_then_success
            
            result = self.translator.translate_tweet(tweet, "Japanese")
            
            assert result is not None
            assert call_count == 3  # Should have retried
    
    def test_retry_on_network_error(self):
        """Test retry mechanism on network errors"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        call_count = 0
        
        def network_error_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise NetworkError("Network connection failed")
            
            mock_response = Mock()
            mock_response.text = "こんにちは"
            return mock_response
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_processor.restore_preservable_elements.return_value = "こんにちは"
            mock_processor.get_character_count.return_value = 5
            mock_processor.is_within_twitter_limit.return_value = True
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            self.translator.model.generate_content = network_error_then_success
            
            result = self.translator.translate_tweet(tweet, "Japanese")
            
            assert result is not None
            assert call_count == 2  # Should have retried once
    
    def test_no_retry_on_quota_error(self):
        """Test that quota errors are not retried"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        call_count = 0
        
        def always_quota_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise GeminiQuotaError("Quota exceeded")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            self.translator.model.generate_content = always_quota_error
            
            with pytest.raises(GeminiQuotaError):
                self.translator.translate_tweet(tweet, "Japanese")
            
            # Should only be called once (no retries for quota errors)
            assert call_count == 1
    
    def test_no_retry_on_auth_error(self):
        """Test that authentication errors are not retried"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        call_count = 0
        
        def always_auth_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise GeminiAuthError("Invalid API key")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            self.translator.model.generate_content = always_auth_error
            
            with pytest.raises(GeminiAuthError):
                self.translator.translate_tweet(tweet, "Japanese")
            
            # Should only be called once (no retries for auth errors)
            assert call_count == 1


class TestGeminiErrorRecovery:
    """Test error recovery mechanisms"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.gemini_translator.settings') as mock_settings:
            mock_settings.GOOGLE_API_KEY = "test_key"
            mock_settings.GEMINI_MODEL = "gemini-pro"
            
            with patch('google.generativeai.configure'), \
                 patch('google.generativeai.GenerativeModel') as mock_model:
                
                self.translator = GeminiTranslator()
                self.translator.model = mock_model.return_value
                self.translator.client_initialized = True
                
                # Mock cache
                self.translator.cache = Mock()
                self.translator.cache.get.return_value = None
    
    def test_error_recovery_success_returns_none(self):
        """Test successful error recovery returns None gracefully"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder, \
             patch('src.services.gemini_translator.recover_from_error') as mock_recovery:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            # Mock unknown error
            self.translator.model.generate_content.side_effect = Exception("Unknown error")
            
            # Mock successful recovery
            mock_recovery.return_value = {'success': True}
            
            result = self.translator.translate_tweet(tweet, "Japanese")
            
            assert result is None  # Should return None as fallback
            mock_recovery.assert_called_once()
    
    def test_error_recovery_failure_raises_translation_error(self):
        """Test failed error recovery raises TranslationError"""
        tweet = Tweet(id="123", text="Hello", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        with patch('src.services.gemini_translator.text_processor') as mock_processor, \
             patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder, \
             patch('src.services.gemini_translator.recover_from_error') as mock_recovery:
            
            mock_processor.extract_preservable_elements.return_value = ("Hello", {})
            mock_prompt_builder.build_translation_prompt.return_value = "Translate: Hello"
            
            # Mock unknown error
            self.translator.model.generate_content.side_effect = Exception("Unknown error")
            
            # Mock failed recovery
            mock_recovery.return_value = {'success': False}
            
            with pytest.raises(TranslationError) as exc_info:
                self.translator.translate_tweet(tweet, "Japanese")
            
            error = exc_info.value
            assert error.tweet_id == "123"
            assert error.target_language == "Japanese"


class TestGeminiUtilityMethods:
    """Test utility methods like cache metrics and clearing"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.gemini_translator.settings') as mock_settings:
            mock_settings.GOOGLE_API_KEY = "test_key"
            mock_settings.GEMINI_MODEL = "gemini-pro"
            
            with patch('google.generativeai.configure'), \
                 patch('google.generativeai.GenerativeModel') as mock_model:
                
                self.translator = GeminiTranslator()
                self.translator.model = mock_model.return_value
                self.translator.client_initialized = True
    
    def test_get_cache_metrics(self):
        """Test getting cache metrics"""
        expected_metrics = {
            'hit_rate': 0.75,
            'total_requests': 100,
            'cache_size': 50
        }
        
        self.translator.cache.get_cache_info.return_value = expected_metrics
        
        metrics = self.translator.get_cache_metrics()
        
        assert metrics == expected_metrics
        self.translator.cache.get_cache_info.assert_called_once()
    
    def test_clear_cache(self):
        """Test clearing translation cache"""
        self.translator.clear_cache()
        
        self.translator.cache.clear.assert_called_once()
    
    def test_preload_common_translations(self):
        """Test preloading common translation patterns"""
        patterns = {
            "Good morning!": {
                "Japanese": "おはようございます！",
                "Spanish": "¡Buenos días!"
            }
        }
        
        self.translator.preload_common_translations(patterns)
        
        self.translator.cache.preload_common_translations.assert_called_once_with(patterns)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
