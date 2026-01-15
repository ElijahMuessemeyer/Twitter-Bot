# =============================================================================
# DATABASE ORM MODELS
# =============================================================================

import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy import (
    Column, String, Integer, DateTime, Text, JSON, Boolean, 
    ForeignKey, Float, Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.ext.mutable import MutableDict
from src.config.database import Base

class Tweet(Base):
    """Database model for tweets"""
    __tablename__ = "tweets"
    
    # Primary key
    id = Column(String(50), primary_key=True)
    
    # Core tweet data
    text = Column(Text, nullable=False)
    author_username = Column(String(255), nullable=False)
    author_id = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    processed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Twitter API metadata
    public_metrics = Column(JSON, default=dict)
    in_reply_to_user_id = Column(String(50), nullable=True)
    referenced_tweets = Column(JSON, default=list)
    entities = Column(JSON, default=dict)
    
    # Processing metadata
    language = Column(String(10), nullable=True)
    character_count = Column(Integer, nullable=False)
    
    # Additional metadata (using different name to avoid SQLAlchemy reserved word)
    tweet_metadata = Column(JSON, default=dict)
    
    # Relationships
    translations = relationship("Translation", back_populates="original_tweet", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_tweets_created_at', 'created_at'),
        Index('idx_tweets_author', 'author_id'),
        Index('idx_tweets_processed', 'processed_at'),
    )
    
    @validates('character_count')
    def validate_character_count(self, key, value):
        if value < 0:
            raise ValueError("Character count cannot be negative")
        return value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'text': self.text,
            'author_username': self.author_username,
            'author_id': self.author_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'public_metrics': self.public_metrics,
            'in_reply_to_user_id': self.in_reply_to_user_id,
            'referenced_tweets': self.referenced_tweets,
            'entities': self.entities,
            'language': self.language,
            'character_count': self.character_count,
            'metadata': self.tweet_metadata
        }

