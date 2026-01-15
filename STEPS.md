# Twitter Auto-Translation Bot - Complete Implementation Steps

## Phase 0: Prerequisites and Setup

### Step 1: Development Environment Setup
```bash
# Create project directory
mkdir twitter_bot
cd twitter_bot

# Set up Python virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Create project structure
mkdir -p src/{config,services,models,utils}
mkdir -p {tests,config,drafts/{pending,posted},logs}
touch src/__init__.py src/{config,services,models,utils}/__init__.py
```

### Step 2: Install Dependencies
```bash
# Install required packages
pip install tweepy google-generativeai python-dotenv schedule requests

# Create requirements.txt
pip freeze > requirements.txt
```

### Step 3: API Access Setup

#### Twitter API Setup
1. Go to https://developer.twitter.com/
2. Apply for Developer Account (free)
3. Create a new app
4. Generate API keys for EACH account (primary + language accounts):
   - API Key (Consumer Key)
   - API Key Secret (Consumer Secret)
   - Access Token
   - Access Token Secret
5. Note down all credentials

#### Google AI Studio API Setup
1. Go to https://makersuite.google.com/app/apikey
2. Create Google account or sign in
3. Get API key (free tier available - no billing required initially)
4. Note down API key

### Step 4: Create Configuration Files

#### Create `.env.template`
```bash
# Twitter API Credentials - Primary Account
PRIMARY_TWITTER_CONSUMER_KEY=your_consumer_key
PRIMARY_TWITTER_CONSUMER_SECRET=your_consumer_secret
PRIMARY_TWITTER_ACCESS_TOKEN=your_access_token
PRIMARY_TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret
PRIMARY_TWITTER_USERNAME=your_english_account

# Twitter API Credentials - Japanese Account (example)
JAPANESE_TWITTER_CONSUMER_KEY=japanese_consumer_key
JAPANESE_TWITTER_CONSUMER_SECRET=japanese_consumer_secret
JAPANESE_TWITTER_ACCESS_TOKEN=japanese_access_token
JAPANESE_TWITTER_ACCESS_TOKEN_SECRET=japanese_access_token_secret
JAPANESE_TWITTER_USERNAME=your_japanese_account

# Google Gemini API
GOOGLE_API_KEY=your_google_api_key
GEMINI_MODEL=gemini-1.5-flash

# Configuration
POLL_INTERVAL_SECONDS=300
LOG_LEVEL=INFO
```

#### Create `config/languages.json`
```json
{
  "target_languages": [
    {
      "code": "ja",
      "name": "Japanese",
      "twitter_username": "your_japanese_account",
      "formal_tone": false,
      "cultural_adaptation": true
    }
  ]
}
```

## Phase 1: Core Implementation

### Step 5: Create Base Configuration Manager

#### Create `src/config/settings.py`
```python
import os
import json
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

class Settings:
    def __init__(self):
        # Twitter API credentials
        self.PRIMARY_TWITTER_CREDS = {
            'consumer_key': os.getenv('PRIMARY_TWITTER_CONSUMER_KEY'),
            'consumer_secret': os.getenv('PRIMARY_TWITTER_CONSUMER_SECRET'),
            'access_token': os.getenv('PRIMARY_TWITTER_ACCESS_TOKEN'),
            'access_token_secret': os.getenv('PRIMARY_TWITTER_ACCESS_TOKEN_SECRET')
        }
        
        self.PRIMARY_USERNAME = os.getenv('PRIMARY_TWITTER_USERNAME')
        
        # Google Gemini API
        self.GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
        self.GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
        
        # App settings
        self.POLL_INTERVAL = int(os.getenv('POLL_INTERVAL_SECONDS', 300))
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        
        # Load language configurations
        self.load_language_config()
        
        # API Limits
        self.TWITTER_FREE_MONTHLY_LIMIT = 1500
        self.TWITTER_FREE_DAILY_LIMIT = 50
        
    def load_language_config(self):
        config_path = Path('config/languages.json')
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                self.TARGET_LANGUAGES = config['target_languages']
        else:
            self.TARGET_LANGUAGES = []
    
    def get_twitter_creds_for_language(self, lang_code):
        """Get Twitter credentials for a specific language account"""
        lang_upper = lang_code.upper()
        return {
            'consumer_key': os.getenv(f'{lang_upper}_TWITTER_CONSUMER_KEY'),
            'consumer_secret': os.getenv(f'{lang_upper}_TWITTER_CONSUMER_SECRET'),
            'access_token': os.getenv(f'{lang_upper}_TWITTER_ACCESS_TOKEN'),
            'access_token_secret': os.getenv(f'{lang_upper}_TWITTER_ACCESS_TOKEN_SECRET')
        }

settings = Settings()
```

### Step 6: Create Logging Utility

#### Create `src/utils/logger.py`
```python
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

logger = Logger().get_logger()
```

### Step 7: Create Tweet Data Models

#### Create `src/models/tweet.py`
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

@dataclass
class Tweet:
    id: str
    text: str
    created_at: datetime
    author_username: str
    author_id: str
    public_metrics: Dict[str, int]
    in_reply_to_user_id: Optional[str] = None
    referenced_tweets: Optional[list] = None
    entities: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_twitter_api(cls, tweet_data):
        """Create Tweet object from Twitter API response"""
        return cls(
            id=tweet_data['id'],
            text=tweet_data['text'],
            created_at=datetime.fromisoformat(tweet_data['created_at'].replace('Z', '+00:00')),
            author_username=tweet_data.get('author_username', ''),
            author_id=tweet_data.get('author_id', ''),
            public_metrics=tweet_data.get('public_metrics', {}),
            in_reply_to_user_id=tweet_data.get('in_reply_to_user_id'),
            referenced_tweets=tweet_data.get('referenced_tweets', []),
            entities=tweet_data.get('entities', {})
        )

