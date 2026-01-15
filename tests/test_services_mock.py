# =============================================================================
# MOCK TESTS FOR API SERVICES
# =============================================================================

import pytest
import sys
import os
from unittest.mock import patch, MagicMock, Mock
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models.tweet import Tweet, Translation
from src.services.gemini_translator import GeminiTranslator
from src.services.twitter_monitor import TwitterMonitor
from src.services.publisher import TwitterPublisher

class TestGeminiTranslatorMock:
    def setup_method(self):
        """Set up test fixtures"""
        self.test_tweet = Tweet(
            id="123456789",
            text="Hello world! #test @user https://example.com",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={}
        )
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    def test_gemini_translator_initialization_success(self, mock_genai, mock_settings):
        """Test successful Gemini translator initialization"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        translator = GeminiTranslator()
        
        assert translator.client_initialized == True
        mock_genai.configure.assert_called_once_with(api_key='valid_api_key')
        mock_genai.GenerativeModel.assert_called_once_with('gemini-2.5-flash-lite')
    
    @patch('src.services.gemini_translator.settings')
    def test_gemini_translator_initialization_no_api_key(self, mock_settings):
        """Test Gemini translator initialization without API key"""
        mock_settings.GOOGLE_API_KEY = 'your_google_api_key_here'  # Placeholder value
        
        translator = GeminiTranslator()
        
        assert translator.client_initialized == False
        assert translator.model is None
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    @patch('src.services.gemini_translator.text_processor')
    @patch('src.services.gemini_translator.prompt_builder')
    def test_translate_tweet_success(self, mock_prompt_builder, mock_text_processor, mock_genai, mock_settings):
        """Test successful tweet translation"""
        # Setup mocks
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        mock_settings.GEMINI_MODEL = 'gemini-2.5-flash-lite'
        
        mock_text_processor.extract_preservable_elements.return_value = (
            "Hello world! {HASHTAG_0} {MENTION_0} {URL_0}",
            {"{HASHTAG_0}": "#test", "{MENTION_0}": "@user", "{URL_0}": "https://example.com"}
        )
        mock_text_processor.restore_preservable_elements.return_value = "¡Hola mundo! #test @user https://example.com"
        mock_text_processor.get_character_count.return_value = 45
        mock_text_processor.is_within_twitter_limit.return_value = True
        
        mock_prompt_builder.build_translation_prompt.return_value = "Translate this tweet to Spanish"
        
        # Mock Gemini API response
        mock_response = MagicMock()
        mock_response.text = "¡Hola mundo! {HASHTAG_0} {MENTION_0} {URL_0}"
        
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        translator = GeminiTranslator()
        
        # Test translation
        translation = translator.translate_tweet(self.test_tweet, "Spanish", {"formal_tone": False})
        
        assert translation is not None
        assert translation.target_language == "Spanish"
        assert translation.translated_text == "¡Hola mundo! #test @user https://example.com"
        assert translation.character_count == 45
        assert translation.status == "pending"
    
    @patch('src.services.gemini_translator.settings')
    def test_translate_tweet_no_client(self, mock_settings):
        """Test tweet translation when client not initialized"""
        mock_settings.GOOGLE_API_KEY = 'your_google_api_key_here'  # Invalid
        
        translator = GeminiTranslator()
        translation = translator.translate_tweet(self.test_tweet, "Spanish")
        
        assert translation is None
    
    @patch('src.services.gemini_translator.settings')
    @patch('src.services.gemini_translator.genai')
    def test_translate_tweet_api_error(self, mock_genai, mock_settings):
        """Test tweet translation when API returns error"""
        mock_settings.GOOGLE_API_KEY = 'valid_api_key'
        
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API Error")
        mock_genai.GenerativeModel.return_value = mock_model
        
        translator = GeminiTranslator()
        translation = translator.translate_tweet(self.test_tweet, "Spanish")
        
        assert translation is None

class TestTwitterMonitorMock:
    @patch('src.services.twitter_monitor.settings')
    @patch('src.services.twitter_monitor.tweepy')
    def test_twitter_monitor_initialization_success(self, mock_tweepy, mock_settings):
        """Test successful Twitter monitor initialization"""
        mock_settings.PRIMARY_TWITTER_CREDS = {
            'consumer_key': 'valid_key',
            'consumer_secret': 'valid_secret',
            'access_token': 'valid_token',
            'access_token_secret': 'valid_token_secret'
        }
        
        mock_api = MagicMock()
        mock_tweepy.API.return_value = mock_api
        
        monitor = TwitterMonitor()
        
        assert monitor.api == mock_api
        mock_tweepy.OAuth1UserHandler.assert_called_once()
    
    @patch('src.services.twitter_monitor.settings')
    def test_twitter_monitor_initialization_invalid_creds(self, mock_settings):
        """Test Twitter monitor initialization with invalid credentials"""
        mock_settings.PRIMARY_TWITTER_CREDS = {
            'consumer_key': 'your_consumer_key_here',  # Placeholder
            'consumer_secret': 'your_consumer_secret_here',
            'access_token': 'your_access_token_here',
            'access_token_secret': 'your_access_token_secret_here'
        }
        
        monitor = TwitterMonitor()
        
        assert monitor.api is None
    
    @patch('src.services.twitter_monitor.settings')
    @patch('src.services.twitter_monitor.tweepy')
    def test_get_new_tweets_success(self, mock_tweepy, mock_settings):
        """Test successful tweet fetching"""
        mock_settings.PRIMARY_TWITTER_CREDS = {
            'consumer_key': 'valid_key',
            'consumer_secret': 'valid_secret', 
            'access_token': 'valid_token',
            'access_token_secret': 'valid_token_secret'
        }
        mock_settings.PRIMARY_USERNAME = 'testuser'
        mock_settings.TWITTER_FREE_DAILY_LIMIT = 50
        
        # Mock API response
        mock_status = MagicMock()
        mock_status.id = 123456789
        mock_status.full_text = "Test tweet"
        mock_status.created_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_status.user.screen_name = "testuser"
        mock_status.user.id = 987654321
        mock_status.retweet_count = 0
        mock_status.favorite_count = 0
        
        mock_cursor = MagicMock()
        mock_cursor.items.return_value = [mock_status]
        mock_tweepy.Cursor.return_value = mock_cursor
        
        mock_api = MagicMock()
        mock_tweepy.API.return_value = mock_api
        
        monitor = TwitterMonitor()
        monitor.daily_requests = 0  # Reset counter
        
        tweets = monitor.get_new_tweets()
        
        assert len(tweets) == 1
        assert tweets[0].id == "123456789"
        assert tweets[0].text == "Test tweet"
    
    @patch('src.services.twitter_monitor.settings')
    def test_get_new_tweets_no_api(self, mock_settings):
        """Test tweet fetching when API not initialized"""
        mock_settings.PRIMARY_TWITTER_CREDS = {
            'consumer_key': 'your_consumer_key_here',
            'consumer_secret': 'your_consumer_secret_here',
            'access_token': 'your_access_token_here',
            'access_token_secret': 'your_access_token_secret_here'
        }
        
        monitor = TwitterMonitor()
        tweets = monitor.get_new_tweets()
        
        assert tweets == []

class TestTwitterPublisherMock:
    @patch('src.services.publisher.settings')
    @patch('src.services.publisher.tweepy')
    def test_publisher_initialization(self, mock_tweepy, mock_settings):
        """Test Twitter publisher initialization"""
        mock_settings.TARGET_LANGUAGES = [
            {'code': 'es', 'name': 'Spanish'},
            {'code': 'fr', 'name': 'French'}
        ]
        
        # Mock successful credential validation
        def mock_get_creds(lang_code):
            return {
                'consumer_key': f'{lang_code}_key',
                'consumer_secret': f'{lang_code}_secret',
                'access_token': f'{lang_code}_token',
                'access_token_secret': f'{lang_code}_token_secret'
            }
        
        mock_settings.get_twitter_creds_for_language.side_effect = mock_get_creds
        
        mock_api = MagicMock()
        mock_tweepy.API.return_value = mock_api
        
        publisher = TwitterPublisher()
        
        # Should have initialized clients for both languages
        assert 'es' in publisher.language_clients
        assert 'fr' in publisher.language_clients
    
    @patch('src.services.publisher.settings')
    @patch('src.services.publisher.tweepy')
    @patch('src.services.publisher.twitter_monitor')
    def test_post_translation_success(self, mock_monitor, mock_tweepy, mock_settings):
        """Test successful translation posting"""
        mock_settings.TARGET_LANGUAGES = [{'code': 'es', 'name': 'Spanish'}]
        
        # Mock credentials
        mock_settings.get_twitter_creds_for_language.return_value = {
            'consumer_key': 'es_key',
            'consumer_secret': 'es_secret',
            'access_token': 'es_token',
            'access_token_secret': 'es_token_secret'
        }
        
        # Mock API
        mock_status = MagicMock()
        mock_status.id = 987654321
        
        mock_api = MagicMock()
        mock_api.update_status.return_value = mock_status
        mock_tweepy.API.return_value = mock_api
        
        # Mock monitor for quota checking
        mock_monitor.can_post_tweet.return_value = True
        
        publisher = TwitterPublisher()
        
        # Create test translation
        test_tweet = Tweet(
            id="123",
            text="Test",
            created_at=datetime.now(),
            author_username="test",
            author_id="123",
            public_metrics={}
        )
        
        translation = Translation(
            original_tweet=test_tweet,
            target_language="Spanish",
            translated_text="Prueba",
            translation_timestamp=datetime.now(),
            character_count=6,
            status="pending"
        )
        
        result = publisher.post_translation(translation)
        
        assert result == True
        assert translation.status == "posted"
        assert translation.post_id == "987654321"
    
    @patch('src.services.publisher.settings')
    @patch('src.services.publisher.twitter_monitor')
    def test_post_translation_no_quota(self, mock_monitor, mock_settings):
        """Test translation posting when quota exceeded"""
        mock_settings.TARGET_LANGUAGES = []
        mock_monitor.can_post_tweet.return_value = False
        
        publisher = TwitterPublisher()
        
        test_tweet = Tweet(
            id="123",
            text="Test", 
            created_at=datetime.now(),
            author_username="test",
            author_id="123",
            public_metrics={}
        )
        
        translation = Translation(
            original_tweet=test_tweet,
            target_language="Spanish",
            translated_text="Prueba",
            translation_timestamp=datetime.now(),
            character_count=6,
            status="pending"
        )
        
        result = publisher.post_translation(translation)
        
        assert result == False