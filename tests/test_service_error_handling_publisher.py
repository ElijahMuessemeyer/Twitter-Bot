# =============================================================================
# TWITTER PUBLISHER SERVICE ERROR HANDLING TESTS
# =============================================================================

import pytest
import tweepy
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.services.publisher import TwitterPublisher, twitter_publisher
from src.models.tweet import Tweet, Translation
from src.exceptions import (
    TwitterAPIError,
    TwitterRateLimitError,
    TwitterAuthError,
    TwitterConnectionError,
    TwitterQuotaExceededError,
    NetworkError,
    ConfigurationError
)
from src.utils.circuit_breaker import CircuitState, CircuitBreakerOpenError


class TestTwitterPublisherInitialization:
    """Test Twitter Publisher initialization and client setup"""
    
    @patch('src.services.publisher.settings')
    def test_initialization_no_language_configs(self, mock_settings):
        """Test initialization with no target languages configured"""
        mock_settings.TARGET_LANGUAGES = []
        mock_settings.get_twitter_creds_for_language.return_value = None
        
        publisher = TwitterPublisher()
        
        assert len(publisher.language_clients) == 0
    
    @patch('src.services.publisher.settings')
    def test_initialization_with_valid_credentials(self, mock_settings):
        """Test initialization with valid language credentials"""
        mock_settings.TARGET_LANGUAGES = [
            {'code': 'ja', 'name': 'Japanese'},
            {'code': 'es', 'name': 'Spanish'}
        ]
        
        # Mock credentials for each language
        def mock_get_creds(lang_code):
            return {
                'consumer_key': f'{lang_code}_consumer_key',
                'consumer_secret': f'{lang_code}_consumer_secret',
                'access_token': f'{lang_code}_access_token',
                'access_token_secret': f'{lang_code}_access_token_secret'
            }
        
        mock_settings.get_twitter_creds_for_language.side_effect = mock_get_creds
        
        with patch('tweepy.OAuth1UserHandler'), \
             patch('tweepy.API') as mock_api_class:
            
            # Mock successful API verification
            mock_api_instance = Mock()
            mock_api_instance.verify_credentials.return_value = Mock()
            mock_api_class.return_value = mock_api_instance
            
            publisher = TwitterPublisher()
            
            assert len(publisher.language_clients) == 2
            assert 'ja' in publisher.language_clients
            assert 'es' in publisher.language_clients
    
    @patch('src.services.publisher.settings')
    def test_initialization_missing_credentials(self, mock_settings):
        """Test initialization with missing credentials for a language"""
        mock_settings.TARGET_LANGUAGES = [
            {'code': 'ja', 'name': 'Japanese'}
        ]
        mock_settings.get_twitter_creds_for_language.return_value = None
        
        publisher = TwitterPublisher()
        
        assert len(publisher.language_clients) == 0
    
    @patch('src.services.publisher.settings')
    def test_initialization_invalid_credentials(self, mock_settings):
        """Test initialization with placeholder credentials"""
        mock_settings.TARGET_LANGUAGES = [
            {'code': 'ja', 'name': 'Japanese'}
        ]
        mock_settings.get_twitter_creds_for_language.return_value = {
            'consumer_key': 'your_consumer_key',
            'consumer_secret': 'your_consumer_secret',
            'access_token': 'your_access_token',
            'access_token_secret': 'your_access_token_secret'
        }
        
        publisher = TwitterPublisher()
        
        assert len(publisher.language_clients) == 0
    
    @patch('src.services.publisher.settings')
    def test_initialization_auth_failure(self, mock_settings):
        """Test initialization with credentials that fail authentication"""
        mock_settings.TARGET_LANGUAGES = [
            {'code': 'ja', 'name': 'Japanese'}
        ]
        mock_settings.get_twitter_creds_for_language.return_value = {
            'consumer_key': 'invalid_key',
            'consumer_secret': 'invalid_secret',
            'access_token': 'invalid_token',
            'access_token_secret': 'invalid_token_secret'
        }
        
        with patch('tweepy.OAuth1UserHandler'), \
             patch('tweepy.API') as mock_api_class:
            
            # Mock authentication failure
            mock_api_instance = Mock()
            mock_api_instance.verify_credentials.side_effect = tweepy.Unauthorized("Invalid credentials")
            mock_api_class.return_value = mock_api_instance
            
            publisher = TwitterPublisher()
            
            assert len(publisher.language_clients) == 0
    
    @patch('src.services.publisher.settings')
    def test_initialization_rate_limit_during_verification(self, mock_settings):
        """Test initialization with rate limit during credential verification"""
        mock_settings.TARGET_LANGUAGES = [
            {'code': 'ja', 'name': 'Japanese'}
        ]
        mock_settings.get_twitter_creds_for_language.return_value = {
            'consumer_key': 'valid_key',
            'consumer_secret': 'valid_secret',
            'access_token': 'valid_token',
            'access_token_secret': 'valid_token_secret'
        }
        
        with patch('tweepy.OAuth1UserHandler'), \
             patch('tweepy.API') as mock_api_class:
            
            # Mock rate limit during verification
            mock_api_instance = Mock()
            mock_api_instance.verify_credentials.side_effect = tweepy.TooManyRequests("Rate limit exceeded")
            mock_api_class.return_value = mock_api_instance
            
            publisher = TwitterPublisher()
            
            assert len(publisher.language_clients) == 0
    
    @patch('src.services.publisher.settings')
    def test_initialization_connection_error_during_verification(self, mock_settings):
        """Test initialization with connection error during verification"""
        mock_settings.TARGET_LANGUAGES = [
            {'code': 'ja', 'name': 'Japanese'}
        ]
        mock_settings.get_twitter_creds_for_language.return_value = {
            'consumer_key': 'valid_key',
            'consumer_secret': 'valid_secret',
            'access_token': 'valid_token',
            'access_token_secret': 'valid_token_secret'
        }
        
        with patch('tweepy.OAuth1UserHandler'), \
             patch('tweepy.API') as mock_api_class:
            
            # Mock connection error during verification
            mock_api_instance = Mock()
            mock_api_instance.verify_credentials.side_effect = ConnectionError("Network error")
            mock_api_class.return_value = mock_api_instance
            
            publisher = TwitterPublisher()
            
            assert len(publisher.language_clients) == 0


