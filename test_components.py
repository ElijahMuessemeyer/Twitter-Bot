#!/usr/bin/env python3
# =============================================================================
# COMPONENT TESTING SCRIPT
# =============================================================================
# Tests individual components without requiring API keys

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all modules can be imported successfully"""
    print("= Testing module imports...")
    
    try:
        from src.utils.text_processor import text_processor
        from src.utils.prompt_builder import prompt_builder
        from src.utils.logger import logger
        from src.models.tweet import Tweet, Translation
        from src.config.settings import settings
        from draft_manager import draft_manager
        print(" All core modules imported successfully")
        return True
    except ImportError as e:
        print(f"L Import error: {str(e)}")
        return False

def test_text_processor():
    """Test text processor functionality"""
    print("\n= Testing text processor...")
    
    try:
        from src.utils.text_processor import text_processor
        
        # Test with sample tweet
        test_text = "Hello @user check out #hashtag and visit https://example.com"
        clean_text, placeholder_map = text_processor.extract_preservable_elements(test_text)
        
        # Verify extraction worked
        assert "{MENTION_0}" in clean_text
        assert "{HASHTAG_0}" in clean_text  
        assert "{URL_0}" in clean_text
        assert "@user" in placeholder_map.values()
        assert "#hashtag" in placeholder_map.values()
        assert "https://example.com" in placeholder_map.values()
        
        # Test restoration
        restored = text_processor.restore_preservable_elements("Translated text with {MENTION_0}", placeholder_map)
        assert "@user" in restored
        
        # Test character counting
        count = text_processor.get_character_count("Test https://example.com")
        assert count == len("Test ") + 23  # URLs count as 23 chars
        
        print(" Text processor working correctly")
        return True
        
    except Exception as e:
        print(f"L Text processor error: {str(e)}")
        return False

def test_prompt_builder():
    """Test prompt builder functionality"""
    print("\n= Testing prompt builder...")
    
    try:
        from src.utils.prompt_builder import prompt_builder
        
        # Test basic prompt building
        prompt = prompt_builder.build_translation_prompt(
            "Hello world",
            "Spanish",
            {"formal_tone": False, "cultural_adaptation": True}
        )
        
        assert "Hello world" in prompt
        assert "Spanish" in prompt
        assert "casual" in prompt.lower() or "informal" in prompt.lower()
        
        # Test shortening prompt
        short_prompt = prompt_builder.build_shortening_prompt(
            "Original text",
            "Very long translated text that exceeds limits",
            "French",
            280
        )
        
        assert "shorter" in short_prompt.lower()
        assert "280" in short_prompt
        
        print(" Prompt builder working correctly")
        return True
        
    except Exception as e:
        print(f"L Prompt builder error: {str(e)}")
        return False

def test_data_models():
    """Test data models"""
    print("\n= Testing data models...")
    
    try:
        from src.models.tweet import Tweet, Translation
        from datetime import datetime
        
        # Test Tweet creation
        tweet = Tweet(
            id="123",
            text="Test tweet",
            created_at=datetime.now(),
            author_username="testuser",
            author_id="456",
            public_metrics={"likes": 0}
        )
        
        assert tweet.id == "123"
        assert tweet.text == "Test tweet"
        
        # Test Translation creation
        translation = Translation(
            original_tweet=tweet,
            target_language="Spanish",
            translated_text="Tweet de prueba", 
            translation_timestamp=datetime.now(),
            character_count=15,
            status="pending"
        )
        
        assert translation.target_language == "Spanish"
        assert translation.original_tweet.id == "123"
        
        print(" Data models working correctly")
        return True
        
    except Exception as e:
        print(f"L Data models error: {str(e)}")
        return False

def test_draft_manager():
    """Test draft manager (without saving files)"""
    print("\n= Testing draft manager...")
    
    try:
        from draft_manager import DraftManager
        import tempfile
        from pathlib import Path
        
        # Create temporary test manager
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            draft_mgr = DraftManager()
            draft_mgr.pending_dir = temp_path / "pending"
            draft_mgr.posted_dir = temp_path / "posted"
            draft_mgr.pending_dir.mkdir(exist_ok=True)
            draft_mgr.posted_dir.mkdir(exist_ok=True)
            
            # Test empty state
            assert draft_mgr.get_draft_count() == 0
            drafts = draft_mgr.get_pending_drafts()
            assert len(drafts) == 0
            
        print(" Draft manager working correctly")
        return True
        
    except Exception as e:
        print(f"L Draft manager error: {str(e)}")
        return False

def test_configuration():
    """Test configuration loading (without API keys)"""
    print("\n= Testing configuration...")
    
    try:
        from src.config.settings import Settings
        
        # Create settings instance (will show warnings about missing keys)
        settings = Settings()
        
        # Test that default values are set
        assert settings.TWITTER_FREE_MONTHLY_LIMIT == 1500
        assert settings.TWITTER_FREE_DAILY_LIMIT == 50
        assert settings.POLL_INTERVAL > 0
        
        # Test credential validation (should fail without real keys)
        # We expect this to fail, so we catch the output
        import io
        from contextlib import redirect_stdout
        
        with redirect_stdout(io.StringIO()):
            validation_result = settings.validate_credentials()
        
        # Should return False since we don't have real API keys
        assert validation_result == False
        
        print(" Configuration system working correctly")
        return True
        
    except Exception as e:
        print(f"L Configuration error: {str(e)}")
        return False

def test_services_without_api_keys():
    """Test that services handle missing API keys gracefully"""
    print("\n= Testing services without API keys...")
    
    try:
        # Test Gemini translator
        from src.services.gemini_translator import GeminiTranslator
        translator = GeminiTranslator()
        assert translator.client_initialized == False  # Should be False without API key
        
        # Test Twitter monitor
        from src.services.twitter_monitor import TwitterMonitor
        monitor = TwitterMonitor()
        assert monitor.api is None  # Should be None without API credentials
        
        # Test publisher
        from src.services.publisher import TwitterPublisher
        publisher = TwitterPublisher()
        # Should initialize but with no language clients
        available_langs = publisher.get_available_languages()
        assert len(available_langs) == 0  # No languages available without credentials
        
        print(" Services handle missing API keys correctly")
        return True
        
    except Exception as e:
        print(f"L Services test error: {str(e)}")
        return False

def main():
    """Run all component tests"""
    print("=== Twitter Translation Bot Component Tests ===\n")
    
    tests = [
        ("Module Imports", test_imports),
        ("Text Processor", test_text_processor), 
        ("Prompt Builder", test_prompt_builder),
        ("Data Models", test_data_models),
        ("Draft Manager", test_draft_manager),
        ("Configuration", test_configuration),
        ("Services (No API Keys)", test_services_without_api_keys)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"L {test_name} failed with exception: {str(e)}")
            results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n=== Test Results: {passed}/{total} passed ===")
    
    if passed == total:
        print("<‰ All component tests passed! The bot core functionality is working.")
        print("\n=Ý Next steps:")
        print("1. Get Twitter API keys from https://developer.twitter.com/")
        print("2. Get Google Gemini API key from https://makersuite.google.com/app/apikey")
        print("3. Copy config/.env.template to .env and fill in your API keys")
        print("4. Run: python main.py test  # to test with real API connections")
    else:
        print("   Some tests failed. Please check the errors above.")
        return False
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)