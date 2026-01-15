# =============================================================================
# STRUCTURED LOGGING TESTS
# =============================================================================

import pytest
import sys
import os
import json
import time
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils.structured_logger import (
    StructuredLogger, StructuredFormatter, JSONLogAnalyzer,
    structured_logger, log_translation_cached, log_gemini_api_call
)
from src.models.tweet import Tweet, Translation

class TestStructuredFormatter:
    def setup_method(self):
        """Set up test fixtures"""
        self.formatter = StructuredFormatter()
    
    def test_basic_json_formatting(self):
        """Test basic JSON log formatting"""
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        formatted = self.formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test message"
        assert log_data["logger"] == "test_logger"
        assert log_data["line"] == 42
        assert "timestamp" in log_data
        assert "hostname" in log_data
    
    def test_structured_data_inclusion(self):
        """Test that structured data is included in JSON output"""
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Add structured data
        record.structured_data = {
            "event": "test_event",
            "tweet_id": "123456",
            "target_language": "Spanish",
            "duration_ms": 1250.5
        }
        
        formatted = self.formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["event"] == "test_event"
        assert log_data["tweet_id"] == "123456"
        assert log_data["target_language"] == "Spanish"
        assert log_data["duration_ms"] == 1250.5
    
    def test_exception_formatting(self):
        """Test exception information in JSON logs"""
        try:
            raise ValueError("Test exception")
        except ValueError:
            record = logging.LogRecord(
                name="test_logger",
                level=logging.ERROR,
                pathname="test.py",
                lineno=42,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info()
            )
        
        formatted = self.formatter.format(record)
        log_data = json.loads(formatted)
        
        assert "exception" in log_data
        assert log_data["exception"]["type"] == "ValueError"
        assert log_data["exception"]["message"] == "Test exception"
        assert "traceback" in log_data["exception"]