@dataclass
class Translation:
    original_tweet: Tweet
    target_language: str
    translated_text: str
    translation_timestamp: datetime
    character_count: int
    status: str  # 'pending', 'posted', 'failed'
    post_id: Optional[str] = None
    error_message: Optional[str] = None
```

### Step 8: Create Text Processing Utilities

#### Create `src/utils/text_processor.py`
```python
import re
from typing import List, Tuple

class TextProcessor:
    def __init__(self):
        # Regex patterns for preserving elements
        self.hashtag_pattern = re.compile(r'#\w+')
        self.mention_pattern = re.compile(r'@\w+')
        self.url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    
    def extract_preservable_elements(self, text: str) -> Tuple[str, dict]:
        """Extract hashtags, mentions, and URLs for preservation"""
        elements = {
            'hashtags': self.hashtag_pattern.findall(text),
            'mentions': self.mention_pattern.findall(text),
            'urls': self.url_pattern.findall(text)
        }
        
        # Create clean text for translation (replace preservable elements with placeholders)
        clean_text = text
        placeholder_map = {}
        
        # Replace URLs with placeholders
        for i, url in enumerate(elements['urls']):
            placeholder = f"{{URL_{i}}}"
            clean_text = clean_text.replace(url, placeholder)
            placeholder_map[placeholder] = url
        
        # Replace mentions with placeholders
        for i, mention in enumerate(elements['mentions']):
            placeholder = f"{{MENTION_{i}}}"
            clean_text = clean_text.replace(mention, placeholder)
            placeholder_map[placeholder] = mention
        
        # Replace hashtags with placeholders
        for i, hashtag in enumerate(elements['hashtags']):
            placeholder = f"{{HASHTAG_{i}}}"
            clean_text = clean_text.replace(hashtag, placeholder)
            placeholder_map[placeholder] = hashtag
        
        return clean_text, placeholder_map
    
    def restore_preservable_elements(self, translated_text: str, placeholder_map: dict) -> str:
        """Restore hashtags, mentions, and URLs in translated text"""
        restored_text = translated_text
        
        for placeholder, original in placeholder_map.items():
            restored_text = restored_text.replace(placeholder, original)
        
        return restored_text
    
    def get_character_count(self, text: str) -> int:
        """Get character count considering Twitter's counting rules"""
        # Twitter counts URLs as 23 characters regardless of actual length
        url_count = len(self.url_pattern.findall(text))
        text_without_urls = self.url_pattern.sub('', text)
        
        return len(text_without_urls) + (url_count * 23)
    
    def is_within_twitter_limit(self, text: str, limit: int = 280) -> bool:
        """Check if text is within Twitter character limit"""
        return self.get_character_count(text) <= limit

text_processor = TextProcessor()
```

### Step 9: Create Gemini Translation Service

#### Create `src/utils/prompt_builder.py`
```python
class PromptBuilder:
    def __init__(self):
        self.base_template = """You are a professional translator specializing in social media content. Translate the following English tweet to {target_language}, maintaining the original tone, style, and intent.

Requirements:
- Keep the same conversational tone and personality
- Preserve all hashtags, @mentions, and URLs exactly as they appear (including placeholders like {{URL_0}}, {{MENTION_0}}, {{HASHTAG_0}})
- Maintain the tweet's character count efficiency for the target platform
- Adapt cultural references appropriately for {target_language} speakers
- If the tweet contains slang or informal language, use equivalent expressions in the target language
- Do not add explanations or additional context
- Keep the translation concise and Twitter-appropriate

Original tweet: "{tweet_content}"

Translate to {target_language}:"""
    
    def build_translation_prompt(self, tweet_text: str, target_language: str, language_config: dict = None) -> str:
        """Build translation prompt for Gemini API"""
        prompt = self.base_template.format(
            target_language=target_language,
            tweet_content=tweet_text
        )
        
        # Add language-specific instructions if available
        if language_config:
            additional_instructions = []
            
            if not language_config.get('formal_tone', False):
                additional_instructions.append("- Use casual/informal tone appropriate for social media")
            else:
                additional_instructions.append("- Use polite/formal tone")
            
            if language_config.get('cultural_adaptation', True):
                additional_instructions.append(f"- Adapt cultural references for {target_language} speakers when possible")
            
            if additional_instructions:
                # Insert additional instructions before the original tweet
                insert_point = prompt.find('Original tweet:')
                additional_text = '\n' + '\n'.join(additional_instructions) + '\n\n'
                prompt = prompt[:insert_point] + additional_text + prompt[insert_point:]
        
        return prompt

prompt_builder = PromptBuilder()
```

#### Create `src/services/gemini_translator.py`
```python
import google.generativeai as genai
from typing import Dict, Optional
import time
import json
from ..config.settings import settings
from ..utils.logger import logger
from ..utils.text_processor import text_processor
from ..utils.prompt_builder import prompt_builder
from ..models.tweet import Translation, Tweet
from datetime import datetime

