# =============================================================================
# INTELLIGENT TRANSLATION CACHE SYSTEM
# =============================================================================
# Added by: AI Assistant on 2025-01-18
# Purpose: High-performance caching system for translations with TTL and LRU eviction
#
# Features:
# - Hash-based cache keys for content deduplication
# - Time-based expiration (TTL) 
# - LRU eviction for memory management
# - Cache hit/miss metrics
# - Thread-safe operations
# - Smart cache warming and preloading
# =============================================================================

import hashlib
import json
import time
import threading
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import OrderedDict
from dataclasses import dataclass, asdict
from ..models.tweet import Translation, Tweet
from ..utils.logger import logger

@dataclass
class CacheEntry:
    """Single cache entry with metadata"""
    translation: Translation
    created_at: float
    access_count: int
    last_accessed: float
    cache_key: str
    
    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if cache entry has expired"""
        return (time.time() - self.created_at) > ttl_seconds
    
    def touch(self):
        """Update last accessed time and increment access count"""
        self.last_accessed = time.time()
        self.access_count += 1

@dataclass 
class CacheMetrics:
    """Cache performance metrics"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0
    memory_usage_mb: float = 0.0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate percentage"""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0
    
    def reset(self):
        """Reset all metrics"""
        self.hits = 0
        self.misses = 0
        self.evictions = 0

class IntelligentTranslationCache:
    """
    High-performance translation cache with TTL and LRU eviction
    
    Features:
    - Content-based hashing for smart deduplication
    - Configurable TTL (time-to-live) for entries
    - LRU (Least Recently Used) eviction when memory limits are reached
    - Thread-safe operations for concurrent access
    - Detailed metrics and monitoring
    - Smart cache key generation considering all relevant factors
    """
    
    def __init__(self, 
                 max_size: int = 1000,
                 ttl_hours: int = 24,
                 cleanup_interval_minutes: int = 30):
        """
        Initialize the translation cache
        
        Args:
            max_size: Maximum number of entries before LRU eviction
            ttl_hours: Time-to-live for cache entries in hours
            cleanup_interval_minutes: How often to run cleanup (remove expired entries)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_hours * 3600
        self.cleanup_interval = cleanup_interval_minutes * 60
        
        # Thread-safe cache storage (LRU ordered)
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        
        # Metrics tracking
        self.metrics = CacheMetrics()
        
        # Automatic cleanup
        self._last_cleanup = time.time()
        
        logger.info(f"🔄 Translation cache initialized: max_size={max_size}, ttl={ttl_hours}h")
    
    def _generate_cache_key(self, 
                          tweet_text: str, 
                          target_language: str, 
                          language_config: dict = None) -> str:
        """
        Generate intelligent cache key based on content hash
        
        This ensures that identical content gets cached regardless of:
        - Tweet ID (different tweets with same text share cache)
        - Timestamp (same content cached across time)
        - Author (same content from different users shares cache)
        
        Key includes:
        - Normalized tweet text hash
        - Target language
        - Language configuration settings (formal_tone, cultural_adaptation)
        """
        # Normalize text (remove extra whitespace, consistent casing for hashtags)
        normalized_text = ' '.join(tweet_text.strip().split())
        
        # Create config fingerprint
        config_str = ""
        if language_config:
            # Only include settings that affect translation output
            relevant_config = {
                'formal_tone': language_config.get('formal_tone', False),
                'cultural_adaptation': language_config.get('cultural_adaptation', True)
            }
            config_str = json.dumps(relevant_config, sort_keys=True)
        
        # Combine all factors that affect translation
        cache_input = f"{normalized_text}|{target_language}|{config_str}"
        
        # Generate hash
        cache_hash = hashlib.sha256(cache_input.encode('utf-8')).hexdigest()[:16]
        
        return f"trans_{target_language}_{cache_hash}"
    
    def get(self, 
            tweet_text: str, 
            target_language: str, 
            language_config: dict = None) -> Optional[Translation]:
        """
        Retrieve translation from cache if available and not expired
        
        Returns:
            Translation object if found and valid, None otherwise
        """
        cache_key = self._generate_cache_key(tweet_text, target_language, language_config)
        
        with self._lock:
            # Check if key exists
            if cache_key not in self._cache:
                self.metrics.misses += 1
                logger.debug(f"🔍 Cache miss: {cache_key}")
                return None
            
            entry = self._cache[cache_key]
            
            # Check if expired
            if entry.is_expired(self.ttl_seconds):
                logger.debug(f"⏰ Cache entry expired: {cache_key}")
                del self._cache[cache_key]
                self.metrics.misses += 1
                return None
            
            # Update access metrics and move to end (most recently used)
            entry.touch()
            self._cache.move_to_end(cache_key)
            
            self.metrics.hits += 1
            logger.info(f"✅ Cache hit: {cache_key} (used {entry.access_count} times)")
            
            return entry.translation
    
    def put(self, 
            tweet_text: str, 
            target_language: str, 
            translation: Translation,
            language_config: dict = None):
        """
        Store translation in cache with automatic eviction if needed
        
        Args:
            tweet_text: Original tweet text for key generation
            target_language: Target language for translation
            translation: Translation object to cache
            language_config: Language configuration used for translation
        """
        cache_key = self._generate_cache_key(tweet_text, target_language, language_config)
        
        with self._lock:
            current_time = time.time()
            
            # Create cache entry
            entry = CacheEntry(
                translation=translation,
                created_at=current_time,
                access_count=0,
                last_accessed=current_time,
                cache_key=cache_key
            )
            
            # Store entry (this automatically moves to end if exists)
            self._cache[cache_key] = entry
            self._cache.move_to_end(cache_key)
            
            # Evict least recently used entries if over size limit
            while len(self._cache) > self.max_size:
                evicted_key, evicted_entry = self._cache.popitem(last=False)
                self.metrics.evictions += 1
                logger.debug(f"🗑️ Evicted LRU entry: {evicted_key}")
            
            self.metrics.size = len(self._cache)
            logger.debug(f"💾 Cached translation: {cache_key} (cache size: {self.metrics.size})")
            
            # Periodic cleanup
            self._maybe_cleanup()
    
    def _maybe_cleanup(self):
        """Run cleanup if enough time has passed since last cleanup"""
        current_time = time.time()
        if current_time - self._last_cleanup > self.cleanup_interval:
            self._cleanup_expired()
            self._last_cleanup = current_time
    
    def _cleanup_expired(self):
        """Remove expired entries from cache"""
        expired_keys = []
        current_time = time.time()
        
        for key, entry in self._cache.items():
            if entry.is_expired(self.ttl_seconds):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
            
        if expired_keys:
            self.metrics.size = len(self._cache)
            logger.info(f"🧹 Cleaned up {len(expired_keys)} expired cache entries")
    
    def get_metrics(self) -> CacheMetrics:
        """Get current cache performance metrics"""
        with self._lock:
            self.metrics.size = len(self._cache)
            
            # Calculate approximate memory usage
            if self._cache:
                # Sample a few entries to estimate memory usage
                sample_size = min(5, len(self._cache))
                sample_entries = list(self._cache.values())[:sample_size]
                
                avg_entry_size = 0
                for entry in sample_entries:
                    # Rough estimate: translation text + metadata
                    entry_size = len(entry.translation.translated_text) * 2  # Unicode
                    entry_size += 200  # Metadata overhead
                    avg_entry_size += entry_size
                
                avg_entry_size = avg_entry_size / sample_size if sample_size > 0 else 0
                self.metrics.memory_usage_mb = (avg_entry_size * len(self._cache)) / (1024 * 1024)
            
            return self.metrics
    
    def clear(self):
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()
            self.metrics.size = 0
            logger.info("🗑️ Cache cleared")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get detailed cache information for monitoring"""
        with self._lock:
            metrics = self.get_metrics()
            
            # Get top accessed entries
            top_entries = sorted(
                self._cache.values(),
                key=lambda e: e.access_count,
                reverse=True
            )[:5]
            
            return {
                'metrics': asdict(metrics),
                'config': {
                    'max_size': self.max_size,
                    'ttl_hours': self.ttl_seconds // 3600,
                    'cleanup_interval_minutes': self.cleanup_interval // 60
                },
                'top_entries': [
                    {
                        'cache_key': entry.cache_key,
                        'access_count': entry.access_count,
                        'age_hours': (time.time() - entry.created_at) / 3600,
                        'target_language': entry.translation.target_language,
                        'character_count': entry.translation.character_count
                    }
                    for entry in top_entries
                ]
            }
    
    def preload_common_translations(self, common_patterns: Dict[str, Dict[str, str]]):
        """
        Preload cache with common translation patterns
        
        Args:
            common_patterns: Dict mapping text patterns to language->translation mappings
            
        Example:
            {
                "Good morning!": {
                    "Japanese": "おはようございます！", 
                    "Spanish": "¡Buenos días!"
                }
            }
        """
        logger.info(f"🔄 Preloading {len(common_patterns)} common translation patterns...")
        
        preload_count = 0
        for text, translations in common_patterns.items():
            for language, translated_text in translations.items():
                # Create dummy tweet for cache key generation
                dummy_translation = Translation(
                    original_tweet=None,
                    target_language=language,
                    translated_text=translated_text,
                    translation_timestamp=datetime.now(),
                    character_count=len(translated_text),
                    status='cached'
                )
                
                self.put(text, language, dummy_translation)
                preload_count += 1
        
        logger.info(f"✅ Preloaded {preload_count} translations into cache")

# Global cache instance
translation_cache = IntelligentTranslationCache(
    max_size=1000,      # Store up to 1000 translations
    ttl_hours=24,       # Cache for 24 hours
    cleanup_interval_minutes=30  # Clean up every 30 minutes
)
