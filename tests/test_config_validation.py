"""
Tests for the configuration validation system.
Tests all validation schemas, error handling, and integration with settings.
"""

import os
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from pydantic import ValidationError

from src.config.validator import (
    ConfigValidator,
    TwitterCredentials,
    GeminiConfig,
    LanguageConfig,
    AppConfig,
    DatabaseConfig,
    CompleteConfig,
    ValidationResult,
    ValidationLevel,
    validate_configuration,
    validate_and_print,
    quick_validate_credentials
)
from src.config.settings import Settings


class TestTwitterCredentials:
    """Test Twitter credentials validation"""
    
    def test_valid_credentials(self):
        """Test valid Twitter credentials"""
        creds = TwitterCredentials(
            consumer_key="valid_consumer_key_1234567890",
            consumer_secret="valid_consumer_secret_1234567890123456789012345678901234567890",
            access_token="1234567890-valid_access_token_1234567890123456789012345678901234567890",
            access_token_secret="valid_access_token_secret_1234567890123456789012345678901234567890"
        )
        assert creds.consumer_key == "valid_consumer_key_1234567890"
    
    def test_placeholder_values_rejected(self):
        """Test that placeholder values are rejected"""
        with pytest.raises(ValidationError) as excinfo:
            TwitterCredentials(
                consumer_key="your_consumer_key",
                consumer_secret="valid_consumer_secret_1234567890123456789012345678901234567890",
                access_token="1234567890-valid_access_token_1234567890123456789012345678901234567890",
                access_token_secret="valid_access_token_secret_1234567890123456789012345678901234567890"
            )
        assert "appears to be a placeholder value" in str(excinfo.value)
    
    def test_empty_values_rejected(self):
        """Test that empty values are rejected"""
        with pytest.raises(ValidationError):
            TwitterCredentials(
                consumer_key="",
                consumer_secret="valid_consumer_secret_1234567890123456789012345678901234567890",
                access_token="1234567890-valid_access_token_1234567890123456789012345678901234567890",
                access_token_secret="valid_access_token_secret_1234567890123456789012345678901234567890"
            )
    
    def test_short_keys_rejected(self):
        """Test that keys that are too short are rejected"""
        with pytest.raises(ValidationError) as excinfo:
            TwitterCredentials(
                consumer_key="short",
                consumer_secret="valid_consumer_secret_1234567890123456789012345678901234567890",
                access_token="1234567890-valid_access_token_1234567890123456789012345678901234567890",
                access_token_secret="valid_access_token_secret_1234567890123456789012345678901234567890"
            )
        assert "appears to be too short" in str(excinfo.value)


class TestGeminiConfig:
    """Test Gemini API configuration validation"""
    
    def test_valid_gemini_config(self):
        """Test valid Gemini configuration"""
        config = GeminiConfig(
            api_key="AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            model="gemini-2.5-flash-lite"
        )
        assert config.api_key.startswith("AIza")
        assert config.model == "gemini-2.5-flash-lite"
    
    def test_invalid_gemini_key_format(self):
        """Test invalid Gemini API key format"""
        with pytest.raises(ValidationError) as excinfo:
            GeminiConfig(api_key="invalid_key_format")
        assert "should start with 'AIza'" in str(excinfo.value)
    
    def test_placeholder_gemini_key(self):
        """Test placeholder Gemini key rejection"""
        with pytest.raises(ValidationError) as excinfo:
            GeminiConfig(api_key="your_api_key")
        assert "appears to be a placeholder value" in str(excinfo.value)
    
    def test_short_gemini_key(self):
        """Test short Gemini key rejection"""
        with pytest.raises(ValidationError) as excinfo:
            GeminiConfig(api_key="AIza123")
        assert "appears to be too short" in str(excinfo.value)
    
    def test_unknown_model_warning(self, caplog):
        """Test warning for unknown model"""
        config = GeminiConfig(
            api_key="AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            model="unknown-model"
        )
        # Should create config but log warning
        assert config.model == "unknown-model"


