# =============================================================================
# ASYNC PERFORMANCE SETTINGS
# =============================================================================
# Configuration for async performance optimizations

from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class ConnectionPoolConfig:
    """HTTP connection pool configuration"""
    max_connections: int = 100
    max_connections_per_host: int = 30
    keepalive_timeout: int = 60
    connection_timeout: int = 10
    read_timeout: int = 30
    dns_cache_ttl: int = 300
    enable_cleanup_closed: bool = True

@dataclass  
class BatchProcessingConfig:
    """Batch processing configuration"""
    max_batch_size: int = 10
    batch_timeout_seconds: float = 5.0
    max_concurrent_batches: int = 3
    enable_intelligent_batching: bool = True

@dataclass
class CacheConfig:
    """Async cache configuration"""
    max_entries: int = 10000
    ttl_hours: int = 168  # 1 week
    save_interval_seconds: int = 300  # 5 minutes
    cleanup_interval_hours: int = 1
    enable_compression: bool = True
    cache_file: str = 'logs/async_translation_cache.json'

@dataclass
class PerformanceConfig:
    """Performance monitoring configuration"""
    enable_monitoring: bool = True
    monitoring_interval_seconds: int = 30
    max_metrics_history: int = 10000
    enable_system_monitoring: bool = True
    
    # Performance thresholds
    api_latency_warning_ms: float = 5000
    api_latency_error_ms: float = 10000
    memory_warning_mb: float = 500
    memory_error_mb: float = 1000
    error_rate_warning_percent: float = 5
    error_rate_error_percent: float = 10

@dataclass
class RateLimitingConfig:
    """Rate limiting configuration"""
    enable_intelligent_rate_limiting: bool = True
    min_post_interval_seconds: float = 5.0
    burst_capacity: int = 10
    refill_rate_per_second: float = 2.0
    enable_per_service_limiting: bool = True

@dataclass
class ConcurrencyConfig:
    """Concurrency configuration"""
    max_concurrent_translations: int = 10
    max_concurrent_posts: int = 5
    max_concurrent_api_calls: int = 15
    translation_timeout_seconds: float = 60.0
    posting_timeout_seconds: float = 30.0
    enable_request_deduplication: bool = True