class TestStructuredLogger:
    def setup_method(self):
        """Set up test fixtures"""
        # Create temporary log directory for testing
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_logs_dir = Path("logs")
        
        # Mock the logs directory to use temp directory
        with patch('src.utils.structured_logger.Path') as mock_path:
            mock_path.return_value = self.temp_dir
            self.test_logger = StructuredLogger("test_bot", enable_json=True)
    
    def teardown_method(self):
        """Clean up test files"""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_structured_logger_initialization(self):
        """Test structured logger initialization"""
        logger = StructuredLogger("test_logger", enable_json=True)
        
        assert logger.logger_name == "test_logger"
        assert logger.enable_json == True
        assert hasattr(logger, '_operation_times')
    
    def test_info_with_structured_data(self):
        """Test info logging with structured data"""
        with patch.object(self.test_logger.logger, 'handle') as mock_handle:
            self.test_logger.info(
                "Test message",
                event="test_event",
                tweet_id="123456",
                target_language="Spanish"
            )
            
            mock_handle.assert_called_once()
            record = mock_handle.call_args[0][0]
            
            assert hasattr(record, 'structured_data')
            assert record.structured_data['event'] == "test_event"
            assert record.structured_data['tweet_id'] == "123456"
            assert record.structured_data['target_language'] == "Spanish"
            assert 'event_id' in record.structured_data
            assert 'service' in record.structured_data
    
    def test_info_without_structured_data(self):
        """Test traditional info logging still works"""
        with patch.object(self.test_logger.logger, 'info') as mock_info:
            self.test_logger.info("Simple message")
            mock_info.assert_called_once_with("Simple message")
    
    def test_error_with_structured_data(self):
        """Test error logging with structured data"""
        with patch.object(self.test_logger.logger, 'handle') as mock_handle:
            self.test_logger.error(
                "Error occurred",
                event="test_error",
                error_type="TestError",
                tweet_id="123456"
            )
            
            mock_handle.assert_called_once()
            record = mock_handle.call_args[0][0]
            
            assert record.structured_data['event'] == "test_error"
            assert record.structured_data['error_type'] == "TestError"
    
    def test_warning_with_structured_data(self):
        """Test warning logging with structured data"""
        with patch.object(self.test_logger.logger, 'handle') as mock_handle:
            self.test_logger.warning(
                "Warning message",
                event="test_warning",
                retry_after=900
            )
            
            mock_handle.assert_called_once()
            record = mock_handle.call_args[0][0]
            
            assert record.structured_data['event'] == "test_warning"
            assert record.structured_data['retry_after'] == 900
    
    def test_tweet_processing_logging(self):
        """Test tweet processing structured logging"""
        with patch.object(self.test_logger, 'info') as mock_info:
            self.test_logger.log_tweet_processing(
                tweet_id="123456",
                text_preview="Hello world! This is a test tweet...",
                language_count=3
            )
            
            mock_info.assert_called_once()
            call_args, call_kwargs = mock_info.call_args
            
            assert "Processing tweet 123456" in call_args[0]
            assert call_kwargs['event'] == "tweet_processing_start"
            assert call_kwargs['tweet_id'] == "123456"
            assert call_kwargs['target_language_count'] == 3
    
    def test_translation_success_logging(self):
        """Test translation success structured logging"""
        with patch.object(self.test_logger, 'info') as mock_info:
            self.test_logger.log_translation_success(
                tweet_id="123456",
                target_language="Spanish",
                character_count=45,
                cache_hit=True,
                duration_ms=1.5
            )
            
            mock_info.assert_called_once()
            call_args, call_kwargs = mock_info.call_args
            
            assert "Translation completed" in call_args[0]
            assert call_kwargs['event'] == "translation_success"
            assert call_kwargs['cache_hit'] == True
            assert call_kwargs['duration_ms'] == 1.5
            assert call_kwargs['api_call_saved'] == True
    
    def test_translation_failure_logging(self):
        """Test translation failure structured logging"""
        with patch.object(self.test_logger, 'error') as mock_error:
            self.test_logger.log_translation_failure(
                tweet_id="123456",
                target_language="Spanish",
                error_type="GeminiAPIError",
                error_message="API quota exceeded"
            )
            
            mock_error.assert_called_once()
            call_args, call_kwargs = mock_error.call_args
            
            assert "Translation failed" in call_args[0]
            assert call_kwargs['event'] == "translation_failed"
            assert call_kwargs['error_type'] == "GeminiAPIError"
            assert call_kwargs['error_message'] == "API quota exceeded"
    
    def test_time_operation_context_manager_success(self):
        """Test operation timing context manager for successful operations"""
        with patch.object(self.test_logger, 'debug') as mock_debug:
            with patch.object(self.test_logger, 'info') as mock_info:
                with self.test_logger.time_operation("test_operation", test_param="value"):
                    time.sleep(0.01)  # Simulate work
                
                # Should log operation start and completion
                mock_debug.assert_called_once()
                mock_info.assert_called_once()
                
                # Check completion log
                call_args, call_kwargs = mock_info.call_args
                assert "Operation completed" in call_args[0]
                assert call_kwargs['event'] == "operation_completed"
                assert call_kwargs['operation'] == "test_operation"
                assert call_kwargs['success'] == True
                assert call_kwargs['duration_ms'] > 0
                assert call_kwargs['test_param'] == "value"
    
    def test_time_operation_context_manager_failure(self):
        """Test operation timing context manager for failed operations"""
        with patch.object(self.test_logger, 'debug') as mock_debug:
            with patch.object(self.test_logger, 'error') as mock_error:
                with pytest.raises(ValueError):
                    with self.test_logger.time_operation("failing_operation"):
                        raise ValueError("Test error")
                
                # Should log operation start and failure
                mock_debug.assert_called_once()
                mock_error.assert_called_once()
                
                # Check failure log
                call_args, call_kwargs = mock_error.call_args
                assert "Operation failed" in call_args[0]
                assert call_kwargs['event'] == "operation_failed"
                assert call_kwargs['success'] == False
                assert call_kwargs['error_type'] == "ValueError"
                assert call_kwargs['error_message'] == "Test error"