class GeminiTranslator:
    def __init__(self):
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
        self.translation_cache = {}  # Simple in-memory cache
    
    def translate_tweet(self, tweet: Tweet, target_language: str, language_config: dict = None) -> Optional[Translation]:
        """Translate a tweet using Gemini API"""
        try:
            # Check cache first
            cache_key = f"{tweet.id}_{target_language}"
            if cache_key in self.translation_cache:
                logger.info(f"Using cached translation for tweet {tweet.id} -> {target_language}")
                return self.translation_cache[cache_key]
            
            # Extract preservable elements
            clean_text, placeholder_map = text_processor.extract_preservable_elements(tweet.text)
            
            # Build prompt
            prompt = prompt_builder.build_translation_prompt(clean_text, target_language, language_config)
            
            logger.info(f"Translating tweet {tweet.id} to {target_language}")
            
            # Make API call to Gemini
            response = self.model.generate_content(prompt)
            
            translated_text = response.text.strip()
            
            # Restore preservable elements
            final_translation = text_processor.restore_preservable_elements(translated_text, placeholder_map)
            
            # Create Translation object
            translation = Translation(
                original_tweet=tweet,
                target_language=target_language,
                translated_text=final_translation,
                translation_timestamp=datetime.now(),
                character_count=text_processor.get_character_count(final_translation),
                status='pending'
            )
            
            # Validate character count
            if not text_processor.is_within_twitter_limit(final_translation):
                logger.warning(f"Translation exceeds character limit: {translation.character_count} chars")
                # Try to get a shorter version
                translation = self._get_shorter_translation(tweet, target_language, language_config, final_translation)
            
            # Cache the translation
            self.translation_cache[cache_key] = translation
            
            logger.info(f"Successfully translated tweet {tweet.id} to {target_language} ({translation.character_count} chars)")
            return translation
            
        except Exception as e:
            logger.error(f"Error translating tweet {tweet.id} to {target_language}: {str(e)}")
            return None
    
    def _get_shorter_translation(self, tweet: Tweet, target_language: str, language_config: dict, current_translation: str) -> Translation:
        """Get a shorter version of the translation"""
        try:
            shorter_prompt = f"""The following translation is {text_processor.get_character_count(current_translation)} characters, which exceeds Twitter's limit. 
Please provide a shorter version that maintains the core meaning and tone:

Original: "{tweet.text}"
Current translation: "{current_translation}"
Target language: {target_language}
Character limit: 280

Shortened translation:"""
            
            response = self.model.generate_content(shorter_prompt)
            
            shorter_text = response.text.strip()
            
            return Translation(
                original_tweet=tweet,
                target_language=target_language,
                translated_text=shorter_text,
                translation_timestamp=datetime.now(),
                character_count=text_processor.get_character_count(shorter_text),
                status='pending'
            )
            
        except Exception as e:
            logger.error(f"Error getting shorter translation: {str(e)}")
            # Return original translation even if too long
            return Translation(
                original_tweet=tweet,
                target_language=target_language,
                translated_text=current_translation,
                translation_timestamp=datetime.now(),
                character_count=text_processor.get_character_count(current_translation),
                status='pending'
            )

gemini_translator = GeminiTranslator()
```

### Step 10: Create Twitter Monitor Service

#### Create `src/services/twitter_monitor.py`
```python
import tweepy
from typing import List, Optional
import json
from datetime import datetime, timedelta
from pathlib import Path
from ..config.settings import settings
from ..utils.logger import logger
from ..models.tweet import Tweet

class TwitterMonitor:
    def __init__(self):
        # Initialize Twitter API client for primary account
        self.api = self._create_twitter_client(settings.PRIMARY_TWITTER_CREDS)
        self.last_tweet_id_file = Path('logs/last_tweet_id.txt')
        self.api_usage_file = Path('logs/api_usage.json')
        self.daily_requests = 0
        self.monthly_posts = 0
        self.load_api_usage()
    
    def _create_twitter_client(self, credentials: dict):
        """Create Twitter API client with given credentials"""
        auth = tweepy.OAuth1UserHandler(
            credentials['consumer_key'],
            credentials['consumer_secret'],
            credentials['access_token'],
            credentials['access_token_secret']
        )
        
        return tweepy.API(auth, wait_on_rate_limit=True)
    
    def load_api_usage(self):
        """Load API usage tracking from file"""
        if self.api_usage_file.exists():
            try:
                with open(self.api_usage_file, 'r') as f:
                    usage_data = json.load(f)
                    today = datetime.now().strftime('%Y-%m-%d')
                    month = datetime.now().strftime('%Y-%m')
                    
                    # Load daily requests
                    if usage_data.get('date') == today:
                        self.daily_requests = usage_data.get('daily_requests', 0)
                    
                    # Load monthly posts
                    if usage_data.get('month') == month:
                        self.monthly_posts = usage_data.get('monthly_posts', 0)
                        
            except Exception as e:
                logger.error(f"Error loading API usage: {str(e)}")
                self.daily_requests = 0
                self.monthly_posts = 0
    
    def save_api_usage(self):
        """Save API usage tracking to file"""
        try:
            usage_data = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'month': datetime.now().strftime('%Y-%m'),
                'daily_requests': self.daily_requests,
                'monthly_posts': self.monthly_posts,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.api_usage_file, 'w') as f:
                json.dump(usage_data, f)
                
        except Exception as e:
            logger.error(f"Error saving API usage: {str(e)}")
    
    def can_make_request(self) -> bool:
        """Check if we can make a Twitter API request without exceeding limits"""
        return self.daily_requests < settings.TWITTER_FREE_DAILY_LIMIT
    
    def can_post_tweet(self) -> bool:
        """Check if we can post a tweet without exceeding monthly limit"""
        return self.monthly_posts < settings.TWITTER_FREE_MONTHLY_LIMIT
    
    def get_last_tweet_id(self) -> Optional[str]:
        """Get the ID of the last processed tweet"""
        if self.last_tweet_id_file.exists():
            try:
                with open(self.last_tweet_id_file, 'r') as f:
                    return f.read().strip()
            except Exception as e:
                logger.error(f"Error reading last tweet ID: {str(e)}")
        return None
    
    def save_last_tweet_id(self, tweet_id: str):
        """Save the ID of the last processed tweet"""
        try:
            with open(self.last_tweet_id_file, 'w') as f:
                f.write(tweet_id)
        except Exception as e:
            logger.error(f"Error saving last tweet ID: {str(e)}")
    
    def get_new_tweets(self) -> List[Tweet]:
        """Get new tweets from the primary account"""
        if not self.can_make_request():
            logger.warning("Daily API request limit reached, skipping tweet fetch")
            return []
        
        try:
            last_id = self.get_last_tweet_id()
            
            # Fetch tweets from primary account
            tweets = tweepy.Cursor(
                self.api.user_timeline,
                screen_name=settings.PRIMARY_USERNAME,
                since_id=last_id,
                include_rts=False,  # Don't include retweets
                exclude_replies=True,  # Don't include replies
                tweet_mode='extended'
            ).items(10)  # Limit to 10 most recent tweets
            
            new_tweets = []
            latest_tweet_id = last_id
            
            for tweet_data in tweets:
                # Convert tweepy Status to our Tweet model
                tweet = Tweet(
                    id=str(tweet_data.id),
                    text=tweet_data.full_text,
                    created_at=tweet_data.created_at,
                    author_username=tweet_data.user.screen_name,
                    author_id=str(tweet_data.user.id),
                    public_metrics={
                        'retweet_count': tweet_data.retweet_count,
                        'favorite_count': tweet_data.favorite_count
                    }
                )
                
                new_tweets.append(tweet)
                latest_tweet_id = tweet.id
            
            # Update request counter and save usage
            self.daily_requests += 1
            self.save_api_usage()
            
            # Save the latest tweet ID
            if latest_tweet_id and latest_tweet_id != last_id:
                self.save_last_tweet_id(latest_tweet_id)
            
            logger.info(f"Found {len(new_tweets)} new tweets from @{settings.PRIMARY_USERNAME}")
            return new_tweets
            
        except Exception as e:
            logger.error(f"Error fetching new tweets: {str(e)}")
            return []

