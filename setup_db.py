#!/usr/bin/env python3
# =============================================================================
# DATABASE INITIALIZATION AND SETUP SCRIPT
# =============================================================================

import os
import sys
from pathlib import Path
from datetime import datetime
from src.config.database import db_config
from src.repositories import (
    TweetRepository, TranslationRepository, APIUsageRepository,
    UserRepository, CacheRepository, SystemStateRepository
)
from src.utils.logger import logger

def create_database_tables():
    """Create all database tables"""
    try:
        logger.info("Creating database tables...")
        db_config.create_all_tables()
        logger.info("✅ Database tables created successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Error creating database tables: {str(e)}")
        return False

def setup_initial_data():
    """Set up initial data and configuration"""
    try:
        logger.info("Setting up initial data...")
        
        with db_config.get_session() as session:
            # Initialize repositories
            user_repo = UserRepository(session)
            system_state_repo = SystemStateRepository(session)
            
            # Create primary user if doesn't exist
            primary_user = user_repo.get_primary_user()
            if not primary_user:
                logger.info("Creating primary user account...")
                primary_user = user_repo.create_user(
                    account_name="primary_account",
                    account_type="primary",
                    settings={
                        "poll_interval": 300,
                        "max_tweets_per_poll": 10,
                        "auto_post_enabled": True
                    }
                )
                logger.info("✅ Primary user account created")
            
            # Initialize system state
            system_state_repo.set_state(
                key="database_initialized",
                value=True,
                description="Indicates database has been properly initialized",
                state_type="system"
            )
            
            system_state_repo.set_state(
                key="initialization_date",
                value=datetime.now().isoformat(),
                description="Date when database was initialized",
                state_type="system"
            )
            
            session.commit()
            logger.info("✅ Initial data setup completed")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error setting up initial data: {str(e)}")
        return False

def migrate_existing_data():
    """Migrate data from existing file-based storage"""
    try:
        logger.info("Checking for existing data to migrate...")
        
        with db_config.get_session() as session:
            system_state_repo = SystemStateRepository(session)
            api_usage_repo = APIUsageRepository(session)
            
            # Migrate last tweet ID
            last_tweet_file = Path('logs/last_tweet_id.txt')
            if last_tweet_file.exists():
                with open(last_tweet_file, 'r') as f:
                    tweet_id = f.read().strip()
                    if tweet_id:
                        system_state_repo.set_last_tweet_id(tweet_id)
                        logger.info(f"✅ Migrated last tweet ID: {tweet_id}")
            
            # Migrate API usage data
            api_usage_file = Path('logs/api_usage.json')
            if api_usage_file.exists():
                import json
                try:
                    with open(api_usage_file, 'r') as f:
                        usage_data = json.load(f)
                        
                    # Store historical API usage data
                    if 'daily_requests' in usage_data:
                        system_state_repo.set_daily_requests('twitter', usage_data['daily_requests'])
                        logger.info(f"✅ Migrated daily requests: {usage_data['daily_requests']}")
                    
                    if 'monthly_posts' in usage_data:
                        system_state_repo.set_monthly_posts('twitter', usage_data['monthly_posts'])
                        logger.info(f"✅ Migrated monthly posts: {usage_data['monthly_posts']}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Could not parse API usage data: {str(e)}")
            
            # Migrate draft files
            drafts_dir = Path('drafts/pending')
            if drafts_dir.exists():
                draft_count = 0
                for draft_file in drafts_dir.glob('*.json'):
                    try:
                        import json
                        with open(draft_file, 'r', encoding='utf-8') as f:
                            draft_data = json.load(f)
                        
                        # Note: We can't directly migrate drafts without the Tweet and Translation models
                        # This would need to be done after implementing the new data access layer
                        draft_count += 1
                    except Exception as e:
                        logger.warning(f"⚠️ Could not migrate draft {draft_file}: {str(e)}")
                
                if draft_count > 0:
                    logger.info(f"📝 Found {draft_count} draft files - will need manual migration")
            
            session.commit()
            logger.info("✅ Data migration completed")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error migrating existing data: {str(e)}")
        return False

def run_database_health_check():
    """Run health check on database connection"""
    try:
        logger.info("Running database health check...")
        
        if db_config.health_check():
            logger.info("✅ Database health check passed")
            return True
        else:
            logger.error("❌ Database health check failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Database health check error: {str(e)}")
        return False

def main():
    """Main setup function"""
    print("🗄️  Twitter Bot Database Setup")
    print("=" * 40)
    
    # Check database connection
    if not run_database_health_check():
        print("❌ Database connection failed. Please check your configuration.")
        sys.exit(1)
    
    # Create tables
    if not create_database_tables():
        print("❌ Failed to create database tables.")
        sys.exit(1)
    
    # Setup initial data
    if not setup_initial_data():
        print("❌ Failed to setup initial data.")
        sys.exit(1)
    
    # Migrate existing data
    if not migrate_existing_data():
        print("⚠️ Some data migration issues occurred, but setup continued.")
    
    print("\n✅ Database setup completed successfully!")
    print("\nNext steps:")
    print("1. Update your .env file with database credentials if using PostgreSQL")
    print("2. Run 'alembic stamp head' to mark the current migration state")
    print("3. Test the bot with 'python main.py once'")
    print("\nDatabase location:", db_config._get_database_url())

if __name__ == "__main__":
    main()
