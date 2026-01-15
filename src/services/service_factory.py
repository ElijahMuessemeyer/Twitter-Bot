# =============================================================================
# SERVICE FACTORY - CHOOSE BETWEEN FILE-BASED AND DATABASE-BACKED SERVICES
# =============================================================================

import os
from src.utils.logger import logger

def get_draft_manager():
    """Get the appropriate draft manager based on configuration"""
    use_database = os.getenv('USE_DATABASE_SERVICES', 'true').lower() == 'true'
    
    if use_database:
        try:
            from src.services.database_draft_manager import database_draft_manager
            logger.info("Using database-backed draft manager")
            return database_draft_manager
        except Exception as e:
            logger.warning(f"Failed to initialize database draft manager: {str(e)}")
            logger.info("Falling back to file-based draft manager")
    
    # Fallback to file-based
    from draft_manager import draft_manager
    return draft_manager

def get_twitter_monitor():
    """Get the appropriate Twitter monitor based on configuration"""
    use_database = os.getenv('USE_DATABASE_SERVICES', 'true').lower() == 'true'
    
    if use_database:
        try:
            from src.services.database_twitter_monitor import database_twitter_monitor
            logger.info("Using database-backed Twitter monitor")
            return database_twitter_monitor
        except Exception as e:
            logger.warning(f"Failed to initialize database Twitter monitor: {str(e)}")
            logger.info("Falling back to file-based Twitter monitor")
    
    # Fallback to file-based
    from src.services.twitter_monitor import twitter_monitor
    return twitter_monitor

def get_translation_cache():
    """Get the appropriate translation cache based on configuration"""
    use_database = os.getenv('USE_DATABASE_CACHE', 'true').lower() == 'true'
    
    if use_database:
        try:
            from src.utils.database_translation_cache import database_translation_cache
            logger.info("Using database-backed translation cache")
            return database_translation_cache
        except Exception as e:
            logger.warning(f"Failed to initialize database translation cache: {str(e)}")
            logger.info("Falling back to in-memory translation cache")
    
    # Fallback to in-memory cache
    try:
        from src.utils.translation_cache import translation_cache
        return translation_cache
    except ImportError:
        # If no cache is available, return a simple no-op cache
        logger.warning("No translation cache available, using no-op cache")
        return NoOpCache()

class NoOpCache:
    """Simple no-operation cache for fallback"""
    
    def get_translation(self, original_text: str, target_language: str):
        return None
    
    def store_translation(self, *args, **kwargs):
        return True
    
    def get_cache_statistics(self):
        return {'status': 'no-op cache'}
