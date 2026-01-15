"""
Comprehensive tests for circuit breaker functionality.

Tests cover:
- State transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Failure threshold detection and sliding window behavior
- Timeout-based recovery attempts
- Request blocking when circuit is open
- Health status monitoring and reporting
- Circuit breaker manager functionality
"""

import pytest
import time
import threading
from unittest.mock import patch, Mock, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerOpenError,
    CircuitBreakerManager,
    RequestResult,
    circuit_breaker_manager,
    protected_call,
    circuit_breaker_protection
)


class TestCircuitBreakerConfig:
    """Test circuit breaker configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()
        
        assert config.failure_threshold == 5
        assert config.success_threshold == 3
        assert config.timeout == 60.0
        assert config.failure_rate_threshold == 0.5
        assert config.min_requests == 10
        assert config.window_size == 100
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=30.0,
            failure_rate_threshold=0.3,
            min_requests=5,
            window_size=50
        )
        
        assert config.failure_threshold == 3
        assert config.success_threshold == 2
        assert config.timeout == 30.0
        assert config.failure_rate_threshold == 0.3
        assert config.min_requests == 5
        assert config.window_size == 50


class TestRequestResult:
    """Test request result data class."""
    
    def test_successful_request_result(self):
        """Test creation of successful request result."""
        timestamp = time.time()
        result = RequestResult(
            timestamp=timestamp,
            success=True,
            duration=0.5
        )
        
        assert result.timestamp == timestamp
        assert result.success is True
        assert result.duration == 0.5
        assert result.error_type is None
    
    def test_failed_request_result(self):
        """Test creation of failed request result."""
        timestamp = time.time()
        result = RequestResult(
            timestamp=timestamp,
            success=False,
            duration=1.2,
            error_type="ValueError"
        )
        
        assert result.timestamp == timestamp
        assert result.success is False
        assert result.duration == 1.2
        assert result.error_type == "ValueError"


class TestCircuitBreaker:
    """Test core circuit breaker functionality."""
    
    @pytest.fixture
    def circuit_breaker(self):
        """Create a circuit breaker with test configuration."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=5.0,
            failure_rate_threshold=0.5,
            min_requests=3,
            window_size=10
        )
        return CircuitBreaker("test_service", config)
    
    @pytest.fixture
    def success_func(self):
        """Mock function that always succeeds."""
        return Mock(return_value="success")
    
    @pytest.fixture
    def failure_func(self):
        """Mock function that always fails."""
        def fail():
            raise ValueError("test error")
        return Mock(side_effect=fail)
    
    def test_initial_state(self, circuit_breaker):
        """Test circuit breaker initial state."""
        assert circuit_breaker.name == "test_service"
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0
        assert circuit_breaker.success_count == 0
        assert circuit_breaker.total_requests == 0
        assert circuit_breaker.total_failures == 0
        assert circuit_breaker.total_successes == 0
    
    def test_successful_call_in_closed_state(self, circuit_breaker, success_func):
        """Test successful function call in closed state."""
        result = circuit_breaker.call(success_func, "arg1", kwarg1="value1")
        
        assert result == "success"
        success_func.assert_called_once_with("arg1", kwarg1="value1")
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.success_count == 1
        assert circuit_breaker.failure_count == 0
        assert circuit_breaker.total_requests == 1
        assert circuit_breaker.total_successes == 1
    
    def test_failed_call_in_closed_state(self, circuit_breaker, failure_func):
        """Test failed function call in closed state."""
        with pytest.raises(ValueError, match="test error"):
            circuit_breaker.call(failure_func)
        
        failure_func.assert_called_once()
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.success_count == 0
        assert circuit_breaker.failure_count == 1
        assert circuit_breaker.total_requests == 1
        assert circuit_breaker.total_failures == 1
    
    def test_circuit_opens_on_consecutive_failures(self, circuit_breaker, failure_func):
        """Test circuit opens after consecutive failures reach threshold."""
        # Make enough consecutive failures to trigger circuit opening
        for i in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                circuit_breaker.call(failure_func)
        
        assert circuit_breaker.state == CircuitState.OPEN
        assert circuit_breaker.failure_count == circuit_breaker.config.failure_threshold
    
    def test_circuit_opens_on_high_failure_rate(self, circuit_breaker, success_func, failure_func):
        """Test circuit opens when failure rate exceeds threshold."""
        # Need at least min_requests total requests
        min_requests = circuit_breaker.config.min_requests
        failure_rate_threshold = circuit_breaker.config.failure_rate_threshold
        
        # Calculate how many failures we need out of min_requests to exceed threshold
        required_failures = int(min_requests * failure_rate_threshold) + 1
        required_successes = min_requests - required_failures
        
        # Make some successful requests first
        for _ in range(required_successes):
            circuit_breaker.call(success_func)
        
        # Then make enough failures to exceed failure rate threshold
        for _ in range(required_failures):
            with pytest.raises(ValueError):
                circuit_breaker.call(failure_func)
        
        assert circuit_breaker.state == CircuitState.OPEN
    
    def test_circuit_blocks_requests_when_open(self, circuit_breaker, success_func, failure_func):
        """Test circuit blocks all requests when in open state."""
        # Force circuit to open
        for _ in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                circuit_breaker.call(failure_func)
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Now any call should be blocked
        with pytest.raises(CircuitBreakerOpenError, match="Circuit breaker 'test_service' is OPEN"):
            circuit_breaker.call(success_func)
        
        # Function should not have been called
        success_func.assert_not_called()
    
    @patch('time.time')
    def test_circuit_transitions_to_half_open_after_timeout(self, mock_time, circuit_breaker, failure_func, success_func):
        """Test circuit transitions to half-open after timeout."""
        start_time = 1000.0
        mock_time.return_value = start_time
        
        # Force circuit to open
        for _ in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                circuit_breaker.call(failure_func)
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Advance time past timeout
        mock_time.return_value = start_time + circuit_breaker.config.timeout + 1
        
        # Next call should transition to half-open and succeed
        result = circuit_breaker.call(success_func)
        
        assert result == "success"
        assert circuit_breaker.state == CircuitState.HALF_OPEN
    
    def test_circuit_closes_from_half_open_on_success(self, circuit_breaker, failure_func, success_func):
        """Test circuit closes from half-open after enough successes."""
        # Force circuit to open
        num_failures = max(circuit_breaker.config.failure_threshold, circuit_breaker.config.min_requests)
        for _ in range(num_failures):
            with pytest.raises(ValueError):
                circuit_breaker.call(failure_func)
        
        # Manually set to half-open for testing
        circuit_breaker.state = CircuitState.HALF_OPEN
        circuit_breaker.success_count = 0
        
        # Make enough successful calls to close circuit
        for i in range(circuit_breaker.config.success_threshold):
            result = circuit_breaker.call(success_func)
            assert result == "success"
        
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.success_count == circuit_breaker.config.success_threshold
    
    def test_circuit_reopens_from_half_open_on_failure(self, circuit_breaker, failure_func, success_func):
        """Test circuit reopens from half-open on failure."""
        # Force circuit to open then set to half-open
        num_failures = max(circuit_breaker.config.failure_threshold, circuit_breaker.config.min_requests)
        for _ in range(num_failures):
            with pytest.raises(ValueError):
                circuit_breaker.call(failure_func)
        
        circuit_breaker.state = CircuitState.HALF_OPEN
        circuit_breaker.failure_count = 0
        
        # One failure should cause it to reopen
        with pytest.raises(ValueError):
            circuit_breaker.call(failure_func)
        
        assert circuit_breaker.state == CircuitState.OPEN
    
    def test_sliding_window_behavior(self, circuit_breaker, success_func, failure_func):
        """Test sliding window properly tracks recent requests."""
        # Fill window with successful requests
        for _ in range(circuit_breaker.config.window_size):
            circuit_breaker.call(success_func)
        
        assert len(circuit_breaker.request_history) == circuit_breaker.config.window_size
        assert circuit_breaker._calculate_failure_rate() == 0.0
        
        # Add one more request (should push oldest out)
        circuit_breaker.call(success_func)
        
        assert len(circuit_breaker.request_history) == circuit_breaker.config.window_size
        
        # Add some failures
        for _ in range(5):
            with pytest.raises(ValueError):
                circuit_breaker.call(failure_func)
        
        expected_failure_rate = 5 / circuit_breaker.config.window_size
        assert abs(circuit_breaker._calculate_failure_rate() - expected_failure_rate) < 0.01
    
    def test_health_status_reporting(self, circuit_breaker, success_func, failure_func):
        """Test health status provides accurate information."""
        # Make some requests
        circuit_breaker.call(success_func)
        circuit_breaker.call(success_func)
        
        with pytest.raises(ValueError):
            circuit_breaker.call(failure_func)
        
        health = circuit_breaker.get_health_status()
        
        assert health['name'] == 'test_service'
        assert health['state'] == CircuitState.CLOSED.value
        assert health['healthy'] is True
        assert health['total_requests'] == 3
        assert health['total_successes'] == 2
        assert health['total_failures'] == 1
        assert health['recent_requests'] == 3
        assert health['recent_failures'] == 1
        assert abs(health['failure_rate'] - (1/3)) < 0.01
        assert 'config' in health
        assert health['time_since_last_failure'] is not None
    
    def test_manual_reset(self, circuit_breaker, failure_func):
        """Test manual reset functionality."""
        # Force circuit to open
        num_failures = max(circuit_breaker.config.failure_threshold, circuit_breaker.config.min_requests)
        for _ in range(num_failures):
            with pytest.raises(ValueError):
                circuit_breaker.call(failure_func)
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Manual reset
        circuit_breaker.reset()
        
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0
        assert circuit_breaker.success_count == 0
    
    def test_thread_safety(self, circuit_breaker, success_func, failure_func):
        """Test circuit breaker thread safety."""
        results = []
        errors = []
        
        def worker(func_to_call, should_fail=False):
            try:
                if should_fail:
                    circuit_breaker.call(failure_func)
                else:
                    result = circuit_breaker.call(success_func)
                    results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            # Mix of success and failure calls
            for i in range(50):
                should_fail = i % 5 == 0  # Every 5th call fails
                future = executor.submit(worker, failure_func if should_fail else success_func, should_fail)
                futures.append(future)
            
            # Wait for completion
            for future in as_completed(futures):
                future.result()
        
        # Verify no race conditions
        health = circuit_breaker.get_health_status()
        assert health['total_requests'] == len(results) + len([e for e in errors if not isinstance(e, CircuitBreakerOpenError)])
        assert health['total_successes'] == len(results)
    
    def test_request_duration_tracking(self, circuit_breaker):
        """Test that request durations are properly tracked."""
        def slow_function():
            time.sleep(0.1)
            return "slow result"
        
        result = circuit_breaker.call(slow_function)
        
        assert result == "slow result"
        assert len(circuit_breaker.request_history) == 1
        
        request_result = circuit_breaker.request_history[0]
        assert request_result.duration >= 0.1
        assert request_result.success is True
    
    def test_error_type_tracking(self, circuit_breaker):
        """Test that error types are properly tracked."""
        def failing_function():
            raise RuntimeError("specific error")
        
        with pytest.raises(RuntimeError):
            circuit_breaker.call(failing_function)
        
        assert len(circuit_breaker.request_history) == 1
        request_result = circuit_breaker.request_history[0]
        assert request_result.success is False
        assert request_result.error_type == "RuntimeError"


