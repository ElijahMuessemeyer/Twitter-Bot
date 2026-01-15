# =============================================================================
# TWITTER MONITOR SERVICE ERROR HANDLING TESTS
# =============================================================================

import pytest
import tweepy
import json
import time
from unittest.mock import Mock, patch, MagicMock, mock_open
from pathlib import Path
from datetime import datetime

from src.services.twitter_monitor import TwitterMonitor, twitter_monitor
from src.models.tweet import Tweet
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


class TestTwitterMonitorInitialization:
    """Test Twitter Monitor initialization and credential validation"""
    
    @patch('src.services.twitter_monitor.settings')
    def test_initialization_without_credentials(self, mock_settings):
        """Test initialization fails gracefully without valid credentials"""
        mock_settings.PRIMARY_TWITTER_CREDS = None
        
        monitor = TwitterMonitor()
        
        assert monitor.api is None
        assert monitor.daily_requests == 0
        assert monitor.monthly_posts == 0
    
    @patch('src.services.twitter_monitor.settings')
    def test_initialization_with_invalid_credentials(self, mock_settings):
        """Test initialization with placeholder credentials"""
        mock_settings.PRIMARY_TWITTER_CREDS = {
            'consumer_key': 'your_consumer_key',
            'consumer_secret': 'your_consumer_secret',
            'access_token': 'your_access_token',
            'access_token_secret': 'your_access_token_secret'
        }
        
        monitor = TwitterMonitor()
        
        assert monitor.api is None
    
    @patch('src.services.twitter_monitor.settings')
    @patch('tweepy.API')
    @patch('tweepy.OAuth1UserHandler')
    def test_initialization_with_valid_credentials_but_auth_fails(self, mock_auth, mock_api, mock_settings):
        """Test initialization with valid credentials but Twitter auth fails"""
        mock_settings.PRIMARY_TWITTER_CREDS = {
            'consumer_key': 'real_key',
            'consumer_secret': 'real_secret',
            'access_token': 'real_token',
            'access_token_secret': 'real_token_secret'
        }
        
        # Mock API to raise auth error on verify_credentials
        mock_api_instance = Mock()
        mock_api_instance.verify_credentials.side_effect = tweepy.Unauthorized("Invalid credentials")
        mock_api.return_value = mock_api_instance
        
        with pytest.raises(TwitterAuthError):
            TwitterMonitor()
    
    @patch('src.services.twitter_monitor.settings')
    @patch('tweepy.API')
    @patch('tweepy.OAuth1UserHandler')
    def test_initialization_with_missing_credentials_keys(self, mock_auth, mock_api, mock_settings):
        """Test initialization with incomplete credential dict"""
        mock_settings.PRIMARY_TWITTER_CREDS = {
            'consumer_key': 'key',
            # Missing other required keys
        }
        
        with pytest.raises(ConfigurationError):
            TwitterMonitor()


