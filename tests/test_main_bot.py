# =============================================================================
# MAIN BOT LOGIC TESTS
# =============================================================================

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import patch, MagicMock, call
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import TwitterTranslationBot, main

class TestTwitterTranslationBot:
    def setup_method(self):
        """Set up test fixtures"""
        self.bot = TwitterTranslationBot()
    
    def test_bot_initialization(self):
        """Test bot initialization"""
        bot = TwitterTranslationBot()
        assert hasattr(bot, 'running')
        assert bot.running == False
    
    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    def test_process_new_tweets_no_tweets(self, mock_cache_monitor, mock_draft_manager, 
                                         mock_publisher, mock_translator, mock_monitor, mock_settings):
        """Test processing when no new tweets are found"""
        # Mock dependencies
        mock_monitor.get_new_tweets.return_value = []
        mock_settings.TARGET_LANGUAGES = []
        
        self.bot.process_new_tweets()
        
        # Should check for tweets and log cache stats
        mock_cache_monitor.log_cache_stats_periodically.assert_called_once()
        mock_monitor.get_new_tweets.assert_called_once()
        
        # Should not call translator or publisher
        mock_translator.translate_tweet.assert_not_called()
        mock_publisher.post_translation.assert_not_called()
    
    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.logger')
    def test_process_new_tweets_with_tweets_success(self, mock_logger, mock_cache_monitor, 
                                                   mock_draft_manager, mock_publisher, 
                                                   mock_translator, mock_monitor, mock_settings):
        """Test processing tweets with successful translation and posting"""
        from src.models.tweet import Tweet, Translation
        
        # Create test tweet
        test_tweet = Tweet(
            id="123456789",
            text="Hello world! #test",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={}
        )
        
        # Create test translation
        test_translation = Translation(
            original_tweet=test_tweet,
            target_language="Spanish",
            translated_text="¡Hola mundo! #test",
            translation_timestamp=datetime.now(),
            character_count=18,
            status="pending"
        )
        
        # Mock dependencies
        mock_monitor.get_new_tweets.return_value = [test_tweet]
        mock_settings.TARGET_LANGUAGES = [
            {"code": "es", "name": "Spanish", "formal_tone": False}
        ]
        mock_translator.translate_tweet.return_value = test_translation
        mock_publisher.post_translation.return_value = True
        
        self.bot.process_new_tweets()
        
        # Should process the tweet
        mock_monitor.get_new_tweets.assert_called_once()
        mock_translator.translate_tweet.assert_called_once_with(
            test_tweet,
            "Spanish",
            {"code": "es", "name": "Spanish", "formal_tone": False}
        )
        mock_publisher.post_translation.assert_called_once_with(test_translation)
        
        # Should not save as draft (posting was successful)
        mock_draft_manager.save_translation_as_draft.assert_not_called()
    
    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    @patch('main.logger')
    def test_process_new_tweets_translation_failure(self, mock_logger, mock_cache_monitor,
                                                   mock_draft_manager, mock_publisher,
                                                   mock_translator, mock_monitor, mock_settings):
        """Test processing tweets when translation fails"""
        from src.models.tweet import Tweet
        
        test_tweet = Tweet(
            id="123456789",
            text="Hello world! #test",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={}
        )
        
        # Mock translation failure
        mock_monitor.get_new_tweets.return_value = [test_tweet]
        mock_settings.TARGET_LANGUAGES = [{"code": "es", "name": "Spanish"}]
        mock_translator.translate_tweet.return_value = None  # Translation failed
        
        self.bot.process_new_tweets()
        
        # Should attempt translation but not proceed to publishing
        mock_translator.translate_tweet.assert_called_once()
        mock_publisher.post_translation.assert_not_called()
        mock_draft_manager.save_translation_as_draft.assert_not_called()
    
    @patch('main.settings')
    @patch('main.twitter_monitor') 
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    def test_process_new_tweets_posting_failure_saves_draft(self, mock_cache_monitor,
                                                           mock_draft_manager, mock_publisher,
                                                           mock_translator, mock_monitor, mock_settings):
        """Test that failed posts are saved as drafts"""
        from src.models.tweet import Tweet, Translation
        
        test_tweet = Tweet(
            id="123456789",
            text="Hello world! #test",
            created_at=datetime.now(),
            author_username="testuser", 
            author_id="987654321",
            public_metrics={}
        )
        
        test_translation = Translation(
            original_tweet=test_tweet,
            target_language="Spanish",
            translated_text="¡Hola mundo! #test",
            translation_timestamp=datetime.now(),
            character_count=18,
            status="pending"
        )
        
        lang_config = {"code": "es", "name": "Spanish"}
        
        # Mock posting failure
        mock_monitor.get_new_tweets.return_value = [test_tweet]
        mock_settings.TARGET_LANGUAGES = [lang_config]
        mock_translator.translate_tweet.return_value = test_translation
        mock_publisher.post_translation.return_value = False  # Posting failed
        
        self.bot.process_new_tweets()
        
        # Should save as draft when posting fails
        mock_draft_manager.save_translation_as_draft.assert_called_once_with(
            test_translation, lang_config
        )
    
    @patch('main.settings')
    @patch('main.twitter_monitor')
    @patch('main.gemini_translator')
    @patch('main.twitter_publisher')
    @patch('main.draft_manager')
    @patch('main.cache_monitor')
    def test_process_new_tweets_multiple_languages(self, mock_cache_monitor, mock_draft_manager,
                                                  mock_publisher, mock_translator, mock_monitor, mock_settings):
        """Test processing tweet for multiple target languages"""
        from src.models.tweet import Tweet, Translation
        
        test_tweet = Tweet(
            id="123456789",
            text="Hello world!",
            created_at=datetime.now(),
            author_username="testuser",
            author_id="987654321",
            public_metrics={}
        )
        
        # Mock multiple target languages
        mock_monitor.get_new_tweets.return_value = [test_tweet]
        mock_settings.TARGET_LANGUAGES = [
            {"code": "es", "name": "Spanish"},
            {"code": "fr", "name": "French"},
            {"code": "de", "name": "German"}
        ]
        
        # Mock successful translations for all languages
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
        mock_publisher.post_translation.return_value = True
        
        self.bot.process_new_tweets()
        
        # Should translate to all three languages
        assert mock_translator.translate_tweet.call_count == 3
        assert mock_publisher.post_translation.call_count == 3
        
        # Check that all languages were processed
        calls = mock_translator.translate_tweet.call_args_list
        languages_processed = [call[0][1] for call in calls]  # Second argument is language
        assert "Spanish" in languages_processed
        assert "French" in languages_processed
        assert "German" in languages_processed
    
    @patch('main.settings')
    @patch('main.logger')
    def test_process_new_tweets_exception_handling(self, mock_logger, mock_settings):
        """Test that exceptions in process_new_tweets are handled gracefully"""
        # Mock an exception during processing
        with patch('main.twitter_monitor') as mock_monitor:
            mock_monitor.get_new_tweets.side_effect = Exception("API Error")
            
            # Should not raise exception, should log error
            self.bot.process_new_tweets()
            
            # Should log the error
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0][0]
            assert "Error in process_new_tweets" in error_call
            assert "API Error" in error_call
    
    @patch('main.settings')
    def test_run_once_validates_credentials(self, mock_settings):
        """Test that run_once validates credentials before processing"""
        mock_settings.validate_credentials.return_value = False
        
        with patch.object(self.bot, 'process_new_tweets') as mock_process:
            with patch('main.logger') as mock_logger:
                self.bot.run_once()
                
                # Should not process tweets if credentials invalid
                mock_process.assert_not_called()
                mock_logger.error.assert_called()
    
    @patch('main.settings')
    @patch('main.draft_manager')
    def test_run_once_shows_draft_status(self, mock_draft_manager, mock_settings):
        """Test that run_once shows draft status after processing"""
        mock_settings.validate_credentials.return_value = True
        mock_draft_manager.get_draft_count.return_value = 5
        
        with patch.object(self.bot, 'process_new_tweets'):
            with patch('main.logger') as mock_logger:
                self.bot.run_once()
                
                # Should log draft count
                mock_logger.info.assert_called()
                info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                assert any("5" in call and "drafts" in call for call in info_calls)
    
    @patch('main.settings')
    @patch('main.schedule')
    @patch('main.time')
    def test_run_scheduled_starts_and_stops(self, mock_time, mock_schedule, mock_settings):
        """Test that run_scheduled starts and can be stopped"""
        mock_settings.validate_credentials.return_value = True
        mock_settings.POLL_INTERVAL = 300
        
        # Mock schedule behavior
        mock_schedule.run_pending = MagicMock()
        
        # Simulate stopping after a few iterations
        iteration_count = 0
        def mock_sleep(duration):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 3:  # Stop after 3 iterations
                self.bot.running = False
        
        mock_time.sleep.side_effect = mock_sleep
        
        self.bot.run_scheduled()
        
        # Should have set up the schedule
        mock_schedule.every.assert_called_with(300)
        
        # Should have run the loop
        assert mock_schedule.run_pending.call_count >= 3
        assert mock_time.sleep.call_count >= 3
    
    @patch('main.settings')
    def test_run_scheduled_handles_keyboard_interrupt(self, mock_settings):
        """Test that run_scheduled handles KeyboardInterrupt gracefully"""
        mock_settings.validate_credentials.return_value = True
        
        with patch('main.schedule') as mock_schedule:
            with patch('main.time') as mock_time:
                with patch('main.logger') as mock_logger:
                    # Simulate KeyboardInterrupt
                    mock_time.sleep.side_effect = KeyboardInterrupt()
                    
                    self.bot.run_scheduled()
                    
                    # Should log stop message and set running to False
                    assert self.bot.running == False
                    mock_logger.info.assert_called()
    
    def test_stop_method(self):
        """Test bot stop method"""
        self.bot.running = True
        self.bot.stop()
        assert self.bot.running == False

