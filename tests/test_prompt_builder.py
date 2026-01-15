# =============================================================================
# PROMPT BUILDER TESTS
# =============================================================================

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils.prompt_builder import PromptBuilder

class TestPromptBuilder:
    def setup_method(self):
        self.builder = PromptBuilder()
    
    def test_basic_translation_prompt(self):
        """Test basic translation prompt generation"""
        prompt = self.builder.build_translation_prompt(
            tweet_text="Hello world",
            target_language="Spanish"
        )
        
        assert "Hello world" in prompt
        assert "Spanish" in prompt
        assert "professional translator" in prompt.lower()
        assert "social media content" in prompt.lower()
    
    def test_translation_prompt_with_placeholders(self):
        """Test translation prompt with preserved element placeholders"""
        prompt = self.builder.build_translation_prompt(
            tweet_text="Check {URL_0} and follow {MENTION_0} for {HASHTAG_0}",
            target_language="French"
        )
        
        assert "{URL_0}" in prompt
        assert "{MENTION_0}" in prompt  
        assert "{HASHTAG_0}" in prompt
        assert "French" in prompt
        assert "preserve" in prompt.lower()
    
    def test_translation_prompt_with_language_config_informal(self):
        """Test prompt with informal tone configuration"""
        language_config = {
            "formal_tone": False,
            "cultural_adaptation": True
        }
        
        prompt = self.builder.build_translation_prompt(
            tweet_text="What's up everyone!",
            target_language="German",
            language_config=language_config
        )
        
        assert "casual/informal tone" in prompt
        assert "cultural references" in prompt
        assert "German" in prompt
    
    def test_translation_prompt_with_language_config_formal(self):
        """Test prompt with formal tone configuration"""
        language_config = {
            "formal_tone": True,
            "cultural_adaptation": False
        }
        
        prompt = self.builder.build_translation_prompt(
            tweet_text="Good morning colleagues",
            target_language="Japanese",
            language_config=language_config
        )
        
        assert "polite/formal tone" in prompt
        assert "Japanese" in prompt
        # The base template always contains cultural adaptation instruction
        # When cultural_adaptation is False, no additional instruction should be added
        # Check that no additional cultural adaptation instruction was added
        additional_cultural_instruction = "adapt cultural references for japanese speakers when possible" in prompt.lower()
        assert not additional_cultural_instruction
    
    def test_translation_prompt_requirements(self):
        """Test that prompt contains all required elements"""
        prompt = self.builder.build_translation_prompt(
            tweet_text="Test tweet",
            target_language="Italian"
        )
        
        # Check for key requirements
        assert "maintain" in prompt.lower() and "tone" in prompt.lower()
        assert "hashtags" in prompt.lower()
        assert "@mentions" in prompt.lower() or "mentions" in prompt.lower()
        assert "urls" in prompt.lower()
        assert "character count" in prompt.lower()
        assert "concise" in prompt.lower()
        assert "twitter" in prompt.lower()
    
    def test_shortening_prompt_basic(self):
        """Test basic shortening prompt generation"""
        prompt = self.builder.build_shortening_prompt(
            original_text="This is the original English text",
            current_translation="Esta es la traducción actual en español que es demasiado larga",
            target_language="Spanish",
            char_limit=50
        )
        
        assert "too long" in prompt.lower()
        assert "shorter version" in prompt.lower()
        assert "This is the original English text" in prompt
        assert "Esta es la traducción actual en español que es demasiado larga" in prompt
        assert "Spanish" in prompt
        assert "50" in prompt
    
    def test_shortening_prompt_custom_limit(self):
        """Test shortening prompt with custom character limit"""
        prompt = self.builder.build_shortening_prompt(
            original_text="Short text",
            current_translation="Texto muy largo en español",
            target_language="Spanish",
            char_limit=100
        )
        
        assert "100 characters" in prompt
        assert "character limit" in prompt.lower()
    
    def test_shortening_prompt_maintains_meaning(self):
        """Test shortening prompt emphasizes maintaining meaning"""
        prompt = self.builder.build_shortening_prompt(
            original_text="Important message",
            current_translation="Mensaje muy importante y detallado",
            target_language="Spanish"
        )
        
        assert "core meaning" in prompt.lower() or "main meaning" in prompt.lower()
        assert "tone" in prompt.lower()
    
    def test_empty_tweet_text(self):
        """Test handling of empty tweet text"""
        prompt = self.builder.build_translation_prompt(
            tweet_text="",
            target_language="French"
        )
        
        assert "French" in prompt
        assert '""' in prompt  # Empty string should be in quotes
    
    def test_special_characters_in_tweet(self):
        """Test handling of special characters in tweet text"""
        tweet_with_specials = "Hello! @user #tag https://test.com 😀 & < > \""
        prompt = self.builder.build_translation_prompt(
            tweet_text=tweet_with_specials,
            target_language="German"
        )
        
        # All special characters should be preserved in the prompt
        assert "Hello!" in prompt
        assert "@user" in prompt
        assert "#tag" in prompt  
        assert "https://test.com" in prompt
        assert "😀" in prompt
        assert "&" in prompt
    
    def test_multiple_language_configs(self):
        """Test different language configuration combinations"""
        configs = [
            {"formal_tone": True, "cultural_adaptation": True},
            {"formal_tone": False, "cultural_adaptation": True},
            {"formal_tone": True, "cultural_adaptation": False},
            {"formal_tone": False, "cultural_adaptation": False},
        ]
        
        for config in configs:
            prompt = self.builder.build_translation_prompt(
                tweet_text="Test message",
                target_language="Portuguese",
                language_config=config
            )
            
            # Should always contain the basic prompt elements
            assert "Test message" in prompt
            assert "Portuguese" in prompt
            
            # Check tone instruction
            if config["formal_tone"]:
                assert "formal" in prompt.lower()
            else:
                assert "casual" in prompt.lower() or "informal" in prompt.lower()
    
    def test_long_tweet_text(self):
        """Test handling of long tweet text"""
        long_text = "This is a very long tweet that contains many words and goes on and on " * 5
        prompt = self.builder.build_translation_prompt(
            tweet_text=long_text,
            target_language="Russian"
        )
        
        assert long_text in prompt
        assert "Russian" in prompt
        assert len(prompt) > len(long_text)  # Prompt should be longer than just the text
    
    def test_prompt_template_consistency(self):
        """Test that prompts are generated consistently"""
        tweet_text = "Consistent test"
        target_lang = "Korean"
        
        prompt1 = self.builder.build_translation_prompt(tweet_text, target_lang)
        prompt2 = self.builder.build_translation_prompt(tweet_text, target_lang)
        
        assert prompt1 == prompt2  # Should be identical for same inputs