class AsyncSettings:
    """Central async performance settings"""
    
    def __init__(self):
        self.connection_pool = ConnectionPoolConfig()
        self.batch_processing = BatchProcessingConfig()
        self.cache = CacheConfig()
        self.performance = PerformanceConfig()
        self.rate_limiting = RateLimitingConfig()
        self.concurrency = ConcurrencyConfig()
        
        # Feature flags
        self.enable_async_mode: bool = True
        self.enable_connection_pooling: bool = True
        self.enable_batch_processing: bool = True
        self.enable_performance_monitoring: bool = True
        self.enable_intelligent_caching: bool = True
        
        # Optimization modes
        self.optimization_mode: str = "balanced"  # "speed", "memory", "balanced"
        
        self._apply_optimization_mode()
    
    def _apply_optimization_mode(self):
        """Apply optimization mode settings"""
        if self.optimization_mode == "speed":
            # Optimize for maximum speed
            self.connection_pool.max_connections = 200
            self.connection_pool.max_connections_per_host = 50
            self.batch_processing.max_batch_size = 20
            self.concurrency.max_concurrent_translations = 20
            self.concurrency.max_concurrent_posts = 10
            self.cache.max_entries = 20000
            
        elif self.optimization_mode == "memory":
            # Optimize for memory usage
            self.connection_pool.max_connections = 50
            self.connection_pool.max_connections_per_host = 15
            self.batch_processing.max_batch_size = 5
            self.concurrency.max_concurrent_translations = 5
            self.concurrency.max_concurrent_posts = 2
            self.cache.max_entries = 5000
            self.performance.max_metrics_history = 5000
            
        # "balanced" mode uses defaults
    
    def get_aiohttp_connector_kwargs(self) -> Dict[str, Any]:
        """Get aiohttp connector configuration"""
        return {
            'limit': self.connection_pool.max_connections,
            'limit_per_host': self.connection_pool.max_connections_per_host,
            'ttl_dns_cache': self.connection_pool.dns_cache_ttl,
            'use_dns_cache': True,
            'keepalive_timeout': self.connection_pool.keepalive_timeout,
            'enable_cleanup_closed': self.connection_pool.enable_cleanup_closed
        }
    
    def get_aiohttp_timeout_config(self):
        """Get aiohttp timeout configuration"""
        import aiohttp
        return aiohttp.ClientTimeout(
            total=self.connection_pool.read_timeout,
            connect=self.connection_pool.connection_timeout
        )
    
    def update_from_dict(self, config_dict: Dict[str, Any]):
        """Update settings from dictionary"""
        for category, settings in config_dict.items():
            if hasattr(self, category):
                category_obj = getattr(self, category)
                for key, value in settings.items():
                    if hasattr(category_obj, key):
                        setattr(category_obj, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export settings to dictionary"""
        return {
            'connection_pool': self.connection_pool.__dict__,
            'batch_processing': self.batch_processing.__dict__,
            'cache': self.cache.__dict__,
            'performance': self.performance.__dict__,
            'rate_limiting': self.rate_limiting.__dict__,
            'concurrency': self.concurrency.__dict__,
            'enable_async_mode': self.enable_async_mode,
            'enable_connection_pooling': self.enable_connection_pooling,
            'enable_batch_processing': self.enable_batch_processing,
            'enable_performance_monitoring': self.enable_performance_monitoring,
            'enable_intelligent_caching': self.enable_intelligent_caching,
            'optimization_mode': self.optimization_mode
        }
    
    def print_settings_summary(self):
        """Print a summary of current settings"""
        print("\n" + "="*60)
        print("⚙️  ASYNC PERFORMANCE SETTINGS SUMMARY")
        print("="*60)
        
        print(f"🚀 Optimization Mode: {self.optimization_mode}")
        print(f"🔧 Async Mode: {'✅ Enabled' if self.enable_async_mode else '❌ Disabled'}")
        
        print(f"\n🌐 CONNECTION POOL:")
        print(f"   Max Connections: {self.connection_pool.max_connections}")
        print(f"   Max Per Host: {self.connection_pool.max_connections_per_host}")
        print(f"   Keepalive Timeout: {self.connection_pool.keepalive_timeout}s")
        
        print(f"\n📦 BATCH PROCESSING:")
        print(f"   Max Batch Size: {self.batch_processing.max_batch_size}")
        print(f"   Batch Timeout: {self.batch_processing.batch_timeout_seconds}s")
        print(f"   Intelligent Batching: {'✅' if self.batch_processing.enable_intelligent_batching else '❌'}")
        
        print(f"\n💾 CACHE:")
        print(f"   Max Entries: {self.cache.max_entries}")
        print(f"   TTL: {self.cache.ttl_hours} hours")
        print(f"   Save Interval: {self.cache.save_interval_seconds}s")
        
        print(f"\n🔄 CONCURRENCY:")
        print(f"   Max Concurrent Translations: {self.concurrency.max_concurrent_translations}")
        print(f"   Max Concurrent Posts: {self.concurrency.max_concurrent_posts}")
        print(f"   Translation Timeout: {self.concurrency.translation_timeout_seconds}s")
        
        print(f"\n📊 MONITORING:")
        print(f"   Enabled: {'✅' if self.performance.enable_monitoring else '❌'}")
        print(f"   Interval: {self.performance.monitoring_interval_seconds}s")
        print(f"   Max History: {self.performance.max_metrics_history}")
        
        print("="*60)

# Global async settings instance
async_settings = AsyncSettings()

# Preset configurations
PRESET_CONFIGS = {
    'development': {
        'optimization_mode': 'balanced',
        'performance': {
            'enable_monitoring': True,
            'monitoring_interval_seconds': 10
        },
        'cache': {
            'max_entries': 1000,
            'save_interval_seconds': 60
        }
    },
    'production': {
        'optimization_mode': 'speed',
        'performance': {
            'enable_monitoring': True,
            'monitoring_interval_seconds': 30
        },
        'cache': {
            'max_entries': 20000,
            'save_interval_seconds': 300
        }
    },
    'low_resource': {
        'optimization_mode': 'memory',
        'performance': {
            'enable_monitoring': False
        },
        'cache': {
            'max_entries': 500,
            'save_interval_seconds': 120
        },
        'concurrency': {
            'max_concurrent_translations': 3,
            'max_concurrent_posts': 1
        }
    }
}

def apply_preset_config(preset_name: str):
    """Apply a preset configuration"""
    if preset_name in PRESET_CONFIGS:
        async_settings.update_from_dict(PRESET_CONFIGS[preset_name])
        async_settings.optimization_mode = PRESET_CONFIGS[preset_name].get('optimization_mode', 'balanced')
        async_settings._apply_optimization_mode()
        print(f"✅ Applied preset configuration: {preset_name}")
    else:
        print(f"❌ Unknown preset configuration: {preset_name}")
        print(f"Available presets: {list(PRESET_CONFIGS.keys())}")
