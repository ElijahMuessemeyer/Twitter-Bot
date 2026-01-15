# =============================================================================
# STRUCTURED JSON LOGGING SYSTEM
# =============================================================================
# Added by: AI Assistant on 2025-01-18
# Purpose: Professional structured logging with JSON output for better monitoring
#
# Features:
# - JSON-formatted logs for machine readability
# - Structured events with metadata
# - Performance timing and metrics
# - Error classification and context
# - Dual output: JSON files + human-readable console
# - Integration with existing logger without breaking changes
# =============================================================================

import json
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Union
from pathlib import Path
from contextlib import contextmanager

class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs JSON structured logs"""
    
    def __init__(self):
        super().__init__()
        self.hostname = "twitter-bot"
        
    def format(self, record):
        """Format log record as JSON structure"""
        # Base log structure
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": threading.current_thread().name,
            "hostname": self.hostname
        }
        
        # Add structured data if available
        if hasattr(record, 'structured_data'):
            log_entry.update(record.structured_data)
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info else None
            }
        
        return json.dumps(log_entry, ensure_ascii=False)

class StructuredLogger:
    """
    Enhanced logger that supports both traditional and structured JSON logging
    
    Provides rich context and metadata for better monitoring and debugging
    """
    
    def __init__(self, name="twitter_bot", enable_json=True):
        self.logger_name = name
        self.enable_json = enable_json
        
        # Create logs directory
        Path("logs").mkdir(exist_ok=True)
        
        # Set up base logger
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:  # Avoid duplicate handlers
            self._setup_handlers()
        
        # Performance tracking
        self._operation_times = {}
        
    def _setup_handlers(self):
        """Set up logging handlers for both JSON and human-readable output"""
        self.logger.setLevel(logging.INFO)
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        if self.enable_json:
            # JSON file handler for machine processing
            json_handler = logging.FileHandler(f'logs/twitter_bot_{today}.json')
            json_handler.setLevel(logging.INFO)
            json_handler.setFormatter(StructuredFormatter())
            self.logger.addHandler(json_handler)
        
        # Human-readable file handler
        text_handler = logging.FileHandler(f'logs/twitter_bot_{today}.log')
        text_handler.setLevel(logging.INFO)
        text_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        text_handler.setFormatter(text_formatter)
        self.logger.addHandler(text_handler)
        
        # Console handler (human-readable)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(text_formatter)
        self.logger.addHandler(console_handler)
    
    def _create_structured_record(self, level: str, message: str, **structured_data):
        """Create a log record with structured data"""
        # Clean and enrich structured data
        enriched_data = {
            "event_id": f"{int(time.time() * 1000)}_{threading.current_thread().ident}",
            "service": "twitter_bot",
            **structured_data
        }
        
        # Create log record
        record = self.logger.makeRecord(
            name=self.logger.name,
            level=getattr(logging, level.upper()),
            fn='',
            lno=0,
            msg=message,
            args=(),
            exc_info=None
        )
        
        # Attach structured data
        record.structured_data = enriched_data
        
        return record
    
    def info(self, message: str, **structured_data):
        """Log info message with optional structured data"""
        if structured_data:
            record = self._create_structured_record("INFO", message, **structured_data)
            self.logger.handle(record)
        else:
            self.logger.info(message)
    
    def warning(self, message: str, **structured_data):
        """Log warning message with optional structured data"""
        if structured_data:
            record = self._create_structured_record("WARNING", message, **structured_data)
            self.logger.handle(record)
        else:
            self.logger.warning(message)
    
    def error(self, message: str, **structured_data):
        """Log error message with optional structured data"""
        if structured_data:
            record = self._create_structured_record("ERROR", message, **structured_data)
            self.logger.handle(record)
        else:
            self.logger.error(message)
    
    def debug(self, message: str, **structured_data):
        """Log debug message with optional structured data"""
        if structured_data:
            record = self._create_structured_record("DEBUG", message, **structured_data)
            self.logger.handle(record)
        else:
            self.logger.debug(message)
    
    # Structured logging methods for specific events
    
    def log_tweet_processing(self, tweet_id: str, text_preview: str, language_count: int):
        """Log tweet processing start"""
        self.info(
            f"Processing tweet {tweet_id}",
            event="tweet_processing_start",
            tweet_id=tweet_id,
            text_preview=text_preview[:50],
            target_language_count=language_count,
            text_length=len(text_preview)
        )
    
    def log_translation_success(self, tweet_id: str, target_language: str, 
                               character_count: int, cache_hit: bool, 
                               duration_ms: float):
        """Log successful translation"""
        self.info(
            f"Translation completed: {tweet_id} -> {target_language}",
            event="translation_success",
            tweet_id=tweet_id,
            target_language=target_language,
            character_count=character_count,
            cache_hit=cache_hit,
            duration_ms=round(duration_ms, 2),
            api_call_saved=cache_hit
        )
    
    def log_translation_failure(self, tweet_id: str, target_language: str, 
                               error_type: str, error_message: str):
        """Log translation failure"""
        self.error(
            f"Translation failed: {tweet_id} -> {target_language}",
            event="translation_failed",
            tweet_id=tweet_id,
            target_language=target_language,
            error_type=error_type,
            error_message=error_message
        )
    
    def log_post_success(self, tweet_id: str, target_language: str, 
                        post_id: str, character_count: int):
        """Log successful post to Twitter"""
        self.info(
            f"Tweet posted successfully: {post_id}",
            event="post_success",
            original_tweet_id=tweet_id,
            target_language=target_language,
            posted_tweet_id=post_id,
            character_count=character_count
        )
    
    def log_post_failure(self, tweet_id: str, target_language: str, 
                        error_type: str, retry_after: Optional[int] = None):
        """Log failed post to Twitter"""
        self.warning(
            f"Post failed: {tweet_id} -> {target_language}",
            event="post_failed",
            original_tweet_id=tweet_id,
            target_language=target_language,
            error_type=error_type,
            retry_after_seconds=retry_after,
            saved_as_draft=True
        )
    
    def log_cache_performance(self, hit_rate: float, total_requests: int, 
                             cache_size: int, memory_mb: float):
        """Log cache performance metrics"""
        self.info(
            f"Cache performance: {hit_rate:.1f}% hit rate",
            event="cache_performance",
            hit_rate_percent=round(hit_rate, 2),
            total_requests=total_requests,
            cache_size=cache_size,
            memory_usage_mb=round(memory_mb, 2)
        )
    
    def log_api_usage(self, daily_requests: int, daily_limit: int, 
                     monthly_posts: int, monthly_limit: int):
        """Log API usage statistics"""
        self.info(
            f"API usage: {daily_requests}/{daily_limit} daily, {monthly_posts}/{monthly_limit} monthly",
            event="api_usage_status",
            daily_requests=daily_requests,
            daily_limit=daily_limit,
            daily_usage_percent=round((daily_requests / daily_limit) * 100, 1),
            monthly_posts=monthly_posts,
            monthly_limit=monthly_limit,
            monthly_usage_percent=round((monthly_posts / monthly_limit) * 100, 1)
        )
    
    def log_draft_saved(self, tweet_id: str, target_language: str, reason: str):
        """Log when translation is saved as draft"""
        self.info(
            f"Translation saved as draft: {tweet_id} -> {target_language}",
            event="draft_saved",
            original_tweet_id=tweet_id,
            target_language=target_language,
            reason=reason
        )
    
    def log_bot_lifecycle(self, event: str, **metadata):
        """Log bot lifecycle events (start, stop, error)"""
        self.info(
            f"Bot lifecycle: {event}",
            event=f"bot_{event}",
            **metadata
        )
    
    @contextmanager
    def time_operation(self, operation_name: str, **context):
        """Context manager to time operations and log performance"""
        start_time = time.time()
        operation_id = f"{operation_name}_{int(start_time * 1000)}"
        
        self.debug(
            f"Operation started: {operation_name}",
            event="operation_start",
            operation=operation_name,
            operation_id=operation_id,
            **context
        )
        
        try:
            yield operation_id
            duration_ms = (time.time() - start_time) * 1000
            
            self.info(
                f"Operation completed: {operation_name} ({duration_ms:.2f}ms)",
                event="operation_completed",
                operation=operation_name,
                operation_id=operation_id,
                duration_ms=round(duration_ms, 2),
                success=True,
                **context
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.error(
                f"Operation failed: {operation_name} after {duration_ms:.2f}ms",
                event="operation_failed", 
                operation=operation_name,
                operation_id=operation_id,
                duration_ms=round(duration_ms, 2),
                success=False,
                error_type=type(e).__name__,
                error_message=str(e),
                **context
            )
            raise

class JSONLogAnalyzer:
    """Utility for analyzing structured JSON logs"""
    
    @staticmethod
    def parse_log_file(file_path: str) -> list:
        """Parse JSON log file and return list of log entries"""
        entries = []
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            entries.append(entry)
                        except json.JSONDecodeError:
                            continue  # Skip malformed lines
        except FileNotFoundError:
            pass
        return entries
    
    @staticmethod
    def get_translation_stats(entries: list) -> Dict[str, Any]:
        """Extract translation statistics from log entries"""
        translation_events = [e for e in entries if e.get('event', '').startswith('translation_')]
        
        if not translation_events:
            return {"error": "No translation events found"}
        
        success_events = [e for e in translation_events if e.get('event') == 'translation_success']
        failure_events = [e for e in translation_events if e.get('event') == 'translation_failed']
        
        total_translations = len(success_events) + len(failure_events)
        success_rate = (len(success_events) / total_translations * 100) if total_translations > 0 else 0
        
        # Calculate average duration for API calls (non-cache hits)
        api_durations = [e.get('duration_ms', 0) for e in success_events if not e.get('cache_hit', False)]
        avg_api_duration = sum(api_durations) / len(api_durations) if api_durations else 0
        
        # Calculate cache hit rate
        cache_hits = len([e for e in success_events if e.get('cache_hit', False)])
        cache_hit_rate = (cache_hits / len(success_events) * 100) if success_events else 0
        
        return {
            "total_translations": total_translations,
            "successful_translations": len(success_events),
            "failed_translations": len(failure_events),
            "success_rate_percent": round(success_rate, 2),
            "cache_hit_rate_percent": round(cache_hit_rate, 2),
            "average_api_duration_ms": round(avg_api_duration, 2),
            "languages_processed": list(set(e.get('target_language') for e in success_events if e.get('target_language')))
        }
    
    @staticmethod
    def get_error_summary(entries: list) -> Dict[str, Any]:
        """Analyze error patterns in logs"""
        error_events = [e for e in entries if e.get('level') == 'ERROR']
        
        if not error_events:
            return {"total_errors": 0}
        
        # Group errors by type
        error_types = {}
        for event in error_events:
            error_type = event.get('error_type', 'unknown')
            if error_type not in error_types:
                error_types[error_type] = []
            error_types[error_type].append(event)
        
        # Get most common errors
        error_counts = {error_type: len(events) for error_type, events in error_types.items()}
        
        return {
            "total_errors": len(error_events),
            "error_types": error_counts,
            "most_common_error": max(error_counts.items(), key=lambda x: x[1])[0] if error_counts else None,
            "recent_errors": error_events[-5:]  # Last 5 errors
        }

# Global structured logger instance  
structured_logger = StructuredLogger("twitter_bot", enable_json=True)

# Convenience functions that maintain backward compatibility
def log_info(message: str, **structured_data):
    """Log info with optional structured data"""
    structured_logger.info(message, **structured_data)

def log_warning(message: str, **structured_data):
    """Log warning with optional structured data"""
    structured_logger.warning(message, **structured_data)

def log_error(message: str, **structured_data):
    """Log error with optional structured data"""
    structured_logger.error(message, **structured_data)

# Event-specific logging functions
def log_translation_start(tweet_id: str, target_language: str, cache_check: bool = True):
    """Log start of translation process"""
    structured_logger.info(
        f"Starting translation: {tweet_id} -> {target_language}",
        event="translation_start",
        tweet_id=tweet_id,
        target_language=target_language,
        cache_check_enabled=cache_check
    )

def log_translation_cached(tweet_id: str, target_language: str, access_count: int):
    """Log cache hit for translation"""
    structured_logger.info(
        f"Translation cache hit: {tweet_id} -> {target_language}",
        event="translation_cache_hit",
        tweet_id=tweet_id,
        target_language=target_language,
        cache_access_count=access_count,
        api_call_saved=True
    )

def log_gemini_api_call(tweet_id: str, target_language: str, 
                       prompt_tokens: int, response_tokens: int, 
                       duration_ms: float):
    """Log Gemini API call details"""
    structured_logger.info(
        f"Gemini API call completed: {tweet_id} -> {target_language}",
        event="gemini_api_call",
        tweet_id=tweet_id,
        target_language=target_language,
        prompt_tokens=prompt_tokens,
        response_tokens=response_tokens,
        duration_ms=round(duration_ms, 2),
        estimated_cost_usd=round((prompt_tokens * 0.075 + response_tokens * 0.30) / 1000000, 6)
    )

def log_rate_limit_event(api_service: str, limit_type: str, 
                        retry_after: Optional[int] = None):
    """Log rate limiting events"""
    structured_logger.warning(
        f"Rate limit encountered: {api_service} {limit_type}",
        event="rate_limit_hit",
        api_service=api_service,
        limit_type=limit_type,
        retry_after_seconds=retry_after,
        action="switching_to_draft_mode"
    )

def log_system_health(component: str, status: str, **metrics):
    """Log system health and performance metrics"""
    structured_logger.info(
        f"System health check: {component} is {status}",
        event="health_check",
        component=component,
        status=status,
        **metrics
    )
