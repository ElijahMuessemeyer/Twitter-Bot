# Twitter Auto-Translation Bot - Planning Document

## Project Overview

This system will automatically monitor tweets from a primary English Twitter account, translate them to alternate languages using Google's Gemini AI API, and post them to corresponding language-specific Twitter accounts.

## System Architecture

### Core Components

1. **Tweet Monitor Service**
   - Monitors primary English account for new tweets
   - Uses Twitter API v2 streaming or polling
   - Handles rate limiting and API quotas

2. **Gemini Translation Service**
   - Uses Google Gemini AI for high-quality, context-aware translations
   - Preserves hashtags, mentions, URLs, and cultural nuances
   - Handles character limits and cultural adaptation per language
   - Provides consistent tone and style matching

3. **Multi-Account Publisher**
   - Posts translated content to language-specific accounts
   - Manages authentication for multiple accounts
   - Handles posting failures and retries

4. **Configuration Manager**
   - Manages language mappings and account credentials
   - Easily extensible for adding new languages
   - Stores translation preferences and prompting strategies

### Technical Stack Recommendations

**Primary Language**: Python
- Rich ecosystem for API integrations
- Excellent for Claude API integration
- Good for automation and scheduling

**Key Dependencies**:
- `tweepy` - Twitter API wrapper
- `google-generativeai` - Official Google Gemini API client
- `python-dotenv` - Environment configuration
- `schedule` or `APScheduler` - Task scheduling
- `logging` - Comprehensive logging
- `requests` - HTTP client for APIs

## API Requirements

### Twitter API v2 Access
- **Essential Access Level**: Basic (free) or Elevated
- **Required Endpoints**:
  - GET /2/tweets/search/recent (monitor tweets)
  - POST /2/tweets (publish translated tweets)
  - GET /2/users/me (account verification)

### Authentication Requirements
- OAuth 2.0 Bearer Token for read operations
- OAuth 1.0a for write operations (posting tweets)
- Separate credentials for each target language account

### Google Gemini API
**Translation Service**: Gemini AI (1.5 Flash/Pro)
- **Pros**: 
  - Superior context understanding and cultural nuance handling
  - Maintains tone, style, and intent better than traditional translation APIs
  - Can adapt content for cultural appropriateness
  - Supports all major languages with high quality
  - Single API for all translation needs
  - Generous free tier available
- **Cost**: 
  - Gemini 1.5 Flash: Free tier up to 15 requests/minute, 1,500 requests/day
  - Gemini 1.5 Pro: Free tier up to 2 requests/minute, 50 requests/day
  - Paid tier: $0.075 per 1M input tokens, $0.30 per 1M output tokens
  - Estimated cost: $0-5/month for typical personal account usage

## System Design

### Directory Structure
```
twitter_bot/
├── src/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   └── languages.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── twitter_monitor.py
│   │   ├── gemini_translator.py
│   │   └── publisher.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tweet.py
│   │   └── translation.py
│   └── utils/
│       ├── __init__.py
│       ├── text_processor.py
│       ├── prompt_builder.py
│       └── logger.py
├── tests/
├── config/
│   ├── .env.template
│   └── languages.json
├── logs/
├── requirements.txt
├── main.py
└── README.md
```

### Core Data Flow

1. **Monitor Phase**
   - Poll primary account every 1-5 minutes
   - Store last processed tweet ID to avoid duplicates
   - Filter out replies, retweets (configurable)

2. **Translation Phase**
   - Extract tweet text, preserving special elements
   - Build context-aware prompts for Gemini API
   - Request translations with cultural adaptation
   - Validate character limits and adjust if needed
   - Cache translations to avoid re-processing

3. **Publishing Phase**
   - Post to each target language account
   - Handle failures with exponential backoff
   - Log all activities for monitoring

### Configuration Schema

```json
{
  "primary_account": {
    "username": "your_english_account",
    "api_keys": {
      "consumer_key": "...",
      "consumer_secret": "...",
      "access_token": "...",
      "access_token_secret": "..."
    }
  },
  "target_accounts": [
    {
      "language": "ja",
      "language_name": "Japanese",
      "username": "your_japanese_account",
      "api_keys": {
        "consumer_key": "...",
        "consumer_secret": "...",
        "access_token": "...",
        "access_token_secret": "..."
      }
    }
  ],
  "gemini_api": {
    "api_key": "...",
    "model": "gemini-1.5-flash",
    "translation_options": {
      "preserve_formatting": true,
      "maintain_tone": true,
      "cultural_adaptation": true,
      "max_output_tokens": 1000
    }
  },
  "monitoring": {
    "poll_interval_seconds": 300,
    "include_replies": false,
    "include_retweets": false
  }
}
```

