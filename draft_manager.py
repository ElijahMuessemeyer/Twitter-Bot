# =============================================================================
# DRAFT MANAGEMENT SYSTEM
# =============================================================================
# Handles saving translations as drafts when Twitter API limits are exceeded

import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from src.models.tweet import Translation
from src.utils.logger import logger

class DraftManager:
    def __init__(self):
        self.pending_dir = Path('drafts/pending')
        self.posted_dir = Path('drafts/posted')
        
        # Ensure directories exist
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.posted_dir.mkdir(parents=True, exist_ok=True)
    
    def save_translation_as_draft(self, translation: Translation, language_config: dict) -> bool:
        """Save a translation as a draft file"""
        try:
            draft_data = {
                'original_tweet_id': translation.original_tweet.id,
                'original_text': translation.original_tweet.text,
                'translated_text': translation.translated_text,
                'target_language': translation.target_language,
                'language_config': language_config,
                'character_count': translation.character_count,
                'created_at': translation.translation_timestamp.isoformat(),
                'status': 'draft'
            }
            
            # Create filename with timestamp and language
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{translation.target_language}_{translation.original_tweet.id}.json"
            filepath = self.pending_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(draft_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved translation as draft: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving draft: {str(e)}")
            return False
    
    def get_pending_drafts(self) -> List[Dict]:
        """Get all pending draft files"""
        drafts = []
        
        try:
            for draft_file in self.pending_dir.glob('*.json'):
                with open(draft_file, 'r', encoding='utf-8') as f:
                    draft_data = json.load(f)
                    draft_data['file_path'] = str(draft_file)
                    drafts.append(draft_data)
        
        except Exception as e:
            logger.error(f"Error reading drafts: {str(e)}")
        
        # Sort by creation date
        drafts.sort(key=lambda x: x['created_at'])
        return drafts
    
    def mark_draft_as_posted(self, draft_file_path: str, post_id: str) -> bool:
        """Move draft from pending to posted directory"""
        try:
            draft_path = Path(draft_file_path)
            
            if not draft_path.exists():
                logger.error(f"Draft file not found: {draft_path}")
                return False
            
            # Read draft data
            with open(draft_path, 'r', encoding='utf-8') as f:
                draft_data = json.load(f)
            
            # Update with posting info
            draft_data['status'] = 'posted'
            draft_data['posted_at'] = datetime.now().isoformat()
            draft_data['post_id'] = post_id
            
            # Move to posted directory
            posted_path = self.posted_dir / draft_path.name
            with open(posted_path, 'w', encoding='utf-8') as f:
                json.dump(draft_data, f, indent=2, ensure_ascii=False)
            
            # Remove from pending
            draft_path.unlink()
            
            logger.info(f"Moved draft to posted: {posted_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error marking draft as posted: {str(e)}")
            return False
    
    def get_draft_count(self) -> int:
        """Get count of pending drafts"""
        return len(list(self.pending_dir.glob('*.json')))
    
    def display_pending_drafts(self):
        """Display pending drafts in a readable format"""
        drafts = self.get_pending_drafts()
        
        if not drafts:
            print("No pending drafts found.")
            return
        
        print(f"\n=== {len(drafts)} Pending Drafts ===\n")
        
        for i, draft in enumerate(drafts, 1):
            created_at = datetime.fromisoformat(draft['created_at'])
            print(f"{i}. [{draft['target_language'].upper()}] ({created_at.strftime('%Y-%m-%d %H:%M')})")
            print(f"   Original: {draft['original_text'][:100]}...")
            print(f"   Translation: {draft['translated_text']}")
            print(f"   Characters: {draft['character_count']}")
            print(f"   File: {Path(draft['file_path']).name}")
            print()
    
    def clear_old_drafts(self, days_old: int = 30):
        """Clear drafts older than specified days"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            removed_count = 0
            
            for draft_file in self.pending_dir.glob('*.json'):
                file_time = datetime.fromtimestamp(draft_file.stat().st_mtime)
                if file_time < cutoff_date:
                    draft_file.unlink()
                    removed_count += 1
            
            if removed_count > 0:
                logger.info(f"Removed {removed_count} old drafts")
                
        except Exception as e:
            logger.error(f"Error clearing old drafts: {str(e)}")

# Global draft manager instance
draft_manager = DraftManager()

if __name__ == "__main__":
    # Command-line interface for managing drafts
    draft_manager.display_pending_drafts()