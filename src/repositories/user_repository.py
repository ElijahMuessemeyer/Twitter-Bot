# =============================================================================
# USER REPOSITORY
# =============================================================================

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from src.models.database_models import User as UserModel
from src.repositories.base_repository import BaseRepository

class UserRepository(BaseRepository[UserModel]):
    """Repository for user account operations"""
    
    def __init__(self, session: Session):
        super().__init__(session, UserModel)
    
    def create_user(
        self,
        account_name: str,
        account_type: str = 'primary',
        api_credentials: Optional[Dict[str, str]] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> UserModel:
        """Create a new user account"""
        return self.create(
            account_name=account_name,
            account_type=account_type,
            api_credentials=api_credentials or {},
            settings=settings or {},
            is_active=True
        )
    
    def get_by_account_name(self, account_name: str) -> Optional[UserModel]:
        """Get user by account name"""
        return self.find_one_by(account_name=account_name)
    
    def get_primary_user(self) -> Optional[UserModel]:
        """Get the primary user account"""
        return self.find_one_by(account_type='primary', is_active=True)
    
    def get_translation_accounts(self) -> List[UserModel]:
        """Get all active translation accounts"""
        return self.find_by(account_type='translation', is_active=True)
    
    def update_api_credentials(self, user_id: int, credentials: Dict[str, str]) -> bool:
        """Update API credentials for a user"""
        try:
            user = self.get_by_id(user_id)
            if user:
                # In production, encrypt credentials before storing
                self.update(user, api_credentials=credentials)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error updating API credentials: {str(e)}")
            return False
    
    def update_user_settings(self, user_id: int, settings: Dict[str, Any]) -> bool:
        """Update user settings"""
        try:
            user = self.get_by_id(user_id)
            if user:
                # Merge with existing settings
                current_settings = user.settings or {}
                current_settings.update(settings)
                
                # Create new dict to trigger SQLAlchemy change detection
                new_settings = dict(current_settings)
                self.update(user, settings=new_settings)
                
                # Force session flush to ensure the update is persisted
                self.session.flush()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error updating user settings: {str(e)}")
            return False
    
    def update_last_active(self, user_id: int) -> bool:
        """Update last active timestamp"""
        try:
            user = self.get_by_id(user_id)
            if user:
                self.update(user, last_active=datetime.now(timezone.utc))
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error updating last active: {str(e)}")
            return False
    
    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate a user account"""
        try:
            user = self.get_by_id(user_id)
            if user:
                self.update(user, is_active=False)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error deactivating user: {str(e)}")
            return False
    
    def activate_user(self, user_id: int) -> bool:
        """Activate a user account"""
        try:
            user = self.get_by_id(user_id)
            if user:
                self.update(user, is_active=True)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error activating user: {str(e)}")
            return False
    
    def get_user_statistics(self) -> Dict[str, Any]:
        """Get user statistics"""
        try:
            total_users = self.count()
            active_users = self.count(is_active=True)
            primary_users = self.count(account_type='primary', is_active=True)
            translation_users = self.count(account_type='translation', is_active=True)
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'primary_accounts': primary_users,
                'translation_accounts': translation_users
            }
        except Exception as e:
            self.logger.error(f"Error getting user statistics: {str(e)}")
            return {}
    
    def has_valid_credentials(self, user_id: int, service: str) -> bool:
        """Check if user has valid credentials for a service"""
        try:
            user = self.get_by_id(user_id)
            if not user or not user.api_credentials:
                return False
            
            service_creds = user.api_credentials.get(service, {})
            if not service_creds:
                return False
            
            # Basic validation - check if required fields are present and not placeholder values
            required_fields = {
                'twitter': ['consumer_key', 'consumer_secret', 'access_token', 'access_token_secret'],
                'gemini': ['api_key']
            }
            
            if service not in required_fields:
                return False
            
            for field in required_fields[service]:
                value = service_creds.get(field, '')
                if not value or value.startswith('your_'):
                    return False
            
            return True
        except Exception as e:
            self.logger.error(f"Error checking credentials for {service}: {str(e)}")
            return False
    
    def get_user_setting(self, user_id: int, setting_key: str, default_value: Any = None) -> Any:
        """Get a specific user setting"""
        try:
            user = self.get_by_id(user_id)
            if user and user.settings:
                return user.settings.get(setting_key, default_value)
            return default_value
        except Exception as e:
            self.logger.error(f"Error getting user setting {setting_key}: {str(e)}")
            return default_value
    
    def set_user_setting(self, user_id: int, setting_key: str, setting_value: Any) -> bool:
        """Set a specific user setting"""
        try:
            current_settings = self.get_by_id(user_id).settings or {}
            current_settings[setting_key] = setting_value
            return self.update_user_settings(user_id, {setting_key: setting_value})
        except Exception as e:
            self.logger.error(f"Error setting user setting {setting_key}: {str(e)}")
            return False
    
    @property
    def logger(self):
        """Get logger for this repository"""
        from src.utils.logger import logger
        return logger