## Implementation Phases

### Phase 1: Core Functionality (Single Language)
- Set up basic Twitter API integration
- Implement translation for one target language
- Basic posting functionality
- Simple error handling and logging

### Phase 2: Multi-Language Support
- Extend configuration for multiple languages
- Implement parallel translation processing
- Add language-specific formatting rules
- Enhanced error handling per account

### Phase 3: Advanced Features
- Tweet thread support
- Media handling (images, videos)
- Scheduled posting delays
- Analytics and monitoring dashboard
- Webhook integration for real-time processing

### Phase 4: Production Readiness
- Comprehensive error recovery
- Database storage for tweet history
- Advanced rate limiting management
- Health checks and monitoring
- Deployment automation

## Risk Considerations

### Twitter API Limitations
- Rate limits: 300 requests per 15-minute window
- Tweet length varies by language
- Account suspension risks for automated behavior

### Translation Quality
- Gemini AI provides superior context preservation
- Better handling of cultural nuances and idioms
- Natural hashtag and mention preservation
- URL and formatting preservation
- Potential for over-translation or verbosity (need concise prompting)

### Operational Risks
- API key exposure (Twitter + Google)
- Service downtime handling
- Gemini API rate limits and token costs
- Account security and 2FA handling

## Deployment Options

### Option 1: Cloud Functions (Serverless)
- **Pros**: Low cost, automatic scaling, minimal maintenance
- **Cons**: Cold start delays, execution time limits
- **Best for**: Low-frequency posting accounts

### Option 2: VPS/Cloud Instance
- **Pros**: Full control, persistent storage, custom scheduling
- **Cons**: Higher cost, requires server management
- **Best for**: High-frequency posting, multiple languages

### Option 3: Container Deployment
- **Pros**: Portable, scalable, easy CI/CD integration
- **Cons**: Container orchestration complexity
- **Best for**: Professional/enterprise use

## Security Considerations

1. **API Key Management**
   - Use environment variables or secure vaults
   - Separate keys for development/production
   - Regular key rotation schedule

2. **Access Control**
   - Principle of least privilege for API permissions
   - Secure storage of authentication tokens
   - Monitor for unusual API activity

3. **Data Handling**
   - No permanent storage of tweet content
   - Encrypted transmission of sensitive data
   - Compliance with data protection regulations

## Success Metrics

- **Reliability**: >99% successful translation and posting rate
- **Speed**: <5 minutes from source tweet to translated post
- **Quality**: Manual review shows >90% translation accuracy
- **Coverage**: Support for 5+ languages within 3 months

## Next Steps

1. Set up development environment
2. Obtain Twitter API access and keys
3. Choose and configure translation service
4. Implement Phase 1 core functionality
5. Test with single language pair
6. Expand to multiple languages
7. Deploy to production environment

## Estimated Timeline

- **Week 1-2**: Environment setup and API integration
- **Week 3-4**: Core translation and posting functionality
- **Week 5-6**: Multi-language support and testing
- **Week 7-8**: Production deployment and monitoring

## Budget Estimation

- Twitter API: Free (Basic) or $100/month (Premium)
- Google Gemini API: $0-5/month (generous free tier covers most usage)
- Hosting: $10-50/month depending on option chosen
- **Total Monthly Cost**: $10-155/month

### Gemini API Cost Breakdown
**For typical personal Twitter account (10-50 tweets/day)**:
- Using Gemini 1.5 Flash: ~200 tweets/month
- Free tier covers: 1,500 requests/day = 45,000 requests/month
- **Estimated Gemini cost: $0/month (free tier sufficient)**

**For active accounts (100+ tweets/day)**:
- Using Gemini 1.5 Flash: ~3K tweets/month
- May exceed free tier: $0.075 per 1M input tokens, $0.30 per 1M output tokens
- **Estimated Gemini cost: ~$1-5/month for heavy usage**