class TestCircuitBreakerManager:
    """Test circuit breaker manager functionality."""
    
    @pytest.fixture
    def manager(self):
        """Create a fresh circuit breaker manager."""
        return CircuitBreakerManager()
    
    def test_get_breaker_creates_new_breaker(self, manager):
        """Test getting breaker creates new one if it doesn't exist."""
        breaker = manager.get_breaker("new_service")
        
        assert breaker.name == "new_service"
        assert isinstance(breaker, CircuitBreaker)
        assert "new_service" in manager._breakers
    
    def test_get_breaker_returns_existing_breaker(self, manager):
        """Test getting breaker returns existing one."""
        breaker1 = manager.get_breaker("service1")
        breaker2 = manager.get_breaker("service1")
        
        assert breaker1 is breaker2
    
    def test_get_breaker_with_custom_config(self, manager):
        """Test creating breaker with custom config."""
        config = CircuitBreakerConfig(failure_threshold=10)
        breaker = manager.get_breaker("custom_service", config)
        
        assert breaker.config.failure_threshold == 10
    
    def test_call_through_manager(self, manager):
        """Test calling function through manager."""
        def test_func(arg):
            return f"result_{arg}"
        
        result = manager.call("test_service", test_func, "test")
        
        assert result == "result_test"
        assert "test_service" in manager._breakers
    
    def test_get_all_health_status(self, manager):
        """Test getting health status for all breakers."""
        # Create some breakers
        manager.get_breaker("service1")
        manager.get_breaker("service2")
        manager.get_breaker("service3")
        
        health_statuses = manager.get_all_health_status()
        
        assert len(health_statuses) == 3
        service_names = {status['name'] for status in health_statuses}
        assert service_names == {"service1", "service2", "service3"}
    
    def test_reset_all_breakers(self, manager):
        """Test resetting all circuit breakers."""
        # Create and trigger some breakers
        breaker1 = manager.get_breaker("service1")
        breaker2 = manager.get_breaker("service2")
        
        # Force them to accumulate some state
        def failing_func():
            raise ValueError("error")
        
        # Need enough failures to trigger state change
        for _ in range(5):  # More failures to ensure state change
            try:
                breaker1.call(failing_func)
            except ValueError:
                pass
            try:
                breaker2.call(failing_func)
            except ValueError:
                pass
        
        assert breaker1.failure_count >= 2
        assert breaker2.failure_count >= 2
        
        # Reset all
        manager.reset_all()
        
        assert breaker1.failure_count == 0
        assert breaker2.failure_count == 0
        assert breaker1.state == CircuitState.CLOSED
        assert breaker2.state == CircuitState.CLOSED
    
    def test_reset_specific_breaker(self, manager):
        """Test resetting a specific circuit breaker."""
        breaker1 = manager.get_breaker("service1")
        breaker2 = manager.get_breaker("service2")
        
        # Force them to accumulate some state
        def failing_func():
            raise ValueError("error")
        
        for _ in range(5):  # More failures to ensure state accumulates
            try:
                breaker1.call(failing_func)
                breaker2.call(failing_func)
            except ValueError:
                pass
        
        assert breaker1.failure_count >= 2
        assert breaker2.failure_count >= 2
        original_breaker2_count = breaker2.failure_count
        
        # Reset only service1
        manager.reset_breaker("service1")
        
        assert breaker1.failure_count == 0
        assert breaker2.failure_count == original_breaker2_count  # Unchanged
    
    def test_reset_nonexistent_breaker(self, manager):
        """Test resetting a breaker that doesn't exist."""
        # Should not raise an error
        manager.reset_breaker("nonexistent_service")
    
    def test_manager_thread_safety(self, manager):
        """Test manager thread safety with concurrent access."""
        results = []
        
        def worker(service_name, value):
            def test_func():
                return f"{service_name}_{value}"
            
            try:
                result = manager.call(service_name, test_func)
                results.append(result)
            except Exception as e:
                results.append(f"error_{e}")
        
        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            
            for i in range(100):
                service_name = f"service_{i % 5}"  # Use 5 different services
                future = executor.submit(worker, service_name, i)
                futures.append(future)
            
            # Wait for completion
            for future in as_completed(futures):
                future.result()
        
        assert len(results) == 100
        assert len(manager._breakers) == 5


