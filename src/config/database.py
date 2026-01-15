# =============================================================================
# DATABASE CONFIGURATION & CONNECTION MANAGEMENT
# =============================================================================

import os
from typing import Optional
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool
from pathlib import Path
from src.utils.logger import logger

# Base class for all ORM models
Base = declarative_base()

class DatabaseConfig:
    """Database configuration and connection management"""
    
    def __init__(self):
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self._init_database()
    
    def _init_database(self):
        """Initialize database connection based on environment"""
        database_url = self._get_database_url()
        
        # Create engine with appropriate configuration
        if database_url.startswith('sqlite'):
            self.engine = create_engine(
                database_url,
                poolclass=StaticPool,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 30
                },
                echo=os.getenv('DB_ECHO', 'false').lower() == 'true'
            )
            # Enable foreign keys for SQLite
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()
        else:
            # PostgreSQL configuration
            self.engine = create_engine(
                database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=os.getenv('DB_ECHO', 'false').lower() == 'true'
            )
        
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info(f"Database initialized: {self._get_db_type()}")
    
    def _get_database_url(self) -> str:
        """Get database URL based on environment"""
        # Check for explicit database URL first
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            return database_url
        
        # Production/staging - use PostgreSQL
        if os.getenv('ENV') in ['production', 'staging']:
            host = os.getenv('DB_HOST', 'localhost')
            port = os.getenv('DB_PORT', '5432')
            name = os.getenv('DB_NAME', 'twitter_bot')
            user = os.getenv('DB_USER', 'postgres')
            password = os.getenv('DB_PASSWORD', '')
            
            if not password:
                raise ValueError("DB_PASSWORD environment variable is required for PostgreSQL")
            
            return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
        
        # Development - use SQLite
        db_path = Path('data/twitter_bot.db')
        db_path.parent.mkdir(exist_ok=True)
        return f"sqlite:///{db_path.absolute()}"
    
    def _get_db_type(self) -> str:
        """Get database type for logging"""
        if self.engine:
            return self.engine.dialect.name
        return "unknown"
    
    def get_session(self):
        """Get a database session"""
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized")
        return self.SessionLocal()
    
    def create_all_tables(self):
        """Create all database tables"""
        if not self.engine:
            raise RuntimeError("Database not initialized")
        
        Base.metadata.create_all(bind=self.engine)
        logger.info("All database tables created")
    
    def drop_all_tables(self):
        """Drop all database tables (for testing)"""
        if not self.engine:
            raise RuntimeError("Database not initialized")
        
        Base.metadata.drop_all(bind=self.engine)
        logger.info("All database tables dropped")
    
    def health_check(self) -> bool:
        """Perform database health check"""
        try:
            from sqlalchemy import text
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return False

# Global database instance
db_config = DatabaseConfig()

def get_db():
    """Dependency function for getting database session"""
    session = db_config.get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
