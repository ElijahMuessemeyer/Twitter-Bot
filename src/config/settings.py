# =============================================================================
# CONFIGURATION SETTINGS
# =============================================================================
# TODO: Before running, you need to:
# 1. Copy config/.env.template to .env
# 2. Get Twitter API keys from https://developer.twitter.com/
# 3. Get Google Gemini API key from https://makersuite.google.com/app/apikey
# 4. Fill in all the API keys in the .env file
# =============================================================================

import os
import json
import logging
from dotenv import load_dotenv
from pathlib import Path
from typing import Dict, Any, Optional

load_dotenv()

# Import validation components
try:
    from .validator import ConfigValidator, validate_configuration, ValidationLevel
except ImportError:
    # Fallback if validator is not available
    ConfigValidator = None
    validate_configuration = None
    ValidationLevel = None

logger = logging.getLogger(__name__)

class Settings:
    def __init__(self, validate_on_init: bool = False):
        # Validation results
        self._validation_results: Optional[Dict[str, Any]] = None
        self._is_valid: Optional[bool] = None
        
        # Twitter API credentials - PRIMARY ACCOUNT
        # TODO: GET THESE FROM TWITTER DEVELOPER PORTAL
        self.PRIMARY_TWITTER_CREDS = {
            'consumer_key': os.getenv('PRIMARY_TWITTER_CONSUMER_KEY'),
            'consumer_secret': os.getenv('PRIMARY_TWITTER_CONSUMER_SECRET'),
            'access_token': os.getenv('PRIMARY_TWITTER_ACCESS_TOKEN'),
            'access_token_secret': os.getenv('PRIMARY_TWITTER_ACCESS_TOKEN_SECRET')
        }
        
        self.PRIMARY_USERNAME = os.getenv('PRIMARY_TWITTER_USERNAME')
        
        # Google Gemini API - TODO: GET THIS FROM GOOGLE AI STUDIO
        self.GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
        self.GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')
        
        # App settings
        self.POLL_INTERVAL = int(os.getenv('POLL_INTERVAL_SECONDS', 300))
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        
        # Load language configurations
        self.load_language_config()
        
        # API Limits (Twitter Free Tier)
        self.TWITTER_FREE_MONTHLY_LIMIT = int(os.getenv('TWITTER_FREE_MONTHLY_LIMIT', 1500))
        self.TWITTER_FREE_DAILY_LIMIT = int(os.getenv('TWITTER_FREE_DAILY_LIMIT', 50))
        
        # Database settings (optional)
        self.DATABASE_URL = os.getenv('DATABASE_URL')
        self.DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', 5))
        self.DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', 10))
        
        # Async settings
        self.ASYNC_MODE = os.getenv('ASYNC_MODE', 'false').lower() == 'true'
        
        # Validate configuration on initialization if requested
        if validate_on_init:
            self.validate_configuration_comprehensive()
        
    def load_language_config(self):
        """Load target language configurations from JSON file"""
        config_path = Path('config/languages.json')
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                self.TARGET_LANGUAGES = config['target_languages']
        else:
            self.TARGET_LANGUAGES = []
    
    def get_twitter_creds_for_language(self, lang_code):
        """Get Twitter credentials for a specific language account
        TODO: Each language needs its own Twitter app with separate API keys
        """
        lang_upper = lang_code.upper()
        return {
            'consumer_key': os.getenv(f'{lang_upper}_TWITTER_CONSUMER_KEY'),
            'consumer_secret': os.getenv(f'{lang_upper}_TWITTER_CONSUMER_SECRET'),
            'access_token': os.getenv(f'{lang_upper}_TWITTER_ACCESS_TOKEN'),
            'access_token_secret': os.getenv(f'{lang_upper}_TWITTER_ACCESS_TOKEN_SECRET')
        }
    
    def validate_credentials(self):
        """Check if required API credentials are available (legacy method)"""
        missing = []
        
        # Check primary Twitter credentials
        for key, value in self.PRIMARY_TWITTER_CREDS.items():
            if not value or value.startswith('your_'):
                missing.append(f'PRIMARY_TWITTER_{key.upper()}')
        
        # Check Google Gemini API key
        if not self.GOOGLE_API_KEY or self.GOOGLE_API_KEY.startswith('your_'):
            missing.append('GOOGLE_API_KEY')
        
        # Check language account credentials
        for lang_config in self.TARGET_LANGUAGES:
            lang_creds = self.get_twitter_creds_for_language(lang_config['code'])
            for key, value in lang_creds.items():
                if not value or value.startswith('your_'):
                    missing.append(f'{lang_config["code"].upper()}_TWITTER_{key.upper()}')
        
        if missing:
            print("❌ MISSING API CREDENTIALS:")
            print("You need to get the following API keys and add them to your .env file:")
            for cred in missing:
                print(f"  - {cred}")
            print("\n📋 Instructions:")
            print("1. Twitter API keys: https://developer.twitter.com/")
            print("2. Google Gemini API key: https://makersuite.google.com/app/apikey")
            print("3. Copy config/.env.template to .env and fill in the keys")
            return False
        
        return True
    
    def validate_configuration_comprehensive(self) -> bool:
        """
        Comprehensive configuration validation using the validator system.
        Returns True if configuration is valid, False otherwise.
        """
        if validate_configuration is None:
            logger.warning("Comprehensive validation not available, falling back to legacy validation")
            return self.validate_credentials()
        
        try:
            # Run comprehensive validation
            self._validation_results = validate_configuration()
            self._is_valid = self._validation_results['valid']
            
            # Print results if there are errors or warnings
            if not self._validation_results['valid'] or any(
                r.level in [ValidationLevel.ERROR, ValidationLevel.WARNING] 
                for r in self._validation_results['results']
            ):
                validator = ConfigValidator()
                validator.results = self._validation_results['results']
                validator.print_results()
            
            return self._is_valid
            
        except Exception as e:
            logger.error(f"Error during comprehensive validation: {str(e)}")
            # Fall back to legacy validation
            return self.validate_credentials()
    
    def get_validation_results(self) -> Optional[Dict[str, Any]]:
        """Get the last validation results"""
        return self._validation_results
    
    def is_configuration_valid(self) -> bool:
        """
        Check if configuration is valid. 
        If validation hasn't been run, run it now.
        """
        if self._is_valid is None:
            return self.validate_configuration_comprehensive()
        return self._is_valid
    
    def get_configuration_summary(self) -> Dict[str, Any]:
        """Get a summary of the current configuration"""
        return {
            'primary_twitter_configured': bool(self.PRIMARY_TWITTER_CREDS.get('consumer_key')),
            'gemini_configured': bool(self.GOOGLE_API_KEY),
            'target_languages_count': len(self.TARGET_LANGUAGES),
            'target_languages': [lang.get('name', 'Unknown') for lang in self.TARGET_LANGUAGES],
            'poll_interval': self.POLL_INTERVAL,
            'log_level': self.LOG_LEVEL,
            'async_mode': self.ASYNC_MODE,
            'database_configured': bool(self.DATABASE_URL),
            'validation_status': self._is_valid,
            'validation_last_run': self._validation_results is not None
        }
    
    def print_configuration_status(self, mask_secrets: bool = True):
        """Print current configuration status with secrets masked"""
        summary = self.get_configuration_summary()
        
        print("🔧 CONFIGURATION STATUS:")
        print(f"   Primary Twitter: {'✅' if summary['primary_twitter_configured'] else '❌'}")
        print(f"   Gemini API: {'✅' if summary['gemini_configured'] else '❌'}")
        print(f"   Target Languages: {summary['target_languages_count']} configured")
        
        if summary['target_languages']:
            for lang in summary['target_languages']:
                print(f"     • {lang}")
        
        print(f"   Poll Interval: {summary['poll_interval']} seconds")
        print(f"   Log Level: {summary['log_level']}")
        print(f"   Async Mode: {'✅' if summary['async_mode'] else '❌'}")
        print(f"   Database: {'✅' if summary['database_configured'] else '❌'}")
        
        if summary['validation_status'] is not None:
            status = "✅ Valid" if summary['validation_status'] else "❌ Invalid"
            print(f"   Validation: {status}")
        else:
            print(f"   Validation: ⚠️ Not run")
        
        if not mask_secrets:
            print("\n🔐 CREDENTIALS (UNMASKED):")
            print(f"   Primary Twitter Consumer Key: {self.PRIMARY_TWITTER_CREDS.get('consumer_key', 'Not set')}")
            print(f"   Gemini API Key: {self.GOOGLE_API_KEY or 'Not set'}")
        else:
            print("\n🔐 CREDENTIALS (MASKED):")
            consumer_key = self.PRIMARY_TWITTER_CREDS.get('consumer_key', '')
            if consumer_key:
                masked_key = consumer_key[:4] + '*' * (len(consumer_key) - 8) + consumer_key[-4:]
                print(f"   Primary Twitter Consumer Key: {masked_key}")
            else:
                print(f"   Primary Twitter Consumer Key: Not set")
            
            if self.GOOGLE_API_KEY:
                masked_gemini = self.GOOGLE_API_KEY[:6] + '*' * (len(self.GOOGLE_API_KEY) - 10) + self.GOOGLE_API_KEY[-4:]
                print(f"   Gemini API Key: {masked_gemini}")
            else:
                print(f"   Gemini API Key: Not set")

# Global settings instance
settings = Settings()