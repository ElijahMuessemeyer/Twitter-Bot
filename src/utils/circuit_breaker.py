# =============================================================================
# CIRCUIT BREAKER PATTERN
# =============================================================================
# Prevents cascade failures by tracking API health and implementing CLOSED/OPEN/HALF_OPEN states

import time
import threading
from enum import Enum
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass
from collections import deque
from ..utils.logger import logger
from ..utils.structured_logger import structured_logger


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation, requests allowed
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    failure_threshold: int = 5  # Number of failures to open circuit
    success_threshold: int = 3  # Number of successes to close circuit in half-open
    timeout: float = 60.0  # Time to wait before trying half-open (seconds)
    failure_rate_threshold: float = 0.5  # Percentage of requests that must fail
    min_requests: int = 10  # Minimum requests before calculating failure rate
    window_size: int = 100  # Size of sliding window for tracking requests


@dataclass
class RequestResult:
    """Result of a single request through circuit breaker"""
    timestamp: float
    success: bool
    duration: float
    error_type: Optional[str] = None


class CircuitBreaker:
    """
    Circuit breaker implementation for protecting services from cascading failures
    """
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.lock = threading.RLock()
        
        # Sliding window for tracking recent requests
        self.request_history: deque = deque(maxlen=self.config.window_size)
        
        # Metrics
        self.total_requests = 0
        self.total_failures = 0
        self.total_successes = 0
        self.last_state_change = time.time()
        
    def _record_request(self, success: bool, duration: float, error_type: Optional[str] = None):
        """Record the result of a request"""
        result = RequestResult(
            timestamp=time.time(),
            success=success,
            duration=duration,
            error_type=error_type
        )
        
        with self.lock:
            self.request_history.append(result)
            self.total_requests += 1
            
            if success:
                self.total_successes += 1
                self.failure_count = 0
                self.success_count += 1
            else:
                self.total_failures += 1
                self.failure_count += 1
                self.success_count = 0
                self.last_failure_time = time.time()
    
    def _calculate_failure_rate(self) -> float:
        """Calculate current failure rate from sliding window"""
        if not self.request_history:
            return 0.0
        
        failures = sum(1 for r in self.request_history if not r.success)
        return failures / len(self.request_history)
    
    def _should_open_circuit(self) -> bool:
        """Determine if circuit should be opened"""
        # Check for consecutive failures first (can trigger regardless of min_requests)
        consecutive_failures = self.failure_count >= self.config.failure_threshold
        if consecutive_failures:
            return True
        
        # For failure rate calculation, need enough requests to make a decision
        if len(self.request_history) < self.config.min_requests:
            return False
        
        failure_rate = self._calculate_failure_rate()
        high_failure_rate = failure_rate >= self.config.failure_rate_threshold
        
        return high_failure_rate
    
    def _should_close_circuit(self) -> bool:
        """Determine if circuit should be closed (in half-open state)"""
        return self.success_count >= self.config.success_threshold
    
    def _can_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        return time.time() - self.last_failure_time >= self.config.timeout
    
    def _update_state(self):
        """Update circuit breaker state based on current conditions"""
        previous_state = self.state
        
        if self.state == CircuitState.CLOSED:
            if self._should_open_circuit():
                self.state = CircuitState.OPEN
                self.last_state_change = time.time()
                
        elif self.state == CircuitState.OPEN:
            if self._can_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = time.time()
                
        elif self.state == CircuitState.HALF_OPEN:
            if self._should_close_circuit():
                self.state = CircuitState.CLOSED
                self.last_state_change = time.time()
            elif self.failure_count >= self.config.failure_threshold:
                # Only reopen if we have new consecutive failures in half-open
                self.state = CircuitState.OPEN
                self.last_state_change = time.time()
        
        # Log state changes
        if previous_state != self.state:
            structured_logger.warning(
                f"Circuit breaker '{self.name}' state changed: {previous_state.value} -> {self.state.value}",
                event="circuit_breaker_state_change",
                circuit_name=self.name,
                previous_state=previous_state.value,
                new_state=self.state.value,
                failure_count=self.failure_count,
                success_count=self.success_count,
                failure_rate=self._calculate_failure_rate()
            )
    
    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker
        
        Raises:
            CircuitBreakerOpenError: When circuit is open and blocking requests
        """
        with self.lock:
            self._update_state()
            
            # Block request if circuit is open
            if self.state == CircuitState.OPEN:
                structured_logger.warning(
                    f"Circuit breaker '{self.name}' is OPEN, blocking request",
                    event="circuit_breaker_blocked_request",
                    circuit_name=self.name,
                    state=self.state.value
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN. Service appears to be failing."
                )
            
            # Allow limited requests in half-open state
            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit breaker '{self.name}' is HALF_OPEN, testing service health")
        
        # Execute the function and track result
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Record success
            self._record_request(success=True, duration=duration)
            
            # Update state after recording success
            with self.lock:
                self._update_state()
            
            structured_logger.debug(
                f"Circuit breaker '{self.name}' recorded successful request",
                event="circuit_breaker_success",
                circuit_name=self.name,
                duration_ms=duration * 1000,
                state=self.state.value
            )
            
            return result
            
        except Exception as exc:
            duration = time.time() - start_time
            
            # Record failure
            self._record_request(
                success=False, 
                duration=duration, 
                error_type=exc.__class__.__name__
            )
            
            # Update state after recording failure
            with self.lock:
                self._update_state()
            
            structured_logger.warning(
                f"Circuit breaker '{self.name}' recorded failed request",
                event="circuit_breaker_failure", 
                circuit_name=self.name,
                duration_ms=duration * 1000,
                state=self.state.value,
                error_type=exc.__class__.__name__,
                error_message=str(exc)
            )
            
            raise
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status and metrics"""
        with self.lock:
            self._update_state()
            
            recent_failures = sum(1 for r in self.request_history if not r.success)
            recent_requests = len(self.request_history)
            
            return {
                'name': self.name,
                'state': self.state.value,
                'healthy': self.state == CircuitState.CLOSED,
                'failure_count': self.failure_count,
                'success_count': self.success_count,
                'total_requests': self.total_requests,
                'total_failures': self.total_failures,
                'total_successes': self.total_successes,
                'failure_rate': self._calculate_failure_rate(),
                'recent_requests': recent_requests,
                'recent_failures': recent_failures,
                'last_failure_time': self.last_failure_time,
                'last_state_change': self.last_state_change,
                'time_since_last_failure': time.time() - self.last_failure_time if self.last_failure_time > 0 else None,
                'config': {
                    'failure_threshold': self.config.failure_threshold,
                    'success_threshold': self.config.success_threshold,
                    'timeout': self.config.timeout,
                    'failure_rate_threshold': self.config.failure_rate_threshold
                }
            }
    
    def reset(self):
        """Manually reset circuit breaker to closed state"""
        with self.lock:
            previous_state = self.state
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_state_change = time.time()
            
            structured_logger.info(
                f"Circuit breaker '{self.name}' manually reset",
                event="circuit_breaker_manual_reset",
                circuit_name=self.name,
                previous_state=previous_state.value,
                new_state=self.state.value
            )


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open and blocking requests"""
    pass


class CircuitBreakerManager:
    """
    Manages multiple circuit breakers for different services
    """
    
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()
    
    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create a circuit breaker for a service"""
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]
    
    def call(self, service_name: str, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Execute a function through the appropriate circuit breaker"""
        breaker = self.get_breaker(service_name)
        return breaker.call(func, *args, **kwargs)
    
    def get_all_health_status(self) -> List[Dict[str, Any]]:
        """Get health status for all circuit breakers"""
        with self._lock:
            return [breaker.get_health_status() for breaker in self._breakers.values()]
    
    def reset_all(self):
        """Reset all circuit breakers"""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()
    
    def reset_breaker(self, name: str):
        """Reset a specific circuit breaker"""
        with self._lock:
            if name in self._breakers:
                self._breakers[name].reset()


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()

# Convenience function for protected calls
def protected_call(service_name: str, func: Callable[..., Any], *args, **kwargs) -> Any:
    """Execute a function with circuit breaker protection"""
    return circuit_breaker_manager.call(service_name, func, *args, **kwargs)


# Decorator for automatic circuit breaker protection
def circuit_breaker_protection(service_name: str, config: Optional[CircuitBreakerConfig] = None):
    """
    Decorator to automatically protect functions with circuit breaker
    
    Usage:
        @circuit_breaker_protection("twitter_api")
        def fetch_tweets():
            # This function is now protected by circuit breaker
            pass
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # Get or create circuit breaker for this service
        breaker = circuit_breaker_manager.get_breaker(service_name, config)
        
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    
    return decorator
