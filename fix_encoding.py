#!/usr/bin/env python3
# Fix encoding issues in source files

import os
import glob

def fix_file_encoding(file_path):
    """Fix encoding issues in a single file"""
    try:
        # Read with error handling
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # Fix specific problematic patterns
        fixes = [
            # Restore correct imports and common words
            ('from typing import ❌ist', 'from typing import List'),
            ('❌ist[', 'List['),
            ('❌oad', 'Load'),
            ('❌imit', 'Limit'),
            ('❌og cache', 'Log cache'),
            
            # Fix log messages with proper emojis but keep original meaning
            ('logger.warning("⚠️ Twitter API credentials', 'logger.warning("⚠️ Twitter API credentials'),
            ('logger.warning("❌ Daily API request', 'logger.warning("⚠️ Daily API request'),
            ('logger.error("❌ Missing API credentials', 'logger.error("❌ Missing API credentials'),
            ('logger.info("📊 API Usage Status', 'logger.info("📊 API Usage Status'),
        ]
        
        original_content = content
        for old, new in fixes:
            content = content.replace(old, new)
        
        # Write back if changed
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Fixed: {file_path}")
        else:
            print(f"OK: {file_path}")
            
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")

def main():
    """Fix encoding in all Python files"""
    files_to_fix = [
        'main.py',
        'src/config/settings.py',
        'src/services/twitter_monitor.py',
        'src/services/gemini_translator.py',
        'src/services/publisher.py',
    ]
    
    for file_path in files_to_fix:
        if os.path.exists(file_path):
            fix_file_encoding(file_path)
        else:
            print(f"Not found: {file_path}")

if __name__ == "__main__":
    main()
