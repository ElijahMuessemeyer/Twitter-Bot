"""
Configuration validation system for Twitter Translation Bot.
Validates all environment variables, API credentials, language configurations, and settings.
"""

import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator
from enum import Enum
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class ValidationLevel(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

@dataclass
class ValidationResult:
    level: ValidationLevel
    field: str
    message: str
    suggestion: Optional[str] = None

class ValidationError(Exception):
    def __init__(self, message: str, results: List[ValidationResult]):
        super().__init__(message)
        self.results = results

# =============================================================================
# PYDANTIC SCHEMAS FOR CONFIGURATION VALIDATION
# =============================================================================

class TwitterCredentials(BaseModel):
    """Schema for Twitter API credentials"""
    consumer_key: str = Field(..., min_length=1, description="Twitter consumer key")
    consumer_secret: str = Field(..., min_length=1, description="Twitter consumer secret")
    access_token: str = Field(..., min_length=1, description="Twitter access token")
    access_token_secret: str = Field(..., min_length=1, description="Twitter access token secret")
    
    @field_validator('consumer_key', 'consumer_secret', 'access_token', 'access_token_secret')
    @classmethod
    def validate_not_placeholder(cls, v, info):
        field_name = info.field_name
        if v.startswith('your_') or v in ['', 'REPLACE_WITH_YOUR_KEY']:
            raise ValueError(f"{field_name} appears to be a placeholder value")
        return v
    
    @field_validator('consumer_key', 'consumer_secret')
    @classmethod
    def validate_consumer_format(cls, v, info):
        field_name = info.field_name
        # Twitter consumer keys are typically 25 characters, consumer secrets are 50
        expected_len = 25 if 'key' in field_name else 50
        if len(v) < expected_len - 5:  # Allow some flexibility
            raise ValueError(f"{field_name} appears to be too short (expected ~{expected_len} characters)")
        return v
    
    @field_validator('access_token', 'access_token_secret')
    @classmethod
    def validate_access_format(cls, v, info):
        field_name = info.field_name
        # Access tokens are typically 50+ characters
        if len(v) < 40:
            raise ValueError(f"{field_name} appears to be too short (expected 40+ characters)")
        return v

class GeminiConfig(BaseModel):
    """Schema for Google Gemini API configuration"""
    api_key: str = Field(..., min_length=1, description="Google Gemini API key")
    model: str = Field(default="gemini-2.5-flash-lite", description="Gemini model to use")
    
    @field_validator('api_key')
    @classmethod
    def validate_gemini_key(cls, v):
        if v.startswith('your_') or v in ['', 'REPLACE_WITH_YOUR_KEY']:
            raise ValueError("API key appears to be a placeholder value")
        if not v.startswith('AIza'):
            raise ValueError("Gemini API key should start with 'AIza'")
        if len(v) < 30:
            raise ValueError("Gemini API key appears to be too short")
        return v
    
    @field_validator('model')
    @classmethod
    def validate_model_name(cls, v):
        valid_models = [
            'gemini-2.5-flash-lite', 'gemini-1.5-pro', 'gemini-1.5-flash',
            'gemini-pro', 'gemini-1.0-pro'
        ]
        if v not in valid_models:
            logger.warning(f"Model '{v}' not in known valid models: {valid_models}")
        return v

class LanguageConfig(BaseModel):
    """Schema for language configuration"""
    code: str = Field(..., min_length=2, max_length=5, description="Language code (e.g., 'ja', 'de')")
    name: str = Field(..., min_length=1, description="Language name (e.g., 'Japanese')")
    twitter_username: str = Field(..., min_length=1, description="Twitter username for this language")
    formal_tone: bool = Field(default=False, description="Use formal tone for translations")
    cultural_adaptation: bool = Field(default=True, description="Apply cultural adaptations")
    
    @field_validator('code')
    @classmethod
    def validate_language_code(cls, v):
        # Basic language code validation (ISO 639-1 or similar)
        if not re.match(r'^[a-z]{2}(-[A-Z]{2})?$', v):
            raise ValueError(f"Language code '{v}' should be in format 'xx' or 'xx-XX' (e.g., 'en', 'zh-CN')")
        return v
    
    @field_validator('twitter_username')
    @classmethod
    def validate_username(cls, v):
        if v.startswith('your_') or v in ['', 'REPLACE_WITH_USERNAME']:
            raise ValueError("Twitter username appears to be a placeholder value")
        if v.startswith('@'):
            v = v[1:]  # Remove @ if present
        if not re.match(r'^[A-Za-z0-9_]{1,15}$', v):
            raise ValueError("Twitter username must be 1-15 characters, alphanumeric and underscore only")
        return v

class AppConfig(BaseModel):
    """Schema for application settings"""
    poll_interval: int = Field(default=300, ge=60, le=3600, description="Polling interval in seconds")
    log_level: str = Field(default="INFO", description="Logging level")
    twitter_daily_limit: int = Field(default=50, ge=1, description="Daily Twitter API limit")
    twitter_monthly_limit: int = Field(default=1500, ge=1, description="Monthly Twitter API limit")
    async_mode: bool = Field(default=False, description="Enable async mode")
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()

class DatabaseConfig(BaseModel):
    """Schema for database configuration (optional)"""
    url: Optional[str] = Field(None, description="Database URL")
    pool_size: int = Field(default=5, ge=1, le=20, description="Connection pool size")
    max_overflow: int = Field(default=10, ge=0, le=50, description="Max pool overflow")
    
    @field_validator('url')
    @classmethod
    def validate_db_url(cls, v):
        if v and not v.startswith(('postgresql://', 'sqlite://', 'mysql://')):
            raise ValueError("Database URL must start with postgresql://, sqlite://, or mysql://")
        return v

class CompleteConfig(BaseModel):
    """Complete configuration schema"""
    primary_twitter: TwitterCredentials
    gemini: GeminiConfig
    languages: List[LanguageConfig]
    language_twitter_creds: Dict[str, TwitterCredentials]
    app: AppConfig
    database: Optional[DatabaseConfig] = None

# =============================================================================
# CONFIGURATION VALIDATOR CLASS
# =============================================================================

class ConfigValidator:
    """Comprehensive configuration validator for Twitter Translation Bot"""
    
    def __init__(self):
        self.results: List[ValidationResult] = []
        self.config_data = {}
        
    def validate_all(self) -> Dict[str, Any]:
        """Validate all configuration and return results"""
        self.results = []
        
        try:
            # Load environment variables
            env_config = self._load_environment_config()
            
            # Load language configuration
            lang_config = self._load_language_config()
            
            # Validate primary Twitter credentials
            primary_twitter = self._validate_primary_twitter(env_config)
            
            # Validate Gemini configuration
            gemini = self._validate_gemini(env_config)
            
            # Validate language-specific Twitter credentials
            lang_creds = self._validate_language_credentials(env_config, lang_config)
            
            # Validate application settings
            app_config = self._validate_app_config(env_config)
            
            # Validate database config (optional)
            db_config = self._validate_database_config(env_config)
            
            # Create complete config model
            complete_config = CompleteConfig(
                primary_twitter=primary_twitter,
                gemini=gemini,
                languages=lang_config,
                language_twitter_creds=lang_creds,
                app=app_config,
                database=db_config
            )
            
            self.config_data = complete_config.dict()
            
            # Additional cross-validation checks
            self._validate_cross_dependencies()
            
            return {
                'valid': len([r for r in self.results if r.level == ValidationLevel.ERROR]) == 0,
                'config': self.config_data,
                'results': self.results
            }
            
        except Exception as e:
            self.results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                field="general",
                message=f"Configuration validation failed: {str(e)}"
            ))
            return {
                'valid': False,
                'config': {},
                'results': self.results
            }
    
    def _load_environment_config(self) -> Dict[str, str]:
        """Load and validate environment variables"""
        env_vars = dict(os.environ)
        
        # Check if .env file exists
        env_file = Path('.env')
        if not env_file.exists():
            self.results.append(ValidationResult(
                level=ValidationLevel.WARNING,
                field="env_file",
                message=".env file not found",
                suggestion="Copy config/.env.template to .env and fill in your API keys"
            ))
        
        return env_vars
    
    def _load_language_config(self) -> List[LanguageConfig]:
        """Load and validate language configuration"""
        config_path = Path('config/languages.json')
        
        if not config_path.exists():
            self.results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                field="languages_file",
                message="config/languages.json not found",
                suggestion="Create config/languages.json with your target language configurations"
            ))
            return []
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'target_languages' not in data:
                raise ValueError("Missing 'target_languages' key in config/languages.json")
            
            languages = []
            for lang_data in data['target_languages']:
                try:
                    lang_config = LanguageConfig(**lang_data)
                    languages.append(lang_config)
                except Exception as e:
                    self.results.append(ValidationResult(
                        level=ValidationLevel.ERROR,
                        field=f"language_{lang_data.get('code', 'unknown')}",
                        message=f"Invalid language configuration: {str(e)}",
                        suggestion="Check the language configuration format in config/languages.json"
                    ))
            
            return languages
            
        except json.JSONDecodeError as e:
            self.results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                field="languages_file",
                message=f"Invalid JSON in config/languages.json: {str(e)}",
                suggestion="Fix JSON syntax errors in config/languages.json"
            ))
            return []
        except Exception as e:
            self.results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                field="languages_file",
                message=f"Error loading config/languages.json: {str(e)}"
            ))
            return []
    
    def _validate_primary_twitter(self, env_config: Dict[str, str]) -> TwitterCredentials:
        """Validate primary Twitter credentials"""
        creds = {
            'consumer_key': env_config.get('PRIMARY_TWITTER_CONSUMER_KEY', ''),
            'consumer_secret': env_config.get('PRIMARY_TWITTER_CONSUMER_SECRET', ''),
            'access_token': env_config.get('PRIMARY_TWITTER_ACCESS_TOKEN', ''),
            'access_token_secret': env_config.get('PRIMARY_TWITTER_ACCESS_TOKEN_SECRET', '')
        }
        
        try:
            return TwitterCredentials(**creds)
        except Exception as e:
            self.results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                field="primary_twitter",
                message=f"Invalid primary Twitter credentials: {str(e)}",
                suggestion="Get Twitter API keys from https://developer.twitter.com/ and add them to .env"
            ))
            # Return a dummy object to continue validation
            return TwitterCredentials(
                consumer_key="invalid", consumer_secret="invalid",
                access_token="invalid", access_token_secret="invalid"
            )
    
    def _validate_gemini(self, env_config: Dict[str, str]) -> GeminiConfig:
        """Validate Gemini API configuration"""
        config = {
            'api_key': env_config.get('GOOGLE_API_KEY', ''),
            'model': env_config.get('GEMINI_MODEL', 'gemini-2.5-flash-lite')
        }
        
        try:
            return GeminiConfig(**config)
        except Exception as e:
            self.results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                field="gemini",
                message=f"Invalid Gemini configuration: {str(e)}",
                suggestion="Get Google Gemini API key from https://makersuite.google.com/app/apikey and add to .env"
            ))
            # Return a dummy object to continue validation
            return GeminiConfig(api_key="invalid")
    
    def _validate_language_credentials(self, env_config: Dict[str, str], languages: List[LanguageConfig]) -> Dict[str, TwitterCredentials]:
        """Validate Twitter credentials for each language"""
        lang_creds = {}
        
        for lang in languages:
            lang_upper = lang.code.upper()
            creds = {
                'consumer_key': env_config.get(f'{lang_upper}_TWITTER_CONSUMER_KEY', ''),
                'consumer_secret': env_config.get(f'{lang_upper}_TWITTER_CONSUMER_SECRET', ''),
                'access_token': env_config.get(f'{lang_upper}_TWITTER_ACCESS_TOKEN', ''),
                'access_token_secret': env_config.get(f'{lang_upper}_TWITTER_ACCESS_TOKEN_SECRET', '')
            }
            
            try:
                lang_creds[lang.code] = TwitterCredentials(**creds)
            except Exception as e:
                self.results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    field=f"twitter_{lang.code}",
                    message=f"Invalid Twitter credentials for {lang.name}: {str(e)}",
                    suggestion=f"Add {lang_upper}_TWITTER_* credentials to .env file for {lang.name} account"
                ))
                # Add dummy creds to continue validation
                lang_creds[lang.code] = TwitterCredentials(
                    consumer_key="invalid", consumer_secret="invalid",
                    access_token="invalid", access_token_secret="invalid"
                )
        
        return lang_creds
    
    def _validate_app_config(self, env_config: Dict[str, str]) -> AppConfig:
        """Validate application configuration"""
        config = {
            'poll_interval': int(env_config.get('POLL_INTERVAL_SECONDS', '300')),
            'log_level': env_config.get('LOG_LEVEL', 'INFO'),
            'twitter_daily_limit': int(env_config.get('TWITTER_FREE_DAILY_LIMIT', '50')),
            'twitter_monthly_limit': int(env_config.get('TWITTER_FREE_MONTHLY_LIMIT', '1500')),
            'async_mode': env_config.get('ASYNC_MODE', 'false').lower() == 'true'
        }
        
        try:
            return AppConfig(**config)
        except Exception as e:
            self.results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                field="app_config",
                message=f"Invalid application configuration: {str(e)}",
                suggestion="Check your .env file for correct values"
            ))
            # Return default config
            return AppConfig()
    
    def _validate_database_config(self, env_config: Dict[str, str]) -> Optional[DatabaseConfig]:
        """Validate database configuration (optional)"""
        db_url = env_config.get('DATABASE_URL')
        if not db_url:
            return None
        
        config = {
            'url': db_url,
            'pool_size': int(env_config.get('DB_POOL_SIZE', '5')),
            'max_overflow': int(env_config.get('DB_MAX_OVERFLOW', '10'))
        }
        
        try:
            return DatabaseConfig(**config)
        except Exception as e:
            self.results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                field="database",
                message=f"Invalid database configuration: {str(e)}",
                suggestion="Check DATABASE_URL format in .env file"
            ))
            return None
    
    def _validate_cross_dependencies(self):
        """Perform cross-validation checks"""
        # Check if username in env matches username in language config
        for lang in self.config_data.get('languages', []):
            expected_username = os.getenv('PRIMARY_TWITTER_USERNAME')
            if expected_username and expected_username != lang.get('twitter_username'):
                self.results.append(ValidationResult(
                    level=ValidationLevel.WARNING,
                    field=f"username_consistency",
                    message=f"Username mismatch for {lang.get('name', 'unknown')} language",
                    suggestion="Ensure usernames in .env match those in config/languages.json"
                ))
        
        # Check for duplicate language codes
        lang_codes = [lang.get('code') for lang in self.config_data.get('languages', [])]
        duplicates = set([code for code in lang_codes if lang_codes.count(code) > 1])
        if duplicates:
            self.results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                field="language_duplicates",
                message=f"Duplicate language codes found: {list(duplicates)}",
                suggestion="Remove duplicate language codes from config/languages.json"
            ))
    
    def print_results(self):
        """Print validation results in a user-friendly format"""
        if not self.results:
            print("✅ All configuration validation checks passed!")
            return
        
        # Group by level
        errors = [r for r in self.results if r.level == ValidationLevel.ERROR]
        warnings = [r for r in self.results if r.level == ValidationLevel.WARNING]
        infos = [r for r in self.results if r.level == ValidationLevel.INFO]
        
        if errors:
            print("❌ CONFIGURATION ERRORS:")
            for result in errors:
                print(f"   • {result.field}: {result.message}")
                if result.suggestion:
                    print(f"     💡 {result.suggestion}")
            print()
        
        if warnings:
            print("⚠️ CONFIGURATION WARNINGS:")
            for result in warnings:
                print(f"   • {result.field}: {result.message}")
                if result.suggestion:
                    print(f"     💡 {result.suggestion}")
            print()
        
        if infos:
            print("ℹ️ CONFIGURATION INFO:")
            for result in infos:
                print(f"   • {result.field}: {result.message}")
                if result.suggestion:
                    print(f"     💡 {result.suggestion}")
            print()
        
        # Summary
        if errors:
            print(f"❌ Configuration validation failed with {len(errors)} error(s)")
            print("🔧 Please fix the errors above before running the bot.")
        else:
            print(f"✅ Configuration validation passed with {len(warnings)} warning(s)")

# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def validate_configuration() -> Dict[str, Any]:
    """Validate complete configuration and return results"""
    validator = ConfigValidator()
    return validator.validate_all()

def validate_and_print() -> bool:
    """Validate configuration and print results, return True if valid"""
    validator = ConfigValidator()
    results = validator.validate_all()
    validator.print_results()
    return results['valid']

def quick_validate_credentials() -> bool:
    """Quick validation of just the API credentials"""
    validator = ConfigValidator()
    env_config = validator._load_environment_config()
    
    try:
        # Check primary Twitter
        validator._validate_primary_twitter(env_config)
        
        # Check Gemini
        validator._validate_gemini(env_config)
        
        # Check language configs exist
        languages = validator._load_language_config()
        if languages:
            validator._validate_language_credentials(env_config, languages)
        
        return len([r for r in validator.results if r.level == ValidationLevel.ERROR]) == 0
        
    except Exception:
        return False
