#!/usr/bin/env python3
# =============================================================================
# ASYNC TWITTER AUTO-TRANSLATION BOT - HIGH PERFORMANCE VERSION
# =============================================================================
# Async implementation with concurrent processing, connection pooling,
# batch operations, and comprehensive performance monitoring

import asyncio
import time
import sys
from typing import List, Dict
from src.services.twitter_monitor_async import get_twitter_monitor_async
from src.services.gemini_translator_async import get_gemini_translator_async
from src.services.publisher_async import get_twitter_publisher_async
from src.config.settings import settings
from src.config.validator import validate_and_print
from src.utils.logger import logger
from src.utils.structured_logger import structured_logger
from src.utils.performance_monitor import performance_monitor
from src.utils.async_cache import async_translation_cache
from src.models.tweet import Translation, Tweet
from draft_manager import draft_manager

class AsyncTwitterTranslationBot:
    def __init__(self):
        self.running = False
        self.session_start_time = time.time()
        
        # Performance configuration
        self.batch_size = 5
        self.max_concurrent_translations = 10
        self.translation_timeout = 60  # seconds
        
        # Deduplication
        self.processed_tweet_ids = set()
        
        logger.info("🚀 Async Twitter Translation Bot initialized")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()
    
    async def initialize(self):
        """Initialize all async components"""
        logger.info("🔧 Initializing async components...")
        
        # Initialize performance monitor
        performance_monitor.start_monitoring()
        await performance_monitor.load_metrics()
        
        # Initialize cache
        await async_translation_cache.initialize()
        
        # Get and initialize services (lazy initialization)
        self.twitter_monitor = get_twitter_monitor_async()
        self.gemini_translator = get_gemini_translator_async()
        self.twitter_publisher = get_twitter_publisher_async()
        
        await self.twitter_monitor.initialize()
        await self.gemini_translator.initialize()
        await self.twitter_publisher.initialize()
        
        logger.info("✅ All async components initialized")
    
    async def cleanup(self):
        """Clean up all async resources"""
        logger.info("🧹 Cleaning up async resources...")
        
        # Stop monitoring
        performance_monitor.stop_monitoring()
        await performance_monitor.save_metrics()
        
        # Close services
        if hasattr(self, 'twitter_monitor'):
            await self.twitter_monitor.close()
        if hasattr(self, 'gemini_translator'):
            await self.gemini_translator.close()
        if hasattr(self, 'twitter_publisher'):
            await self.twitter_publisher.close()
        await async_translation_cache.close()
        
        logger.info("✅ Cleanup completed")
    
    async def process_new_tweets(self):
        """Main async processing function with performance optimizations"""
        logger.info("🔍 Checking for new tweets (async)...")
        
        try:
            async with performance_monitor.track_async_operation("full_processing_cycle"):
                # Get new tweets
                new_tweets = await self.twitter_monitor.get_new_tweets()
                
                if not new_tweets:
                    logger.info("📭 No new tweets found")
                    return
                
                # Remove duplicates
                unique_tweets = await self._deduplicate_tweets(new_tweets)
                if len(unique_tweets) < len(new_tweets):
                    logger.info(f"🔄 Filtered {len(new_tweets) - len(unique_tweets)} duplicate tweets")
                
                # Process tweets with different strategies based on volume
                if len(unique_tweets) == 1:
                    await self._process_single_tweet(unique_tweets[0])
                else:
                    await self._process_tweets_batch(unique_tweets)
                
        except Exception as e:
            logger.error(f"❌ Error in async process_new_tweets: {str(e)}")
    
    async def _deduplicate_tweets(self, tweets: List[Tweet]) -> List[Tweet]:
        """Remove duplicate tweets based on content and recent processing"""
        unique_tweets = []
        
        for tweet in tweets:
            if tweet.id not in self.processed_tweet_ids:
                unique_tweets.append(tweet)
                self.processed_tweet_ids.add(tweet.id)
                
                # Keep only last 1000 IDs in memory
                if len(self.processed_tweet_ids) > 1000:
                    # Remove oldest half
                    self.processed_tweet_ids = set(list(self.processed_tweet_ids)[-500:])
        
        return unique_tweets
    
    async def _process_single_tweet(self, tweet: Tweet):
        """Process a single tweet with concurrent translation"""
        logger.info(f"🔄 Processing single tweet: {tweet.id}")
        
        # Log tweet processing
        structured_logger.log_tweet_processing(
            tweet_id=tweet.id,
            text_preview=tweet.text,
            language_count=len(settings.TARGET_LANGUAGES)
        )
        
        # Translate to all languages concurrently
        translations = await self.gemini_translator.translate_concurrent(
            tweet, settings.TARGET_LANGUAGES
        )
        
        if not translations:
            logger.warning(f"⚠️ No successful translations for tweet {tweet.id}")
            return
        
        # Post translations with intelligent batching
        await self._post_translations_intelligently(translations)
        
        # Small delay for rate limiting
        await asyncio.sleep(1)
    
    async def _process_tweets_batch(self, tweets: List[Tweet]):
        """Process multiple tweets with advanced batch optimizations"""
        logger.info(f"🔄 Processing batch of {len(tweets)} tweets")
        
        # Batch translate all tweets to all languages
        batch_results = await self.gemini_translator.translate_batch(
            tweets, settings.TARGET_LANGUAGES
        )
        
        # Collect all successful translations
        all_translations = []
        for lang_code, translations in batch_results.items():
            all_translations.extend(translations)
        
        if not all_translations:
            logger.warning("⚠️ No successful translations in batch")
            return
        
        logger.info(f"✅ Batch translation completed: {len(all_translations)} translations")
        
        # Post all translations with concurrent optimization
        await self._post_translations_concurrent(all_translations)
    
    async def _post_translations_intelligently(self, translations: List[Translation]):
        """Post translations using the most efficient method"""
        if not translations:
            return
        
        successful_posts = 0
        failed_posts = 0
        
        # Group translations by whether we can post them
        postable = []
        draftable = []
        
        for translation in translations:
            if await self.twitter_publisher.can_post():
                postable.append(translation)
            else:
                draftable.append(translation)
        
        # Post what we can concurrently
        if postable:
            results = await self.twitter_publisher.post_concurrent_translations(postable)
            successful_posts = sum(1 for success in results.values() if success)
            failed_posts = len(postable) - successful_posts
        
        # Save rest as drafts
        for translation in draftable:
            lang_config = next(
                (lang for lang in settings.TARGET_LANGUAGES 
                 if lang['name'] == translation.target_language), 
                {}
            )
            await asyncio.to_thread(
                draft_manager.save_translation_as_draft,
                translation, lang_config
            )
        
        logger.info(f"📊 Posting results: {successful_posts} posted, {failed_posts} failed, {len(draftable)} drafts")
    
    async def _post_translations_concurrent(self, translations: List[Translation]):
        """Post translations with maximum concurrency"""
        if not translations:
            return
        
        # Check posting limits
        can_post_count = 0
        postable_translations = []
        
        for translation in translations:
            if await self.twitter_publisher.can_post() and can_post_count < 20:  # Reasonable limit
                postable_translations.append(translation)
                can_post_count += 1
            else:
                # Save as draft
                lang_config = next(
                    (lang for lang in settings.TARGET_LANGUAGES 
                     if lang['name'] == translation.target_language), 
                    {}
                )
                await asyncio.to_thread(
                    draft_manager.save_translation_as_draft,
                    translation, lang_config
                )
        
        if postable_translations:
            results = await self.twitter_publisher.post_concurrent_translations(postable_translations)
            successful = sum(1 for success in results.values() if success)
            logger.info(f"✅ Concurrent posting: {successful}/{len(postable_translations)} successful")
        
    async def run_once(self):
        """Run the bot once (async version)"""
        structured_logger.log_bot_lifecycle("start_single_run", mode="async_once")
        
        # Check credentials with comprehensive validation
        if not settings.validate_configuration_comprehensive():
            logger.error("❌ Configuration validation failed. Please fix the issues above.")
            return
        
        # Process tweets
        await self.process_new_tweets()
        
        # Show draft status
        draft_count = await asyncio.to_thread(draft_manager.get_draft_count)
        if draft_count > 0:
            logger.info(f"📝 Current pending drafts: {draft_count}")
        
        # Show performance summary
        self._print_performance_summary()
    
    async def run_scheduled(self, poll_interval: int = None):
        """Run the bot on a schedule (async version)"""
        logger.info("🚀 Starting Async Twitter Translation Bot (scheduled mode)")
        
        # Check credentials with comprehensive validation
        if not settings.validate_configuration_comprehensive():
            logger.error("❌ Configuration validation failed. Please fix the issues above.")
            return
        
        poll_interval = poll_interval or settings.POLL_INTERVAL
        self.running = True
        
        structured_logger.log_bot_lifecycle("start_scheduled", mode="async_scheduled")
        
        try:
            while self.running:
                cycle_start = asyncio.get_event_loop().time()
                
                # Process tweets
                await self.process_new_tweets()
                
                # Cleanup expired cache entries periodically
                if int(time.time()) % 3600 == 0:  # Every hour
                    await async_translation_cache.cleanup_expired()
                
                # Calculate sleep time to maintain consistent intervals
                cycle_duration = asyncio.get_event_loop().time() - cycle_start
                sleep_time = max(0, poll_interval - cycle_duration)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                else:
                    logger.warning(f"⚠️ Processing cycle took {cycle_duration:.1f}s, longer than {poll_interval}s interval")
                
        except asyncio.CancelledError:
            logger.info("⚠️ Stopping bot due to cancellation")
            self.running = False
        except KeyboardInterrupt:
            logger.info("⚠️ Stopping bot due to keyboard interrupt")
            self.running = False
        except Exception as e:
            logger.error(f"❌ Unexpected error in async scheduled run: {str(e)}")
            self.running = False
    
    def stop(self):
        """Stop the scheduled bot"""
        self.running = False
        logger.info("🛑 Bot stop requested")
    
    def _print_performance_summary(self):
        """Print performance summary"""
        uptime = time.time() - self.session_start_time
        
        logger.info(f"📊 Session Performance Summary:")
        logger.info(f"   Uptime: {uptime:.1f} seconds")
        
        # Print detailed performance dashboard
        performance_monitor.print_dashboard()
        
        # Print cache stats
        async_translation_cache.print_cache_stats()
        
        # Print service performance
        monitor_metrics = self.twitter_monitor.get_performance_metrics() if hasattr(self, 'twitter_monitor') else {}
        translator_metrics = self.gemini_translator.get_performance_metrics() if hasattr(self, 'gemini_translator') else {}
        publisher_metrics = self.twitter_publisher.get_performance_metrics() if hasattr(self, 'twitter_publisher') else {}
        
        logger.info(f"🔍 Twitter Monitor: {monitor_metrics.get('total_requests', 0)} requests, {monitor_metrics.get('avg_response_time', 0):.2f}s avg")
        logger.info(f"🌐 Translator: {translator_metrics.get('total_translations', 0)} translations, {translator_metrics.get('cache_hit_rate', 0):.1f}% cache hit rate")
        logger.info(f"📤 Publisher: {publisher_metrics.get('total_post_attempts', 0)} attempts, {publisher_metrics.get('success_rate_percent', 0):.1f}% success rate")

