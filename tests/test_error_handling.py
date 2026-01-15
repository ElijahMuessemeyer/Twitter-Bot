# =============================================================================
# TESTS FOR ERROR HANDLING SYSTEM
# =============================================================================

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from src.exceptions import (
    TwitterAPIError,
    TwitterRateLimitError,
    GeminiAPIError,
    GeminiQuotaError,
    TranslationError,
    NetworkError
)
from src.utils.retry import retry_with_backoff, RetryConfig, execute_with_retry
from src.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState, CircuitBreakerOpenError
from src.utils.error_recovery import ErrorRecoveryManager, RecoveryAction, RecoveryPlan


class TestExceptions:
    """Test custom exception hierarchy"""
    
    def test_twitter_api_error_creation(self):
        error = TwitterAPIError("Test error", status_code=429, error_code="TEST_ERROR")
        assert str(error) == "Test error [TEST_ERROR]"
        assert error.status_code == 429
        assert error.error_code == "TEST_ERROR"
        assert not error.retryable  # Default
    
    def test_twitter_rate_limit_error(self):
        error = TwitterRateLimitError("Rate limited", reset_time=1234567890, remaining=0)
        assert error.retryable  # Should be retryable by default
        assert error.reset_time == 1234567890
        assert error.remaining == 0
        
        error_dict = error.to_dict()
        assert error_dict['error_type'] == 'TwitterRateLimitError'
        assert error_dict['reset_time'] == 1234567890
    
    def test_gemini_quota_error(self):
        error = GeminiQuotaError("Quota exceeded", quota_type="daily")
        assert error.quota_type == "daily"
        assert error.error_code == "QUOTA_EXCEEDED"
    
    def test_translation_error(self):
        error = TranslationError(
            "Translation failed",
            tweet_id="123",
            target_language="ja"
        )
        assert error.tweet_id == "123"
        assert error.target_language == "ja"


class TestRetryLogic:
    """Test retry mechanism with exponential backoff"""
    
    def test_successful_function_no_retry(self):
        @retry_with_backoff(config=RetryConfig(max_attempts=3))
        def success_function():
            return "success"
        
        result = success_function()
        assert result == "success"
    
    def test_function_fails_then_succeeds(self):
        call_count = 0
        
        @retry_with_backoff(config=RetryConfig(max_attempts=3, base_delay=0.01))
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise NetworkError("Temporary failure")
            return "success"
        
        result = flaky_function()
        assert result == "success"
        assert call_count == 3
    
    def test_function_exceeds_max_attempts(self):
        @retry_with_backoff(config=RetryConfig(max_attempts=2, base_delay=0.01))
        def always_fails():
            raise TwitterAPIError("Always fails")
        
        with pytest.raises(TwitterAPIError):
            always_fails()
    
    def test_non_retryable_error_not_retried(self):
        call_count = 0
        
        @retry_with_backoff(config=RetryConfig(max_attempts=3))
        def auth_error_function():
            nonlocal call_count
            call_count += 1
            raise TwitterAPIError("Auth error")  # Not retryable by default
        
        with pytest.raises(TwitterAPIError):
            auth_error_function()
        
        assert call_count == 1  # Should not retry
    
    def test_execute_with_retry_convenience_function(self):
        def flaky_function(arg1, arg2, kwarg1=None):
            if kwarg1 == "fail":
                raise NetworkError("Network error")
            return f"{arg1}-{arg2}-{kwarg1}"
        
        result = execute_with_retry(
            flaky_function,
            "test1", "test2",
            config=RetryConfig(max_attempts=2, base_delay=0.01),
            kwarg1="success"
        )
        
        assert result == "test1-test2-success"


class TestCircuitBreaker:
    """Test circuit breaker pattern"""
    
    def test_circuit_breaker_closed_state(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        assert cb.state == CircuitState.CLOSED
        
        # Successful calls should keep circuit closed
        result = cb.call(lambda: "success")
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
    
    def test_circuit_breaker_opens_after_failures(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=2,
            min_requests=1
        ))
        
        # First failure
        with pytest.raises(Exception):
            cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        
        # Second failure should open circuit
        with pytest.raises(Exception):
            cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        
        # Circuit should now be open
        cb._update_state()
        assert cb.state == CircuitState.OPEN
    
    def test_circuit_breaker_blocks_requests_when_open(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1, min_requests=1))
        
        # Cause failure to open circuit
        with pytest.raises(Exception):
            cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        
        cb._update_state()
        
        # Next call should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should be blocked")
    
    def test_circuit_breaker_half_open_after_timeout(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=1,
            timeout=0.01,  # Very short timeout for testing
            min_requests=1
        ))
        
        # Cause failure
        with pytest.raises(Exception):
            cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        
        cb._update_state()
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout
        time.sleep(0.02)
        cb._update_state()
        
        assert cb.state == CircuitState.HALF_OPEN
    
    def test_circuit_breaker_health_status(self):
        cb = CircuitBreaker("test")
        
        status = cb.get_health_status()
        assert status['name'] == 'test'
        assert status['state'] == 'closed'
        assert status['healthy'] is True
        assert status['total_requests'] == 0
        assert status['total_failures'] == 0


