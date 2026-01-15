# =============================================================================
# TWITTER PUBLISHER SERVICE - ENHANCED ERROR HANDLING
# =============================================================================
# TODO: You need Twitter API keys for each language account

import tweepy
from typing import Dict, Optional, List
from ..config.settings import settings
from ..utils.logger import logger
from ..models.tweet import Translation
from ..services.twitter_monitor import twitter_monitor
from ..exceptions import (
    TwitterAPIError,
    TwitterRateLimitError,
    TwitterAuthError,
    TwitterConnectionError,
    TwitterQuotaExceededError,
    NetworkError,
    ConfigurationError
)
from ..utils.retry import retry_with_backoff, RetryConfig
from ..utils.circuit_breaker import circuit_breaker_protection, CircuitBreakerConfig
from ..utils.error_recovery import recover_from_error
from ..utils.structured_logger import structured_logger

class TwitterPublisher:
    def __init__(self):
        self.language_clients = {}
        self._initialize_language_clients()
    
    def _initialize_language_clients(self):
        """Initialize Twitter API clients for each language account"""
        for lang_config in settings.TARGET_LANGUAGES:
            lang_code = lang_config['code']
            credentials = settings.get_twitter_creds_for_language(lang_code)
            
            # Check if we have valid credentials
            if all(credentials.values()) and not any(v.startswith('your_') for v in credentials.values()):
                try:
                    auth = tweepy.OAuth1UserHandler(
                        credentials['consumer_key'],
                        credentials['consumer_secret'],
                        credentials['access_token'],
                        credentials['access_token_secret']
                    )
                    
                    client = tweepy.API(auth, wait_on_rate_limit=True)
                    self.language_clients[lang_code] = client
                    logger.info(f" Initialized Twitter client for {lang_code}")
                    
                except Exception as e:
                    logger.error(f"L Failed to initialize Twitter client for {lang_code}: {str(e)}")
            else:
                logger.warning(f"⚠️ Missing or invalid credentials for {lang_code} Twitter account")
                logger.info(f"   TODO: Add {lang_code.upper()}_TWITTER_* credentials to .env file")
    
    def can_post(self) -> bool:
        """Check if we can post without exceeding API limits"""
        return twitter_monitor.can_post_tweet()
    
    def post_translation(self, translation: Translation) -> bool:
        """Post a translation to the appropriate language account"""
        if not self.can_post():
            logger.warning("⚠️ Monthly posting limit reached, cannot post translation")
            return False
        
        lang_code = translation.target_language.lower()
        
        # Map full language names to codes if needed
        lang_code_map = {
            'japanese': 'ja',
            'german': 'de',
            'spanish': 'es',
            'french': 'fr'
        }
        
        if lang_code in lang_code_map:
            lang_code = lang_code_map[lang_code]
        
        if lang_code not in self.language_clients:
            logger.error(f"L No Twitter client available for language: {lang_code}")
            logger.info(f"   TODO: Add {lang_code.upper()}_TWITTER_* credentials to .env file")
            return False
        
        try:
            client = self.language_clients[lang_code]
            
            # Post the tweet
            status = client.update_status(translation.translated_text)
            
            # Update translation status
            translation.status = 'posted'
            translation.post_id = str(status.id)
            
            # Update API usage counter
            twitter_monitor.monthly_posts += 1
            twitter_monitor.save_api_usage()
            
            logger.info(f" Successfully posted translation to {lang_code}: {status.id}")
            logger.info(f"   Tweet: {translation.translated_text[:100]}...")
            return True
            
        except Exception as e:
            logger.error(f"L Error posting translation to {lang_code}: {str(e)}")
            translation.status = 'failed'
            translation.error_message = str(e)
            return False
    
    def post_multiple_translations(self, translations: List[Translation]) -> Dict[str, bool]:
        """Post multiple translations, returning success status for each"""
        results = {}
        
        for translation in translations:
            lang_code = translation.target_language
            results[lang_code] = self.post_translation(translation)
            
            # Stop if we hit API limits
            if not self.can_post():
                logger.warning("⚠️ Reached API limits, stopping batch posting")
                break
        
        return results
    
    def get_available_languages(self) -> List[str]:
        """Get list of languages we can actually post to (have valid credentials)"""
        return list(self.language_clients.keys())
    
    def test_connections(self):
        """Test all language account connections"""
        logger.info(">⚠️ Testing Twitter connections for all language accounts...")
        
        for lang_code, client in self.language_clients.items():
            try:
                # Try to get account info
                user = client.verify_credentials()
                logger.info(f" {lang_code}: Connected as @{user.screen_name}")
            except Exception as e:
                logger.error(f"L {lang_code}: Connection failed - {str(e)}")
        
        if not self.language_clients:
            logger.warning("⚠️ No language accounts configured!")
            logger.info("   Add Twitter API credentials for your language accounts to .env file")

# Global publisher instance
twitter_publisher = TwitterPublisher()