# =============================================================================
# DATABASE-BACKED DRAFT MANAGEMENT SYSTEM
# =============================================================================
# Replaces file-based draft storage with database-backed solution

from datetime import datetime, timezone
from typing import List, Dict, Optional
from src.models.tweet import Translation
from src.models.database_models import Translation as TranslationModel
from src.repositories import TranslationRepository, TweetRepository
from src.config.database import db_config
from src.utils.logger import logger

class DatabaseDraftManager:
    """Database-backed draft management system"""
    
    def save_translation_as_draft(self, translation: Translation, language_config: dict) -> bool:
        """Save a translation as a draft in the database"""
        try:
            with db_config.get_session() as session:
                tweet_repo = TweetRepository(session)
                translation_repo = TranslationRepository(session)
                
                # Ensure the original tweet exists in database
                db_tweet = tweet_repo.get_by_id(translation.original_tweet.id)
                if not db_tweet:
                    db_tweet = tweet_repo.create_from_tweet_object(translation.original_tweet)
                
                # Create or update translation record
                existing_translation = translation_repo.get_by_tweet_and_language(
                    translation.original_tweet.id,
                    translation.target_language
                )
                
                if existing_translation:
                    # Update existing draft
                    translation_repo.update(
                        existing_translation,
                        translated_text=translation.translated_text,
                        status='draft',
                        character_count=translation.character_count,
                        translation_metadata={
                            'language_config': language_config,
                            'original_text': translation.original_tweet.text,
                            'translation_timestamp': translation.translation_timestamp.isoformat(),
                            'draft_saved_at': datetime.now(timezone.utc).isoformat()
                        }
                    )
                    logger.info(f"Updated existing draft for tweet {translation.original_tweet.id} in {translation.target_language}")
                else:
                    # Create new draft
                    db_translation = translation_repo.create(
                        original_tweet_id=translation.original_tweet.id,
                        translated_text=translation.translated_text,
                        target_language=translation.target_language,
                        status='draft',
                        character_count=translation.character_count,
                        translation_metadata={
                            'language_config': language_config,
                            'original_text': translation.original_tweet.text,
                            'translation_timestamp': translation.translation_timestamp.isoformat(),
                            'draft_saved_at': datetime.now(timezone.utc).isoformat()
                        }
                    )
                    logger.info(f"Saved new draft for tweet {translation.original_tweet.id} in {translation.target_language}")
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error saving translation as draft: {str(e)}")
            return False
    
    def get_pending_drafts(self) -> List[Dict]:
        """Get all pending draft translations"""
        try:
            with db_config.get_session() as session:
                translation_repo = TranslationRepository(session)
                draft_translations = translation_repo.get_draft_translations()
                
                drafts = []
                for db_translation in draft_translations:
                    draft_data = {
                        'id': db_translation.id,
                        'original_tweet_id': db_translation.original_tweet_id,
                        'original_text': db_translation.original_tweet.text,
                        'translated_text': db_translation.translated_text,
                        'target_language': db_translation.target_language,
                        'character_count': db_translation.character_count,
                        'created_at': db_translation.created_at.isoformat(),
                        'language_config': db_translation.translation_metadata.get('language_config', {}),
                        'translation_timestamp': db_translation.translation_metadata.get('translation_timestamp')
                    }
                    drafts.append(draft_data)
                
                return drafts
                
        except Exception as e:
            logger.error(f"Error getting pending drafts: {str(e)}")
            return []
    
    def mark_draft_as_posted(self, draft_id: int, post_id: str) -> bool:
        """Move draft from pending to posted status"""
        try:
            with db_config.get_session() as session:
                translation_repo = TranslationRepository(session)
                
                success = translation_repo.mark_as_posted(draft_id, post_id)
                if success:
                    session.commit()
                    logger.info(f"Marked draft {draft_id} as posted with ID {post_id}")
                    return True
                else:
                    logger.warning(f"Could not find draft with ID {draft_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error marking draft as posted: {str(e)}")
            return False
    
    def get_draft_count(self) -> int:
        """Get count of pending drafts"""
        try:
            with db_config.get_session() as session:
                translation_repo = TranslationRepository(session)
                return translation_repo.count(status='draft')
                
        except Exception as e:
            logger.error(f"Error getting draft count: {str(e)}")
            return 0
    
    def display_pending_drafts(self):
        """Display pending drafts in a readable format"""
        drafts = self.get_pending_drafts()
        
        if not drafts:
            print("No pending drafts found.")
            return
        
        print(f"\n=== {len(drafts)} Pending Drafts ===\n")
        
        for i, draft in enumerate(drafts, 1):
            created_at = datetime.fromisoformat(draft['created_at']).replace(tzinfo=timezone.utc)
            print(f"{i}. [{draft['target_language'].upper()}] ({created_at.strftime('%Y-%m-%d %H:%M')})")
            print(f"   Original: {draft['original_text'][:100]}...")
            print(f"   Translation: {draft['translated_text']}")
            print(f"   Characters: {draft['character_count']}")
            print(f"   Draft ID: {draft['id']}")
            print()
    
    def move_draft_to_pending(self, draft_id: int) -> bool:
        """Move a draft to pending status for posting"""
        try:
            with db_config.get_session() as session:
                translation_repo = TranslationRepository(session)
                
                success = translation_repo.move_draft_to_pending(draft_id)
                if success:
                    session.commit()
                    logger.info(f"Moved draft {draft_id} to pending status")
                    return True
                else:
                    logger.warning(f"Could not find draft with ID {draft_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error moving draft to pending: {str(e)}")
            return False
    
    def delete_draft(self, draft_id: int) -> bool:
        """Delete a draft translation"""
        try:
            with db_config.get_session() as session:
                translation_repo = TranslationRepository(session)
                
                draft = translation_repo.get_by_id(draft_id)
                if draft and draft.status == 'draft':
                    translation_repo.delete(draft)
                    session.commit()
                    logger.info(f"Deleted draft {draft_id}")
                    return True
                else:
                    logger.warning(f"Could not find draft with ID {draft_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error deleting draft: {str(e)}")
            return False
    
    def clear_old_drafts(self, days_old: int = 30) -> int:
        """Clear drafts older than specified days"""
        try:
            with db_config.get_session() as session:
                translation_repo = TranslationRepository(session)
                
                # Get drafts older than specified days
                from datetime import timedelta
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
                
                old_drafts = session.query(TranslationModel).filter(
                    TranslationModel.status == 'draft',
                    TranslationModel.created_at < cutoff_date
                ).all()
                
                removed_count = 0
                for draft in old_drafts:
                    translation_repo.delete(draft)
                    removed_count += 1
                
                if removed_count > 0:
                    session.commit()
                    logger.info(f"Removed {removed_count} old drafts")
                
                return removed_count
                
        except Exception as e:
            logger.error(f"Error clearing old drafts: {str(e)}")
            return 0
    
    def get_draft_statistics(self) -> Dict:
        """Get statistics about drafts"""
        try:
            with db_config.get_session() as session:
                translation_repo = TranslationRepository(session)
                
                stats = translation_repo.get_translation_statistics()
                return {
                    'total_drafts': stats.get('status_counts', {}).get('draft', 0),
                    'draft_by_language': {},  # Could be enhanced to get language breakdown
                    'oldest_draft_age': None,  # Could be enhanced
                    'total_pending': stats.get('status_counts', {}).get('pending', 0),
                    'total_posted': stats.get('status_counts', {}).get('posted', 0)
                }
                
        except Exception as e:
            logger.error(f"Error getting draft statistics: {str(e)}")
            return {}

# Global instance
database_draft_manager = DatabaseDraftManager()
