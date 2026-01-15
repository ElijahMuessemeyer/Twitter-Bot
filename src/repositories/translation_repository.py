# =============================================================================
# TRANSLATION REPOSITORY
# =============================================================================

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, and_, func, or_
from src.models.database_models import Translation as TranslationModel
from src.models.tweet import Translation
from src.repositories.base_repository import BaseRepository

class TranslationRepository(BaseRepository[TranslationModel]):
    """Repository for translation operations"""
    
    def __init__(self, session: Session):
        super().__init__(session, TranslationModel)
    
    def create_from_translation_object(self, translation: Translation) -> TranslationModel:
        """Create database record from Translation dataclass"""
        return self.create(
            original_tweet_id=translation.original_tweet.id,
            translated_text=translation.translated_text,
            target_language=translation.target_language,
            character_count=translation.character_count,
            status=translation.status,
            post_id=translation.post_id,
            error_info={'message': translation.error_message} if translation.error_message else None,
            translation_metadata={
                'original_text': translation.original_tweet.text,
                'translation_timestamp': translation.translation_timestamp.isoformat()
            }
        )
    
    def get_by_tweet_and_language(self, tweet_id: str, language: str) -> Optional[TranslationModel]:
        """Get translation by tweet ID and target language"""
        return self.find_one_by(
            original_tweet_id=tweet_id,
            target_language=language
        )
    
    def get_translations_for_tweet(self, tweet_id: str) -> List[TranslationModel]:
        """Get all translations for a specific tweet"""
        return self.find_by(original_tweet_id=tweet_id)
    
    def get_draft_translations(self, language: Optional[str] = None, limit: Optional[int] = None) -> List[TranslationModel]:
        """Get draft translations, optionally filtered by language"""
        query = self.session.query(TranslationModel).filter(
            TranslationModel.status == 'draft'
        ).options(joinedload(TranslationModel.original_tweet))
        
        if language:
            query = query.filter(TranslationModel.target_language == language)
        
        query = query.order_by(TranslationModel.created_at)
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_pending_translations(self, language: Optional[str] = None, limit: Optional[int] = None) -> List[TranslationModel]:
        """Get pending translations ready to be posted"""
        query = self.session.query(TranslationModel).filter(
            TranslationModel.status == 'pending'
        ).options(joinedload(TranslationModel.original_tweet))
        
        if language:
            query = query.filter(TranslationModel.target_language == language)
        
        query = query.order_by(TranslationModel.created_at)
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_failed_translations(self, retry_limit: int = 3, limit: Optional[int] = None) -> List[TranslationModel]:
        """Get failed translations that can be retried"""
        query = self.session.query(TranslationModel).filter(
            and_(
                TranslationModel.status == 'failed',
                TranslationModel.retry_count < retry_limit
            )
        ).options(joinedload(TranslationModel.original_tweet))
        
        if limit:
            query = query.limit(limit)
        
        return query.order_by(TranslationModel.updated_at).all()
    
    def get_posted_translations(self, days_back: int = 7) -> List[TranslationModel]:
        """Get recently posted translations"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        return self.session.query(TranslationModel).filter(
            and_(
                TranslationModel.status == 'posted',
                TranslationModel.posted_at >= cutoff_date
            )
        ).options(joinedload(TranslationModel.original_tweet)).order_by(
            desc(TranslationModel.posted_at)
        ).all()
    
    def mark_as_posted(self, translation_id: int, post_id: str) -> bool:
        """Mark translation as posted"""
        try:
            translation = self.get_by_id(translation_id)
            if translation:
                self.update(
                    translation,
                    status='posted',
                    post_id=post_id,
                    posted_at=datetime.now(timezone.utc)
                )
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error marking translation as posted: {str(e)}")
            return False
    
    def mark_as_failed(self, translation_id: int, error_message: str) -> bool:
        """Mark translation as failed"""
        try:
            translation = self.get_by_id(translation_id)
            if translation:
                self.update(
                    translation,
                    status='failed',
                    retry_count=translation.retry_count + 1,
                    error_info={
                        'message': error_message,
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'retry_count': translation.retry_count + 1
                    }
                )
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error marking translation as failed: {str(e)}")
            return False
    
    def move_draft_to_pending(self, translation_id: int) -> bool:
        """Move draft translation to pending status"""
        try:
            translation = self.get_by_id(translation_id)
            if translation and translation.status == 'draft':
                self.update(translation, status='pending')
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error moving draft to pending: {str(e)}")
            return False
    
    def get_translation_statistics(self) -> Dict[str, Any]:
        """Get translation statistics"""
        try:
            # Count by status
            status_counts = self.session.query(
                TranslationModel.status,
                func.count(TranslationModel.id).label('count')
            ).group_by(TranslationModel.status).all()
            
            # Count by language
            language_counts = self.session.query(
                TranslationModel.target_language,
                func.count(TranslationModel.id).label('count')
            ).group_by(TranslationModel.target_language).order_by(
                desc('count')
            ).limit(10).all()
            
            # Get success rate (posted vs total non-draft)
            total_non_draft = self.session.query(TranslationModel).filter(
                TranslationModel.status != 'draft'
            ).count()
            
            posted_count = self.session.query(TranslationModel).filter(
                TranslationModel.status == 'posted'
            ).count()
            
            success_rate = (posted_count / total_non_draft * 100) if total_non_draft > 0 else 0
            
            # Recent translations (last 24 hours)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            recent_count = self.session.query(TranslationModel).filter(
                TranslationModel.created_at >= recent_cutoff
            ).count()
            
            return {
                'status_counts': {status: count for status, count in status_counts},
                'language_counts': {lang: count for lang, count in language_counts},
                'success_rate': round(success_rate, 2),
                'recent_translations_24h': recent_count,
                'total_translations': self.count()
            }
        except Exception as e:
            self.logger.error(f"Error getting translation statistics: {str(e)}")
            return {}
    
    def get_translations_by_language_and_status(self, language: str, status: str) -> List[TranslationModel]:
        """Get translations filtered by language and status"""
        return self.find_by(
            target_language=language,
            status=status
        )
    
    def cleanup_old_failed_translations(self, days_old: int = 30) -> int:
        """Clean up old failed translations that can't be retried"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            
            deleted_count = self.session.query(TranslationModel).filter(
                and_(
                    TranslationModel.status == 'failed',
                    TranslationModel.updated_at < cutoff_date,
                    TranslationModel.retry_count >= 3
                )
            ).delete()
            
            self.session.flush()
            return deleted_count
        except Exception as e:
            self.logger.error(f"Error cleaning up old failed translations: {str(e)}")
            self.session.rollback()
            return 0
    
    def get_translation_audit_trail(self, tweet_id: str) -> List[Dict[str, Any]]:
        """Get audit trail for all translations of a tweet"""
        translations = self.get_translations_for_tweet(tweet_id)
        
        audit_trail = []
        for translation in translations:
            audit_entry = {
                'translation_id': translation.id,
                'language': translation.target_language,
                'status': translation.status,
                'created_at': translation.created_at,
                'updated_at': translation.updated_at,
                'posted_at': translation.posted_at,
                'retry_count': translation.retry_count,
                'character_count': translation.character_count,
                'error_info': translation.error_info
            }
            audit_trail.append(audit_entry)
        
        return audit_trail
    
    def batch_update_status(self, translation_ids: List[int], new_status: str) -> int:
        """Batch update status for multiple translations"""
        try:
            updated_count = self.session.query(TranslationModel).filter(
                TranslationModel.id.in_(translation_ids)
            ).update(
                {
                    'status': new_status,
                    'updated_at': datetime.now(timezone.utc)
                },
                synchronize_session=False
            )
            
            self.session.flush()
            return updated_count
        except Exception as e:
            self.logger.error(f"Error batch updating translation status: {str(e)}")
            self.session.rollback()
            return 0
    
    @property
    def logger(self):
        """Get logger for this repository"""
        from src.utils.logger import logger
        return logger
