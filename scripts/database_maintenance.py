#!/usr/bin/env python3
# =============================================================================
# DATABASE MAINTENANCE AND BACKUP SCRIPTS
# =============================================================================

import os
import sys
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.database import db_config
from src.repositories import (
    TweetRepository, TranslationRepository, APIUsageRepository,
    CacheRepository, SystemStateRepository
)
from src.utils.logger import logger

def backup_sqlite_database(backup_dir: str = "backups") -> bool:
    """Create a backup of SQLite database"""
    try:
        db_url = db_config._get_database_url()
        if not db_url.startswith('sqlite'):
            logger.error("Database backup is currently only supported for SQLite")
            return False
        
        # Extract database file path
        db_path = db_url.replace('sqlite:///', '')
        db_file = Path(db_path)
        
        if not db_file.exists():
            logger.error(f"Database file not found: {db_file}")
            return False
        
        # Create backup directory
        backup_path = Path(backup_dir)
        backup_path.mkdir(exist_ok=True)
        
        # Create timestamped backup filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"twitter_bot_backup_{timestamp}.db"
        backup_file = backup_path / backup_filename
        
        # Copy database file
        shutil.copy2(db_file, backup_file)
        
        logger.info(f"✅ Database backed up to: {backup_file}")
        logger.info(f"   Size: {backup_file.stat().st_size / 1024 / 1024:.2f} MB")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error backing up database: {str(e)}")
        return False

def cleanup_old_data():
    """Clean up old data from database tables"""
    try:
        logger.info("🧹 Starting database cleanup...")
        
        with db_config.get_session() as session:
            # Initialize repositories
            tweet_repo = TweetRepository(session)
            translation_repo = TranslationRepository(session)
            api_usage_repo = APIUsageRepository(session)
            cache_repo = CacheRepository(session)
            system_state_repo = SystemStateRepository(session)
            
            total_cleaned = 0
            
            # Clean up old tweets (older than 90 days)
            logger.info("Cleaning up old tweets...")
            deleted_tweets = tweet_repo.delete_old_tweets(days_old=90)
            logger.info(f"  Removed {deleted_tweets} old tweets")
            total_cleaned += deleted_tweets
            
            # Clean up old failed translations (older than 30 days)
            logger.info("Cleaning up old failed translations...")
            deleted_translations = translation_repo.cleanup_old_failed_translations(days_old=30)
            logger.info(f"  Removed {deleted_translations} old failed translations")
            total_cleaned += deleted_translations
            
            # Clean up old API usage logs (older than 90 days)
            logger.info("Cleaning up old API usage logs...")
            deleted_api_logs = api_usage_repo.cleanup_old_logs(days_old=90)
            logger.info(f"  Removed {deleted_api_logs} old API logs")
            total_cleaned += deleted_api_logs
            
            # Clean up expired cache entries
            logger.info("Cleaning up expired cache entries...")
            deleted_cache = cache_repo.cleanup_expired_entries()
            logger.info(f"  Removed {deleted_cache} expired cache entries")
            total_cleaned += deleted_cache
            
            # Clean up old system state entries
            logger.info("Cleaning up old system states...")
            deleted_states = system_state_repo.cleanup_old_states(days_old=30)
            logger.info(f"  Removed {deleted_states} old system states")
            total_cleaned += deleted_states
            
            session.commit()
            
            logger.info(f"✅ Database cleanup completed. Total items removed: {total_cleaned}")
            return total_cleaned
            
    except Exception as e:
        logger.error(f"❌ Error during database cleanup: {str(e)}")
        return 0

def vacuum_database():
    """Optimize database (SQLite VACUUM)"""
    try:
        logger.info("🔧 Optimizing database...")
        
        db_url = db_config._get_database_url()
        if not db_url.startswith('sqlite'):
            logger.info("Database optimization is currently only supported for SQLite")
            return True
        
        # Get database size before
        db_path = db_url.replace('sqlite:///', '')
        db_file = Path(db_path)
        size_before = db_file.stat().st_size / 1024 / 1024 if db_file.exists() else 0
        
        # Run VACUUM
        with db_config.get_session() as session:
            session.execute("VACUUM")
            session.commit()
        
        # Get database size after
        size_after = db_file.stat().st_size / 1024 / 1024 if db_file.exists() else 0
        space_saved = size_before - size_after
        
        logger.info(f"✅ Database optimized")
        logger.info(f"   Size before: {size_before:.2f} MB")
        logger.info(f"   Size after: {size_after:.2f} MB")
        logger.info(f"   Space saved: {space_saved:.2f} MB")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error optimizing database: {str(e)}")
        return False

