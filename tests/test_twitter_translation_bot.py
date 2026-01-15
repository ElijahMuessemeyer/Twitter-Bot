# =============================================================================
# COMPREHENSIVE TWITTER TRANSLATION BOT TESTS
# =============================================================================

import pytest
import sys
import os
import time
from datetime import datetime
from unittest.mock import patch, MagicMock, call, AsyncMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import TwitterTranslationBot
from src.models.tweet import Tweet, Translation
from src.exceptions import (
    TwitterAPIError,
    TwitterRateLimitError,
    TwitterAuthError,
    TwitterQuotaExceededError,
    GeminiAPIError,
    GeminiQuotaError,
    TranslationError,
    ConfigurationError,
    NetworkError
)


class TestTwitterTranslationBot:
    """Comprehensive test suite for TwitterTranslationBot class"""

    @pytest.fixture
    def bot(self):
        """Create a TwitterTranslationBot instance for testing"""
        return TwitterTranslationBot()

    @pytest.fixture
    def sample_tweet(self):
        """Create a sample tweet for testing"""
        return Tweet(
            id="123456789",
            text="Hello world! This is a test tweet #testing",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={"like_count": 10, "retweet_count": 5}
        )

    @pytest.fixture
    def sample_translation(self, sample_tweet):
        """Create a sample translation for testing"""
        return Translation(
            original_tweet=sample_tweet,
            target_language="Spanish",
            translated_text="¡Hola mundo! Esta es una prueba de tweet #testing",
            translation_timestamp=datetime.now(),
            character_count=50,
            status="pending",
            post_id="trans_123"
        )

    @pytest.fixture
    def language_configs(self):
        """Create sample language configurations"""
        return [
            {"code": "es", "name": "Spanish", "formal_tone": False},
            {"code": "fr", "name": "French", "formal_tone": True},
            {"code": "de", "name": "German", "formal_tone": False}
        ]

    def test_init(self, bot):
        """Test TwitterTranslationBot initialization"""
        assert hasattr(bot, 'running')
        assert bot.running is False

    def test_stop_method(self, bot):
        """Test bot stop method"""
        bot.running = True
        with patch('main.logger') as mock_logger:
            bot.stop()
            assert bot.running is False
            mock_logger.info.assert_called_once_with("🛑 Bot stop requested")

    # =========================================================================
    # PROCESS_NEW_TWEETS TESTS
    # =========================================================================

    @patch('main.cache_monitor')
    @patch('main.twitter_monitor')
    def test_process_new_tweets_no_tweets(self, mock_monitor, mock_cache_monitor, bot):
        """Test process_new_tweets when no new tweets are found"""
        mock_monitor.get_new_tweets.return_value = []
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        mock_cache_monitor.log_cache_stats_periodically.assert_called_once()
        mock_monitor.get_new_tweets.assert_called_once()
        mock_logger.info.assert_called_with("📭 No new tweets found")

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_success_flow(self, mock_sleep, mock_structured_logger, 
                                           mock_cache_monitor, mock_draft_manager, 
                                           mock_publisher, mock_translator, mock_monitor, 
                                           mock_settings, bot, sample_tweet, sample_translation, 
                                           language_configs):
        """Test successful tweet processing flow"""
        # Setup mocks
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = language_configs[:1]  # Just Spanish
        mock_translator.translate_tweet.return_value = sample_translation
        mock_publisher.can_post.return_value = True
        mock_publisher.post_translation.return_value = True
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Verify cache monitoring
        mock_cache_monitor.log_cache_stats_periodically.assert_called_once()
        
        # Verify structured logging
        mock_structured_logger.log_tweet_processing.assert_called_once_with(
            tweet_id=sample_tweet.id,
            text_preview=sample_tweet.text,
            language_count=1
        )
        
        # Verify translation and posting
        mock_translator.translate_tweet.assert_called_once_with(
            sample_tweet, "Spanish", language_configs[0]
        )
        mock_publisher.can_post.assert_called_once()
        mock_publisher.post_translation.assert_called_once_with(sample_translation)
        
        # Verify no draft saved (posting was successful)
        mock_draft_manager.save_translation_as_draft.assert_not_called()
        
        # Verify delay between tweets
        mock_sleep.assert_called_once_with(2)

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_multiple_languages(self, mock_sleep, mock_structured_logger,
                                                  mock_cache_monitor, mock_draft_manager,
                                                  mock_publisher, mock_translator, mock_monitor,
                                                  mock_settings, bot, sample_tweet, language_configs):
        """Test processing tweet for multiple target languages"""
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = language_configs
        mock_publisher.can_post.return_value = True
        mock_publisher.post_translation.return_value = True
        
        # Mock different translations for each language
        def mock_translate(tweet, lang, config):
            return Translation(
                original_tweet=tweet,
                target_language=lang,
                translated_text=f"Hello in {lang}",
                translation_timestamp=datetime.now(),
                character_count=15,
                status="pending"
            )
        
        mock_translator.translate_tweet.side_effect = mock_translate
        
        bot.process_new_tweets()
        
        # Should translate to all three languages
        assert mock_translator.translate_tweet.call_count == 3
        assert mock_publisher.post_translation.call_count == 3
        
        # Verify all languages were processed
        calls = mock_translator.translate_tweet.call_args_list
        languages_processed = [call[0][1] for call in calls]
        assert "Spanish" in languages_processed
        assert "French" in languages_processed
        assert "German" in languages_processed

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_posting_failure_saves_draft(self, mock_sleep, mock_structured_logger,
                                                           mock_cache_monitor, mock_draft_manager,
                                                           mock_publisher, mock_translator, mock_monitor,
                                                           mock_settings, bot, sample_tweet, 
                                                           sample_translation, language_configs):
        """Test that failed posts are saved as drafts"""
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = language_configs[:1]
        mock_translator.translate_tweet.return_value = sample_translation
        mock_publisher.can_post.return_value = True
        mock_publisher.post_translation.return_value = False  # Posting failed
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should save as draft when posting fails
        mock_draft_manager.save_translation_as_draft.assert_called_once_with(
            sample_translation, language_configs[0]
        )
        
        # Should log warning about failed post
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if "Failed to post" in str(call)]
        assert len(warning_calls) > 0

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_quota_limit_saves_draft(self, mock_sleep, mock_structured_logger,
                                                       mock_cache_monitor, mock_draft_manager,
                                                       mock_publisher, mock_translator, mock_monitor,
                                                       mock_settings, bot, sample_tweet, 
                                                       sample_translation, language_configs):
        """Test that API quota limits save translations as drafts"""
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = language_configs[:1]
        mock_translator.translate_tweet.return_value = sample_translation
        mock_publisher.can_post.return_value = False  # API limit reached
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should save as draft when API limits reached
        mock_draft_manager.save_translation_as_draft.assert_called_once_with(
            sample_translation, language_configs[0]
        )
        
        # Should log info about API limit
        info_calls = [call for call in mock_logger.info.call_args_list 
                     if "API limit reached" in str(call)]
        assert len(info_calls) > 0

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.cache_monitor')
    def test_process_new_tweets_twitter_quota_exceeded(self, mock_cache_monitor, mock_monitor, 
                                                      mock_settings, bot):
        """Test handling TwitterQuotaExceededError"""
        mock_monitor.get_new_tweets.side_effect = TwitterQuotaExceededError(
            "Daily quota exceeded", quota_type="daily", current_usage=1500, quota_limit=1500
        )
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should log warning and return early
        mock_logger.warning.assert_called()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "Twitter quota exceeded" in warning_call

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.cache_monitor')
    def test_process_new_tweets_twitter_auth_error(self, mock_cache_monitor, mock_monitor, 
                                                  mock_settings, bot):
        """Test handling TwitterAuthError"""
        mock_monitor.get_new_tweets.side_effect = TwitterAuthError("Invalid credentials")
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should log error and return early
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0][0]
        assert "Twitter configuration error" in error_call

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.cache_monitor')
    def test_process_new_tweets_twitter_rate_limit(self, mock_cache_monitor, mock_monitor, 
                                                  mock_settings, bot):
        """Test handling TwitterRateLimitError"""
        mock_monitor.get_new_tweets.side_effect = TwitterRateLimitError(
            "Rate limit exceeded", reset_time=1640995200, remaining=0
        )
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should log info and return early
        mock_logger.info.assert_called()
        info_call = mock_logger.info.call_args[0][0]
        assert "Twitter rate limit hit" in info_call

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.cache_monitor')
    def test_process_new_tweets_network_error(self, mock_cache_monitor, mock_monitor, 
                                             mock_settings, bot):
        """Test handling NetworkError"""
        mock_monitor.get_new_tweets.side_effect = NetworkError("Connection timeout")
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should log warning and return early
        mock_logger.warning.assert_called()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "Network error fetching tweets" in warning_call

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.cache_monitor')
    def test_process_new_tweets_twitter_api_error(self, mock_cache_monitor, mock_monitor, 
                                                 mock_settings, bot):
        """Test handling TwitterAPIError"""
        mock_monitor.get_new_tweets.side_effect = TwitterAPIError("API error occurred")
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should log error and return early
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0][0]
        assert "Twitter API error" in error_call

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_gemini_quota_error(self, mock_sleep, mock_structured_logger,
                                                  mock_cache_monitor, mock_draft_manager,
                                                  mock_publisher, mock_translator, mock_monitor,
                                                  mock_settings, bot, sample_tweet, language_configs):
        """Test handling GeminiQuotaError during translation"""
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = language_configs
        mock_translator.translate_tweet.side_effect = [
            GeminiQuotaError("Gemini quota exceeded"),  # First language fails
            None,  # Second language succeeds with None (no translation)
            None   # Third language succeeds with None
        ]
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should log error for quota exceeded
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if "Gemini quota exceeded" in str(call)]
        assert len(error_calls) > 0
        
        # Should continue processing other languages
        assert mock_translator.translate_tweet.call_count == 3

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_translation_error(self, mock_sleep, mock_structured_logger,
                                                 mock_cache_monitor, mock_draft_manager,
                                                 mock_publisher, mock_translator, mock_monitor,
                                                 mock_settings, bot, sample_tweet, language_configs):
        """Test handling TranslationError during translation"""
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = language_configs[:1]
        mock_translator.translate_tweet.side_effect = TranslationError("Translation failed")
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should log error and continue
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if "Translation failed" in str(call)]
        assert len(error_calls) > 0

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_posting_quota_exception(self, mock_sleep, mock_structured_logger,
                                                       mock_cache_monitor, mock_draft_manager,
                                                       mock_publisher, mock_translator, mock_monitor,
                                                       mock_settings, bot, sample_tweet, 
                                                       sample_translation, language_configs):
        """Test handling TwitterQuotaExceededError during posting"""
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = language_configs[:1]
        mock_translator.translate_tweet.return_value = sample_translation
        mock_publisher.can_post.return_value = True
        mock_publisher.post_translation.side_effect = TwitterQuotaExceededError("Quota exceeded")
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should save as draft when quota exceeded during posting
        mock_draft_manager.save_translation_as_draft.assert_called_once_with(
            sample_translation, language_configs[0]
        )
        
        # Should log quota limit message
        info_calls = [call for call in mock_logger.info.call_args_list 
                     if "Quota limit reached" in str(call)]
        assert len(info_calls) > 0

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_posting_auth_error(self, mock_sleep, mock_structured_logger,
                                                  mock_cache_monitor, mock_draft_manager,
                                                  mock_publisher, mock_translator, mock_monitor,
                                                  mock_settings, bot, sample_tweet, 
                                                  sample_translation, language_configs):
        """Test handling TwitterAuthError during posting"""
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = language_configs[:1]
        mock_translator.translate_tweet.return_value = sample_translation
        mock_publisher.can_post.return_value = True
        mock_publisher.post_translation.side_effect = TwitterAuthError("Auth failed")
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should save as draft when auth error during posting
        mock_draft_manager.save_translation_as_draft.assert_called_once_with(
            sample_translation, language_configs[0]
        )
        
        # Should log warning about failed post
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if "Failed to post" in str(call)]
        assert len(warning_calls) > 0

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.cache_monitor')
    @patch('main.recover_from_error')
    @patch('main.circuit_breaker_manager')
    def test_process_new_tweets_unexpected_exception_recovery(self, mock_circuit_breaker, 
                                                             mock_recover, mock_cache_monitor,
                                                             mock_monitor, mock_settings, bot):
        """Test error recovery for unexpected exceptions"""
        mock_monitor.get_new_tweets.side_effect = Exception("Unexpected error")
        mock_recover.return_value = {'success': False}
        mock_circuit_breaker.get_all_health_status.return_value = [
            {'name': 'twitter_api', 'healthy': False, 'state': 'open', 'failure_count': 5}
        ]
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should call error recovery
        mock_recover.assert_called_once()
        recovery_call = mock_recover.call_args[0]
        assert isinstance(recovery_call[0], Exception)
        assert recovery_call[1]['operation_type'] == 'process_new_tweets'
        assert recovery_call[1]['service'] == 'twitter_bot'
        
        # Should log error
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0][0]
        assert "Error in process_new_tweets" in error_call
        
        # Should check circuit breaker health
        mock_circuit_breaker.get_all_health_status.assert_called_once()

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_translation_returns_none(self, mock_sleep, mock_structured_logger,
                                                        mock_cache_monitor, mock_translator,
                                                        mock_monitor, mock_settings, bot, 
                                                        sample_tweet, language_configs):
        """Test handling when translation returns None"""
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = language_configs[:1]
        mock_translator.translate_tweet.return_value = None  # Translation failed
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should log error about failed translation
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if "Failed to translate tweet" in str(call)]
        assert len(error_calls) > 0

    # =========================================================================
    # RUN_ONCE TESTS
    # =========================================================================

    @patch('main.settings')
    @patch('main.structured_logger')
    def test_run_once_validates_credentials_failure(self, mock_structured_logger, mock_settings, bot):
        """Test run_once validation failure"""
        mock_settings.validate_credentials.return_value = False
        
        with patch.object(bot, 'process_new_tweets') as mock_process:
            with patch('main.logger') as mock_logger:
                bot.run_once()
        
        # Should log bot lifecycle start
        mock_structured_logger.log_bot_lifecycle.assert_called_once_with("start_single_run", mode="once")
        
        # Should not process tweets if credentials invalid
        mock_process.assert_not_called()
        
        # Should log error about missing credentials
        mock_logger.error.assert_called_once_with(
            "❌ Missing API credentials. Please check your .env file."
        )

    @patch('main.settings')
    @patch('main.draft_manager')
    @patch('main.structured_logger')
    def test_run_once_success_with_drafts(self, mock_structured_logger, mock_draft_manager, mock_settings, bot):
        """Test successful run_once with draft status"""
        mock_settings.validate_credentials.return_value = True
        mock_draft_manager.get_draft_count.return_value = 5
        
        with patch.object(bot, 'process_new_tweets') as mock_process:
            with patch('main.logger') as mock_logger:
                bot.run_once()
        
        # Should validate credentials and process tweets
        mock_settings.validate_credentials.assert_called_once()
        mock_process.assert_called_once()
        
        # Should show draft status
        mock_draft_manager.get_draft_count.assert_called_once()
        
        # Should log draft count
        info_calls = [call for call in mock_logger.info.call_args_list 
                     if "Current pending drafts: 5" in str(call)]
        assert len(info_calls) > 0

    @patch('main.settings')
    @patch('main.draft_manager')
    @patch('main.structured_logger')
    def test_run_once_success_no_drafts(self, mock_structured_logger, mock_draft_manager, mock_settings, bot):
        """Test successful run_once with no drafts"""
        mock_settings.validate_credentials.return_value = True
        mock_draft_manager.get_draft_count.return_value = 0
        
        with patch.object(bot, 'process_new_tweets') as mock_process:
            with patch('main.logger') as mock_logger:
                bot.run_once()
        
        # Should process tweets
        mock_process.assert_called_once()
        
        # Should check draft count but not log it (0 drafts)
        mock_draft_manager.get_draft_count.assert_called_once()
        
        # Should not log draft count for 0 drafts
        info_calls = [call for call in mock_logger.info.call_args_list 
                     if "drafts" in str(call)]
        assert len(info_calls) == 0

    @patch('main.settings')
    @patch('main.structured_logger')
    @patch('main.recover_from_error')
    def test_run_once_exception_recovery(self, mock_recover, mock_structured_logger, mock_settings, bot):
        """Test error recovery in run_once"""
        mock_settings.validate_credentials.return_value = True
        
        with patch.object(bot, 'process_new_tweets') as mock_process:
            mock_process.side_effect = Exception("Process error")
            mock_recover.return_value = {'success': True}
            
            with patch('main.logger') as mock_logger:
                bot.run_once()
        
        # Should call error recovery
        mock_recover.assert_called_once()
        recovery_call = mock_recover.call_args[0]
        assert isinstance(recovery_call[0], Exception)
        assert recovery_call[1]['operation_type'] == 'run_once'
        assert recovery_call[1]['service'] == 'twitter_bot'
        
        # Should log error
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0][0]
        assert "Error in run_once" in error_call

    # =========================================================================
    # RUN_SCHEDULED TESTS
    # =========================================================================

    @patch('main.settings')
    def test_run_scheduled_validates_credentials_failure(self, mock_settings, bot):
        """Test run_scheduled validation failure"""
        mock_settings.validate_credentials.return_value = False
        
        with patch('main.logger') as mock_logger:
            bot.run_scheduled()
        
        # Should log error about missing credentials
        mock_logger.error.assert_called_once_with(
            "❌ Missing API credentials. Please check your .env file."
        )
        
        # Should not start running
        assert bot.running is False

    @patch('main.settings')
    @patch('main.schedule')
    @patch('main.time')
    def test_run_scheduled_success_start_and_stop(self, mock_time, mock_schedule, mock_settings, bot):
        """Test successful run_scheduled start and stop"""
        mock_settings.validate_credentials.return_value = True
        mock_settings.POLL_INTERVAL = 300
        
        # Mock schedule behavior
        mock_schedule.run_pending = MagicMock()
        
        # Simulate stopping after a few iterations
        iteration_count = 0
        def mock_sleep(duration):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 3:
                bot.running = False
        
        mock_time.sleep.side_effect = mock_sleep
        
        with patch('main.logger') as mock_logger:
            bot.run_scheduled()
        
        # Should set up the schedule
        mock_schedule.every.assert_called_once_with(300)
        mock_schedule.every.return_value.seconds.do.assert_called_once()
        
        # Should have started running
        assert mock_schedule.run_pending.call_count >= 3
        assert mock_time.sleep.call_count >= 3
        
        # Should have set running to True at some point
        assert bot.running is False  # Now stopped

    @patch('main.settings')
    @patch('main.schedule')
    @patch('main.time')
    def test_run_scheduled_keyboard_interrupt(self, mock_time, mock_schedule, mock_settings, bot):
        """Test run_scheduled handles KeyboardInterrupt"""
        mock_settings.validate_credentials.return_value = True
        mock_settings.POLL_INTERVAL = 300
        
        # Simulate KeyboardInterrupt
        mock_time.sleep.side_effect = KeyboardInterrupt()
        
        with patch('main.logger') as mock_logger:
            bot.run_scheduled()
        
        # Should log stop message and set running to False
        assert bot.running is False
        
        stop_calls = [call for call in mock_logger.info.call_args_list 
                     if "Stopping bot due to keyboard interrupt" in str(call)]
        assert len(stop_calls) > 0

    @patch('main.settings')
    @patch('main.schedule')
    @patch('main.time')
    def test_run_scheduled_exception_in_loop(self, mock_time, mock_schedule, mock_settings, bot):
        """Test run_scheduled handles exceptions in loop"""
        mock_settings.validate_credentials.return_value = True
        mock_settings.POLL_INTERVAL = 300
        
        # First call raises exception, subsequent calls work, then stop
        iteration_count = 0
        def mock_run_pending():
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count == 1:
                raise Exception("Loop error")
            elif iteration_count >= 3:
                bot.running = False
        
        mock_schedule.run_pending.side_effect = mock_run_pending
        
        with patch('main.logger') as mock_logger:
            bot.run_scheduled()
        
        # Should log error but continue running
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if "Error in scheduled loop" in str(call)]
        assert len(error_calls) > 0
        
        # Should have continued after error
        assert mock_schedule.run_pending.call_count >= 3

    @patch('main.settings')
    @patch('main.recover_from_error')
    def test_run_scheduled_exception_recovery(self, mock_recover, mock_settings, bot):
        """Test error recovery in run_scheduled"""
        mock_settings.validate_credentials.side_effect = Exception("Settings error")
        mock_recover.return_value = {'success': False}
        
        with patch('main.logger') as mock_logger:
            bot.run_scheduled()
        
        # Should call error recovery
        mock_recover.assert_called_once()
        recovery_call = mock_recover.call_args[0]
        assert isinstance(recovery_call[0], Exception)
        assert recovery_call[1]['operation_type'] == 'run_scheduled'
        assert recovery_call[1]['service'] == 'twitter_bot'
        
        # Should log error and stop running
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0][0]
        assert "Error in run_scheduled" in error_call
        assert bot.running is False

    # =========================================================================
    # INTEGRATION AND EDGE CASE TESTS
    # =========================================================================

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_partial_success(self, mock_sleep, mock_structured_logger,
                                               mock_cache_monitor, mock_draft_manager,
                                               mock_publisher, mock_translator, mock_monitor,
                                               mock_settings, bot, sample_tweet, language_configs):
        """Test processing with partial success across languages"""
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = language_configs
        
        # Mock mixed results for different languages
        translation_results = [
            # Spanish succeeds
            Translation(
                original_tweet=sample_tweet,
                target_language="Spanish",
                translated_text="Spanish translation",
                translation_timestamp=datetime.now(),
                character_count=20,
                status="pending"
            ),
            # French fails with None
            None,
            # German succeeds
            Translation(
                original_tweet=sample_tweet,
                target_language="German",
                translated_text="German translation",
                translation_timestamp=datetime.now(),
                character_count=18,
                status="pending"
            )
        ]
        
        mock_translator.translate_tweet.side_effect = translation_results
        mock_publisher.can_post.return_value = True
        mock_publisher.post_translation.return_value = True
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should attempt all three translations
        assert mock_translator.translate_tweet.call_count == 3
        
        # Should only post successful translations (Spanish and German)
        assert mock_publisher.post_translation.call_count == 2
        
        # Should log error for failed French translation
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if "Failed to translate tweet" in str(call) and "French" in str(call)]
        assert len(error_calls) > 0

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    @patch('main.time.sleep')
    def test_process_new_tweets_multiple_tweets(self, mock_sleep, mock_structured_logger,
                                               mock_cache_monitor, mock_draft_manager,
                                               mock_publisher, mock_translator, mock_monitor,
                                               mock_settings, bot, language_configs):
        """Test processing multiple tweets"""
        # Create multiple test tweets
        tweets = []
        for i in range(3):
            tweets.append(Tweet(
                id=f"12345678{i}",
                text=f"Test tweet {i} #test",
                created_at=datetime(2024, 1, 1, 12, i, 0),
                author_username="testuser",
                author_id="987654321",
                public_metrics={}
            ))
        
        mock_monitor.get_new_tweets.return_value = tweets
        mock_settings.TARGET_LANGUAGES = language_configs[:1]  # Just one language
        
        # Mock successful translation for all tweets
        def mock_translate(tweet, lang, config):
            return Translation(
                original_tweet=tweet,
                target_language=lang,
                translated_text=f"Translation of {tweet.text}",
                translation_timestamp=datetime.now(),
                character_count=len(tweet.text),
                status="pending"
            )
        
        mock_translator.translate_tweet.side_effect = mock_translate
        mock_publisher.can_post.return_value = True
        mock_publisher.post_translation.return_value = True
        
        bot.process_new_tweets()
        
        # Should process all tweets
        assert mock_translator.translate_tweet.call_count == 3
        assert mock_publisher.post_translation.call_count == 3
        
        # Should have delays between tweets
        assert mock_sleep.call_count == 3  # One delay per tweet

    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.cache_monitor')
    @patch('main.structured_logger')
    def test_process_new_tweets_tweet_processing_exception(self, mock_structured_logger,
                                                          mock_cache_monitor, mock_monitor,
                                                          mock_settings, bot, sample_tweet):
        """Test handling exception during individual tweet processing"""
        mock_monitor.get_new_tweets.return_value = [sample_tweet]
        mock_settings.TARGET_LANGUAGES = [{"code": "es", "name": "Spanish"}]
        
        # Mock structured logger to raise exception
        mock_structured_logger.log_tweet_processing.side_effect = Exception("Logging error")
        
        with patch('main.logger') as mock_logger:
            bot.process_new_tweets()
        
        # Should log error for tweet processing
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if "Error processing tweet" in str(call)]
        assert len(error_calls) > 0

    def test_circuit_breaker_integration(self, bot):
        """Test that circuit breaker manager is properly integrated"""
        # Verify circuit breaker manager is imported and available
        from main import circuit_breaker_manager
        assert circuit_breaker_manager is not None

    def test_error_recovery_integration(self, bot):
        """Test that error recovery is properly integrated"""
        # Verify error recovery is imported and available
        from main import recover_from_error
        assert recover_from_error is not None

    def test_structured_logging_integration(self, bot):
        """Test that structured logging is properly integrated"""
        # Verify structured logger is imported and available
        from main import structured_logger
        assert structured_logger is not None

    def test_cache_monitoring_integration(self, bot):
        """Test that cache monitoring is properly integrated"""
        # Verify cache monitor is imported and available
        from main import cache_monitor
        assert cache_monitor is not None