class TestJSONLogAnalyzer:
    def setup_method(self):
        """Set up test fixtures"""
        self.analyzer = JSONLogAnalyzer()
        
        # Sample log entries for testing
        self.sample_log_entries = [
            {
                "timestamp": "2025-01-18T10:30:00Z",
                "level": "INFO",
                "event": "translation_success",
                "tweet_id": "123",
                "target_language": "Spanish",
                "cache_hit": False,
                "duration_ms": 1200.5
            },
            {
                "timestamp": "2025-01-18T10:30:01Z", 
                "level": "INFO",
                "event": "translation_success",
                "tweet_id": "124",
                "target_language": "French",
                "cache_hit": True,
                "duration_ms": 1.2
            },
            {
                "timestamp": "2025-01-18T10:30:02Z",
                "level": "ERROR",
                "event": "translation_failed",
                "tweet_id": "125",
                "target_language": "German",
                "error_type": "GeminiAPIError"
            }
        ]
    
    def test_parse_log_file_success(self):
        """Test successful log file parsing"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            for entry in self.sample_log_entries:
                f.write(json.dumps(entry) + '\n')
            temp_file = f.name
        
        try:
            entries = self.analyzer.parse_log_file(temp_file)
            
            assert len(entries) == 3
            assert entries[0]['tweet_id'] == "123"
            assert entries[1]['cache_hit'] == True
            assert entries[2]['event'] == "translation_failed"
        finally:
            os.unlink(temp_file)
    
    def test_parse_log_file_nonexistent(self):
        """Test parsing non-existent log file"""
        entries = self.analyzer.parse_log_file("/nonexistent/file.json")
        assert entries == []
    
    def test_parse_log_file_malformed_json(self):
        """Test parsing log file with malformed JSON"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(json.dumps(self.sample_log_entries[0]) + '\n')
            f.write('invalid json line\n')
            f.write(json.dumps(self.sample_log_entries[1]) + '\n')
            temp_file = f.name
        
        try:
            entries = self.analyzer.parse_log_file(temp_file)
            
            # Should skip malformed line and parse valid ones
            assert len(entries) == 2
            assert entries[0]['tweet_id'] == "123"
            assert entries[1]['tweet_id'] == "124"
        finally:
            os.unlink(temp_file)
    
    def test_get_translation_stats_success(self):
        """Test translation statistics extraction"""
        stats = self.analyzer.get_translation_stats(self.sample_log_entries)
        
        assert stats['total_translations'] == 3
        assert stats['successful_translations'] == 2
        assert stats['failed_translations'] == 1
        assert stats['success_rate_percent'] == 66.67
        assert stats['cache_hit_rate_percent'] == 50.0  # 1 out of 2 successful
        assert stats['average_api_duration_ms'] == 1200.5  # Only non-cache API call
        assert "Spanish" in stats['languages_processed']
        assert "French" in stats['languages_processed']
    
    def test_get_translation_stats_no_events(self):
        """Test translation stats with no translation events"""
        non_translation_logs = [
            {"level": "INFO", "event": "bot_start"},
            {"level": "INFO", "event": "cache_performance"}
        ]
        
        stats = self.analyzer.get_translation_stats(non_translation_logs)
        assert "error" in stats
        assert "No translation events found" in stats["error"]
    
    def test_get_error_summary_with_errors(self):
        """Test error summary extraction"""
        error_logs = [
            {
                "level": "ERROR",
                "event": "translation_failed", 
                "error_type": "GeminiAPIError",
                "tweet_id": "123"
            },
            {
                "level": "ERROR",
                "event": "post_failed",
                "error_type": "RateLimitError",
                "tweet_id": "124"
            },
            {
                "level": "ERROR",
                "event": "translation_failed",
                "error_type": "GeminiAPIError", 
                "tweet_id": "125"
            }
        ]
        
        summary = self.analyzer.get_error_summary(error_logs)
        
        assert summary['total_errors'] == 3
        assert summary['error_types']['GeminiAPIError'] == 2
        assert summary['error_types']['RateLimitError'] == 1
        assert summary['most_common_error'] == "GeminiAPIError"
        assert len(summary['recent_errors']) == 3
    
    def test_get_error_summary_no_errors(self):
        """Test error summary with no errors"""
        no_error_logs = [
            {"level": "INFO", "event": "translation_success"},
            {"level": "INFO", "event": "post_success"}
        ]
        
        summary = self.analyzer.get_error_summary(no_error_logs)
        assert summary['total_errors'] == 0