async def main():
    """Main async entry point"""
    command = sys.argv[1].lower() if len(sys.argv) > 1 else 'scheduled'
    
    async with AsyncTwitterTranslationBot() as bot:
        if command == 'once':
            await bot.run_once()
        elif command == 'drafts':
            await asyncio.to_thread(draft_manager.display_pending_drafts)
        elif command == 'status':
            monitor = get_twitter_monitor_async()
            await monitor.load_api_usage()
            print(f"📊 API Usage Status:")
            print(f"  Daily requests: {monitor.daily_requests}/{settings.TWITTER_FREE_DAILY_LIMIT}")
            print(f"  Monthly posts: {monitor.monthly_posts}/{settings.TWITTER_FREE_MONTHLY_LIMIT}")
            print(f"  Pending drafts: {await asyncio.to_thread(draft_manager.get_draft_count)}")
        elif command == 'cache':
            cache_info = async_translation_cache.get_cache_info()
            async_translation_cache.print_cache_stats()
        elif command == 'performance' or command == 'perf':
            performance_monitor.print_dashboard()
        elif command == 'test':
            logger.info("🧪 Testing async API connections...")
            if settings.validate_configuration_comprehensive():
                publisher = get_twitter_publisher_async()
                await publisher.initialize()
                await publisher.test_connections()
                await publisher.close()
            else:
                logger.error("❌ Cannot test connections - missing API credentials")
        elif command == 'benchmark':
            logger.info("🏁 Running performance benchmark...")
            await run_benchmark()
        else:
            print("Usage: python main_async.py [once|drafts|status|cache|performance|test|benchmark]")
            print("  once        - Run once and exit")
            print("  drafts      - Show pending drafts")
            print("  status      - Show API usage status")
            print("  cache       - Show translation cache performance")
            print("  performance - Show detailed performance metrics")
            print("  test        - Test API connections")
            print("  benchmark   - Run performance benchmark")
            print("  (no args)   - Run continuously on schedule")
            return
        
        if command not in ['once', 'drafts', 'status', 'cache', 'performance', 'test', 'benchmark']:
            await bot.run_scheduled()