class TestLanguageConfig:
    """Test language configuration validation"""
    
    def test_valid_language_config(self):
        """Test valid language configuration"""
        config = LanguageConfig(
            code="ja",
            name="Japanese",
            twitter_username="test_username",
            formal_tone=True,
            cultural_adaptation=True
        )
        assert config.code == "ja"
        assert config.name == "Japanese"
    
    def test_invalid_language_code(self):
        """Test invalid language code format"""
        with pytest.raises(ValidationError) as excinfo:
            LanguageConfig(
                code="invalid_code",
                name="Test Language",
                twitter_username="test_user"
            )
        assert "should be in format 'xx' or 'xx-XX'" in str(excinfo.value)
    
    def test_placeholder_username(self):
        """Test placeholder username rejection"""
        with pytest.raises(ValidationError) as excinfo:
            LanguageConfig(
                code="ja",
                name="Japanese",
                twitter_username="your_username"
            )
        assert "appears to be a placeholder value" in str(excinfo.value)
    
    def test_invalid_twitter_username(self):
        """Test invalid Twitter username format"""
        with pytest.raises(ValidationError) as excinfo:
            LanguageConfig(
                code="ja",
                name="Japanese",
                twitter_username="invalid-username-too-long-and-with-dashes"
            )
        assert "must be 1-15 characters, alphanumeric and underscore only" in str(excinfo.value)
    
    def test_username_with_at_symbol(self):
        """Test username with @ symbol gets cleaned"""
        config = LanguageConfig(
            code="ja",
            name="Japanese",
            twitter_username="@valid_user"
        )
        assert config.twitter_username == "valid_user"


class TestAppConfig:
    """Test application configuration validation"""
    
    def test_valid_app_config(self):
        """Test valid application configuration"""
        config = AppConfig(
            poll_interval=300,
            log_level="INFO",
            twitter_daily_limit=50,
            twitter_monthly_limit=1500,
            async_mode=True
        )
        assert config.poll_interval == 300
        assert config.log_level == "INFO"
    
    def test_invalid_poll_interval(self):
        """Test invalid poll interval"""
        with pytest.raises(ValidationError):
            AppConfig(poll_interval=30)  # Too short
        
        with pytest.raises(ValidationError):
            AppConfig(poll_interval=4000)  # Too long
    
    def test_invalid_log_level(self):
        """Test invalid log level"""
        with pytest.raises(ValidationError) as excinfo:
            AppConfig(log_level="INVALID")
        assert "Log level must be one of" in str(excinfo.value)
    
    def test_log_level_case_conversion(self):
        """Test log level case conversion"""
        config = AppConfig(log_level="debug")
        assert config.log_level == "DEBUG"


class TestDatabaseConfig:
    """Test database configuration validation"""
    
    def test_valid_database_config(self):
        """Test valid database configuration"""
        config = DatabaseConfig(
            url="postgresql://user:pass@localhost:5432/dbname",
            pool_size=5,
            max_overflow=10
        )
        assert config.url.startswith("postgresql://")
    
    def test_invalid_database_url(self):
        """Test invalid database URL"""
        with pytest.raises(ValidationError) as excinfo:
            DatabaseConfig(url="invalid://url")
        assert "must start with postgresql://, sqlite://, or mysql://" in str(excinfo.value)
    
    def test_optional_database_config(self):
        """Test that database config is optional"""
        config = DatabaseConfig()
        assert config.url is None