twitter_monitor = TwitterMonitor()
```

### Step 11: Create Draft Management System

#### Create `draft_manager.py` (in root directory)
```python
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from src.models.tweet import Translation
from src.utils.logger import logger

class DraftManager:
    def __init__(self):
        self.pending_dir = Path('drafts/pending')
        self.posted_dir = Path('drafts/posted')
        
        # Ensure directories exist
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.posted_dir.mkdir(parents=True, exist_ok=True)
    
    def save_translation_as_draft(self, translation: Translation, language_config: dict) -> bool:
        """Save a translation as a draft file"""
        try:
            draft_data = {
                'original_tweet_id': translation.original_tweet.id,
                'original_text': translation.original_tweet.text,
                'translated_text': translation.translated_text,
                'target_language': translation.target_language,
                'language_config': language_config,
                'character_count': translation.character_count,
                'created_at': translation.translation_timestamp.isoformat(),
                'status': 'draft'
            }
            
            # Create filename with timestamp and language
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{translation.target_language}_{translation.original_tweet.id}.json"
            filepath = self.pending_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(draft_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved translation as draft: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving draft: {str(e)}")
            return False
    
    def get_pending_drafts(self) -> List[Dict]:
        """Get all pending draft files"""
        drafts = []
        
        try:
            for draft_file in self.pending_dir.glob('*.json'):
                with open(draft_file, 'r', encoding='utf-8') as f:
                    draft_data = json.load(f)
                    draft_data['file_path'] = str(draft_file)
                    drafts.append(draft_data)
        
        except Exception as e:
            logger.error(f"Error reading drafts: {str(e)}")
        
        # Sort by creation date
        drafts.sort(key=lambda x: x['created_at'])
        return drafts
    
    def mark_draft_as_posted(self, draft_file_path: str, post_id: str) -> bool:
        """Move draft from pending to posted directory"""
        try:
            draft_path = Path(draft_file_path)
            
            if not draft_path.exists():
                logger.error(f"Draft file not found: {draft_path}")
                return False
            
            # Read draft data
            with open(draft_path, 'r', encoding='utf-8') as f:
                draft_data = json.load(f)
            
            # Update with posting info
            draft_data['status'] = 'posted'
            draft_data['posted_at'] = datetime.now().isoformat()
            draft_data['post_id'] = post_id
            
            # Move to posted directory
            posted_path = self.posted_dir / draft_path.name
            with open(posted_path, 'w', encoding='utf-8') as f:
                json.dump(draft_data, f, indent=2, ensure_ascii=False)
            
            # Remove from pending
            draft_path.unlink()
            
            logger.info(f"Moved draft to posted: {posted_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error marking draft as posted: {str(e)}")
            return False
    
    def get_draft_count(self) -> int:
        """Get count of pending drafts"""
        return len(list(self.pending_dir.glob('*.json')))
    
    def display_pending_drafts(self):
        """Display pending drafts in a readable format"""
        drafts = self.get_pending_drafts()
        
        if not drafts:
            print("No pending drafts found.")
            return
        
        print(f"\n=== {len(drafts)} Pending Drafts ===\n")
        
        for i, draft in enumerate(drafts, 1):
            created_at = datetime.fromisoformat(draft['created_at'])
            print(f"{i}. [{draft['target_language'].upper()}] ({created_at.strftime('%Y-%m-%d %H:%M')})")
            print(f"   Original: {draft['original_text'][:100]}...")
            print(f"   Translation: {draft['translated_text']}")
            print(f"   Characters: {draft['character_count']}")
            print(f"   File: {Path(draft['file_path']).name}")
            print()

draft_manager = DraftManager()

if __name__ == "__main__":
    # Command-line interface for managing drafts
    draft_manager.display_pending_drafts()
```

## Phase 2: Integration and Publishing

### Step 12: Create Multi-Account Publisher

#### Create `src/services/publisher.py`
```python
import tweepy
from typing import Dict, Optional, List
from ..config.settings import settings
from ..utils.logger import logger
from ..models.tweet import Translation
from ..services.twitter_monitor import twitter_monitor

class TwitterPublisher:
    def __init__(self):
        self.language_clients = {}
        self._initialize_language_clients()
    
    def _initialize_language_clients(self):
        """Initialize Twitter API clients for each language account"""
        for lang_config in settings.TARGET_LANGUAGES:
            lang_code = lang_config['code']
            credentials = settings.get_twitter_creds_for_language(lang_code)
            
            if all(credentials.values()):
                try:
                    auth = tweepy.OAuth1UserHandler(
                        credentials['consumer_key'],
                        credentials['consumer_secret'],
                        credentials['access_token'],
                        credentials['access_token_secret']
                    )
                    
                    client = tweepy.API(auth, wait_on_rate_limit=True)
                    self.language_clients[lang_code] = client
                    logger.info(f"Initialized Twitter client for {lang_code}")
                    
                except Exception as e:
                    logger.error(f"Failed to initialize Twitter client for {lang_code}: {str(e)}")
            else:
                logger.warning(f"Missing credentials for {lang_code} Twitter account")
    
    def can_post(self) -> bool:
        """Check if we can post without exceeding API limits"""
        return twitter_monitor.can_post_tweet()
    
    def post_translation(self, translation: Translation) -> bool:
        """Post a translation to the appropriate language account"""
        if not self.can_post():
            logger.warning("Monthly posting limit reached, cannot post translation")
            return False
        
        lang_code = translation.target_language
        
        if lang_code not in self.language_clients:
            logger.error(f"No Twitter client available for language: {lang_code}")
            return False
        
        try:
            client = self.language_clients[lang_code]
            
            # Post the tweet
            status = client.update_status(translation.translated_text)
            
            # Update translation status
            translation.status = 'posted'
            translation.post_id = str(status.id)
            
            # Update API usage counter
            twitter_monitor.monthly_posts += 1
            twitter_monitor.save_api_usage()
            
            logger.info(f"Successfully posted translation to {lang_code}: {status.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error posting translation to {lang_code}: {str(e)}")
            translation.status = 'failed'
            translation.error_message = str(e)
            return False
    
    def post_multiple_translations(self, translations: List[Translation]) -> Dict[str, bool]:
        """Post multiple translations, returning success status for each"""
        results = {}
        
        for translation in translations:
            lang_code = translation.target_language
            results[lang_code] = self.post_translation(translation)
            
            # Stop if we hit API limits
            if not self.can_post():
                logger.warning("Reached API limits, stopping batch posting")
                break
        
        return results

twitter_publisher = TwitterPublisher()
```

### Step 13: Create Main Application Logic

#### Create `main.py`
```python
#!/usr/bin/env python3
import time
import schedule
from typing import List
from src.services.twitter_monitor import twitter_monitor
from src.services.gemini_translator import gemini_translator
from src.services.publisher import twitter_publisher
from src.config.settings import settings
from src.utils.logger import logger
from src.models.tweet import Translation
from draft_manager import draft_manager

class TwitterTranslationBot:
    def __init__(self):
        self.running = False
    
    def process_new_tweets(self):
        """Main processing function - check for new tweets and translate them"""
        logger.info("Checking for new tweets...")
        
        try:
            # Get new tweets from primary account
            new_tweets = twitter_monitor.get_new_tweets()
            
            if not new_tweets:
                logger.info("No new tweets found")
                return
            
            # Process each tweet
            for tweet in new_tweets:
                logger.info(f"Processing tweet {tweet.id}: {tweet.text[:50]}...")
                
                # Translate to each target language
                for lang_config in settings.TARGET_LANGUAGES:
                    translation = gemini_translator.translate_tweet(
                        tweet, 
                        lang_config['name'], 
                        lang_config
                    )
                    
                    if translation:
                        # Try to post translation
                        if twitter_publisher.can_post():
                            success = twitter_publisher.post_translation(translation)
                            if success:
                                logger.info(f"Posted translation to {lang_config['code']}: {translation.post_id}")
                            else:
                                logger.warning(f"Failed to post to {lang_config['code']}, saving as draft")
                                draft_manager.save_translation_as_draft(translation, lang_config)
                        else:
                            # Save as draft when API limits reached
                            logger.info(f"API limit reached, saving {lang_config['code']} translation as draft")
                            draft_manager.save_translation_as_draft(translation, lang_config)
                    else:
                        logger.error(f"Failed to translate tweet {tweet.id} to {lang_config['name']}")
                
                # Small delay between tweets to be respectful
                time.sleep(2)
        
        except Exception as e:
            logger.error(f"Error in process_new_tweets: {str(e)}")
    
    def run_once(self):
        """Run the bot once (useful for testing)"""
        logger.info("Running Twitter Translation Bot (single run)")
        self.process_new_tweets()
        
        # Show draft status
        draft_count = draft_manager.get_draft_count()
        if draft_count > 0:
            logger.info(f"Current pending drafts: {draft_count}")
    
    def run_scheduled(self):
        """Run the bot on a schedule"""
        logger.info("Starting Twitter Translation Bot (scheduled mode)")
        
        # Schedule the job
        schedule.every(settings.POLL_INTERVAL).seconds.do(self.process_new_tweets)
        
        self.running = True
        
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping bot due to keyboard interrupt")
            self.running = False
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            self.running = False
    
    def stop(self):
        """Stop the scheduled bot"""
        self.running = False

def main():
    import sys
    
    bot = TwitterTranslationBot()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'once':
            bot.run_once()
        elif command == 'drafts':
            draft_manager.display_pending_drafts()
        elif command == 'status':
            print(f"Daily API requests: {twitter_monitor.daily_requests}/{settings.TWITTER_FREE_DAILY_LIMIT}")
            print(f"Monthly posts: {twitter_monitor.monthly_posts}/{settings.TWITTER_FREE_MONTHLY_LIMIT}")
            print(f"Pending drafts: {draft_manager.get_draft_count()}")
        else:
            print("Usage: python main.py [once|drafts|status]")
            print("  once   - Run once and exit")
            print("  drafts - Show pending drafts")
            print("  status - Show API usage status")
            print("  (no args) - Run continuously on schedule")
    else:
        bot.run_scheduled()

if __name__ == "__main__":
    main()
```

## Phase 3: Testing and Configuration

### Step 14: Create Test Configuration

#### Create `.env` file from template
```bash
cp config/.env.template .env
# Edit .env with your actual credentials
```

### Step 15: Test Individual Components

#### Create test script `test_components.py`
```python
#!/usr/bin/env python3
"""Test individual components of the Twitter bot"""

from src.services.twitter_monitor import twitter_monitor
from src.services.gemini_translator import gemini_translator
from src.utils.logger import logger
from src.config.settings import settings

def test_twitter_connection():
    """Test Twitter API connection"""
    print("Testing Twitter API connection...")
    try:
        tweets = twitter_monitor.get_new_tweets()
        print(f"✓ Successfully connected to Twitter API")
        print(f"✓ Found {len(tweets)} recent tweets")
        return True
    except Exception as e:
        print(f"✗ Twitter API connection failed: {str(e)}")
        return False

def test_gemini_translation():
    """Test Gemini API translation"""
    print("Testing Gemini API translation...")
    try:
        from src.models.tweet import Tweet
        from datetime import datetime
        
        # Create a test tweet
        test_tweet = Tweet(
            id="test123",
            text="Hello world! This is a test tweet with #hashtag and @mention",
            created_at=datetime.now(),
            author_username="test_user",
            author_id="123",
            public_metrics={}
        )
        
        # Test translation
        if settings.TARGET_LANGUAGES:
            lang_config = settings.TARGET_LANGUAGES[0]
            translation = gemini_translator.translate_tweet(
                test_tweet, 
                lang_config['name'], 
                lang_config
            )
            
            if translation:
                print(f"✓ Successfully translated test tweet")
                print(f"  Original: {test_tweet.text}")
                print(f"  Translation: {translation.translated_text}")
                print(f"  Character count: {translation.character_count}")
                return True
        
        print("✗ No target languages configured")
        return False
        
    except Exception as e:
        print(f"✗ Gemini API translation failed: {str(e)}")
        return False

def test_draft_system():
    """Test draft management system"""
    print("Testing draft management system...")
    try:
        from draft_manager import draft_manager
        
        draft_count = draft_manager.get_draft_count()
        print(f"✓ Draft system working, {draft_count} pending drafts")
        return True
        
    except Exception as e:
        print(f"✗ Draft system test failed: {str(e)}")
        return False

def main():
    print("=== Twitter Translation Bot Component Tests ===\n")
    
    tests = [
        test_twitter_connection,
        test_gemini_translation,
        test_draft_system
    ]
    
    results = []
    for test in tests:
        result = test()
        results.append(result)
        print()
    
    passed = sum(results)
    total = len(results)
    
    print(f"=== Test Results: {passed}/{total} passed ===")
    
    if passed == total:
        print("✓ All tests passed! Bot is ready to run.")
    else:
        print("✗ Some tests failed. Check configuration and credentials.")

if __name__ == "__main__":
    main()
```

## Phase 4: Deployment Options

### Step 16: GitHub Actions Deployment (Recommended)

#### Create `.github/workflows/twitter-bot.yml`
```yaml
name: Twitter Translation Bot

on:
  schedule:
    - cron: '*/30 * * * *'  # Run every 30 minutes
  workflow_dispatch:  # Allow manual runs

jobs:
  translate-tweets:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Create necessary directories
      run: |
        mkdir -p logs drafts/pending drafts/posted
    
    - name: Run bot
      env:
        PRIMARY_TWITTER_CONSUMER_KEY: ${{ secrets.PRIMARY_TWITTER_CONSUMER_KEY }}
        PRIMARY_TWITTER_CONSUMER_SECRET: ${{ secrets.PRIMARY_TWITTER_CONSUMER_SECRET }}
        PRIMARY_TWITTER_ACCESS_TOKEN: ${{ secrets.PRIMARY_TWITTER_ACCESS_TOKEN }}
        PRIMARY_TWITTER_ACCESS_TOKEN_SECRET: ${{ secrets.PRIMARY_TWITTER_ACCESS_TOKEN_SECRET }}
        PRIMARY_TWITTER_USERNAME: ${{ secrets.PRIMARY_TWITTER_USERNAME }}
        
        JAPANESE_TWITTER_CONSUMER_KEY: ${{ secrets.JAPANESE_TWITTER_CONSUMER_KEY }}
        JAPANESE_TWITTER_CONSUMER_SECRET: ${{ secrets.JAPANESE_TWITTER_CONSUMER_SECRET }}
        JAPANESE_TWITTER_ACCESS_TOKEN: ${{ secrets.JAPANESE_TWITTER_ACCESS_TOKEN }}
        JAPANESE_TWITTER_ACCESS_TOKEN_SECRET: ${{ secrets.JAPANESE_TWITTER_ACCESS_TOKEN_SECRET }}
        
        GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
GEMINI_MODEL: ${{ secrets.GEMINI_MODEL }}
        
        POLL_INTERVAL_SECONDS: 300
        LOG_LEVEL: INFO
      run: |
        python main.py once
    
    - name: Upload logs
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: bot-logs
        path: logs/
        retention-days: 7
    
    - name: Upload drafts
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: pending-drafts
        path: drafts/
        retention-days: 30
```

### Step 17: Local Development Setup

#### Create `run_local.py`
```python
#!/usr/bin/env python3
"""Local development runner with enhanced features"""

import os
import sys
import time
from pathlib import Path
from main import TwitterTranslationBot
from draft_manager import draft_manager

def setup_local_environment():
    """Set up local development environment"""
    # Create necessary directories
    Path("logs").mkdir(exist_ok=True)
    Path("drafts/pending").mkdir(parents=True, exist_ok=True)
    Path("drafts/posted").mkdir(parents=True, exist_ok=True)
    
    # Check for .env file
    if not Path(".env").exists():
        print("❌ .env file not found!")
        print("Please copy .env.template to .env and fill in your credentials.")
        return False
    
    return True

def interactive_menu():
    """Interactive menu for local development"""
    bot = TwitterTranslationBot()
    
    while True:
        print("\n=== Twitter Translation Bot - Local Development ===")
        print("1. Run once")
        print("2. Run continuously") 
        print("3. Show pending drafts")
        print("4. Show API status")
        print("5. Test components")
        print("6. Exit")
        
        choice = input("\nSelect option (1-6): ").strip()
        
        if choice == '1':
            print("\n--- Running bot once ---")
            bot.run_once()
            
        elif choice == '2':
            print("\n--- Running bot continuously (Ctrl+C to stop) ---")
            try:
                bot.run_scheduled()
            except KeyboardInterrupt:
                print("\nBot stopped by user")
                
        elif choice == '3':
            print("\n--- Pending Drafts ---")
            draft_manager.display_pending_drafts()
            
        elif choice == '4':
            print("\n--- API Status ---")
            from src.services.twitter_monitor import twitter_monitor
            from src.config.settings import settings
            print(f"Daily API requests: {twitter_monitor.daily_requests}/{settings.TWITTER_FREE_DAILY_LIMIT}")
            print(f"Monthly posts: {twitter_monitor.monthly_posts}/{settings.TWITTER_FREE_MONTHLY_LIMIT}")
            print(f"Pending drafts: {draft_manager.get_draft_count()}")
            
        elif choice == '5':
            print("\n--- Testing Components ---")
            os.system('python test_components.py')
            
        elif choice == '6':
            print("Goodbye!")
            break
            
        else:
            print("Invalid choice, please try again")

def main():
    if not setup_local_environment():
        return 1
    
    if len(sys.argv) > 1:
        # Command line mode
        command = sys.argv[1].lower()
        bot = TwitterTranslationBot()
        
        if command == 'once':
            bot.run_once()
        elif command == 'continuous':
            bot.run_scheduled()
        elif command == 'test':
            os.system('python test_components.py')
        else:
            print("Usage: python run_local.py [once|continuous|test]")
            return 1
    else:
        # Interactive mode
        interactive_menu()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

## Phase 5: Documentation and Final Setup

### Step 18: Create README

#### Create `README.md`
```markdown
# Twitter Auto-Translation Bot

Automatically translates tweets from your primary English account to multiple language-specific accounts using Google's Gemini AI API.

## Features

- 🔄 Automatic tweet monitoring and translation
- 🌍 Multi-language support with cultural adaptation
- 💾 Draft system for API limit management
- 🆓 Designed for Twitter's free tier (1,500 tweets/month)
- 🤖 High-quality translations using Gemini AI
- 📊 Usage tracking and logging
- ☁️ Free deployment options

## Quick Start

### 1. Clone and Setup
```bash
git clone <your-repo>
cd twitter_bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Credentials
```bash
cp config/.env.template .env
# Edit .env with your API credentials
```

### 3. Test Setup
```bash
python test_components.py
```

### 4. Run Bot
```bash
# Run once
python main.py once

# Run continuously
python main.py

# Interactive local development
python run_local.py
```

## Configuration

### Required API Keys

1. **Twitter API**: Create apps at https://developer.twitter.com/
   - One app per Twitter account (primary + each language account)
   - Copy Consumer Key/Secret and Access Token/Secret for each

2. **Google Gemini API**: Get key from https://makersuite.google.com/app/apikey
   - Generous free tier available, paid tier ~$0-5/month

### Language Configuration

Edit `config/languages.json`:

```json
{
  "target_languages": [
    {
      "code": "ja",
      "name": "Japanese", 
      "twitter_username": "your_japanese_account",
      "formal_tone": false,
      "cultural_adaptation": true
    }
  ]
}
```

## Deployment Options

### GitHub Actions (Recommended - Free)
1. Push code to GitHub repository
2. Add secrets in repository settings:
   - All Twitter API credentials
   - GOOGLE_API_KEY
3. Bot runs automatically every 30 minutes

### Local Machine
```bash
python run_local.py continuous
```

### Oracle Cloud (Free Forever)
1. Create free Oracle Cloud account
2. Launch free ARM instance
3. Deploy code and run with systemd

## Usage

### Command Line Options
```bash
python main.py once      # Run once and exit
python main.py drafts    # Show pending drafts
python main.py status    # Show API usage
python main.py           # Run continuously
```

### Draft Management
When Twitter API limits are reached, translations are saved as drafts:
- Location: `drafts/pending/`
- Manual posting: Review and post drafts when limits reset
- Auto-retry: System automatically retries when quotas reset

## Cost Estimation

- **Twitter API**: Free (1,500 tweets/month limit)
- **Google Gemini**: $0-5/month (generous free tier)
- **Hosting**: Free (GitHub Actions, Oracle Cloud, or local)
- **Total**: $0-5/month

## Troubleshooting

### Common Issues

1. **Twitter API Errors**
   - Check credentials in .env file
   - Verify account permissions
   - Check API usage limits

2. **Translation Failures**
   - Verify Google API key
   - Check internet connection
   - Review error logs in logs/

3. **Character Limit Issues**
   - Bot automatically shortens translations
   - Manual review may be needed for some tweets

### Support

Check logs in `logs/` directory for detailed error information.

## License

MIT License - see LICENSE file for details.
```

### Step 19: Create Setup Script

#### Create `setup.sh`
```bash
#!/bin/bash
# Twitter Translation Bot Setup Script

echo "=== Twitter Translation Bot Setup ==="
echo

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1)
if [[ $? -eq 0 ]]; then
    echo "✓ Python found: $python_version"