class Translation(Base):
    """Database model for tweet translations"""
    __tablename__ = "translations"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key to original tweet
    original_tweet_id = Column(String(50), ForeignKey('tweets.id'), nullable=False)
    
    # Translation content
    translated_text = Column(Text, nullable=False)
    target_language = Column(String(10), nullable=False)
    
    # Status tracking
    status = Column(String(20), default='pending')  # pending, posted, failed, draft
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Publishing information
    post_id = Column(String(50), nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Error tracking
    error_info = Column(JSON, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Translation metadata
    character_count = Column(Integer, nullable=False)
    translation_metadata = Column(JSON, default=dict)
    
    # Relationships
    original_tweet = relationship("Tweet", back_populates="translations")
    
    # Constraints and indexes
    __table_args__ = (
        Index('idx_translations_tweet_lang', 'original_tweet_id', 'target_language'),
        Index('idx_translations_status', 'status'),
        Index('idx_translations_created', 'created_at'),
        UniqueConstraint('original_tweet_id', 'target_language', name='uq_tweet_language'),
        CheckConstraint('status IN ("pending", "posted", "failed", "draft")', name='ck_translation_status'),
    )
    
    @validates('status')
    def validate_status(self, key, value):
        valid_statuses = ['pending', 'posted', 'failed', 'draft']
        if value not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        return value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'original_tweet_id': self.original_tweet_id,
            'translated_text': self.translated_text,
            'target_language': self.target_language,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'post_id': self.post_id,
            'posted_at': self.posted_at.isoformat() if self.posted_at else None,
            'error_info': self.error_info,
            'retry_count': self.retry_count,
            'character_count': self.character_count,
            'translation_metadata': self.translation_metadata
        }

class APIUsage(Base):
    """Database model for API usage tracking"""
    __tablename__ = "api_usage"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # API details
    service = Column(String(50), nullable=False)  # twitter, gemini
    endpoint = Column(String(100), nullable=False)
    method = Column(String(10), default='GET')
    
    # Timing
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    response_time = Column(Float, nullable=True)
    
    # Response details
    status_code = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)
    
    # Error information
    error_info = Column(JSON, nullable=True)
    
    # Request metadata
    request_metadata = Column(JSON, default=dict)
    
    # Daily/monthly counters
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    month = Column(String(7), nullable=False)  # YYYY-MM
    
    # Indexes
    __table_args__ = (
        Index('idx_api_usage_service', 'service'),
        Index('idx_api_usage_timestamp', 'timestamp'),
        Index('idx_api_usage_date', 'date'),
        Index('idx_api_usage_month', 'month'),
        Index('idx_api_usage_success', 'success'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'service': self.service,
            'endpoint': self.endpoint,
            'method': self.method,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'response_time': self.response_time,
            'status_code': self.status_code,
            'success': self.success,
            'error_info': self.error_info,
            'request_metadata': self.request_metadata,
            'date': self.date,
            'month': self.month
        }

class User(Base):
    """Database model for user accounts and configurations"""
    __tablename__ = "users"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Account identification
    account_name = Column(String(100), unique=True, nullable=False)
    account_type = Column(String(20), default='primary')  # primary, translation
    
    # API credentials (encrypted/hashed in production)
    api_credentials = Column(JSON, default=dict)
    
    # User settings (using MutableDict for change tracking)
    settings = Column(MutableDict.as_mutable(JSON), default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_active = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_users_account_name', 'account_name'),
        Index('idx_users_active', 'is_active'),
        Index('idx_users_last_active', 'last_active'),
    )
    
    def to_dict(self, include_credentials: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        result = {
            'id': self.id,
            'account_name': self.account_name,
            'account_type': self.account_type,
            'settings': self.settings,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_active': self.last_active.isoformat() if self.last_active else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_active': self.is_active
        }
        
        if include_credentials:
            result['api_credentials'] = self.api_credentials
        
        return result

class TranslationCache(Base):
    """Database model for translation caching with TTL support"""
    __tablename__ = "translation_cache"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Cache key (hash of original text + target language)
    cache_key = Column(String(128), unique=True, nullable=False)
    
    # Original and translated content
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    source_language = Column(String(10), nullable=True)
    target_language = Column(String(10), nullable=False)
    
    # TTL and access tracking
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_accessed = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    access_count = Column(Integer, default=0)
    
    # Quality and confidence metrics
    confidence_score = Column(Float, nullable=True)
    quality_metrics = Column(JSON, default=dict)
    
    # Cache metadata
    translator_service = Column(String(50), default='gemini')
    cache_metadata = Column(JSON, default=dict)
    
    # Indexes
    __table_args__ = (
        Index('idx_cache_key', 'cache_key'),
        Index('idx_cache_expires', 'expires_at'),
        Index('idx_cache_lang_pair', 'source_language', 'target_language'),
        Index('idx_cache_accessed', 'last_accessed'),
    )
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        if self.expires_at is None:
            return False
        
        now = datetime.now(timezone.utc)
        expires_at = self.expires_at
        
        # Ensure both datetimes are timezone-aware for comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            
        return now > expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'cache_key': self.cache_key,
            'original_text': self.original_text,
            'translated_text': self.translated_text,
            'source_language': self.source_language,
            'target_language': self.target_language,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None,
            'access_count': self.access_count,
            'confidence_score': self.confidence_score,
            'quality_metrics': self.quality_metrics,
            'translator_service': self.translator_service,
            'cache_metadata': self.cache_metadata,
            'is_expired': self.is_expired()
        }

class SystemState(Base):
    """Database model for system state tracking"""
    __tablename__ = "system_state"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # State identification
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    
    # State metadata
    description = Column(String(500), nullable=True)
    state_type = Column(String(50), default='general')  # general, tweet_tracking, api_limits
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Indexes
    __table_args__ = (
        Index('idx_system_state_key', 'key'),
        Index('idx_system_state_type', 'state_type'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'state_type': self.state_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
