# =============================================================================
# DATABASE MODELS TESTS
# =============================================================================

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.database_models import (
    Base, Tweet, Translation, APIUsage, User, TranslationCache, SystemState
)

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

class TestTweetModel:
    """Test Tweet database model"""
    
    def test_create_tweet(self, test_session):
        """Test creating a tweet record"""
        tweet = Tweet(
            id="123456789",
            text="This is a test tweet",
            author_username="testuser",
            author_id="987654321",
            created_at=datetime.now(timezone.utc),
            character_count=21,
            public_metrics={"retweet_count": 5, "favorite_count": 10}
        )
        
        test_session.add(tweet)
        test_session.commit()
        
        # Verify tweet was created
        retrieved_tweet = test_session.query(Tweet).filter_by(id="123456789").first()
        assert retrieved_tweet is not None
        assert retrieved_tweet.text == "This is a test tweet"
        assert retrieved_tweet.author_username == "testuser"
        assert retrieved_tweet.character_count == 21
    
    def test_tweet_validation(self, test_session):
        """Test tweet model validation"""
        # Test invalid character count
        with pytest.raises(ValueError):
            tweet = Tweet(
                id="123456789",
                text="Test tweet",
                author_username="testuser",
                author_id="987654321",
                created_at=datetime.now(timezone.utc),
                character_count=-1  # Invalid
            )
            # Trigger validation
            tweet.character_count = tweet.__table__.columns.character_count.type.python_type(tweet.character_count)
    
    def test_tweet_to_dict(self, test_session):
        """Test tweet serialization"""
        tweet = Tweet(
            id="123456789",
            text="Test tweet",
            author_username="testuser",
            author_id="987654321",
            created_at=datetime.now(timezone.utc),
            character_count=10,
            public_metrics={"retweet_count": 1}
        )
        
        test_session.add(tweet)
        test_session.commit()
        
        tweet_dict = tweet.to_dict()
        assert tweet_dict['id'] == "123456789"
        assert tweet_dict['text'] == "Test tweet"
        assert 'created_at' in tweet_dict
        assert tweet_dict['public_metrics'] == {"retweet_count": 1}

class TestTranslationModel:
    """Test Translation database model"""
    
    def test_create_translation(self, test_session):
        """Test creating a translation record"""
        # First create a tweet
        tweet = Tweet(
            id="123456789",
            text="Hello world",
            author_username="testuser",
            author_id="987654321",
            created_at=datetime.now(timezone.utc),
            character_count=11
        )
        test_session.add(tweet)
        test_session.flush()
        
        # Create translation
        translation = Translation(
            original_tweet_id="123456789",
            translated_text="Hola mundo",
            target_language="es",
            status="pending",
            character_count=10
        )
        
        test_session.add(translation)
        test_session.commit()
        
        # Verify translation was created
        retrieved_translation = test_session.query(Translation).first()
        assert retrieved_translation is not None
        assert retrieved_translation.translated_text == "Hola mundo"
        assert retrieved_translation.target_language == "es"
        assert retrieved_translation.status == "pending"
    
    def test_translation_status_validation(self, test_session):
        """Test translation status validation"""
        # Test that invalid status raises validation error
        with pytest.raises(ValueError, match="Status must be one of"):
            translation = Translation(
                original_tweet_id="123456789",
                translated_text="Test",
                target_language="es",
                status="invalid_status",  # This should be validated
                character_count=4
            )
        
    def test_translation_relationships(self, test_session):
        """Test translation-tweet relationship"""
        # Create tweet
        tweet = Tweet(
            id="123456789",
            text="Hello world",
            author_username="testuser",
            author_id="987654321",
            created_at=datetime.now(timezone.utc),
            character_count=11
        )
        test_session.add(tweet)
        test_session.flush()
        
        # Create translation
        translation = Translation(
            original_tweet_id="123456789",
            translated_text="Hola mundo",
            target_language="es",
            status="pending",
            character_count=10
        )
        test_session.add(translation)
        test_session.commit()
        
        # Test relationship
        retrieved_translation = test_session.query(Translation).first()
        assert retrieved_translation.original_tweet is not None
        assert retrieved_translation.original_tweet.text == "Hello world"

class TestAPIUsageModel:
    """Test APIUsage database model"""
    
    def test_create_api_usage(self, test_session):
        """Test creating API usage record"""
        now = datetime.now(timezone.utc)
        api_usage = APIUsage(
            service="twitter",
            endpoint="user_timeline",
            method="GET",
            timestamp=now,
            response_time=0.245,
            status_code=200,
            success=True,
            date=now.strftime('%Y-%m-%d'),
            month=now.strftime('%Y-%m')
        )
        
        test_session.add(api_usage)
        test_session.commit()
        
        # Verify API usage was created
        retrieved_usage = test_session.query(APIUsage).first()
        assert retrieved_usage is not None
        assert retrieved_usage.service == "twitter"
        assert retrieved_usage.endpoint == "user_timeline"
        assert retrieved_usage.success == True
        assert retrieved_usage.response_time == 0.245

