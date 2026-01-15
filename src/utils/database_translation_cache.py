# =============================================================================
# DATABASE-BACKED TRANSLATION CACHE
# =============================================================================
# Replaces in-memory cache with persistent database storage

from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from src.repositories import CacheRepository
from src.config.database import db_config
from src.utils.logger import logger

class DatabaseTranslationCache:
    """Database-backed translation cache with TTL support"""
    
    def __init__(self, default_ttl_hours: int = 24):
        self.default_ttl_hours = default_ttl_hours
        self.hit_count = 0
        self.miss_count = 0
    
    def get_translation(self, original_text: str, target_language: str) -> Optional[str]:
        """Get cached translation if available and not expired"""
        try:
            with db_config.get_session() as session:
                cache_repo = CacheRepository(session)
                
                # Clean up expired entries occasionally
                if self._should_cleanup():
                    cache_repo.cleanup_expired_entries()
                
                translation = cache_repo.get_translation(original_text, target_language)
                
                if translation:
                    self.hit_count += 1
                    logger.debug(f"Cache HIT for {target_language}: {original_text[:50]}...")
                    session.commit()  # Commit access count update
                    return translation
                else:
                    self.miss_count += 1
                    logger.debug(f"Cache MISS for {target_language}: {original_text[:50]}...")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting cached translation: {str(e)}")
            self.miss_count += 1
            return None
    
    def store_translation(
        self,
        original_text: str,
        translated_text: str,
        target_language: str,
        source_language: Optional[str] = None,
        confidence_score: Optional[float] = None,
        translator_service: str = 'gemini',
        ttl_hours: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store a translation in cache with optional TTL"""
        try:
            with db_config.get_session() as session:
                cache_repo = CacheRepository(session)
                
                cache_repo.store_translation(
                    original_text=original_text,
                    translated_text=translated_text,
                    target_language=target_language,
                    source_language=source_language,
                    ttl_hours=ttl_hours or self.default_ttl_hours,
                    confidence_score=confidence_score,
                    translator_service=translator_service,
                    metadata=metadata
                )
                
                session.commit()
                logger.debug(f"Cached translation for {target_language}: {original_text[:50]}...")
                return True
                
        except Exception as e:
            logger.error(f"Error storing cached translation: {str(e)}")
            return False
    
    def invalidate_translation(self, original_text: str, target_language: str) -> bool:
        """Invalidate a specific cache entry"""
        try:
            with db_config.get_session() as session:
                cache_repo = CacheRepository(session)
                
                success = cache_repo.invalidate_cache(original_text, target_language)
                if success:
                    session.commit()
                    logger.debug(f"Invalidated cache for {target_language}: {original_text[:50]}...")
                
                return success
                
        except Exception as e:
            logger.error(f"Error invalidating cached translation: {str(e)}")
            return False
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        try:
            with db_config.get_session() as session:
                cache_repo = CacheRepository(session)
                
                db_stats = cache_repo.get_cache_statistics()
                size_stats = cache_repo.get_cache_size_by_language()
                
                # Calculate hit rate
                total_requests = self.hit_count + self.miss_count
                hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0
                
                return {
                    'session_statistics': {
                        'hit_count': self.hit_count,
                        'miss_count': self.miss_count,
                        'hit_rate_percent': round(hit_rate, 2),
                        'total_requests': total_requests
                    },
                    'database_statistics': db_stats,
                    'size_by_language': size_stats
                }
                
        except Exception as e:
            logger.error(f"Error getting cache statistics: {str(e)}")
            return {}
    
    def cleanup_expired_entries(self) -> int:
        """Manually trigger cleanup of expired entries"""
        try:
            with db_config.get_session() as session:
                cache_repo = CacheRepository(session)
                
                removed_count = cache_repo.cleanup_expired_entries()
                session.commit()
                
                if removed_count > 0:
                    logger.info(f"Cleaned up {removed_count} expired cache entries")
                
                return removed_count
                
        except Exception as e:
            logger.error(f"Error cleaning up expired cache entries: {str(e)}")
            return 0
    
    def get_cache_entries_by_language(self, target_language: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get cache entries for a specific language"""
        try:
            with db_config.get_session() as session:
                cache_repo = CacheRepository(session)
                
                entries = cache_repo.get_entries_by_language(target_language, limit)
                
                return [entry.to_dict() for entry in entries]
                
        except Exception as e:
            logger.error(f"Error getting cache entries for {target_language}: {str(e)}")
            return []
    
    def get_low_quality_translations(self, confidence_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Get translations with low confidence scores for review"""
        try:
            with db_config.get_session() as session:
                cache_repo = CacheRepository(session)
                
                entries = cache_repo.get_low_quality_entries(confidence_threshold)
                
                return [entry.to_dict() for entry in entries]
                
        except Exception as e:
            logger.error(f"Error getting low quality translations: {str(e)}")
            return []
    
    def set_ttl_for_language(self, language: str, hours: int) -> int:
        """Set TTL for all cache entries in a specific language"""
        try:
            with db_config.get_session() as session:
                cache_repo = CacheRepository(session)
                
                updated_count = cache_repo.bulk_set_ttl(hours, language)
                session.commit()
                
                if updated_count > 0:
                    logger.info(f"Updated TTL for {updated_count} {language} cache entries")
                
                return updated_count
                
        except Exception as e:
            logger.error(f"Error setting TTL for {language}: {str(e)}")
            return 0
    
    def _should_cleanup(self) -> bool:
        """Determine if we should run cleanup (every 100 requests)"""
        total_requests = self.hit_count + self.miss_count
        return total_requests > 0 and total_requests % 100 == 0
    
    def reset_session_statistics(self):
        """Reset session-level statistics (hits/misses)"""
        self.hit_count = 0
        self.miss_count = 0
        logger.info("Reset cache session statistics")
    
    def warm_up_cache(self, popular_phrases: List[Dict[str, str]]) -> int:
        """Pre-populate cache with popular phrases"""
        warmed_count = 0
        
        for phrase_data in popular_phrases:
            original = phrase_data.get('original_text')
            translated = phrase_data.get('translated_text')
            language = phrase_data.get('target_language')
            
            if original and translated and language:
                success = self.store_translation(
                    original_text=original,
                    translated_text=translated,
                    target_language=language,
                    confidence_score=phrase_data.get('confidence_score'),
                    ttl_hours=phrase_data.get('ttl_hours', self.default_ttl_hours),
                    metadata={'warm_up': True, 'warm_up_date': datetime.now().isoformat()}
                )
                
                if success:
                    warmed_count += 1
        
        logger.info(f"Warmed up cache with {warmed_count} translations")
        return warmed_count

# Global instance
database_translation_cache = DatabaseTranslationCache()

# Backwards compatibility
translation_cache = database_translation_cache
