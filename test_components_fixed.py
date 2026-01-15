#!/usr/bin/env python3
# =============================================================================
# COMPONENT TESTING SCRIPT
# =============================================================================
# Tests individual components without requiring API keys

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all modules can be imported successfully"""
    print("🔍 Testing module imports...")
    
    try:
        from src.utils.text_processor import text_processor
        from src.utils.prompt_builder import prompt_builder
        from src.utils.logger import logger
        from src.models.tweet import Tweet, Translation
        from src.config.settings import settings
        from draft_manager import draft_manager
        print("✅ All core modules imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {str(e)}")
        return False

def main():
    """Run basic import test"""
    print("=== Basic Component Test ===\n")
    
    result = test_imports()
    
    if result:
        print("\n🎉 Basic import test passed!")
        print("For full tests, run: python -m pytest tests/")
    else:
        print("\n❌ Import test failed")
    
    return result

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)