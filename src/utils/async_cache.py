# =============================================================================
# ASYNC-OPTIMIZED TRANSLATION CACHE
# =============================================================================
# Thread-safe async version of the translation cache with better performance

import asyncio
import aiofiles
import hashlib
import json
import time
from typing import Dict, Optional, List, Tuple, Any
from pathlib import Path
from collections import OrderedDict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from ..models.tweet import Translation
from ..utils.logger import logger
from threading import RLock

@dataclass
class AsyncCacheEntry:
    """Async cache entry with metadata"""
    translation: Translation
    language_config: Dict[str, Any]
    access_count: int
    created_at: float
    last_accessed: float
    expiry_time: Optional[float] = None

class AsyncTranslationCache:
    """
    Thread-safe async-optimized translation cache with:
    - Concurrent access support
    - Intelligent eviction policies
    - Async file I/O
    - Memory optimization
    - Performance monitoring
    """
    
    def __init__(
        self,
        cache_file: str = 'logs/async_translation_cache.json',
        max_entries: int = 10000,
        ttl_hours: int = 168,  # 1 week default
        save_interval: int = 300  # 5 minutes
    ):
        self.cache_file = Path(cache_file)
        self.max_entries = max_entries
        self.ttl_seconds = ttl_hours * 3600
        self.save_interval = save_interval
        
        # Thread-safe cache storage
        self.cache: OrderedDict[str, AsyncCacheEntry] = OrderedDict()
        self._lock = RLock()
        
        # Performance tracking
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.saves = 0
        self.loads = 0
        
        # Async operations
        self._save_task: Optional[asyncio.Task] = None
        self._last_save = time.time()
        
        # Cache warming
        self._warm_cache_patterns: Dict[str, Dict[str, str]] = {}
        
        logger.info(f"🔄 Async translation cache initialized (max_entries: {max_entries}, TTL: {ttl_hours}h)")
    
    async def initialize(self):
        """Initialize async cache"""
        await self.load_cache()
        self._start_auto_save()
        logger.info("✅ Async translation cache ready")
    
    async def close(self):
        """Clean shutdown"""
        if self._save_task:
            self._save_task.cancel()
        await self.save_cache()
        logger.info("💾 Async translation cache closed")
    
    def _generate_cache_key(self, text: str, target_language: str, language_config: dict = None) -> str:
        """Generate cache key using content-based hashing"""
        # Include language config in hash for different translation styles
        config_str = ""
        if language_config:
            # Sort keys for consistent hashing
            config_items = sorted(language_config.items()) if isinstance(language_config, dict) else []
            config_str = json.dumps(config_items, sort_keys=True)
        
        combined = f"{text}|{target_language}|{config_str}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    async def get(self, text: str, target_language: str, language_config: dict = None) -> Optional[Translation]:
        """Get translation from cache (thread-safe, async-optimized)"""
        cache_key = self._generate_cache_key(text, target_language, language_config)
        current_time = time.time()
        
        with self._lock:
            entry = self.cache.get(cache_key)
            
            if entry is None:
                self.misses += 1
                return None
            
            # Check if entry has expired
            if entry.expiry_time and current_time > entry.expiry_time:
                del self.cache[cache_key]
                self.misses += 1
                return None
            
            # Update access patterns
            entry.access_count += 1
            entry.last_accessed = current_time
            
            # Move to end (LRU)
            self.cache.move_to_end(cache_key)
            
            self.hits += 1
            
            return entry.translation
    
    async def put(self, text: str, target_language: str, translation: Translation, language_config: dict = None):
        """Store translation in cache (thread-safe, async-optimized)"""
        cache_key = self._generate_cache_key(text, target_language, language_config)
        current_time = time.time()
        
        with self._lock:
            # Create cache entry
            entry = AsyncCacheEntry(
                translation=translation,
                language_config=language_config or {},
                access_count=1,
                created_at=current_time,
                last_accessed=current_time,
                expiry_time=current_time + self.ttl_seconds if self.ttl_seconds > 0 else None
            )
            
            # Add to cache
            self.cache[cache_key] = entry
            self.cache.move_to_end(cache_key)
            
            # Evict if over limit
            await self._evict_if_needed()
        
        # Trigger save if needed
        await self._maybe_save_cache()
    
    async def _evict_if_needed(self):
        """Evict entries if cache is over limit (must be called with lock held)"""
        while len(self.cache) > self.max_entries:
            # Remove least recently used
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            self.evictions += 1
    
    async def batch_get(self, requests: List[Tuple[str, str, dict]]) -> Dict[str, Optional[Translation]]:
        """Get multiple translations from cache efficiently"""
        results = {}
        
        with self._lock:
            for text, target_language, language_config in requests:
                cache_key = self._generate_cache_key(text, target_language, language_config)
                translation = await self.get(text, target_language, language_config)
                results[cache_key] = translation
        
        return results
    
    async def batch_put(self, entries: List[Tuple[str, str, Translation, dict]]):
        """Store multiple translations in cache efficiently"""
        for text, target_language, translation, language_config in entries:
            await self.put(text, target_language, translation, language_config)
    
    async def load_cache(self):
        """Load cache from file asynchronously"""
        if not self.cache_file.exists():
            logger.info("🔄 No existing async cache file found")
            return
        
        try:
            async with aiofiles.open(self.cache_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
            
            loaded_entries = 0
            current_time = time.time()
            
            with self._lock:
                for cache_key, entry_data in data.get('cache', {}).items():
                    try:
                        # Check if entry has expired
                        expiry_time = entry_data.get('expiry_time')
                        if expiry_time and current_time > expiry_time:
                            continue
                        
                        # Reconstruct Translation object
                        translation_data = entry_data['translation']
                        translation = Translation(
                            original_tweet=None,  # Will be set when used
                            target_language=translation_data['target_language'],
                            translated_text=translation_data['translated_text'],
                            translation_timestamp=datetime.fromisoformat(translation_data['translation_timestamp']),
                            character_count=translation_data.get('character_count', 0),
                            status=translation_data.get('status', 'cached'),
                            post_id=translation_data.get('post_id'),
                            error_message=translation_data.get('error_message')
                        )
                        
                        # Create cache entry
                        entry = AsyncCacheEntry(
                            translation=translation,
                            language_config=entry_data.get('language_config', {}),
                            access_count=entry_data.get('access_count', 1),
                            created_at=entry_data.get('created_at', current_time),
                            last_accessed=entry_data.get('last_accessed', current_time),
                            expiry_time=expiry_time
                        )
                        
                        self.cache[cache_key] = entry
                        loaded_entries += 1
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Skipping corrupted cache entry {cache_key}: {str(e)}")
                        continue
                
                # Load stats
                stats = data.get('stats', {})
                self.hits = stats.get('hits', 0)
                self.misses = stats.get('misses', 0)
                self.evictions = stats.get('evictions', 0)
                self.saves = stats.get('saves', 0)
                self.loads = stats.get('loads', 0) + 1
            
            logger.info(f"📂 Loaded {loaded_entries} cache entries from {self.cache_file}")
            
        except Exception as e:
            logger.error(f"❌ Error loading async cache: {str(e)}")
            with self._lock:
                self.cache.clear()
    
    async def save_cache(self):
        """Save cache to file asynchronously"""
        try:
            # Ensure logs directory exists
            self.cache_file.parent.mkdir(exist_ok=True)
            
            cache_data = {}
            stats_data = {}
            
            with self._lock:
                # Serialize cache entries
                for cache_key, entry in self.cache.items():
                    try:
                        cache_data[cache_key] = {
                            'translation': {
                                'target_language': entry.translation.target_language,
                                'translated_text': entry.translation.translated_text,
                                'translation_timestamp': entry.translation.translation_timestamp.isoformat(),
                                'character_count': entry.translation.character_count,
                                'status': entry.translation.status,
                                'post_id': entry.translation.post_id,
                                'error_message': entry.translation.error_message
                            },
                            'language_config': entry.language_config,
                            'access_count': entry.access_count,
                            'created_at': entry.created_at,
                            'last_accessed': entry.last_accessed,
                            'expiry_time': entry.expiry_time
                        }
                    except Exception as e:
                        logger.warning(f"⚠️ Skipping entry {cache_key} during save: {str(e)}")
                        continue
                
                # Copy stats
                stats_data = {
                    'hits': self.hits,
                    'misses': self.misses,
                    'evictions': self.evictions,
                    'saves': self.saves + 1,
                    'loads': self.loads
                }
            
            data = {
                'metadata': {
                    'version': '2.0',
                    'saved_at': datetime.now().isoformat(),
                    'entries_count': len(cache_data)
                },
                'cache': cache_data,
                'stats': stats_data
            }
            
            async with aiofiles.open(self.cache_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2))
            
            self.saves += 1
            self._last_save = time.time()
            
            logger.info(f"💾 Saved {len(cache_data)} cache entries to {self.cache_file}")
            
        except Exception as e:
            logger.error(f"❌ Error saving async cache: {str(e)}")
    
    async def _maybe_save_cache(self):
        """Save cache if enough time has passed"""
        if time.time() - self._last_save > self.save_interval:
            await self.save_cache()
    
    def _start_auto_save(self):
        """Start automatic cache saving"""
        if self._save_task is None:
            self._save_task = asyncio.create_task(self._auto_save_loop())
    
    async def _auto_save_loop(self):
        """Automatic cache saving loop"""
        while True:
            try:
                await asyncio.sleep(self.save_interval)
                await self.save_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error in auto-save loop: {str(e)}")
    
    async def clear(self):
        """Clear all cache entries"""
        with self._lock:
            self.cache.clear()
            self.evictions = 0
        
        await self.save_cache()
        logger.info("🗑️ Async translation cache cleared")
    
    async def cleanup_expired(self) -> int:
        """Remove expired entries and return count removed"""
        current_time = time.time()
        removed_count = 0
        
        with self._lock:
            expired_keys = []
            for cache_key, entry in self.cache.items():
                if entry.expiry_time and current_time > entry.expiry_time:
                    expired_keys.append(cache_key)
            
            for key in expired_keys:
                del self.cache[key]
                removed_count += 1
        
        if removed_count > 0:
            logger.info(f"🧹 Removed {removed_count} expired cache entries")
        
        return removed_count
    
    async def preload_common_translations(self, patterns: dict):
        """Preload cache with common translation patterns"""
        logger.info(f"🔄 Preloading {len(patterns)} common translation patterns")
        
        preload_count = 0
        for text, translations in patterns.items():
            for target_language, translated_text in translations.items():
                # Create mock translation
                translation = Translation(
                    original_tweet=None,
                    target_language=target_language,
                    translated_text=translated_text,
                    translation_timestamp=datetime.now(),
                    character_count=len(translated_text),
                    status='preloaded'
                )
                
                await self.put(text, target_language, translation)
                preload_count += 1
        
        logger.info(f"✅ Preloaded {preload_count} translations")
    
    def get_cache_info(self) -> dict:
        """Get comprehensive cache information"""
        with self._lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            # Calculate cache efficiency
            avg_access_count = 0
            top_entries = []
            
            if self.cache:
                access_counts = [entry.access_count for entry in self.cache.values()]
                avg_access_count = sum(access_counts) / len(access_counts)
                
                # Get top 10 most accessed entries
                sorted_entries = sorted(
                    self.cache.items(),
                    key=lambda x: x[1].access_count,
                    reverse=True
                )[:10]
                
                top_entries = [
                    {
                        'target_language': entry.translation.target_language,
                        'access_count': entry.access_count,
                        'character_count': entry.translation.character_count
                    }
                    for key, entry in sorted_entries
                ]
            
            return {
                'total_entries': len(self.cache),
                'max_entries': self.max_entries,
                'utilization_percent': (len(self.cache) / self.max_entries * 100),
                'hit_rate_percent': hit_rate,
                'total_hits': self.hits,
                'total_misses': self.misses,
                'total_evictions': self.evictions,
                'total_saves': self.saves,
                'total_loads': self.loads,
                'avg_access_count': avg_access_count,
                'top_entries': top_entries,
                'cache_file': str(self.cache_file),
                'ttl_hours': self.ttl_seconds / 3600
            }
    
    def print_cache_stats(self):
        """Print formatted cache statistics"""
        info = self.get_cache_info()
        
        print("\n" + "="*60)
        print("🔄 ASYNC TRANSLATION CACHE STATISTICS")
        print("="*60)
        print(f"📊 Cache Utilization: {info['total_entries']}/{info['max_entries']} entries ({info['utilization_percent']:.1f}%)")
        print(f"🎯 Hit Rate: {info['hit_rate_percent']:.1f}% ({info['total_hits']} hits, {info['total_misses']} misses)")
        print(f"♻️  Evictions: {info['total_evictions']}")
        print(f"💾 Saves: {info['total_saves']}, Loads: {info['total_loads']}")
        print(f"📈 Average Access Count: {info['avg_access_count']:.1f}")
        print(f"⏰ TTL: {info['ttl_hours']:.1f} hours")
        
        if info['top_entries']:
            print(f"\n🏆 TOP CACHED TRANSLATIONS:")
            for i, entry in enumerate(info['top_entries'][:5], 1):
                print(f"   {i}. {entry['target_language']}: {entry['access_count']} accesses")
        
        print("="*60)

# Global async cache instance
async_translation_cache = AsyncTranslationCache()