class TestConfigValidator:
    """Test the main ConfigValidator class"""
    
    def setup_method(self):
        """Set up test environment"""
        self.validator = ConfigValidator()
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch.dict(os.environ, {
        'PRIMARY_TWITTER_CONSUMER_KEY': 'valid_consumer_key_1234567890',
        'PRIMARY_TWITTER_CONSUMER_SECRET': 'valid_consumer_secret_1234567890123456789012345678901234567890',
        'PRIMARY_TWITTER_ACCESS_TOKEN': '1234567890-valid_access_token_1234567890123456789012345678901234567890',
        'PRIMARY_TWITTER_ACCESS_TOKEN_SECRET': 'valid_access_token_secret_1234567890123456789012345678901234567890',
        'GOOGLE_API_KEY': 'AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'GEMINI_MODEL': 'gemini-2.5-flash-lite',
        'POLL_INTERVAL_SECONDS': '300',
        'LOG_LEVEL': 'INFO'
    })
    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"target_languages": []}')
    def test_validation_with_minimal_config(self, mock_file, mock_exists):
        """Test validation with minimal configuration"""
        mock_exists.return_value = True
        
        with patch('os.getcwd', return_value=self.temp_dir):
            results = self.validator.validate_all()
        
        assert results['valid'] == True
        assert len(results['config']['languages']) == 0
    
    @patch.dict(os.environ, {}, clear=True)
    @patch('pathlib.Path.exists')
    def test_validation_with_missing_env_file(self, mock_exists):
        """Test validation when .env file is missing"""
        mock_exists.return_value = False
        
        with patch('os.getcwd', return_value=self.temp_dir):
            results = self.validator.validate_all()
        
        assert results['valid'] == False
        warning_results = [r for r in results['results'] if r.level == ValidationLevel.WARNING]
        assert any("env file not found" in r.message for r in warning_results)
    
    @patch.dict(os.environ, {
        'PRIMARY_TWITTER_CONSUMER_KEY': 'your_consumer_key',
        'GOOGLE_API_KEY': 'your_api_key'
    })
    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"target_languages": []}')
    def test_validation_with_placeholder_values(self, mock_file, mock_exists):
        """Test validation with placeholder values"""
        mock_exists.return_value = True
        
        with patch('os.getcwd', return_value=self.temp_dir):
            results = self.validator.validate_all()
        
        assert results['valid'] == False
        error_results = [r for r in results['results'] if r.level == ValidationLevel.ERROR]
        assert len(error_results) > 0
        assert any("primary_twitter" in r.field for r in error_results)
        assert any("gemini" in r.field for r in error_results)
    
    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='invalid json')
    def test_validation_with_invalid_json(self, mock_file, mock_exists):
        """Test validation with invalid JSON in languages.json"""
        mock_exists.return_value = True
        
        with patch('os.getcwd', return_value=self.temp_dir):
            results = self.validator.validate_all()
        
        assert results['valid'] == False
        error_results = [r for r in results['results'] if r.level == ValidationLevel.ERROR]
        assert any("Invalid JSON" in r.message for r in error_results)
    
    @patch.dict(os.environ, {
        'PRIMARY_TWITTER_CONSUMER_KEY': 'valid_consumer_key_1234567890',
        'PRIMARY_TWITTER_CONSUMER_SECRET': 'valid_consumer_secret_1234567890123456789012345678901234567890',
        'PRIMARY_TWITTER_ACCESS_TOKEN': '1234567890-valid_access_token_1234567890123456789012345678901234567890',
        'PRIMARY_TWITTER_ACCESS_TOKEN_SECRET': 'valid_access_token_secret_1234567890123456789012345678901234567890',
        'GOOGLE_API_KEY': 'AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'JA_TWITTER_CONSUMER_KEY': 'valid_ja_key_1234567890',
        'JA_TWITTER_CONSUMER_SECRET': 'valid_ja_secret_1234567890123456789012345678901234567890',
        'JA_TWITTER_ACCESS_TOKEN': '1234567890-valid_ja_token_1234567890123456789012345678901234567890',
        'JA_TWITTER_ACCESS_TOKEN_SECRET': 'valid_ja_token_secret_1234567890123456789012345678901234567890'
    })
    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"target_languages": [{"code": "ja", "name": "Japanese", "twitter_username": "test_ja", "formal_tone": false, "cultural_adaptation": true}]}')
    def test_validation_with_complete_config(self, mock_file, mock_exists):
        """Test validation with complete configuration"""
        mock_exists.return_value = True
        
        with patch('os.getcwd', return_value=self.temp_dir):
            results = self.validator.validate_all()
        
        assert results['valid'] == True
        assert len(results['config']['languages']) == 1
        assert results['config']['languages'][0]['code'] == 'ja'
        assert 'ja' in results['config']['language_twitter_creds']
    
    def test_cross_validation_duplicate_languages(self):
        """Test cross validation detects duplicate language codes"""
        self.validator.config_data = {
            'languages': [
                {'code': 'ja', 'name': 'Japanese'},
                {'code': 'ja', 'name': 'Japanese Duplicate'}
            ]
        }
        
        self.validator._validate_cross_dependencies()
        
        error_results = [r for r in self.validator.results if r.level == ValidationLevel.ERROR]
        assert any("Duplicate language codes" in r.message for r in error_results)


