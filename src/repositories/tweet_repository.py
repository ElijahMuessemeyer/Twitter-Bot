# =============================================================================
# TWEET REPOSITORY
# =============================================================================

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func
from src.models.database_models import Tweet as TweetModel
from src.models.tweet import Tweet
from src.repositories.base_repository import BaseRepository

class TweetRepository(BaseRepository[TweetModel]):
    """Repository for tweet operations"""
    
    def __init__(self, session: Session):
        super().__init__(session, TweetModel)
    
    def create_from_tweet_object(self, tweet: Tweet) -> TweetModel:
        """Create database record from Tweet dataclass"""
        return self.create(
            id=tweet.id,
            text=tweet.text,
            author_username=tweet.author_username,
            author_id=tweet.author_id,
            created_at=tweet.created_at,
            public_metrics=tweet.public_metrics,
            in_reply_to_user_id=tweet.in_reply_to_user_id,
            referenced_tweets=tweet.referenced_tweets or [],
            entities=tweet.entities or {},
            character_count=len(tweet.text),
            language=self._detect_language(tweet.text)
        )
    
    def get_latest_tweet_id(self) -> Optional[str]:
        """Get the ID of the most recently processed tweet"""
        try:
            latest_tweet = self.session.query(TweetModel).order_by(
                desc(TweetModel.processed_at)
            ).first()
            
            return latest_tweet.id if latest_tweet else None
        except Exception as e:
            self.logger.error(f"Error getting latest tweet ID: {str(e)}")
            return None
    
    def get_tweets_after_id(self, tweet_id: Optional[str] = None, limit: int = 50) -> List[TweetModel]:
        """Get tweets created after a specific tweet ID"""
        try:
            query = self.session.query(TweetModel)
            
            if tweet_id:
                # Get tweets created after the reference tweet
                reference_tweet = self.get_by_id(tweet_id)
                if reference_tweet:
                    query = query.filter(TweetModel.created_at > reference_tweet.created_at)
            
            return query.order_by(TweetModel.created_at).limit(limit).all()
        except Exception as e:
            self.logger.error(f"Error getting tweets after ID {tweet_id}: {str(e)}")
            return []
    
    def get_tweets_by_author(self, author_id: str, limit: Optional[int] = None) -> List[TweetModel]:
        """Get tweets by author"""
        query = self.session.query(TweetModel).filter(TweetModel.author_id == author_id)
        
        if limit:
            query = query.limit(limit)
        
        return query.order_by(desc(TweetModel.created_at)).all()
    
    def get_tweets_in_date_range(self, start_date: datetime, end_date: datetime) -> List[TweetModel]:
        """Get tweets within a date range"""
        return self.session.query(TweetModel).filter(
            and_(
                TweetModel.created_at >= start_date,
                TweetModel.created_at <= end_date
            )
        ).order_by(TweetModel.created_at).all()
    
    def get_recent_tweets(self, hours: int = 24, limit: Optional[int] = None) -> List[TweetModel]:
        """Get recent tweets within specified hours"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        query = self.session.query(TweetModel).filter(
            TweetModel.created_at >= cutoff_time
        ).order_by(desc(TweetModel.created_at))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def search_tweets(self, search_text: str, limit: Optional[int] = None) -> List[TweetModel]:
        """Search tweets by text content"""
        query = self.session.query(TweetModel).filter(
            TweetModel.text.contains(search_text)
        ).order_by(desc(TweetModel.created_at))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_tweet_statistics(self) -> Dict[str, Any]:
        """Get tweet statistics"""
        try:
            total_tweets = self.count()
            
            # Get tweets from last 24 hours
            recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            recent_tweets = self.session.query(TweetModel).filter(
                TweetModel.created_at >= recent_cutoff
            ).count()
            
            # Get average character count
            avg_chars = self.session.query(
                func.avg(TweetModel.character_count)
            ).scalar() or 0
            
            # Get most active author
            top_author = self.session.query(
                TweetModel.author_username,
                func.count(TweetModel.id).label('tweet_count')
            ).group_by(TweetModel.author_username).order_by(
                desc('tweet_count')
            ).first()
            
            return {
                'total_tweets': total_tweets,
                'recent_tweets_24h': recent_tweets,
                'average_character_count': round(float(avg_chars), 2),
                'top_author': top_author[0] if top_author else None,
                'top_author_count': top_author[1] if top_author else 0
            }
        except Exception as e:
            self.logger.error(f"Error getting tweet statistics: {str(e)}")
            return {}
    
    def delete_old_tweets(self, days_old: int = 90) -> int:
        """Delete tweets older than specified days"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            
            deleted_count = self.session.query(TweetModel).filter(
                TweetModel.created_at < cutoff_date
            ).delete()
            
            self.session.flush()
            return deleted_count
        except Exception as e:
            self.logger.error(f"Error deleting old tweets: {str(e)}")
            self.session.rollback()
            return 0
    
    def get_untranslated_tweets(self, target_language: str, limit: Optional[int] = None) -> List[TweetModel]:
        """Get tweets that haven't been translated to target language"""
        from src.models.database_models import Translation as TranslationModel
        
        query = self.session.query(TweetModel).outerjoin(
            TranslationModel,
            and_(
                TweetModel.id == TranslationModel.original_tweet_id,
                TranslationModel.target_language == target_language
            )
        ).filter(TranslationModel.id.is_(None))
        
        if limit:
            query = query.limit(limit)
        
        return query.order_by(TweetModel.created_at).all()
    
    def _detect_language(self, text: str) -> Optional[str]:
        """Simple language detection (can be enhanced with proper detection library)"""
        # This is a placeholder - in production, you'd use a proper language detection library
        # For now, we'll assume English if not specified
        return 'en'
    
    @property
    def logger(self):
        """Get logger for this repository"""
        from src.utils.logger import logger
        return logger
