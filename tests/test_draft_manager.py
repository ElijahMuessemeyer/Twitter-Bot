# =============================================================================
# DRAFT MANAGER TESTS
# =============================================================================

import pytest
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models.tweet import Tweet, Translation
from draft_manager import DraftManager

class TestDraftManager:
    def setup_method(self):
        """Set up test fixtures with temporary directories"""
        # Create temporary directory for tests
        self.test_dir = Path(tempfile.mkdtemp())
        self.pending_dir = self.test_dir / "pending"
        self.posted_dir = self.test_dir / "posted"
        
        # Create test draft manager with temporary directories
        self.draft_manager = DraftManager()
        self.draft_manager.pending_dir = self.pending_dir
        self.draft_manager.posted_dir = self.posted_dir
        
        # Ensure directories exist
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.posted_dir.mkdir(parents=True, exist_ok=True)
        
        # Create test tweet and translation
        self.test_tweet = Tweet(
            id="123456789",
            text="This is a test tweet #test @user https://example.com",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={"retweet_count": 5, "favorite_count": 10}
        )
        
        self.test_translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Spanish",
            translated_text="Este es un tweet de prueba #test @user https://example.com",
            translation_timestamp=datetime(2024, 1, 1, 12, 5, 0),
            character_count=58,
            status="draft"
        )
        
        self.test_lang_config = {
            "code": "es",
            "name": "Spanish",
            "formal_tone": False,
            "cultural_adaptation": True
        }
    
    def teardown_method(self):
        """Clean up temporary directories"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_save_translation_as_draft(self):
        """Test saving a translation as a draft file"""
        success = self.draft_manager.save_translation_as_draft(
            self.test_translation, 
            self.test_lang_config
        )
        
        assert success == True
        
        # Check that draft file was created
        draft_files = list(self.pending_dir.glob("*.json"))
        assert len(draft_files) == 1
        
        # Check draft file content
        with open(draft_files[0], 'r', encoding='utf-8') as f:
            draft_data = json.load(f)
        
        assert draft_data['original_tweet_id'] == "123456789"
        assert draft_data['original_text'] == self.test_tweet.text
        assert draft_data['translated_text'] == self.test_translation.translated_text
        assert draft_data['target_language'] == "Spanish"
        assert draft_data['character_count'] == 58
        assert draft_data['status'] == "draft"
    
    def test_get_pending_drafts_empty(self):
        """Test getting pending drafts when none exist"""
        drafts = self.draft_manager.get_pending_drafts()
        assert drafts == []
    
    def test_get_pending_drafts_with_drafts(self):
        """Test getting pending drafts when drafts exist"""
        # Save a draft first
        self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        drafts = self.draft_manager.get_pending_drafts()
        assert len(drafts) == 1
        assert drafts[0]['original_tweet_id'] == "123456789"
        assert drafts[0]['target_language'] == "Spanish"
        assert 'file_path' in drafts[0]
    
    def test_mark_draft_as_posted(self):
        """Test moving draft from pending to posted"""
        # Save a draft first
        self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        # Get the draft file path
        drafts = self.draft_manager.get_pending_drafts()
        draft_file_path = drafts[0]['file_path']
        
        # Mark as posted
        success = self.draft_manager.mark_draft_as_posted(draft_file_path, "posted_tweet_id_123")
        
        assert success == True
        
        # Check that file moved from pending to posted
        assert len(list(self.pending_dir.glob("*.json"))) == 0
        posted_files = list(self.posted_dir.glob("*.json"))
        assert len(posted_files) == 1
        
        # Check posted file content
        with open(posted_files[0], 'r', encoding='utf-8') as f:
            posted_data = json.load(f)
        
        assert posted_data['status'] == "posted"
        assert posted_data['post_id'] == "posted_tweet_id_123"
        assert 'posted_at' in posted_data
    
    def test_mark_nonexistent_draft_as_posted(self):
        """Test marking non-existent draft as posted"""
        success = self.draft_manager.mark_draft_as_posted("/nonexistent/path.json", "123")
        assert success == False
    
    def test_get_draft_count(self):
        """Test getting count of pending drafts"""
        assert self.draft_manager.get_draft_count() == 0
        
        # Add some drafts
        self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        # Create a second translation for testing
        translation2 = Translation(
            original_tweet=self.test_tweet,
            target_language="French",
            translated_text="Ceci est un tweet de test",
            translation_timestamp=datetime.now(),
            character_count=25,
            status="draft"
        )
        
        lang_config2 = {"code": "fr", "name": "French"}
        self.draft_manager.save_translation_as_draft(translation2, lang_config2)
        
        assert self.draft_manager.get_draft_count() == 2
    
    def test_save_draft_with_unicode(self):
        """Test saving draft with Unicode characters"""
        # Create translation with Unicode characters
        unicode_translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Japanese",
            translated_text="これは日本語のテストツイートです 🎌",
            translation_timestamp=datetime.now(),
            character_count=20,
            status="draft"
        )
        
        lang_config = {"code": "ja", "name": "Japanese"}
        
        success = self.draft_manager.save_translation_as_draft(
            unicode_translation,
            lang_config
        )
        
        assert success == True
        
        # Verify Unicode characters are preserved
        drafts = self.draft_manager.get_pending_drafts()
        assert len(drafts) == 1
        assert "これは日本語のテストツイートです 🎌" in drafts[0]['translated_text']
    
    def test_draft_filename_format(self):
        """Test that draft filenames follow expected format"""
        self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        draft_files = list(self.pending_dir.glob("*.json"))
        assert len(draft_files) == 1
        
        filename = draft_files[0].name
        # Format should be: YYYYMMDD_HHMMSS_language_tweetid.json
        parts = filename.replace('.json', '').split('_')
        assert len(parts) >= 3
        assert parts[-1] == "123456789"  # tweet ID
        assert parts[-2] == "Spanish"    # language
        # First part should be timestamp in YYYYMMDD format
        assert len(parts[0]) == 8 and parts[0].isdigit()
    
    def test_clear_old_drafts(self):
        """Test clearing old draft files"""
        import os
        import time
        
        # Create an old draft file manually
        old_draft_path = self.pending_dir / "old_draft.json"
        old_draft_data = {
            'original_tweet_id': '999',
            'created_at': (datetime.now() - timedelta(days=35)).isoformat()
        }
        
        with open(old_draft_path, 'w') as f:
            json.dump(old_draft_data, f)
        
        # Set file modification time to 35 days ago
        old_time = time.time() - (35 * 24 * 3600)  # 35 days ago in seconds
        os.utime(old_draft_path, (old_time, old_time))
        
        # Create a recent draft
        self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        # Clear old drafts (older than 30 days)
        self.draft_manager.clear_old_drafts(days_old=30)
        
        # Should have 1 draft remaining (the recent one)
        remaining_drafts = list(self.pending_dir.glob("*.json"))
        assert len(remaining_drafts) == 1
        
        # The remaining draft should be the recent one, not the old one
        with open(remaining_drafts[0], 'r') as f:
            data = json.load(f)
        assert data['original_tweet_id'] == "123456789"  # Recent draft
    
    def test_draft_sorting_by_date(self):
        """Test that drafts are sorted by creation date"""
        # Create multiple drafts with different timestamps
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        
        for i in range(3):
            translation = Translation(
                original_tweet=Tweet(
                    id=f"tweet_{i}",
                    text=f"Tweet {i}",
                    created_at=base_time,
                    author_username="test",
                    author_id="123",
                    public_metrics={}
                ),
                target_language="Spanish",
                translated_text=f"Tweet {i} en español",
                translation_timestamp=base_time + timedelta(minutes=i),
                character_count=20,
                status="draft"
            )
            
            self.draft_manager.save_translation_as_draft(
                translation,
                self.test_lang_config
            )
        
        drafts = self.draft_manager.get_pending_drafts()
        assert len(drafts) == 3
        
        # Should be sorted by creation date (earliest first)
        for i in range(len(drafts) - 1):
            current_time = datetime.fromisoformat(drafts[i]['created_at'])
            next_time = datetime.fromisoformat(drafts[i + 1]['created_at'])
            assert current_time <= next_time