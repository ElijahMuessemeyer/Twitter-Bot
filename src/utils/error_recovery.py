# =============================================================================
# ERROR RECOVERY STRATEGIES
# =============================================================================
# Intelligent error recovery and fallback mechanisms

import time
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
from dataclasses import dataclass, field
from ..exceptions import (
    TwitterRateLimitError,
    TwitterQuotaExceededError,
    GeminiAPIError,
    GeminiQuotaError,
    TranslationError,
    NetworkError
)
from ..utils.logger import logger
from ..utils.structured_logger import structured_logger


class RecoveryAction(Enum):
    """Types of recovery actions"""
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    SAVE_TO_QUEUE = "save_to_queue" 
    USE_FALLBACK = "use_fallback"
    DEGRADE_SERVICE = "degrade_service"
    NOTIFY_ADMIN = "notify_admin"
    SKIP_OPERATION = "skip_operation"


@dataclass
class RecoveryPlan:
    """Plan for recovering from a specific error"""
    actions: List[RecoveryAction] = field(default_factory=list)
    retry_delay: float = 0.0
    max_retries: int = 0
    fallback_func: Optional[Callable] = None
    notification_level: str = "warning"
    context: Dict[str, Any] = field(default_factory=dict)


class ErrorRecoveryManager:
    """
    Manages error recovery strategies for different types of failures
    """
    
    def __init__(self):
        self._recovery_strategies: Dict[type, RecoveryPlan] = {}
        self._operation_queue: List[Dict[str, Any]] = []
        self._degraded_services: set = set()
        self._setup_default_strategies()
    
    def _setup_default_strategies(self):
        """Setup default recovery strategies for common errors"""
        
        # Twitter rate limit - wait and retry
        self._recovery_strategies[TwitterRateLimitError] = RecoveryPlan(
            actions=[RecoveryAction.RETRY_WITH_BACKOFF],
            retry_delay=60.0,
            max_retries=2,
            notification_level="info"
        )
        
        # Twitter quota exceeded - queue for later
        self._recovery_strategies[TwitterQuotaExceededError] = RecoveryPlan(
            actions=[RecoveryAction.SAVE_TO_QUEUE, RecoveryAction.NOTIFY_ADMIN],
            notification_level="warning"
        )
        
        # Gemini API errors - retry with shorter delay
        self._recovery_strategies[GeminiAPIError] = RecoveryPlan(
            actions=[RecoveryAction.RETRY_WITH_BACKOFF, RecoveryAction.SAVE_TO_QUEUE],
            retry_delay=10.0,
            max_retries=3,
            notification_level="warning"
        )
        
        # Gemini quota exceeded - use fallback or queue
        self._recovery_strategies[GeminiQuotaError] = RecoveryPlan(
            actions=[RecoveryAction.USE_FALLBACK, RecoveryAction.SAVE_TO_QUEUE, RecoveryAction.NOTIFY_ADMIN],
            notification_level="error"
        )
        
        # Network errors - aggressive retry
        self._recovery_strategies[NetworkError] = RecoveryPlan(
            actions=[RecoveryAction.RETRY_WITH_BACKOFF],
            retry_delay=5.0,
            max_retries=5,
            notification_level="warning"
        )
        
        # Translation errors - try fallback, then queue
        self._recovery_strategies[TranslationError] = RecoveryPlan(
            actions=[RecoveryAction.USE_FALLBACK, RecoveryAction.SAVE_TO_QUEUE],
            notification_level="error"
        )
    
    def register_strategy(self, exception_type: type, plan: RecoveryPlan):
        """Register a custom recovery strategy for an exception type"""
        self._recovery_strategies[exception_type] = plan
        logger.info(f"Registered recovery strategy for {exception_type.__name__}")
    
    def handle_error(
        self, 
        error: Exception, 
        operation_context: Dict[str, Any],
        fallback_func: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Handle an error according to the registered recovery strategy
        
        Returns:
            Dict with recovery result information
        """
        error_type = type(error)
        recovery_plan = self._get_recovery_plan(error_type)
        
        if not recovery_plan:
            # No specific strategy, use default
            recovery_plan = RecoveryPlan(
                actions=[RecoveryAction.NOTIFY_ADMIN],
                notification_level="error"
            )
        
        recovery_result = {
            'error_type': error_type.__name__,
            'error_message': str(error),
            'recovery_actions': [action.value for action in recovery_plan.actions],
            'success': False,
            'actions_taken': []
        }
        
        # Execute recovery actions
        for action in recovery_plan.actions:
            try:
                action_result = self._execute_recovery_action(
                    action, error, operation_context, recovery_plan, fallback_func
                )
                recovery_result['actions_taken'].append({
                    'action': action.value,
                    'result': action_result
                })
                
                # If any action succeeded, mark overall recovery as success
                if action_result.get('success', False):
                    recovery_result['success'] = True
                    break
                    
            except Exception as recovery_error:
                logger.error(f"Recovery action {action.value} failed: {recovery_error}")
                recovery_result['actions_taken'].append({
                    'action': action.value,
                    'result': {'success': False, 'error': str(recovery_error)}
                })
        
        # Log recovery attempt
        structured_logger.info(
            f"Error recovery attempted for {error_type.__name__}",
            event="error_recovery_attempt",
            error_type=error_type.__name__,
            error_message=str(error),
            recovery_success=recovery_result['success'],
            actions_taken=recovery_result['actions_taken'],
            **operation_context
        )
        
        return recovery_result
    
    def _get_recovery_plan(self, error_type: type) -> Optional[RecoveryPlan]:
        """Get recovery plan for error type, checking inheritance hierarchy"""
        # Direct match
        if error_type in self._recovery_strategies:
            return self._recovery_strategies[error_type]
        
        # Check parent classes
        for registered_type, plan in self._recovery_strategies.items():
            if issubclass(error_type, registered_type):
                return plan
        
        return None
    
    def _execute_recovery_action(
        self,
        action: RecoveryAction,
        error: Exception,
        context: Dict[str, Any],
        plan: RecoveryPlan,
        fallback_func: Optional[Callable]
    ) -> Dict[str, Any]:
        """Execute a specific recovery action"""
        
        if action == RecoveryAction.RETRY_WITH_BACKOFF:
            return self._handle_retry(error, context, plan)
        
        elif action == RecoveryAction.SAVE_TO_QUEUE:
            return self._handle_save_to_queue(error, context)
        
        elif action == RecoveryAction.USE_FALLBACK:
            return self._handle_use_fallback(error, context, fallback_func or plan.fallback_func)
        
        elif action == RecoveryAction.DEGRADE_SERVICE:
            return self._handle_degrade_service(error, context)
        
        elif action == RecoveryAction.NOTIFY_ADMIN:
            return self._handle_notify_admin(error, context, plan.notification_level)
        
        elif action == RecoveryAction.SKIP_OPERATION:
            return self._handle_skip_operation(error, context)
        
        else:
            return {'success': False, 'message': f'Unknown recovery action: {action.value}'}
    
    def _handle_retry(self, error: Exception, context: Dict[str, Any], plan: RecoveryPlan) -> Dict[str, Any]:
        """Handle retry with backoff recovery action"""
        # This is more of a signal that retry should be attempted
        # The actual retry logic is handled by the retry decorator
        return {
            'success': False,  # Not actually successful until retry succeeds
            'message': f'Retry recommended with {plan.retry_delay}s delay',
            'retry_delay': plan.retry_delay,
            'max_retries': plan.max_retries
        }
    
    def _handle_save_to_queue(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle save to queue recovery action"""
        queue_item = {
            'timestamp': time.time(),
            'operation_type': context.get('operation_type', 'unknown'),
            'context': context,
            'error': str(error),
            'retry_count': 0
        }
        
        self._operation_queue.append(queue_item)
        
        logger.info(f"Saved failed operation to queue: {context.get('operation_type')}")
        
        return {
            'success': True,
            'message': 'Operation saved to queue for later retry',
            'queue_position': len(self._operation_queue)
        }
    
    def _handle_use_fallback(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        fallback_func: Optional[Callable]
    ) -> Dict[str, Any]:
        """Handle fallback function recovery action"""
        if not fallback_func:
            return {
                'success': False,
                'message': 'No fallback function available'
            }
        
        try:
            result = fallback_func(error, context)
            return {
                'success': True,
                'message': 'Fallback function executed successfully',
                'result': result
            }
        except Exception as fallback_error:
            return {
                'success': False,
                'message': f'Fallback function failed: {fallback_error}',
                'fallback_error': str(fallback_error)
            }
    
    def _handle_degrade_service(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle service degradation recovery action"""
        service_name = context.get('service_name', 'unknown')
        self._degraded_services.add(service_name)
        
        logger.warning(f"Service '{service_name}' degraded due to error: {error}")
        
        return {
            'success': True,
            'message': f'Service {service_name} marked as degraded',
            'degraded_services': list(self._degraded_services)
        }
    
    def _handle_notify_admin(
        self, 
        error: Exception, 
        context: Dict[str, Any], 
        level: str
    ) -> Dict[str, Any]:
        """Handle admin notification recovery action"""
        # For now, just log at appropriate level
        # In production, this could send emails, Slack messages, etc.
        
        log_func = getattr(logger, level, logger.error)
        log_func(f"Admin notification: {error} in context {context}")
        
        return {
            'success': True,
            'message': f'Admin notified at {level} level',
            'notification_level': level
        }
    
    def _handle_skip_operation(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle skip operation recovery action"""
        logger.info(f"Skipping operation due to error: {error}")
        
        return {
            'success': True,
            'message': 'Operation skipped due to error',
            'skipped': True
        }
    
    def get_queued_operations(self) -> List[Dict[str, Any]]:
        """Get list of queued operations"""
        return self._operation_queue.copy()
    
    def retry_queued_operations(self, max_operations: int = 10) -> Dict[str, Any]:
        """Attempt to retry queued operations"""
        if not self._operation_queue:
            return {'message': 'No operations in queue', 'processed': 0}
        
        processed = 0
        successful = 0
        failed = 0
        
        # Process up to max_operations from queue
        operations_to_process = self._operation_queue[:max_operations]
        
        for operation in operations_to_process:
            processed += 1
            
            try:
                # This is a placeholder - in real implementation, you'd have
                # a way to reconstruct and retry the original operation
                logger.info(f"Would retry operation: {operation['operation_type']}")
                successful += 1
                
                # Remove from queue on success
                self._operation_queue.remove(operation)
                
            except Exception as retry_error:
                failed += 1
                operation['retry_count'] += 1
                logger.error(f"Failed to retry queued operation: {retry_error}")
                
                # Remove from queue if too many retries
                if operation['retry_count'] >= 3:
                    self._operation_queue.remove(operation)
        
        return {
            'processed': processed,
            'successful': successful, 
            'failed': failed,
            'remaining_in_queue': len(self._operation_queue)
        }
    
    def is_service_degraded(self, service_name: str) -> bool:
        """Check if a service is currently degraded"""
        return service_name in self._degraded_services
    
    def restore_service(self, service_name: str):
        """Mark a service as restored (no longer degraded)"""
        self._degraded_services.discard(service_name)
        logger.info(f"Service '{service_name}' restored to normal operation")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall recovery system health status"""
        return {
            'queued_operations': len(self._operation_queue),
            'degraded_services': list(self._degraded_services),
            'registered_strategies': len(self._recovery_strategies),
            'strategy_types': [exc.__name__ for exc in self._recovery_strategies.keys()]
        }


# Global error recovery manager
error_recovery_manager = ErrorRecoveryManager()


def recover_from_error(
    error: Exception,
    operation_context: Dict[str, Any],
    fallback_func: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Convenience function for error recovery
    
    Usage:
        try:
            # risky operation
            result = api_call()
        except Exception as e:
            recovery_result = recover_from_error(
                e, 
                {'operation_type': 'api_call', 'service': 'twitter'},
                fallback_func=lambda err, ctx: "fallback_result"
            )
    """
    return error_recovery_manager.handle_error(error, operation_context, fallback_func)