class TestUserModel:
    """Test User database model"""
    
    def test_create_user(self, test_session):
        """Test creating a user record"""
        user = User(
            account_name="primary_account",
            account_type="primary",
            api_credentials={"consumer_key": "test_key"},
            settings={"auto_post": True},
            is_active=True
        )
        
        test_session.add(user)
        test_session.commit()
        
        # Verify user was created
        retrieved_user = test_session.query(User).first()
        assert retrieved_user is not None
        assert retrieved_user.account_name == "primary_account"
        assert retrieved_user.account_type == "primary"
        assert retrieved_user.is_active == True
        assert retrieved_user.settings["auto_post"] == True
    
    def test_user_to_dict(self, test_session):
        """Test user serialization with credential control"""
        user = User(
            account_name="test_user",
            account_type="primary",
            api_credentials={"secret": "hidden"},
            settings={"public": "setting"},
            is_active=True
        )
        
        test_session.add(user)
        test_session.commit()
        
        # Test without credentials
        user_dict = user.to_dict(include_credentials=False)
        assert 'api_credentials' not in user_dict
        assert user_dict['settings'] == {"public": "setting"}
        
        # Test with credentials
        user_dict_with_creds = user.to_dict(include_credentials=True)
        assert user_dict_with_creds['api_credentials'] == {"secret": "hidden"}

class TestTranslationCacheModel:
    """Test TranslationCache database model"""
    
    def test_create_cache_entry(self, test_session):
        """Test creating a cache entry"""
        cache_entry = TranslationCache(
            cache_key="abc123",
            original_text="Hello world",
            translated_text="Hola mundo",
            source_language="en",
            target_language="es",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            access_count=1,
            confidence_score=0.95,
            translator_service="gemini"
        )
        
        test_session.add(cache_entry)
        test_session.commit()
        
        # Verify cache entry was created
        retrieved_entry = test_session.query(TranslationCache).first()
        assert retrieved_entry is not None
        assert retrieved_entry.original_text == "Hello world"
        assert retrieved_entry.translated_text == "Hola mundo"
        assert retrieved_entry.target_language == "es"
        assert retrieved_entry.confidence_score == 0.95
    
    def test_cache_expiration(self, test_session):
        """Test cache expiration logic"""
        # Create expired entry
        expired_entry = TranslationCache(
            cache_key="expired123",
            original_text="Old text",
            translated_text="Texto viejo",
            target_language="es",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1)  # Expired
        )
        
        # Create valid entry
        valid_entry = TranslationCache(
            cache_key="valid123",
            original_text="New text",
            translated_text="Texto nuevo",
            target_language="es",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)  # Valid
        )
        
        test_session.add_all([expired_entry, valid_entry])
        test_session.commit()
        
        # Test expiration logic
        assert expired_entry.is_expired() == True
        assert valid_entry.is_expired() == False

class TestSystemStateModel:
    """Test SystemState database model"""
    
    def test_create_system_state(self, test_session):
        """Test creating a system state record"""
        state = SystemState(
            key="last_tweet_id",
            value="123456789",
            description="ID of last processed tweet",
            state_type="tweet_tracking"
        )
        
        test_session.add(state)
        test_session.commit()
        
        # Verify state was created
        retrieved_state = test_session.query(SystemState).first()
        assert retrieved_state is not None
        assert retrieved_state.key == "last_tweet_id"
        assert retrieved_state.value == "123456789"
        assert retrieved_state.state_type == "tweet_tracking"
    
    def test_system_state_to_dict(self, test_session):
        """Test system state serialization"""
        state = SystemState(
            key="test_config",
            value="test_value",
            description="Test configuration",
            state_type="general"
        )
        
        test_session.add(state)
        test_session.commit()
        
        state_dict = state.to_dict()
        assert state_dict['key'] == "test_config"
        assert state_dict['value'] == "test_value"
        assert 'created_at' in state_dict
        assert 'updated_at' in state_dict

class TestModelConstraints:
    """Test database constraints and indexes"""
    
    def test_unique_constraints(self, test_session):
        """Test unique constraints"""
        # Test unique cache key
        cache1 = TranslationCache(
            cache_key="duplicate123",
            original_text="Hello",
            translated_text="Hola",
            target_language="es"
        )
        
        cache2 = TranslationCache(
            cache_key="duplicate123",  # Same key
            original_text="Hello again",
            translated_text="Hola otra vez",
            target_language="es"
        )
        
        test_session.add(cache1)
        test_session.commit()
        
        # This should raise an integrity error
        test_session.add(cache2)
        with pytest.raises(Exception):  # IntegrityError
            test_session.commit()

if __name__ == "__main__":
    pytest.main([__file__])
