#!/usr/bin/env python3
# =============================================================================
# ASYNC PERFORMANCE TESTS
# =============================================================================
# Comprehensive test suite for async performance optimizations

import asyncio
import pytest
import time
import sys
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.services.twitter_monitor_async import AsyncTwitterMonitor
from src.services.gemini_translator_async import AsyncGeminiTranslator
from src.services.publisher_async import AsyncTwitterPublisher
from src.utils.performance_monitor import PerformanceMonitor
from src.utils.async_cache import AsyncTranslationCache
from src.models.tweet import Tweet, Translation
from main_async import AsyncTwitterTranslationBot
from datetime import datetime

class TestAsyncPerformance:
    """Test suite for async performance optimizations"""
    
    @pytest.fixture
    async def mock_tweet(self):
        """Create a mock tweet for testing"""
        return Tweet(
            id="test_123",
            text="Hello world! This is a test tweet.",
            created_at=datetime.now(),
            author_username="testuser",
            author_id="user123",
            public_metrics={"retweet_count": 5, "favorite_count": 10}
        )
    
    @pytest.fixture
    async def mock_translation(self, mock_tweet):
        """Create a mock translation for testing"""
        return Translation(
            original_tweet=mock_tweet,
            target_language="Japanese",
            translated_text="こんにちは世界！これはテストツイートです。",
            translation_timestamp=datetime.now(),
            character_count=25,
            status='pending'
        )
    
    @pytest.fixture
    async def performance_monitor(self):
        """Create a performance monitor for testing"""
        monitor = PerformanceMonitor(max_history=100)
        yield monitor
        monitor.stop_monitoring()
    
    @pytest.fixture
    async def async_cache(self):
        """Create an async cache for testing"""
        cache = AsyncTranslationCache(
            cache_file='test_cache.json',
            max_entries=100,
            ttl_hours=1
        )
        await cache.initialize()
        yield cache
        await cache.close()
        # Cleanup test file
        Path('test_cache.json').unlink(missing_ok=True)

class TestAsyncTwitterMonitor(TestAsyncPerformance):
    """Test async Twitter monitor performance"""
    
    @pytest.mark.asyncio
    async def test_connection_pooling(self):
        """Test connection pool initialization"""
        monitor = AsyncTwitterMonitor()
        await monitor.initialize()
        
        assert monitor.connector is not None
        assert monitor.session is not None
        assert monitor.connector._limit == 100
        assert monitor.connector._limit_per_host == 30
        
        await monitor.close()
    
    @pytest.mark.asyncio
    async def test_concurrent_tweet_fetching(self, mock_tweet):
        """Test concurrent tweet fetching performance"""
        monitor = AsyncTwitterMonitor()
        await monitor.initialize()
        
        # Mock the sync tweet fetching
        with patch.object(monitor, '_fetch_tweets_sync', return_value=[]):
            start_time = time.time()
            tweets = await monitor.get_new_tweets()
            duration = time.time() - start_time
            
            # Should complete quickly with mocked data
            assert duration < 1.0
            assert isinstance(tweets, list)
        
        await monitor.close()
    
    @pytest.mark.asyncio
    async def test_batch_tweet_processing(self):
        """Test batch tweet ID processing"""
        monitor = AsyncTwitterMonitor()
        await monitor.initialize()
        
        tweet_ids = ["123", "456", "789"]
        
        with patch.object(monitor.api, 'lookup_statuses', return_value=[]) if monitor.api else patch('asyncio.to_thread'):
            start_time = time.time()
            tweets = await monitor.batch_get_tweets(tweet_ids)
            duration = time.time() - start_time
            
            assert duration < 2.0
            assert isinstance(tweets, list)
        
        await monitor.close()
    
    @pytest.mark.asyncio
    async def test_performance_metrics_tracking(self, performance_monitor):
        """Test performance metrics are tracked correctly"""
        monitor = AsyncTwitterMonitor()
        await monitor.initialize()
        
        # Simulate some operations
        monitor._request_times = [100, 200, 150, 300, 250]
        
        metrics = monitor.get_performance_metrics()
        
        assert metrics['avg_response_time'] == 200
        assert metrics['min_response_time'] == 100
        assert metrics['max_response_time'] == 300
        assert metrics['total_requests'] == 5
        
        await monitor.close()