else
    echo "✗ Python 3 not found. Please install Python 3.7+ first."
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment..."
if python3 -m venv venv; then
    echo "✓ Virtual environment created"
else
    echo "✗ Failed to create virtual environment"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
if pip install -r requirements.txt; then
    echo "✓ Dependencies installed"
else
    echo "✗ Failed to install dependencies"
    exit 1
fi

# Create necessary directories
echo "Creating directories..."
mkdir -p logs drafts/{pending,posted}
echo "✓ Directories created"

# Copy environment template
if [[ ! -f .env ]]; then
    echo "Creating .env file from template..."
    cp config/.env.template .env
    echo "✓ .env file created"
    echo "⚠️  Please edit .env file with your API credentials"
else
    echo "✓ .env file already exists"
fi

echo
echo "=== Setup Complete ==="
echo
echo "Next steps:"
echo "1. Edit .env file with your API credentials"
echo "2. Edit config/languages.json with your target languages" 
echo "3. Run: python test_components.py"
echo "4. Run: python main.py once"
echo
echo "For local development: python run_local.py"
echo "For GitHub Actions: Push to GitHub and configure secrets"
echo
```

### Step 20: Final Testing and Documentation

#### Create `DEPLOYMENT.md`
```markdown
# Deployment Guide

## GitHub Actions Deployment (Recommended)

