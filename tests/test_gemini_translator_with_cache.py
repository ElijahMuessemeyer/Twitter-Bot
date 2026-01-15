# =============================================================================
# GEMINI TRANSLATOR WITH CACHE INTEGRATION TESTS
# =============================================================================

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import patch, MagicMock, Mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.gemini_translator import GeminiTranslator, gemini_translator
from src.models.tweet import Tweet, Translation
from src.utils.translation_cache import IntelligentTranslationCache

class TestGeminiTranslatorWithCache:
    def setup_method(self):
        """Set up test fixtures"""
        # Clear global cache before each test
        from src.utils.translation_cache import translation_cache
        translation_cache.clear()
        self.test_tweet = Tweet(
            id="123456789",
            text="Hello world! #test @user https://example.com",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={}
        )
        
        self.test_translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Spanish",
            translated_text="¡Hola mundo! #test @user https://example.com",
            translation_timestamp=datetime.now(),
            character_count=45,
            status="pending"
        )
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    def test_translator_initialization_with_cache(self, mock_genai, mock_settings):
        """Test translator initialization includes cache"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        translator = GeminiTranslator()
        
        assert translator.client_initialized == True
        assert hasattr(translator, 'cache')
        assert isinstance(translator.cache, IntelligentTranslationCache)
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    def test_translate_tweet_cache_hit(self, mock_genai, mock_settings):
        """Test translation with cache hit (no API call needed)"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        translator = GeminiTranslator()
        
        # Pre-populate cache
        translator.cache.put(
            self.test_tweet.text, 
            "Spanish", 
            self.test_translation,
            {"formal_tone": False}
        )
        
        # Mock Gemini model (should not be called due to cache hit)
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        
        # Translate tweet - should hit cache
        result = translator.translate_tweet(
            self.test_tweet, 
            "Spanish", 
            {"formal_tone": False}
        )
        
        assert result is not None
        assert result.translated_text == self.test_translation.translated_text
        assert result.target_language == "Spanish"
        assert result.original_tweet == self.test_tweet  # Should be updated to current tweet
        
        # API should not have been called due to cache hit
        mock_model.generate_content.assert_not_called()
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    @patch('src.services.gemini_translator.text_processor')
    @patch('src.services.gemini_translator.prompt_builder')
    def test_translate_tweet_cache_miss_then_cache(self, mock_prompt_builder, mock_text_processor, mock_genai, mock_settings):
        """Test translation with cache miss, API call, then cache population"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        # Setup text processor mocks
        mock_text_processor.extract_preservable_elements.return_value = (
            "Hello world! {HASHTAG_0} {MENTION_0} {URL_0}",
            {"{HASHTAG_0}": "#test", "{MENTION_0}": "@user", "{URL_0}": "https://example.com"}
        )
        mock_text_processor.restore_preservable_elements.return_value = "¡Hola mundo! #test @user https://example.com"
        mock_text_processor.get_character_count.return_value = 45
        mock_text_processor.is_within_twitter_limit.return_value = True
        
        # Setup prompt builder mock
        mock_prompt_builder.build_translation_prompt.return_value = "Translate this tweet to Spanish"
        
        # Setup Gemini API mock
        mock_response = MagicMock()
        mock_response.text = "¡Hola mundo! {HASHTAG_0} {MENTION_0} {URL_0}"
        
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        translator = GeminiTranslator()
        
        # Clear cache to ensure miss
        translator.cache.clear()
        
        # First translation - should be cache miss and API call
        result1 = translator.translate_tweet(
            self.test_tweet,
            "Spanish", 
            {"formal_tone": False}
        )
        
        assert result1 is not None
        assert result1.translated_text == "¡Hola mundo! #test @user https://example.com"
        
        # API should have been called once
        mock_model.generate_content.assert_called_once()
        
        # Reset mock call count
        mock_model.generate_content.reset_mock()
        
        # Second translation of same content - should be cache hit
        same_content_tweet = Tweet(
            id="different_id",
            text=self.test_tweet.text,  # Same content
            created_at=datetime.now(),
            author_username="different_user",
            author_id="different_id",
            public_metrics={}
        )
        
        result2 = translator.translate_tweet(
            same_content_tweet,
            "Spanish",
            {"formal_tone": False}
        )
        
        assert result2 is not None
        assert result2.translated_text == result1.translated_text
        
        # API should not have been called again due to cache hit
        mock_model.generate_content.assert_not_called()
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    def test_translate_tweet_different_language_configs_different_cache(self, mock_genai, mock_settings):
        """Test that different language configs create different cache entries"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        translator = GeminiTranslator()
        translator.cache.clear()
        
        # Pre-populate cache with formal tone translation
        formal_translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Spanish",
            translated_text="Hola mundo (formal). #test @user https://example.com",
            translation_timestamp=datetime.now(),
            character_count=48,
            status="pending"
        )
        
        translator.cache.put(
            self.test_tweet.text,
            "Spanish",
            formal_translation,
            {"formal_tone": True, "cultural_adaptation": True}
        )
        
        # Request translation with different config (informal)
        # Should be cache miss due to different config
        with patch('src.services.gemini_translator.text_processor') as mock_text_processor:
            with patch('src.services.gemini_translator.prompt_builder') as mock_prompt_builder:
                mock_text_processor.extract_preservable_elements.return_value = (
                    "Hello world! {HASHTAG_0} {MENTION_0} {URL_0}",
                    {"{HASHTAG_0}": "#test", "{MENTION_0}": "@user", "{URL_0}": "https://example.com"}
                )
                mock_text_processor.restore_preservable_elements.return_value = "¡Hola mundo! #test @user https://example.com"
                mock_text_processor.get_character_count.return_value = 45
                mock_text_processor.is_within_twitter_limit.return_value = True
                
                mock_prompt_builder.build_translation_prompt.return_value = "Translate informally to Spanish"
                
                mock_response = MagicMock()
                mock_response.text = "¡Hola mundo! {HASHTAG_0} {MENTION_0} {URL_0}"
                
                mock_model = MagicMock()
                mock_model.generate_content.return_value = mock_response
                mock_genai.GenerativeModel.return_value = mock_model
                
                result = translator.translate_tweet(
                    self.test_tweet,
                    "Spanish",
                    {"formal_tone": False, "cultural_adaptation": True}
                )
                
                # Should have made API call (cache miss due to different config)
                mock_model.generate_content.assert_called_once()
                
                # Result should be different from cached formal translation
                assert result.translated_text != formal_translation.translated_text
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    def test_get_cache_metrics(self, mock_genai, mock_settings):
        """Test getting cache metrics from translator"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        translator = GeminiTranslator()
        translator.cache.metrics.reset()  # Reset metrics for clean test
        
        # Add some data to cache
        translator.cache.put("Test text", "Spanish", self.test_translation)
        translator.cache.get("Test text", "Spanish")  # Generate a hit
        translator.cache.get("Different text", "Spanish")  # Generate a miss
        
        metrics = translator.get_cache_metrics()
        
        assert 'metrics' in metrics
        assert 'config' in metrics
        assert metrics['metrics']['hits'] == 1
        assert metrics['metrics']['misses'] == 1
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    def test_clear_cache(self, mock_genai, mock_settings):
        """Test clearing cache through translator"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        translator = GeminiTranslator()
        
        # Add data to cache
        translator.cache.put("Test text", "Spanish", self.test_translation)
        assert len(translator.cache._cache) == 1
        
        # Clear cache
        with patch('src.services.gemini_translator.logger') as mock_logger:
            translator.clear_cache()
            
            assert len(translator.cache._cache) == 0
            mock_logger.info.assert_called_with("🗑️ Translation cache cleared")
    
    @patch('src.services.gemini_translator.settings') 
    @patch('src.services.gemini_translator.genai')
    def test_preload_common_translations(self, mock_genai, mock_settings):
        """Test preloading common translations through translator"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        translator = GeminiTranslator()
        translator.cache.clear()
        
        common_patterns = {
            "Good morning!": {
                "Spanish": "¡Buenos días!",
                "French": "Bonjour !"
            },
            "Thank you": {
                "Spanish": "Gracias"
            }
        }
        
        translator.preload_common_translations(common_patterns)
        
        # Should have 3 translations cached
        assert len(translator.cache._cache) == 3
        
        # Test that preloaded translations work
        result = translator.cache.get("Good morning!", "Spanish")
        assert result is not None
        assert result.translated_text == "¡Buenos días!"
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    @patch('src.services.gemini_translator.text_processor')
    @patch('src.services.gemini_translator.prompt_builder')
    def test_cache_content_normalization(self, mock_prompt_builder, mock_text_processor, mock_genai, mock_settings):
        """Test that cache normalizes whitespace in content"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        # Setup mocks
        mock_text_processor.extract_preservable_elements.return_value = (
            "Hello world",
            {}
        )
        mock_text_processor.restore_preservable_elements.return_value = "Hola mundo"
        mock_text_processor.get_character_count.return_value = 10
        mock_text_processor.is_within_twitter_limit.return_value = True
        
        mock_prompt_builder.build_translation_prompt.return_value = "Translate to Spanish"
        
        mock_response = MagicMock()
        mock_response.text = "Hola mundo"
        
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        translator = GeminiTranslator()
        translator.cache.clear()
        
        # Create tweets with different whitespace but same content
        tweet1 = Tweet(
            id="1", text="Hello   world", created_at=datetime.now(),
            author_username="user1", author_id="1", public_metrics={}
        )
        
        tweet2 = Tweet(
            id="2", text="  Hello world  ", created_at=datetime.now(),
            author_username="user2", author_id="2", public_metrics={}
        )
        
        # First translation should call API
        result1 = translator.translate_tweet(tweet1, "Spanish")
        assert result1 is not None
        mock_model.generate_content.assert_called_once()
        
        # Reset mock
        mock_model.generate_content.reset_mock()
        
        # Second translation should hit cache (normalized content is same)
        result2 = translator.translate_tweet(tweet2, "Spanish")
        assert result2 is not None
        
        # Should not call API again due to cache hit
        mock_model.generate_content.assert_not_called()
        
        # Results should be the same
        assert result1.translated_text == result2.translated_text
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    @patch('src.services.gemini_translator.text_processor')
    @patch('src.services.gemini_translator.prompt_builder')
    def test_cache_handles_translation_shortening(self, mock_prompt_builder, mock_text_processor, mock_genai, mock_settings):
        """Test that shortened translations are also cached"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        # Setup mocks for initial translation (too long)
        mock_text_processor.extract_preservable_elements.return_value = (
            "This is a very long tweet",
            {}
        )
        mock_text_processor.restore_preservable_elements.return_value = "Esta es una traducción muy larga que excede el límite"
        mock_text_processor.get_character_count.return_value = 350  # Over limit
        mock_text_processor.is_within_twitter_limit.return_value = False
        
        mock_prompt_builder.build_translation_prompt.return_value = "Translate to Spanish"
        mock_prompt_builder.build_shortening_prompt.return_value = "Make it shorter"
        
        # Mock initial long response
        mock_response_long = MagicMock()
        mock_response_long.text = "Esta es una traducción muy larga que excede el límite"
        
        # Mock shortened response
        mock_response_short = MagicMock()
        mock_response_short.text = "Traducción corta"
        
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = [mock_response_long, mock_response_short]
        mock_genai.GenerativeModel.return_value = mock_model
        
        translator = GeminiTranslator()
        translator.cache.clear()
        
        tweet = Tweet(
            id="1", text="This is a very long tweet", created_at=datetime.now(),
            author_username="user", author_id="1", public_metrics={}
        )
        
        # Should get shortened translation and cache it
        result = translator.translate_tweet(tweet, "Spanish")
        
        assert result is not None
        assert mock_model.generate_content.call_count == 2  # Original + shortening
        
        # Reset mock
        mock_model.generate_content.reset_mock()
        
        # Second request for same content should hit cache
        same_tweet = Tweet(
            id="2", text="This is a very long tweet", created_at=datetime.now(),
            author_username="user2", author_id="2", public_metrics={}
        )
        
        result2 = translator.translate_tweet(same_tweet, "Spanish")
        
        assert result2 is not None
        # Should not call API again
        mock_model.generate_content.assert_not_called()
    
    def test_global_translator_instance_has_cache(self):
        """Test that the global translator instance has cache properly initialized"""
        # The global instance should have cache
        assert hasattr(gemini_translator, 'cache')
        assert isinstance(gemini_translator.cache, IntelligentTranslationCache)
    
    @patch('src.services.gemini_translator.settings')
    def test_translator_without_api_key_still_has_cache(self, mock_settings):
        """Test that translator without API key still initializes cache"""
        mock_settings.GOOGLE_API_KEY = 'your_google_api_key_here'  # Invalid placeholder
        
        translator = GeminiTranslator()
        
        assert translator.client_initialized == False
        assert hasattr(translator, 'cache')
        assert isinstance(translator.cache, IntelligentTranslationCache)
        
        # Should return None for translation but cache should work
        result = translator.translate_tweet(self.test_tweet, "Spanish")
        assert result is None
