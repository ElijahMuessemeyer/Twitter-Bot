#!/usr/bin/env python3
# =============================================================================
# TWITTER AUTO-TRANSLATION BOT - DATABASE-ENABLED MAIN APPLICATION
# =============================================================================
# This version uses database-backed services instead of file-based storage

import time
import schedule
from typing import List
from src.services.gemini_translator import gemini_translator
from src.services.publisher import twitter_publisher
from src.services.service_factory import get_twitter_monitor, get_draft_manager
from src.config.settings import settings
from src.config.database import db_config
from src.utils.logger import logger
from src.utils.structured_logger import structured_logger
from src.utils.cache_monitor import cache_monitor
from src.models.tweet import Translation

class DatabaseTwitterTranslationBot:
    def __init__(self):
        self.running = False
        self.twitter_monitor = get_twitter_monitor()
        self.draft_manager = get_draft_manager()
        
        # Run database health check
        if not self._check_database_health():
            logger.warning("⚠️ Database health check failed, some features may not work properly")
    
    def _check_database_health(self) -> bool:
        """Check database connectivity"""
        try:
            return db_config.health_check()
        except Exception as e:
            logger.error(f"Database health check error: {str(e)}")
            return False
    
    def process_new_tweets(self):
        """Main processing function - check for new tweets and translate them"""
        logger.info("🔍 Checking for new tweets...")
        
        try:
            # Log cache performance periodically
            cache_monitor.log_cache_stats_periodically()
            
            # Get new tweets from primary account (now database-backed)
            new_tweets = self.twitter_monitor.get_new_tweets()
            
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
                                logger.info(f" Posted translation to {lang_config['code']}: {translation.post_id}")
                                
                                # If we had a draft, mark it as posted
                                if hasattr(translation, 'draft_id'):
                                    self.draft_manager.mark_draft_as_posted(
                                        translation.draft_id, 
                                        translation.post_id
                                    )
                            else:
                                logger.warning(f"⚠️ Failed to post to {lang_config['code']}, saving as draft")
                                self.draft_manager.save_translation_as_draft(translation, lang_config)
                        else:
                            # Save as draft when API limits reached
                            logger.info(f"📊 API limit reached, saving {lang_config['code']} translation as draft")
                            self.draft_manager.save_translation_as_draft(translation, lang_config)
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
        draft_count = self.draft_manager.get_draft_count()
        if draft_count > 0:
            logger.info(f"📝 Current pending drafts: {draft_count}")
    
    def run_scheduled(self):
        """Run the bot on a schedule"""
        logger.info("📭 Starting Twitter Translation Bot (database-enabled mode)")
        
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
            logger.info("⚠️ Stopping bot due to keyboard interrupt")
            self.running = False
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            self.running = False
    
    def stop(self):
        """Stop the scheduled bot"""
        self.running = False
    
    def show_database_status(self):
        """Show database and API usage statistics"""
        try:
            # Database health
            health_ok = self._check_database_health()
            print(f"📊 Database Status: {'✅ Healthy' if health_ok else '❌ Unhealthy'}")
            
            # API usage stats from database
            if hasattr(self.twitter_monitor, 'get_api_statistics'):
                api_stats = self.twitter_monitor.get_api_statistics()
                if api_stats:
                    current_limits = api_stats.get('current_limits', {})
                    print(f"🐦 Twitter API Usage:")
                    print(f"  Daily requests: {current_limits.get('daily_requests', 0)}/{api_stats.get('daily_limit', '?')}")
                    print(f"  Monthly requests: {current_limits.get('monthly_requests', 0)}/{api_stats.get('monthly_limit', '?')}")
            
            # Draft statistics
            draft_count = self.draft_manager.get_draft_count()
            print(f"📝 Pending drafts: {draft_count}")
            
            # Database type
            db_type = db_config._get_db_type()
            db_url = db_config._get_database_url()
            print(f"🗄️  Database: {db_type}")
            if 'sqlite' in db_url.lower():
                print(f"   Location: {db_url}")
            
        except Exception as e:
            logger.error(f"Error showing database status: {str(e)}")
            print("❌ Error retrieving database status")

def main():
    import sys
    
    bot = DatabaseTwitterTranslationBot()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'once':
            bot.run_once()
        elif command == 'drafts':
            bot.draft_manager.display_pending_drafts()
        elif command == 'status':
            bot.show_database_status()
        elif command == 'cache':
            cache_monitor.print_performance_summary()
        elif command == 'test':
            logger.info("🧪 Testing API connections and database...")
            if settings.validate_credentials():
                # Test database
                if bot._check_database_health():
                    logger.info("✅ Database connection successful")
                else:
                    logger.error("❌ Database connection failed")
                
                # Test Twitter API
                twitter_publisher.test_connections()
            else:
                logger.error("❌ Cannot test connections - missing API credentials")
        elif command == 'migrate':
            logger.info("🔄 Running database migrations...")
            try:
                import subprocess
                result = subprocess.run(['alembic', 'upgrade', 'head'], 
                                      capture_output=True, text=True, cwd='.')
                if result.returncode == 0:
                    logger.info("✅ Database migrations completed successfully")
                else:
                    logger.error(f"❌ Migration failed: {result.stderr}")
            except Exception as e:
                logger.error(f"❌ Error running migrations: {str(e)}")
        elif command == 'setup':
            logger.info("🛠️ Setting up database...")
            try:
                import subprocess
                result = subprocess.run(['python', 'setup_db.py'], 
                                      capture_output=True, text=True, cwd='.')
                if result.returncode == 0:
                    logger.info("✅ Database setup completed")
                    print(result.stdout)
                else:
                    logger.error(f"❌ Database setup failed: {result.stderr}")
            except Exception as e:
                logger.error(f"❌ Error setting up database: {str(e)}")
        else:
            print("Usage: python main_database.py [once|drafts|status|cache|test|migrate|setup]")
            print("  once    - Run once and exit")
            print("  drafts  - Show pending drafts")
            print("  status  - Show database and API usage status")
            print("  cache   - Show translation cache performance")
            print("  test    - Test API connections and database")
            print("  migrate - Run database migrations")
            print("  setup   - Initialize database")
            print("  (no args) - Run continuously on schedule")
    else:
        bot.run_scheduled()

if __name__ == "__main__":
    main()