### 1. Repository Setup
1. Create new GitHub repository
2. Push your bot code to the repository
3. Ensure `.github/workflows/twitter-bot.yml` is included

### 2. Configure Secrets
Go to repository Settings → Secrets and variables → Actions

Add these secrets:

**Primary Account:**
- `PRIMARY_TWITTER_CONSUMER_KEY`
- `PRIMARY_TWITTER_CONSUMER_SECRET` 
- `PRIMARY_TWITTER_ACCESS_TOKEN`
- `PRIMARY_TWITTER_ACCESS_TOKEN_SECRET`
- `PRIMARY_TWITTER_USERNAME`

**Language Accounts (example for Japanese):**
- `JAPANESE_TWITTER_CONSUMER_KEY`
- `JAPANESE_TWITTER_CONSUMER_SECRET`
- `JAPANESE_TWITTER_ACCESS_TOKEN`
- `JAPANESE_TWITTER_ACCESS_TOKEN_SECRET`

**Google Gemini API:**
- `GOOGLE_API_KEY`
- `GEMINI_MODEL` (optional, defaults to gemini-1.5-flash)

### 3. Test Workflow
1. Go to Actions tab
2. Select "Twitter Translation Bot"
3. Click "Run workflow"
4. Check logs for any errors

### 4. Monitor Operation
- Workflow runs every 30 minutes automatically
- Check Actions tab for run history
- Download artifacts to see logs and drafts
- Bot respects API limits automatically