async def run_benchmark():
    """Run performance benchmarks"""
    logger.info("🏁 Starting performance benchmark...")
    
    # Create dummy tweets for benchmarking
    dummy_tweets = [
        Tweet(
            id=f"benchmark_{i}",
            text=f"This is a benchmark tweet #{i} with some test content to translate.",
            created_at=None,
            author_username="benchmark",
            author_id="benchmark",
            public_metrics={}
        )
        for i in range(10)
    ]
    
    start_time = time.time()
    
    async with AsyncTwitterTranslationBot() as bot:
        # Benchmark translation performance
        translation_start = time.time()
        
        # Initialize translator for benchmark
        translator = get_gemini_translator_async()
        await translator.initialize()
        
        # Test batch translation
        batch_results = await translator.translate_batch(
            dummy_tweets[:5], settings.TARGET_LANGUAGES[:2]  # Limit for benchmark
        )
        
        await translator.close()
        
        translation_time = time.time() - translation_start
        total_translations = sum(len(translations) for translations in batch_results.values())
        
        logger.info(f"🏁 Benchmark Results:")
        logger.info(f"   Total time: {time.time() - start_time:.2f}s")
        logger.info(f"   Translation time: {translation_time:.2f}s")
        logger.info(f"   Translations completed: {total_translations}")
        logger.info(f"   Translations/second: {total_translations/max(translation_time, 0.1):.2f}")
        
        # Print performance benchmarks
        benchmarks = performance_monitor.get_benchmarks()
        logger.info(f"   Performance tiers: {benchmarks}")

if __name__ == "__main__":
    asyncio.run(main())
