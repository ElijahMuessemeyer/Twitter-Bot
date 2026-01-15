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
        """Initialize Twitter API clients for each language account with enhanced error handling"""
        for lang_config in settings.TARGET_LANGUAGES:
            lang_code = lang_config['code']
            
            try:
                credentials = settings.get_twitter_creds_for_language(lang_code)
                
                # Check if we have valid credentials
                if not credentials:
                    raise ConfigurationError(f"No credentials found for {lang_code}")
                
                if not all(credentials.values()) or any(v.startswith('your_') for v in credentials.values()):
                    raise ConfigurationError(f"Invalid credentials for {lang_code}")
                
                # Create and test client
                auth = tweepy.OAuth1UserHandler(
                    credentials['consumer_key'],
                    credentials['consumer_secret'],
                    credentials['access_token'],
                    credentials['access_token_secret']
                )
                
                client = tweepy.API(auth, wait_on_rate_limit=True)
                
                # Test the client
                try:
                    client.verify_credentials()
                    self.language_clients[lang_code] = client
                    logger.info(f" ✅ Initialized Twitter client for {lang_code}")
                except tweepy.Unauthorized:
                    raise TwitterAuthError(f"Invalid credentials for {lang_code}")
                except tweepy.TooManyRequests:
                    raise TwitterRateLimitError(f"Rate limit during verification for {lang_code}")
                except Exception as verify_error:
                    raise TwitterConnectionError(f"Failed to verify credentials for {lang_code}: {verify_error}")
                    
            except (TwitterAuthError, TwitterRateLimitError, TwitterConnectionError, ConfigurationError) as e:
                logger.error(f"❌ Failed to initialize Twitter client for {lang_code}: {str(e)}")
            except Exception as e:
                logger.error(f"❌ Unexpected error initializing Twitter client for {lang_code}: {str(e)}")
                
        if not self.language_clients:
            logger.warning("⚠️ No language accounts configured!")
            logger.info("   Add Twitter API credentials for your language accounts to .env file")
    
    def can_post(self) -> bool:
        """Check if we can post without exceeding API limits"""
        try:
            return twitter_monitor.can_post_tweet()
        except TwitterQuotaExceededError:
            logger.warning("Monthly posting limit reached")
            return False
    
    @retry_with_backoff(
        retryable_exceptions=(TwitterConnectionError, NetworkError),
        config=RetryConfig(max_attempts=3, base_delay=2.0)
    )
    @circuit_breaker_protection(
        "twitter_publisher",
        config=CircuitBreakerConfig(failure_threshold=3, timeout=120.0)
    )
    def post_translation(self, translation: Translation) -> bool:
        """Post a translation to the appropriate language account with enhanced error handling"""
        if not self.can_post():
            raise TwitterQuotaExceededError("Monthly posting limit reached, cannot post translation")
        
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
            raise ConfigurationError(
                f"No Twitter client available for language: {lang_code}. "
                f"Add {lang_code.upper()}_TWITTER_* credentials to .env file"
            )
        
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
            
            # Log successful post
            structured_logger.info(
                f"Successfully posted translation to {lang_code}",
                event="translation_posted",
                language=lang_code,
                tweet_id=status.id,
                character_count=len(translation.translated_text),
                original_tweet_id=translation.original_tweet.id
            )
            
            logger.info(f" ✅ Successfully posted translation to {lang_code}: {status.id}")
            logger.info(f"   Tweet: {translation.translated_text[:100]}...")
            return True
            
        except tweepy.Unauthorized:
            error = TwitterAuthError(f"Authentication failed for {lang_code}")
            translation.status = 'failed'
            translation.error_message = str(error)
            raise error
        except tweepy.TooManyRequests as e:
            reset_time = getattr(e.response, 'headers', {}).get('x-rate-limit-reset')
            error = TwitterRateLimitError(
                f"Rate limit exceeded for {lang_code}",
                reset_time=int(reset_time) if reset_time else None
            )
            translation.status = 'failed'
            translation.error_message = str(error)
            raise error
        except tweepy.Forbidden:
            error = TwitterAuthError(f"Access forbidden for {lang_code}")
            translation.status = 'failed'
            translation.error_message = str(error)
            raise error
        except (tweepy.BadRequest, tweepy.NotFound) as e:
            error = TwitterAPIError(f"Twitter API error for {lang_code}: {e}")
            translation.status = 'failed'
            translation.error_message = str(error)
            raise error
        except (ConnectionError, TimeoutError) as e:
            error = NetworkError(f"Network error posting to {lang_code}: {e}")
            translation.status = 'failed'
            translation.error_message = str(error)
            raise error
        except Exception as e:
            # Try error recovery for unknown errors
            recovery_result = recover_from_error(
                e,
                {
                    'operation_type': 'post_translation',
                    'service': 'twitter_publisher',
                    'language': lang_code,
                    'tweet_id': translation.original_tweet.id
                }
            )
            
            translation.status = 'failed'
            translation.error_message = str(e)
            
            if recovery_result['success']:
                return False  # Return false but don't raise - let calling code handle gracefully
            else:
                raise TwitterAPIError(f"Error posting translation to {lang_code}: {str(e)}")
    
    def post_multiple_translations(self, translations: List[Translation]) -> Dict[str, bool]:
        """Post multiple translations, returning success status for each with enhanced error handling"""
        results = {}
        
        for translation in translations:
            lang_code = translation.target_language
            
            try:
                results[lang_code] = self.post_translation(translation)
            except TwitterQuotaExceededError:
                logger.warning("⚠️ Reached API limits, stopping batch posting")
                results[lang_code] = False
                break
            except (TwitterAuthError, TwitterAPIError, NetworkError) as e:
                logger.error(f"Failed to post translation for {lang_code}: {e}")
                results[lang_code] = False
                continue
            
        return results
    
    def get_available_languages(self) -> List[str]:
        """Get list of languages we can actually post to (have valid credentials)"""
        return list(self.language_clients.keys())
    
    def test_connections(self):
        """Test all language account connections with enhanced error handling"""
        logger.info("🧪 Testing Twitter connections for all language accounts...")
        
        if not self.language_clients:
            logger.warning("⚠️ No language accounts configured!")
            logger.info("   Add Twitter API credentials for your language accounts to .env file")
            return
        
        for lang_code, client in self.language_clients.items():
            try:
                # Try to get account info
                user = client.verify_credentials()
                logger.info(f" ✅ {lang_code}: Connected as @{user.screen_name}")
                
                # Log connection test result
                structured_logger.info(
                    f"Twitter connection test successful for {lang_code}",
                    event="connection_test_success",
                    language=lang_code,
                    username=user.screen_name,
                    user_id=user.id
                )
                
            except tweepy.Unauthorized:
                logger.error(f"❌ {lang_code}: Authentication failed - invalid credentials")
            except tweepy.TooManyRequests:
                logger.error(f"❌ {lang_code}: Rate limit exceeded during connection test")
            except Exception as e:
                logger.error(f"❌ {lang_code}: Connection failed - {str(e)}")
                
                # Log connection test failure
                structured_logger.error(
                    f"Twitter connection test failed for {lang_code}",
                    event="connection_test_failed",
                    language=lang_code,
                    error_type=e.__class__.__name__,
                    error_message=str(e)
                )

# Global publisher instance
twitter_publisher = TwitterPublisher()
