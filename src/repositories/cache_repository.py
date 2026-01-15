# =============================================================================
# CACHE REPOSITORY
# =============================================================================

import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from src.models.database_models import TranslationCache as CacheModel
from src.repositories.base_repository import BaseRepository

class CacheRepository(BaseRepository[CacheModel]):
    """Repository for translation cache operations"""
    
    def __init__(self, session: Session):
        super().__init__(session, CacheModel)
    
    def generate_cache_key(self, original_text: str, target_language: str) -> str:
        """Generate a cache key for given text and language"""
        content = f"{original_text}:{target_language}".encode('utf-8')
        return hashlib.sha256(content).hexdigest()
    
    def store_translation(
        self,
        original_text: str,
        translated_text: str,
        target_language: str,
        source_language: Optional[str] = None,
        ttl_hours: Optional[int] = None,
        confidence_score: Optional[float] = None,
        translator_service: str = 'gemini',
        metadata: Optional[Dict[str, Any]] = None
    ) -> CacheModel:
        """Store a translation in cache"""
        cache_key = self.generate_cache_key(original_text, target_language)
        
        # Calculate expiration time
        expires_at = None
        if ttl_hours:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        
        # Check if entry already exists
        existing = self.get_by_cache_key(cache_key)
        if existing:
            # Update existing entry
            return self.update(
                existing,
                translated_text=translated_text,
                source_language=source_language,
                expires_at=expires_at,
                confidence_score=confidence_score,
                quality_metrics=metadata or {},
                translator_service=translator_service,
                access_count=existing.access_count + 1,
                last_accessed=datetime.now(timezone.utc)
            )
        else:
            # Create new entry
            return self.create(
                cache_key=cache_key,
                original_text=original_text,
                translated_text=translated_text,
                source_language=source_language,
                target_language=target_language,
                expires_at=expires_at,
                confidence_score=confidence_score,
                quality_metrics=metadata or {},
                translator_service=translator_service,
                access_count=1
            )
    
    def get_translation(self, original_text: str, target_language: str) -> Optional[str]:
        """Get cached translation if available and not expired"""
        cache_key = self.generate_cache_key(original_text, target_language)
        entry = self.get_by_cache_key(cache_key)
        
        if not entry:
            return None
        
        # Check if expired
        if entry.is_expired():
            # Clean up expired entry
            self.delete(entry)
            return None
        
        # Update access information
        self.update(
            entry,
            last_accessed=datetime.now(timezone.utc),
            access_count=entry.access_count + 1
        )
        
        return entry.translated_text
    
    def get_by_cache_key(self, cache_key: str) -> Optional[CacheModel]:
        """Get cache entry by key"""
        return self.find_one_by(cache_key=cache_key)
    
    def cleanup_expired_entries(self) -> int:
        """Remove all expired cache entries"""
        try:
            now = datetime.now(timezone.utc)
            
            deleted_count = self.session.query(CacheModel).filter(
                and_(
                    CacheModel.expires_at.isnot(None),
                    CacheModel.expires_at < now
                )
            ).delete()
            
            self.session.flush()
            return deleted_count
        except Exception as e:
            self.logger.error(f"Error cleaning up expired cache entries: {str(e)}")
            self.session.rollback()
            return 0
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        try:
            total_entries = self.count()
            
            # Count expired entries
            now = datetime.now(timezone.utc)
            expired_entries = self.session.query(CacheModel).filter(
                and_(
                    CacheModel.expires_at.isnot(None),
                    CacheModel.expires_at < now
                )
            ).count()
            
            active_entries = total_entries - expired_entries
            
            # Get most accessed translations
            top_translations = self.session.query(CacheModel).order_by(
                desc(CacheModel.access_count)
            ).limit(10).all()
            
            # Get language statistics
            from sqlalchemy import func
            language_stats = self.session.query(
                CacheModel.target_language,
                func.count(CacheModel.id).label('count'),
                func.avg(CacheModel.access_count).label('avg_access')
            ).group_by(CacheModel.target_language).order_by(
                desc('count')
            ).all()
            
            # Calculate hit rate (this would need to be tracked separately in a real implementation)
            # For now, we'll estimate based on access counts
            total_accesses = sum([entry.access_count for entry in self.get_all()])
            estimated_hit_rate = (total_accesses / (total_accesses + total_entries)) * 100 if total_entries > 0 else 0
            
            return {
                'total_entries': total_entries,
                'active_entries': active_entries,
                'expired_entries': expired_entries,
                'estimated_hit_rate': round(estimated_hit_rate, 2),
                'total_accesses': total_accesses,
                'language_statistics': [
                    {
                        'language': lang,
                        'entry_count': count,
                        'average_access_count': round(float(avg_access), 2)
                    }
                    for lang, count, avg_access in language_stats
                ],
                'most_accessed': [
                    {
                        'original_text': entry.original_text[:100] + '...' if len(entry.original_text) > 100 else entry.original_text,
                        'target_language': entry.target_language,
                        'access_count': entry.access_count,
                        'created_at': entry.created_at
                    }
                    for entry in top_translations
                ]
            }
        except Exception as e:
            self.logger.error(f"Error getting cache statistics: {str(e)}")
            return {}
    
    def invalidate_cache(self, original_text: str, target_language: str) -> bool:
        """Invalidate a specific cache entry"""
        try:
            cache_key = self.generate_cache_key(original_text, target_language)
            entry = self.get_by_cache_key(cache_key)
            
            if entry:
                self.delete(entry)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error invalidating cache: {str(e)}")
            return False
    
    def get_entries_by_language(self, target_language: str, limit: Optional[int] = None) -> List[CacheModel]:
        """Get cache entries for a specific target language"""
        query = self.session.query(CacheModel).filter(
            CacheModel.target_language == target_language
        ).order_by(desc(CacheModel.last_accessed))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_low_quality_entries(self, confidence_threshold: float = 0.7) -> List[CacheModel]:
        """Get cache entries with low confidence scores"""
        return self.session.query(CacheModel).filter(
            and_(
                CacheModel.confidence_score.isnot(None),
                CacheModel.confidence_score < confidence_threshold
            )
        ).order_by(CacheModel.confidence_score).all()
    
    def bulk_set_ttl(self, hours: int, language: Optional[str] = None) -> int:
        """Bulk set TTL for cache entries"""
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
            
            query = self.session.query(CacheModel)
            if language:
                query = query.filter(CacheModel.target_language == language)
            
            updated_count = query.update(
                {'expires_at': expires_at},
                synchronize_session=False
            )
            
            self.session.flush()
            return updated_count
        except Exception as e:
            self.logger.error(f"Error bulk setting TTL: {str(e)}")
            self.session.rollback()
            return 0
    
    def get_cache_size_by_language(self) -> Dict[str, Dict[str, Any]]:
        """Get cache size statistics by language"""
        try:
            from sqlalchemy import func
            
            stats = self.session.query(
                CacheModel.target_language,
                func.count(CacheModel.id).label('entry_count'),
                func.sum(func.length(CacheModel.original_text)).label('original_text_size'),
                func.sum(func.length(CacheModel.translated_text)).label('translated_text_size'),
                func.avg(CacheModel.access_count).label('avg_access_count')
            ).group_by(CacheModel.target_language).all()
            
            result = {}
            for lang, count, orig_size, trans_size, avg_access in stats:
                result[lang] = {
                    'entry_count': count,
                    'original_text_size_bytes': orig_size or 0,
                    'translated_text_size_bytes': trans_size or 0,
                    'total_size_bytes': (orig_size or 0) + (trans_size or 0),
                    'average_access_count': round(float(avg_access or 0), 2)
                }
            
            return result
        except Exception as e:
            self.logger.error(f"Error getting cache size by language: {str(e)}")
            return {}
    
    @property
    def logger(self):
        """Get logger for this repository"""
        from src.utils.logger import logger
        return logger
