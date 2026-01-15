# =============================================================================
# SYSTEM STATE REPOSITORY
# =============================================================================

import json
from datetime import datetime, timezone
from typing import Any, Optional, Dict, List
from sqlalchemy.orm import Session
from src.models.database_models import SystemState as SystemStateModel
from src.repositories.base_repository import BaseRepository

class SystemStateRepository(BaseRepository[SystemStateModel]):
    """Repository for system state tracking (replaces file-based state storage)"""
    
    def __init__(self, session: Session):
        super().__init__(session, SystemStateModel)
    
    def set_state(
        self,
        key: str,
        value: Any,
        description: Optional[str] = None,
        state_type: str = 'general'
    ) -> SystemStateModel:
        """Set a system state value"""
        # Convert value to string for storage
        value_str = json.dumps(value) if not isinstance(value, str) else value
        
        # Check if state already exists
        existing = self.get_state_entry(key)
        if existing:
            return self.update(
                existing,
                value=value_str,
                description=description,
                state_type=state_type
            )
        else:
            return self.create(
                key=key,
                value=value_str,
                description=description,
                state_type=state_type
            )
    
    def get_state(self, key: str, default: Any = None) -> Any:
        """Get a system state value"""
        entry = self.get_state_entry(key)
        if not entry or entry.value is None:
            return default
        
        try:
            # Try to parse as JSON first
            parsed_value = json.loads(entry.value)
            return parsed_value
        except (json.JSONDecodeError, TypeError):
            # If not JSON, return as string
            return entry.value
    
    def get_state_entry(self, key: str) -> Optional[SystemStateModel]:
        """Get the full state entry"""
        return self.find_one_by(key=key)
    
    def delete_state(self, key: str) -> bool:
        """Delete a system state"""
        entry = self.get_state_entry(key)
        if entry:
            return self.delete(entry)
        return False
    
    def get_states_by_type(self, state_type: str) -> List[SystemStateModel]:
        """Get all states of a specific type"""
        return self.find_by(state_type=state_type)
    
    def get_all_states(self) -> Dict[str, Any]:
        """Get all system states as a dictionary"""
        entries = self.get_all()
        states = {}
        
        for entry in entries:
            try:
                states[entry.key] = json.loads(entry.value) if entry.value else None
            except (json.JSONDecodeError, TypeError):
                states[entry.key] = entry.value
        
        return states
    
    # Twitter-specific state methods (replacing file-based storage)
    
    def set_last_tweet_id(self, tweet_id: str) -> SystemStateModel:
        """Set the last processed tweet ID"""
        return self.set_state(
            key='last_tweet_id',
            value=tweet_id,
            description='ID of the last processed tweet from the primary account',
            state_type='tweet_tracking'
        )
    
    def get_last_tweet_id(self) -> Optional[str]:
        """Get the last processed tweet ID"""
        tweet_id = self.get_state('last_tweet_id')
        # Ensure we always return a string
        return str(tweet_id) if tweet_id is not None else None
    
    def set_api_usage_data(self, service: str, usage_data: Dict[str, Any]) -> SystemStateModel:
        """Set API usage data for a service"""
        return self.set_state(
            key=f'api_usage_{service}',
            value=usage_data,
            description=f'API usage tracking data for {service}',
            state_type='api_limits'
        )
    
    def get_api_usage_data(self, service: str) -> Dict[str, Any]:
        """Get API usage data for a service"""
        return self.get_state(f'api_usage_{service}', {})
    
    def set_daily_requests(self, service: str, count: int) -> SystemStateModel:
        """Set daily request count for a service"""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        return self.set_state(
            key=f'daily_requests_{service}_{today}',
            value=count,
            description=f'Daily request count for {service} on {today}',
            state_type='api_limits'
        )
    
    def get_daily_requests(self, service: str) -> int:
        """Get daily request count for a service"""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        return self.get_state(f'daily_requests_{service}_{today}', 0)
    
    def increment_daily_requests(self, service: str) -> int:
        """Increment and return daily request count for a service"""
        current_count = self.get_daily_requests(service)
        new_count = current_count + 1
        self.set_daily_requests(service, new_count)
        return new_count
    
    def set_monthly_posts(self, service: str, count: int) -> SystemStateModel:
        """Set monthly post count for a service"""
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        return self.set_state(
            key=f'monthly_posts_{service}_{month}',
            value=count,
            description=f'Monthly post count for {service} in {month}',
            state_type='api_limits'
        )
    
    def get_monthly_posts(self, service: str) -> int:
        """Get monthly post count for a service"""
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        return self.get_state(f'monthly_posts_{service}_{month}', 0)
    
    def increment_monthly_posts(self, service: str) -> int:
        """Increment and return monthly post count for a service"""
        current_count = self.get_monthly_posts(service)
        new_count = current_count + 1
        self.set_monthly_posts(service, new_count)
        return new_count
    
    # Bot configuration states
    
    def set_bot_config(self, config_key: str, config_value: Any) -> SystemStateModel:
        """Set bot configuration value"""
        return self.set_state(
            key=f'bot_config_{config_key}',
            value=config_value,
            description=f'Bot configuration for {config_key}',
            state_type='configuration'
        )
    
    def get_bot_config(self, config_key: str, default: Any = None) -> Any:
        """Get bot configuration value"""
        return self.get_state(f'bot_config_{config_key}', default)
    
    # System health and monitoring
    
    def set_last_health_check(self, service: str, status: str, details: Optional[Dict] = None) -> SystemStateModel:
        """Record last health check for a service"""
        health_data = {
            'status': status,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'details': details or {}
        }
        return self.set_state(
            key=f'health_check_{service}',
            value=health_data,
            description=f'Last health check status for {service}',
            state_type='monitoring'
        )
    
    def get_last_health_check(self, service: str) -> Optional[Dict[str, Any]]:
        """Get last health check for a service"""
        return self.get_state(f'health_check_{service}')
    
    def cleanup_old_states(self, days_old: int = 30) -> int:
        """Clean up old temporary states"""
        try:
            from datetime import timedelta
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            
            # Only clean up temporary states like daily counters and health checks
            temp_patterns = ['daily_requests_', 'health_check_']
            
            deleted_count = 0
            for pattern in temp_patterns:
                entries = self.session.query(SystemStateModel).filter(
                    SystemStateModel.key.like(f'{pattern}%')
                ).filter(
                    SystemStateModel.updated_at < cutoff_date
                ).all()
                
                for entry in entries:
                    self.delete(entry)
                    deleted_count += 1
            
            self.session.flush()
            return deleted_count
        except Exception as e:
            self.logger.error(f"Error cleaning up old states: {str(e)}")
            self.session.rollback()
            return 0
    
    def get_state_statistics(self) -> Dict[str, Any]:
        """Get statistics about system states"""
        try:
            from sqlalchemy import func
            
            # Count by state type
            type_counts = self.session.query(
                SystemStateModel.state_type,
                func.count(SystemStateModel.id).label('count')
            ).group_by(SystemStateModel.state_type).all()
            
            total_states = self.count()
            
            return {
                'total_states': total_states,
                'states_by_type': {state_type: count for state_type, count in type_counts}
            }
        except Exception as e:
            self.logger.error(f"Error getting state statistics: {str(e)}")
            return {}
    
    @property
    def logger(self):
        """Get logger for this repository"""
        from src.utils.logger import logger
        return logger
