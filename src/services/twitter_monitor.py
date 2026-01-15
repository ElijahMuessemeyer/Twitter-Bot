# =============================================================================
# TWITTER MONITORING SERVICE - ENHANCED ERROR HANDLING
# =============================================================================
# TODO: You need to get Twitter API keys from https://developer.twitter.com/

import tweepy
from typing import List, Optional
import json
from datetime import datetime, timedelta
from pathlib import Path
from ..config.settings import settings
from ..utils.logger import logger
from ..models.tweet import Tweet
from ..exceptions import (
    TwitterAPIError,
    TwitterRateLimitError,
    TwitterAuthError,
    TwitterConnectionError,
    TwitterQuotaExceededError,
    NetworkError,
    ConfigurationError
)
from ..utils.retry import retry_with_backoff, RetryConfig
from ..utils.circuit_breaker import circuit_breaker_protection, CircuitBreakerConfig
from ..utils.error_recovery import recover_from_error
from ..utils.structured_logger import structured_logger

class TwitterMonitor:
    def __init__(self):
        # TODO: This will fail until you add Twitter API keys to your .env file
        if self._has_valid_credentials():
            try:
                self.api = self._create_twitter_client(settings.PRIMARY_TWITTER_CREDS)
            except (TwitterAuthError, TwitterConnectionError, ConfigurationError) as e:
                logger.error(f"Failed to initialize Twitter client: {e}")
                self.api = None
        else:
            self.api = None
            logger.warning("⚠️ Twitter API credentials not configured. Monitoring will not work.")
        
        self.last_tweet_id_file = Path('logs/last_tweet_id.txt')
        self.api_usage_file = Path('logs/api_usage.json')
        self.daily_requests = 0
        self.monthly_posts = 0
        self.load_api_usage()
    
    def _has_valid_credentials(self) -> bool:
        """Check if we have valid Twitter credentials"""
        try:
            creds = settings.PRIMARY_TWITTER_CREDS
            if not creds:
                raise ConfigurationError("PRIMARY_TWITTER_CREDS not configured")
            
            return all(creds.values()) and not any(v.startswith('your_') for v in creds.values())
        except Exception as e:
            logger.error(f"Error validating Twitter credentials: {e}")
            return False
    
    def _create_twitter_client(self, credentials: dict):
        """Create Twitter API client with given credentials"""
        try:
            if not all(key in credentials for key in ['consumer_key', 'consumer_secret', 'access_token', 'access_token_secret']):
                raise ConfigurationError("Missing required Twitter API credentials")
            
            auth = tweepy.OAuth1UserHandler(
                credentials['consumer_key'],
                credentials['consumer_secret'],
                credentials['access_token'],
                credentials['access_token_secret']
            )
            
            api = tweepy.API(auth, wait_on_rate_limit=True)
            
            # Test the connection
            try:
                api.verify_credentials()
                logger.info("✅ Twitter API client created and verified")
                return api
            except tweepy.Unauthorized:
                raise TwitterAuthError("Twitter API credentials are invalid")
            except tweepy.TooManyRequests:
                raise TwitterRateLimitError("Twitter API rate limit exceeded during verification")
            except Exception as verify_error:
                raise TwitterConnectionError(f"Failed to verify Twitter credentials: {verify_error}")
                
        except TwitterAuthError:
            raise  # Re-raise specific Twitter errors
        except TwitterRateLimitError:
            raise
        except TwitterConnectionError:
            raise
        except ConfigurationError:
            raise
        except Exception as e:
            raise TwitterAPIError(f"Failed to create Twitter client: {str(e)}")
    
    def load_api_usage(self):
        """Load API usage tracking from file"""
        if self.api_usage_file.exists():
            try:
                with open(self.api_usage_file, 'r') as f:
                    usage_data = json.load(f)
                    today = datetime.now().strftime('%Y-%m-%d')
                    month = datetime.now().strftime('%Y-%m')
                    
                    # Load daily requests
                    if usage_data.get('date') == today:
                        self.daily_requests = usage_data.get('daily_requests', 0)
                    
                    # Load monthly posts
                    if usage_data.get('month') == month:
                        self.monthly_posts = usage_data.get('monthly_posts', 0)
                        
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in API usage file: {e}")
                self._reset_api_usage()
            except FileNotFoundError:
                logger.info("API usage file not found, starting fresh")
                self._reset_api_usage()
            except Exception as e:
                logger.error(f"Error loading API usage: {str(e)}")
                self._reset_api_usage()
    
    def _reset_api_usage(self):
        """Reset API usage counters"""
        self.daily_requests = 0
        self.monthly_posts = 0
    
    def save_api_usage(self):
        """Save API usage tracking to file"""
        try:
            usage_data = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'month': datetime.now().strftime('%Y-%m'),
                'daily_requests': self.daily_requests,
                'monthly_posts': self.monthly_posts,
                'last_updated': datetime.now().isoformat()
            }
            
            # Ensure logs directory exists
            Path('logs').mkdir(exist_ok=True)
            
            with open(self.api_usage_file, 'w') as f:
                json.dump(usage_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving API usage: {str(e)}")
    
    def can_make_request(self) -> bool:
        """Check if we can make a Twitter API request without exceeding limits"""
        if self.daily_requests >= settings.TWITTER_FREE_DAILY_LIMIT:
            raise TwitterQuotaExceededError(
                "Daily request limit exceeded",
                quota_type="daily_requests",
                current_usage=self.daily_requests,
                quota_limit=settings.TWITTER_FREE_DAILY_LIMIT
            )
        return True
    
    def can_post_tweet(self) -> bool:
        """Check if we can post a tweet without exceeding monthly limit"""
        if self.monthly_posts >= settings.TWITTER_FREE_MONTHLY_LIMIT:
            raise TwitterQuotaExceededError(
                "Monthly posting limit exceeded",
                quota_type="monthly_posts",
                current_usage=self.monthly_posts,
                quota_limit=settings.TWITTER_FREE_MONTHLY_LIMIT
            )
        return True
    
    def get_last_tweet_id(self) -> Optional[str]:
        """Get the ID of the last processed tweet"""
        if self.last_tweet_id_file.exists():
            try:
                with open(self.last_tweet_id_file, 'r') as f:
                    return f.read().strip()
            except Exception as e:
                logger.error(f"Error reading last tweet ID: {str(e)}")
        return None
    
    def save_last_tweet_id(self, tweet_id: str):
        """Save the ID of the last processed tweet"""
        try:
            # Ensure logs directory exists
            Path('logs').mkdir(exist_ok=True)
            
            with open(self.last_tweet_id_file, 'w') as f:
                f.write(tweet_id)
        except Exception as e:
            logger.error(f"Error saving last tweet ID: {str(e)}")
    
    @retry_with_backoff(
        retryable_exceptions=(TwitterConnectionError, NetworkError),
        config=RetryConfig(max_attempts=3, base_delay=5.0)
    )
    @circuit_breaker_protection(
        "twitter_api",
        config=CircuitBreakerConfig(failure_threshold=5, timeout=120.0)
    )
    def get_new_tweets(self) -> List[Tweet]:
        """Get new tweets from the primary account with enhanced error handling"""
        if not self.api:
            raise ConfigurationError("Twitter API not initialized. Need API keys in .env file")
            
        try:
            # Check quota before proceeding
            self.can_make_request()
            
            last_id = self.get_last_tweet_id()
            
            # Fetch tweets from primary account
            tweets = tweepy.Cursor(
                self.api.user_timeline,
                screen_name=settings.PRIMARY_USERNAME,
                since_id=last_id,
                include_rts=False,  # Don't include retweets
                exclude_replies=True,  # Don't include replies
                tweet_mode='extended'
            ).items(10)  # Limit to 10 most recent tweets
            
            new_tweets = []
            latest_tweet_id = last_id
            
            for tweet_data in tweets:
                try:
                    # Convert tweepy Status to our Tweet model
                    tweet = Tweet(
                        id=str(tweet_data.id),
                        text=tweet_data.full_text,
                        created_at=tweet_data.created_at,
                        author_username=tweet_data.user.screen_name,
                        author_id=str(tweet_data.user.id),
                        public_metrics={
                            'retweet_count': tweet_data.retweet_count,
                            'favorite_count': tweet_data.favorite_count
                        }
                    )
                    
                    new_tweets.append(tweet)
                    latest_tweet_id = tweet.id
                    
                except Exception as tweet_error:
                    logger.warning(f"Error processing tweet {tweet_data.id}: {tweet_error}")
                    continue
            
            # Update request counter and save usage
            self.daily_requests += 1
            self.save_api_usage()
            
            # Save the latest tweet ID
            if latest_tweet_id and latest_tweet_id != last_id:
                self.save_last_tweet_id(latest_tweet_id)
            
            logger.info(f" Found {len(new_tweets)} new tweets from @{settings.PRIMARY_USERNAME}")
            
            # Log success metrics
            structured_logger.info(
                f"Successfully fetched {len(new_tweets)} tweets",
                event="twitter_fetch_success",
                tweet_count=len(new_tweets),
                daily_requests=self.daily_requests,
                username=settings.PRIMARY_USERNAME
            )
            
            return new_tweets
            
        except TwitterQuotaExceededError:
            # Don't retry quota exceeded errors, just re-raise
            raise
        except tweepy.Unauthorized:
            raise TwitterAuthError("Twitter API authentication failed - check credentials")
        except tweepy.TooManyRequests as e:
            # Extract reset time if available
            reset_time = getattr(e.response, 'headers', {}).get('x-rate-limit-reset')
            raise TwitterRateLimitError(
                "Twitter API rate limit exceeded",
                reset_time=int(reset_time) if reset_time else None
            )
        except tweepy.Forbidden:
            raise TwitterAuthError("Twitter API access forbidden - check permissions")
        except (tweepy.BadRequest, tweepy.NotFound) as e:
            raise TwitterAPIError(f"Twitter API error: {e}")
        except (ConnectionError, TimeoutError) as e:
            raise NetworkError(f"Network error while fetching tweets: {e}")
        except Exception as e:
            # Try error recovery for unknown errors
            recovery_result = recover_from_error(
                e,
                {
                    'operation_type': 'fetch_tweets',
                    'service': 'twitter_api',
                    'username': settings.PRIMARY_USERNAME
                }
            )
            
            if recovery_result['success']:
                return []  # Return empty list as fallback
            else:
                raise TwitterAPIError(f"Error fetching new tweets: {str(e)}")

# Global monitor instance
twitter_monitor = TwitterMonitor()