def generate_database_report():
    """Generate a comprehensive database usage report"""
    try:
        logger.info("📊 Generating database report...")
        
        with db_config.get_session() as session:
            tweet_repo = TweetRepository(session)
            translation_repo = TranslationRepository(session)
            api_usage_repo = APIUsageRepository(session)
            cache_repo = CacheRepository(session)
            system_state_repo = SystemStateRepository(session)
            
            # Get statistics
            tweet_stats = tweet_repo.get_tweet_statistics()
            translation_stats = translation_repo.get_translation_statistics()
            api_overview = api_usage_repo.get_service_overview()
            cache_stats = cache_repo.get_cache_statistics()
            state_stats = system_state_repo.get_state_statistics()
            
            # Generate report
            report = f"""
# Twitter Bot Database Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Database: {db_config._get_db_type()}

## Tweet Statistics
- Total tweets: {tweet_stats.get('total_tweets', 0)}
- Recent tweets (24h): {tweet_stats.get('recent_tweets_24h', 0)}
- Average character count: {tweet_stats.get('average_character_count', 0)}
- Top author: {tweet_stats.get('top_author', 'N/A')} ({tweet_stats.get('top_author_count', 0)} tweets)

## Translation Statistics
- Total translations: {translation_stats.get('total_translations', 0)}
- Recent translations (24h): {translation_stats.get('recent_translations_24h', 0)}
- Success rate: {translation_stats.get('success_rate', 0)}%
- Status breakdown:
"""
            
            # Add status breakdown
            status_counts = translation_stats.get('status_counts', {})
            for status, count in status_counts.items():
                report += f"  - {status.title()}: {count}\n"
            
            report += f"""
## Language Breakdown
"""
            language_counts = translation_stats.get('language_counts', {})
            for lang, count in language_counts.items():
                report += f"  - {lang}: {count}\n"
            
            report += f"""
## API Usage Overview
"""
            for service, stats in api_overview.items():
                daily_usage = stats.get('daily_usage', {})
                report += f"- {service.title()}:\n"
                report += f"  - Daily requests: {daily_usage.get('total_calls', 0)}\n"
                report += f"  - Success rate: {daily_usage.get('success_rate', 0)}%\n"
                report += f"  - Monthly total: {stats.get('monthly_total', 0)}\n"
            
            report += f"""
## Cache Performance
- Total entries: {cache_stats.get('total_entries', 0)}
- Active entries: {cache_stats.get('active_entries', 0)}
- Expired entries: {cache_stats.get('expired_entries', 0)}
- Estimated hit rate: {cache_stats.get('estimated_hit_rate', 0)}%
- Total accesses: {cache_stats.get('total_accesses', 0)}

## System State
- Total states: {state_stats.get('total_states', 0)}
- States by type:
"""
            
            states_by_type = state_stats.get('states_by_type', {})
            for state_type, count in states_by_type.items():
                report += f"  - {state_type}: {count}\n"
            
            # Save report to file
            report_file = Path(f"database_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
            with open(report_file, 'w') as f:
                f.write(report)
            
            logger.info(f"✅ Database report generated: {report_file}")
            print(report)
            
            return str(report_file)
            
    except Exception as e:
        logger.error(f"❌ Error generating database report: {str(e)}")
        return None

def restore_database(backup_file: str) -> bool:
    """Restore database from backup (SQLite only)"""
    try:
        db_url = db_config._get_database_url()
        if not db_url.startswith('sqlite'):
            logger.error("Database restore is currently only supported for SQLite")
            return False
        
        backup_path = Path(backup_file)
        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_file}")
            return False
        
        # Extract database file path
        db_path = db_url.replace('sqlite:///', '')
        db_file = Path(db_path)
        
        # Create backup of current database
        if db_file.exists():
            backup_current = f"{db_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(db_file, backup_current)
            logger.info(f"Current database backed up to: {backup_current}")
        
        # Restore from backup
        shutil.copy2(backup_path, db_file)
        
        logger.info(f"✅ Database restored from: {backup_file}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error restoring database: {str(e)}")
        return False

def main():
    """Main maintenance function"""
    if len(sys.argv) < 2:
        print("Usage: python database_maintenance.py [backup|cleanup|vacuum|report|restore]")
        print("  backup  - Create database backup")
        print("  cleanup - Clean up old data")
        print("  vacuum  - Optimize database")
        print("  report  - Generate usage report")
        print("  restore - Restore from backup (requires backup file path)")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == 'backup':
        backup_sqlite_database()
    elif command == 'cleanup':
        cleanup_old_data()
    elif command == 'vacuum':
        vacuum_database()
    elif command == 'report':
        generate_database_report()
    elif command == 'restore':
        if len(sys.argv) < 3:
            logger.error("❌ Restore requires backup file path")
            sys.exit(1)
        restore_database(sys.argv[2])
    elif command == 'full':
        # Full maintenance: backup, cleanup, vacuum
        logger.info("🔧 Running full database maintenance...")
        backup_sqlite_database()
        cleanup_old_data()
        vacuum_database()
        logger.info("✅ Full maintenance completed")
    else:
        logger.error(f"❌ Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