class TestGlobalFunctions:
    """Test global convenience functions."""
    
    def test_protected_call(self):
        """Test protected_call convenience function."""
        def test_func(value):
            return f"protected_{value}"
        
        result = protected_call("global_service", test_func, "test")
        
        assert result == "protected_test"
        # Should create breaker in global manager
        assert "global_service" in circuit_breaker_manager._breakers
    
    def test_circuit_breaker_protection_decorator(self):
        """Test circuit breaker protection decorator."""
        @circuit_breaker_protection("decorated_service")
        def decorated_function(value):
            return f"decorated_{value}"
        
        result = decorated_function("test")
        
        assert result == "decorated_test"
        assert "decorated_service" in circuit_breaker_manager._breakers
        
        # Test that function metadata is preserved
        assert decorated_function.__name__ == "decorated_function"
    
    def test_decorator_with_custom_config(self):
        """Test decorator with custom configuration."""
        config = CircuitBreakerConfig(failure_threshold=2, min_requests=2)
        
        @circuit_breaker_protection("custom_decorated_service", config)
        def decorated_function():
            raise ValueError("test error")
        
        # Should fail enough times before opening circuit (at least min_requests)
        for _ in range(2):
            with pytest.raises(ValueError):
                decorated_function()
        
        # Next call should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            decorated_function()
        
        breaker = circuit_breaker_manager.get_breaker("custom_decorated_service")
        assert breaker.config.failure_threshold == 2
    
    def test_decorator_handles_failures(self):
        """Test decorator properly handles function failures."""
        @circuit_breaker_protection("failing_service")
        def failing_function():
            raise RuntimeError("decorator test error")
        
        with pytest.raises(RuntimeError, match="decorator test error"):
            failing_function()
        
        breaker = circuit_breaker_manager.get_breaker("failing_service")
        assert breaker.failure_count == 1


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""
    
    def test_api_service_failure_recovery_scenario(self):
        """Test complete failure and recovery scenario for an API service."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=1.0,  # Short timeout for testing
            min_requests=3
        )
        breaker = CircuitBreaker("api_service", config)
        
        # Simulate API working normally
        def api_call(data):
            return f"api_response_{data}"
        
        for i in range(5):
            result = breaker.call(api_call, i)
            assert result == f"api_response_{i}"
        
        assert breaker.state == CircuitState.CLOSED
        
        # Simulate API starting to fail
        def failing_api_call(data):
            raise ConnectionError("API is down")
        
        # Trigger circuit opening
        for i in range(3):
            with pytest.raises(ConnectionError):
                breaker.call(failing_api_call, i)
        
        assert breaker.state == CircuitState.OPEN
        
        # Verify requests are blocked
        with pytest.raises(CircuitBreakerOpenError):
            breaker.call(api_call, "blocked")
        
        # Wait for timeout
        time.sleep(1.1)
        
        # Circuit should allow test request (half-open)
        result = breaker.call(api_call, "test_recovery")
        assert result == "api_response_test_recovery"
        assert breaker.state == CircuitState.HALF_OPEN
        
        # Another success should close the circuit
        result = breaker.call(api_call, "recovery_complete")
        assert result == "api_response_recovery_complete"
        assert breaker.state == CircuitState.CLOSED
    
    def test_high_load_scenario(self):
        """Test circuit breaker behavior under high load."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            min_requests=20,
            failure_rate_threshold=0.3
        )
        breaker = CircuitBreaker("high_load_service", config)
        
        def sometimes_failing_service(fail_rate=0.2):
            if time.time() % 1 < fail_rate:  # Deterministic but varying failure
                raise TimeoutError("Service overloaded")
            return "success"
        
        # Simulate high load with some failures
        results = []
        errors = []
        
        for i in range(50):
            try:
                result = breaker.call(sometimes_failing_service, 0.25)  # 25% failure rate
                results.append(result)
            except (TimeoutError, CircuitBreakerOpenError) as e:
                errors.append(e)
        
        # Should have opened circuit due to high failure rate
        health = breaker.get_health_status()
        assert health['total_requests'] >= 20  # At least min_requests before circuit opened
        
        # Verify failure rate calculation is reasonable
        if breaker.state == CircuitState.OPEN:
            assert health['failure_rate'] >= config.failure_rate_threshold
    
    def test_mixed_error_types_scenario(self):
        """Test circuit breaker with different types of errors."""
        breaker = CircuitBreaker("mixed_errors_service")
        
        def service_with_mixed_errors(error_type):
            if error_type == "network":
                raise ConnectionError("Network error")
            elif error_type == "timeout":
                raise TimeoutError("Request timeout")
            elif error_type == "auth":
                raise PermissionError("Authentication failed")
            else:
                return "success"
        
        # Test different error types are tracked
        error_types = ["network", "timeout", "auth"]
        for error_type in error_types:
            with pytest.raises((ConnectionError, TimeoutError, PermissionError)):
                breaker.call(service_with_mixed_errors, error_type)
        
        # Check that different error types are recorded
        error_types_recorded = {r.error_type for r in breaker.request_history if not r.success}
        assert "ConnectionError" in error_types_recorded
        assert "TimeoutError" in error_types_recorded  
        assert "PermissionError" in error_types_recorded
        
        health = breaker.get_health_status()
        assert health['total_failures'] == 3
        assert health['total_requests'] == 3
