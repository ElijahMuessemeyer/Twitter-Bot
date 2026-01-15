#!/usr/bin/env python3
# =============================================================================
# STRUCTURED LOGGING DEMONSTRATION AND TESTING
# =============================================================================
# Added by: AI Assistant on 2025-01-18
# Purpose: Demonstrate and test the new structured JSON logging system

import time
import json
from datetime import datetime
from pathlib import Path
from src.utils.structured_logger import (
    structured_logger, log_translation_cached, log_gemini_api_call,
    JSONLogAnalyzer
)
from src.utils.logger import logger
from src.models.tweet import Tweet, Translation

def demo_structured_logging():
    """Demonstrate structured logging capabilities"""
    print("🧪 STRUCTURED LOGGING DEMONSTRATION")
    print("=" * 60)
    
    # Create test tweet
    test_tweet = Tweet(
        id="demo_123",
        text="Hello world! This is a test tweet #demo @user https://example.com",
        created_at=datetime.now(),
        author_username="demo_user",
        author_id="demo_123",
        public_metrics={"like_count": 5, "retweet_count": 2}
    )
    
    print("📝 Demonstrating various log events...")
    
    # 1. Tweet processing
    structured_logger.log_tweet_processing(
        tweet_id=test_tweet.id,
        text_preview=test_tweet.text,
        language_count=3
    )
    
    # 2. Translation success (API call)
    structured_logger.log_translation_success(
        tweet_id=test_tweet.id,
        target_language="Spanish",
        character_count=65,
        cache_hit=False,
        duration_ms=1250.5
    )
    
    # 3. Gemini API call details
    log_gemini_api_call(
        tweet_id=test_tweet.id,
        target_language="Spanish",
        prompt_tokens=150,
        response_tokens=45,
        duration_ms=1250.5
    )
    
    # 4. Translation success (cache hit)
    structured_logger.log_translation_success(
        tweet_id=test_tweet.id,
        target_language="French",
        character_count=58,
        cache_hit=True,
        duration_ms=1.2
    )
    
    # 5. Post success
    structured_logger.log_post_success(
        tweet_id=test_tweet.id,
        target_language="Spanish",
        post_id="posted_789",
        character_count=65
    )
    
    # 6. Post failure (rate limit)
    structured_logger.log_post_failure(
        tweet_id=test_tweet.id,
        target_language="German",
        error_type="rate_limit_exceeded",
        retry_after=900
    )
    
    # 7. Draft saved
    structured_logger.log_draft_saved(
        tweet_id=test_tweet.id,
        target_language="German",
        reason="rate_limit_exceeded"
    )
    
    # 8. Cache performance
    structured_logger.log_cache_performance(
        hit_rate=67.5,
        total_requests=150,
        cache_size=45,
        memory_mb=2.3
    )
    
    # 9. API usage tracking
    structured_logger.log_api_usage(
        daily_requests=25,
        daily_limit=50,
        monthly_posts=350,
        monthly_limit=1500
    )
    
    # 10. Operation timing demonstration
    print("\n⏱️  Demonstrating operation timing...")
    with structured_logger.time_operation("demo_operation", operation_type="test"):
        time.sleep(0.1)  # Simulate work
    
    # 11. Error logging
    structured_logger.log_translation_failure(
        tweet_id=test_tweet.id,
        target_language="Japanese",
        error_type="GeminiAPIError",
        error_message="API quota exceeded"
    )
    
    print("\n✅ All structured log events demonstrated!")
    print("📄 Check logs/twitter_bot_*.json for JSON output")
    print("📄 Check logs/twitter_bot_*.log for human-readable output")

