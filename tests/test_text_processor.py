# =============================================================================
# TEXT PROCESSOR TESTS
# =============================================================================

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils.text_processor import TextProcessor

class TestTextProcessor:
    def setup_method(self):
        self.processor = TextProcessor()
    
    def test_extract_hashtags(self):
        """Test hashtag extraction"""
        text = "This is a tweet with #hashtag and #another_tag"
        clean_text, placeholder_map = self.processor.extract_preservable_elements(text)
        
        assert "{HASHTAG_0}" in clean_text
        assert "{HASHTAG_1}" in clean_text
        assert "{HASHTAG_0}" in placeholder_map
        assert "{HASHTAG_1}" in placeholder_map
        assert placeholder_map["{HASHTAG_0}"] == "#hashtag"
        assert placeholder_map["{HASHTAG_1}"] == "#another_tag"
    
    def test_extract_mentions(self):
        """Test mention extraction"""
        text = "Hello @user1 and @user2!"
        clean_text, placeholder_map = self.processor.extract_preservable_elements(text)
        
        assert "{MENTION_0}" in clean_text
        assert "{MENTION_1}" in clean_text
        assert placeholder_map["{MENTION_0}"] == "@user1"
        assert placeholder_map["{MENTION_1}"] == "@user2"
    
    def test_extract_urls(self):
        """Test URL extraction"""
        text = "Check out https://example.com and http://test.org"
        clean_text, placeholder_map = self.processor.extract_preservable_elements(text)
        
        assert "{URL_0}" in clean_text
        assert "{URL_1}" in clean_text
        assert placeholder_map["{URL_0}"] == "https://example.com"
        assert placeholder_map["{URL_1}"] == "http://test.org"
    
    def test_extract_mixed_elements(self):
        """Test extraction of mixed hashtags, mentions, and URLs"""
        text = "Tweet with @user #hashtag and https://example.com"
        clean_text, placeholder_map = self.processor.extract_preservable_elements(text)
        
        # Should have all three types
        assert any("URL_" in key for key in placeholder_map.keys())
        assert any("MENTION_" in key for key in placeholder_map.keys()) 
        assert any("HASHTAG_" in key for key in placeholder_map.keys())
        
        # Original elements should be preserved
        assert "https://example.com" in placeholder_map.values()
        assert "@user" in placeholder_map.values()
        assert "#hashtag" in placeholder_map.values()
    
    def test_restore_preservable_elements(self):
        """Test restoration of preserved elements"""
        original_text = "Tweet with @user #hashtag and https://example.com"
        clean_text, placeholder_map = self.processor.extract_preservable_elements(original_text)
        
        # Simulate translation (keep placeholders intact for restoration test)
        translated_text = clean_text.replace("Tweet", "Mensaje")
        
        # Restore elements
        restored_text = self.processor.restore_preservable_elements(translated_text, placeholder_map)
        
        # Should contain original preservable elements
        assert "@user" in restored_text
        assert "#hashtag" in restored_text
        assert "https://example.com" in restored_text
    
    def test_character_count_without_urls(self):
        """Test character counting without URLs"""
        text = "This is a test tweet"
        count = self.processor.get_character_count(text)
        assert count == len(text)
    
    def test_character_count_with_urls(self):
        """Test character counting with URLs (should count as 23 chars each)"""
        text = "Check out https://example.com"
        count = self.processor.get_character_count(text)
        
        # "Check out " = 10 chars + 23 for URL = 33
        expected = len("Check out ") + 23
        assert count == expected
    
    def test_character_count_multiple_urls(self):
        """Test character counting with multiple URLs"""
        text = "Links: https://example.com and http://test.org"
        count = self.processor.get_character_count(text)
        
        # "Links:  and " = 12 chars + 23 + 23 for URLs = 58
        expected = len("Links:  and ") + (23 * 2)
        assert count == expected
    
    def test_within_twitter_limit(self):
        """Test Twitter character limit checking"""
        short_text = "This is short"
        long_text = "x" * 300  # Over 280 limit
        
        assert self.processor.is_within_twitter_limit(short_text) == True
        assert self.processor.is_within_twitter_limit(long_text) == False
    
    def test_within_custom_limit(self):
        """Test custom character limit checking"""
        text = "x" * 150
        
        assert self.processor.is_within_twitter_limit(text, limit=200) == True
        assert self.processor.is_within_twitter_limit(text, limit=100) == False
    
    def test_empty_text(self):
        """Test handling of empty text"""
        clean_text, placeholder_map = self.processor.extract_preservable_elements("")
        
        assert clean_text == ""
        assert placeholder_map == {}
        assert self.processor.get_character_count("") == 0
    
    def test_text_with_no_preservable_elements(self):
        """Test text without hashtags, mentions, or URLs"""
        text = "This is just plain text"
        clean_text, placeholder_map = self.processor.extract_preservable_elements(text)
        
        assert clean_text == text  # Should be unchanged
        assert placeholder_map == {}
    
    def test_special_characters_in_hashtags(self):
        """Test hashtags with underscores and numbers"""
        text = "Tags: #test_tag #tag123 #Tag_With_Underscores"
        clean_text, placeholder_map = self.processor.extract_preservable_elements(text)
        
        assert len([k for k in placeholder_map.keys() if "HASHTAG_" in k]) == 3
        assert "#test_tag" in placeholder_map.values()
        assert "#tag123" in placeholder_map.values()
        assert "#Tag_With_Underscores" in placeholder_map.values()
    
    def test_complex_urls(self):
        """Test complex URLs with parameters"""
        text = "Link: https://example.com/path?param=value&other=123"
        clean_text, placeholder_map = self.processor.extract_preservable_elements(text)
        
        assert len([k for k in placeholder_map.keys() if "URL_" in k]) == 1
        assert "https://example.com/path?param=value&other=123" in placeholder_map.values()
        
        # Character count should still be 23 for the URL
        count = self.processor.get_character_count(text)
        expected = len("Link: ") + 23
        assert count == expected