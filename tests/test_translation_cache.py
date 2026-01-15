# =============================================================================
# TRANSLATION CACHE TESTS
# =============================================================================

import pytest
import sys
import os
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils.translation_cache import IntelligentTranslationCache, CacheEntry, CacheMetrics
from src.models.tweet import Tweet, Translation

class TestCacheEntry:
    def test_cache_entry_creation(self):
        """Test cache entry creation"""
        tweet = Tweet(
            id="123",
            text="Test tweet",
            created_at=datetime.now(),
            author_username="test",
            author_id="123",
            public_metrics={}
        )
        
        translation = Translation(
            original_tweet=tweet,
            target_language="Spanish",
            translated_text="Tweet de prueba",
            translation_timestamp=datetime.now(),
            character_count=15,
            status="pending"
        )
        
        entry = CacheEntry(
            translation=translation,
            created_at=time.time(),
            access_count=0,
            last_accessed=time.time(),
            cache_key="test_key"
        )
        
        assert entry.translation == translation
        assert entry.access_count == 0
        assert entry.cache_key == "test_key"
    
    def test_cache_entry_expiration(self):
        """Test cache entry expiration logic"""
        tweet = Tweet(
            id="123",
            text="Test",
            created_at=datetime.now(),
            author_username="test",
            author_id="123",
            public_metrics={}
        )
        
        translation = Translation(
            original_tweet=tweet,
            target_language="Spanish",
            translated_text="Prueba",
            translation_timestamp=datetime.now(),
            character_count=6,
            status="pending"
        )
        
        # Create entry that's 2 hours old
        old_time = time.time() - (2 * 3600)  # 2 hours ago
        entry = CacheEntry(
            translation=translation,
            created_at=old_time,
            access_count=5,
            last_accessed=time.time(),
            cache_key="test_key"
        )
        
        # Should not be expired with 3 hour TTL
        assert entry.is_expired(3 * 3600) == False
        
        # Should be expired with 1 hour TTL
        assert entry.is_expired(1 * 3600) == True
    
    def test_cache_entry_touch(self):
        """Test cache entry touch functionality"""
        tweet = Tweet(
            id="123",
            text="Test",
            created_at=datetime.now(),
            author_username="test",
            author_id="123",
            public_metrics={}
        )
        
        translation = Translation(
            original_tweet=tweet,
            target_language="Spanish",
            translated_text="Prueba",
            translation_timestamp=datetime.now(),
            character_count=6,
            status="pending"
        )
        
        entry = CacheEntry(
            translation=translation,
            created_at=time.time(),
            access_count=0,
            last_accessed=time.time() - 100,  # 100 seconds ago
            cache_key="test_key"
        )
        
        original_access_count = entry.access_count
        original_last_accessed = entry.last_accessed
        
        entry.touch()
        
        assert entry.access_count == original_access_count + 1
        assert entry.last_accessed > original_last_accessed

class TestCacheMetrics:
    def test_cache_metrics_creation(self):
        """Test cache metrics creation and defaults"""
        metrics = CacheMetrics()
        
        assert metrics.hits == 0
        assert metrics.misses == 0
        assert metrics.evictions == 0
        assert metrics.size == 0
        assert metrics.memory_usage_mb == 0.0
    
    def test_cache_metrics_hit_rate_calculation(self):
        """Test hit rate calculation"""
        metrics = CacheMetrics()
        
        # No requests yet
        assert metrics.hit_rate == 0.0
        
        # 7 hits, 3 misses = 70% hit rate
        metrics.hits = 7
        metrics.misses = 3
        assert metrics.hit_rate == 70.0
        
        # 10 hits, 0 misses = 100% hit rate
        metrics.hits = 10
        metrics.misses = 0
        assert metrics.hit_rate == 100.0
    
    def test_cache_metrics_reset(self):
        """Test metrics reset functionality"""
        metrics = CacheMetrics()
        metrics.hits = 10
        metrics.misses = 5
        metrics.evictions = 2
        
        metrics.reset()
        
        assert metrics.hits == 0
        assert metrics.misses == 0
        assert metrics.evictions == 0

