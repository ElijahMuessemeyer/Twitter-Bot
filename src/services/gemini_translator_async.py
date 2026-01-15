# =============================================================================
# ASYNC GEMINI TRANSLATION SERVICE
# =============================================================================
# High-performance async version with batch processing and connection pooling

import asyncio
import aiohttp
import google.generativeai as genai
from typing import Dict, Optional, List, Tuple
import time
import json
from concurrent.futures import ThreadPoolExecutor
from ..config.settings import settings
from ..utils.logger import logger
from ..utils.structured_logger import structured_logger, log_translation_cached, log_gemini_api_call
from ..utils.text_processor import text_processor
from ..utils.prompt_builder import prompt_builder
from ..utils.translation_cache import translation_cache
from ..utils.performance_monitor import performance_monitor
from ..models.tweet import Translation, Tweet
from datetime import datetime

class AsyncGeminiTranslator:
    def __init__(self):
        self.model = None
        self.client_initialized = False
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Initialize Gemini client
        if settings.GOOGLE_API_KEY and not settings.GOOGLE_API_KEY.startswith('your_'):
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
            self.client_initialized = True
            logger.info(f"✅ Async Gemini API initialized with model: {settings.GEMINI_MODEL}")
        else:
            logger.warning("⚠️ Google Gemini API key not configured")
        
        # Use intelligent caching system
        self.cache = translation_cache
        
        # Thread pool for CPU-intensive operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Batch processing configuration
        self.batch_size = 5
        self.batch_timeout = 2.0  # seconds
        self.pending_translations = {}
        
        # Performance tracking
        self._translation_times = []
        self._cache_hits = 0
        self._cache_misses = 0
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def initialize(self):
        """Initialize async components"""
        # Setup connection pool for HTTP requests
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=aiohttp.TCPConnector(
                limit=50,
                limit_per_host=20,
                keepalive_timeout=60
            )
        )
        logger.info("✅ Async Gemini translator initialized")
    
    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
        self.executor.shutdown(wait=True)
    
    async def translate_tweet(self, tweet: Tweet, target_language: str, language_config: dict = None) -> Optional[Translation]:
        """
        Async translate a single tweet with performance monitoring
        """
        if not self.client_initialized:
            logger.error("❌ Gemini API not initialized")
            return None
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            with performance_monitor.track_operation(f"gemini_translate_{target_language}"):
                # Check cache first
                cached_translation = await self._check_cache_async(tweet.text, target_language, language_config)
                
                if cached_translation:
                    self._cache_hits += 1
                    duration = (asyncio.get_event_loop().time() - start_time) * 1000
                    
                    structured_logger.log_translation_success(
                        tweet_id=tweet.id,
                        target_language=target_language,
                        character_count=cached_translation.character_count,
                        cache_hit=True,
                        duration_ms=duration
                    )
                    
                    cached_translation.original_tweet = tweet
                    return cached_translation
                
                # Perform translation
                translation = await self._translate_single(tweet, target_language, language_config)
                
                if translation:
                    self._cache_misses += 1
                    # Cache the result
                    await self._cache_translation_async(tweet.text, target_language, translation, language_config)
                
                duration = (asyncio.get_event_loop().time() - start_time) * 1000
                self._translation_times.append(duration)
                
                performance_monitor.record_api_call(
                    service="gemini",
                    operation="translate",
                    duration_ms=duration,
                    success=translation is not None,
                    response_size=len(translation.translated_text) if translation else 0
                )
                
                return translation
                
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start_time) * 1000
            performance_monitor.record_api_call(
                service="gemini",
                operation="translate",
                duration_ms=duration,
                success=False,
                error=str(e)
            )
            logger.error(f"❌ Translation failed: {str(e)}")
            return None
    
    async def translate_batch(self, tweets: List[Tweet], languages: List[dict]) -> Dict[str, List[Translation]]:
        """
        Batch translate multiple tweets to multiple languages concurrently
        """
        if not self.client_initialized or not tweets or not languages:
            return {}
        
        results = {lang['code']: [] for lang in languages}
        
        # Create translation tasks
        tasks = []
        for tweet in tweets:
            for lang_config in languages:
                task = asyncio.create_task(
                    self.translate_tweet(tweet, lang_config['name'], lang_config),
                    name=f"translate_{tweet.id}_{lang_config['code']}"
                )
                tasks.append((task, tweet, lang_config))
        
        # Execute all translations concurrently with progress tracking
        completed = 0
        total = len(tasks)
        
        logger.info(f"🔄 Starting batch translation: {len(tweets)} tweets × {len(languages)} languages = {total} translations")
        
        for task, tweet, lang_config in tasks:
            try:
                translation = await task
                if translation:
                    results[lang_config['code']].append(translation)
                
                completed += 1
                if completed % 5 == 0:  # Progress update every 5 completions
                    logger.info(f"📊 Batch progress: {completed}/{total} translations completed")
                    
            except Exception as e:
                logger.error(f"❌ Batch translation failed for tweet {tweet.id} -> {lang_config['code']}: {str(e)}")
        
        logger.info(f"✅ Batch translation completed: {completed}/{total} successful")
        return results
    
    async def translate_concurrent(self, tweet: Tweet, target_languages: List[dict]) -> List[Translation]:
        """
        Translate a single tweet to multiple languages concurrently
        """
        if not self.client_initialized or not target_languages:
            return []
        
        # Create concurrent translation tasks
        tasks = [
            asyncio.create_task(
                self.translate_tweet(tweet, lang_config['name'], lang_config),
                name=f"translate_{tweet.id}_{lang_config['code']}"
            )
            for lang_config in target_languages
        ]
        
        # Wait for all translations to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and None results
        successful_translations = []
        for i, result in enumerate(results):
            if isinstance(result, Translation):
                successful_translations.append(result)
            elif isinstance(result, Exception):
                lang_code = target_languages[i]['code']
                logger.error(f"❌ Concurrent translation failed for {lang_code}: {str(result)}")
        
        logger.info(f"📊 Concurrent translation: {len(successful_translations)}/{len(target_languages)} successful")
        return successful_translations
    
    async def _check_cache_async(self, text: str, target_language: str, language_config: dict) -> Optional[Translation]:
        """Check cache asynchronously"""
        return await asyncio.to_thread(
            self.cache.get,
            text, target_language, language_config
        )
    
    async def _cache_translation_async(self, text: str, target_language: str, translation: Translation, language_config: dict):
        """Cache translation asynchronously"""
        await asyncio.to_thread(
            self.cache.put,
            text, target_language, translation, language_config
        )
    
    async def _translate_single(self, tweet: Tweet, target_language: str, language_config: dict = None) -> Optional[Translation]:
        """Perform single translation with async processing"""
        try:
            # Extract preservable elements
            clean_text, placeholder_map = await asyncio.to_thread(
                text_processor.extract_preservable_elements,
                tweet.text
            )
            
            # Build prompt
            prompt = await asyncio.to_thread(
                prompt_builder.build_translation_prompt,
                clean_text, target_language, language_config
            )
            
            # Log translation start
            structured_logger.info(
                f"Starting Gemini API translation: {tweet.id} -> {target_language}",
                event="gemini_api_start",
                tweet_id=tweet.id,
                target_language=target_language,
                prompt_length=len(prompt),
                cache_miss=True
            )
            
            # Make API call using thread executor to avoid blocking
            api_start_time = asyncio.get_event_loop().time()
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt
            )
            api_duration_ms = (asyncio.get_event_loop().time() - api_start_time) * 1000
            
            if not response.text:
                structured_logger.log_translation_failure(
                    tweet_id=tweet.id,
                    target_language=target_language,
                    error_type="empty_response",
                    error_message="Gemini API returned empty response"
                )
                return None
            
            translated_text = response.text.strip()
            
            # Restore preservable elements
            final_translation = await asyncio.to_thread(
                text_processor.restore_preservable_elements,
                translated_text, placeholder_map
            )
            
            # Create Translation object
            translation = Translation(
                original_tweet=tweet,
                target_language=target_language,
                translated_text=final_translation,
                translation_timestamp=datetime.now(),
                character_count=text_processor.get_character_count(final_translation),
                status='pending'
            )
            
            # Validate character count and shorten if needed
            if not text_processor.is_within_twitter_limit(final_translation):
                logger.warning(f"Translation exceeds character limit: {translation.character_count} chars")
                translation = await self._get_shorter_translation_async(tweet, target_language, language_config, final_translation)
            
            # Log successful translation
            structured_logger.log_translation_success(
                tweet_id=tweet.id,
                target_language=target_language,
                character_count=translation.character_count,
                cache_hit=False,
                duration_ms=api_duration_ms
            )
            
            # Log API call details
            log_gemini_api_call(
                tweet_id=tweet.id,
                target_language=target_language,
                prompt_tokens=len(prompt.split()),
                response_tokens=len(translated_text.split()),
                duration_ms=api_duration_ms
            )
            
            return translation
            
        except Exception as e:
            structured_logger.log_translation_failure(
                tweet_id=tweet.id,
                target_language=target_language,
                error_type=type(e).__name__,
                error_message=str(e)
            )
            return None
    
    async def _get_shorter_translation_async(self, tweet: Tweet, target_language: str, language_config: dict, current_translation: str) -> Translation:
        """Get a shorter version of the translation asynchronously"""
        try:
            shorter_prompt = await asyncio.to_thread(
                prompt_builder.build_shortening_prompt,
                tweet.text, current_translation, target_language
            )
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                shorter_prompt
            )
            
            if not response.text:
                logger.warning(f"⚠️ Empty response from Gemini API for shortening, using original")
                shorter_text = current_translation
            else:
                shorter_text = response.text.strip()
            
            return Translation(
                original_tweet=tweet,
                target_language=target_language,
                translated_text=shorter_text,
                translation_timestamp=datetime.now(),
                character_count=text_processor.get_character_count(shorter_text),
                status='pending'
            )
            
        except Exception as e:
            logger.error(f"❌ Error getting shorter translation: {str(e)}")
            # Return original translation even if too long
            return Translation(
                original_tweet=tweet,
                target_language=target_language,
                translated_text=current_translation,
                translation_timestamp=datetime.now(),
                character_count=text_processor.get_character_count(current_translation),
                status='pending'
            )
    
    def get_performance_metrics(self) -> dict:
        """Get translation performance metrics"""
        total_requests = self._cache_hits + self._cache_misses
        cache_hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        avg_time = sum(self._translation_times) / len(self._translation_times) if self._translation_times else 0
        
        return {
            'total_translations': total_requests,
            'cache_hit_rate': cache_hit_rate,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'avg_translation_time_ms': avg_time,
            'min_translation_time_ms': min(self._translation_times) if self._translation_times else 0,
            'max_translation_time_ms': max(self._translation_times) if self._translation_times else 0
        }
    
    async def preload_common_translations_async(self, patterns: dict):
        """Preload cache with common translation patterns asynchronously"""
        await asyncio.to_thread(
            self.cache.preload_common_translations,
            patterns
        )
    
    def get_cache_metrics(self) -> dict:
        """Get cache performance metrics"""
        return self.cache.get_cache_info()

# Global async translator instance (lazy initialization)
gemini_translator_async = None

def get_gemini_translator_async():
    """Get or create the global async translator instance"""
    global gemini_translator_async
    if gemini_translator_async is None:
        gemini_translator_async = AsyncGeminiTranslator()
    return gemini_translator_async