class TestErrorRecovery:
    """Test error recovery strategies"""
    
    def test_error_recovery_manager_initialization(self):
        erm = ErrorRecoveryManager()
        assert len(erm._recovery_strategies) > 0
        assert TwitterRateLimitError in erm._recovery_strategies
        assert GeminiQuotaError in erm._recovery_strategies
    
    def test_recovery_plan_registration(self):
        erm = ErrorRecoveryManager()
        
        custom_plan = RecoveryPlan(
            actions=[RecoveryAction.RETRY_WITH_BACKOFF],
            retry_delay=5.0,
            max_retries=3
        )
        
        erm.register_strategy(CustomError, custom_plan)
        assert CustomError in erm._recovery_strategies
        assert erm._recovery_strategies[CustomError] == custom_plan
    
    def test_error_handling_with_save_to_queue(self):
        erm = ErrorRecoveryManager()
        
        error = GeminiQuotaError("Quota exceeded")
        context = {
            'operation_type': 'translate',
            'tweet_id': '123'
        }
        
        result = erm.handle_error(error, context)
        
        assert result['error_type'] == 'GeminiQuotaError'
        assert len(result['actions_taken']) > 0
        
        # Check if operation was queued
        queued_ops = erm.get_queued_operations()
        assert len(queued_ops) > 0
        assert queued_ops[0]['operation_type'] == 'translate'
    
    def test_fallback_function_execution(self):
        erm = ErrorRecoveryManager()
        
        def fallback_func(error, context):
            return f"fallback for {context.get('operation_type')}"
        
        error = TranslationError("Translation failed")
        context = {'operation_type': 'translate_tweet'}
        
        result = erm.handle_error(error, context, fallback_func)
        
        # Should have used fallback
        fallback_action = next((action for action in result['actions_taken'] 
                               if action['action'] == 'use_fallback'), None)
        assert fallback_action is not None
        assert fallback_action['result']['success'] is True
    
    def test_service_degradation(self):
        erm = ErrorRecoveryManager()
        
        # Register strategy with degradation
        plan = RecoveryPlan(actions=[RecoveryAction.DEGRADE_SERVICE])
        erm.register_strategy(CustomError, plan)
        
        error = CustomError("Service failing")
        context = {'service_name': 'test_service'}
        
        erm.handle_error(error, context)
        
        assert erm.is_service_degraded('test_service')
        
        # Test restoration
        erm.restore_service('test_service')
        assert not erm.is_service_degraded('test_service')
    
    def test_health_status(self):
        erm = ErrorRecoveryManager()
        
        health = erm.get_health_status()
        assert 'queued_operations' in health
        assert 'degraded_services' in health
        assert 'registered_strategies' in health
        assert isinstance(health['registered_strategies'], int)


class TestIntegration:
    """Integration tests for error handling components"""
    
    @patch('src.utils.structured_logger.structured_logger')
    def test_retry_with_circuit_breaker(self, mock_logger):
        # Test that retry and circuit breaker work together
        failure_count = 0
        
        def flaky_service():
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 2:
                raise NetworkError("Service unavailable")
            return "success"
        
        cb = CircuitBreaker("integration_test", CircuitBreakerConfig(failure_threshold=5))
        
        @retry_with_backoff(config=RetryConfig(max_attempts=5, base_delay=0.01))
        def protected_call():
            return cb.call(flaky_service)
        
        result = protected_call()
        assert result == "success"
        assert failure_count == 3
    
    def test_full_error_handling_flow(self):
        """Test a complete error handling scenario"""
        erm = ErrorRecoveryManager()
        cb = CircuitBreaker("test_service")
        
        failure_count = 0
        
        def failing_service():
            nonlocal failure_count
            failure_count += 1
            raise NetworkError("Service down")
        
        # Try to call service through circuit breaker
        try:
            cb.call(failing_service)
        except NetworkError as e:
            # Handle error with recovery manager
            result = erm.handle_error(e, {
                'operation_type': 'test_call',
                'service_name': 'test_service'
            })
            
            assert not result['success']  # No fallback provided
            assert len(result['actions_taken']) > 0
        
        # Verify circuit breaker recorded the failure
        status = cb.get_health_status()
        assert status['total_failures'] == 1


# Custom error class for testing
class CustomError(Exception):
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
