# =============================================================================
# DATA MODELS TESTS
# =============================================================================

import pytest
import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models.tweet import Tweet, Translation

class TestTweet:
    def test_tweet_creation(self):
        """Test basic tweet creation"""
        tweet = Tweet(
            id="123456789",
            text="This is a test tweet",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={"retweet_count": 5, "favorite_count": 10}
        )
        
        assert tweet.id == "123456789"
        assert tweet.text == "This is a test tweet"
        assert tweet.author_username == "testuser"
        assert tweet.author_id == "987654321"
        assert tweet.public_metrics["retweet_count"] == 5
        assert tweet.public_metrics["favorite_count"] == 10
    
    def test_tweet_with_optional_fields(self):
        """Test tweet creation with optional fields"""
        tweet = Tweet(
            id="123456789",
            text="Reply tweet",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={},
            in_reply_to_user_id="555555555",
            referenced_tweets=[{"type": "replied_to", "id": "111111111"}],
            entities={"hashtags": [{"tag": "test"}]}
        )
        
        assert tweet.in_reply_to_user_id == "555555555"
        assert tweet.referenced_tweets == [{"type": "replied_to", "id": "111111111"}]
        assert tweet.entities == {"hashtags": [{"tag": "test"}]}
    
    def test_tweet_from_twitter_api(self):
        """Test creating tweet from Twitter API response format"""
        api_data = {
            'id': '123456789',
            'text': 'API test tweet',
            'created_at': '2024-01-01T12:00:00.000Z',
            'author_username': 'apiuser',
            'author_id': '987654321',
            'public_metrics': {'retweet_count': 3, 'like_count': 7},
            'in_reply_to_user_id': '555555555',
            'referenced_tweets': [],
            'entities': {'urls': []}
        }
        
        tweet = Tweet.from_twitter_api(api_data)
        
        assert tweet.id == '123456789'
        assert tweet.text == 'API test tweet'
        assert tweet.author_username == 'apiuser'
        assert tweet.author_id == '987654321'
        assert tweet.in_reply_to_user_id == '555555555'
        assert isinstance(tweet.created_at, datetime)

class TestTranslation:
    def setup_method(self):
        """Set up test fixtures"""
        self.test_tweet = Tweet(
            id="123456789",
            text="Original English tweet",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={"retweet_count": 0, "favorite_count": 0}
        )
    
    def test_translation_creation(self):
        """Test basic translation creation"""
        translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Japanese",
            translated_text="これは日本語のツイートです",
            translation_timestamp=datetime(2024, 1, 1, 12, 5, 0),
            character_count=15,
            status="pending"
        )
        
        assert translation.original_tweet.id == "123456789"
        assert translation.target_language == "Japanese"
        assert translation.translated_text == "これは日本語のツイートです"
        assert translation.character_count == 15
        assert translation.status == "pending"
        assert translation.post_id is None
        assert translation.error_message is None
    
    def test_translation_with_optional_fields(self):
        """Test translation with optional fields filled"""
        translation = Translation(
            original_tweet=self.test_tweet,
            target_language="German",
            translated_text="Dies ist ein deutscher Tweet",
            translation_timestamp=datetime(2024, 1, 1, 12, 5, 0),
            character_count=28,
            status="posted",
            post_id="987654321",
            error_message=None
        )
        
        assert translation.status == "posted"
        assert translation.post_id == "987654321"
        assert translation.error_message is None
    
    def test_translation_with_error(self):
        """Test translation with error state"""
        translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Spanish",
            translated_text="",
            translation_timestamp=datetime(2024, 1, 1, 12, 5, 0),
            character_count=0,
            status="failed",
            post_id=None,
            error_message="Translation service unavailable"
        )
        
        assert translation.status == "failed"
        assert translation.post_id is None
        assert translation.error_message == "Translation service unavailable"
    
    def test_translation_status_values(self):
        """Test different status values"""
        valid_statuses = ['pending', 'posted', 'failed', 'draft']
        
        for status in valid_statuses:
            translation = Translation(
                original_tweet=self.test_tweet,
                target_language="French",
                translated_text="Ceci est un tweet français",
                translation_timestamp=datetime.now(),
                character_count=26,
                status=status
            )
            assert translation.status == status
    
    def test_translation_character_count_accuracy(self):
        """Test that character count matches actual text length"""
        text = "Este es un tweet en español"
        translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Spanish",
            translated_text=text,
            translation_timestamp=datetime.now(),
            character_count=len(text),
            status="pending"
        )
        
        assert translation.character_count == len(text)
    
    def test_translation_preserves_original_tweet(self):
        """Test that translation preserves reference to original tweet"""
        translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Italian",
            translated_text="Questo è un tweet italiano",
            translation_timestamp=datetime.now(),
            character_count=26,
            status="pending"
        )
        
        # Should be able to access original tweet data
        assert translation.original_tweet.text == "Original English tweet"
        assert translation.original_tweet.author_username == "testuser"
        assert translation.original_tweet.id == "123456789"