class TestSettingsIntegration:
    """Test integration with Settings class"""
    
    @patch.dict(os.environ, {
        'PRIMARY_TWITTER_CONSUMER_KEY': 'valid_consumer_key_1234567890',
        'PRIMARY_TWITTER_CONSUMER_SECRET': 'valid_consumer_secret_1234567890123456789012345678901234567890',
        'PRIMARY_TWITTER_ACCESS_TOKEN': '1234567890-valid_access_token_1234567890123456789012345678901234567890',
        'PRIMARY_TWITTER_ACCESS_TOKEN_SECRET': 'valid_access_token_secret_1234567890123456789012345678901234567890',
        'GOOGLE_API_KEY': 'AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
    })
    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"target_languages": []}')
    def test_settings_comprehensive_validation(self, mock_file, mock_exists):
        """Test Settings comprehensive validation"""
        mock_exists.return_value = True
        
        settings = Settings()
        is_valid = settings.validate_configuration_comprehensive()
        
        assert is_valid == True
        assert settings._is_valid == True
        assert settings._validation_results is not None
    
    @patch.dict(os.environ, {'GOOGLE_API_KEY': 'invalid_key'})
    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"target_languages": []}')
    def test_settings_validation_failure(self, mock_file, mock_exists):
        """Test Settings validation failure"""
        mock_exists.return_value = True
        
        settings = Settings()
        is_valid = settings.validate_configuration_comprehensive()
        
        assert is_valid == False
        assert settings._is_valid == False
    
    def test_settings_configuration_summary(self):
        """Test Settings configuration summary"""
        settings = Settings()
        summary = settings.get_configuration_summary()
        
        assert 'primary_twitter_configured' in summary
        assert 'gemini_configured' in summary
        assert 'target_languages_count' in summary
        assert 'validation_status' in summary
    
    @patch('builtins.print')
    def test_settings_print_configuration_status(self, mock_print):
        """Test Settings print configuration status"""
        settings = Settings()
        settings.print_configuration_status()
        
        # Verify print was called
        mock_print.assert_called()
        # Check that configuration status was printed
        printed_text = ''.join([str(call.args[0]) for call in mock_print.call_args_list])
        assert 'CONFIGURATION STATUS' in printed_text


class TestValidationFunctions:
    """Test standalone validation functions"""
    
    @patch('src.config.validator.ConfigValidator')
    def test_validate_configuration_function(self, mock_validator_class):
        """Test validate_configuration function"""
        mock_validator = MagicMock()
        mock_validator.validate_all.return_value = {'valid': True, 'config': {}, 'results': []}
        mock_validator_class.return_value = mock_validator
        
        result = validate_configuration()
        
        assert result['valid'] == True
        mock_validator.validate_all.assert_called_once()
    
    @patch('src.config.validator.ConfigValidator')
    @patch('builtins.print')
    def test_validate_and_print_function(self, mock_print, mock_validator_class):
        """Test validate_and_print function"""
        mock_validator = MagicMock()
        mock_validator.validate_all.return_value = {'valid': True, 'config': {}, 'results': []}
        mock_validator.print_results = MagicMock()
        mock_validator_class.return_value = mock_validator
        
        result = validate_and_print()
        
        assert result == True
        mock_validator.print_results.assert_called_once()
    
    @patch('src.config.validator.ConfigValidator')
    def test_quick_validate_credentials_function(self, mock_validator_class):
        """Test quick_validate_credentials function"""
        mock_validator = MagicMock()
        mock_validator.results = []
        mock_validator._load_environment_config.return_value = {}
        mock_validator._load_language_config.return_value = []
        mock_validator_class.return_value = mock_validator
        
        result = quick_validate_credentials()
        
        assert isinstance(result, bool)


class TestErrorHandling:
    """Test error handling in validation"""
    
    def test_validation_result_creation(self):
        """Test ValidationResult creation"""
        result = ValidationResult(
            level=ValidationLevel.ERROR,
            field="test_field",
            message="Test error message",
            suggestion="Test suggestion"
        )
        
        assert result.level == ValidationLevel.ERROR
        assert result.field == "test_field"
        assert result.message == "Test error message"
        assert result.suggestion == "Test suggestion"
    
    @patch('src.config.validator.logger')
    def test_validation_with_exception(self, mock_logger):
        """Test validation gracefully handles exceptions"""
        validator = ConfigValidator()
        
        with patch.object(validator, '_load_environment_config', side_effect=Exception("Test error")):
            results = validator.validate_all()
        
        assert results['valid'] == False
        assert len(results['results']) > 0
        assert any("Configuration validation failed" in r.message for r in results['results'])


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