class TestTwitterMonitorAPIUsageTracking:
    """Test API usage tracking and quota management"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.twitter_monitor.settings') as mock_settings:
            mock_settings.PRIMARY_TWITTER_CREDS = None
            self.monitor = TwitterMonitor()
    
    def test_load_api_usage_file_not_exists(self):
        """Test loading usage when file doesn't exist"""
        with patch.object(Path, 'exists', return_value=False):
            self.monitor.load_api_usage()
            
            assert self.monitor.daily_requests == 0
            assert self.monitor.monthly_posts == 0
    
    def test_load_api_usage_invalid_json(self):
        """Test loading usage with corrupted JSON file"""
        mock_file_data = "invalid json data"
        
        with patch.object(Path, 'exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=mock_file_data)):
            
            self.monitor.load_api_usage()
            
            # Should reset to defaults on JSON error
            assert self.monitor.daily_requests == 0
            assert self.monitor.monthly_posts == 0
    
    def test_load_api_usage_valid_data_same_day(self):
        """Test loading usage data from same day"""
        today = datetime.now().strftime('%Y-%m-%d')
        month = datetime.now().strftime('%Y-%m')
        
        mock_usage_data = {
            'date': today,
            'month': month,
            'daily_requests': 50,
            'monthly_posts': 15,
            'last_updated': datetime.now().isoformat()
        }
        
        with patch.object(Path, 'exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(mock_usage_data))):
            
            self.monitor.load_api_usage()
            
            assert self.monitor.daily_requests == 50
            assert self.monitor.monthly_posts == 15
    
    def test_load_api_usage_different_day(self):
        """Test loading usage data from different day resets daily counter"""
        yesterday_date = '2024-01-01'
        month = datetime.now().strftime('%Y-%m')
        
        mock_usage_data = {
            'date': yesterday_date,
            'month': month,
            'daily_requests': 50,
            'monthly_posts': 15,
            'last_updated': '2024-01-01T10:00:00'
        }
        
        with patch.object(Path, 'exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(mock_usage_data))):
            
            self.monitor.load_api_usage()
            
            assert self.monitor.daily_requests == 0  # Reset for new day
            assert self.monitor.monthly_posts == 15  # Keep monthly count
    
    @patch('src.services.twitter_monitor.settings')
    def test_can_make_request_within_limit(self, mock_settings):
        """Test quota check when within daily limit"""
        mock_settings.TWITTER_FREE_DAILY_LIMIT = 100
        
        self.monitor.daily_requests = 50
        
        assert self.monitor.can_make_request() is True
    
    @patch('src.services.twitter_monitor.settings')
    def test_can_make_request_exceeds_limit(self, mock_settings):
        """Test quota check when exceeding daily limit"""
        mock_settings.TWITTER_FREE_DAILY_LIMIT = 100
        
        self.monitor.daily_requests = 100
        
        with pytest.raises(TwitterQuotaExceededError) as exc_info:
            self.monitor.can_make_request()
        
        error = exc_info.value
        assert error.quota_type == "daily_requests"
        assert error.current_usage == 100
        assert error.quota_limit == 100
    
    @patch('src.services.twitter_monitor.settings')
    def test_can_post_tweet_within_limit(self, mock_settings):
        """Test monthly posting quota check"""
        mock_settings.TWITTER_FREE_MONTHLY_LIMIT = 50
        
        self.monitor.monthly_posts = 25
        
        assert self.monitor.can_post_tweet() is True
    
    @patch('src.services.twitter_monitor.settings')
    def test_can_post_tweet_exceeds_limit(self, mock_settings):
        """Test monthly posting quota exceeded"""
        mock_settings.TWITTER_FREE_MONTHLY_LIMIT = 50
        
        self.monitor.monthly_posts = 50
        
        with pytest.raises(TwitterQuotaExceededError) as exc_info:
            self.monitor.can_post_tweet()
        
        error = exc_info.value
        assert error.quota_type == "monthly_posts"
        assert error.current_usage == 50
        assert error.quota_limit == 50


class TestTwitterMonitorTweetFetching:
    """Test tweet fetching with comprehensive error scenarios"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.twitter_monitor.settings') as mock_settings:
            mock_settings.PRIMARY_TWITTER_CREDS = {
                'consumer_key': 'test_key',
                'consumer_secret': 'test_secret',
                'access_token': 'test_token',
                'access_token_secret': 'test_token_secret'
            }
            mock_settings.PRIMARY_USERNAME = 'test_user'
            mock_settings.TWITTER_FREE_DAILY_LIMIT = 100
            
            # Mock the API creation to avoid actual Twitter connection
            with patch('tweepy.API') as mock_api, \
                 patch('tweepy.OAuth1UserHandler'):
                mock_api_instance = Mock()
                mock_api_instance.verify_credentials.return_value = Mock()
                mock_api.return_value = mock_api_instance
                
                self.monitor = TwitterMonitor()
                self.monitor.api = mock_api_instance
    
    def test_get_new_tweets_no_api_initialized(self):
        """Test fetching tweets when API is not initialized"""
        self.monitor.api = None
        
        with pytest.raises(ConfigurationError):
            self.monitor.get_new_tweets()
    
    def test_get_new_tweets_quota_exceeded(self):
        """Test fetching tweets when daily quota is exceeded"""
        with patch.object(self.monitor, 'can_make_request') as mock_can_request:
            mock_can_request.side_effect = TwitterQuotaExceededError(
                "Daily limit exceeded",
                quota_type="daily_requests",
                current_usage=100,
                quota_limit=100
            )
            
            with pytest.raises(TwitterQuotaExceededError):
                self.monitor.get_new_tweets()
    
    def test_get_new_tweets_twitter_auth_error(self):
        """Test handling Twitter authentication errors"""
        # Mock the cursor to raise auth error
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.side_effect = tweepy.Unauthorized("Invalid token")
            
            with pytest.raises(TwitterAuthError) as exc_info:
                self.monitor.get_new_tweets()
            
            assert "authentication failed" in str(exc_info.value).lower()
    
    def test_get_new_tweets_rate_limit_error(self):
        """Test handling Twitter rate limit errors"""
        # Create mock response with rate limit headers
        mock_response = Mock()
        mock_response.headers = {'x-rate-limit-reset': '1234567890'}
        
        rate_limit_error = tweepy.TooManyRequests(response=mock_response)
        
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.side_effect = rate_limit_error
            
            with pytest.raises(TwitterRateLimitError) as exc_info:
                self.monitor.get_new_tweets()
            
            error = exc_info.value
            assert error.reset_time == 1234567890
    
    def test_get_new_tweets_forbidden_error(self):
        """Test handling Twitter forbidden errors"""
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.side_effect = tweepy.Forbidden("Access forbidden")
            
            with pytest.raises(TwitterAuthError) as exc_info:
                self.monitor.get_new_tweets()
            
            assert "forbidden" in str(exc_info.value).lower()
    
    def test_get_new_tweets_network_error(self):
        """Test handling network connectivity errors"""
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.side_effect = ConnectionError("Network down")
            
            with pytest.raises(NetworkError) as exc_info:
                self.monitor.get_new_tweets()
            
            assert "network error" in str(exc_info.value).lower()
    
    def test_get_new_tweets_timeout_error(self):
        """Test handling timeout errors"""
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.side_effect = TimeoutError("Request timeout")
            
            with pytest.raises(NetworkError) as exc_info:
                self.monitor.get_new_tweets()
            
            assert "network error" in str(exc_info.value).lower()
    
    def test_get_new_tweets_bad_request_error(self):
        """Test handling Twitter bad request errors"""
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.side_effect = tweepy.BadRequest("Invalid parameters")
            
            with pytest.raises(TwitterAPIError) as exc_info:
                self.monitor.get_new_tweets()
            
            assert "twitter api error" in str(exc_info.value).lower()
    
    def test_get_new_tweets_successful_fetch(self):
        """Test successful tweet fetching"""
        # Create mock tweet data
        mock_tweet = Mock()
        mock_tweet.id = 123456789
        mock_tweet.full_text = "Test tweet content"
        mock_tweet.created_at = datetime.now()
        mock_tweet.user.screen_name = "test_user"
        mock_tweet.user.id = 987654321
        mock_tweet.retweet_count = 5
        mock_tweet.favorite_count = 10
        
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.return_value = [mock_tweet]
            
            with patch.object(self.monitor, 'get_last_tweet_id', return_value=None), \
                 patch.object(self.monitor, 'save_last_tweet_id'), \
                 patch.object(self.monitor, 'save_api_usage'):
                
                tweets = self.monitor.get_new_tweets()
                
                assert len(tweets) == 1
                assert tweets[0].id == "123456789"
                assert tweets[0].text == "Test tweet content"
                assert tweets[0].author_username == "test_user"
                assert self.monitor.daily_requests == 1
    
    def test_get_new_tweets_error_recovery_success(self):
        """Test error recovery mechanism on unknown errors"""
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.side_effect = Exception("Unknown error")
            
            with patch('src.services.twitter_monitor.recover_from_error') as mock_recovery:
                mock_recovery.return_value = {'success': True}
                
                tweets = self.monitor.get_new_tweets()
                
                # Should return empty list as fallback
                assert tweets == []
                mock_recovery.assert_called_once()
    
    def test_get_new_tweets_error_recovery_failure(self):
        """Test error recovery mechanism failure"""
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.side_effect = Exception("Unknown error")
            
            with patch('src.services.twitter_monitor.recover_from_error') as mock_recovery:
                mock_recovery.return_value = {'success': False}
                
                with pytest.raises(TwitterAPIError):
                    self.monitor.get_new_tweets()
    
    def test_get_new_tweets_individual_tweet_processing_error(self):
        """Test handling errors in individual tweet processing"""
        # Create one good tweet and one that will cause an error
        mock_tweet_good = Mock()
        mock_tweet_good.id = 123456789
        mock_tweet_good.full_text = "Good tweet"
        mock_tweet_good.created_at = datetime.now()
        mock_tweet_good.user.screen_name = "test_user"
        mock_tweet_good.user.id = 987654321
        mock_tweet_good.retweet_count = 5
        mock_tweet_good.favorite_count = 10
        
        mock_tweet_bad = Mock()
        mock_tweet_bad.id = 987654321
        # Simulate missing attribute to cause error
        del mock_tweet_bad.full_text
        
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.return_value = [mock_tweet_good, mock_tweet_bad]
            
            with patch.object(self.monitor, 'get_last_tweet_id', return_value=None), \
                 patch.object(self.monitor, 'save_last_tweet_id'), \
                 patch.object(self.monitor, 'save_api_usage'):
                
                tweets = self.monitor.get_new_tweets()
                
                # Should only return the good tweet, skip the bad one
                assert len(tweets) == 1
                assert tweets[0].id == "123456789"


class TestTwitterMonitorCircuitBreaker:
    """Test circuit breaker integration with Twitter Monitor"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.twitter_monitor.settings') as mock_settings:
            mock_settings.PRIMARY_TWITTER_CREDS = {
                'consumer_key': 'test_key',
                'consumer_secret': 'test_secret',
                'access_token': 'test_token',
                'access_token_secret': 'test_token_secret'
            }
            mock_settings.PRIMARY_USERNAME = 'test_user'
            mock_settings.TWITTER_FREE_DAILY_LIMIT = 100
            
            with patch('tweepy.API') as mock_api, \
                 patch('tweepy.OAuth1UserHandler'):
                mock_api_instance = Mock()
                mock_api_instance.verify_credentials.return_value = Mock()
                mock_api.return_value = mock_api_instance
                
                self.monitor = TwitterMonitor()
                self.monitor.api = mock_api_instance
    
    @patch('src.services.twitter_monitor.circuit_breaker_protection')
    def test_circuit_breaker_protection_decorator_applied(self, mock_cb_decorator):
        """Test that circuit breaker decorator is properly applied"""
        # The decorator should be applied to get_new_tweets method
        # This test verifies the decorator is in place
        mock_cb_decorator.return_value = lambda func: func
        
        # Call the method to ensure decorator is triggered
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items.return_value = []
            
            with patch.object(self.monitor, 'get_last_tweet_id', return_value=None):
                self.monitor.get_new_tweets()
        
        # Verify circuit breaker was configured for "twitter_api"
        mock_cb_decorator.assert_called()
    
    def test_circuit_breaker_opens_on_repeated_failures(self):
        """Test circuit breaker opens after repeated failures"""
        from src.utils.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig
        
        # Get or create circuit breaker for twitter_api
        cb_manager = CircuitBreakerManager()
        
        # Configure a low threshold for testing
        test_config = CircuitBreakerConfig(
            failure_threshold=2,
            min_requests=1,
            timeout=0.1
        )
        cb = cb_manager.get_circuit_breaker("twitter_api_test", test_config)
        
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
    
    def test_circuit_breaker_half_open_recovery(self):
        """Test circuit breaker recovery to half-open state"""
        from src.utils.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig
        
        cb_manager = CircuitBreakerManager()
        test_config = CircuitBreakerConfig(
            failure_threshold=1,
            min_requests=1,
            timeout=0.01  # Very short timeout for testing
        )
        cb = cb_manager.get_circuit_breaker("twitter_api_recovery_test", test_config)
        
        # Cause failure to open circuit
        try:
            cb.call(lambda: (_ for _ in ()).throw(TwitterConnectionError("Connection failed")))
        except TwitterConnectionError:
            pass
        
        cb._update_state()
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout and check recovery
        time.sleep(0.02)
        cb._update_state()
        assert cb.state == CircuitState.HALF_OPEN


class TestTwitterMonitorRetryMechanism:
    """Test retry mechanism integration"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.twitter_monitor.settings') as mock_settings:
            mock_settings.PRIMARY_TWITTER_CREDS = {
                'consumer_key': 'test_key',
                'consumer_secret': 'test_secret',
                'access_token': 'test_token',
                'access_token_secret': 'test_token_secret'
            }
            mock_settings.PRIMARY_USERNAME = 'test_user'
            mock_settings.TWITTER_FREE_DAILY_LIMIT = 100
            
            with patch('tweepy.API') as mock_api, \
                 patch('tweepy.OAuth1UserHandler'):
                mock_api_instance = Mock()
                mock_api_instance.verify_credentials.return_value = Mock()
                mock_api.return_value = mock_api_instance
                
                self.monitor = TwitterMonitor()
                self.monitor.api = mock_api_instance
    
    def test_retry_on_network_error(self):
        """Test retry mechanism on network errors"""
        call_count = 0
        
        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise NetworkError("Network temporarily down")
            return [Mock()]  # Return mock tweet list
        
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items = failing_then_success
            
            with patch.object(self.monitor, 'get_last_tweet_id', return_value=None), \
                 patch.object(self.monitor, 'save_last_tweet_id'), \
                 patch.object(self.monitor, 'save_api_usage'):
                
                # This should succeed after retries
                tweets = self.monitor.get_new_tweets()
                
                # Verify it was called multiple times
                assert call_count == 3
    
    def test_retry_on_connection_error(self):
        """Test retry mechanism on connection errors"""
        call_count = 0
        
        def failing_connection():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TwitterConnectionError("Connection failed")
            return []
        
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items = failing_connection
            
            with patch.object(self.monitor, 'get_last_tweet_id', return_value=None):
                
                tweets = self.monitor.get_new_tweets()
                
                # Should have retried once
                assert call_count == 2
    
    def test_no_retry_on_auth_error(self):
        """Test that authentication errors are not retried"""
        call_count = 0
        
        def always_auth_error():
            nonlocal call_count
            call_count += 1
            raise tweepy.Unauthorized("Invalid credentials")
        
        with patch('tweepy.Cursor') as mock_cursor:
            mock_cursor.return_value.items = always_auth_error
            
            with pytest.raises(TwitterAuthError):
                self.monitor.get_new_tweets()
            
            # Should only be called once (no retries for auth errors)
            assert call_count == 1
    
    def test_no_retry_on_quota_exceeded(self):
        """Test that quota exceeded errors are not retried"""
        call_count = 0
        
        def quota_exceeded_error():
            nonlocal call_count
            call_count += 1
            raise TwitterQuotaExceededError("Quota exceeded")
        
        with patch.object(self.monitor, 'can_make_request', side_effect=quota_exceeded_error):
            
            with pytest.raises(TwitterQuotaExceededError):
                self.monitor.get_new_tweets()
            
            # Should only be called once (no retries for quota errors)
            assert call_count == 1


class TestTwitterMonitorFileOperations:
    """Test file operations for tweet ID and usage tracking"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('src.services.twitter_monitor.settings') as mock_settings:
            mock_settings.PRIMARY_TWITTER_CREDS = None
            self.monitor = TwitterMonitor()
    
    def test_get_last_tweet_id_file_not_exists(self):
        """Test getting last tweet ID when file doesn't exist"""
        with patch.object(Path, 'exists', return_value=False):
            result = self.monitor.get_last_tweet_id()
            assert result is None
    
    def test_get_last_tweet_id_file_read_error(self):
        """Test handling file read errors"""
        with patch.object(Path, 'exists', return_value=True), \
             patch('builtins.open', side_effect=IOError("Permission denied")):
            
            result = self.monitor.get_last_tweet_id()
            assert result is None
    
    def test_save_last_tweet_id_success(self):
        """Test saving last tweet ID successfully"""
        mock_file = mock_open()
        
        with patch('builtins.open', mock_file), \
             patch.object(Path, 'mkdir'):
            
            self.monitor.save_last_tweet_id("123456789")
            
            mock_file.assert_called_once_with(self.monitor.last_tweet_id_file, 'w')
            mock_file().write.assert_called_once_with("123456789")
    
    def test_save_last_tweet_id_write_error(self):
        """Test handling write errors when saving tweet ID"""
        with patch('builtins.open', side_effect=IOError("Disk full")), \
             patch.object(Path, 'mkdir'):
            
            # Should not raise exception, just log error
            self.monitor.save_last_tweet_id("123456789")
    
    def test_save_api_usage_success(self):
        """Test saving API usage successfully"""
        mock_file = mock_open()
        
        with patch('builtins.open', mock_file), \
             patch.object(Path, 'mkdir'), \
             patch('json.dump') as mock_json_dump:
            
            self.monitor.save_api_usage()
            
            mock_file.assert_called_once()
            mock_json_dump.assert_called_once()
    
    def test_save_api_usage_write_error(self):
        """Test handling write errors when saving API usage"""
        with patch('builtins.open', side_effect=IOError("Permission denied")), \
             patch.object(Path, 'mkdir'):
            
            # Should not raise exception, just log error
            self.monitor.save_api_usage()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
