# =============================================================================
# CACHE MONITORING AND REPORTING
# =============================================================================
# Added by: AI Assistant on 2025-01-18
# Purpose: Monitor cache performance and provide detailed reporting

import json
import time
from datetime import datetime
from typing import Dict, Any
from ..utils.logger import logger
from ..utils.structured_logger import structured_logger
from ..services.gemini_translator import gemini_translator

class CacheMonitor:
    """Monitor and report on translation cache performance"""
    
    def __init__(self):
        self.start_time = time.time()
        self.last_report_time = time.time()
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate detailed cache performance report"""
        cache_info = gemini_translator.get_cache_metrics()
        current_time = time.time()
        
        metrics = cache_info.get('metrics', {})
        config = cache_info.get('config', {})
        
        # Calculate rates
        uptime_hours = (current_time - self.start_time) / 3600
        total_requests = metrics.get('hits', 0) + metrics.get('misses', 0)
        requests_per_hour = total_requests / uptime_hours if uptime_hours > 0 else 0
        
        return {
            'performance': {
                'hit_rate_percent': round(metrics.get('hit_rate', 0), 2),
                'total_requests': total_requests,
                'cache_hits': metrics.get('hits', 0),
                'cache_misses': metrics.get('misses', 0),
                'evictions': metrics.get('evictions', 0),
                'requests_per_hour': round(requests_per_hour, 2)
            },
            'cache_status': {
                'current_size': metrics.get('size', 0),
                'max_size': config.get('max_size', 0),
                'memory_usage_mb': round(metrics.get('memory_usage_mb', 0), 2),
                'fill_percentage': round(
                    (metrics.get('size', 0) / config.get('max_size', 1)) * 100, 1
                )
            },
            'configuration': {
                'ttl_hours': config.get('ttl_hours', 0),
                'cleanup_interval_minutes': config.get('cleanup_interval_minutes', 0)
            },
            'top_entries': cache_info.get('top_entries', []),
            'system': {
                'uptime_hours': round(uptime_hours, 2),
                'last_report': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        }
    
    def print_performance_summary(self):
        """Print a human-readable cache performance summary"""
        try:
            report = self.get_performance_report()
            
            print("\n" + "="*60)
            print("🔄 TRANSLATION CACHE PERFORMANCE REPORT")
            print("="*60)
            
            # Performance metrics
            perf = report['performance']
            print(f"📊 Cache Hit Rate: {perf['hit_rate_percent']}%")
            print(f"📈 Total Requests: {perf['total_requests']}")
            print(f"✅ Cache Hits: {perf['cache_hits']}")
            print(f"❌ Cache Misses: {perf['cache_misses']}")
            print(f"🗑️  Evictions: {perf['evictions']}")
            print(f"⚡ Requests/Hour: {perf['requests_per_hour']}")
            
            # Cache status
            status = report['cache_status']
            print(f"\n💾 Cache Usage: {status['current_size']}/{status['max_size']} ({status['fill_percentage']}%)")
            print(f"🧠 Memory Usage: {status['memory_usage_mb']} MB")
            
            # Configuration
            config = report['configuration']
            print(f"\n⚙️  TTL: {config['ttl_hours']} hours")
            print(f"🧹 Cleanup Interval: {config['cleanup_interval_minutes']} minutes")
            
            # Top entries
            top_entries = report.get('top_entries', [])
            if top_entries:
                print(f"\n🔥 Most Accessed Translations:")
                for i, entry in enumerate(top_entries[:3], 1):
                    print(f"   {i}. {entry['target_language']} ({entry['access_count']} hits, {entry['age_hours']:.1f}h old)")
            
            # System info
            system = report['system']
            print(f"\n🕐 Uptime: {system['uptime_hours']} hours")
            print(f"📅 Report Time: {system['last_report']}")
            
            # Performance assessment
            hit_rate = perf['hit_rate_percent']
            if hit_rate >= 70:
                print(f"\n🎉 EXCELLENT: Cache is performing very well!")
            elif hit_rate >= 50:
                print(f"\n✅ GOOD: Cache is providing solid performance benefits.")
            elif hit_rate >= 30:
                print(f"\n⚠️  FAIR: Cache is helping but could be better.")
            else:
                print(f"\n❌ POOR: Cache needs attention or more time to warm up.")
            
            print("="*60 + "\n")
            
        except Exception as e:
            logger.error(f"❌ Error generating cache report: {str(e)}")
            print("❌ Unable to generate cache performance report")
    
    def log_cache_stats_periodically(self, interval_minutes: int = 60):
        """Log cache statistics periodically"""
        current_time = time.time()
        if current_time - self.last_report_time >= (interval_minutes * 60):
            try:
                report = self.get_performance_report()
                perf = report['performance']
                status = report['cache_status']
                
                # Log both traditional and structured metrics
                logger.info(
                    f"📊 Cache Stats: {perf['hit_rate_percent']}% hit rate, "
                    f"{status['current_size']}/{status['max_size']} entries, "
                    f"{status['memory_usage_mb']:.1f}MB memory"
                )
                
                # Structured logging for machine processing
                structured_logger.log_cache_performance(
                    hit_rate=perf['hit_rate_percent'],
                    total_requests=perf['total_requests'],
                    cache_size=status['current_size'],
                    memory_mb=status['memory_usage_mb']
                )
                
                self.last_report_time = current_time
            except Exception as e:
                logger.error(f"❌ Error logging cache stats: {str(e)}")
    
    def save_performance_report(self, filename: str = None):
        """Save detailed performance report to JSON file"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"cache_report_{timestamp}.json"
        
        try:
            report = self.get_performance_report()
            
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2)
            
            logger.info(f"📁 Cache performance report saved to: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"❌ Error saving cache report: {str(e)}")
            return None

# Global cache monitor instance
cache_monitor = CacheMonitor()
