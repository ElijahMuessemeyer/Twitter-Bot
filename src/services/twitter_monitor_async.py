# =============================================================================
# ASYNC TWITTER MONITORING SERVICE
# =============================================================================
# High-performance async version of Twitter monitoring with connection pooling

import asyncio
import aiohttp
import tweepy
from typing import List, Optional
import json
from datetime import datetime, timedelta
from pathlib import Path
from ..config.settings import settings
from ..utils.logger import logger
from ..utils.performance_monitor import performance_monitor
from ..models.tweet import Tweet

class AsyncTwitterMonitor:
    def __init__(self):
        self.api = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_tweet_id_file = Path('logs/last_tweet_id.txt')
        self.api_usage_file = Path('logs/api_usage.json')
        self.daily_requests = 0
        self.monthly_posts = 0
        
        # Connection pool configuration
        self.connector = None
        self._setup_connection_pool()
        
        # Performance tracking
        self._request_times = []
        
        # Rate limiting with token bucket
        self._rate_limiter = None
        
    def _setup_connection_pool(self):
        """Setup HTTP connection pool for optimal performance"""
        connector_config = {
            'limit': 100,
            'limit_per_host': 30,
            'ttl_dns_cache': 300,
            'use_dns_cache': True,
            'keepalive_timeout': 60,
            'enable_cleanup_closed': True
        }
        
        try:
            import aiodns
            connector_config['resolver'] = aiohttp.AsyncResolver()
        except ImportError:
            logger.warning("aiodns not available, using default resolver")
        
        self.connector = aiohttp.TCPConnector(**connector_config)
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def initialize(self):
        """Initialize async components"""
        # Load API usage
        await self.load_api_usage()
        
        # Initialize session with connection pooling
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(
            connector=self.connector,
            timeout=timeout,
            headers={
                'User-Agent': 'TwitterBot/1.0 (Async)',
                'Accept': 'application/json'
            }
        )
        
        # Initialize Twitter API client
        if self._has_valid_credentials():
            self.api = self._create_twitter_client(settings.PRIMARY_TWITTER_CREDS)
            logger.info("✅ Async Twitter monitor initialized")
        else:
            logger.warning("⚠️ Twitter API credentials not configured")
    
    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
        if self.connector:
            await self.connector.close()
    
    def _has_valid_credentials(self) -> bool:
        """Check if we have valid Twitter credentials"""
        creds = settings.PRIMARY_TWITTER_CREDS
        return all(creds.values()) and not any(v.startswith('your_') for v in creds.values())
    
    def _create_twitter_client(self, credentials: dict):
        """Create Twitter API client with given credentials"""
        try:
            auth = tweepy.OAuth1UserHandler(
                credentials['consumer_key'],
                credentials['consumer_secret'],
                credentials['access_token'],
                credentials['access_token_secret']
            )
            
            return tweepy.API(auth, wait_on_rate_limit=True)
        except Exception as e:
            logger.error(f"❌ Failed to create Twitter client: {str(e)}")
            return None
    
    async def load_api_usage(self):
        """Load API usage tracking from file"""
        if self.api_usage_file.exists():
            try:
                import aiofiles
                async with aiofiles.open(self.api_usage_file, 'r') as f:
                    content = await f.read()
                    usage_data = json.loads(content)
                    today = datetime.now().strftime('%Y-%m-%d')
                    month = datetime.now().strftime('%Y-%m')
                    
                    # Load daily requests
                    if usage_data.get('date') == today:
                        self.daily_requests = usage_data.get('daily_requests', 0)
                    
                    # Load monthly posts
                    if usage_data.get('month') == month:
                        self.monthly_posts = usage_data.get('monthly_posts', 0)
                        
            except Exception as e:
                logger.error(f"Error loading API usage: {str(e)}")
                self.daily_requests = 0
                self.monthly_posts = 0
        else:
            self.daily_requests = 0
            self.monthly_posts = 0
    
    async def save_api_usage(self):
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
            
            import aiofiles
            async with aiofiles.open(self.api_usage_file, 'w') as f:
                await f.write(json.dumps(usage_data, indent=2))
                
        except Exception as e:
            logger.error(f"Error saving API usage: {str(e)}")
    
    def can_make_request(self) -> bool:
        """Check if we can make a Twitter API request without exceeding limits"""
        return self.daily_requests < settings.TWITTER_FREE_DAILY_LIMIT
    
    def can_post_tweet(self) -> bool:
        """Check if we can post a tweet without exceeding monthly limit"""
        return self.monthly_posts < settings.TWITTER_FREE_MONTHLY_LIMIT
    
    async def get_last_tweet_id(self) -> Optional[str]:
        """Get the ID of the last processed tweet"""
        if self.last_tweet_id_file.exists():
            try:
                import aiofiles
                async with aiofiles.open(self.last_tweet_id_file, 'r') as f:
                    return (await f.read()).strip()
            except Exception as e:
                logger.error(f"Error reading last tweet ID: {str(e)}")
        return None
    
    async def save_last_tweet_id(self, tweet_id: str):
        """Save the ID of the last processed tweet"""
        try:
            # Ensure logs directory exists
            Path('logs').mkdir(exist_ok=True)
            
            import aiofiles
            async with aiofiles.open(self.last_tweet_id_file, 'w') as f:
                await f.write(tweet_id)
        except Exception as e:
            logger.error(f"Error saving last tweet ID: {str(e)}")
    
    async def get_new_tweets(self) -> List[Tweet]:
        """Get new tweets from the primary account with performance monitoring"""
        if not self.api:
            logger.error("❌ Twitter API not initialized. Need API keys in .env file")
            return []
            
        if not self.can_make_request():
            logger.warning("⚠️ Daily API request limit reached, skipping tweet fetch")
            return []
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            with performance_monitor.track_operation("twitter_api_fetch"):
                last_id = await self.get_last_tweet_id()
                
                # Use asyncio.to_thread for blocking Twitter API call
                tweets_data = await asyncio.to_thread(
                    self._fetch_tweets_sync,
                    last_id
                )
                
                new_tweets = []
                latest_tweet_id = last_id
                
                for tweet_data in tweets_data:
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
                
                # Update request counter and save usage
                self.daily_requests += 1
                await self.save_api_usage()
                
                # Save the latest tweet ID
                if latest_tweet_id and latest_tweet_id != last_id:
                    await self.save_last_tweet_id(latest_tweet_id)
                
                # Track performance
                duration = asyncio.get_event_loop().time() - start_time
                self._request_times.append(duration)
                
                performance_monitor.record_api_call(
                    service="twitter",
                    operation="get_tweets",
                    duration_ms=duration * 1000,
                    success=True,
                    response_size=len(new_tweets)
                )
                
                logger.info(f"📊 Found {len(new_tweets)} new tweets from @{settings.PRIMARY_USERNAME} ({duration:.2f}s)")
                return new_tweets
                
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            performance_monitor.record_api_call(
                service="twitter",
                operation="get_tweets",
                duration_ms=duration * 1000,
                success=False,
                error=str(e)
            )
            logger.error(f"❌ Error fetching new tweets: {str(e)}")
            return []
    
    def _fetch_tweets_sync(self, last_id: Optional[str]):
        """Synchronous tweet fetching for use with asyncio.to_thread"""
        tweets = tweepy.Cursor(
            self.api.user_timeline,
            screen_name=settings.PRIMARY_USERNAME,
            since_id=last_id,
            include_rts=False,
            exclude_replies=True,
            tweet_mode='extended'
        ).items(10)
        
        return list(tweets)
    
    async def batch_get_tweets(self, tweet_ids: List[str]) -> List[Tweet]:
        """Get multiple tweets by ID in batch (for deduplication)"""
        if not self.api or not tweet_ids:
            return []
        
        try:
            with performance_monitor.track_operation("twitter_batch_fetch"):
                # Use asyncio.to_thread for blocking Twitter API call
                statuses = await asyncio.to_thread(
                    self.api.lookup_statuses,
                    tweet_ids,
                    tweet_mode='extended'
                )
                
                tweets = []
                for status in statuses:
                    tweet = Tweet(
                        id=str(status.id),
                        text=status.full_text,
                        created_at=status.created_at,
                        author_username=status.user.screen_name,
                        author_id=str(status.user.id),
                        public_metrics={
                            'retweet_count': status.retweet_count,
                            'favorite_count': status.favorite_count
                        }
                    )
                    tweets.append(tweet)
                
                return tweets
                
        except Exception as e:
            logger.error(f"❌ Error in batch tweet fetch: {str(e)}")
            return []
    
    def get_performance_metrics(self) -> dict:
        """Get performance metrics for monitoring"""
        if not self._request_times:
            return {
                'avg_response_time': 0,
                'min_response_time': 0,
                'max_response_time': 0,
                'total_requests': 0
            }
        
        return {
            'avg_response_time': sum(self._request_times) / len(self._request_times),
            'min_response_time': min(self._request_times),
            'max_response_time': max(self._request_times),
            'total_requests': len(self._request_times),
            'daily_requests_used': self.daily_requests,
            'monthly_posts_used': self.monthly_posts
        }

# Global async monitor instance (lazy initialization)
twitter_monitor_async = None

def get_twitter_monitor_async():
    """Get or create the global async monitor instance"""
    global twitter_monitor_async
    if twitter_monitor_async is None:
        twitter_monitor_async = AsyncTwitterMonitor()
    return twitter_monitor_async
