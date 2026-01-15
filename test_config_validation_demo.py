#!/usr/bin/env python3
"""
Demo script showing the configuration validation system in action.
This demonstrates what happens with both valid and invalid configurations.
"""

import os
import tempfile
import json
from pathlib import Path
from src.config.validator import (
    ConfigValidator, 
    TwitterCredentials, 
    GeminiConfig, 
    LanguageConfig,
    validate_and_print
)

def demo_individual_schema_validation():
    """Demo individual schema validation"""
    print("🧪 SCHEMA VALIDATION DEMO")
    print("=" * 50)
    
    # Test 1: Valid Twitter credentials
    print("\n1. Valid Twitter Credentials:")
    try:
        creds = TwitterCredentials(
            consumer_key="valid_consumer_key_1234567890",
            consumer_secret="valid_consumer_secret_1234567890123456789012345678901234567890",
            access_token="1234567890-valid_access_token_1234567890123456789012345678901234567890",
            access_token_secret="valid_access_token_secret_1234567890123456789012345678901234567890"
        )
        print("   ✅ Valid Twitter credentials accepted")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Invalid Twitter credentials (placeholder)
    print("\n2. Invalid Twitter Credentials (placeholder):")
    try:
        creds = TwitterCredentials(
            consumer_key="your_consumer_key",
            consumer_secret="your_consumer_secret", 
            access_token="your_access_token",
            access_token_secret="your_access_token_secret"
        )
        print("   ❌ Should have failed but didn't!")
    except Exception as e:
        print(f"   ✅ Correctly rejected: {str(e)[:60]}...")
    
    # Test 3: Valid Gemini config
    print("\n3. Valid Gemini Configuration:")
    try:
        gemini = GeminiConfig(
            api_key="AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            model="gemini-2.5-flash-lite"
        )
        print("   ✅ Valid Gemini config accepted")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 4: Invalid Gemini API key
    print("\n4. Invalid Gemini API Key:")
    try:
        gemini = GeminiConfig(api_key="invalid_api_key")
        print("   ❌ Should have failed but didn't!")
    except Exception as e:
        print(f"   ✅ Correctly rejected: {str(e)[:60]}...")
    
    # Test 5: Valid Language Config
    print("\n5. Valid Language Configuration:")
    try:
        lang = LanguageConfig(
            code="ja",
            name="Japanese",
            twitter_username="test_jp_bot",
            formal_tone=True,
            cultural_adaptation=True
        )
        print("   ✅ Valid language config accepted")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 6: Invalid Language Code
    print("\n6. Invalid Language Code:")
    try:
        lang = LanguageConfig(
            code="invalid_language_code",
            name="Invalid Language",
            twitter_username="test_bot"
        )
        print("   ❌ Should have failed but didn't!")
    except Exception as e:
        print(f"   ✅ Correctly rejected: {str(e)[:60]}...")