class TestTwitterPublisherQuotaManagement:
    """Test posting quota management"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.publisher.settings') as mock_settings:
            mock_settings.TARGET_LANGUAGES = []
            self.publisher = TwitterPublisher()
    
    @patch('src.services.publisher.twitter_monitor')
    def test_can_post_within_quota(self, mock_monitor):
        """Test posting permission when within quota"""
        mock_monitor.can_post_tweet.return_value = True
        
        assert self.publisher.can_post() is True
    
    @patch('src.services.publisher.twitter_monitor')
    def test_can_post_quota_exceeded(self, mock_monitor):
        """Test posting blocked when quota exceeded"""
        mock_monitor.can_post_tweet.side_effect = TwitterQuotaExceededError("Monthly limit reached")
        
        assert self.publisher.can_post() is False


class TestTwitterPublisherPostTranslation:
    """Test posting individual translations with error scenarios"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.publisher.settings') as mock_settings:
            mock_settings.TARGET_LANGUAGES = [
                {'code': 'ja', 'name': 'Japanese'}
            ]
            mock_settings.get_twitter_creds_for_language.return_value = {
                'consumer_key': 'test_key',
                'consumer_secret': 'test_secret',
                'access_token': 'test_token',
                'access_token_secret': 'test_token_secret'
            }
            
            with patch('tweepy.OAuth1UserHandler'), \
                 patch('tweepy.API') as mock_api_class:
                
                # Mock successful API verification
                mock_api_instance = Mock()
                mock_api_instance.verify_credentials.return_value = Mock()
                mock_api_class.return_value = mock_api_instance
                
                self.publisher = TwitterPublisher()
                self.mock_api = mock_api_instance
    
    def test_post_translation_quota_exceeded(self):
        """Test posting when quota is exceeded"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        with patch.object(self.publisher, 'can_post', return_value=False):
            with pytest.raises(TwitterQuotaExceededError):
                self.publisher.post_translation(translation)
    
    def test_post_translation_language_not_configured(self):
        """Test posting to unconfigured language"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="French",  # Not configured
            translated_text="Texte traduit",
            translation_timestamp=datetime.now(),
            character_count=13,
            status='pending'
        )
        
        with patch.object(self.publisher, 'can_post', return_value=True):
            with pytest.raises(ConfigurationError) as exc_info:
                self.publisher.post_translation(translation)
            
            assert "no twitter client available" in str(exc_info.value).lower()
    
    def test_post_translation_successful(self):
        """Test successful translation posting"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        # Mock successful posting
        mock_status = Mock()
        mock_status.id = 987654321
        self.mock_api.update_status.return_value = mock_status
        
        with patch.object(self.publisher, 'can_post', return_value=True), \
             patch('src.services.publisher.twitter_monitor') as mock_monitor:
            
            result = self.publisher.post_translation(translation)
            
            assert result is True
            assert translation.status == 'posted'
            assert translation.post_id == "987654321"
            
            # Verify API call
            self.mock_api.update_status.assert_called_once_with("翻訳されたテキスト")
            
            # Verify usage tracking
            assert mock_monitor.monthly_posts == 1
            mock_monitor.save_api_usage.assert_called_once()
    
    def test_post_translation_language_code_mapping(self):
        """Test language code mapping for full language names"""
        # Add German client for testing
        self.publisher.language_clients['de'] = self.mock_api
        
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="German",  # Full name should map to 'de'
            translated_text="Übersetzter Text",
            translation_timestamp=datetime.now(),
            character_count=16,
            status='pending'
        )
        
        mock_status = Mock()
        mock_status.id = 987654321
        self.mock_api.update_status.return_value = mock_status
        
        with patch.object(self.publisher, 'can_post', return_value=True), \
             patch('src.services.publisher.twitter_monitor'):
            
            result = self.publisher.post_translation(translation)
            
            assert result is True
            self.mock_api.update_status.assert_called_once_with("Übersetzter Text")
    
    def test_post_translation_unauthorized_error(self):
        """Test handling Twitter authentication errors during posting"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        self.mock_api.update_status.side_effect = tweepy.Unauthorized("Invalid token")
        
        with patch.object(self.publisher, 'can_post', return_value=True):
            with pytest.raises(TwitterAuthError) as exc_info:
                self.publisher.post_translation(translation)
            
            assert translation.status == 'failed'
            assert "authentication failed" in str(exc_info.value).lower()
    
    def test_post_translation_rate_limit_error(self):
        """Test handling Twitter rate limit errors during posting"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        # Create mock response with rate limit headers
        mock_response = Mock()
        mock_response.headers = {'x-rate-limit-reset': '1234567890'}
        rate_limit_error = tweepy.TooManyRequests(response=mock_response)
        
        self.mock_api.update_status.side_effect = rate_limit_error
        
        with patch.object(self.publisher, 'can_post', return_value=True):
            with pytest.raises(TwitterRateLimitError) as exc_info:
                self.publisher.post_translation(translation)
            
            error = exc_info.value
            assert error.reset_time == 1234567890
            assert translation.status == 'failed'
    
    def test_post_translation_forbidden_error(self):
        """Test handling Twitter forbidden errors during posting"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        self.mock_api.update_status.side_effect = tweepy.Forbidden("Access forbidden")
        
        with patch.object(self.publisher, 'can_post', return_value=True):
            with pytest.raises(TwitterAuthError) as exc_info:
                self.publisher.post_translation(translation)
            
            assert "forbidden" in str(exc_info.value).lower()
            assert translation.status == 'failed'
    
    def test_post_translation_bad_request_error(self):
        """Test handling Twitter bad request errors during posting"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        self.mock_api.update_status.side_effect = tweepy.BadRequest("Invalid parameters")
        
        with patch.object(self.publisher, 'can_post', return_value=True):
            with pytest.raises(TwitterAPIError) as exc_info:
                self.publisher.post_translation(translation)
            
            assert "twitter api error" in str(exc_info.value).lower()
            assert translation.status == 'failed'
    
    def test_post_translation_network_error(self):
        """Test handling network errors during posting"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        self.mock_api.update_status.side_effect = ConnectionError("Network unreachable")
        
        with patch.object(self.publisher, 'can_post', return_value=True):
            with pytest.raises(NetworkError) as exc_info:
                self.publisher.post_translation(translation)
            
            assert "network error" in str(exc_info.value).lower()
            assert translation.status == 'failed'
    
    def test_post_translation_timeout_error(self):
        """Test handling timeout errors during posting"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        self.mock_api.update_status.side_effect = TimeoutError("Request timeout")
        
        with patch.object(self.publisher, 'can_post', return_value=True):
            with pytest.raises(NetworkError) as exc_info:
                self.publisher.post_translation(translation)
            
            assert "network error" in str(exc_info.value).lower()
            assert translation.status == 'failed'
    
    def test_post_translation_error_recovery_success(self):
        """Test successful error recovery returns False gracefully"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        self.mock_api.update_status.side_effect = Exception("Unknown error")
        
        with patch.object(self.publisher, 'can_post', return_value=True), \
             patch('src.services.publisher.recover_from_error') as mock_recovery:
            
            mock_recovery.return_value = {'success': True}
            
            result = self.publisher.post_translation(translation)
            
            assert result is False  # Should return False as fallback
            assert translation.status == 'failed'
            mock_recovery.assert_called_once()
    
    def test_post_translation_error_recovery_failure(self):
        """Test failed error recovery raises TwitterAPIError"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        self.mock_api.update_status.side_effect = Exception("Unknown error")
        
        with patch.object(self.publisher, 'can_post', return_value=True), \
             patch('src.services.publisher.recover_from_error') as mock_recovery:
            
            mock_recovery.return_value = {'success': False}
            
            with pytest.raises(TwitterAPIError):
                self.publisher.post_translation(translation)
            
            assert translation.status == 'failed'


class TestTwitterPublisherBatchPosting:
    """Test posting multiple translations"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.publisher.settings') as mock_settings:
            mock_settings.TARGET_LANGUAGES = [
                {'code': 'ja', 'name': 'Japanese'},
                {'code': 'es', 'name': 'Spanish'}
            ]
            
            def mock_get_creds(lang_code):
                return {
                    'consumer_key': f'{lang_code}_key',
                    'consumer_secret': f'{lang_code}_secret',
                    'access_token': f'{lang_code}_token',
                    'access_token_secret': f'{lang_code}_token_secret'
                }
            
            mock_settings.get_twitter_creds_for_language.side_effect = mock_get_creds
            
            with patch('tweepy.OAuth1UserHandler'), \
                 patch('tweepy.API') as mock_api_class:
                
                # Create separate mock instances for each language
                self.mock_api_ja = Mock()
                self.mock_api_ja.verify_credentials.return_value = Mock()
                self.mock_api_es = Mock()
                self.mock_api_es.verify_credentials.return_value = Mock()
                
                mock_api_class.side_effect = [self.mock_api_ja, self.mock_api_es]
                
                self.publisher = TwitterPublisher()
    
    def test_post_multiple_translations_all_success(self):
        """Test posting multiple translations successfully"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        translations = [
            Translation(
                original_tweet=tweet,
                target_language="Japanese",
                translated_text="翻訳されたテキスト",
                translation_timestamp=datetime.now(),
                character_count=10,
                status='pending'
            ),
            Translation(
                original_tweet=tweet,
                target_language="Spanish",
                translated_text="Texto traducido",
                translation_timestamp=datetime.now(),
                character_count=15,
                status='pending'
            )
        ]
        
        # Mock successful posting for both
        mock_status_ja = Mock()
        mock_status_ja.id = 111
        mock_status_es = Mock()
        mock_status_es.id = 222
        
        self.mock_api_ja.update_status.return_value = mock_status_ja
        self.mock_api_es.update_status.return_value = mock_status_es
        
        with patch.object(self.publisher, 'can_post', return_value=True), \
             patch('src.services.publisher.twitter_monitor'):
            
            results = self.publisher.post_multiple_translations(translations)
            
            assert results['Japanese'] is True
            assert results['Spanish'] is True
    
    def test_post_multiple_translations_partial_failure(self):
        """Test posting multiple translations with some failures"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        translations = [
            Translation(
                original_tweet=tweet,
                target_language="Japanese",
                translated_text="翻訳されたテキスト",
                translation_timestamp=datetime.now(),
                character_count=10,
                status='pending'
            ),
            Translation(
                original_tweet=tweet,
                target_language="Spanish",
                translated_text="Texto traducido",
                translation_timestamp=datetime.now(),
                character_count=15,
                status='pending'
            )
        ]
        
        # Mock success for Japanese, failure for Spanish
        mock_status_ja = Mock()
        mock_status_ja.id = 111
        self.mock_api_ja.update_status.return_value = mock_status_ja
        self.mock_api_es.update_status.side_effect = tweepy.Unauthorized("Auth failed")
        
        with patch.object(self.publisher, 'can_post', return_value=True), \
             patch('src.services.publisher.twitter_monitor'):
            
            results = self.publisher.post_multiple_translations(translations)
            
            assert results['Japanese'] is True
            assert results['Spanish'] is False
    
    def test_post_multiple_translations_quota_exceeded_stops_batch(self):
        """Test that quota exceeded error stops batch processing"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        
        translations = [
            Translation(
                original_tweet=tweet,
                target_language="Japanese",
                translated_text="翻訳されたテキスト",
                translation_timestamp=datetime.now(),
                character_count=10,
                status='pending'
            ),
            Translation(
                original_tweet=tweet,
                target_language="Spanish",
                translated_text="Texto traducido",
                translation_timestamp=datetime.now(),
                character_count=15,
                status='pending'
            )
        ]
        
        # Mock quota exceeded on first translation
        with patch.object(self.publisher, 'post_translation') as mock_post:
            mock_post.side_effect = [
                TwitterQuotaExceededError("Monthly limit reached"),
                None  # Should not be called
            ]
            
            results = self.publisher.post_multiple_translations(translations)
            
            assert results['Japanese'] is False
            assert 'Spanish' not in results  # Should not process second translation
            
            # Verify only first translation was attempted
            assert mock_post.call_count == 1


class TestTwitterPublisherCircuitBreaker:
    """Test circuit breaker integration with Twitter Publisher"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.publisher.settings') as mock_settings:
            mock_settings.TARGET_LANGUAGES = [
                {'code': 'ja', 'name': 'Japanese'}
            ]
            mock_settings.get_twitter_creds_for_language.return_value = {
                'consumer_key': 'test_key',
                'consumer_secret': 'test_secret',
                'access_token': 'test_token',
                'access_token_secret': 'test_token_secret'
            }
            
            with patch('tweepy.OAuth1UserHandler'), \
                 patch('tweepy.API') as mock_api_class:
                
                mock_api_instance = Mock()
                mock_api_instance.verify_credentials.return_value = Mock()
                mock_api_class.return_value = mock_api_instance
                
                self.publisher = TwitterPublisher()
                self.mock_api = mock_api_instance
    
    @patch('src.services.publisher.circuit_breaker_protection')
    def test_circuit_breaker_protection_applied(self, mock_cb_decorator):
        """Test that circuit breaker decorator is applied"""
        mock_cb_decorator.return_value = lambda func: func
        
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        mock_status = Mock()
        mock_status.id = 987654321
        self.mock_api.update_status.return_value = mock_status
        
        with patch.object(self.publisher, 'can_post', return_value=True), \
             patch('src.services.publisher.twitter_monitor'):
            
            self.publisher.post_translation(translation)
        
        # Verify circuit breaker was configured for "twitter_publisher"
        mock_cb_decorator.assert_called()
    
    def test_circuit_breaker_opens_on_repeated_failures(self):
        """Test circuit breaker opens after repeated posting failures"""
        from src.utils.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig
        
        cb_manager = CircuitBreakerManager()
        test_config = CircuitBreakerConfig(
            failure_threshold=2,
            min_requests=1,
            timeout=0.1
        )
        cb = cb_manager.get_circuit_breaker("twitter_publisher_test", test_config)
        
        # Simulate failures
        for _ in range(3):
            try:
                cb.call(lambda: (_ for _ in ()).throw(TwitterConnectionError("Connection failed")))
            except TwitterConnectionError:
                pass
        
        # Circuit should now be open
        cb._update_state()
        assert cb.state == CircuitState.OPEN
        
        # Next call should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should be blocked")


