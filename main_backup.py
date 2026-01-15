#!/usr/bin/env python3
# =============================================================================
# TWITTER AUTO-TRANSLATION BOT - MAIN APPLICATION
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

class TwitterTranslationBot:
    def __init__(self):
        self.running = False
    
    def process_new_tweets(self):
        """Main processing function - check for new tweets and translate them"""
        logger.info("🔍 Checking for new tweets...")
        
        try:
            # Log cache performance periodically
            cache_monitor.log_cache_stats_periodically()
            
            # Get new tweets from primary account
            new_tweets = twitter_monitor.get_new_tweets()
            
            if not new_tweets:
                logger.info("📭 No new tweets found")
                return
            
            # Process each tweet
            for tweet in new_tweets:
                # Log tweet processing with structured data
                structured_logger.log_tweet_processing(
                    tweet_id=tweet.id,
                    text_preview=tweet.text,
                    language_count=len(settings.TARGET_LANGUAGES)
                )
                
                # Translate to each target language
                for lang_config in settings.TARGET_LANGUAGES:
                    translation = gemini_translator.translate_tweet(
                        tweet, 
                        lang_config['name'], 
                        lang_config
                    )
                    
                    if translation:
                        # Try to post translation
                        if twitter_publisher.can_post():
                            success = twitter_publisher.post_translation(translation)
                            if success:
                                logger.info(f" Posted translation to {lang_config['code']}: {translation.post_id}")
                            else:
                                logger.warning(f"⚠️ Failed to post to {lang_config['code']}, saving as draft")
                                draft_manager.save_translation_as_draft(translation, lang_config)
                        else:
                            # Save as draft when API limits reached
                            logger.info(f"📊 API limit reached, saving {lang_config['code']} translation as draft")
                            draft_manager.save_translation_as_draft(translation, lang_config)
                    else:
                        logger.error(f"❌ Failed to translate tweet {tweet.id} to {lang_config['name']}")
                
                # Small delay between tweets to be respectful
                time.sleep(2)
        
        except Exception as e:
            logger.error(f"❌ Error in process_new_tweets: {str(e)}")
    
    def run_once(self):
        """Run the bot once (useful for testing)"""
        structured_logger.log_bot_lifecycle("start_single_run", mode="once")
        
        # Check credentials first
        if not settings.validate_credentials():
            logger.error("❌ Missing API credentials. Please check your .env file.")
            return
        
        self.process_new_tweets()
        
        # Show draft status
        draft_count = draft_manager.get_draft_count()
        if draft_count > 0:
            logger.info(f"📝 Current pending drafts: {draft_count}")
    
    def run_scheduled(self):
        """Run the bot on a schedule"""
        logger.info("📭 Starting Twitter Translation Bot (scheduled mode)")
        
        # Check credentials first
        if not settings.validate_credentials():
            logger.error("❌ Missing API credentials. Please check your .env file.")
            return
        
        # Schedule the job
        schedule.every(settings.POLL_INTERVAL).seconds.do(self.process_new_tweets)
        
        self.running = True
        
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("⚠️ Stopping bot due to keyboard interrupt")
            self.running = False
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            self.running = False
    
    def stop(self):
        """Stop the scheduled bot"""
        self.running = False

def main():
    import sys
    import os
    
    # Check if async mode is enabled
    use_async = os.getenv('ASYNC_MODE', 'false').lower() == 'true'
    
    if use_async:
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
            print(f"📊 API Usage Status:")
            print(f"  Daily requests: {twitter_monitor.daily_requests}/{settings.TWITTER_FREE_DAILY_LIMIT}")
            print(f"  Monthly posts: {twitter_monitor.monthly_posts}/{settings.TWITTER_FREE_MONTHLY_LIMIT}")
            print(f"  Pending drafts: {draft_manager.get_draft_count()}")
        elif command == 'cache':
            cache_monitor.print_performance_summary()
        elif command == 'test':
            logger.info("🧪 Testing API connections...")
            if settings.validate_credentials():
                twitter_publisher.test_connections()
            else:
                logger.error("❌ Cannot test connections - missing API credentials")
        elif command == 'async':
            logger.info("🚀 Switching to async mode...")
            import asyncio
            from main_async import main as async_main
            asyncio.run(async_main())
        else:
            print("Usage: python main.py [once|drafts|status|cache|test|async]")
            print("  once   - Run once and exit")
            print("  drafts - Show pending drafts")
            print("  status - Show API usage status")
            print("  cache  - Show translation cache performance")
            print("  test   - Test API connections")
            print("  async  - Switch to async mode for enhanced performance")
            print("  (no args) - Run continuously on schedule")
            print("")
            print("💡 Tip: Set ASYNC_MODE=true in .env for automatic async mode")
    else:
        bot.run_scheduled()

if __name__ == "__main__":
    main()