class TestMainFunction:
    @patch('main.sys.argv', ['main.py', 'once'])
    @patch('main.TwitterTranslationBot')
    def test_main_once_command(self, mock_bot_class):
        """Test main function with 'once' command"""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        main()
        
        mock_bot.run_once.assert_called_once()
        mock_bot.run_scheduled.assert_not_called()
    
    @patch('main.sys.argv', ['main.py', 'drafts'])
    @patch('main.draft_manager')
    def test_main_drafts_command(self, mock_draft_manager):
        """Test main function with 'drafts' command"""
        main()
        mock_draft_manager.display_pending_drafts.assert_called_once()
    
    @patch('main.sys.argv', ['main.py', 'status'])
    @patch('main.twitter_monitor')
    @patch('main.settings')
    @patch('main.draft_manager')
    @patch('builtins.print')
    def test_main_status_command(self, mock_print, mock_draft_manager, mock_settings, mock_monitor):
        """Test main function with 'status' command"""
        mock_monitor.daily_requests = 25
        mock_monitor.monthly_posts = 150
        mock_settings.TWITTER_FREE_DAILY_LIMIT = 50
        mock_settings.TWITTER_FREE_MONTHLY_LIMIT = 1500
        mock_draft_manager.get_draft_count.return_value = 3
        
        main()
        
        # Should print status information
        mock_print.assert_called()
        print_calls = [str(call[0][0]) for call in mock_print.call_args_list]
        status_text = ' '.join(print_calls)
        
        assert "25/50" in status_text
        assert "150/1500" in status_text
        assert "3" in status_text
    
    @patch('main.sys.argv', ['main.py', 'cache'])
    @patch('main.cache_monitor')
    def test_main_cache_command(self, mock_cache_monitor):
        """Test main function with 'cache' command"""
        main()
        mock_cache_monitor.print_performance_summary.assert_called_once()
    
    @patch('main.sys.argv', ['main.py', 'test'])
    @patch('main.settings')
    @patch('main.twitter_publisher')
    @patch('main.logger')
    def test_main_test_command_with_valid_credentials(self, mock_logger, mock_publisher, mock_settings):
        """Test main function with 'test' command and valid credentials"""
        mock_settings.validate_credentials.return_value = True
        
        main()
        
        mock_publisher.test_connections.assert_called_once()
    
    @patch('main.sys.argv', ['main.py', 'test'])
    @patch('main.settings')
    @patch('main.twitter_publisher')
    @patch('main.logger')
    def test_main_test_command_with_invalid_credentials(self, mock_logger, mock_publisher, mock_settings):
        """Test main function with 'test' command and invalid credentials"""
        mock_settings.validate_credentials.return_value = False
        
        main()
        
        mock_publisher.test_connections.assert_not_called()
        mock_logger.error.assert_called()
    
    @patch('main.sys.argv', ['main.py', 'invalid'])
    @patch('builtins.print')
    def test_main_invalid_command(self, mock_print):
        """Test main function with invalid command"""
        main()
        
        # Should print usage information
        mock_print.assert_called()
        print_calls = [str(call[0][0]) for call in mock_print.call_args_list]
        usage_text = ' '.join(print_calls)
        
        assert "Usage:" in usage_text
        assert "once" in usage_text
        assert "drafts" in usage_text
        assert "status" in usage_text
        assert "cache" in usage_text
        assert "test" in usage_text
    
    @patch('main.sys.argv', ['main.py'])
    @patch('main.TwitterTranslationBot')
    def test_main_no_args_runs_scheduled(self, mock_bot_class):
        """Test main function with no arguments runs in scheduled mode"""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        main()
        
        mock_bot.run_scheduled.assert_called_once()
        mock_bot.run_once.assert_not_called()
    
    @patch('main.sys.argv', ['main.py', 'once'])
    @patch('main.TwitterTranslationBot')
    @patch('main.logger')
    def test_main_logs_cache_integration(self, mock_logger, mock_bot_class):
        """Test that main function includes cache monitoring integration"""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        
        # Verify that cache monitoring is imported and available
        from main import cache_monitor
        assert cache_monitor is not None
        
        main()
        
        # Bot should have been created and run
        mock_bot.run_once.assert_called_once()
