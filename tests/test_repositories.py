# =============================================================================
# REPOSITORY PATTERN TESTS
# =============================================================================

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.database_models import Base
from src.repositories import (
    TweetRepository, TranslationRepository, APIUsageRepository,
    UserRepository, CacheRepository, SystemStateRepository
)
from src.models.tweet import Tweet

# Test database setup
@pytest.fixture
def test_engine():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    return engine

@pytest.fixture
def test_session(test_engine):
    """Create test database session"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = SessionLocal()
    yield session
    session.close()

class TestTweetRepository:
    """Test TweetRepository functionality"""
    
    def test_create_tweet_from_object(self, test_session):
        """Test creating tweet from Tweet dataclass"""
        repo = TweetRepository(test_session)
        
        # Create Tweet object
        tweet = Tweet(
            id="123456789",
            text="Hello world",
            created_at=datetime.now(timezone.utc),
            author_username="testuser",
            author_id="987654321",
            public_metrics={"retweet_count": 5},
            in_reply_to_user_id=None,
            referenced_tweets=[],
            entities={}
        )
        
        # Create database record
        db_tweet = repo.create_from_tweet_object(tweet)
        test_session.commit()
        
        assert db_tweet.id == "123456789"
        assert db_tweet.text == "Hello world"
        assert db_tweet.author_username == "testuser"
        assert db_tweet.character_count == len(tweet.text)
    
    def test_get_latest_tweet_id(self, test_session):
        """Test getting latest processed tweet ID"""
        repo = TweetRepository(test_session)
        
        # Should return None when no tweets exist
        assert repo.get_latest_tweet_id() is None
        
        # Create some tweets
        tweet1 = repo.create(
            id="111111111",
            text="First tweet",
            author_username="user1",
            author_id="123",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            character_count=11
        )
        
        tweet2 = repo.create(
            id="222222222",
            text="Second tweet",
            author_username="user1",
            author_id="123",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            character_count=12
        )
        
        test_session.commit()
        
        # Should return the most recent tweet ID
        latest_id = repo.get_latest_tweet_id()
        assert latest_id == "222222222"
    
    def test_get_tweets_by_author(self, test_session):
        """Test getting tweets by author"""
        repo = TweetRepository(test_session)
        
        # Create tweets from different authors
        repo.create(
            id="111111111",
            text="Tweet from user1",
            author_username="user1",
            author_id="123",
            created_at=datetime.now(timezone.utc),
            character_count=16
        )
        
        repo.create(
            id="222222222",
            text="Tweet from user2",
            author_username="user2",
            author_id="456",
            created_at=datetime.now(timezone.utc),
            character_count=16
        )
        
        test_session.commit()
        
        # Get tweets by author
        user1_tweets = repo.get_tweets_by_author("123")
        assert len(user1_tweets) == 1
        assert user1_tweets[0].author_username == "user1"
        
        user2_tweets = repo.get_tweets_by_author("456")
        assert len(user2_tweets) == 1
        assert user2_tweets[0].author_username == "user2"
    
    def test_get_tweet_statistics(self, test_session):
        """Test getting tweet statistics"""
        repo = TweetRepository(test_session)
        
        # Create test tweets
        repo.create(
            id="111111111",
            text="Short",
            author_username="user1",
            author_id="123",
            created_at=datetime.now(timezone.utc),
            character_count=5
        )
        
        repo.create(
            id="222222222",
            text="This is a longer tweet",
            author_username="user1",
            author_id="123",
            created_at=datetime.now(timezone.utc),
            character_count=22
        )
        
        test_session.commit()
        
        stats = repo.get_tweet_statistics()
        assert stats['total_tweets'] == 2
        assert stats['average_character_count'] == 13.5
        assert stats['top_author'] == "user1"
        assert stats['top_author_count'] == 2

class TestTranslationRepository:
    """Test TranslationRepository functionality"""
    
    @pytest.fixture
    def sample_tweet(self, test_session):
        """Create a sample tweet for translation tests"""
        tweet_repo = TweetRepository(test_session)
        return tweet_repo.create(
            id="123456789",
            text="Hello world",
            author_username="testuser",
            author_id="987654321",
            created_at=datetime.now(timezone.utc),
            character_count=11
        )
    
    def test_create_translation(self, test_session, sample_tweet):
        """Test creating a translation"""
        repo = TranslationRepository(test_session)
        
        translation = repo.create(
            original_tweet_id=sample_tweet.id,
            translated_text="Hola mundo",
            target_language="es",
            status="pending",
            character_count=10
        )
        
        test_session.commit()
        
        assert translation.original_tweet_id == sample_tweet.id
        assert translation.translated_text == "Hola mundo"
        assert translation.target_language == "es"
        assert translation.status == "pending"
    
    def test_get_by_tweet_and_language(self, test_session, sample_tweet):
        """Test getting translation by tweet and language"""
        repo = TranslationRepository(test_session)
        
        # Create translation
        repo.create(
            original_tweet_id=sample_tweet.id,
            translated_text="Hola mundo",
            target_language="es",
            status="pending",
            character_count=10
        )
        
        test_session.commit()
        
        # Retrieve translation
        translation = repo.get_by_tweet_and_language(sample_tweet.id, "es")
        assert translation is not None
        assert translation.translated_text == "Hola mundo"
        
        # Non-existent translation
        no_translation = repo.get_by_tweet_and_language(sample_tweet.id, "fr")
        assert no_translation is None
    
    def test_mark_as_posted(self, test_session, sample_tweet):
        """Test marking translation as posted"""
        repo = TranslationRepository(test_session)
        
        # Create pending translation
        translation = repo.create(
            original_tweet_id=sample_tweet.id,
            translated_text="Hola mundo",
            target_language="es",
            status="pending",
            character_count=10
        )
        
        test_session.commit()
        translation_id = translation.id
        
        # Mark as posted
        success = repo.mark_as_posted(translation_id, "987654321")
        test_session.commit()
        
        assert success == True
        
        # Verify status change
        updated_translation = repo.get_by_id(translation_id)
        assert updated_translation.status == "posted"
        assert updated_translation.post_id == "987654321"
        assert updated_translation.posted_at is not None
    
    def test_get_draft_translations(self, test_session, sample_tweet):
        """Test getting draft translations"""
        repo = TranslationRepository(test_session)
        
        # Create draft and pending translations
        repo.create(
            original_tweet_id=sample_tweet.id,
            translated_text="Draft translation",
            target_language="es",
            status="draft",
            character_count=18
        )
        
        repo.create(
            original_tweet_id=sample_tweet.id,
            translated_text="Pending translation",
            target_language="fr",
            status="pending",
            character_count=19
        )
        
        test_session.commit()
        
        # Get drafts
        drafts = repo.get_draft_translations()
        assert len(drafts) == 1
        assert drafts[0].status == "draft"
        assert drafts[0].translated_text == "Draft translation"
    
    def test_get_translation_statistics(self, test_session, sample_tweet):
        """Test getting translation statistics"""
        repo = TranslationRepository(test_session)
        
        # Create translations with different statuses
        repo.create(
            original_tweet_id=sample_tweet.id,
            translated_text="Posted translation",
            target_language="es",
            status="posted",
            character_count=18
        )
        
        repo.create(
            original_tweet_id=sample_tweet.id,
            translated_text="Failed translation",
            target_language="fr",
            status="failed",
            character_count=18
        )
        
        test_session.commit()
        
        stats = repo.get_translation_statistics()
        assert stats['total_translations'] == 2
        assert stats['status_counts']['posted'] == 1
        assert stats['status_counts']['failed'] == 1

class TestAPIUsageRepository:
    """Test APIUsageRepository functionality"""
    
    def test_log_api_call(self, test_session):
        """Test logging an API call"""
        repo = APIUsageRepository(test_session)
        
        api_call = repo.log_api_call(
            service="twitter",
            endpoint="user_timeline",
            method="GET",
            response_time=0.25,
            status_code=200,
            success=True,
            error_info=None,
            request_metadata={"count": 20}
        )
        
        test_session.commit()
        
        assert api_call.service == "twitter"
        assert api_call.endpoint == "user_timeline"
        assert api_call.success == True
        assert api_call.response_time == 0.25
        assert api_call.request_metadata["count"] == 20
    
    def test_get_daily_usage(self, test_session):
        """Test getting daily API usage statistics"""
        repo = APIUsageRepository(test_session)
        
        # Create some API calls for today
        today = datetime.now(timezone.utc)
        
        for i in range(3):
            repo.log_api_call(
                service="twitter",
                endpoint="user_timeline",
                response_time=0.1 + i * 0.1,
                success=True
            )
        
        # Create one failed call
        repo.log_api_call(
            service="twitter",
            endpoint="post_tweet",
            success=False,
            error_info={"message": "Rate limited"}
        )
        
        test_session.commit()
        
        daily_usage = repo.get_daily_usage("twitter", today)
        assert daily_usage['total_calls'] == 4
        assert daily_usage['successful_calls'] == 3
        assert daily_usage['failed_calls'] == 1
        assert daily_usage['success_rate'] == 75.0
    
    def test_get_current_limits(self, test_session):
        """Test getting current API limits"""
        repo = APIUsageRepository(test_session)
        
        # Create some API calls
        for i in range(5):
            repo.log_api_call(service="twitter", endpoint="test")
        
        test_session.commit()
        
        limits = repo.get_current_limits("twitter")
        assert limits['daily_requests'] == 5
        assert limits['monthly_requests'] == 5

class TestUserRepository:
    """Test UserRepository functionality"""
    
    def test_create_user(self, test_session):
        """Test creating a user"""
        repo = UserRepository(test_session)
        
        user = repo.create_user(
            account_name="primary_account",
            account_type="primary",
            api_credentials={"consumer_key": "test_key"},
            settings={"auto_post": True}
        )
        
        test_session.commit()
        
        assert user.account_name == "primary_account"
        assert user.account_type == "primary"
        assert user.is_active == True
        assert user.settings["auto_post"] == True
    
    def test_get_by_account_name(self, test_session):
        """Test getting user by account name"""
        repo = UserRepository(test_session)
        
        # Create user
        repo.create_user(account_name="test_account")
        test_session.commit()
        
        # Retrieve user
        user = repo.get_by_account_name("test_account")
        assert user is not None
        assert user.account_name == "test_account"
        
        # Non-existent user
        no_user = repo.get_by_account_name("non_existent")
        assert no_user is None
    
    def test_update_user_settings(self, test_session):
        """Test updating user settings"""
        repo = UserRepository(test_session)
        
        # Create user
        user = repo.create_user(
            account_name="test_user",
            settings={"setting1": "value1"}
        )
        test_session.commit()
        user_id = user.id
        
        # Update settings
        success = repo.update_user_settings(user_id, {
            "setting1": "updated_value1",
            "setting2": "value2"
        })
        test_session.commit()
        
        assert success == True
        
        # Refresh the session to get the latest data
        test_session.refresh(user)
        
        # Verify settings were updated
        assert user.settings["setting1"] == "updated_value1"
        assert user.settings["setting2"] == "value2"

class TestCacheRepository:
    """Test CacheRepository functionality"""
    
    def test_store_and_get_translation(self, test_session):
        """Test storing and retrieving cached translations"""
        repo = CacheRepository(test_session)
        
        # Store translation
        cache_entry = repo.store_translation(
            original_text="Hello world",
            translated_text="Hola mundo",
            target_language="es",
            confidence_score=0.95,
            ttl_hours=24
        )
        
        test_session.commit()
        
        assert cache_entry is not None
        
        # Retrieve translation
        cached_translation = repo.get_translation("Hello world", "es")
        assert cached_translation == "Hola mundo"
        
        # Non-existent translation
        no_translation = repo.get_translation("Different text", "es")
        assert no_translation is None
    
    def test_cache_expiration(self, test_session):
        """Test cache expiration functionality"""
        repo = CacheRepository(test_session)
        
        # Store translation with very short TTL
        repo.store_translation(
            original_text="Expiring text",
            translated_text="Texto que expira",
            target_language="es",
            ttl_hours=-1  # Already expired
        )
        
        test_session.commit()
        
        # Should not retrieve expired translation
        cached_translation = repo.get_translation("Expiring text", "es")
        assert cached_translation is None
    
    def test_cleanup_expired_entries(self, test_session):
        """Test cleaning up expired cache entries"""
        repo = CacheRepository(test_session)
        
        # Create expired and valid entries
        repo.store_translation("Expired", "Expirado", "es", ttl_hours=-1)
        repo.store_translation("Valid", "Válido", "es", ttl_hours=24)
        
        test_session.commit()
        
        # Cleanup expired entries
        removed_count = repo.cleanup_expired_entries()
        test_session.commit()
        
        assert removed_count == 1
        
        # Verify only valid entry remains
        assert repo.get_translation("Expired", "es") is None
        assert repo.get_translation("Valid", "es") == "Válido"

class TestSystemStateRepository:
    """Test SystemStateRepository functionality"""
    
    def test_set_and_get_state(self, test_session):
        """Test setting and getting system state"""
        repo = SystemStateRepository(test_session)
        
        # Set state
        repo.set_state("test_key", "test_value", "Test description", "test")
        test_session.commit()
        
        # Get state
        value = repo.get_state("test_key")
        assert value == "test_value"
        
        # Get non-existent state
        no_value = repo.get_state("non_existent", "default")
        assert no_value == "default"
    
    def test_twitter_specific_methods(self, test_session):
        """Test Twitter-specific state methods"""
        repo = SystemStateRepository(test_session)
        
        # Test tweet ID methods
        repo.set_last_tweet_id("123456789")
        test_session.commit()
        
        tweet_id = repo.get_last_tweet_id()
        assert tweet_id == "123456789"
        
        # Test API usage methods
        repo.set_daily_requests("twitter", 50)
        test_session.commit()
        
        daily_requests = repo.get_daily_requests("twitter")
        assert daily_requests == 50
        
        # Test increment
        new_count = repo.increment_daily_requests("twitter")
        test_session.commit()
        assert new_count == 51

if __name__ == "__main__":
    pytest.main([__file__])
