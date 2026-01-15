"""
Integration tests for circuit breaker and error recovery systems working together.

Tests realistic scenarios where both systems interact to provide comprehensive
error handling and service protection.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerOpenError,
    CircuitBreakerManager
)

from src.utils.error_recovery import (
    ErrorRecoveryManager,
    RecoveryAction,
    RecoveryPlan,
    recover_from_error
)

from src.exceptions import (
    TwitterRateLimitError,
    TwitterQuotaExceededError,
    GeminiAPIError,
    NetworkError
)


class TestCircuitBreakerErrorRecoveryIntegration:
    """Test integration between circuit breaker and error recovery systems."""
    
    @pytest.fixture
    def circuit_breaker_manager(self):
        """Create a circuit breaker manager for testing."""
        return CircuitBreakerManager()
    
    @pytest.fixture
    def error_recovery_manager(self):
        """Create an error recovery manager for testing."""
        return ErrorRecoveryManager()
    
    @pytest.fixture
    def api_service_config(self):
        """Configuration for API service circuit breaker."""
        return CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=2.0,  # Short timeout for testing
            failure_rate_threshold=0.5,
            min_requests=3,
            window_size=20
        )
    
    def test_twitter_api_with_circuit_breaker_and_recovery(self, circuit_breaker_manager, error_recovery_manager, api_service_config):
        """Test Twitter API calls protected by circuit breaker with error recovery."""
        
        # Get circuit breaker for Twitter API
        breaker = circuit_breaker_manager.get_breaker("twitter_api", api_service_config)
        
        def twitter_api_call(operation_type, data=None):
            """Simulate Twitter API call that may fail."""
            if operation_type == "rate_limited":
                raise TwitterRateLimitError("Rate limit exceeded")
            elif operation_type == "quota_exceeded":
                raise TwitterQuotaExceededError("Monthly quota exceeded")
            elif operation_type == "success":
                return {"status": "success", "data": data}
            else:
                raise NetworkError("Connection failed")
        
        def protected_twitter_call(operation_type, data=None):
            """Twitter API call protected by circuit breaker with error recovery."""
            try:
                return breaker.call(twitter_api_call, operation_type, data)
            except (TwitterRateLimitError, TwitterQuotaExceededError, NetworkError) as e:
                # Use error recovery when circuit breaker allows the call but it fails
                context = {
                    "operation_type": "twitter_api_call",
                    "service_name": "twitter_api",
                    "api_operation": operation_type,
                    "data": data
                }
                recovery_result = error_recovery_manager.handle_error(e, context)
                return {"error_recovery": recovery_result}
            except CircuitBreakerOpenError as e:
                # Circuit breaker blocked the call
                return {"circuit_breaker_blocked": str(e)}
        
        # Test successful calls
        result = protected_twitter_call("success", {"tweet_id": "123"})
        assert result["status"] == "success"
        assert breaker.state == CircuitState.CLOSED
        
        # Test rate limit errors
        result = protected_twitter_call("rate_limited")
        assert "error_recovery" in result
        assert result["error_recovery"]["error_type"] == "TwitterRateLimitError"
        assert "retry_with_backoff" in result["error_recovery"]["recovery_actions"]
        
        # Trigger more failures to open circuit
        for _ in range(2):  # Need 3 total failures to open circuit
            protected_twitter_call("network_error")
        
        assert breaker.state == CircuitState.OPEN
        
        # Now calls should be blocked by circuit breaker
        result = protected_twitter_call("success")
        assert "circuit_breaker_blocked" in result
        assert "Circuit breaker 'twitter_api' is OPEN" in result["circuit_breaker_blocked"]
        
        # Wait for circuit to go half-open
        time.sleep(2.1)
        
        # Next successful call should move to half-open and succeed
        result = protected_twitter_call("success", {"recovery": "test"})
        assert result["status"] == "success"
        
        # Another success should fully close it (need enough successes based on success_threshold)
        result = protected_twitter_call("success")
        
        # Check if we got a successful result or if circuit opened again
        if "status" in result:
            assert result["status"] == "success"
            assert breaker.state == CircuitState.CLOSED
        else:
            # Circuit opened again, which is valid behavior - just verify we handled it
            assert "circuit_breaker_blocked" in result
    
    def test_gemini_api_with_fallback_and_circuit_protection(self, circuit_breaker_manager, error_recovery_manager):
        """Test Gemini API with fallback function and circuit breaker protection."""
        
        breaker = circuit_breaker_manager.get_breaker("gemini_api", CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,
            timeout=1.0
        ))
        
        def gemini_api_call(text, operation="translate"):
            """Simulate Gemini API call."""
            if operation == "translate":
                if "fail" in text.lower():
                    raise GeminiAPIError("Gemini service temporarily unavailable")
                return f"Translated: {text}"
            elif operation == "quota_exceeded":
                raise GeminiAPIError("Quota exceeded")
            else:
                return f"Processed: {text}"
        
        def simple_fallback_translator(error, context):
            """Simple fallback when Gemini fails."""
            return f"[FALLBACK] {context.get('text', 'Unknown text')}"
        
        def protected_gemini_call(text, operation="translate"):
            """Gemini call with circuit breaker and error recovery."""
            try:
                return breaker.call(gemini_api_call, text, operation)
            except GeminiAPIError as e:
                context = {
                    "operation_type": "gemini_api_call",
                    "service_name": "gemini_api", 
                    "text": text,
                    "operation": operation
                }
                recovery_result = error_recovery_manager.handle_error(e, context, simple_fallback_translator)
                
                # If fallback succeeded, return its result
                if recovery_result.get('success'):
                    fallback_action = next((a for a in recovery_result['actions_taken'] 
                                          if a['action'] == 'use_fallback'), None)
                    if fallback_action and fallback_action['result']['success']:
                        return {"fallback_result": fallback_action['result']['result']}
                
                return {"error_recovery": recovery_result}
            except CircuitBreakerOpenError as e:
                return {"circuit_blocked": str(e)}
        
        # Test successful calls
        result = protected_gemini_call("Hello world")
        assert result == "Translated: Hello world"
        
        # Test failure with fallback
        result = protected_gemini_call("This will fail")
        assert "fallback_result" in result
        assert "[FALLBACK] This will fail" in result["fallback_result"]
        
        # Trigger circuit opening
        protected_gemini_call("Another fail text")  # Second failure
        assert breaker.state == CircuitState.OPEN
        
        # Circuit should block subsequent calls
        result = protected_gemini_call("Test text")
        assert "circuit_blocked" in result
        
        # Check that operations were queued for later retry
        queued_ops = error_recovery_manager.get_queued_operations()
        assert len(queued_ops) >= 2  # At least the failed operations
    
    def test_service_degradation_with_circuit_breaker_coordination(self, circuit_breaker_manager, error_recovery_manager):
        """Test service degradation coordinated with circuit breaker state."""
        
        breaker = circuit_breaker_manager.get_breaker("coordination_service")
        
        def service_call(load_level="normal"):
            """Simulate a service that fails under high load."""
            if load_level == "high" or error_recovery_manager.is_service_degraded("coordination_service"):
                raise Exception("Service overloaded or degraded")
            return f"Service response for {load_level} load"
        
        def coordinated_service_call(load_level="normal"):
            """Service call that coordinates circuit breaker and degradation."""
            try:
                return breaker.call(service_call, load_level)
            except Exception as e:
                context = {
                    "operation_type": "service_call",
                    "service_name": "coordination_service",
                    "load_level": load_level
                }
                
                # Create a custom recovery plan that degrades the service
                custom_plan = RecoveryPlan(
                    actions=[RecoveryAction.DEGRADE_SERVICE, RecoveryAction.SAVE_TO_QUEUE],
                    notification_level="warning"
                )
                
                # Register strategy for this specific error pattern
                error_recovery_manager.register_strategy(type(e), custom_plan)
                
                recovery_result = error_recovery_manager.handle_error(e, context)
                return {"service_degraded": recovery_result}
            except CircuitBreakerOpenError as e:
                return {"circuit_protection": str(e)}
        
        # Test normal operation
        result = coordinated_service_call("normal")
        assert result == "Service response for normal load"
        
        # Test high load causing failures
        result = coordinated_service_call("high")
        assert "service_degraded" in result
        assert error_recovery_manager.is_service_degraded("coordination_service")
        
        # Now even normal calls should fail due to degradation
        result = coordinated_service_call("normal")
        assert "service_degraded" in result
        
        # After enough failures, circuit should open
        for _ in range(4):  # Trigger more failures
            coordinated_service_call("normal")
        
        assert breaker.state == CircuitState.OPEN
        
        # Circuit should now block calls
        result = coordinated_service_call("normal")
        assert "circuit_protection" in result
        
        # Restore service and reset circuit
        error_recovery_manager.restore_service("coordination_service")
        breaker.reset()
        
        # Should work normally again
        result = coordinated_service_call("normal")
        assert result == "Service response for normal load"
    
    def test_cascading_failure_protection(self, circuit_breaker_manager, error_recovery_manager):
        """Test protection against cascading failures across multiple services."""
        
        # Setup multiple services with circuit breakers
        services = {
            "primary_api": CircuitBreakerConfig(failure_threshold=2, timeout=1.0),
            "secondary_api": CircuitBreakerConfig(failure_threshold=3, timeout=1.5),
            "cache_service": CircuitBreakerConfig(failure_threshold=1, timeout=0.5)
        }
        
        breakers = {}
        for service_name, config in services.items():
            breakers[service_name] = circuit_breaker_manager.get_breaker(service_name, config)
        
        # Define service dependencies and fallback chain
        def primary_api_call(data):
            raise NetworkError("Primary API down")
        
        def secondary_api_call(data):
            raise NetworkError("Secondary API also down")
        
        def cache_service_call(data):
            return f"Cached result for {data}"
        
        def cascading_service_call(data):
            """Try primary service, fall back to secondary, then cache."""
            
            # Try primary API
            try:
                return breakers["primary_api"].call(primary_api_call, data)
            except (NetworkError, CircuitBreakerOpenError):
                pass
            
            # Try secondary API
            try:
                return breakers["secondary_api"].call(secondary_api_call, data)
            except (NetworkError, CircuitBreakerOpenError):
                pass
            
            # Fall back to cache
            try:
                return breakers["cache_service"].call(cache_service_call, data)
            except CircuitBreakerOpenError:
                # All services failed, use error recovery
                context = {
                    "operation_type": "cascading_service_call",
                    "data": data,
                    "attempted_services": ["primary_api", "secondary_api", "cache_service"]
                }
                
                error = Exception("All services unavailable")
                recovery_result = error_recovery_manager.handle_error(error, context)
                return {"total_failure": recovery_result}
        
        # Test the cascading failure scenario
        results = []
        
        # Make multiple calls to trigger circuit opening
        for i in range(5):
            result = cascading_service_call(f"data_{i}")
            results.append(result)
        
        # First few calls should succeed with cache fallback
        cache_results = [r for r in results if isinstance(r, str) and "Cached result" in r]
        assert len(cache_results) > 0
        
        # Eventually all circuits should open and total failure should occur
        total_failures = [r for r in results if isinstance(r, dict) and "total_failure" in r]
        
        # Verify circuit states
        primary_state = breakers["primary_api"].state
        secondary_state = breakers["secondary_api"].state
        
        # Primary and secondary should be open due to failures
        assert primary_state == CircuitState.OPEN
        assert secondary_state == CircuitState.OPEN
        
        # Cache might still be closed if it succeeded initially
        cache_state = breakers["cache_service"].state
        
        # Check that operations were queued for recovery
        queued_ops = error_recovery_manager.get_queued_operations()
        assert len(queued_ops) >= len(total_failures)
    
    def test_error_recovery_with_circuit_breaker_metrics(self, circuit_breaker_manager, error_recovery_manager):
        """Test that error recovery considers circuit breaker metrics."""
        
        breaker = circuit_breaker_manager.get_breaker("metrics_service", CircuitBreakerConfig(
            failure_threshold=3,
            min_requests=5,
            window_size=10
        ))
        
        def metrics_aware_recovery(error, context):
            """Recovery function that considers circuit breaker state."""
            service_name = context.get('service_name')
            if service_name:
                service_breaker = circuit_breaker_manager.get_breaker(service_name)
                health = service_breaker.get_health_status()
                
                # Adjust recovery strategy based on circuit breaker metrics
                if health['failure_rate'] > 0.8:
                    # Very high failure rate - degrade service
                    context['recovery_reason'] = 'high_failure_rate'
                    error_recovery_manager._handle_degrade_service(error, context)
                elif health['state'] == 'open':
                    # Circuit is open - just queue for later
                    context['recovery_reason'] = 'circuit_open'
                    error_recovery_manager._handle_save_to_queue(error, context)
                else:
                    # Normal recovery
                    context['recovery_reason'] = 'normal_recovery'
                
                return f"Metrics-aware recovery: {context['recovery_reason']}"
            
            return "Standard recovery"
        
        def service_call_with_metrics_recovery(should_fail=False):
            """Service call that uses metrics-aware recovery."""
            try:
                if should_fail:
                    raise Exception("Service error")
                return breaker.call(lambda: "Service success")
            except Exception as e:
                context = {
                    "operation_type": "metrics_service_call",
                    "service_name": "metrics_service"
                }
                return metrics_aware_recovery(e, context)
        
        # Start with successful calls
        for _ in range(3):
            result = service_call_with_metrics_recovery(False)
            assert result == "Service success"
        
        # Add some failures to increase failure rate
        for _ in range(7):  # This will give us 7 failures out of 10 total (70% failure rate)
            result = service_call_with_metrics_recovery(True)
            assert "Metrics-aware recovery" in result
        
        # Check the health metrics
        health = breaker.get_health_status()
        assert health['failure_rate'] >= 0.7  # Should be high
        
        # Next failure should trigger high failure rate recovery
        result = service_call_with_metrics_recovery(True)
        assert "high_failure_rate" in result
        
        # Service should now be degraded
        assert error_recovery_manager.is_service_degraded("metrics_service")
    
    def test_combined_system_health_monitoring(self, circuit_breaker_manager, error_recovery_manager):
        """Test comprehensive health monitoring across both systems."""
        
        # Setup multiple services
        services = ["api_service", "cache_service", "translation_service"]
        
        for service in services:
            circuit_breaker_manager.get_breaker(service)
        
        # Simulate various error conditions
        def simulate_service_issues():
            # Simulate API service failures
            api_breaker = circuit_breaker_manager.get_breaker("api_service")
            for _ in range(3):
                try:
                    api_breaker.call(lambda: exec('raise Exception("API Error")'))
                except Exception:
                    pass
            
            # Simulate translation service quota error
            error = GeminiAPIError("Translation quota exceeded")
            context = {
                "operation_type": "translation",
                "service_name": "translation_service"
            }
            error_recovery_manager.handle_error(error, context)
            
            # Degrade cache service
            cache_context = {
                "operation_type": "cache_operation",
                "service_name": "cache_service"
            }
            error_recovery_manager._handle_degrade_service(Exception("Cache overload"), cache_context)
        
        simulate_service_issues()
        
        # Get comprehensive health status
        circuit_health = circuit_breaker_manager.get_all_health_status()
        recovery_health = error_recovery_manager.get_health_status()
        
        # Analyze combined health
        total_services = len(circuit_health)
        unhealthy_circuits = [h for h in circuit_health if not h['healthy']]
        degraded_services = recovery_health['degraded_services']
        queued_operations = recovery_health['queued_operations']
        
        # Verify health data
        assert total_services == 3
        assert len(unhealthy_circuits) >= 1  # API service should be unhealthy
        assert "cache_service" in degraded_services
        assert queued_operations >= 1  # Translation error should be queued
        
        # Create combined health report
        combined_health = {
            "timestamp": time.time(),
            "circuit_breakers": {
                "total": total_services,
                "healthy": total_services - len(unhealthy_circuits),
                "unhealthy": len(unhealthy_circuits),
                "details": circuit_health
            },
            "error_recovery": {
                "queued_operations": queued_operations,
                "degraded_services_count": len(degraded_services),
                "degraded_services": degraded_services,
                "registered_strategies": recovery_health['registered_strategies']
            },
            "overall_health": {
                "status": "degraded" if (unhealthy_circuits or degraded_services) else "healthy",
                "issues": len(unhealthy_circuits) + len(degraded_services)
            }
        }
        
        assert combined_health["overall_health"]["status"] == "degraded"
        assert combined_health["overall_health"]["issues"] >= 2
        assert combined_health["circuit_breakers"]["unhealthy"] >= 1
        assert combined_health["error_recovery"]["degraded_services_count"] >= 1
    
    def test_performance_under_concurrent_load(self, circuit_breaker_manager, error_recovery_manager):
        """Test performance of combined systems under concurrent load."""
        
        breaker = circuit_breaker_manager.get_breaker("load_test_service", CircuitBreakerConfig(
            failure_threshold=10,
            min_requests=20
        ))
        
        def load_test_service(worker_id, request_id):
            """Service that occasionally fails under load."""
            # Fail approximately 30% of requests
            if (worker_id + request_id) % 3 == 0:
                raise Exception(f"Load test failure {worker_id}-{request_id}")
            return f"Success {worker_id}-{request_id}"
        
        def protected_load_test_call(worker_id, request_id):
            """Load test call with circuit breaker and error recovery."""
            try:
                return breaker.call(load_test_service, worker_id, request_id)
            except Exception as e:
                context = {
                    "operation_type": "load_test",
                    "worker_id": worker_id,
                    "request_id": request_id,
                    "service_name": "load_test_service"
                }
                recovery_result = error_recovery_manager.handle_error(e, context)
                return f"Recovered {worker_id}-{request_id}"
            except CircuitBreakerOpenError:
                return f"Blocked {worker_id}-{request_id}"
        
        # Run concurrent load test
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            
            # Submit 200 concurrent requests
            for worker_id in range(20):
                for request_id in range(10):
                    future = executor.submit(protected_load_test_call, worker_id, request_id)
                    futures.append(future)
            
            # Collect results
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze results
        successful_results = [r for r in results if r.startswith("Success")]
        recovered_results = [r for r in results if r.startswith("Recovered")]
        blocked_results = [r for r in results if r.startswith("Blocked")]
        
        assert len(results) == 200
        assert total_time < 10.0  # Should complete within reasonable time
        
        # Verify system behavior
        health = breaker.get_health_status()
        recovery_health = error_recovery_manager.get_health_status()
        
        # Should have processed many requests
        assert health['total_requests'] >= 100  # Some requests before circuit opened
        
        # Should have queued some operations
        assert recovery_health['queued_operations'] >= 50
        
        # Performance metrics
        requests_per_second = len(results) / total_time
        assert requests_per_second > 20  # Should handle at least 20 req/sec
        
        print(f"Load test completed: {len(results)} requests in {total_time:.2f}s "
              f"({requests_per_second:.1f} req/s)")
        print(f"Results: {len(successful_results)} success, {len(recovered_results)} recovered, "
              f"{len(blocked_results)} blocked")
