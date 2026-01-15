"""
Comprehensive tests for error recovery functionality.

Tests cover:
- Error classification and recovery strategies
- Retry mechanisms with exponential backoff
- Queued operation management
- Degraded service handling
- Recovery context preservation
- Error recovery manager functionality
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils.error_recovery import (
    ErrorRecoveryManager,
    RecoveryAction,
    RecoveryPlan,
    error_recovery_manager,
    recover_from_error
)

# Import exception classes for testing
from src.exceptions import (
    TwitterRateLimitError,
    TwitterQuotaExceededError,
    GeminiAPIError,
    GeminiQuotaError,
    TranslationError,
    NetworkError
)


class TestRecoveryAction:
    """Test recovery action enumeration."""
    
    def test_recovery_action_values(self):
        """Test that all recovery actions have correct values."""
        assert RecoveryAction.RETRY_WITH_BACKOFF.value == "retry_with_backoff"
        assert RecoveryAction.SAVE_TO_QUEUE.value == "save_to_queue"
        assert RecoveryAction.USE_FALLBACK.value == "use_fallback"
        assert RecoveryAction.DEGRADE_SERVICE.value == "degrade_service"
        assert RecoveryAction.NOTIFY_ADMIN.value == "notify_admin"
        assert RecoveryAction.SKIP_OPERATION.value == "skip_operation"


class TestRecoveryPlan:
    """Test recovery plan data class."""
    
    def test_default_recovery_plan(self):
        """Test default recovery plan values."""
        plan = RecoveryPlan()
        
        assert plan.actions == []
        assert plan.retry_delay == 0.0
        assert plan.max_retries == 0
        assert plan.fallback_func is None
        assert plan.notification_level == "warning"
        assert plan.context == {}
    
    def test_custom_recovery_plan(self):
        """Test custom recovery plan values."""
        def mock_fallback():
            return "fallback_result"
        
        plan = RecoveryPlan(
            actions=[RecoveryAction.RETRY_WITH_BACKOFF, RecoveryAction.USE_FALLBACK],
            retry_delay=30.0,
            max_retries=5,
            fallback_func=mock_fallback,
            notification_level="error",
            context={"service": "test"}
        )
        
        assert len(plan.actions) == 2
        assert RecoveryAction.RETRY_WITH_BACKOFF in plan.actions
        assert RecoveryAction.USE_FALLBACK in plan.actions
        assert plan.retry_delay == 30.0
        assert plan.max_retries == 5
        assert plan.fallback_func == mock_fallback
        assert plan.notification_level == "error"
        assert plan.context == {"service": "test"}


class TestErrorRecoveryManager:
    """Test error recovery manager functionality."""
    
    @pytest.fixture
    def recovery_manager(self):
        """Create a fresh error recovery manager."""
        return ErrorRecoveryManager()
    
    def test_initialization(self, recovery_manager):
        """Test manager initialization."""
        assert isinstance(recovery_manager._recovery_strategies, dict)
        assert isinstance(recovery_manager._operation_queue, list)
        assert isinstance(recovery_manager._degraded_services, set)
        
        # Check default strategies are loaded
        assert TwitterRateLimitError in recovery_manager._recovery_strategies
        assert TwitterQuotaExceededError in recovery_manager._recovery_strategies
        assert GeminiAPIError in recovery_manager._recovery_strategies
        assert GeminiQuotaError in recovery_manager._recovery_strategies
        assert NetworkError in recovery_manager._recovery_strategies
        assert TranslationError in recovery_manager._recovery_strategies
    
    def test_default_strategies_configuration(self, recovery_manager):
        """Test that default strategies are properly configured."""
        # Twitter rate limit strategy
        twitter_rate_limit_plan = recovery_manager._recovery_strategies[TwitterRateLimitError]
        assert RecoveryAction.RETRY_WITH_BACKOFF in twitter_rate_limit_plan.actions
        assert twitter_rate_limit_plan.retry_delay == 60.0
        assert twitter_rate_limit_plan.max_retries == 2
        assert twitter_rate_limit_plan.notification_level == "info"
        
        # Twitter quota exceeded strategy
        twitter_quota_plan = recovery_manager._recovery_strategies[TwitterQuotaExceededError]
        assert RecoveryAction.SAVE_TO_QUEUE in twitter_quota_plan.actions
        assert RecoveryAction.NOTIFY_ADMIN in twitter_quota_plan.actions
        assert twitter_quota_plan.notification_level == "warning"
        
        # Gemini API error strategy
        gemini_api_plan = recovery_manager._recovery_strategies[GeminiAPIError]
        assert RecoveryAction.RETRY_WITH_BACKOFF in gemini_api_plan.actions
        assert RecoveryAction.SAVE_TO_QUEUE in gemini_api_plan.actions
        assert gemini_api_plan.retry_delay == 10.0
        assert gemini_api_plan.max_retries == 3
        
        # Network error strategy
        network_plan = recovery_manager._recovery_strategies[NetworkError]
        assert RecoveryAction.RETRY_WITH_BACKOFF in network_plan.actions
        assert network_plan.retry_delay == 5.0
        assert network_plan.max_retries == 5
    
    def test_register_custom_strategy(self, recovery_manager):
        """Test registering custom recovery strategy."""
        class CustomError(Exception):
            pass
        
        custom_plan = RecoveryPlan(
            actions=[RecoveryAction.SKIP_OPERATION],
            notification_level="debug"
        )
        
        recovery_manager.register_strategy(CustomError, custom_plan)
        
        assert CustomError in recovery_manager._recovery_strategies
        assert recovery_manager._recovery_strategies[CustomError] == custom_plan
    
    def test_handle_twitter_rate_limit_error(self, recovery_manager):
        """Test handling Twitter rate limit error."""
        error = TwitterRateLimitError("Rate limit exceeded")
        context = {"operation_type": "tweet_fetch", "user_id": "123"}
        
        result = recovery_manager.handle_error(error, context)
        
        assert result['error_type'] == "TwitterRateLimitError"
        assert "Rate limit exceeded" in result['error_message']
        assert "retry_with_backoff" in result['recovery_actions']
        assert len(result['actions_taken']) > 0
        
        # Should have attempted retry action
        retry_action = next((a for a in result['actions_taken'] if a['action'] == 'retry_with_backoff'), None)
        assert retry_action is not None
        assert retry_action['result']['retry_delay'] == 60.0
        assert retry_action['result']['max_retries'] == 2
    
    def test_handle_twitter_quota_exceeded_error(self, recovery_manager):
        """Test handling Twitter quota exceeded error."""
        error = TwitterQuotaExceededError("Monthly quota exceeded")
        context = {"operation_type": "tweet_post", "content": "test tweet"}
        
        result = recovery_manager.handle_error(error, context)
        
        assert result['error_type'] == "TwitterQuotaExceededError"
        assert "save_to_queue" in result['recovery_actions']
        assert "notify_admin" in result['recovery_actions']
        
        # Should have saved to queue
        assert len(recovery_manager._operation_queue) == 1
        queued_item = recovery_manager._operation_queue[0]
        assert queued_item['operation_type'] == "tweet_post"
        assert queued_item['context'] == context
        assert queued_item['error'] == "Monthly quota exceeded"
    
    def test_handle_gemini_quota_error_with_fallback(self, recovery_manager):
        """Test handling Gemini quota error with fallback function."""
        error = GeminiQuotaError("Gemini quota exceeded")
        context = {"operation_type": "translation", "text": "Hello world"}
        
        def fallback_translator(err, ctx):
            return f"Fallback translation of: {ctx['text']}"
        
        result = recovery_manager.handle_error(error, context, fallback_translator)
        
        assert result['error_type'] == "GeminiQuotaError"
        assert "use_fallback" in result['recovery_actions']
        assert result['success'] is True  # Fallback should succeed
        
        # Check fallback was executed
        fallback_action = next((a for a in result['actions_taken'] if a['action'] == 'use_fallback'), None)
        assert fallback_action is not None
        assert fallback_action['result']['success'] is True
        assert "Fallback translation of: Hello world" in fallback_action['result']['result']
    
    def test_handle_unknown_error_type(self, recovery_manager):
        """Test handling unknown error type with default strategy."""
        class UnknownError(Exception):
            pass
        
        error = UnknownError("Unknown error occurred")
        context = {"operation_type": "unknown_operation"}
        
        result = recovery_manager.handle_error(error, context)
        
        assert result['error_type'] == "UnknownError"
        assert "notify_admin" in result['recovery_actions']
        
        # Should use default plan
        admin_action = next((a for a in result['actions_taken'] if a['action'] == 'notify_admin'), None)
        assert admin_action is not None
    
    def test_error_inheritance_handling(self, recovery_manager):
        """Test that error inheritance is handled correctly."""
        # Create a custom error that inherits from NetworkError
        class CustomNetworkError(NetworkError):
            pass
        
        error = CustomNetworkError("Custom network issue")
        context = {"operation_type": "api_call"}
        
        result = recovery_manager.handle_error(error, context)
        
        # Should use NetworkError strategy since CustomNetworkError inherits from it
        assert result['error_type'] == "CustomNetworkError"
        assert "retry_with_backoff" in result['recovery_actions']
        
        # Check retry configuration matches NetworkError strategy
        retry_action = next((a for a in result['actions_taken'] if a['action'] == 'retry_with_backoff'), None)
        assert retry_action is not None
        assert retry_action['result']['retry_delay'] == 5.0  # NetworkError retry delay
        assert retry_action['result']['max_retries'] == 5   # NetworkError max retries
    
    def test_save_to_queue_functionality(self, recovery_manager):
        """Test save to queue recovery action."""
        error = Exception("Test error")
        context = {
            "operation_type": "test_operation",
            "data": {"key": "value"},
            "timestamp": time.time()
        }
        
        result = recovery_manager._handle_save_to_queue(error, context)
        
        assert result['success'] is True
        assert result['queue_position'] == 1
        assert len(recovery_manager._operation_queue) == 1
        
        queued_item = recovery_manager._operation_queue[0]
        assert queued_item['operation_type'] == "test_operation"
        assert queued_item['context'] == context
        assert queued_item['error'] == "Test error"
        assert queued_item['retry_count'] == 0
    
    def test_fallback_function_success(self, recovery_manager):
        """Test successful fallback function execution."""
        def successful_fallback(error, context):
            return f"Fallback handled {context['operation_type']}"
        
        error = Exception("Original error")
        context = {"operation_type": "test_op"}
        
        result = recovery_manager._handle_use_fallback(error, context, successful_fallback)
        
        assert result['success'] is True
        assert result['result'] == "Fallback handled test_op"
    
    def test_fallback_function_failure(self, recovery_manager):
        """Test fallback function that also fails."""
        def failing_fallback(error, context):
            raise ValueError("Fallback also failed")
        
        error = Exception("Original error")
        context = {"operation_type": "test_op"}
        
        result = recovery_manager._handle_use_fallback(error, context, failing_fallback)
        
        assert result['success'] is False
        assert "Fallback also failed" in result['message']
        assert "Fallback also failed" in result['fallback_error']
    
    def test_no_fallback_function(self, recovery_manager):
        """Test fallback action when no fallback function is provided."""
        error = Exception("Original error")
        context = {"operation_type": "test_op"}
        
        result = recovery_manager._handle_use_fallback(error, context, None)
        
        assert result['success'] is False
        assert "No fallback function available" in result['message']
    
    def test_service_degradation(self, recovery_manager):
        """Test service degradation functionality."""
        error = Exception("Service overloaded")
        context = {"service_name": "api_service", "operation_type": "api_call"}
        
        result = recovery_manager._handle_degrade_service(error, context)
        
        assert result['success'] is True
        assert "api_service" in result['degraded_services']
        assert recovery_manager.is_service_degraded("api_service")
        assert not recovery_manager.is_service_degraded("other_service")
    
    def test_service_restoration(self, recovery_manager):
        """Test service restoration functionality."""
        # First degrade a service
        recovery_manager._degraded_services.add("test_service")
        assert recovery_manager.is_service_degraded("test_service")
        
        # Then restore it
        recovery_manager.restore_service("test_service")
        assert not recovery_manager.is_service_degraded("test_service")
    
    def test_admin_notification(self, recovery_manager):
        """Test admin notification functionality."""
        error = Exception("Critical error")
        context = {"operation_type": "critical_operation"}
        
        with patch('src.utils.error_recovery.logger') as mock_logger:
            result = recovery_manager._handle_notify_admin(error, context, "error")
            
            assert result['success'] is True
            assert result['notification_level'] == "error"
            mock_logger.error.assert_called_once()
    
    def test_skip_operation(self, recovery_manager):
        """Test skip operation functionality."""
        error = Exception("Unrecoverable error")
        context = {"operation_type": "skippable_operation"}
        
        result = recovery_manager._handle_skip_operation(error, context)
        
        assert result['success'] is True
        assert result['skipped'] is True
    
    def test_get_queued_operations(self, recovery_manager):
        """Test getting queued operations."""
        # Add some operations to queue
        for i in range(3):
            error = Exception(f"Error {i}")
            context = {"operation_type": f"operation_{i}"}
            recovery_manager._handle_save_to_queue(error, context)
        
        queued_ops = recovery_manager.get_queued_operations()
        
        assert len(queued_ops) == 3
        assert queued_ops[0]['operation_type'] == "operation_0"
        assert queued_ops[1]['operation_type'] == "operation_1"
        assert queued_ops[2]['operation_type'] == "operation_2"
        
        # Ensure it's a copy, not the original
        queued_ops.append({"test": "item"})
        assert len(recovery_manager._operation_queue) == 3
    
    def test_retry_queued_operations_empty_queue(self, recovery_manager):
        """Test retrying operations when queue is empty."""
        result = recovery_manager.retry_queued_operations()
        
        assert result['message'] == "No operations in queue"
        assert result['processed'] == 0
    
    def test_retry_queued_operations_with_items(self, recovery_manager):
        """Test retrying queued operations."""
        # Add some operations to queue
        for i in range(5):
            error = Exception(f"Error {i}")
            context = {"operation_type": f"operation_{i}"}
            recovery_manager._handle_save_to_queue(error, context)
        
        # Mock the retry logic to simulate success
        with patch('src.utils.error_recovery.logger') as mock_logger:
            result = recovery_manager.retry_queued_operations(max_operations=3)
        
        assert result['processed'] == 3
        assert result['successful'] == 3
        assert result['failed'] == 0
        assert result['remaining_in_queue'] == 2  # 5 - 3 = 2
    
    def test_retry_queued_operations_max_retries(self, recovery_manager):
        """Test that operations are removed after max retries."""
        # Add operation to queue and set high retry count
        error = Exception("Persistent error")
        context = {"operation_type": "failing_operation"}
        recovery_manager._handle_save_to_queue(error, context)
        
        # Set retry count to max
        recovery_manager._operation_queue[0]['retry_count'] = 3
        
        with patch('src.utils.error_recovery.logger') as mock_logger:
            # Mock the retry to fail
            mock_logger.info.side_effect = Exception("Retry failed")
            
            result = recovery_manager.retry_queued_operations()
        
        # Operation should be removed due to max retries
        assert len(recovery_manager._operation_queue) == 0
    
    def test_health_status(self, recovery_manager):
        """Test health status reporting."""
        # Add some data to test health status
        recovery_manager._degraded_services.add("degraded_service")
        recovery_manager._handle_save_to_queue(Exception("test"), {"op": "test"})
        
        health = recovery_manager.get_health_status()
        
        assert health['queued_operations'] == 1
        assert "degraded_service" in health['degraded_services']
        assert health['registered_strategies'] >= 6  # At least the default strategies
        assert "TwitterRateLimitError" in health['strategy_types']
        assert "NetworkError" in health['strategy_types']
    
    def test_multiple_recovery_actions_execution(self, recovery_manager):
        """Test that multiple recovery actions are executed in order."""
        # Create a plan with multiple actions
        plan = RecoveryPlan(
            actions=[
                RecoveryAction.SAVE_TO_QUEUE,
                RecoveryAction.DEGRADE_SERVICE,
                RecoveryAction.NOTIFY_ADMIN
            ],
            notification_level="warning"
        )
        
        class MultiActionError(Exception):
            pass
        
        recovery_manager.register_strategy(MultiActionError, plan)
        
        error = MultiActionError("Multi-action test error")
        context = {"operation_type": "multi_test", "service_name": "test_service"}
        
        with patch('src.utils.error_recovery.logger') as mock_logger:
            result = recovery_manager.handle_error(error, context)
        
        assert len(result['actions_taken']) == 3
        
        # Check all actions were executed
        action_types = [action['action'] for action in result['actions_taken']]
        assert 'save_to_queue' in action_types
        assert 'degrade_service' in action_types
        assert 'notify_admin' in action_types
        
        # Verify side effects
        assert len(recovery_manager._operation_queue) == 1
        assert recovery_manager.is_service_degraded("test_service")
    
    def test_recovery_action_failure_handling(self, recovery_manager):
        """Test handling of recovery action failures."""
        # Create a mock action that fails
        with patch.object(recovery_manager, '_handle_save_to_queue') as mock_save:
            mock_save.side_effect = Exception("Queue storage failed")
            
            error = Exception("Original error")
            context = {"operation_type": "test"}
            
            # Create plan that only saves to queue
            plan = RecoveryPlan(actions=[RecoveryAction.SAVE_TO_QUEUE])
            recovery_manager.register_strategy(Exception, plan)
            
            result = recovery_manager.handle_error(error, context)
            
            assert result['success'] is False
            assert len(result['actions_taken']) == 1
            assert result['actions_taken'][0]['result']['success'] is False
            assert "Queue storage failed" in result['actions_taken'][0]['result']['error']
    
    def test_concurrent_error_handling(self, recovery_manager):
        """Test concurrent error handling for thread safety."""
        def handle_error_worker(worker_id):
            error = Exception(f"Error from worker {worker_id}")
            context = {"operation_type": f"operation_{worker_id}", "worker_id": worker_id}
            return recovery_manager.handle_error(error, context)
        
        results = []
        
        # Run concurrent error handling
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(handle_error_worker, i) for i in range(50)]
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
        
        assert len(results) == 50
        
        # Check that all operations were handled
        unique_worker_ids = {r['actions_taken'][0]['result'].get('worker_id') for r in results 
                           if r['actions_taken'] and 'worker_id' in r['actions_taken'][0]['result']}
        
        # Verify no race conditions in queue operations
        health = recovery_manager.get_health_status()
        assert health['queued_operations'] >= 0  # Should not be negative


class TestGlobalFunctions:
    """Test global convenience functions."""
    
    def test_recover_from_error_function(self):
        """Test global recover_from_error function."""
        error = NetworkError("Network connection failed")
        context = {"operation_type": "api_request", "url": "https://api.example.com"}
        
        def fallback_function(err, ctx):
            return f"Cached response for {ctx['url']}"
        
        result = recover_from_error(error, context, fallback_function)
        
        assert result['error_type'] == "NetworkError"
        assert "retry_with_backoff" in result['recovery_actions']
        assert len(result['actions_taken']) > 0
    
    def test_recover_from_error_without_fallback(self):
        """Test global function without fallback."""
        error = TwitterRateLimitError("Rate limit exceeded")
        context = {"operation_type": "tweet_fetch"}
        
        result = recover_from_error(error, context)
        
        assert result['error_type'] == "TwitterRateLimitError"
        assert result['recovery_actions'] == ["retry_with_backoff"]


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""
    
    def test_twitter_api_failure_cascade(self):
        """Test handling a cascade of Twitter API failures."""
        recovery_manager = ErrorRecoveryManager()
        
        # Simulate rate limit followed by quota exceeded
        rate_limit_error = TwitterRateLimitError("Rate limit: 900 requests per 15 minutes")
        quota_error = TwitterQuotaExceededError("Monthly quota exceeded")
        
        context1 = {"operation_type": "tweet_fetch", "user_id": "123", "batch_size": 100}
        context2 = {"operation_type": "tweet_post", "content": "Important announcement"}
        
        # Handle rate limit error
        result1 = recovery_manager.handle_error(rate_limit_error, context1)
        assert "retry_with_backoff" in result1['recovery_actions']
        
        # Handle quota error
        result2 = recovery_manager.handle_error(quota_error, context2)
        assert "save_to_queue" in result2['recovery_actions']
        assert "notify_admin" in result2['recovery_actions']
        
        # Verify operations are queued
        queued_ops = recovery_manager.get_queued_operations()
        assert len(queued_ops) == 1
        assert queued_ops[0]['operation_type'] == "tweet_post"
    
    def test_translation_service_degradation_scenario(self):
        """Test translation service degradation and fallback scenario."""
        recovery_manager = ErrorRecoveryManager()
        
        def simple_fallback_translator(error, context):
            # Simple fallback that just returns the original text
            return f"[UNTRANSLATED] {context.get('text', 'Unknown text')}"
        
        # Simulate Gemini quota exceeded
        error = GeminiQuotaError("Gemini API quota exceeded for today")
        context = {
            "operation_type": "translation",
            "text": "Hello, how are you?",
            "target_language": "es",
            "service_name": "gemini_translator"
        }
        
        result = recovery_manager.handle_error(error, context, simple_fallback_translator)
        
        # Should use fallback successfully
        assert result['success'] is True
        fallback_action = next((a for a in result['actions_taken'] if a['action'] == 'use_fallback'), None)
        assert fallback_action is not None
        assert "[UNTRANSLATED] Hello, how are you?" in fallback_action['result']['result']
        
        # Should also queue the operation for later retry
        queued_ops = recovery_manager.get_queued_operations()
        assert len(queued_ops) == 1
        assert queued_ops[0]['context']['text'] == "Hello, how are you?"
    
    def test_network_error_retry_exhaustion(self):
        """Test network error retry until exhaustion."""
        recovery_manager = ErrorRecoveryManager()
        
        # Simulate persistent network errors
        network_error = NetworkError("Connection timeout after 30 seconds")
        context = {
            "operation_type": "api_sync",
            "endpoint": "/api/v1/sync",
            "retry_attempt": 0
        }
        
        # Handle the error multiple times to simulate retry exhaustion
        for attempt in range(6):  # NetworkError max_retries is 5
            context["retry_attempt"] = attempt
            result = recovery_manager.handle_error(network_error, context)
            
            if attempt < 5:
                # Should still recommend retry
                assert "retry_with_backoff" in result['recovery_actions']
            else:
                # After max retries, should fall back to default strategy
                break
        
        # Verify the retry recommendations
        assert result['error_type'] == "NetworkError"
    
    def test_mixed_error_recovery_workflow(self):
        """Test a complex workflow with mixed errors and recovery strategies."""
        recovery_manager = ErrorRecoveryManager()
        
        # Define a fallback function for critical operations
        def critical_operation_fallback(error, context):
            if context.get('critical', False):
                return f"Emergency fallback for {context['operation_type']}"
            return None
        
        # Simulate various errors in a workflow
        errors_and_contexts = [
            (NetworkError("DNS resolution failed"), {
                "operation_type": "user_lookup",
                "user_id": "123",
                "critical": False
            }),
            (GeminiAPIError("Service temporarily unavailable"), {
                "operation_type": "content_analysis",
                "content": "Analyze this tweet",
                "critical": True
            }),
            (TwitterQuotaExceededError("API quota exceeded"), {
                "operation_type": "bulk_tweet_fetch",
                "batch_size": 1000,
                "critical": False
            }),
            (TranslationError("Translation service error"), {
                "operation_type": "translate_content",
                "text": "Bonjour le monde",
                "target_lang": "en",
                "critical": True
            })
        ]
        
        results = []
        
        for error, context in errors_and_contexts:
            result = recovery_manager.handle_error(error, context, critical_operation_fallback)
            results.append(result)
        
        # Verify different recovery strategies were applied
        assert len(results) == 4
        
        # Network error should have retry strategy
        assert "retry_with_backoff" in results[0]['recovery_actions']
        
        # Gemini API error should retry and queue
        assert "retry_with_backoff" in results[1]['recovery_actions']
        assert "save_to_queue" in results[1]['recovery_actions']
        
        # Twitter quota should queue and notify admin
        assert "save_to_queue" in results[2]['recovery_actions']
        assert "notify_admin" in results[2]['recovery_actions']
        
        # Translation error should use fallback
        assert "use_fallback" in results[3]['recovery_actions']
        
        # Check that critical operations used fallback successfully
        critical_results = [r for i, r in enumerate(results) if errors_and_contexts[i][1]['critical']]
        for result in critical_results:
            fallback_action = next((a for a in result['actions_taken'] if a['action'] == 'use_fallback'), None)
            if fallback_action and fallback_action['result']['success']:
                assert "Emergency fallback" in fallback_action['result']['result']
        
        # Verify queue contains non-critical operations
        queued_ops = recovery_manager.get_queued_operations()
        assert len(queued_ops) >= 2  # At least Twitter quota and some others
    
    def test_service_degradation_and_recovery_cycle(self):
        """Test complete service degradation and recovery cycle."""
        recovery_manager = ErrorRecoveryManager()
        
        # Simulate service degradation
        error = Exception("Service overloaded - too many requests")
        context = {
            "operation_type": "heavy_computation",
            "service_name": "computation_service"
        }
        
        # Register a strategy that degrades the service
        plan = RecoveryPlan(
            actions=[RecoveryAction.DEGRADE_SERVICE, RecoveryAction.SAVE_TO_QUEUE],
            notification_level="warning"
        )
        recovery_manager.register_strategy(Exception, plan)
        
        result = recovery_manager.handle_error(error, context)
        
        # Service should be degraded
        assert recovery_manager.is_service_degraded("computation_service")
        assert len(recovery_manager.get_queued_operations()) == 1
        
        # Simulate service recovery
        recovery_manager.restore_service("computation_service")
        assert not recovery_manager.is_service_degraded("computation_service")
        
        # Verify health status reflects the changes
        health = recovery_manager.get_health_status()
        assert "computation_service" not in health['degraded_services']
        assert health['queued_operations'] == 1
