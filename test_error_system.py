#!/usr/bin/env python3
"""
Test script to verify error handling system without external dependencies
"""

import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_exceptions():
    """Test custom exception hierarchy"""
    print("🧪 Testing Exception Hierarchy...")
    
    from src.exceptions import (
        TwitterAPIError,
        TwitterRateLimitError,
        GeminiQuotaError,
        TranslationError
    )
    
    # Test Twitter API error
    error = TwitterAPIError("Test error", status_code=429, error_code="TEST_ERROR")
    print(f"  ✅ TwitterAPIError: {error}")
    
    # Test rate limit error
    rate_error = TwitterRateLimitError("Rate limited", reset_time=1234567890)
    print(f"  ✅ TwitterRateLimitError: retryable={rate_error.retryable}")
    
    # Test Gemini quota error
    quota_error = GeminiQuotaError("Quota exceeded", quota_type="daily")
    print(f"  ✅ GeminiQuotaError: quota_type={quota_error.quota_type}")
    
    print("  ✅ Exception hierarchy working!")


def test_circuit_breaker():
    """Test circuit breaker functionality"""
    print("🧪 Testing Circuit Breaker...")
    
    from src.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
    
    # Create circuit breaker
    cb = CircuitBreaker('test', CircuitBreakerConfig(failure_threshold=2, min_requests=1))
    print(f"  ✅ Created circuit breaker: {cb.state.value}")
    
    # Test successful call
    result = cb.call(lambda: "success")
    print(f"  ✅ Successful call: {result}")
    
    # Test health status
    health = cb.get_health_status()
    print(f"  ✅ Health check: healthy={health['healthy']}, state={health['state']}")
    
    print("  ✅ Circuit breaker working!")


def test_retry_logic():
    """Test retry with exponential backoff"""
    print("🧪 Testing Retry Logic...")
    
    from src.utils.retry import retry_with_backoff, RetryConfig
    from src.exceptions import NetworkError
    
    call_count = 0
    
    @retry_with_backoff(config=RetryConfig(max_attempts=3, base_delay=0.01))
    def flaky_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise NetworkError("Temporary failure")
        return "success"
    
    result = flaky_function()
    print(f"  ✅ Retry successful: {result}, attempts: {call_count}")
    
    print("  ✅ Retry logic working!")


def test_error_recovery():
    """Test error recovery system"""
    print("🧪 Testing Error Recovery...")
    
    from src.utils.error_recovery import error_recovery_manager, recover_from_error
    from src.exceptions import GeminiQuotaError
    
    # Test error recovery
    error = GeminiQuotaError("Quota exceeded")
    context = {
        'operation_type': 'translate',
        'tweet_id': '123'
    }
    
    result = error_recovery_manager.handle_error(error, context)
    print(f"  ✅ Recovery result: success={result['success']}")
    print(f"  ✅ Actions taken: {len(result['actions_taken'])}")
    
    # Check queued operations
    queued = error_recovery_manager.get_queued_operations()
    print(f"  ✅ Queued operations: {len(queued)}")
    
    # Test health status
    health = error_recovery_manager.get_health_status()
    print(f"  ✅ Recovery health: strategies={health['registered_strategies']}")
    
    print("  ✅ Error recovery working!")


def test_integration():
    """Test integration between components"""
    print("🧪 Testing Integration...")
    
    from src.utils.circuit_breaker import circuit_breaker_manager
    from src.utils.retry import retry_with_backoff, RetryConfig
    from src.exceptions import NetworkError
    
    failure_count = 0
    
    def flaky_service():
        nonlocal failure_count
        failure_count += 1
        if failure_count <= 2:
            raise NetworkError("Service unavailable")
        return "success"
    
    @retry_with_backoff(config=RetryConfig(max_attempts=5, base_delay=0.01))
    def protected_call():
        return circuit_breaker_manager.call("integration_test", flaky_service)
    
    result = protected_call()
    print(f"  ✅ Integration test: {result}, failures: {failure_count}")
    
    # Check circuit breaker health
    health = circuit_breaker_manager.get_all_health_status()
    print(f"  ✅ Circuit breakers: {len(health)} configured")
    
    print("  ✅ Integration working!")


def main():
    """Run all tests"""
    print("🚀 Testing Error Handling and Resilience System")
    print("=" * 50)
    
    try:
        test_exceptions()
        print()
        
        test_circuit_breaker()
        print()
        
        test_retry_logic()
        print()
        
        test_error_recovery()
        print()
        
        test_integration()
        print()
        
        print("🎉 All tests passed! Error handling system is working correctly.")
        
        print("\n📋 System Summary:")
        from src.utils.circuit_breaker import circuit_breaker_manager
        from src.utils.error_recovery import error_recovery_manager
        
        cb_health = circuit_breaker_manager.get_all_health_status()
        recovery_health = error_recovery_manager.get_health_status()
        
        print(f"  🔧 Circuit Breakers: {len(cb_health)} configured")
        print(f"  🔄 Error Recovery: {recovery_health['registered_strategies']} strategies")
        print(f"  📋 Queued Operations: {recovery_health['queued_operations']}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
