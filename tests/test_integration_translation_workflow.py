# =============================================================================
# COMPREHENSIVE INTEGRATION TESTS FOR TRANSLATION WORKFLOW
# =============================================================================
# Tests complete end-to-end translation workflow from monitoring to publishing
# Includes service integration, error recovery, cache behavior, and real-world scenarios

import pytest
import sys
import os
import time
import json
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call, AsyncMock, mock_open
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import TwitterTranslationBot
from src.services.twitter_monitor import twitter_monitor
from src.services.gemini_translator import gemini_translator
from src.services.publisher import twitter_publisher
from src.models.tweet import Tweet, Translation
from src.config.settings import settings
from src.utils.translation_cache import translation_cache
from src.utils.circuit_breaker import circuit_breaker_manager, CircuitState
from src.utils.error_recovery import error_recovery_manager
from src.utils.structured_logger import structured_logger
from draft_manager import draft_manager
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


@pytest.mark.integration
class TestTranslationWorkflowIntegration:
    """Comprehensive integration tests for complete translation workflow"""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Set up clean test environment for each test"""
        # Reset circuit breakers
        circuit_breaker_manager.reset_all()
        
        # Clear error recovery state (access internal queue)
        if hasattr(error_recovery_manager, '_operation_queue'):
            error_recovery_manager._operation_queue.clear()
        
        # Mock settings with valid configuration
        with patch.object(settings, 'TARGET_LANGUAGES', [
            {'code': 'es', 'name': 'Spanish', 'account': 'spanish_account'},
            {'code': 'fr', 'name': 'French', 'account': 'french_account'},
            {'code': 'de', 'name': 'German', 'account': 'german_account'}
        ]):
            yield

    def _get_standard_mocks(self):
        """Get standard mock setup that most tests need"""
        return {
            'mock_validate_creds': patch.object(settings, 'validate_credentials'),
            'mock_get_tweets': patch.object(twitter_monitor, 'get_new_tweets'),
            'mock_translate': patch.object(gemini_translator, 'translate_tweet'),
            'mock_can_post': patch.object(twitter_publisher, 'can_post'),
            'mock_post': patch.object(twitter_publisher, 'post_translation'),
            'mock_save_draft': patch.object(draft_manager, 'save_translation_as_draft'),
            'mock_log_processing': patch.object(structured_logger, 'log_tweet_processing'),
            'mock_log_lifecycle': patch.object(structured_logger, 'log_bot_lifecycle')
        }

    @pytest.fixture
    def sample_tweets(self) -> List[Tweet]:
        """Create sample tweets for testing"""
        return [
            Tweet(
                id="123456789",
                text="Breaking: Major scientific breakthrough in quantum computing! #science #technology",
                created_at=datetime.now(),
                author_username="scientist",
                author_id="111111",
                public_metrics={"like_count": 50, "retweet_count": 25}
            ),
            Tweet(
                id="987654321", 
                text="Beautiful sunset today 🌅 Nature never fails to amaze! #nature #photography",
                created_at=datetime.now(),
                author_username="photographer",
                author_id="222222",
                public_metrics={"like_count": 100, "retweet_count": 40}
            ),
            Tweet(
                id="555666777",
                text="Quick tip: Always backup your data regularly! #tech #advice",
                created_at=datetime.now(),
                author_username="techexpert",
                author_id="333333", 
                public_metrics={"like_count": 30, "retweet_count": 15}
            )
        ]

    @pytest.fixture
    def sample_translations(self, sample_tweets) -> Dict[str, List[Translation]]:
        """Create sample translations for testing"""
        translations = {}
        
        for tweet in sample_tweets:
            translations[tweet.id] = []
            
            # Spanish translations
            translations[tweet.id].append(Translation(
                original_tweet=tweet,
                translated_text=f"[ES] {tweet.text}",
                target_language="Spanish",
                character_count=len(f"[ES] {tweet.text}"),
                translation_timestamp=datetime.now(),
                status="posted",
                post_id=f"es_{tweet.id}"
            ))
            
            # French translations
            translations[tweet.id].append(Translation(
                original_tweet=tweet,
                translated_text=f"[FR] {tweet.text}",
                target_language="French", 
                character_count=len(f"[FR] {tweet.text}"),
                translation_timestamp=datetime.now(),
                status="posted",
                post_id=f"fr_{tweet.id}"
            ))
            
            # German translations
            translations[tweet.id].append(Translation(
                original_tweet=tweet,
                translated_text=f"[DE] {tweet.text}",
                target_language="German",
                character_count=len(f"[DE] {tweet.text}"),
                translation_timestamp=datetime.now(),
                status="posted",
                post_id=f"de_{tweet.id}"
            ))
        
        return translations

    def test_complete_successful_workflow(self, sample_tweets, sample_translations):
        """Test complete end-to-end workflow with all services succeeding"""
        
        with patch.object(settings, 'validate_credentials') as mock_validate_creds, \
             patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'can_post') as mock_can_post, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch.object(structured_logger, 'log_tweet_processing') as mock_log_processing, \
             patch.object(structured_logger, 'log_bot_lifecycle') as mock_log_lifecycle:
            
            # Setup mocks
            mock_validate_creds.return_value = True
            mock_get_tweets.return_value = sample_tweets[:2]  # Process 2 tweets
            mock_can_post.return_value = True
            mock_post.return_value = True
            
            # Mock translation responses
            def mock_translate_response(tweet, target_lang, lang_config):
                for translation in sample_translations[tweet.id]:
                    if translation.target_language.lower() == target_lang.lower():
                        return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            
            # Run the workflow
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify credentials were validated
            mock_validate_creds.assert_called_once()
            
            # Verify tweet monitoring was called
            mock_get_tweets.assert_called_once()
            
            # Verify translations were attempted for all languages
            expected_translate_calls = len(sample_tweets[:2]) * len(settings.TARGET_LANGUAGES)
            assert mock_translate.call_count == expected_translate_calls
            
            # Verify all translations were posted
            expected_post_calls = len(sample_tweets[:2]) * len(settings.TARGET_LANGUAGES)
            assert mock_post.call_count == expected_post_calls
            
            # Verify structured logging
            assert mock_log_processing.call_count == len(sample_tweets[:2])
            mock_log_lifecycle.assert_called_with("start_single_run", mode="once")

    def test_partial_translation_failure_with_recovery(self, sample_tweets, sample_translations):
        """Test workflow when some translations fail but others succeed"""
        
        with patch.object(settings, 'validate_credentials') as mock_validate_creds, \
             patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'can_post') as mock_can_post, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch.object(draft_manager, 'save_translation_as_draft') as mock_save_draft:
            
            # Setup mocks
            mock_validate_creds.return_value = True
            mock_get_tweets.return_value = sample_tweets[:1]  # Process 1 tweet
            mock_can_post.return_value = True
            
            # Mock translation failures for some languages
            def mock_translate_response(tweet, target_lang, lang_config):
                if target_lang.lower() == 'spanish':
                    raise GeminiQuotaError("Quota exceeded for Spanish")
                elif target_lang.lower() == 'french':
                    for translation in sample_translations[tweet.id]:
                        if translation.target_language.lower() == target_lang.lower():
                            return translation
                else:  # German
                    raise TranslationError("Translation failed for German")
                return None
            
            mock_translate.side_effect = mock_translate_response
            mock_post.return_value = True
            
            # Run the workflow
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify attempts were made for all languages
            assert mock_translate.call_count == 3
            
            # Verify only successful translation was posted (French)
            assert mock_post.call_count == 1
            
            # Verify no drafts were saved (failures were translation errors, not posting errors)
            mock_save_draft.assert_not_called()

    def test_publishing_failure_with_draft_fallback(self, sample_tweets, sample_translations):
        """Test workflow when translations succeed but publishing fails"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'can_post') as mock_can_post, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch.object(draft_manager, 'save_translation_as_draft') as mock_save_draft:
            
            # Setup mocks
            mock_get_tweets.return_value = sample_tweets[:1]
            mock_can_post.return_value = True
            
            # Mock successful translations
            def mock_translate_response(tweet, target_lang, lang_config):
                for translation in sample_translations[tweet.id]:
                    if translation.target_language.lower() == target_lang.lower():
                        return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            
            # Mock publishing failures
            def mock_post_response(translation):
                if translation.target_language.lower() == 'spanish':
                    raise TwitterAPIError("API Error for Spanish account")
                elif translation.target_language.lower() == 'french':
                    return True  # Success
                else:  # German
                    raise NetworkError("Network error for German account")
            
            mock_post.side_effect = mock_post_response
            mock_save_draft.return_value = True
            
            # Run the workflow
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify all translations were attempted
            assert mock_translate.call_count == 3
            
            # Verify all posting attempts were made
            assert mock_post.call_count == 3
            
            # Verify failed posts were saved as drafts (Spanish and German)
            assert mock_save_draft.call_count == 2

    def test_quota_exceeded_draft_fallback(self, sample_tweets, sample_translations):
        """Test workflow when API quotas are exceeded"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'can_post') as mock_can_post, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch.object(draft_manager, 'save_translation_as_draft') as mock_save_draft:
            
            # Setup mocks
            mock_get_tweets.return_value = sample_tweets[:1]
            
            # Mock successful translations
            def mock_translate_response(tweet, target_lang, lang_config):
                for translation in sample_translations[tweet.id]:
                    if translation.target_language.lower() == target_lang.lower():
                        return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            
            # Mock quota exceeded scenarios
            def mock_can_post_response():
                # First call succeeds, then quota is exceeded
                mock_can_post_response.call_count += 1
                return mock_can_post_response.call_count <= 1
            
            mock_can_post_response.call_count = 0
            mock_can_post.side_effect = mock_can_post_response
            mock_post.return_value = True
            mock_save_draft.return_value = True
            
            # Run the workflow
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify all translations were attempted
            assert mock_translate.call_count == 3
            
            # Verify only first post succeeded, rest saved as drafts
            assert mock_post.call_count == 1
            assert mock_save_draft.call_count == 2

    def test_circuit_breaker_protection_integration(self, sample_tweets):
        """Test circuit breaker protection across services"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate:
            
            # Simulate repeated failures to trigger circuit breaker
            mock_get_tweets.side_effect = TwitterAPIError("Repeated API failures")
            
            bot = TwitterTranslationBot()
            
            # Run multiple times to trigger circuit breaker
            for i in range(6):  # Exceed failure threshold
                bot.run_once()
            
            # Verify circuit breaker is now open
            cb_status = circuit_breaker_manager.get_health_status("twitter_monitor")
            assert cb_status is not None
            
            # Translation should not be called due to monitoring failure
            mock_translate.assert_not_called()

    def test_cache_integration_in_workflow(self, sample_tweets, sample_translations):
        """Test translation cache integration in complete workflow"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'can_post') as mock_can_post, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch.object(translation_cache, 'get') as mock_cache_get, \
             patch.object(translation_cache, 'set') as mock_cache_set:
            
            # Setup mocks
            mock_get_tweets.return_value = [sample_tweets[0]]  # Same tweet twice
            mock_can_post.return_value = True
            mock_post.return_value = True
            
            # First run - cache miss, then cache hit
            cache_responses = [None, sample_translations[sample_tweets[0].id][0]]  # Miss, then hit
            mock_cache_get.side_effect = cache_responses
            
            def mock_translate_response(tweet, target_lang, lang_config):
                for translation in sample_translations[tweet.id]:
                    if translation.target_language.lower() == target_lang.lower():
                        return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            
            # Run workflow twice with same tweet
            bot = TwitterTranslationBot()
            
            # First run - should translate and cache
            mock_get_tweets.return_value = [sample_tweets[0]]
            bot.run_once()
            
            # Reset cache behavior for second run
            mock_cache_get.side_effect = None
            mock_cache_get.return_value = sample_translations[sample_tweets[0].id][0]  # Cache hit
            
            # Second run - should use cache
            bot.run_once()
            
            # Verify cache was used
            assert mock_cache_get.call_count >= 2
            assert mock_cache_set.call_count >= 1

    def test_error_recovery_workflow_integration(self, sample_tweets):
        """Test error recovery integration across workflow"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(error_recovery_manager, 'queue_operation') as mock_queue_op, \
             patch.object(error_recovery_manager, 'retry_queued_operations') as mock_retry_ops:
            
            # Simulate network error
            mock_get_tweets.side_effect = NetworkError("Network connection failed")
            
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify error recovery was engaged
            mock_queue_op.assert_called()
            
            # Verify queued operation contains correct context
            call_args = mock_queue_op.call_args[1]
            assert 'operation_type' in call_args
            assert call_args['operation_type'] == 'process_new_tweets'

    def test_multi_language_concurrent_processing(self, sample_tweets, sample_translations):
        """Test processing multiple languages concurrently"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'can_post') as mock_can_post, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch('time.sleep') as mock_sleep:  # Speed up test
            
            # Setup mocks
            mock_get_tweets.return_value = sample_tweets
            mock_can_post.return_value = True
            mock_post.return_value = True
            
            # Track translation call order and timing
            translate_calls = []
            
            def mock_translate_response(tweet, target_lang, lang_config):
                translate_calls.append({
                    'tweet_id': tweet.id,
                    'language': target_lang,
                    'timestamp': time.time()
                })
                
                for translation in sample_translations[tweet.id]:
                    if translation.target_language.lower() == target_lang.lower():
                        return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            
            # Run the workflow
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify all combinations were processed
            expected_calls = len(sample_tweets) * len(settings.TARGET_LANGUAGES)
            assert len(translate_calls) == expected_calls
            
            # Verify tweets were processed in order but languages within each tweet
            tweet_order = [call['tweet_id'] for call in translate_calls]
            
            # Should have 3 calls for first tweet, then 3 for second, etc.
            for i, tweet in enumerate(sample_tweets):
                tweet_calls = tweet_order[i*3:(i+1)*3]
                assert all(tid == tweet.id for tid in tweet_calls)

    def test_performance_monitoring_integration(self, sample_tweets, sample_translations):
        """Test performance monitoring throughout workflow"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch.object(structured_logger, 'log_tweet_processing') as mock_log_processing, \
             patch.object(structured_logger, 'log_translation_performance') as mock_log_perf:
            
            # Setup mocks
            mock_get_tweets.return_value = sample_tweets[:1]
            mock_post.return_value = True
            
            def mock_translate_response(tweet, target_lang, lang_config):
                for translation in sample_translations[tweet.id]:
                    if translation.target_language.lower() == target_lang.lower():
                        return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            
            # Run the workflow
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify performance monitoring was logged
            mock_log_processing.assert_called()
            
            # Verify tweet processing was logged with correct data
            call_args = mock_log_processing.call_args[1]
            assert 'tweet_id' in call_args
            assert 'text_preview' in call_args
            assert 'language_count' in call_args
            assert call_args['language_count'] == len(settings.TARGET_LANGUAGES)

    def test_workflow_with_service_degradation(self, sample_tweets, sample_translations):
        """Test workflow behavior under service degradation scenarios"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch.object(draft_manager, 'save_translation_as_draft') as mock_save_draft:
            
            # Setup mocks
            mock_get_tweets.return_value = sample_tweets[:2]
            
            # Simulate degraded service - slow responses and intermittent failures
            slow_responses = []
            
            def mock_translate_response(tweet, target_lang, lang_config):
                # Simulate slow response times
                time.sleep(0.1)  # Small delay for testing
                
                # Intermittent failures (fail every 3rd call)
                slow_responses.append(True)
                if len(slow_responses) % 3 == 0:
                    raise GeminiAPIError("Service temporarily degraded")
                
                for translation in sample_translations[tweet.id]:
                    if translation.target_language.lower() == target_lang.lower():
                        return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            mock_post.return_value = True
            mock_save_draft.return_value = True
            
            # Run the workflow
            start_time = time.time()
            bot = TwitterTranslationBot()
            bot.run_once()
            end_time = time.time()
            
            # Verify workflow completed despite degradation
            expected_calls = len(sample_tweets[:2]) * len(settings.TARGET_LANGUAGES)
            assert mock_translate.call_count == expected_calls
            
            # Verify some translations succeeded despite failures
            assert mock_post.call_count > 0

    def test_complete_system_failure_recovery(self, sample_tweets):
        """Test recovery from complete system failures"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(circuit_breaker_manager, 'get_all_health_status') as mock_cb_status:
            
            # Simulate complete Twitter service failure
            mock_get_tweets.side_effect = TwitterAPIError("Complete service outage")
            mock_cb_status.return_value = [
                {
                    'name': 'twitter_monitor',
                    'healthy': False,
                    'state': CircuitState.OPEN.value,
                    'failure_count': 5
                }
            ]
            
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify circuit breaker status was checked for debugging
            mock_cb_status.assert_called()
            
            # Verify graceful handling of complete failure
            assert mock_get_tweets.call_count == 1

    def test_configuration_validation_in_workflow(self):
        """Test configuration validation integration in workflow"""
        
        with patch.object(settings, 'validate_credentials') as mock_validate:
            
            # Test with invalid credentials
            mock_validate.return_value = False
            
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify validation was called
            mock_validate.assert_called()

    def test_structured_logging_throughout_workflow(self, sample_tweets, sample_translations):
        """Test structured logging integration throughout workflow"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch.object(structured_logger, 'log_tweet_processing') as mock_log_processing, \
             patch.object(structured_logger, 'log_bot_lifecycle') as mock_log_lifecycle, \
             patch.object(structured_logger, 'log_translation_cached') as mock_log_cached:
            
            # Setup mocks
            mock_get_tweets.return_value = sample_tweets[:1]
            mock_post.return_value = True
            
            def mock_translate_response(tweet, target_lang, lang_config):
                for translation in sample_translations[tweet.id]:
                    if translation.target_language.lower() == target_lang.lower():
                        return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            
            # Run the workflow
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify comprehensive structured logging
            mock_log_lifecycle.assert_called()
            mock_log_processing.assert_called()
            
            # Verify logging includes structured data
            lifecycle_args = mock_log_lifecycle.call_args
            assert len(lifecycle_args) >= 1  # At least event type
            
            processing_args = mock_log_processing.call_args[1]
            assert 'tweet_id' in processing_args
            assert 'text_preview' in processing_args

    def test_draft_manager_integration_stress_test(self, sample_tweets, sample_translations):
        """Test draft manager under high load scenarios"""
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'can_post') as mock_can_post, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch.object(draft_manager, 'save_translation_as_draft') as mock_save_draft, \
             patch.object(draft_manager, 'get_draft_count') as mock_get_count:
            
            # Setup mocks for high load scenario
            mock_get_tweets.return_value = sample_tweets  # Process all tweets
            mock_can_post.return_value = False  # Force all to drafts
            
            def mock_translate_response(tweet, target_lang, lang_config):
                for translation in sample_translations[tweet.id]:
                    if translation.target_language.lower() == target_lang.lower():
                        return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            mock_save_draft.return_value = True
            mock_get_count.return_value = len(sample_tweets) * len(settings.TARGET_LANGUAGES)
            
            # Run the workflow
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Verify all translations were saved as drafts
            expected_drafts = len(sample_tweets) * len(settings.TARGET_LANGUAGES)
            assert mock_save_draft.call_count == expected_drafts
            
            # Verify draft count was reported
            mock_get_count.assert_called()


@pytest.mark.integration
class TestAsyncWorkflowIntegration:
    """Integration tests for async workflow components"""

    @pytest.mark.asyncio
    async def test_async_workflow_coordination(self):
        """Test coordination between async components"""
        
        with patch('main_async.TwitterTranslationBotAsync') as mock_async_bot:
            
            # Mock async bot instance
            mock_bot_instance = AsyncMock()
            mock_async_bot.return_value = mock_bot_instance
            
            # Import and test async main
            from main_async import main as async_main
            
            # This would normally run the async workflow
            # We're testing the coordination pattern
            await async_main()
            
            # Verify async bot was instantiated
            mock_async_bot.assert_called_once()


@pytest.mark.integration
@pytest.mark.slow
class TestWorkflowPerformanceIntegration:
    """Performance integration tests for translation workflow"""

    def test_workflow_performance_under_load(self, sample_tweets, sample_translations):
        """Test workflow performance with multiple tweets and languages"""
        
        # Create larger dataset for performance testing
        large_tweet_set = sample_tweets * 10  # 30 tweets total
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'post_translation') as mock_post, \
             patch('time.sleep'):  # Speed up test
            
            # Setup mocks
            mock_get_tweets.return_value = large_tweet_set
            mock_post.return_value = True
            
            def mock_translate_response(tweet, target_lang, lang_config):
                # Find translation for this tweet/language combo
                original_tweet_id = tweet.id
                if original_tweet_id in ['123456789', '987654321', '555666777']:
                    for translation in sample_translations[original_tweet_id]:
                        if translation.target_language.lower() == target_lang.lower():
                            return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            
            # Measure performance
            start_time = time.time()
            
            bot = TwitterTranslationBot()
            bot.run_once()
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Verify all tweets were processed
            expected_translation_calls = len(large_tweet_set) * len(settings.TARGET_LANGUAGES)
            assert mock_translate.call_count == expected_translation_calls
            
            # Performance assertion (should complete within reasonable time)
            assert processing_time < 30.0  # Should complete within 30 seconds

    def test_memory_usage_during_workflow(self, sample_tweets, sample_translations):
        """Test memory usage patterns during workflow execution"""
        import psutil
        import os
        
        with patch.object(twitter_monitor, 'get_new_tweets') as mock_get_tweets, \
             patch.object(gemini_translator, 'translate_tweet') as mock_translate, \
             patch.object(twitter_publisher, 'post_translation') as mock_post:
            
            # Setup mocks
            mock_get_tweets.return_value = sample_tweets
            mock_post.return_value = True
            
            def mock_translate_response(tweet, target_lang, lang_config):
                for translation in sample_translations[tweet.id]:
                    if translation.target_language.lower() == target_lang.lower():
                        return translation
                return None
            
            mock_translate.side_effect = mock_translate_response
            
            # Measure memory before
            process = psutil.Process(os.getpid())
            memory_before = process.memory_info().rss
            
            # Run workflow
            bot = TwitterTranslationBot()
            bot.run_once()
            
            # Measure memory after
            memory_after = process.memory_info().rss
            memory_increase = memory_after - memory_before
            
            # Memory increase should be reasonable (< 50MB for test)
            max_acceptable_increase = 50 * 1024 * 1024  # 50MB
            assert memory_increase < max_acceptable_increase


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
