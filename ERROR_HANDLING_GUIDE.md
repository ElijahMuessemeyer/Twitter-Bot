# Error Handling and Resilience Guide

This document describes the comprehensive error handling and resilience patterns implemented in the Twitter translation bot.

## Overview

The error handling system consists of four main components:

1. **Custom Exception Hierarchy** - Specific error types for different failure modes
2. **Retry Logic with Exponential Backoff** - Automatic retry of transient failures
3. **Circuit Breaker Pattern** - Prevents cascade failures by isolating failing services
4. **Error Recovery Strategies** - Intelligent fallback and recovery mechanisms

## Custom Exception Hierarchy

### Base Exceptions

All custom exceptions inherit from `TwitterBotError`:

```python
from src.exceptions import TwitterBotError

try:
    risky_operation()
except TwitterBotError as e:
    # Handle any bot-related error
    print(f"Bot error: {e}")
    print(f"Retryable: {e.retryable}")
    print(f"Context: {e.context}")
```

### Twitter API Exceptions

```python
from src.exceptions import (
    TwitterAPIError,        # General Twitter API errors
    TwitterRateLimitError,  # Rate limits exceeded
    TwitterAuthError,       # Authentication failures
    TwitterConnectionError, # Network/connection issues
    TwitterQuotaExceededError # Daily/monthly limits
)

try:
    twitter_monitor.get_new_tweets()
except TwitterRateLimitError as e:
    print(f"Rate limited until: {e.reset_time}")
except TwitterQuotaExceededError as e:
    print(f"Quota: {e.current_usage}/{e.quota_limit}")
```

### Gemini API Exceptions

```python
from src.exceptions import (
    GeminiAPIError,         # General Gemini API errors
    GeminiQuotaError,       # Quota/billing issues
    GeminiUnavailableError, # Service unavailable
    GeminiRateLimitError,   # Rate limits
    GeminiAuthError         # Authentication errors
)

try:
    gemini_translator.translate_tweet(tweet, "Japanese")
except GeminiQuotaError as e:
    print(f"Gemini quota exceeded: {e.quota_type}")
```

### Translation-Specific Exceptions

```python
from src.exceptions import (
    TranslationError,           # General translation failures
    TranslationTimeoutError,    # Translation timeouts
    TranslationValidationError, # Invalid translation results
    TranslationCacheError       # Cache operation failures
)
```

## Retry Logic with Exponential Backoff

### Using the Retry Decorator

```python
from src.utils.retry import retry_with_backoff, RetryConfig
from src.exceptions import NetworkError

@retry_with_backoff(
    retryable_exceptions=(NetworkError, ConnectionError),
    config=RetryConfig(
        max_attempts=5,
        base_delay=1.0,
        max_delay=60.0,
        exponential_base=2.0
    )
)
def fetch_data():
    # This function will be retried on NetworkError or ConnectionError
    return api_call()
```

### Manual Retry Execution

```python
from src.utils.retry import execute_with_retry

result = execute_with_retry(
    risky_function,
    arg1, arg2,
    config=RetryConfig(max_attempts=3),
    retryable_exceptions=(NetworkError,),
    kwarg1="value"
)
```

### Retry Strategies by Error Type

The system has predefined retry strategies:

- **NetworkError**: 5 attempts, aggressive retry (1s → 2s → 4s → 8s → 16s)
- **TwitterConnectionError**: 3 attempts, moderate retry (2s → 4s → 8s)
- **TwitterRateLimitError**: 2 attempts, long delays (60s → 90s)
- **GeminiRateLimitError**: 3 attempts, short delays (5s → 10s → 20s)

## Circuit Breaker Pattern

### Automatic Circuit Breaker Protection

```python
from src.utils.circuit_breaker import circuit_breaker_protection, CircuitBreakerConfig

@circuit_breaker_protection(
    "external_api",
    config=CircuitBreakerConfig(
        failure_threshold=5,    # Open after 5 failures
        timeout=120.0,          # Wait 2 minutes before retry
        success_threshold=3     # Close after 3 successes
    )
)
def call_external_api():
    return external_api.get_data()
```

### Manual Circuit Breaker Usage

```python
from src.utils.circuit_breaker import circuit_breaker_manager

try:
    result = circuit_breaker_manager.call("service_name", risky_function, arg1, arg2)
except CircuitBreakerOpenError:
    # Service is currently failing, circuit is open
    return fallback_result()
```

### Circuit Breaker States

1. **CLOSED** (Normal): All requests pass through
2. **OPEN** (Failing): All requests are blocked
3. **HALF_OPEN** (Testing): Limited requests allowed to test recovery

### Health Monitoring

```python
from src.utils.circuit_breaker import circuit_breaker_manager

# Get health status for all circuit breakers
health_status = circuit_breaker_manager.get_all_health_status()

for breaker in health_status:
    print(f"{breaker['name']}: {breaker['state']}")
    print(f"  Healthy: {breaker['healthy']}")
    print(f"  Failures: {breaker['failure_count']}")
    print(f"  Failure Rate: {breaker['failure_rate']:.2%}")
```

## Error Recovery Strategies

### Automatic Error Recovery

The bot automatically handles errors based on registered recovery strategies:

```python
from src.utils.error_recovery import recover_from_error

try:
    result = risky_operation()
except Exception as e:
    recovery_result = recover_from_error(
        e,
        {
            'operation_type': 'translate_tweet',
            'service': 'gemini_api',
            'tweet_id': '123'
        },
        fallback_func=lambda err, ctx: "fallback_translation"
    )
    
    if recovery_result['success']:
        print("Recovery successful!")
    else:
        print(f"Recovery failed: {recovery_result}")
```

### Recovery Actions

