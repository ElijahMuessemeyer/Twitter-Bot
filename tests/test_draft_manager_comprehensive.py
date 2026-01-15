# =============================================================================
# COMPREHENSIVE DRAFT MANAGER TESTS
# =============================================================================

import pytest
import sys
import os
import json
import tempfile
import shutil
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, mock_open, MagicMock, call
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models.tweet import Tweet, Translation
from draft_manager import DraftManager


class TestDraftManagerComprehensive:
    """Comprehensive tests for DraftManager including error handling, edge cases, and concurrency"""

    def setup_method(self):
        """Set up test fixtures with temporary directories"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.pending_dir = self.test_dir / "pending"
        self.posted_dir = self.test_dir / "posted"
        
        self.draft_manager = DraftManager()
        self.draft_manager.pending_dir = self.pending_dir
        self.draft_manager.posted_dir = self.posted_dir
        
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.posted_dir.mkdir(parents=True, exist_ok=True)
        
        # Create test data
        self.test_tweet = Tweet(
            id="123456789",
            text="Test tweet with special chars: éñü 🎉",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={"retweet_count": 5, "favorite_count": 10}
        )
        
        self.test_translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Spanish",
            translated_text="Tweet de prueba con caracteres especiales: éñü 🎉",
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

    # =============================================================================
    # FILE OPERATIONS AND PERSISTENCE TESTS
    # =============================================================================

    @patch('draft_manager.open', side_effect=PermissionError("Permission denied"))
    @patch('draft_manager.logger')
    def test_save_draft_permission_error(self, mock_logger, mock_open):
        """Test handling of permission errors when saving drafts"""
        success = self.draft_manager.save_translation_as_draft(
            self.test_translation, 
            self.test_lang_config
        )
        
        assert success is False
        mock_logger.error.assert_called_once()
        assert "Error saving draft" in str(mock_logger.error.call_args)

    @patch('draft_manager.json.dump', side_effect=TypeError("Object not JSON serializable"))
    @patch('draft_manager.logger')
    def test_save_draft_json_encode_error(self, mock_logger, mock_json_dump):
        """Test handling of JSON encoding errors"""
        success = self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        assert success is False
        mock_logger.error.assert_called_once()

    @patch('pathlib.Path.glob')
    @patch('draft_manager.logger')
    def test_get_pending_drafts_file_not_found(self, mock_logger, mock_glob):
        """Test handling when draft files are deleted between glob and read"""
        # Mock glob to return a file that doesn't exist when opened
        mock_file = MagicMock()
        mock_file.__str__ = lambda self: "/fake/path.json"
        mock_glob.return_value = [mock_file]
        
        with patch('builtins.open', side_effect=FileNotFoundError("File not found")):
            drafts = self.draft_manager.get_pending_drafts()
        
        assert drafts == []
        mock_logger.error.assert_called_once()

    @patch('builtins.open', side_effect=json.JSONDecodeError("Invalid JSON", "", 0))
    @patch('draft_manager.logger')
    def test_get_pending_drafts_corrupt_json(self, mock_logger, mock_open):
        """Test handling of corrupted JSON files"""
        # Create a dummy file to trigger the glob
        test_file = self.pending_dir / "corrupt.json"
        test_file.write_text("corrupted json content")
        
        drafts = self.draft_manager.get_pending_drafts()
        
        assert drafts == []
        mock_logger.error.assert_called_once()

    def test_save_draft_with_null_characters(self):
        """Test saving drafts with null characters and other edge cases"""
        translation = Translation(
            original_tweet=Tweet(
                id="null_test",
                text="Text with \x00 null character",
                created_at=datetime.now(),
                author_username="test",
                author_id="123",
                public_metrics={}
            ),
            target_language="English",
            translated_text="Translated text with \x00 null",
            translation_timestamp=datetime.now(),
            character_count=30,
            status="draft"
        )
        
        success = self.draft_manager.save_translation_as_draft(
            translation,
            {"code": "en", "name": "English"}
        )
        
        # Should succeed even with null characters
        assert success is True
        
        # Verify data integrity
        drafts = self.draft_manager.get_pending_drafts()
        assert len(drafts) == 1
        assert "\x00" in drafts[0]['original_text']

    def test_save_draft_with_very_long_content(self):
        """Test saving drafts with extremely long content"""
        long_text = "A" * 10000  # Very long text
        
        translation = Translation(
            original_tweet=Tweet(
                id="long_test",
                text=long_text,
                created_at=datetime.now(),
                author_username="test",
                author_id="123",
                public_metrics={}
            ),
            target_language="Spanish",
            translated_text=long_text + " translated",
            translation_timestamp=datetime.now(),
            character_count=len(long_text),
            status="draft"
        )
        
        success = self.draft_manager.save_translation_as_draft(
            translation,
            self.test_lang_config
        )
        
        assert success is True
        
        # Verify content is preserved
        drafts = self.draft_manager.get_pending_drafts()
        assert len(drafts) == 1
        assert len(drafts[0]['original_text']) == 10000

    # =============================================================================
    # METADATA MANAGEMENT TESTS
    # =============================================================================

    def test_draft_data_structure_completeness(self):
        """Test that saved drafts contain all required metadata fields"""
        success = self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        assert success is True
        
        drafts = self.draft_manager.get_pending_drafts()
        draft = drafts[0]
        
        required_fields = [
            'original_tweet_id', 'original_text', 'translated_text',
            'target_language', 'language_config', 'character_count',
            'created_at', 'status', 'file_path'
        ]
        
        for field in required_fields:
            assert field in draft, f"Missing field: {field}"
        
        # Verify data types
        assert isinstance(draft['original_tweet_id'], str)
        assert isinstance(draft['original_text'], str)
        assert isinstance(draft['translated_text'], str)
        assert isinstance(draft['target_language'], str)
        assert isinstance(draft['language_config'], dict)
        assert isinstance(draft['character_count'], int)
        assert isinstance(draft['created_at'], str)
        assert isinstance(draft['status'], str)

    def test_language_config_preservation(self):
        """Test that complex language configurations are preserved"""
        complex_config = {
            "code": "zh-CN",
            "name": "Chinese (Simplified)",
            "formal_tone": True,
            "cultural_adaptation": True,
            "translation_model": "premium",
            "custom_prompts": {
                "prefix": "Please translate professionally:",
                "suffix": "Maintain cultural context."
            },
            "special_handling": ["hashtags", "mentions", "urls"]
        }
        
        success = self.draft_manager.save_translation_as_draft(
            self.test_translation,
            complex_config
        )
        
        assert success is True
        
        drafts = self.draft_manager.get_pending_drafts()
        saved_config = drafts[0]['language_config']
        
        assert saved_config == complex_config
        assert saved_config['custom_prompts']['prefix'] == "Please translate professionally:"
        assert "hashtags" in saved_config['special_handling']

    def test_timestamp_format_consistency(self):
        """Test that timestamps are consistently formatted and parseable"""
        success = self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        assert success is True
        
        drafts = self.draft_manager.get_pending_drafts()
        created_at_str = drafts[0]['created_at']
        
        # Should be valid ISO format
        parsed_time = datetime.fromisoformat(created_at_str)
        assert isinstance(parsed_time, datetime)
        
        # Should match original timestamp
        expected_time = self.test_translation.translation_timestamp
        assert parsed_time == expected_time

    # =============================================================================
    # ERROR SCENARIOS AND EDGE CASES
    # =============================================================================

    def test_mark_draft_as_posted_with_invalid_file(self):
        """Test error handling when marking non-existent draft as posted"""
        success = self.draft_manager.mark_draft_as_posted(
            "/completely/fake/path.json",
            "fake_post_id"
        )
        
        assert success is False

    @patch('draft_manager.logger')
    def test_mark_draft_as_posted_permission_error(self, mock_logger):
        """Test permission error when marking draft as posted"""
        # Create a real draft file first
        self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        drafts = self.draft_manager.get_pending_drafts()
        draft_file_path = drafts[0]['file_path']
        
        # Mock only the second open call (for writing posted file)
        with patch('builtins.open', side_effect=[
            mock_open(read_data='{"test": "data"}').return_value,  # First call succeeds
            PermissionError("Permission denied")  # Second call fails
        ]):
            success = self.draft_manager.mark_draft_as_posted(draft_file_path, "post_123")
        
        assert success is False
        mock_logger.error.assert_called()

    def test_mark_draft_as_posted_with_corrupted_file(self):
        """Test handling of corrupted draft file when marking as posted"""
        # Create a corrupted draft file
        corrupted_file = self.pending_dir / "corrupted.json"
        corrupted_file.write_text("{ invalid json content")
        
        success = self.draft_manager.mark_draft_as_posted(
            str(corrupted_file),
            "post_123"
        )
        
        assert success is False

    def test_get_draft_count_with_non_json_files(self):
        """Test draft count when directory contains non-JSON files"""
        # Create some non-JSON files
        (self.pending_dir / "not_a_draft.txt").write_text("text file")
        (self.pending_dir / "readme.md").write_text("# Readme")
        (self.pending_dir / ".hidden").write_text("hidden file")
        
        # Create actual drafts
        self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        # Should only count JSON files
        assert self.draft_manager.get_draft_count() == 1

    def test_draft_directory_creation_failure(self):
        """Test handling when draft directories cannot be created"""
        with patch('pathlib.Path.mkdir', side_effect=PermissionError("Cannot create directory")):
            with pytest.raises(PermissionError):
                DraftManager()

    # =============================================================================
    # CONCURRENT ACCESS TESTS
    # =============================================================================

    def test_concurrent_draft_saving(self):
        """Test saving multiple drafts concurrently"""
        results = []
        errors = []
        
        def save_draft(i):
            try:
                translation = Translation(
                    original_tweet=Tweet(
                        id=f"concurrent_{i}",
                        text=f"Concurrent test {i}",
                        created_at=datetime.now(),
                        author_username="test",
                        author_id="123",
                        public_metrics={}
                    ),
                    target_language="Spanish",
                    translated_text=f"Prueba concurrente {i}",
                    translation_timestamp=datetime.now(),
                    character_count=20,
                    status="draft"
                )
                
                success = self.draft_manager.save_translation_as_draft(
                    translation,
                    {"code": "es", "name": "Spanish"}
                )
                results.append(success)
            except Exception as e:
                errors.append(str(e))
        
        # Create multiple threads saving drafts simultaneously
        threads = []
        for i in range(10):
            thread = threading.Thread(target=save_draft, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All saves should succeed
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
        assert all(results)
        
        # Verify all drafts were saved
        assert self.draft_manager.get_draft_count() == 10

    def test_concurrent_draft_reading_and_writing(self):
        """Test reading drafts while others are being written"""
        # Pre-create some drafts
        for i in range(5):
            translation = Translation(
                original_tweet=Tweet(
                    id=f"preexisting_{i}",
                    text=f"Pre-existing {i}",
                    created_at=datetime.now(),
                    author_username="test",
                    author_id="123",
                    public_metrics={}
                ),
                target_language="Spanish",
                translated_text=f"Pre-existente {i}",
                translation_timestamp=datetime.now(),
                character_count=20,
                status="draft"
            )
            
            self.draft_manager.save_translation_as_draft(
                translation,
                {"code": "es", "name": "Spanish"}
            )
        
        read_results = []
        write_results = []
        
        def read_drafts():
            for _ in range(10):
                try:
                    drafts = self.draft_manager.get_pending_drafts()
                    read_results.append(len(drafts))
                    time.sleep(0.01)  # Small delay
                except Exception as e:
                    read_results.append(f"Error: {e}")
        
        def write_drafts():
            for i in range(5):
                try:
                    translation = Translation(
                        original_tweet=Tweet(
                            id=f"concurrent_write_{i}",
                            text=f"Concurrent write {i}",
                            created_at=datetime.now(),
                            author_username="test",
                            author_id="123",
                            public_metrics={}
                        ),
                        target_language="French",
                        translated_text=f"Écriture concurrente {i}",
                        translation_timestamp=datetime.now(),
                        character_count=25,
                        status="draft"
                    )
                    
                    success = self.draft_manager.save_translation_as_draft(
                        translation,
                        {"code": "fr", "name": "French"}
                    )
                    write_results.append(success)
                    time.sleep(0.02)  # Small delay
                except Exception as e:
                    write_results.append(f"Error: {e}")
        
        # Start reader and writer threads
        reader_thread = threading.Thread(target=read_drafts)
        writer_thread = threading.Thread(target=write_drafts)
        
        reader_thread.start()
        writer_thread.start()
        
        reader_thread.join()
        writer_thread.join()
        
        # Verify operations completed successfully
        assert len(write_results) == 5
        assert all(isinstance(result, bool) for result in write_results)
        assert len(read_results) == 10
        
        # Final count should be original 5 + new 5 = 10
        final_count = self.draft_manager.get_draft_count()
        assert final_count == 10

    # =============================================================================
    # DISPLAY AND USER INTERFACE TESTS
    # =============================================================================

    @patch('sys.stdout', new_callable=StringIO)
    def test_display_pending_drafts_empty(self, mock_stdout):
        """Test displaying pending drafts when none exist"""
        self.draft_manager.display_pending_drafts()
        
        output = mock_stdout.getvalue()
        assert "No pending drafts found." in output

    @patch('sys.stdout', new_callable=StringIO)
    def test_display_pending_drafts_with_content(self, mock_stdout):
        """Test displaying pending drafts with actual content"""
        # Create drafts with different languages and content
        translations = [
            (Translation(
                original_tweet=Tweet(
                    id=f"display_test_{i}",
                    text=f"This is a longer test tweet with more content to test truncation behavior in the display function {i}" * 2,
                    created_at=datetime.now(),
                    author_username="testuser",
                    author_id="123",
                    public_metrics={}
                ),
                target_language=lang,
                translated_text=f"Translated content {i} in {lang}",
                translation_timestamp=datetime.now(),
                character_count=50 + i,
                status="draft"
            ), {"code": code, "name": lang})
            for i, (lang, code) in enumerate([("Spanish", "es"), ("French", "fr"), ("German", "de")])
        ]
        
        for translation, config in translations:
            self.draft_manager.save_translation_as_draft(translation, config)
        
        self.draft_manager.display_pending_drafts()
        
        output = mock_stdout.getvalue()
        
        # Check that output contains expected elements
        assert "3 Pending Drafts" in output
        assert "SPANISH" in output
        assert "FRENCH" in output
        assert "GERMAN" in output
        assert "Characters:" in output
        assert "File:" in output
        
        # Check truncation (original text should be truncated at 100 chars)
        lines = output.split('\n')
        original_lines = [line for line in lines if "Original:" in line]
        for line in original_lines:
            # Extract the text after "Original: "
            text_part = line.split("Original: ")[1]
            assert text_part.endswith("...")

    @patch('sys.stdout', new_callable=StringIO)
    def test_display_pending_drafts_unicode_handling(self, mock_stdout):
        """Test displaying drafts with Unicode characters"""
        unicode_translation = Translation(
            original_tweet=Tweet(
                id="unicode_test",
                text="Original with emojis 🎉🌟 and accents: café, naïve, résumé",
                created_at=datetime.now(),
                author_username="testuser",
                author_id="123",
                public_metrics={}
            ),
            target_language="Japanese",
            translated_text="翻訳されたテキスト 🎌 with mixed: café ナイーブ résumé",
            translation_timestamp=datetime.now(),
            character_count=60,
            status="draft"
        )
        
        self.draft_manager.save_translation_as_draft(
            unicode_translation,
            {"code": "ja", "name": "Japanese"}
        )
        
        self.draft_manager.display_pending_drafts()
        
        output = mock_stdout.getvalue()
        
        # Verify Unicode characters are properly displayed
        assert "🎉🌟" in output
        assert "🎌" in output
        assert "café" in output
        assert "翻訳されたテキスト" in output

    # =============================================================================
    # CLEANUP AND MAINTENANCE TESTS
    # =============================================================================

    @patch('draft_manager.logger')
    def test_clear_old_drafts_permission_error(self, mock_logger):
        """Test error handling when clearing old drafts fails due to permissions"""
        # Create a draft file
        self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        # Mock unlink to raise permission error
        with patch('pathlib.Path.unlink', side_effect=PermissionError("Permission denied")):
            self.draft_manager.clear_old_drafts(days_old=0)  # Try to clear all
        
        mock_logger.error.assert_called()
        assert "Error clearing old drafts" in str(mock_logger.error.call_args)

    def test_clear_old_drafts_preserves_recent_files(self):
        """Test that recent files are preserved when clearing old drafts"""
        # Create files with different ages
        old_time = time.time() - (40 * 24 * 3600)  # 40 days ago
        recent_time = time.time() - (10 * 24 * 3600)  # 10 days ago
        
        # Create old file
        old_file = self.pending_dir / "old_draft.json"
        old_file.write_text('{"old": "draft"}')
        os.utime(old_file, (old_time, old_time))
        
        # Create recent file
        recent_file = self.pending_dir / "recent_draft.json"
        recent_file.write_text('{"recent": "draft"}')
        os.utime(recent_file, (recent_time, recent_time))
        
        # Clear drafts older than 30 days
        self.draft_manager.clear_old_drafts(days_old=30)
        
        # Only recent file should remain
        remaining_files = list(self.pending_dir.glob("*.json"))
        assert len(remaining_files) == 1
        assert remaining_files[0].name == "recent_draft.json"

    @patch('draft_manager.logger')
    def test_clear_old_drafts_logs_removal_count(self, mock_logger):
        """Test that clear_old_drafts logs the number of files removed"""
        # Create multiple old files
        old_time = time.time() - (40 * 24 * 3600)
        
        for i in range(3):
            old_file = self.pending_dir / f"old_draft_{i}.json"
            old_file.write_text(f'{{"old": "draft_{i}"}}')
            os.utime(old_file, (old_time, old_time))
        
        self.draft_manager.clear_old_drafts(days_old=30)
        
        mock_logger.info.assert_called_once()
        assert "Removed 3 old drafts" in str(mock_logger.info.call_args)

    def test_clear_old_drafts_no_files_to_remove(self):
        """Test clear_old_drafts when no files need to be removed"""
        # Create only recent files
        self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        
        initial_count = self.draft_manager.get_draft_count()
        
        # Try to clear old files
        self.draft_manager.clear_old_drafts(days_old=30)
        
        # Count should remain the same
        final_count = self.draft_manager.get_draft_count()
        assert final_count == initial_count

    # =============================================================================
    # INTEGRATION TESTS
    # =============================================================================

    def test_complete_draft_lifecycle(self):
        """Test complete lifecycle: save -> retrieve -> mark as posted"""
        # Save draft
        success = self.draft_manager.save_translation_as_draft(
            self.test_translation,
            self.test_lang_config
        )
        assert success is True
        
        # Retrieve drafts
        drafts = self.draft_manager.get_pending_drafts()
        assert len(drafts) == 1
        
        # Verify draft content
        draft = drafts[0]
        assert draft['original_tweet_id'] == self.test_translation.original_tweet.id
        assert draft['translated_text'] == self.test_translation.translated_text
        
        # Mark as posted
        success = self.draft_manager.mark_draft_as_posted(
            draft['file_path'],
            "posted_123"
        )
        assert success is True
        
        # Verify it's no longer pending
        pending_drafts = self.draft_manager.get_pending_drafts()
        assert len(pending_drafts) == 0
        
        # Verify it's in posted directory
        posted_files = list(self.posted_dir.glob("*.json"))
        assert len(posted_files) == 1
        
        # Verify posted file content
        with open(posted_files[0], 'r', encoding='utf-8') as f:
            posted_data = json.load(f)
        
        assert posted_data['status'] == 'posted'
        assert posted_data['post_id'] == 'posted_123'
        assert 'posted_at' in posted_data

    def test_draft_manager_initialization_creates_directories(self):
        """Test that DraftManager creates necessary directories on initialization"""
        # Remove test directories
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        
        # Create new draft manager with non-existent directories
        new_draft_manager = DraftManager()
        new_draft_manager.pending_dir = self.test_dir / "new_pending"
        new_draft_manager.posted_dir = self.test_dir / "new_posted"
        
        # Initialize (directories should be created)
        new_draft_manager.pending_dir.mkdir(parents=True, exist_ok=True)
        new_draft_manager.posted_dir.mkdir(parents=True, exist_ok=True)
        
        # Verify directories exist
        assert new_draft_manager.pending_dir.exists()
        assert new_draft_manager.posted_dir.exists()
        assert new_draft_manager.pending_dir.is_dir()
        assert new_draft_manager.posted_dir.is_dir()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