class TestTwitterPublisherRetryMechanism:
    """Test retry mechanism integration with Twitter Publisher"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.publisher.settings') as mock_settings:
            mock_settings.TARGET_LANGUAGES = [
                {'code': 'ja', 'name': 'Japanese'}
            ]
            mock_settings.get_twitter_creds_for_language.return_value = {
                'consumer_key': 'test_key',
                'consumer_secret': 'test_secret',
                'access_token': 'test_token',
                'access_token_secret': 'test_token_secret'
            }
            
            with patch('tweepy.OAuth1UserHandler'), \
                 patch('tweepy.API') as mock_api_class:
                
                mock_api_instance = Mock()
                mock_api_instance.verify_credentials.return_value = Mock()
                mock_api_class.return_value = mock_api_instance
                
                self.publisher = TwitterPublisher()
                self.mock_api = mock_api_instance
    
    def test_retry_on_network_error(self):
        """Test retry mechanism on network errors"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        call_count = 0
        
        def failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            
            mock_status = Mock()
            mock_status.id = 987654321
            return mock_status
        
        self.mock_api.update_status = failing_then_success
        
        with patch.object(self.publisher, 'can_post', return_value=True), \
             patch('src.services.publisher.twitter_monitor'):
            
            result = self.publisher.post_translation(translation)
            
            assert result is True
            assert call_count == 3  # Should have retried
    
    def test_retry_on_connection_error(self):
        """Test retry mechanism on connection errors"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        call_count = 0
        
        def connection_error_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TwitterConnectionError("Connection failed")
            
            mock_status = Mock()
            mock_status.id = 987654321
            return mock_status
        
        self.mock_api.update_status = connection_error_then_success
        
        with patch.object(self.publisher, 'can_post', return_value=True), \
             patch('src.services.publisher.twitter_monitor'):
            
            result = self.publisher.post_translation(translation)
            
            assert result is True
            assert call_count == 2  # Should have retried once
    
    def test_no_retry_on_auth_error(self):
        """Test that authentication errors are not retried"""
        tweet = Tweet(id="123", text="Original", created_at=datetime.now(),
                     author_username="test", author_id="456")
        translation = Translation(
            original_tweet=tweet,
            target_language="Japanese",
            translated_text="翻訳されたテキスト",
            translation_timestamp=datetime.now(),
            character_count=10,
            status='pending'
        )
        
        call_count = 0
        
        def always_auth_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise tweepy.Unauthorized("Invalid credentials")
        
        self.mock_api.update_status = always_auth_error
        
        with patch.object(self.publisher, 'can_post', return_value=True):
            with pytest.raises(TwitterAuthError):
                self.publisher.post_translation(translation)
            
            # Should only be called once (no retries for auth errors)
            assert call_count == 1


class TestTwitterPublisherUtilityMethods:
    """Test utility methods like testing connections and getting available languages"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.publisher.settings') as mock_settings:
            mock_settings.TARGET_LANGUAGES = [
                {'code': 'ja', 'name': 'Japanese'},
                {'code': 'es', 'name': 'Spanish'}
            ]
            
            def mock_get_creds(lang_code):
                return {
                    'consumer_key': f'{lang_code}_key',
                    'consumer_secret': f'{lang_code}_secret',
                    'access_token': f'{lang_code}_token',
                    'access_token_secret': f'{lang_code}_token_secret'
                }
            
            mock_settings.get_twitter_creds_for_language.side_effect = mock_get_creds
            
            with patch('tweepy.OAuth1UserHandler'), \
                 patch('tweepy.API') as mock_api_class:
                
                # Create separate mock instances for each language
                self.mock_api_ja = Mock()
                self.mock_api_ja.verify_credentials.return_value = Mock()
                self.mock_api_es = Mock()
                self.mock_api_es.verify_credentials.return_value = Mock()
                
                mock_api_class.side_effect = [self.mock_api_ja, self.mock_api_es]
                
                self.publisher = TwitterPublisher()
    
    def test_get_available_languages(self):
        """Test getting list of available languages"""
        languages = self.publisher.get_available_languages()
        
        assert 'ja' in languages
        assert 'es' in languages
        assert len(languages) == 2
    
    def test_test_connections_all_successful(self):
        """Test connection testing when all accounts work"""
        # Mock successful verification for both accounts
        mock_user_ja = Mock()
        mock_user_ja.screen_name = "test_ja"
        mock_user_ja.id = 123
        
        mock_user_es = Mock()
        mock_user_es.screen_name = "test_es"
        mock_user_es.id = 456
        
        self.mock_api_ja.verify_credentials.return_value = mock_user_ja
        self.mock_api_es.verify_credentials.return_value = mock_user_es
        
        # Should not raise any exceptions
        self.publisher.test_connections()
    
    def test_test_connections_auth_failure(self):
        """Test connection testing with authentication failures"""
        # Mock auth failure for Japanese account
        self.mock_api_ja.verify_credentials.side_effect = tweepy.Unauthorized("Invalid token")
        
        # Mock success for Spanish account
        mock_user_es = Mock()
        mock_user_es.screen_name = "test_es"
        mock_user_es.id = 456
        self.mock_api_es.verify_credentials.return_value = mock_user_es
        
        # Should not raise exceptions, just log errors
        self.publisher.test_connections()
    
    def test_test_connections_rate_limit(self):
        """Test connection testing with rate limit errors"""
        # Mock rate limit for Japanese account
        self.mock_api_ja.verify_credentials.side_effect = tweepy.TooManyRequests("Rate limited")
        
        # Mock success for Spanish account
        mock_user_es = Mock()
        mock_user_es.screen_name = "test_es"
        mock_user_es.id = 456
        self.mock_api_es.verify_credentials.return_value = mock_user_es
        
        # Should not raise exceptions, just log errors
        self.publisher.test_connections()
    
    def test_test_connections_general_error(self):
        """Test connection testing with general errors"""
        # Mock general error for Japanese account
        self.mock_api_ja.verify_credentials.side_effect = Exception("Unknown error")
        
        # Mock success for Spanish account
        mock_user_es = Mock()
        mock_user_es.screen_name = "test_es"
        mock_user_es.id = 456
        self.mock_api_es.verify_credentials.return_value = mock_user_es
        
        # Should not raise exceptions, just log errors
        self.publisher.test_connections()
    
    def test_test_connections_no_clients(self):
        """Test connection testing when no clients are configured"""
        # Create publisher with no language clients
        empty_publisher = TwitterPublisher()
        empty_publisher.language_clients = {}
        
        # Should not raise exceptions, just log warning
        empty_publisher.test_connections()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
