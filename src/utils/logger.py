# =============================================================================
# LOGGING UTILITY
# =============================================================================

import logging
import os
from pathlib import Path
from datetime import datetime

class Logger:
    def __init__(self, name="twitter_bot"):
        # Create logs directory if it doesn't exist
        Path("logs").mkdir(exist_ok=True)
        
        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Create formatters
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # File handler (daily rotation)
        today = datetime.now().strftime('%Y-%m-%d')
        file_handler = logging.FileHandler(f'logs/twitter_bot_{today}.log')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        if not self.logger.handlers:
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)
    
    def get_logger(self):
        return self.logger

# Global logger instance
logger = Logger().get_logger()