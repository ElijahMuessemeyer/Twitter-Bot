# =============================================================================
# DATA MODELS FOR TWEETS AND TRANSLATIONS
# =============================================================================

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

@dataclass
class Tweet:
    """Represents a tweet from the primary account"""
    id: str
    text: str
    created_at: datetime
    author_username: str
    author_id: str
    public_metrics: Dict[str, int]
    in_reply_to_user_id: Optional[str] = None
    referenced_tweets: Optional[list] = None
    entities: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_twitter_api(cls, tweet_data):
        """Create Tweet object from Twitter API response"""
        return cls(
            id=tweet_data['id'],
            text=tweet_data['text'],
            created_at=datetime.fromisoformat(tweet_data['created_at'].replace('Z', '+00:00')),
            author_username=tweet_data.get('author_username', ''),
            author_id=tweet_data.get('author_id', ''),
            public_metrics=tweet_data.get('public_metrics', {}),
            in_reply_to_user_id=tweet_data.get('in_reply_to_user_id'),
            referenced_tweets=tweet_data.get('referenced_tweets', []),
            entities=tweet_data.get('entities', {})
        )

@dataclass
class Translation:
    """Represents a translated tweet"""
    original_tweet: Tweet
    target_language: str
    translated_text: str
    translation_timestamp: datetime
    character_count: int
    status: str  # 'pending', 'posted', 'failed', 'draft'
    post_id: Optional[str] = None
    error_message: Optional[str] = None