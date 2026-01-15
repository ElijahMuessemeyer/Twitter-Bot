#!/usr/bin/env python3
# =============================================================================
# TWITTER AUTO-TRANSLATION BOT - MAIN APPLICATION WITH ENHANCED ERROR HANDLING
# =============================================================================
# TODO: Before running, make sure you have:
# 1. Twitter API keys in .env file
# 2. Google Gemini API key in .env file
# 3. Configure your target languages in config/languages.json
# =============================================================================

import time
import schedule
from typing import List
from src.services.twitter_monitor import twitter_monitor
from src.services.gemini_translator import gemini_translator
from src.services.publisher import twitter_publisher
from src.config.settings import settings
from src.config.validator import validate_and_print
from src.utils.logger import logger
from src.utils.structured_logger import structured_logger
from src.utils.cache_monitor import cache_monitor
from src.models.tweet import Translation
from draft_manager import draft_manager
from src.exceptions import (
    TwitterAPIError,
    TwitterRateLimitError,
    TwitterAuthError,
    TwitterQuotaExceededError,
    GeminiAPIError,
    GeminiQuotaError,
    TranslationError,
    ConfigurationError,
    NetworkError
)
from src.utils.error_recovery import recover_from_error
from src.utils.circuit_breaker import circuit_breaker_manager
from src.web.dashboard import start_dashboard, update_dashboard_stats

class TwitterTranslationBot:
    def __init__(self):
        self.running = False
    
    def process_new_tweets(self):
        """Main processing function - check for new tweets and translate them with enhanced error handling"""
        logger.info("🔍 Checking for new tweets...")
        
        success = False
        error_occurred = False
        translations_count = 0
        
        try:
            # Log cache performance periodically
            cache_monitor.log_cache_stats_periodically()
            
            # Get new tweets from primary account with enhanced error handling
            try:
                new_tweets = twitter_monitor.get_new_tweets()
            except TwitterQuotaExceededError as e:
                logger.warning(f"⚠️ Twitter quota exceeded: {e}")
                return
            except (TwitterAuthError, ConfigurationError) as e:
                logger.error(f"❌ Twitter configuration error: {e}")
                return
            except TwitterRateLimitError as e:
                logger.info(f"🕐 Twitter rate limit hit, will retry later: {e}")
                return
            except NetworkError as e:
                logger.warning(f"🌐 Network error fetching tweets: {e}")
                return
            except TwitterAPIError as e:
                logger.error(f"❌ Twitter API error: {e}")
                return
            
            if not new_tweets:
                logger.info("📭 No new tweets found")
                success = True  # No errors, just no tweets
                return
            
            # Process each tweet with enhanced error handling
            for tweet in new_tweets:
                try:
                    # Log tweet processing with structured data
                    structured_logger.log_tweet_processing(
                        tweet_id=tweet.id,
                        text_preview=tweet.text,
                        language_count=len(settings.TARGET_LANGUAGES)
                    )
                    
                    # Translate to each target language
                    for lang_config in settings.TARGET_LANGUAGES:
                        try:
                            translation = gemini_translator.translate_tweet(
                                tweet, 
                                lang_config['name'], 
                                lang_config
                            )
                            
                            if translation:
                                # Try to post translation
                                try:
                                    if twitter_publisher.can_post():
                                        post_success = twitter_publisher.post_translation(translation)
                                        if post_success:
                                            logger.info(f" ✅ Posted translation to {lang_config['code']}: {translation.post_id}")
                                            translations_count += 1
                                        else:
                                            logger.warning(f"⚠️ Failed to post to {lang_config['code']}, saving as draft")
                                            draft_manager.save_translation_as_draft(translation, lang_config)
                                    else:
                                        # Save as draft when API limits reached
                                        logger.info(f"📊 API limit reached, saving {lang_config['code']} translation as draft")
                                        draft_manager.save_translation_as_draft(translation, lang_config)
                                        
                                except TwitterQuotaExceededError:
                                    logger.info(f"📊 Quota limit reached, saving {lang_config['code']} translation as draft")
                                    draft_manager.save_translation_as_draft(translation, lang_config)
                                except (TwitterAuthError, TwitterAPIError, NetworkError) as e:
                                    logger.warning(f"⚠️ Failed to post to {lang_config['code']}: {e}, saving as draft")
                                    draft_manager.save_translation_as_draft(translation, lang_config)
                            else:
                                logger.error(f"❌ Failed to translate tweet {tweet.id} to {lang_config['name']}")
                                
                        except GeminiQuotaError as e:
                            logger.error(f"❌ Gemini quota exceeded for {lang_config['name']}: {e}")
                            # Skip this language but continue with others
                            continue
                        except (GeminiAPIError, TranslationError) as e:
                            logger.error(f"❌ Translation failed for {lang_config['name']}: {e}")
                            continue
                        except Exception as e:
                            logger.error(f"❌ Unexpected error translating to {lang_config['name']}: {e}")
                            continue
                    
                    # Small delay between tweets to be respectful
                    time.sleep(2)
                    
                except Exception as tweet_error:
                    logger.error(f"❌ Error processing tweet {tweet.id}: {tweet_error}")
                    continue
        
        except Exception as e:
            # Final catch-all with error recovery
            error_occurred = True
            recovery_result = recover_from_error(
                e,
                {
                    'operation_type': 'process_new_tweets',
                    'service': 'twitter_bot'
                }
            )
            logger.error(f"❌ Error in process_new_tweets: {str(e)}")
            
            if not recovery_result['success']:
                # Log circuit breaker health status for debugging
                health_status = circuit_breaker_manager.get_all_health_status()
                logger.info(f"🔍 Circuit breaker status: {health_status}")
        
        finally:
            # Update dashboard statistics
            if not error_occurred:
                success = True
            update_dashboard_stats(
                successful_run=success,
                error_occurred=error_occurred,
                translations_count=translations_count
            )
    
    def run_once(self):
        """Run the bot once (useful for testing) with enhanced error handling"""
        structured_logger.log_bot_lifecycle("start_single_run", mode="once")
        
        try:
            # Check credentials with comprehensive validation
            if not settings.validate_configuration_comprehensive():
                logger.error("❌ Configuration validation failed. Please fix the issues above.")
                return
            
            self.process_new_tweets()
            
            # Show draft status
            draft_count = draft_manager.get_draft_count()
            if draft_count > 0:
                logger.info(f"📝 Current pending drafts: {draft_count}")
                
        except Exception as e:
            recovery_result = recover_from_error(
                e,
                {
                    'operation_type': 'run_once',
                    'service': 'twitter_bot'
                }
            )
            logger.error(f"❌ Error in run_once: {str(e)}")
    
    def run_scheduled(self):
        """Run the bot on a schedule with enhanced error handling"""
        logger.info("📭 Starting Twitter Translation Bot (scheduled mode)")
        
        try:
            # Check credentials with comprehensive validation
            if not settings.validate_configuration_comprehensive():
                logger.error("❌ Configuration validation failed. Please fix the issues above.")
                return
            
            # Schedule the job
            schedule.every(settings.POLL_INTERVAL).seconds.do(self.process_new_tweets)
            
            self.running = True
            
            while self.running:
                try:
                    schedule.run_pending()
                    time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("⚠️ Stopping bot due to keyboard interrupt")
                    self.running = False
                    break
                except Exception as e:
                    # Log error but continue running
                    logger.error(f"❌ Error in scheduled loop: {str(e)}")
                    time.sleep(5)  # Wait before continuing
                    
        except Exception as e:
            recovery_result = recover_from_error(
                e,
                {
                    'operation_type': 'run_scheduled',
                    'service': 'twitter_bot'
                }
            )
            logger.error(f"❌ Error in run_scheduled: {str(e)}")
            self.running = False
    
    def stop(self):
        """Stop the scheduled bot"""
        self.running = False
        logger.info("🛑 Bot stop requested")