def demo_comprehensive_validation_mock():
    """Demo comprehensive validation with mocked environment"""
    print("\n\n🔍 COMPREHENSIVE VALIDATION DEMO")
    print("=" * 50)
    
    # Create temporary directories and files for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        os.chdir(temp_dir)
        
        # Create config directory and languages.json
        config_dir = Path("config")
        config_dir.mkdir()
        
        # Test Case 1: Complete valid configuration
        print("\n1. Testing Complete Valid Configuration:")
        
        # Mock environment variables for valid config
        valid_env = {
            'PRIMARY_TWITTER_CONSUMER_KEY': 'valid_consumer_key_1234567890',
            'PRIMARY_TWITTER_CONSUMER_SECRET': 'valid_consumer_secret_1234567890123456789012345678901234567890',
            'PRIMARY_TWITTER_ACCESS_TOKEN': '1234567890-valid_access_token_1234567890123456789012345678901234567890',
            'PRIMARY_TWITTER_ACCESS_TOKEN_SECRET': 'valid_access_token_secret_1234567890123456789012345678901234567890',
            'GOOGLE_API_KEY': 'AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
            'GEMINI_MODEL': 'gemini-2.5-flash-lite',
            'POLL_INTERVAL_SECONDS': '300',
            'LOG_LEVEL': 'INFO',
            'JA_TWITTER_CONSUMER_KEY': 'valid_ja_consumer_key_1234567890',
            'JA_TWITTER_CONSUMER_SECRET': 'valid_ja_consumer_secret_1234567890123456789012345678901234567890',
            'JA_TWITTER_ACCESS_TOKEN': '1234567890-valid_ja_access_token_1234567890123456789012345678901234567890',
            'JA_TWITTER_ACCESS_TOKEN_SECRET': 'valid_ja_access_token_secret_1234567890123456789012345678901234567890',
        }
        
        languages_config = {
            "target_languages": [
                {
                    "code": "ja",
                    "name": "Japanese",
                    "twitter_username": "test_jp_bot",
                    "formal_tone": True,
                    "cultural_adaptation": True
                }
            ]
        }
        
        # Write languages.json
        with open(config_dir / "languages.json", "w") as f:
            json.dump(languages_config, f, indent=2)
        
        # Test with valid configuration
        original_env = os.environ.copy()
        try:
            os.environ.update(valid_env)
            validator = ConfigValidator()
            results = validator.validate_all()
            
            if results['valid']:
                print("   ✅ All validation checks passed!")
                print(f"   📊 Languages configured: {len(results['config']['languages'])}")
                print(f"   🔧 App config valid: {results['config']['app'] is not None}")
            else:
                print("   ❌ Validation failed:")
                for result in results['results']:
                    print(f"      • {result.field}: {result.message}")
        
        finally:
            os.environ.clear()
            os.environ.update(original_env)
        
        # Test Case 2: Missing credentials
        print("\n2. Testing Missing Credentials:")
        
        invalid_env = {
            'GOOGLE_API_KEY': 'invalid_key',  # Invalid format
            'POLL_INTERVAL_SECONDS': '300'
        }
        
        try:
            os.environ.update(invalid_env)
            validator = ConfigValidator()
            results = validator.validate_all()
            
            if not results['valid']:
                error_count = len([r for r in results['results'] if r.level.name == 'ERROR'])
                print(f"   ✅ Correctly detected {error_count} configuration errors")
                
                # Show a few example errors
                for result in results['results'][:3]:  # Show first 3 errors
                    print(f"      • {result.field}: {result.message[:50]}...")
            else:
                print("   ❌ Should have failed validation")
        
        finally:
            os.environ.clear()
            os.environ.update(original_env)

def demo_validation_output():
    """Demo the validation output formatting"""
    print("\n\n📋 VALIDATION OUTPUT DEMO")
    print("=" * 50)
    
    print("\n✨ This is what users see when running validation:")
    print("\n$ python main.py validate")
    print("🔍 Running comprehensive configuration validation...")
    print()
    print("❌ CONFIGURATION ERRORS:")
    print("   • primary_twitter: Invalid primary Twitter credentials")
    print("     💡 Get Twitter API keys from https://developer.twitter.com/ and add them to .env")
    print("   • gemini: Invalid Gemini configuration")
    print("     💡 Get Google Gemini API key from https://makersuite.google.com/app/apikey")
    print()
    print("⚠️ CONFIGURATION WARNINGS:")
    print("   • env_file: .env file not found")
    print("     💡 Copy config/.env.template to .env and fill in your API keys")
    print()
    print("❌ Configuration validation failed with 2 error(s)")
    print("🔧 Please fix the errors above before running the bot.")

if __name__ == "__main__":
    print("🚀 TWITTER BOT CONFIGURATION VALIDATION DEMO")
    print("=" * 60)
    
    demo_individual_schema_validation()
    demo_comprehensive_validation_mock()
    demo_validation_output()
    
    print("\n\n✅ DEMO COMPLETE!")
    print("=" * 60)
    print("📚 Features Demonstrated:")
    print("• Pydantic schema validation for all configuration types")
    print("• Comprehensive environment and file validation")
    print("• User-friendly error messages with suggestions")
    print("• Integration with main.py startup process")
    print("• Command-line validation tools (validate, config)")
    print("• Graceful fallback to legacy validation if needed")
    print("\n🛠️ Ready for production use!")
