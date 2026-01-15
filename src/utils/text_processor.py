# =============================================================================
# TEXT PROCESSING UTILITIES
# =============================================================================
# Handles hashtags, mentions, URLs, and character counting for tweets

import re
from typing import List, Tuple

class TextProcessor:
    def __init__(self):
        # Regex patterns for preserving elements
        self.hashtag_pattern = re.compile(r'#\w+')
        self.mention_pattern = re.compile(r'@\w+')
        self.url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    
    def extract_preservable_elements(self, text: str) -> Tuple[str, dict]:
        """Extract hashtags, mentions, and URLs for preservation during translation"""
        elements = {
            'hashtags': self.hashtag_pattern.findall(text),
            'mentions': self.mention_pattern.findall(text),
            'urls': self.url_pattern.findall(text)
        }
        
        # Create clean text for translation (replace preservable elements with placeholders)
        clean_text = text
        placeholder_map = {}
        
        # Replace URLs with placeholders
        for i, url in enumerate(elements['urls']):
            placeholder = f"{{URL_{i}}}"
            clean_text = clean_text.replace(url, placeholder)
            placeholder_map[placeholder] = url
        
        # Replace mentions with placeholders
        for i, mention in enumerate(elements['mentions']):
            placeholder = f"{{MENTION_{i}}}"
            clean_text = clean_text.replace(mention, placeholder)
            placeholder_map[placeholder] = mention
        
        # Replace hashtags with placeholders
        for i, hashtag in enumerate(elements['hashtags']):
            placeholder = f"{{HASHTAG_{i}}}"
            clean_text = clean_text.replace(hashtag, placeholder)
            placeholder_map[placeholder] = hashtag
        
        return clean_text, placeholder_map
    
    def restore_preservable_elements(self, translated_text: str, placeholder_map: dict) -> str:
        """Restore hashtags, mentions, and URLs in translated text"""
        restored_text = translated_text
        
        for placeholder, original in placeholder_map.items():
            restored_text = restored_text.replace(placeholder, original)
        
        return restored_text
    
    def get_character_count(self, text: str) -> int:
        """Get character count considering Twitter's counting rules"""
        # Twitter counts URLs as 23 characters regardless of actual length
        url_count = len(self.url_pattern.findall(text))
        text_without_urls = self.url_pattern.sub('', text)
        
        return len(text_without_urls) + (url_count * 23)
    
    def is_within_twitter_limit(self, text: str, limit: int = 280) -> bool:
        """Check if text is within Twitter character limit"""
        return self.get_character_count(text) <= limit

# Global text processor instance
text_processor = TextProcessor()