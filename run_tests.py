#!/usr/bin/env python3
# =============================================================================
# TEST RUNNER SCRIPT
# =============================================================================
# Comprehensive test runner for the Twitter translation bot

import subprocess
import sys
import os
from pathlib import Path

def run_pytest():
    """Run pytest with comprehensive coverage"""
    print("🧪 Running comprehensive test suite with pytest...\n")
    
    try:
        # Run pytest with verbose output
        cmd = [
            sys.executable, "-m", "pytest", 
            "tests/",
            "-v",
            "--tb=short",
            "-x"  # Stop on first failure
        ]
        
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Error running pytest: {str(e)}")
        return False

def run_component_tests():
    """Run the component tests"""
    print("\n🔧 Running component tests (no API keys required)...\n")
    
    try:
        result = subprocess.run([sys.executable, "test_components.py"], capture_output=False, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error running component tests: {str(e)}")
        return False

def check_code_quality():
    """Run basic code quality checks"""
    print("\n📊 Checking code quality...\n")
    
    # Check for Python syntax errors
    try:
        import py_compile
        python_files = []
        
        # Find all Python files
        for root, dirs, files in os.walk("."):
            # Skip virtual environment and hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'venv']
            
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
        
        syntax_errors = 0
        for file_path in python_files:
            try:
                py_compile.compile(file_path, doraise=True)
            except py_compile.PyCompileError as e:
                print(f"❌ Syntax error in {file_path}: {str(e)}")
                syntax_errors += 1
        
        if syntax_errors == 0:
            print(f"✅ All {len(python_files)} Python files have valid syntax")
            return True
        else:
            print(f"❌ Found {syntax_errors} syntax errors")
            return False
            
    except Exception as e:
        print(f"⚠️ Could not check code quality: {str(e)}")
        return True  # Don't fail the tests for this

def check_dependencies():
    """Check that all required dependencies are installed"""
    print("\n📦 Checking dependencies...\n")
    
    required_packages = [
        'tweepy',
        'google.generativeai', 
        'python-dotenv',
        'schedule',
        'requests',
        'pytest',
        'pytest-mock'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing packages: {', '.join(missing_packages)}")
        print("   Run: pip install -r requirements.txt")
        return False
    else:
        print("✅ All required dependencies are installed")
        return True

def check_project_structure():
    """Verify project structure is correct"""
    print("\n📁 Checking project structure...\n")
    
    required_files = [
        'main.py',
        'draft_manager.py',
        'requirements.txt',
        'config/.env.template',
        'config/languages.json',
        'src/config/settings.py',
        'src/utils/text_processor.py',
        'src/utils/prompt_builder.py',
        'src/utils/logger.py',
        'src/models/tweet.py',
        'src/services/gemini_translator.py',
        'src/services/twitter_monitor.py',
        'src/services/publisher.py',
        'tests/test_text_processor.py',
        'tests/test_models.py',
        'tests/test_prompt_builder.py',
        'tests/test_draft_manager.py',
        'tests/test_settings.py',
        'tests/test_services_mock.py'
    ]
    
    required_dirs = [
        'src',
        'src/config',
        'src/services',
        'src/models',
        'src/utils',
        'tests',
        'config',
        'drafts',
        'drafts/pending',
        'drafts/posted',
        'logs'
    ]
    
    missing_files = []
    missing_dirs = []
    
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    for dir_path in required_dirs:
        if not Path(dir_path).exists():
            missing_dirs.append(dir_path)
    
    if missing_files or missing_dirs:
        if missing_files:
            print(f"❌ Missing files: {', '.join(missing_files)}")
        if missing_dirs:
            print(f"❌ Missing directories: {', '.join(missing_dirs)}")
        return False
    else:
        print("✅ All required files and directories are present")
        return True

def main():
    """Run all tests and checks"""
    print("🚀 Twitter Translation Bot - Comprehensive Test Suite")
    print("=" * 60)
    
    checks = [
        ("Project Structure", check_project_structure),
        ("Dependencies", check_dependencies),
        ("Code Quality", check_code_quality),
        ("Component Tests", run_component_tests),
        ("Unit Tests (pytest)", run_pytest)
    ]
    
    results = []
    for check_name, check_func in checks:
        print(f"\n{'=' * 20} {check_name} {'=' * 20}")
        try:
            result = check_func()
            results.append((check_name, result))
        except KeyboardInterrupt:
            print(f"\n⏹️ Tests interrupted by user")
            return False
        except Exception as e:
            print(f"❌ {check_name} failed with exception: {str(e)}")
            results.append((check_name, False))
    
    # Summary
    print(f"\n{'=' * 60}")
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for check_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:8} {check_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall Result: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Your Twitter translation bot is ready to use.")
        print("\n📝 Next steps:")
        print("1. Get API keys:")
        print("   • Twitter: https://developer.twitter.com/")
        print("   • Google Gemini: https://makersuite.google.com/app/apikey")
        print("2. Copy config/.env.template to .env and fill in your keys")
        print("3. Update config/languages.json with your target accounts")
        print("4. Test with: python main.py test")
        print("5. Run once: python main.py once")
        print("6. Run continuously: python main.py")
        return True
    else:
        print("\n⚠️ Some tests failed. Please fix the issues above before proceeding.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)