class TestAsyncGeminiTranslator(TestAsyncPerformance):
    """Test async Gemini translator performance"""
    
    @pytest.mark.asyncio
    async def test_concurrent_translation(self, mock_tweet):
        """Test concurrent translation to multiple languages"""
        translator = AsyncGeminiTranslator()
        await translator.initialize()
        
        languages = [
            {'name': 'Japanese', 'code': 'ja'},
            {'name': 'Spanish', 'code': 'es'},
            {'name': 'French', 'code': 'fr'}
        ]
        
        # Mock translation calls
        with patch.object(translator, '_translate_single', new_callable=AsyncMock) as mock_translate:
            mock_translate.return_value = MagicMock(spec=Translation)
            
            start_time = time.time()
            translations = await translator.translate_concurrent(mock_tweet, languages)
            duration = time.time() - start_time
            
            # Should complete much faster than sequential
            assert duration < 3.0  # Would be 9+ seconds if sequential
            assert len(translations) <= len(languages)
        
        await translator.close()
    
    @pytest.mark.asyncio
    async def test_batch_translation_performance(self, mock_tweet):
        """Test batch translation performance"""
        translator = AsyncGeminiTranslator()
        await translator.initialize()
        
        tweets = [mock_tweet] * 3
        languages = [{'name': 'Japanese', 'code': 'ja'}]
        
        with patch.object(translator, 'translate_tweet', new_callable=AsyncMock) as mock_translate:
            mock_translate.return_value = MagicMock(spec=Translation)
            
            start_time = time.time()
            results = await translator.translate_batch(tweets, languages)
            duration = time.time() - start_time
            
            assert duration < 5.0
            assert 'ja' in results
        
        await translator.close()
    
    @pytest.mark.asyncio
    async def test_cache_performance_async(self, async_cache, mock_tweet, mock_translation):
        """Test async cache performance"""
        translator = AsyncGeminiTranslator()
        translator.cache = async_cache
        await translator.initialize()
        
        # Pre-populate cache
        await async_cache.put(mock_tweet.text, "Japanese", mock_translation)
        
        # Test cache hit performance
        start_time = time.time()
        cached_result = await translator._check_cache_async(
            mock_tweet.text, "Japanese", {}
        )
        cache_duration = time.time() - start_time
        
        assert cache_duration < 0.1  # Should be very fast
        assert cached_result is not None
        
        await translator.close()

class TestAsyncTwitterPublisher(TestAsyncPerformance):
    """Test async Twitter publisher performance"""
    
    @pytest.mark.asyncio
    async def test_concurrent_posting(self, mock_translation):
        """Test concurrent posting to multiple accounts"""
        publisher = AsyncTwitterPublisher()
        await publisher.initialize()
        
        translations = [mock_translation] * 3
        
        with patch.object(publisher, 'post_translation', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = True
            
            start_time = time.time()
            results = await publisher.post_concurrent_translations(translations)
            duration = time.time() - start_time
            
            assert duration < 5.0
            assert isinstance(results, dict)
        
        await publisher.close()
    
    @pytest.mark.asyncio
    async def test_connection_initialization_performance(self):
        """Test concurrent client initialization"""
        publisher = AsyncTwitterPublisher()
        
        start_time = time.time()
        await publisher.initialize()
        duration = time.time() - start_time
        
        # Should initialize quickly (even with mocked connections)
        assert duration < 3.0
        
        await publisher.close()
    
    @pytest.mark.asyncio
    async def test_rate_limiting_performance(self, mock_translation):
        """Test rate limiting doesn't block unnecessarily"""
        publisher = AsyncTwitterPublisher()
        publisher._min_post_interval = 0.1  # Fast for testing
        await publisher.initialize()
        
        start_time = time.time()
        can_post = await publisher._can_post_to_account('ja')
        duration = time.time() - start_time
        
        assert duration < 0.05
        assert isinstance(can_post, bool)
        
        await publisher.close()

class TestAsyncCache(TestAsyncPerformance):
    """Test async cache performance"""
    
    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, async_cache, mock_tweet, mock_translation):
        """Test concurrent cache gets and puts"""
        # Create multiple cache operations
        tasks = []
        
        # Mix of gets and puts
        for i in range(10):
            if i % 2 == 0:
                task = async_cache.put(f"text_{i}", "Japanese", mock_translation)
            else:
                task = async_cache.get(f"text_{i}", "Japanese")
            tasks.append(task)
        
        start_time = time.time()
        await asyncio.gather(*tasks)
        duration = time.time() - start_time
        
        # Should handle concurrent operations efficiently
        assert duration < 1.0
    
    @pytest.mark.asyncio
    async def test_batch_cache_operations(self, async_cache, mock_translation):
        """Test batch cache operations performance"""
        # Prepare batch data
        entries = [
            (f"text_{i}", "Japanese", mock_translation, {})
            for i in range(20)
        ]
        
        start_time = time.time()
        await async_cache.batch_put(entries)
        duration = time.time() - start_time
        
        # Batch operations should be faster than individual
        assert duration < 2.0
        
        # Test batch retrieval
        requests = [(f"text_{i}", "Japanese", {}) for i in range(20)]
        
        start_time = time.time()
        results = await async_cache.batch_get(requests)
        duration = time.time() - start_time
        
        assert duration < 1.0
        assert len(results) == 20
    
    @pytest.mark.asyncio
    async def test_cache_cleanup_performance(self, async_cache):
        """Test cache cleanup performance"""
        # Add entries that will expire quickly
        cache = AsyncTranslationCache(
            cache_file='test_cleanup_cache.json',
            max_entries=10,
            ttl_hours=0.001  # Very short TTL for testing
        )
        await cache.initialize()
        
        # Add some entries
        for i in range(5):
            translation = Translation(
                original_tweet=None,
                target_language="Japanese",
                translated_text=f"Translation {i}",
                translation_timestamp=datetime.now(),
                character_count=15,
                status='test'
            )
            await cache.put(f"text_{i}", "Japanese", translation)
        
        # Wait for expiration
        await asyncio.sleep(0.1)
        
        start_time = time.time()
        removed_count = await cache.cleanup_expired()
        duration = time.time() - start_time
        
        assert duration < 0.5
        assert removed_count >= 0
        
        await cache.close()
        Path('test_cleanup_cache.json').unlink(missing_ok=True)