1. **RETRY_WITH_BACKOFF**: Retry with exponential backoff
2. **SAVE_TO_QUEUE**: Queue operation for later retry
3. **USE_FALLBACK**: Execute fallback function
4. **DEGRADE_SERVICE**: Mark service as degraded
5. **NOTIFY_ADMIN**: Send admin notification
6. **SKIP_OPERATION**: Skip and continue

### Custom Recovery Strategies

```python
from src.utils.error_recovery import error_recovery_manager, RecoveryPlan, RecoveryAction

# Register custom recovery strategy
custom_plan = RecoveryPlan(
    actions=[RecoveryAction.USE_FALLBACK, RecoveryAction.SAVE_TO_QUEUE],
    fallback_func=my_fallback_function,
    notification_level="warning"
)

error_recovery_manager.register_strategy(MyCustomError, custom_plan)
```

### Queued Operations

Failed operations are queued for later retry:

```python
from src.utils.error_recovery import error_recovery_manager

# Get queued operations
queued_ops = error_recovery_manager.get_queued_operations()
print(f"Operations in queue: {len(queued_ops)}")

# Retry queued operations
retry_result = error_recovery_manager.retry_queued_operations(max_operations=10)
print(f"Processed: {retry_result['processed']}")
print(f"Successful: {retry_result['successful']}")
print(f"Failed: {retry_result['failed']}")
```

## Service Integration

### Twitter Monitor Service

Enhanced with specific error handling:

```python
try:
    tweets = twitter_monitor.get_new_tweets()
except TwitterQuotaExceededError:
    logger.warning("Daily quota exceeded, will try again tomorrow")
except TwitterRateLimitError as e:
    logger.info(f"Rate limited, retry after {e.reset_time}")
except TwitterAuthError:
    logger.error("Authentication failed, check credentials")
```

### Gemini Translator Service

Includes circuit breaker protection and retry logic:

```python
try:
    translation = gemini_translator.translate_tweet(tweet, "Japanese")
except GeminiQuotaError:
    logger.error("Gemini quota exceeded")
    # Automatically queued for later retry
except TranslationError as e:
    logger.error(f"Translation failed: {e}")
    # Fallback mechanisms activated
```

### Twitter Publisher Service

Handles posting failures gracefully:

```python
try:
    success = twitter_publisher.post_translation(translation)
except TwitterQuotaExceededError:
    # Automatically saved as draft
    draft_manager.save_translation_as_draft(translation, lang_config)
```

## Main Application Integration

The main bot loop handles all errors gracefully:

```python
def process_new_tweets(self):
    try:
        tweets = twitter_monitor.get_new_tweets()
        for tweet in tweets:
            # Process each tweet with individual error handling
            for lang_config in settings.TARGET_LANGUAGES:
                try:
                    translation = gemini_translator.translate_tweet(tweet, lang_config['name'])
                    if translation:
                        twitter_publisher.post_translation(translation)
                except GeminiQuotaError:
                    # Skip this language, continue with others
                    continue
                except Exception as e:
                    # Individual error handling per language
                    logger.error(f"Error for {lang_config['name']}: {e}")
                    continue
    except TwitterQuotaExceededError:
        # Stop processing, try again later
        return
    except Exception as e:
        # Final catch-all with error recovery
        recovery_result = recover_from_error(e, {'operation': 'process_tweets'})
```

## Monitoring and Observability

### Health Check Command

```bash
python main.py health
```

Shows:
- Circuit breaker status for all services
- Number of queued operations
- Degraded services
- System health metrics

### Status Command

```bash
python main.py status
```

Shows:
- API usage and limits
- Circuit breaker states
- Pending drafts
- Error recovery queue

### Retry Command

```bash
python main.py retry
```

Manually retry queued operations.

## Testing Error Handling

### Unit Tests

Run error handling tests:

```bash
python -m pytest tests/test_error_handling.py -v
```

### Manual Testing

Test specific error scenarios:

```python
# Test circuit breaker
from src.utils.circuit_breaker import circuit_breaker_manager

# Simulate failures to open circuit
for i in range(6):
    try:
        circuit_breaker_manager.call("test", lambda: (_ for _ in ()).throw(Exception("fail")))
    except:
        pass

# Check status
health = circuit_breaker_manager.get_all_health_status()
print(health)
```

## Best Practices

1. **Use Specific Exceptions**: Always raise the most specific exception type
2. **Include Context**: Add relevant context information to exceptions
3. **Design for Graceful Degradation**: Implement fallbacks for non-critical failures
4. **Monitor Health**: Regularly check circuit breaker and error recovery health
5. **Queue Non-Critical Operations**: Use the queue for operations that can be delayed
6. **Test Error Scenarios**: Regularly test error handling paths

## Configuration

Error handling behavior can be configured through:

1. **Environment Variables**: API timeouts, retry limits
2. **Circuit Breaker Configs**: Per-service failure thresholds
3. **Recovery Strategies**: Custom recovery actions
4. **Logging Levels**: Error reporting verbosity

## Troubleshooting

### Common Issues

1. **Circuit Breaker Stuck Open**
   - Check service health
   - Consider manual reset: `circuit_breaker_manager.reset_breaker("service_name")`

2. **Queue Growing Too Large**
   - Run manual retry: `python main.py retry`
   - Check for persistent failures

3. **High Error Rates**
   - Check API credentials and quotas
   - Verify network connectivity
   - Review service health dashboard

### Debug Commands

```bash
# Check system health
python main.py health

# View error recovery queue
python main.py status

# Test API connections
python main.py test

# Manual retry of queued operations
python main.py retry
```

This error handling system provides comprehensive resilience and graceful degradation, ensuring the bot continues operating even when individual services experience issues.
