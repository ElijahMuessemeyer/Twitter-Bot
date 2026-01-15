# =============================================================================
# ASYNC TWITTER PUBLISHER SERVICE
# =============================================================================
# High-performance async version with concurrent posting and connection pooling

import asyncio
import aiohttp
import tweepy
from typing import Dict, Optional, List, Tuple
import time
from ..config.settings import settings
from ..utils.logger import logger
from ..utils.performance_monitor import performance_monitor
from ..models.tweet import Translation
from ..services.twitter_monitor_async import get_twitter_monitor_async

class AsyncTwitterPublisher:
    def __init__(self):
        self.language_clients = {}
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Performance tracking
        self._post_times = []
        self._successful_posts = 0
        self._failed_posts = 0
        
        # Rate limiting
        self._last_post_times = {}
        self._min_post_interval = 5  # seconds between posts per account
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def initialize(self):
        """Initialize async components"""
        # Initialize language clients
        await self._initialize_language_clients_async()
        
        # Setup HTTP session
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=aiohttp.TCPConnector(
                limit=50,
                limit_per_host=20,
                keepalive_timeout=60
            )
        )
        
        logger.info("✅ Async Twitter publisher initialized")
    
    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
    
    async def _initialize_language_clients_async(self):
        """Initialize Twitter API clients for each language account asynchronously"""
        initialization_tasks = []
        
        for lang_config in settings.TARGET_LANGUAGES:
            task = asyncio.create_task(
                self._init_single_client(lang_config),
                name=f"init_client_{lang_config['code']}"
            )
            initialization_tasks.append(task)
        
        # Initialize all clients concurrently
        results = await asyncio.gather(*initialization_tasks, return_exceptions=True)
        
        successful_inits = 0
        for i, result in enumerate(results):
            lang_config = settings.TARGET_LANGUAGES[i]
            if isinstance(result, Exception):
                logger.error(f"❌ Failed to initialize client for {lang_config['code']}: {str(result)}")
            elif result:
                successful_inits += 1
        
        logger.info(f"📊 Initialized {successful_inits}/{len(settings.TARGET_LANGUAGES)} Twitter clients")
    
    async def _init_single_client(self, lang_config: dict) -> bool:
        """Initialize a single Twitter client"""
        lang_code = lang_config['code']
        
        try:
            credentials = await asyncio.to_thread(
                settings.get_twitter_creds_for_language,
                lang_code
            )
            
            # Check if we have valid credentials
            if all(credentials.values()) and not any(v.startswith('your_') for v in credentials.values()):
                auth = tweepy.OAuth1UserHandler(
                    credentials['consumer_key'],
                    credentials['consumer_secret'],
                    credentials['access_token'],
                    credentials['access_token_secret']
                )
                
                client = tweepy.API(auth, wait_on_rate_limit=True)
                self.language_clients[lang_code] = client
                logger.info(f"✅ Initialized Twitter client for {lang_code}")
                return True
            else:
                logger.warning(f"⚠️ Missing or invalid credentials for {lang_code} Twitter account")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Twitter client for {lang_code}: {str(e)}")
            return False
    
    async def can_post(self) -> bool:
        """Check if we can post without exceeding API limits"""
        monitor = get_twitter_monitor_async()
        return await asyncio.to_thread(monitor.can_post_tweet)
    
    async def post_translation(self, translation: Translation) -> bool:
        """Post a translation to the appropriate language account with performance tracking"""
        if not await self.can_post():
            logger.warning("⚠️ Monthly posting limit reached, cannot post translation")
            return False
        
        lang_code = translation.target_language.lower()
        
        # Map full language names to codes if needed
        lang_code_map = {
            'japanese': 'ja',
            'german': 'de',
            'spanish': 'es',
            'french': 'fr'
        }
        
        if lang_code in lang_code_map:
            lang_code = lang_code_map[lang_code]
        
        if lang_code not in self.language_clients:
            logger.error(f"❌ No Twitter client available for language: {lang_code}")
            return False
        
        # Rate limiting check
        if not await self._can_post_to_account(lang_code):
            logger.warning(f"⚠️ Rate limit reached for {lang_code}, waiting...")
            await asyncio.sleep(self._min_post_interval)
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            with performance_monitor.track_operation(f"twitter_post_{lang_code}"):
                client = self.language_clients[lang_code]
                
                # Post the tweet using thread executor
                status = await asyncio.to_thread(
                    client.update_status,
                    translation.translated_text
                )
                
                # Update translation status
                translation.status = 'posted'
                translation.post_id = str(status.id)
                
                # Update API usage counter
                monitor = get_twitter_monitor_async()
                monitor.monthly_posts += 1
                await monitor.save_api_usage()
                
                # Update rate limiting tracker
                self._last_post_times[lang_code] = asyncio.get_event_loop().time()
                
                # Track performance
                duration = (asyncio.get_event_loop().time() - start_time) * 1000
                self._post_times.append(duration)
                self._successful_posts += 1
                
                performance_monitor.record_api_call(
                    service="twitter",
                    operation="post_tweet",
                    duration_ms=duration,
                    success=True,
                    response_size=len(translation.translated_text)
                )
                
                logger.info(f"✅ Successfully posted translation to {lang_code}: {status.id} ({duration:.1f}ms)")
                return True
                
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start_time) * 1000
            self._failed_posts += 1
            
            performance_monitor.record_api_call(
                service="twitter",
                operation="post_tweet",
                duration_ms=duration,
                success=False,
                error=str(e)
            )
            
            logger.error(f"❌ Error posting translation to {lang_code}: {str(e)}")
            translation.status = 'failed'
            translation.error_message = str(e)
            return False
    
    async def _can_post_to_account(self, lang_code: str) -> bool:
        """Check if enough time has passed since last post to this account"""
        if lang_code not in self._last_post_times:
            return True
        
        time_since_last = asyncio.get_event_loop().time() - self._last_post_times[lang_code]
        return time_since_last >= self._min_post_interval
    
    async def post_multiple_translations(self, translations: List[Translation]) -> Dict[str, bool]:
        """Post multiple translations concurrently with intelligent batching"""
        if not translations:
            return {}
        
        results = {}
        
        # Group translations by language to avoid rate limiting
        language_groups = {}
        for translation in translations:
            lang_code = translation.target_language.lower()
            if lang_code not in language_groups:
                language_groups[lang_code] = []
            language_groups[lang_code].append(translation)
        
        # Process each language group with appropriate delays
        for lang_code, lang_translations in language_groups.items():
            logger.info(f"📊 Posting {len(lang_translations)} translations to {lang_code}")
            
            for translation in lang_translations:
                if not await self.can_post():
                    logger.warning("⚠️ Reached API limits, stopping batch posting")
                    results[f"{translation.original_tweet.id}_{lang_code}"] = False
                    break
                
                success = await self.post_translation(translation)
                results[f"{translation.original_tweet.id}_{lang_code}"] = success
                
                # Small delay between posts to same language to respect rate limits
                if success and len(lang_translations) > 1:
                    await asyncio.sleep(2)
        
        successful = sum(1 for success in results.values() if success)
        logger.info(f"📊 Batch posting completed: {successful}/{len(results)} successful")
        
        return results
    
    async def post_concurrent_translations(self, translations: List[Translation]) -> Dict[str, bool]:
        """Post translations concurrently (different languages only)"""
        if not translations:
            return {}
        
        # Group by language to avoid concurrent posts to same account
        language_groups = {}
        for translation in translations:
            lang_code = translation.target_language.lower()
            if lang_code not in language_groups:
                language_groups[lang_code] = []
            language_groups[lang_code].append(translation)
        
        # Create tasks for first translation of each language (concurrent)
        # Then handle remaining translations sequentially per language
        concurrent_tasks = []
        sequential_translations = []
        
        for lang_code, lang_translations in language_groups.items():
            if lang_translations:
                # First translation can be posted concurrently
                task = asyncio.create_task(
                    self.post_translation(lang_translations[0]),
                    name=f"post_{lang_translations[0].original_tweet.id}_{lang_code}"
                )
                concurrent_tasks.append((task, lang_translations[0]))
                
                # Remaining translations need sequential processing
                if len(lang_translations) > 1:
                    sequential_translations.extend(lang_translations[1:])
        
        results = {}
        
        # Execute concurrent posts
        logger.info(f"🔄 Starting concurrent posting: {len(concurrent_tasks)} translations")
        for task, translation in concurrent_tasks:
            try:
                success = await task
                results[f"{translation.original_tweet.id}_{translation.target_language}"] = success
            except Exception as e:
                logger.error(f"❌ Concurrent post failed: {str(e)}")
                results[f"{translation.original_tweet.id}_{translation.target_language}"] = False
        
        # Execute sequential posts
        if sequential_translations:
            logger.info(f"🔄 Starting sequential posting: {len(sequential_translations)} translations")
            for translation in sequential_translations:
                if not await self.can_post():
                    break
                success = await self.post_translation(translation)
                results[f"{translation.original_tweet.id}_{translation.target_language}"] = success
                await asyncio.sleep(1)  # Small delay between sequential posts
        
        successful = sum(1 for success in results.values() if success)
        logger.info(f"✅ Concurrent posting completed: {successful}/{len(results)} successful")
        
        return results
    
    def get_available_languages(self) -> List[str]:
        """Get list of languages we can actually post to (have valid credentials)"""
        return list(self.language_clients.keys())
    
    async def test_connections(self):
        """Test all language account connections asynchronously"""
        logger.info("🧪 Testing Twitter connections for all language accounts...")
        
        if not self.language_clients:
            logger.warning("⚠️ No language accounts configured!")
            return
        
        test_tasks = []
        for lang_code, client in self.language_clients.items():
            task = asyncio.create_task(
                self._test_single_connection(lang_code, client),
                name=f"test_{lang_code}"
            )
            test_tasks.append(task)
        
        # Test all connections concurrently
        results = await asyncio.gather(*test_tasks, return_exceptions=True)
        
        successful_tests = 0
        for i, result in enumerate(results):
            lang_codes = list(self.language_clients.keys())
            lang_code = lang_codes[i]
            
            if isinstance(result, Exception):
                logger.error(f"❌ {lang_code}: Connection test failed - {str(result)}")
            elif result:
                successful_tests += 1
        
        logger.info(f"📊 Connection tests completed: {successful_tests}/{len(self.language_clients)} successful")
    
    async def _test_single_connection(self, lang_code: str, client) -> bool:
        """Test a single connection"""
        try:
            # Try to get account info
            user = await asyncio.to_thread(client.verify_credentials)
            logger.info(f"✅ {lang_code}: Connected as @{user.screen_name}")
            return True
        except Exception as e:
            logger.error(f"❌ {lang_code}: Connection failed - {str(e)}")
            return False
    
    def get_performance_metrics(self) -> dict:
        """Get publishing performance metrics"""
        total_posts = self._successful_posts + self._failed_posts
        success_rate = (self._successful_posts / total_posts * 100) if total_posts > 0 else 0
        
        avg_time = sum(self._post_times) / len(self._post_times) if self._post_times else 0
        
        return {
            'total_post_attempts': total_posts,
            'successful_posts': self._successful_posts,
            'failed_posts': self._failed_posts,
            'success_rate_percent': success_rate,
            'avg_post_time_ms': avg_time,
            'min_post_time_ms': min(self._post_times) if self._post_times else 0,
            'max_post_time_ms': max(self._post_times) if self._post_times else 0,
            'available_languages': len(self.language_clients)
        }

# Global async publisher instance (lazy initialization)
twitter_publisher_async = None

def get_twitter_publisher_async():
    """Get or create the global async publisher instance"""
    global twitter_publisher_async
    if twitter_publisher_async is None:
        twitter_publisher_async = AsyncTwitterPublisher()
    return twitter_publisher_async