class TestPerformanceMonitor(TestAsyncPerformance):
    """Test performance monitoring system"""
    
    @pytest.mark.asyncio
    async def test_concurrent_metrics_recording(self, performance_monitor):
        """Test concurrent metrics recording"""
        async def record_metrics():
            for i in range(10):
                performance_monitor.record_api_call(
                    service="test",
                    operation="concurrent_test",
                    duration_ms=100 + i,
                    success=True
                )
                await asyncio.sleep(0.01)
        
        # Run multiple concurrent recording tasks
        start_time = time.time()
        await asyncio.gather(*[record_metrics() for _ in range(5)])
        duration = time.time() - start_time
        
        # Should handle concurrent recording efficiently
        assert duration < 2.0
        
        stats = performance_monitor.get_service_stats("test")
        assert stats.total_calls == 50
    
    @pytest.mark.asyncio
    async def test_async_operation_tracking(self, performance_monitor):
        """Test async operation tracking"""
        async with performance_monitor.track_async_operation("test_operation"):
            await asyncio.sleep(0.1)
        
        stats = performance_monitor.get_service_stats("system")
        assert stats.total_calls >= 1
        assert stats.avg_duration_ms >= 100  # At least 100ms from sleep
    
    @pytest.mark.asyncio
    async def test_performance_threshold_checking(self, performance_monitor):
        """Test performance threshold monitoring"""
        # Set low thresholds for testing
        performance_monitor.thresholds['api_latency_warning_ms'] = 50
        
        # Record some high-latency operations
        for i in range(5):
            performance_monitor.record_api_call(
                service="slow_service",
                operation="slow_op",
                duration_ms=100,  # Above threshold
                success=True
            )
        
        # Trigger threshold check
        await performance_monitor._check_performance_thresholds()
        
        # Should complete without errors
        stats = performance_monitor.get_service_stats("slow_service")
        assert stats.avg_duration_ms == 100

class TestFullAsyncBot(TestAsyncPerformance):
    """Test full async bot performance"""
    
    @pytest.mark.asyncio
    async def test_async_bot_initialization_performance(self):
        """Test async bot initialization speed"""
        start_time = time.time()
        
        async with AsyncTwitterTranslationBot() as bot:
            initialization_time = time.time() - start_time
            
            # Initialization should be reasonably fast
            assert initialization_time < 10.0
            assert bot.running is False
    
    @pytest.mark.asyncio
    async def test_tweet_processing_performance(self, mock_tweet):
        """Test tweet processing pipeline performance"""
        async with AsyncTwitterTranslationBot() as bot:
            
            # Mock all external services
            with patch.object(bot, '_deduplicate_tweets', new_callable=AsyncMock) as mock_dedup, \
                 patch.object(bot, '_process_single_tweet', new_callable=AsyncMock) as mock_process:
                
                mock_dedup.return_value = [mock_tweet]
                
                start_time = time.time()
                await bot.process_new_tweets()
                duration = time.time() - start_time
                
                assert duration < 5.0
                mock_process.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_deduplication_performance(self):
        """Test tweet deduplication performance"""
        bot = AsyncTwitterTranslationBot()
        
        # Create many duplicate tweets
        tweets = [
            Tweet(
                id=f"tweet_{i % 10}",  # Creates duplicates
                text=f"Text {i % 10}",
                created_at=datetime.now(),
                author_username="test",
                author_id="test",
                public_metrics={}
            )
            for i in range(100)
        ]
        
        start_time = time.time()
        unique_tweets = await bot._deduplicate_tweets(tweets)
        duration = time.time() - start_time
        
        assert duration < 1.0
        assert len(unique_tweets) <= 10  # Should remove duplicates