class TestStructuredLoggerIntegration:
    def setup_method(self):
        """Set up test fixtures"""
        self.test_tweet = Tweet(
            id="123456789",
            text="Hello world! #test @user https://example.com",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            author_username="testuser",
            author_id="987654321",
            public_metrics={}
        )
        
        self.test_translation = Translation(
            original_tweet=self.test_tweet,
            target_language="Spanish",
            translated_text="¡Hola mundo! #test @user https://example.com",
            translation_timestamp=datetime.now(),
            character_count=45,
            status="pending"
        )
    
    @patch('src.utils.structured_logger.structured_logger')
    def test_log_tweet_processing(self, mock_logger):
        """Test tweet processing logging"""
        mock_logger.log_tweet_processing(
            tweet_id=self.test_tweet.id,
            text_preview=self.test_tweet.text,
            language_count=3
        )
        
        mock_logger.log_tweet_processing.assert_called_once_with(
            tweet_id="123456789",
            text_preview=self.test_tweet.text,
            language_count=3
        )
    
    @patch('src.utils.structured_logger.structured_logger')
    def test_log_translation_success(self, mock_logger):
        """Test translation success logging"""
        mock_logger.log_translation_success(
            tweet_id="123456",
            target_language="Spanish",
            character_count=45,
            cache_hit=True,
            duration_ms=1.5
        )
        
        mock_logger.log_translation_success.assert_called_once_with(
            tweet_id="123456",
            target_language="Spanish",
            character_count=45,
            cache_hit=True,
            duration_ms=1.5
        )
    
    @patch('src.utils.structured_logger.structured_logger')
    def test_log_cache_performance(self, mock_logger):
        """Test cache performance logging"""
        mock_logger.log_cache_performance(
            hit_rate=75.5,
            total_requests=200,
            cache_size=150,
            memory_mb=3.2
        )
        
        mock_logger.log_cache_performance.assert_called_once_with(
            hit_rate=75.5,
            total_requests=200,
            cache_size=150,
            memory_mb=3.2
        )
    
    def test_convenience_functions(self):
        """Test convenience logging functions"""
        from src.utils.structured_logger import log_info, log_warning, log_error
        
        with patch('src.utils.structured_logger.structured_logger') as mock_logger:
            log_info("Test info", test_param="value")
            log_warning("Test warning", warning_type="test")
            log_error("Test error", error_code=500)
            
            mock_logger.info.assert_called_once_with("Test info", test_param="value")
            mock_logger.warning.assert_called_once_with("Test warning", warning_type="test")
            mock_logger.error.assert_called_once_with("Test error", error_code=500)
    
    def test_gemini_api_call_logging(self):
        """Test Gemini API call logging"""
        with patch('src.utils.structured_logger.structured_logger') as mock_logger:
            log_gemini_api_call(
                tweet_id="123456",
                target_language="Spanish",
                prompt_tokens=150,
                response_tokens=45,
                duration_ms=1250.5
            )
            
            mock_logger.info.assert_called_once()
            call_args, call_kwargs = mock_logger.info.call_args
            
            assert "Gemini API call completed" in call_args[0]
            assert call_kwargs['event'] == "gemini_api_call"
            assert call_kwargs['prompt_tokens'] == 150
            assert call_kwargs['response_tokens'] == 45
            assert call_kwargs['duration_ms'] == 1250.5
            assert 'estimated_cost_usd' in call_kwargs
    
    def test_rate_limit_logging(self):
        """Test rate limit event logging"""
        from src.utils.structured_logger import log_rate_limit_event
        
        with patch('src.utils.structured_logger.structured_logger') as mock_logger:
            log_rate_limit_event(
                api_service="twitter",
                limit_type="daily_limit",
                retry_after=900
            )
            
            mock_logger.warning.assert_called_once()
            call_args, call_kwargs = mock_logger.warning.call_args
            
            assert "Rate limit encountered" in call_args[0]
            assert call_kwargs['event'] == "rate_limit_hit"
            assert call_kwargs['api_service'] == "twitter"
            assert call_kwargs['retry_after_seconds'] == 900
    
    def test_system_health_logging(self):
        """Test system health logging"""
        from src.utils.structured_logger import log_system_health
        
        with patch('src.utils.structured_logger.structured_logger') as mock_logger:
            log_system_health(
                component="cache",
                status="healthy",
                hit_rate=75.0,
                memory_usage=2.3
            )
            
            mock_logger.info.assert_called_once()
            call_args, call_kwargs = mock_logger.info.call_args
            
            assert "System health check" in call_args[0]
            assert call_kwargs['event'] == "health_check"
            assert call_kwargs['component'] == "cache"
            assert call_kwargs['status'] == "healthy"
            assert call_kwargs['hit_rate'] == 75.0
