# =============================================================================
# SETTINGS AND CONFIGURATION TESTS
# =============================================================================

import pytest
import sys
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config.settings import Settings

class TestSettings:
    def setup_method(self):
        """Set up test fixtures"""
        # Create temporary config file for testing
        self.test_config_dir = Path(tempfile.mkdtemp())
        self.test_languages_file = self.test_config_dir / "languages.json"
        
        # Sample language configuration
        self.sample_lang_config = {
            "target_languages": [
                {
                    "code": "es",
                    "name": "Spanish",
                    "twitter_username": "spanish_account",
                    "formal_tone": False,
                    "cultural_adaptation": True
                },
                {
                    "code": "fr", 
                    "name": "French",
                    "twitter_username": "french_account",
                    "formal_tone": True,
                    "cultural_adaptation": False
                }
            ]
        }
        
        # Write test config file
        with open(self.test_languages_file, 'w') as f:
            json.dump(self.sample_lang_config, f)
    
    def teardown_method(self):
        """Clean up test files"""
        if self.test_config_dir.exists():
            import shutil
            shutil.rmtree(self.test_config_dir)
    
    @patch.dict(os.environ, {
        'PRIMARY_TWITTER_CONSUMER_KEY': 'test_consumer_key',
        'PRIMARY_TWITTER_CONSUMER_SECRET': 'test_consumer_secret',
        'PRIMARY_TWITTER_ACCESS_TOKEN': 'test_access_token',
        'PRIMARY_TWITTER_ACCESS_TOKEN_SECRET': 'test_access_token_secret',
        'PRIMARY_TWITTER_USERNAME': 'test_user',
        'GOOGLE_API_KEY': 'test_google_api_key',
        'GEMINI_MODEL': 'gemini-2.5-flash-lite',
        'POLL_INTERVAL_SECONDS': '300',
        'LOG_LEVEL': 'INFO'
    })
    @patch('src.config.settings.Path')
    def test_settings_initialization_with_env_vars(self, mock_path):
        """Test settings initialization with environment variables"""
        # Mock the config file path
        mock_path.return_value.exists.return_value = True
        
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(self.sample_lang_config)
            
            settings = Settings()
            
            assert settings.PRIMARY_TWITTER_CREDS['consumer_key'] == 'test_consumer_key'
            assert settings.PRIMARY_TWITTER_CREDS['consumer_secret'] == 'test_consumer_secret'
            assert settings.PRIMARY_USERNAME == 'test_user'
            assert settings.GOOGLE_API_KEY == 'test_google_api_key'
            assert settings.GEMINI_MODEL == 'gemini-2.5-flash-lite'
            assert settings.POLL_INTERVAL == 300
            assert settings.LOG_LEVEL == 'INFO'
    
    def test_settings_default_values(self):
        """Test settings with default values when env vars not set"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('src.config.settings.Path') as mock_path:
                mock_path.return_value.exists.return_value = False
                
                settings = Settings()
                
                assert settings.GEMINI_MODEL == 'gemini-2.5-flash-lite'  # Default value
                assert settings.POLL_INTERVAL == 300  # Default value
                assert settings.LOG_LEVEL == 'INFO'  # Default value
                assert settings.TARGET_LANGUAGES == []  # No config file
    
    def test_load_language_config_success(self):
        """Test successful loading of language configuration"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = True
            
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = MagicMock()
                
                with patch('json.load') as mock_json:
                    mock_json.return_value = self.sample_lang_config
                    
                    settings = Settings()
                    
                    assert len(settings.TARGET_LANGUAGES) == 2
                    assert settings.TARGET_LANGUAGES[0]['code'] == 'es'
                    assert settings.TARGET_LANGUAGES[1]['code'] == 'fr'
    
    def test_load_language_config_file_not_found(self):
        """Test language config loading when file doesn't exist"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = False
            
            settings = Settings()
            
            assert settings.TARGET_LANGUAGES == []
    
    @patch.dict(os.environ, {
        'ES_TWITTER_CONSUMER_KEY': 'es_consumer_key',
        'ES_TWITTER_CONSUMER_SECRET': 'es_consumer_secret',
        'ES_TWITTER_ACCESS_TOKEN': 'es_access_token',
        'ES_TWITTER_ACCESS_TOKEN_SECRET': 'es_access_token_secret',
    })
    def test_get_twitter_creds_for_language(self):
        """Test getting Twitter credentials for specific language"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = False
            
            settings = Settings()
            
            creds = settings.get_twitter_creds_for_language('es')
            
            assert creds['consumer_key'] == 'es_consumer_key'
            assert creds['consumer_secret'] == 'es_consumer_secret'
            assert creds['access_token'] == 'es_access_token'
            assert creds['access_token_secret'] == 'es_access_token_secret'
    
    def test_get_twitter_creds_for_language_missing(self):
        """Test getting credentials for language with missing env vars"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('src.config.settings.Path') as mock_path:
                mock_path.return_value.exists.return_value = False
                
                settings = Settings()
                
                creds = settings.get_twitter_creds_for_language('de')
                
                assert creds['consumer_key'] is None
                assert creds['consumer_secret'] is None
                assert creds['access_token'] is None
                assert creds['access_token_secret'] is None
    
    @patch.dict(os.environ, {
        'PRIMARY_TWITTER_CONSUMER_KEY': 'valid_key',
        'PRIMARY_TWITTER_CONSUMER_SECRET': 'valid_secret',
        'PRIMARY_TWITTER_ACCESS_TOKEN': 'valid_token',
        'PRIMARY_TWITTER_ACCESS_TOKEN_SECRET': 'valid_token_secret',
        'GOOGLE_API_KEY': 'valid_google_key'
    })
    def test_validate_credentials_success(self):
        """Test credential validation with valid credentials"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = False
            
            settings = Settings()
            
            with patch('builtins.print'):  # Suppress print output
                result = settings.validate_credentials()
            
            assert result == True
    
    @patch.dict(os.environ, {
        'PRIMARY_TWITTER_CONSUMER_KEY': 'your_consumer_key_here',  # Invalid placeholder
        'GOOGLE_API_KEY': 'your_google_api_key_here'  # Invalid placeholder
    })
    def test_validate_credentials_with_placeholders(self):
        """Test credential validation with placeholder values"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = False
            
            settings = Settings()
            
            with patch('builtins.print'):  # Suppress print output
                result = settings.validate_credentials()
            
            assert result == False
    
    @patch.dict(os.environ, {}, clear=True)
    def test_validate_credentials_missing_all(self):
        """Test credential validation with missing credentials"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = False
            
            settings = Settings()
            
            with patch('builtins.print'):  # Suppress print output
                result = settings.validate_credentials()
            
            assert result == False
    
    def test_api_limits_constants(self):
        """Test API limit constants are set correctly"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = False
            
            settings = Settings()
            
            assert settings.TWITTER_FREE_MONTHLY_LIMIT == 1500
            assert settings.TWITTER_FREE_DAILY_LIMIT == 50
    
    @patch.dict(os.environ, {
        'POLL_INTERVAL_SECONDS': '600',
        'LOG_LEVEL': 'DEBUG'
    })
    def test_custom_app_settings(self):
        """Test custom application settings"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = False
            
            settings = Settings()
            
            assert settings.POLL_INTERVAL == 600
            assert settings.LOG_LEVEL == 'DEBUG'
    
    @patch.dict(os.environ, {
        'POLL_INTERVAL_SECONDS': 'invalid_number'
    })
    def test_invalid_poll_interval(self):
        """Test handling of invalid poll interval"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = False
            
            # Should raise ValueError when trying to convert invalid string to int
            with pytest.raises(ValueError):
                Settings()
    
    def test_language_config_with_invalid_json(self):
        """Test handling of invalid JSON in language config"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = True
            
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = MagicMock()
                
                with patch('json.load') as mock_json:
                    mock_json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
                    
                    # Should handle JSON decode error gracefully
                    settings = Settings()
                    assert settings.TARGET_LANGUAGES == []
    
    def test_case_insensitive_language_codes(self):
        """Test that language code handling works with different cases"""
        with patch('src.config.settings.Path') as mock_path:
            mock_path.return_value.exists.return_value = False
            
            settings = Settings()
            
            # Test with lowercase
            with patch.dict(os.environ, {'ES_TWITTER_CONSUMER_KEY': 'test_key'}):
                creds_lower = settings.get_twitter_creds_for_language('es')
                creds_upper = settings.get_twitter_creds_for_language('ES')
                
                # Both should work (function converts to uppercase internally)
                assert creds_lower['consumer_key'] == 'test_key'
                assert creds_upper['consumer_key'] == 'test_key'