# Performance benchmark functions
async def benchmark_concurrent_translations():
    """Benchmark concurrent vs sequential translations"""
    print("\n🏁 TRANSLATION CONCURRENCY BENCHMARK")
    print("="*50)
    
    # Create test tweets
    tweets = [
        Tweet(
            id=f"benchmark_{i}",
            text=f"Benchmark tweet {i} with different content",
            created_at=datetime.now(),
            author_username="benchmark",
            author_id="benchmark",
            public_metrics={}
        )
        for i in range(5)
    ]
    
    languages = [
        {'name': 'Japanese', 'code': 'ja'},
        {'name': 'Spanish', 'code': 'es'}
    ]
    
    async with AsyncGeminiTranslator() as translator:
        # Mock translation to avoid API calls
        with patch.object(translator, '_translate_single', new_callable=AsyncMock) as mock_translate:
            mock_translate.return_value = Translation(
                original_tweet=None,
                target_language="Test",
                translated_text="Test translation",
                translation_timestamp=datetime.now(),
                character_count=16,
                status='test'
            )
            
            # Sequential benchmark
            sequential_start = time.time()
            sequential_results = []
            for tweet in tweets:
                for lang in languages:
                    result = await translator.translate_tweet(tweet, lang['name'], lang)
                    sequential_results.append(result)
            sequential_time = time.time() - sequential_start
            
            # Concurrent benchmark  
            concurrent_start = time.time()
            concurrent_results = await translator.translate_batch(tweets, languages)
            concurrent_time = time.time() - concurrent_start
            
            total_concurrent = sum(len(results) for results in concurrent_results.values())
            
            print(f"Sequential: {len(sequential_results)} translations in {sequential_time:.2f}s")
            print(f"Concurrent: {total_concurrent} translations in {concurrent_time:.2f}s")
            print(f"Speedup: {sequential_time / max(concurrent_time, 0.001):.2f}x")

async def benchmark_cache_performance():
    """Benchmark cache performance improvements"""
    print("\n💾 CACHE PERFORMANCE BENCHMARK")
    print("="*50)
    
    cache = AsyncTranslationCache(
        cache_file='benchmark_cache.json',
        max_entries=1000
    )
    await cache.initialize()
    
    # Create test data
    test_translation = Translation(
        original_tweet=None,
        target_language="Japanese",
        translated_text="テストの翻訳",
        translation_timestamp=datetime.now(),
        character_count=7,
        status='test'
    )
    
    # Benchmark cache misses (fresh data)
    miss_start = time.time()
    for i in range(100):
        result = await cache.get(f"fresh_text_{i}", "Japanese")
        assert result is None  # Should be misses
    miss_time = time.time() - miss_start
    
    # Populate cache
    for i in range(100):
        await cache.put(f"cached_text_{i}", "Japanese", test_translation)
    
    # Benchmark cache hits
    hit_start = time.time()
    for i in range(100):
        result = await cache.get(f"cached_text_{i}", "Japanese")
        assert result is not None  # Should be hits
    hit_time = time.time() - hit_start
    
    print(f"Cache misses: 100 operations in {miss_time:.3f}s ({miss_time*10:.3f}ms avg)")
    print(f"Cache hits: 100 operations in {hit_time:.3f}s ({hit_time*10:.3f}ms avg)")
    print(f"Cache speedup: {miss_time / max(hit_time, 0.001):.2f}x")
    
    await cache.close()
    Path('benchmark_cache.json').unlink(missing_ok=True)

if __name__ == "__main__":
    # Run benchmarks if called directly
    async def main():
        await benchmark_concurrent_translations()
        await benchmark_cache_performance()
    
    asyncio.run(main())