## Alternative Deployments

### Local Machine (Development)
```bash
# Setup
./setup.sh
source venv/bin/activate

# Run interactively
python run_local.py

# Run once
python main.py once

# Run continuously
python main.py
```

### Oracle Cloud Free Tier
1. Create Oracle Cloud account
2. Launch free ARM instance (up to 24GB RAM)
3. Install Python and dependencies
4. Clone repository
5. Setup systemd service:

```bash
# Create service file
sudo tee /etc/systemd/system/twitter-bot.service > /dev/null <<EOF
[Unit]
Description=Twitter Translation Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/twitter_bot
Environment=PATH=/home/ubuntu/twitter_bot/venv/bin
ExecStart=/home/ubuntu/twitter_bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl enable twitter-bot
sudo systemctl start twitter-bot

# Check status
sudo systemctl status twitter-bot
```

### Railway/Render Free Tier
1. Connect GitHub repository
2. Set environment variables in platform
3. Use `Procfile`:
```
worker: python main.py
```

## Monitoring and Maintenance

### Check Bot Status
```bash
# Show current status
python main.py status

# View pending drafts
python main.py drafts

# View logs
tail -f logs/twitter_bot_$(date +%Y-%m-%d).log
```

### Managing API Limits
- Bot automatically tracks Twitter API usage
- Switches to draft mode when limits reached
- Monthly limits reset on the first of each month
- Daily limits reset every 24 hours