def main():
    import sys
    import os
    
    # Start dashboard if enabled (before everything else)
    dashboard_thread = start_dashboard()
    
    # Check if async mode is enabled
    use_async = os.getenv('ASYNC_MODE', 'false').lower() == 'true'
    async_arg = len(sys.argv) > 1 and sys.argv[1].lower() == 'async'
    
    if use_async or async_arg:
        logger.info("🚀 Starting in ASYNC mode for enhanced performance")
        # Import and run async version
        import asyncio
        from main_async import main as async_main
        asyncio.run(async_main())
        return
    
    logger.info("⚡ Starting in SYNC mode (traditional)")
    bot = TwitterTranslationBot()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'once':
            bot.run_once()
        elif command == 'drafts':
            draft_manager.display_pending_drafts()
        elif command == 'status':
            try:
                print(f"📊 API Usage Status:")
                print(f"  Daily requests: {twitter_monitor.daily_requests}/{settings.TWITTER_FREE_DAILY_LIMIT}")
                print(f"  Monthly posts: {twitter_monitor.monthly_posts}/{settings.TWITTER_FREE_MONTHLY_LIMIT}")
                print(f"  Pending drafts: {draft_manager.get_draft_count()}")
                
                # Show circuit breaker health
                health_status = circuit_breaker_manager.get_all_health_status()
                if health_status:
                    print(f"🔧 Circuit Breaker Status:")
                    for cb in health_status:
                        status = "🟢 Healthy" if cb['healthy'] else "🔴 Unhealthy" 
                        print(f"  {cb['name']}: {status} ({cb['state']})")
                        
            except Exception as e:
                logger.error(f"Error getting status: {e}")
                
        elif command == 'cache':
            cache_monitor.print_performance_summary()
        elif command == 'test':
            try:
                logger.info("🧪 Testing API connections...")
                if settings.validate_configuration_comprehensive():
                    twitter_publisher.test_connections()
                else:
                    logger.error("❌ Cannot test connections - invalid configuration")
            except Exception as e:
                logger.error(f"Error testing connections: {e}")
        
        elif command == 'config':
            try:
                print("🔧 Configuration Validation Report:")
                print("=" * 50)
                settings.print_configuration_status()
                print("\n" + "=" * 50)
                
                # Run comprehensive validation
                is_valid = validate_and_print()
                
                if is_valid:
                    print("\n✅ All configuration checks passed! Bot is ready to run.")
                else:
                    print("\n❌ Configuration issues found. Please fix them before running the bot.")
                    
            except Exception as e:
                logger.error(f"Error checking configuration: {e}")
        
        elif command == 'validate':
            try:
                print("🔍 Running comprehensive configuration validation...")
                is_valid = validate_and_print()
                
                if is_valid:
                    print("\n🚀 Configuration is valid! You can now run the bot.")
                    exit(0)
                else:
                    print("\n⚠️ Please fix the configuration issues above.")
                    exit(1)
                    
            except Exception as e:
                logger.error(f"Error during validation: {e}")
                exit(1)
                
        elif command == 'health':
            try:
                print("🏥 System Health Check:")
                
                # Circuit breaker health
                health_status = circuit_breaker_manager.get_all_health_status()
                print(f"Circuit Breakers: {len(health_status)} configured")
                for cb in health_status:
                    status = "🟢" if cb['healthy'] else "🔴"
                    print(f"  {status} {cb['name']}: {cb['state']} (failures: {cb['failure_count']})")
                
                # Error recovery health
                from src.utils.error_recovery import error_recovery_manager
                recovery_health = error_recovery_manager.get_health_status()
                print(f"Error Recovery: {recovery_health['queued_operations']} queued operations")
                if recovery_health['degraded_services']:
                    print(f"  ⚠️ Degraded services: {recovery_health['degraded_services']}")
                
            except Exception as e:
                logger.error(f"Error getting health status: {e}")
                
        elif command == 'retry':
            try:
                from src.utils.error_recovery import error_recovery_manager
                result = error_recovery_manager.retry_queued_operations()
                print(f"🔄 Retry Results: {result}")
            except Exception as e:
                logger.error(f"Error retrying operations: {e}")
                
        elif command == 'dashboard':
            print("🌐 Dashboard Information:")
            print("=" * 50)
            dashboard_enabled = os.getenv('ENABLE_DASHBOARD', 'false').lower() == 'true'
            ui_enabled = os.getenv('ENABLE_DASHBOARD_UI', 'false').lower() == 'true'
            port = os.getenv('DASHBOARD_PORT', '8080')
            
            if dashboard_enabled:
                print(f"✅ Dashboard is ENABLED")
                print(f"🔗 API Endpoints: http://localhost:{port}")
                print("   • /health - System health status")
                print("   • /metrics - Performance metrics")
                print("   • /config - Configuration status")  
                print("   • /drafts - Draft management status")
                print("   • /services - Individual service status")
                
                if ui_enabled:
                    print(f"🎨 Web UI: http://localhost:{port}")
                    print("   • Simple dashboard with auto-refresh")
                else:
                    print("🎨 Web UI: DISABLED (set ENABLE_DASHBOARD_UI=true to enable)")
                    
                print(f"\nTo start dashboard with bot: ENABLE_DASHBOARD=true python main.py")
            else:
                print("❌ Dashboard is DISABLED")
                print("To enable: ENABLE_DASHBOARD=true python main.py")
                print(f"Optional UI: ENABLE_DASHBOARD_UI=true")
                print(f"Custom port: DASHBOARD_PORT={port}")
                
        else:
            print("Usage: python main.py [once|drafts|status|cache|test|config|validate|health|retry|dashboard]")
            print("  once      - Run once and exit")
            print("  drafts    - Show pending drafts")
            print("  status    - Show API usage status")
            print("  cache     - Show translation cache performance")
            print("  test      - Test API connections")
            print("  config    - Show detailed configuration status and validation")
            print("  validate  - Run comprehensive configuration validation (exit 0/1)")
            print("  health    - Show system health and circuit breaker status")
            print("  retry     - Retry queued operations")
            print("  dashboard - Show dashboard configuration and endpoints")
            print("  (no args) - Run continuously on schedule")
    else:
        bot.run_scheduled()

if __name__ == "__main__":
    main()
