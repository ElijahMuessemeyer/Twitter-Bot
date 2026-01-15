# =============================================================================
# BASE REPOSITORY PATTERN
# =============================================================================

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from src.utils.logger import logger

T = TypeVar('T')

class BaseRepository(Generic[T], ABC):
    """Base repository with common CRUD operations"""
    
    def __init__(self, session: Session, model_class):
        self.session = session
        self.model_class = model_class
    
    def create(self, **kwargs) -> T:
        """Create a new record"""
        try:
            instance = self.model_class(**kwargs)
            self.session.add(instance)
            self.session.flush()
            return instance
        except SQLAlchemyError as e:
            logger.error(f"Error creating {self.model_class.__name__}: {str(e)}")
            self.session.rollback()
            raise
    
    def get_by_id(self, id: Any) -> Optional[T]:
        """Get record by primary key"""
        try:
            return self.session.query(self.model_class).filter(
                self.model_class.id == id
            ).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting {self.model_class.__name__} by id {id}: {str(e)}")
            raise
    
    def get_all(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[T]:
        """Get all records with optional pagination"""
        try:
            query = self.session.query(self.model_class)
            
            if offset:
                query = query.offset(offset)
            
            if limit:
                query = query.limit(limit)
            
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting all {self.model_class.__name__}: {str(e)}")
            raise
    
    def update(self, instance: T, **kwargs) -> T:
        """Update an existing record"""
        try:
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            
            self.session.flush()
            return instance
        except SQLAlchemyError as e:
            logger.error(f"Error updating {self.model_class.__name__}: {str(e)}")
            self.session.rollback()
            raise
    
    def delete(self, instance: T) -> bool:
        """Delete a record"""
        try:
            self.session.delete(instance)
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error deleting {self.model_class.__name__}: {str(e)}")
            self.session.rollback()
            raise
    
    def delete_by_id(self, id: Any) -> bool:
        """Delete record by primary key"""
        instance = self.get_by_id(id)
        if instance:
            return self.delete(instance)
        return False
    
    def exists(self, **filters) -> bool:
        """Check if record exists with given filters"""
        try:
            query = self.session.query(self.model_class)
            
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)
            
            return query.first() is not None
        except SQLAlchemyError as e:
            logger.error(f"Error checking existence in {self.model_class.__name__}: {str(e)}")
            raise
    
    def count(self, **filters) -> int:
        """Count records with optional filters"""
        try:
            query = self.session.query(self.model_class)
            
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)
            
            return query.count()
        except SQLAlchemyError as e:
            logger.error(f"Error counting {self.model_class.__name__}: {str(e)}")
            raise
    
    def find_by(self, **filters) -> List[T]:
        """Find records by filters"""
        try:
            query = self.session.query(self.model_class)
            
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)
            
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error finding {self.model_class.__name__}: {str(e)}")
            raise
    
    def find_one_by(self, **filters) -> Optional[T]:
        """Find single record by filters"""
        results = self.find_by(**filters)
        return results[0] if results else None
    
    def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[T]:
        """Create multiple records efficiently"""
        try:
            instances = [self.model_class(**data) for data in data_list]
            self.session.add_all(instances)
            self.session.flush()
            return instances
        except SQLAlchemyError as e:
            logger.error(f"Error bulk creating {self.model_class.__name__}: {str(e)}")
            self.session.rollback()
            raise
    
    def bulk_update(self, updates: List[Dict[str, Any]]) -> bool:
        """Bulk update records"""
        try:
            for update_data in updates:
                id_value = update_data.pop('id', None)
                if id_value:
                    self.session.query(self.model_class).filter(
                        self.model_class.id == id_value
                    ).update(update_data)
            
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error bulk updating {self.model_class.__name__}: {str(e)}")
            self.session.rollback()
            raise