### Draft Management
When API limits are reached:
1. Translations saved to `drafts/pending/`
2. Review drafts with `python main.py drafts`
3. Manual posting available through draft system
4. Auto-retry when quotas reset (if enabled)

### Cost Management
- Set Google API spending limits in console
- Monitor usage in Google AI Studio dashboard
- Bot only translates when within limits

## Troubleshooting

### GitHub Actions Issues
1. **Secrets not working**: Ensure exact secret names match workflow
2. **Dependencies fail**: Check requirements.txt format
3. **Bot not running**: Check workflow triggers and schedule syntax

### API Issues
1. **Twitter 401 errors**: Check credentials and account permissions
2. **Rate limits**: Normal behavior, bot will wait/use drafts
3. **Gemini API errors**: Check API key and billing status

### File System Issues
1. **Permission denied**: Ensure write access to logs/ and drafts/
2. **Missing directories**: Run setup.sh or create manually
3. **Log files growing**: Implement log rotation if needed

## Security Best Practices

1. **Never commit .env files** - use .gitignore
2. **Rotate API keys regularly** - Twitter and Google AI Studio consoles
3. **Monitor API usage** - Watch for unexpected spikes
4. **Use least privilege** - Twitter apps should have minimal permissions
5. **Keep dependencies updated** - Regular pip updates

## Performance Optimization

### For High-Volume Accounts
- Use Gemini 1.5 Pro for better quality (still very cost-effective)
- Increase polling frequency (lower POLL_INTERVAL_SECONDS)
- Consider paid Twitter API tier if needed
- Implement caching for repeated translations

### For Multiple Languages
- Add languages incrementally
- Monitor translation costs (minimal with Gemini free tier)
- Use language-specific optimization prompts
- Consider different Gemini models per language complexity

## Support

For issues:
1. Check logs first: `logs/twitter_bot_YYYY-MM-DD.log`
2. Test components: `python test_components.py`
3. Verify configuration: Review .env and languages.json
4. Check API status: Twitter Developer Portal and Google AI Studio Console
```

## Final Steps

### Step 21: Complete Project Structure Verification

<function_calls>
<invoke name="TodoWrite">
<parameter name="todos">[{"id": "1", "content": "Create comprehensive step-by-step implementation guide", "status": "completed", "priority": "high"}, {"id": "2", "content": "Break down setup requirements and prerequisites", "status": "completed", "priority": "high"}, {"id": "3", "content": "Detail code implementation steps for each component", "status": "completed", "priority": "high"}, {"id": "4", "content": "Include deployment and configuration instructions", "status": "completed", "priority": "medium"}]