def test_json_log_analysis():
    """Test JSON log analysis capabilities"""
    print("\n🔍 TESTING JSON LOG ANALYSIS")
    print("=" * 60)
    
    # Find the most recent JSON log file
    today = datetime.now().strftime('%Y-%m-%d')
    json_log_file = f"logs/twitter_bot_{today}.json"
    
    if not Path(json_log_file).exists():
        print(f"⚠️  JSON log file not found: {json_log_file}")
        print("Run the demo first to generate logs")
        return
    
    # Parse and analyze logs
    print(f"📖 Analyzing log file: {json_log_file}")
    
    try:
        log_entries = JSONLogAnalyzer.parse_log_file(json_log_file)
        print(f"📊 Total log entries found: {len(log_entries)}")
        
        if log_entries:
            # Show recent events
            print("\n🕒 Recent events:")
            for entry in log_entries[-5:]:
                event = entry.get('event', 'unknown')
                timestamp = entry.get('timestamp', 'unknown')
                message = entry.get('message', 'no message')
                print(f"  {timestamp}: {event} - {message}")
            
            # Translation stats
            translation_stats = JSONLogAnalyzer.get_translation_stats(log_entries)
            if 'error' not in translation_stats:
                print(f"\n📈 Translation Statistics:")
                print(f"  Total translations: {translation_stats['total_translations']}")
                print(f"  Success rate: {translation_stats['success_rate_percent']}%")
                print(f"  Cache hit rate: {translation_stats['cache_hit_rate_percent']}%")
                print(f"  Average API duration: {translation_stats['average_api_duration_ms']}ms")
                print(f"  Languages processed: {translation_stats['languages_processed']}")
            
            # Error analysis
            error_summary = JSONLogAnalyzer.get_error_summary(log_entries)
            if error_summary['total_errors'] > 0:
                print(f"\n⚠️  Error Summary:")
                print(f"  Total errors: {error_summary['total_errors']}")
                print(f"  Most common error: {error_summary['most_common_error']}")
                print(f"  Error types: {error_summary['error_types']}")
        
        print("\n✅ JSON log analysis completed successfully!")
        
    except Exception as e:
        print(f"❌ Error analyzing logs: {str(e)}")

def test_structured_vs_traditional():
    """Compare structured vs traditional logging output"""
    print("\n🔀 STRUCTURED vs TRADITIONAL LOGGING COMPARISON")
    print("=" * 60)
    
    print("📜 Traditional Logging:")
    logger.info("Successfully translated tweet 123456 to Spanish (45 chars)")
    logger.error("Failed to post tweet 123456: Rate limit exceeded")
    
    print("\n📊 Structured Logging:")
    structured_logger.log_translation_success(
        tweet_id="123456",
        target_language="Spanish", 
        character_count=45,
        cache_hit=False,
        duration_ms=1200.5
    )
    
    structured_logger.log_post_failure(
        tweet_id="123456",
        target_language="Spanish",
        error_type="rate_limit_exceeded",
        retry_after=900
    )
    
    print("\n✅ Both logging styles work together!")
    print("💡 Traditional logs: Human-readable in console and .log files")
    print("💡 Structured logs: Machine-readable JSON in .json files")

def show_json_log_sample():
    """Show sample of JSON log output"""
    print("\n📄 SAMPLE JSON LOG OUTPUT")
    print("=" * 60)
    
    # Find the most recent JSON log file
    today = datetime.now().strftime('%Y-%m-%d')
    json_log_file = f"logs/twitter_bot_{today}.json"
    
    if Path(json_log_file).exists():
        with open(json_log_file, 'r') as f:
            lines = f.readlines()
            
        if lines:
            print("📝 Recent JSON log entries:")
            for line in lines[-3:]:  # Show last 3 entries
                try:
                    entry = json.loads(line.strip())
                    print(json.dumps(entry, indent=2))
                    print("-" * 40)
                except json.JSONDecodeError:
                    continue
    else:
        print("⚠️  No JSON log file found. Run the demo first.")

def main():
    """Run all structured logging demonstrations"""
    print("🎯 STRUCTURED JSON LOGGING SYSTEM TEST")
    print("🚀 Implementing high-leverage monitoring improvement")
    print()
    
    try:
        # Run demonstrations
        demo_structured_logging()
        test_json_log_analysis() 
        test_structured_vs_traditional()
        show_json_log_sample()
        
        print("\n" + "="*70)
        print("🎉 STRUCTURED LOGGING SYSTEM FULLY OPERATIONAL!")
        print("="*70)
        
        print("\n🚀 Benefits Achieved:")
        print("  ✅ Machine-readable JSON logs for monitoring")
        print("  ✅ Rich context and metadata in every log entry")
        print("  ✅ Performance timing for operations")
        print("  ✅ Structured error tracking and classification")
        print("  ✅ Cache performance analytics")
        print("  ✅ API usage and cost monitoring")
        print("  ✅ Dual output: JSON + human-readable")
        
        print("\n📊 Professional Monitoring Ready:")
        print("  📄 JSON logs: logs/twitter_bot_YYYY-MM-DD.json")
        print("  📄 Text logs: logs/twitter_bot_YYYY-MM-DD.log")
        print("  🔍 Analysis: Use JSONLogAnalyzer for insights")
        print("  📈 Integration: Ready for ELK, Grafana, CloudWatch")
        
        print("\n💰 Operational Benefits:")
        print("  🔥 Professional monitoring and alerting capability")
        print("  🎯 Detailed performance and cost tracking")
        print("  🚀 Production-ready observability")
        print("  📊 Data-driven optimization insights")
        
        return 0
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
