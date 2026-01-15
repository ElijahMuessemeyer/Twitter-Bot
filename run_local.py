#!/usr/bin/env python3
# =============================================================================
# LOCAL DEVELOPMENT RUNNER
# =============================================================================
# Interactive development environment for the Twitter Auto-Translation Bot
# Provides a menu-driven interface for testing and running the bot locally

import os
import sys
import time
import signal
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import bot components
try:
    from main import TwitterTranslationBot
    from draft_manager import draft_manager
    from src.config.settings import settings
    from src.utils.logger import logger
    from src.services.twitter_monitor import twitter_monitor
    from src.services.publisher import twitter_publisher
except ImportError as e:
    print(f"L Import error: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)

class LocalDevelopmentRunner:
    def __init__(self):
        self.bot = TwitterTranslationBot()
        self.running = False
        
        # Setup signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals gracefully"""
        print("\n=Ñ Shutting down gracefully...")
        self.running = False
        if hasattr(self.bot, 'running'):
            self.bot.running = False
    
    def setup_local_environment(self):
        """Set up local development environment"""
        print("=' Setting up local development environment...")
        
        # Create necessary directories
        directories = ['logs', 'drafts/pending', 'drafts/posted']
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
        
        # Check for .env file
        if not Path(".env").exists():
            print("L .env file not found!")
            print("=Ý Please copy config/.env.template to .env and fill in your API credentials.")
            print("   cp config/.env.template .env")
            return False
        
        # Check if basic imports work
        try:
            from src.config.settings import settings
            from src.utils.logger import logger
            print(" Environment setup complete")
            return True
        except Exception as e:
            print(f"L Environment setup failed: {e}")
            return False
    
    def show_status(self):
        """Display current bot status"""
        print("\n" + "="*50)
        print("=Ê TWITTER TRANSLATION BOT STATUS")
        print("="*50)
        
        # API Credentials Status
        print("\n= API Credentials:")
        if settings.validate_credentials():
            print("    All required API keys configured")
        else:
            print("   L Missing API keys - check your .env file")
        
        # API Usage Status
        print(f"\n=È API Usage:")
        print(f"   Daily requests: {twitter_monitor.daily_requests}/{settings.TWITTER_FREE_DAILY_LIMIT}")
        print(f"   Monthly posts: {twitter_monitor.monthly_posts}/{settings.TWITTER_FREE_MONTHLY_LIMIT}")
        
        # Draft Status
        draft_count = draft_manager.get_draft_count()
        print(f"   Pending drafts: {draft_count}")
        
        # Language Configuration
        print(f"\n< Configured Languages:")
        if settings.TARGET_LANGUAGES:
            available_langs = twitter_publisher.get_available_languages()
            for lang_config in settings.TARGET_LANGUAGES:
                lang_code = lang_config['code']
                status = "" if lang_code in available_langs else "L"
                print(f"   {status} {lang_code.upper()} ({lang_config['name']}) - @{lang_config.get('twitter_username', 'not_set')}")
        else:
            print("   L No languages configured - check config/languages.json")
        
        # Last Activity
        last_tweet_file = Path('logs/last_tweet_id.txt')
        if last_tweet_file.exists():
            try:
                last_id = last_tweet_file.read_text().strip()
                print(f"\n=R Last processed tweet ID: {last_id}")
            except:
                print(f"\n=R Last processed tweet ID: Unable to read")
        else:
            print(f"\n=R Last processed tweet ID: None (first run)")
        
        print("="*50)
    
    def run_tests(self):
        """Run component tests"""
        print("\n>ê Running component tests...")
        print("-" * 30)
        
        # Run the test script
        import subprocess
        try:
            result = subprocess.run([sys.executable, "test_components.py"], 
                                  capture_output=True, text=True, cwd=Path.cwd())
            print(result.stdout)
            if result.stderr:
                print("Errors:")
                print(result.stderr)
            return result.returncode == 0
        except Exception as e:
            print(f"L Failed to run tests: {e}")
            return False
    
    def test_api_connections(self):
        """Test API connections"""
        print("\n= Testing API connections...")
        print("-" * 30)
        
        if not settings.validate_credentials():
            print("L Cannot test connections - missing API credentials")
            return False
        
        # Test Twitter connections
        try:
            twitter_publisher.test_connections()
            print(" Twitter API connection tests completed")
        except Exception as e:
            print(f"L Twitter API test failed: {e}")
        
        # Test Gemini translation
        try:
            from src.services.gemini_translator import gemini_translator
            if gemini_translator.client_initialized:
                print(" Google Gemini API initialized successfully")
            else:
                print("L Google Gemini API not initialized - check GOOGLE_API_KEY")
        except Exception as e:
            print(f"L Gemini API test failed: {e}")
        
        return True
    
    def show_drafts(self):
        """Show pending drafts"""
        print("\n=Ý Pending Drafts:")
        print("-" * 30)
        draft_manager.display_pending_drafts()
    
    def show_logs(self):
        """Show recent log entries"""
        print("\n=Ë Recent Log Entries:")
        print("-" * 30)
        
        today = datetime.now().strftime('%Y-%m-%d')
        log_file = Path(f'logs/twitter_bot_{today}.log')
        
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    # Show last 20 lines
                    recent_lines = lines[-20:] if len(lines) > 20 else lines
                    for line in recent_lines:
                        print(line.rstrip())
            except Exception as e:
                print(f"L Error reading log file: {e}")
        else:
            print("=Ý No log file found for today. Run the bot to generate logs.")
    
    def run_once(self):
        """Run the bot once"""
        print("\n> Running bot once...")
        print("-" * 30)
        self.bot.run_once()
        print(" Single run completed")
    
    def run_continuous(self):
        """Run the bot continuously"""
        print("\n> Running bot continuously...")
        print("Press Ctrl+C to stop")
        print("-" * 30)
        
        self.running = True
        try:
            self.bot.run_scheduled()
        except KeyboardInterrupt:
            print("\n=Ñ Bot stopped by user")
        except Exception as e:
            print(f"\nL Bot stopped due to error: {e}")
        finally:
            self.running = False
    
    def interactive_menu(self):
        """Display interactive menu"""
        while True:
            print("\n" + "="*50)
            print("> TWITTER TRANSLATION BOT - LOCAL DEVELOPMENT")
            print("="*50)
            print("1. =Ê Show Status")
            print("2. <Ã Run Once")
            print("3. = Run Continuously")
            print("4. >ê Run Tests")
            print("5. = Test API Connections") 
            print("6. =Ý Show Pending Drafts")
            print("7. =Ë Show Recent Logs")
            print("8. ™  Configuration Help")
            print("9. =€ Deployment Help")
            print("0. =ª Exit")
            print("-" * 50)
            
            try:
                choice = input("Select option (0-9): ").strip()
                
                if choice == '1':
                    self.show_status()
                    
                elif choice == '2':
                    self.run_once()
                    
                elif choice == '3':
                    self.run_continuous()
                    
                elif choice == '4':
                    self.run_tests()
                    
                elif choice == '5':
                    self.test_api_connections()
                    
                elif choice == '6':
                    self.show_drafts()
                    
                elif choice == '7':
                    self.show_logs()
                    
                elif choice == '8':
                    self.show_configuration_help()
                    
                elif choice == '9':
                    self.show_deployment_help()
                    
                elif choice == '0':
                    print("=K Goodbye!")
                    break
                    
                else:
                    print("L Invalid choice. Please select 0-9.")
                    
            except KeyboardInterrupt:
                print("\n=K Goodbye!")
                break
            except EOFError:
                print("\n=K Goodbye!")
                break
            
            # Wait for user to continue
            if choice != '0':
                input("\nPress Enter to continue...")
    
    def show_configuration_help(self):
        """Show configuration help"""
        print("\n™  CONFIGURATION HELP")
        print("="*50)
        
        print("\n=Ë Setup Checklist:")
        print("1. Copy config/.env.template to .env")
        print("2. Get Twitter API keys from https://developer.twitter.com/")
        print("3. Get Google Gemini API key from https://makersuite.google.com/app/apikey")
        print("4. Fill in all API keys in .env file")
        print("5. Configure target languages in config/languages.json")
        
        print("\n= Required API Keys:")
        print("" PRIMARY_TWITTER_* - Your main English account")
        print("" [LANG]_TWITTER_* - Each target language account (e.g., JA_TWITTER_*)")
        print("" GOOGLE_API_KEY - For Gemini AI translation")
        
        print("\n< Language Configuration:")
        print("Edit config/languages.json to add/remove languages")
        print("Each language needs its own Twitter account and API keys")
        
        print("\n=¡ Tips:")
        print("" Test with one language first before adding more")
        print("" Use different Twitter apps for each account")
        print("" Gemini has a generous free tier (1M tokens/day)")
        print("" Twitter free tier allows 1,500 tweets/month")
    
    def show_deployment_help(self):
        """Show deployment help"""
        print("\n=€ DEPLOYMENT OPTIONS")
        print("="*50)
        
        print("\n1. <à Local Machine (Current):")
        print("   " Development and testing")
        print("   " Full control over execution")
        print("   " Run: python run_local.py")
        
        print("\n2. > GitHub Actions (Recommended):")
        print("   " Free automated deployment")
        print("   " Runs every 30 minutes automatically")
        print("   " Zero maintenance required")
        print("   " See DEPLOYMENT.md for setup instructions")
        
        print("\n3.   Cloud Platforms:")
        print("   " Railway (Free tier): $5 credits/month")
        print("   " Render (Free tier): 750 hours/month")
        print("   " Oracle Cloud (Always free): Generous ARM instances")
        print("   " See DEPLOYMENT.md for detailed instructions")
        
        print("\n=Ö Next Steps:")
        print("1. Test locally first: python main.py test")
        print("2. Run once to verify: python main.py once")
        print("3. Choose deployment option from DEPLOYMENT.md")
        print("4. Monitor with: python main.py status")
    
    def command_line_mode(self, args):
        """Handle command line arguments"""
        if not args:
            return self.interactive_menu()
        
        command = args[0].lower()
        
        if command == 'status':
            self.show_status()
        elif command == 'once':
            self.run_once()
        elif command == 'continuous':
            self.run_continuous()
        elif command == 'test':
            self.run_tests()
        elif command == 'connections':
            self.test_api_connections()
        elif command == 'drafts':
            self.show_drafts()
        elif command == 'logs':
            self.show_logs()
        elif command == 'help':
            self.show_help()
        else:
            print(f"L Unknown command: {command}")
            self.show_help()
    
    def show_help(self):
        """Show command line help"""
        print("\n> Twitter Translation Bot - Local Runner")
        print("="*50)
        print("Usage: python run_local.py [command]")
        print("\nCommands:")
        print("  status      - Show bot status and configuration")
        print("  once        - Run bot once and exit")
        print("  continuous  - Run bot continuously (Ctrl+C to stop)")
        print("  test        - Run component tests")
        print("  connections - Test API connections")  
        print("  drafts      - Show pending drafts")
        print("  logs        - Show recent log entries")
        print("  help        - Show this help message")
        print("  (no args)   - Start interactive menu")
        print("\nExamples:")
        print("  python run_local.py status")
        print("  python run_local.py once")
        print("  python run_local.py")

def main():
    """Main entry point"""
    runner = LocalDevelopmentRunner()
    
    # Setup environment first
    if not runner.setup_local_environment():
        return 1
    
    # Handle command line arguments
    try:
        runner.command_line_mode(sys.argv[1:])
        return 0
    except KeyboardInterrupt:
        print("\n=K Goodbye!")
        return 0
    except Exception as e:
        print(f"\nL Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())