class TestIntelligentTranslationCache:
    def setup_method(self):
        """Set up test fixtures"""
        self.cache = IntelligentTranslationCache(
            max_size=100,
            ttl_hours=1,
            cleanup_interval_minutes=5
        )
        
        self.test_tweet = Tweet(
            id="123456789",
            text="Hello world! #test @user https://example.com",
            created_at=datetime.now(),
            author_username="testuser",
            author_id="987654321",
            public_metrics={}
        )
        
        self.test_translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Spanish",
            translated_text="¡Hola mundo! #test @user https://example.com",
            translation_timestamp=datetime.now(),
            character_count=45,
            status="pending"
        )
    
    def test_cache_initialization(self):
        """Test cache initialization with parameters"""
        cache = IntelligentTranslationCache(
            max_size=500,
            ttl_hours=12,
            cleanup_interval_minutes=15
        )
        
        assert cache.max_size == 500
        assert cache.ttl_seconds == 12 * 3600
        assert cache.cleanup_interval == 15 * 60
        assert len(cache._cache) == 0
        assert cache.metrics.size == 0
    
    def test_generate_cache_key_basic(self):
        """Test basic cache key generation"""
        key1 = self.cache._generate_cache_key("Hello world", "Spanish")
        key2 = self.cache._generate_cache_key("Hello world", "Spanish")
        key3 = self.cache._generate_cache_key("Hello world", "French")
        key4 = self.cache._generate_cache_key("Goodbye world", "Spanish")
        
        # Same content and language should produce same key
        assert key1 == key2
        
        # Different language should produce different key
        assert key1 != key3
        
        # Different content should produce different key
        assert key1 != key4
    
    def test_generate_cache_key_with_config(self):
        """Test cache key generation with language config"""
        config1 = {"formal_tone": True, "cultural_adaptation": True}
        config2 = {"formal_tone": False, "cultural_adaptation": True}
        config3 = {"formal_tone": True, "cultural_adaptation": True}
        
        key1 = self.cache._generate_cache_key("Hello", "Spanish", config1)
        key2 = self.cache._generate_cache_key("Hello", "Spanish", config2)
        key3 = self.cache._generate_cache_key("Hello", "Spanish", config3)
        
        # Different configs should produce different keys
        assert key1 != key2
        
        # Same configs should produce same keys
        assert key1 == key3
    
    def test_generate_cache_key_normalization(self):
        """Test that cache key normalizes whitespace"""
        key1 = self.cache._generate_cache_key("Hello   world", "Spanish")
        key2 = self.cache._generate_cache_key("Hello world", "Spanish")
        key3 = self.cache._generate_cache_key("  Hello world  ", "Spanish")
        
        # All should produce the same key after normalization
        assert key1 == key2 == key3
    
    def test_cache_put_and_get_basic(self):
        """Test basic cache put and get operations"""
        tweet_text = "Hello world"
        target_language = "Spanish"
        
        # Should be cache miss initially
        result = self.cache.get(tweet_text, target_language)
        assert result is None
        assert self.cache.metrics.misses == 1
        
        # Put translation in cache
        self.cache.put(tweet_text, target_language, self.test_translation)
        
        # Should be cache hit now
        result = self.cache.get(tweet_text, target_language)
        assert result is not None
        assert result.translated_text == self.test_translation.translated_text
        assert self.cache.metrics.hits == 1
    
    def test_cache_content_deduplication(self):
        """Test that identical content shares cache regardless of tweet ID"""
        same_text = "Hello world!"
        
        # Create different tweets with same content
        tweet1 = Tweet(
            id="111", text=same_text, created_at=datetime.now(),
            author_username="user1", author_id="111", public_metrics={}
        )
        tweet2 = Tweet(
            id="222", text=same_text, created_at=datetime.now(),
            author_username="user2", author_id="222", public_metrics={}
        )
        
        translation1 = Translation(
            original_tweet=tweet1, target_language="Spanish",
            translated_text="¡Hola mundo!", translation_timestamp=datetime.now(),
            character_count=12, status="pending"
        )
        
        # Put first translation
        self.cache.put(same_text, "Spanish", translation1)
        
        # Get with second tweet (same content) - should hit cache
        result = self.cache.get(same_text, "Spanish")
        assert result is not None
        assert result.translated_text == "¡Hola mundo!"
        assert self.cache.metrics.hits == 1
        assert self.cache.metrics.misses == 0
    
    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration"""
        # Create cache with very short TTL
        short_cache = IntelligentTranslationCache(
            max_size=100,
            ttl_hours=0,  # Should expire immediately
            cleanup_interval_minutes=60
        )
        
        tweet_text = "Hello world"
        target_language = "Spanish"
        
        # Put translation in cache
        short_cache.put(tweet_text, target_language, self.test_translation)
        
        # Should be expired immediately due to 0 TTL
        time.sleep(0.1)  # Small delay to ensure time passes
        result = short_cache.get(tweet_text, target_language)
        assert result is None
        assert short_cache.metrics.misses == 1
    
    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache reaches max size"""
        # Create small cache
        small_cache = IntelligentTranslationCache(
            max_size=2,
            ttl_hours=24,
            cleanup_interval_minutes=60
        )
        
        # Add entries up to max size
        for i in range(3):  # One more than max size
            text = f"Hello {i}"
            translation = Translation(
                original_tweet=self.test_tweet,
                target_language="Spanish",
                translated_text=f"Hola {i}",
                translation_timestamp=datetime.now(),
                character_count=7,
                status="pending"
            )
            small_cache.put(text, "Spanish", translation)
        
        # Should have evicted oldest entry
        assert len(small_cache._cache) == 2
        assert small_cache.metrics.evictions == 1
        
        # First entry should be gone (LRU evicted)
        result = small_cache.get("Hello 0", "Spanish")
        assert result is None
        
        # Later entries should still be there
        result = small_cache.get("Hello 1", "Spanish")
        assert result is not None
        result = small_cache.get("Hello 2", "Spanish")
        assert result is not None
    
    def test_cache_lru_access_updates(self):
        """Test that accessing entries updates LRU order"""
        small_cache = IntelligentTranslationCache(max_size=2, ttl_hours=24)
        
        # Add two entries
        translation1 = Translation(
            original_tweet=self.test_tweet, target_language="Spanish",
            translated_text="Hola 1", translation_timestamp=datetime.now(),
            character_count=6, status="pending"
        )
        translation2 = Translation(
            original_tweet=self.test_tweet, target_language="Spanish", 
            translated_text="Hola 2", translation_timestamp=datetime.now(),
            character_count=6, status="pending"
        )
        
        small_cache.put("Text 1", "Spanish", translation1)
        small_cache.put("Text 2", "Spanish", translation2)
        
        # Access first entry to make it recently used
        small_cache.get("Text 1", "Spanish")
        
        # Add third entry - should evict Text 2, not Text 1
        translation3 = Translation(
            original_tweet=self.test_tweet, target_language="Spanish",
            translated_text="Hola 3", translation_timestamp=datetime.now(),
            character_count=6, status="pending"
        )
        small_cache.put("Text 3", "Spanish", translation3)
        
        # Text 1 should still be there (recently accessed)
        result = small_cache.get("Text 1", "Spanish")
        assert result is not None
        
        # Text 2 should be evicted (least recently used)
        result = small_cache.get("Text 2", "Spanish")
        assert result is None
        
        # Text 3 should be there (newly added)
        result = small_cache.get("Text 3", "Spanish") 
        assert result is not None
    
    def test_cache_metrics_tracking(self):
        """Test cache metrics are tracked correctly"""
        # Reset metrics
        self.cache.metrics.reset()
        
        tweet_text = "Hello world"
        
        # Cache miss
        result = self.cache.get(tweet_text, "Spanish")
        assert result is None
        assert self.cache.metrics.hits == 0
        assert self.cache.metrics.misses == 1
        
        # Cache put
        self.cache.put(tweet_text, "Spanish", self.test_translation)
        
        # Cache hit
        result = self.cache.get(tweet_text, "Spanish")
        assert result is not None
        assert self.cache.metrics.hits == 1
        assert self.cache.metrics.misses == 1
        
        # Another hit
        result = self.cache.get(tweet_text, "Spanish")
        assert self.cache.metrics.hits == 2
        assert self.cache.metrics.misses == 1
        
        # Hit rate should be 66.67% (2 hits, 1 miss)
        assert abs(self.cache.metrics.hit_rate - 66.67) < 0.01
    
    def test_cache_clear(self):
        """Test cache clear functionality"""
        # Add some entries
        self.cache.put("Text 1", "Spanish", self.test_translation)
        self.cache.put("Text 2", "French", self.test_translation)
        
        assert len(self.cache._cache) == 2
        
        # Clear cache
        self.cache.clear()
        
        assert len(self.cache._cache) == 0
        assert self.cache.metrics.size == 0
    
    def test_cache_preload_common_translations(self):
        """Test preloading common translation patterns"""
        common_patterns = {
            "Good morning!": {
                "Spanish": "¡Buenos días!",
                "French": "Bonjour !",
                "Japanese": "おはようございます！"
            },
            "Thank you": {
                "Spanish": "Gracias",
                "French": "Merci"
            }
        }
        
        self.cache.preload_common_translations(common_patterns)
        
        # Should have 5 translations cached (3 + 2)
        assert len(self.cache._cache) == 5
        
        # Test that preloaded translations work
        result = self.cache.get("Good morning!", "Spanish")
        assert result is not None
        assert result.translated_text == "¡Buenos días!"
        
        result = self.cache.get("Thank you", "French")
        assert result is not None
        assert result.translated_text == "Merci"
    
    def test_cache_info_reporting(self):
        """Test cache information reporting"""
        # Add some test data
        self.cache.put("Hello", "Spanish", self.test_translation)
        
        # Access it to build up metrics
        self.cache.get("Hello", "Spanish")
        self.cache.get("Hello", "Spanish")
        
        info = self.cache.get_cache_info()
        
        assert 'metrics' in info
        assert 'config' in info
        assert 'top_entries' in info
        
        assert info['metrics']['size'] == 1
        assert info['metrics']['hits'] == 2
        assert info['config']['max_size'] == 100
        assert len(info['top_entries']) == 1
        assert info['top_entries'][0]['access_count'] == 2
    
    def test_cache_thread_safety(self):
        """Test cache thread safety with concurrent operations"""
        results = []
        errors = []
        
        def worker_put(thread_id):
            try:
                for i in range(10):
                    text = f"Thread{thread_id}_Text{i}"
                    translation = Translation(
                        original_tweet=self.test_tweet,
                        target_language="Spanish",
                        translated_text=f"Hilo{thread_id}_Texto{i}",
                        translation_timestamp=datetime.now(),
                        character_count=20,
                        status="pending"
                    )
                    self.cache.put(text, "Spanish", translation)
                results.append(f"PUT_{thread_id}_OK")
            except Exception as e:
                errors.append(f"PUT_{thread_id}_{str(e)}")
        
        def worker_get(thread_id):
            try:
                for i in range(10):
                    text = f"Thread{thread_id}_Text{i}"
                    result = self.cache.get(text, "Spanish")
                    if result:
                        results.append(f"GET_{thread_id}_{i}_HIT")
                    else:
                        results.append(f"GET_{thread_id}_{i}_MISS")
            except Exception as e:
                errors.append(f"GET_{thread_id}_{str(e)}")
        
        # Start multiple threads
        threads = []
        for i in range(3):
            t1 = threading.Thread(target=worker_put, args=(i,))
            t2 = threading.Thread(target=worker_get, args=(i,))
            threads.extend([t1, t2])
        
        # Run all threads
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Should have no errors
        assert len(errors) == 0
        assert len(results) > 0
    
    def test_cache_cleanup_expired_entries(self):
        """Test cleanup of expired entries"""
        # Create cache with longer TTL but test manual expiration
        test_cache = IntelligentTranslationCache(
            max_size=100,
            ttl_hours=24,  # Normal TTL
            cleanup_interval_minutes=60
        )
        
        # Add entry normally
        test_cache.put("Test", "Spanish", self.test_translation)
        assert len(test_cache._cache) == 1
        
        # Manually set TTL to 0 to simulate expiration
        test_cache.ttl_seconds = 0
        
        # Force cleanup
        test_cache._cleanup_expired()
        
        # Entry should be removed
        assert len(test_cache._cache) == 0
    
    def test_cache_memory_usage_estimation(self):
        """Test memory usage estimation"""
        # Add several translations
        for i in range(5):
            translation = Translation(
                original_tweet=self.test_tweet,
                target_language="Spanish",
                translated_text=f"Translation {i}" * 10,  # Make it longer
                translation_timestamp=datetime.now(),
                character_count=100,
                status="pending"
            )
            self.cache.put(f"Text {i}", "Spanish", translation)
        
        metrics = self.cache.get_metrics()
        
        # Should have non-zero memory usage
        assert metrics.memory_usage_mb > 0
        assert metrics.size == 5
