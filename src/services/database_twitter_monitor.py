# =============================================================================
# DATABASE-BACKED TWITTER MONITORING SERVICE
# =============================================================================
# Replaces file-based state storage with database-backed solution

import tweepy
from datetime import datetime, timezone
from typing import List, Optional
from src.models.tweet import Tweet
from src.repositories import TweetRepository, SystemStateRepository, APIUsageRepository
from src.config.database import db_config
from src.config.settings import settings
from src.utils.logger import logger

class DatabaseTwitterMonitor:
    """Database-backed Twitter monitoring service"""
    
    def __init__(self):
        self.api = None
        self._init_twitter_client()
    
    def _init_twitter_client(self):
        """Initialize Twitter API client"""
        if self._has_valid_credentials():
            try:
                auth = tweepy.OAuth1UserHandler(
                    settings.PRIMARY_TWITTER_CREDS['consumer_key'],
                    settings.PRIMARY_TWITTER_CREDS['consumer_secret'],
                    settings.PRIMARY_TWITTER_CREDS['access_token'],
                    settings.PRIMARY_TWITTER_CREDS['access_token_secret']
                )
                self.api = tweepy.API(auth, wait_on_rate_limit=True)
                logger.info("✅ Twitter API client initialized")
            except Exception as e:
                logger.error(f"❌ Failed to create Twitter client: {str(e)}")
                self.api = None
        else:
            self.api = None
            logger.warning("⚠️ Twitter API credentials not configured. Monitoring will not work.")
    
    def _has_valid_credentials(self) -> bool:
        """Check if we have valid Twitter credentials"""
        creds = settings.PRIMARY_TWITTER_CREDS
        return all(creds.values()) and not any(v.startswith('your_') for v in creds.values())
    
    def log_api_call(self, endpoint: str, success: bool = True, response_time: Optional[float] = None, error: Optional[str] = None):
        """Log API call to database"""
        try:
            with db_config.get_session() as session:
                api_usage_repo = APIUsageRepository(session)
                
                api_usage_repo.log_api_call(
                    service='twitter',
                    endpoint=endpoint,
                    method='GET',
                    response_time=response_time,
                    status_code=200 if success else 400,
                    success=success,
                    error_info={'message': error} if error else None
                )
                
                session.commit()
        except Exception as e:
            logger.error(f"Error logging API call: {str(e)}")
    
    def get_current_usage_limits(self) -> dict:
        """Get current API usage limits from database"""
        try:
            with db_config.get_session() as session:
                api_usage_repo = APIUsageRepository(session)
                limits = api_usage_repo.get_current_limits('twitter')
                return limits
        except Exception as e:
            logger.error(f"Error getting usage limits: {str(e)}")
            return {'daily_requests': 0, 'monthly_requests': 0}
    
    def can_make_request(self) -> bool:
        """Check if we can make a Twitter API request without exceeding limits"""
        try:
            limits = self.get_current_usage_limits()
            return limits['daily_requests'] < settings.TWITTER_FREE_DAILY_LIMIT
        except:
            return True  # Allow if can't check limits
    
    def can_post_tweet(self) -> bool:
        """Check if we can post a tweet without exceeding monthly limit"""
        try:
            limits = self.get_current_usage_limits()
            return limits['monthly_requests'] < settings.TWITTER_FREE_MONTHLY_LIMIT
        except:
            return True  # Allow if can't check limits
    
    def get_last_tweet_id(self) -> Optional[str]:
        """Get the ID of the last processed tweet from database"""
        try:
            with db_config.get_session() as session:
                system_state_repo = SystemStateRepository(session)
                return system_state_repo.get_last_tweet_id()
        except Exception as e:
            logger.error(f"Error getting last tweet ID: {str(e)}")
            return None
    
    def save_last_tweet_id(self, tweet_id: str):
        """Save the ID of the last processed tweet to database"""
        try:
            with db_config.get_session() as session:
                system_state_repo = SystemStateRepository(session)
                system_state_repo.set_last_tweet_id(tweet_id)
                session.commit()
                logger.debug(f"Saved last tweet ID: {tweet_id}")
        except Exception as e:
            logger.error(f"Error saving last tweet ID: {str(e)}")
    
    def get_new_tweets(self) -> List[Tweet]:
        """Get new tweets from the primary account and store them in database"""
        if not self.api:
            logger.error("❌ Twitter API not initialized. Need API keys in .env file")
            return []
        
        if not self.can_make_request():
            logger.warning("⚠️ Daily API request limit reached, skipping tweet fetch")
            return []
        
        start_time = datetime.now()
        new_tweets = []
        
        try:
            # Get last processed tweet ID
            last_tweet_id = self.get_last_tweet_id()
            
            # Fetch tweets from primary account
            tweets = self.api.user_timeline(
                screen_name=settings.PRIMARY_ACCOUNT_USERNAME,
                count=settings.MAX_TWEETS_PER_POLL,
                since_id=last_tweet_id,
                include_rts=False,
                exclude_replies=True,
                tweet_mode='extended'
            )
            
            # Log API call
            response_time = (datetime.now() - start_time).total_seconds()
            self.log_api_call('user_timeline', success=True, response_time=response_time)
            
            if not tweets:
                logger.info("📭 No new tweets found")
                return []
            
            # Process and store tweets in database
            with db_config.get_session() as session:
                tweet_repo = TweetRepository(session)
                
                for tweet_data in reversed(tweets):  # Process oldest first
                    try:
                        # Create Tweet object
                        tweet = Tweet(
                            id=str(tweet_data.id),
                            text=tweet_data.full_text,
                            created_at=tweet_data.created_at.replace(tzinfo=timezone.utc),
                            author_username=tweet_data.user.screen_name,
                            author_id=str(tweet_data.user.id),
                            public_metrics={
                                'retweet_count': tweet_data.retweet_count,
                                'favorite_count': tweet_data.favorite_count,
                                'reply_count': getattr(tweet_data, 'reply_count', 0),
                                'quote_count': getattr(tweet_data, 'quote_count', 0)
                            },
                            in_reply_to_user_id=str(tweet_data.in_reply_to_user_id) if tweet_data.in_reply_to_user_id else None,
                            referenced_tweets=[],
                            entities=tweet_data.entities if hasattr(tweet_data, 'entities') else {}
                        )
                        
                        # Store in database (if not already exists)
                        existing_tweet = tweet_repo.get_by_id(tweet.id)
                        if not existing_tweet:
                            tweet_repo.create_from_tweet_object(tweet)
                            logger.info(f"📝 Stored new tweet {tweet.id} in database")
                        
                        new_tweets.append(tweet)
                        
                    except Exception as e:
                        logger.error(f"Error processing tweet {tweet_data.id}: {str(e)}")
                        continue
                
                # Update last processed tweet ID
                if new_tweets:
                    latest_tweet_id = max(tweet.id for tweet in new_tweets)
                    self.save_last_tweet_id(latest_tweet_id)
                
                session.commit()
                logger.info(f"🔍 Found {len(new_tweets)} new tweets")
            
            return new_tweets
            
        except tweepy.TweepyException as e:
            # Log API call failure
            response_time = (datetime.now() - start_time).total_seconds()
            self.log_api_call('user_timeline', success=False, response_time=response_time, error=str(e))
            
            if hasattr(e, 'response') and e.response:
                if e.response.status_code == 429:
                    logger.warning("⚠️ Twitter API rate limit exceeded")
                elif e.response.status_code == 401:
                    logger.error("❌ Twitter API authentication failed - check credentials")
                elif e.response.status_code == 403:
                    logger.error("❌ Twitter API access forbidden - account may be suspended")
                else:
                    logger.error(f"❌ Twitter API error {e.response.status_code}: {str(e)}")
            else:
                logger.error(f"❌ Twitter API error: {str(e)}")
            return []
            
        except Exception as e:
            # Log API call failure
            response_time = (datetime.now() - start_time).total_seconds()
            self.log_api_call('user_timeline', success=False, response_time=response_time, error=str(e))
            
            logger.error(f"❌ Unexpected error fetching tweets: {str(e)}")
            return []
    
    def get_tweet_history(self, limit: int = 50) -> List[Tweet]:
        """Get tweet history from database"""
        try:
            with db_config.get_session() as session:
                tweet_repo = TweetRepository(session)
                db_tweets = tweet_repo.get_recent_tweets(hours=24*30, limit=limit)  # Last 30 days
                
                tweets = []
                for db_tweet in db_tweets:
                    tweet = Tweet(
                        id=db_tweet.id,
                        text=db_tweet.text,
                        created_at=db_tweet.created_at,
                        author_username=db_tweet.author_username,
                        author_id=db_tweet.author_id,
                        public_metrics=db_tweet.public_metrics,
                        in_reply_to_user_id=db_tweet.in_reply_to_user_id,
                        referenced_tweets=db_tweet.referenced_tweets,
                        entities=db_tweet.entities
                    )
                    tweets.append(tweet)
                
                return tweets
                
        except Exception as e:
            logger.error(f"Error getting tweet history: {str(e)}")
            return []
    
    def get_api_statistics(self) -> dict:
        """Get API usage statistics from database"""
        try:
            with db_config.get_session() as session:
                api_usage_repo = APIUsageRepository(session)
                
                daily_stats = api_usage_repo.get_daily_usage('twitter')
                monthly_stats = api_usage_repo.get_monthly_usage('twitter')
                current_limits = api_usage_repo.get_current_limits('twitter')
                
                return {
                    'daily_stats': daily_stats,
                    'monthly_stats': monthly_stats,
                    'current_limits': current_limits,
                    'daily_limit': settings.TWITTER_FREE_DAILY_LIMIT,
                    'monthly_limit': settings.TWITTER_FREE_MONTHLY_LIMIT
                }
                
        except Exception as e:
            logger.error(f"Error getting API statistics: {str(e)}")
            return {}

# Global instance
database_twitter_monitor = DatabaseTwitterMonitor()

# Backwards compatibility
# For existing code that imports twitter_monitor
twitter_monitor = database_twitter_monitor
