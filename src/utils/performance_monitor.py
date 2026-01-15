# =============================================================================
# PERFORMANCE MONITORING & METRICS
# =============================================================================
# Comprehensive performance monitoring system for the async Twitter bot

import asyncio
import time
import psutil
import threading
from typing import Dict, List, Optional, Any
from contextlib import contextmanager, asynccontextmanager
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
from pathlib import Path
from ..utils.logger import logger

@dataclass
class ApiCallMetric:
    """Represents a single API call metric"""
    timestamp: float
    service: str
    operation: str
    duration_ms: float
    success: bool
    response_size: int = 0
    error: Optional[str] = None

@dataclass
class PerformanceStats:
    """Aggregated performance statistics"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    avg_duration_ms: float = 0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0
    total_duration_ms: float = 0
    throughput_per_second: float = 0
    error_rate_percent: float = 0

class PerformanceMonitor:
    """
    Comprehensive performance monitoring system with:
    - API latency tracking
    - Memory usage monitoring  
    - Throughput measurement
    - Error rate tracking
    - Real-time metrics dashboard
    """
    
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self.metrics: deque[ApiCallMetric] = deque(maxlen=max_history)
        self.service_stats: Dict[str, PerformanceStats] = defaultdict(PerformanceStats)
        
        # System resource tracking
        self.process = psutil.Process()
        self.memory_usage_history = deque(maxlen=1000)
        self.cpu_usage_history = deque(maxlen=1000)
        
        # Operation tracking for context managers
        self.active_operations: Dict[str, float] = {}
        
        # Real-time metrics
        self._start_time = time.time()
        self._metrics_lock = threading.Lock()
        
        # Periodic monitoring
        self._monitoring_task: Optional[asyncio.Task] = None
        self._monitoring_interval = 30  # seconds
        
        # Performance thresholds
        self.thresholds = {
            'api_latency_warning_ms': 5000,
            'api_latency_error_ms': 10000,
            'memory_warning_mb': 500,
            'memory_error_mb': 1000,
            'error_rate_warning_percent': 5,
            'error_rate_error_percent': 10
        }
        
        # Metrics file
        self.metrics_file = Path('logs/performance_metrics.json')
        
        logger.info("🔧 Performance monitor initialized")
    
    def start_monitoring(self):
        """Start continuous performance monitoring"""
        if self._monitoring_task is None:
            self._monitoring_task = asyncio.create_task(self._monitor_system_resources())
            logger.info("📊 Started continuous performance monitoring")
    
    def stop_monitoring(self):
        """Stop continuous performance monitoring"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            self._monitoring_task = None
            logger.info("🛑 Stopped performance monitoring")
    
    async def _monitor_system_resources(self):
        """Monitor system resources continuously"""
        while True:
            try:
                await asyncio.sleep(self._monitoring_interval)
                
                # Memory usage
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                self.memory_usage_history.append(memory_mb)
                
                # CPU usage
                cpu_percent = self.process.cpu_percent()
                self.cpu_usage_history.append(cpu_percent)
                
                # Check thresholds
                await self._check_performance_thresholds()
                
                # Log periodic summary
                await self._log_periodic_summary()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error in resource monitoring: {str(e)}")
    
    async def _check_performance_thresholds(self):
        """Check if any performance thresholds are exceeded"""
        current_memory = self.memory_usage_history[-1] if self.memory_usage_history else 0
        
        # Memory warnings
        if current_memory > self.thresholds['memory_error_mb']:
            logger.error(f"🚨 CRITICAL: Memory usage {current_memory:.1f}MB exceeds error threshold")
        elif current_memory > self.thresholds['memory_warning_mb']:
            logger.warning(f"⚠️  Memory usage {current_memory:.1f}MB exceeds warning threshold")
        
        # API latency warnings
        recent_metrics = list(self.metrics)[-100:]  # Last 100 calls
        if recent_metrics:
            avg_latency = sum(m.duration_ms for m in recent_metrics) / len(recent_metrics)
            
            if avg_latency > self.thresholds['api_latency_error_ms']:
                logger.error(f"🚨 CRITICAL: Average API latency {avg_latency:.1f}ms exceeds error threshold")
            elif avg_latency > self.thresholds['api_latency_warning_ms']:
                logger.warning(f"⚠️  Average API latency {avg_latency:.1f}ms exceeds warning threshold")
    
    async def _log_periodic_summary(self):
        """Log periodic performance summary"""
        stats = self.get_overall_stats()
        memory_mb = self.memory_usage_history[-1] if self.memory_usage_history else 0
        cpu_percent = self.cpu_usage_history[-1] if self.cpu_usage_history else 0
        
        logger.info(
            f"📊 Performance Summary - "
            f"API Calls: {stats.total_calls} "
            f"(Success: {stats.successful_calls}, Errors: {stats.failed_calls}) | "
            f"Avg Latency: {stats.avg_duration_ms:.1f}ms | "
            f"Memory: {memory_mb:.1f}MB | "
            f"CPU: {cpu_percent:.1f}%"
        )
    
    def record_api_call(
        self, 
        service: str, 
        operation: str, 
        duration_ms: float, 
        success: bool, 
        response_size: int = 0, 
        error: Optional[str] = None
    ):
        """Record an API call metric"""
        with self._metrics_lock:
            metric = ApiCallMetric(
                timestamp=time.time(),
                service=service,
                operation=operation,
                duration_ms=duration_ms,
                success=success,
                response_size=response_size,
                error=error
            )
            
            self.metrics.append(metric)
            self._update_service_stats(service, metric)
    
    def _update_service_stats(self, service: str, metric: ApiCallMetric):
        """Update aggregated statistics for a service"""
        stats = self.service_stats[service]
        
        stats.total_calls += 1
        stats.total_duration_ms += metric.duration_ms
        
        if metric.success:
            stats.successful_calls += 1
        else:
            stats.failed_calls += 1
        
        # Update min/max
        stats.min_duration_ms = min(stats.min_duration_ms, metric.duration_ms)
        stats.max_duration_ms = max(stats.max_duration_ms, metric.duration_ms)
        
        # Update averages
        stats.avg_duration_ms = stats.total_duration_ms / stats.total_calls
        stats.error_rate_percent = (stats.failed_calls / stats.total_calls) * 100
        
        # Calculate throughput (calls per second over last minute)
        recent_calls = [
            m for m in self.metrics 
            if m.service == service and m.timestamp > time.time() - 60
        ]
        stats.throughput_per_second = len(recent_calls) / 60
    
    @contextmanager
    def track_operation(self, operation_name: str):
        """Context manager to track operation duration"""
        start_time = time.time()
        self.active_operations[operation_name] = start_time
        
        try:
            yield
        finally:
            duration_ms = (time.time() - start_time) * 1000
            self.active_operations.pop(operation_name, None)
            
            # Record as generic operation
            self.record_api_call(
                service="system",
                operation=operation_name,
                duration_ms=duration_ms,
                success=True
            )
    
    @asynccontextmanager
    async def track_async_operation(self, operation_name: str):
        """Async context manager to track operation duration"""
        start_time = asyncio.get_event_loop().time()
        self.active_operations[operation_name] = start_time
        
        try:
            yield
        finally:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            self.active_operations.pop(operation_name, None)
            
            # Record as generic operation
            self.record_api_call(
                service="system",
                operation=operation_name,
                duration_ms=duration_ms,
                success=True
            )
    
    def get_service_stats(self, service: str) -> PerformanceStats:
        """Get performance statistics for a specific service"""
        return self.service_stats.get(service, PerformanceStats())
    
    def get_overall_stats(self) -> PerformanceStats:
        """Get overall performance statistics"""
        if not self.metrics:
            return PerformanceStats()
        
        total_calls = len(self.metrics)
        successful_calls = sum(1 for m in self.metrics if m.success)
        failed_calls = total_calls - successful_calls
        
        durations = [m.duration_ms for m in self.metrics]
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        total_duration = sum(durations)
        
        # Calculate throughput over last minute
        recent_calls = [m for m in self.metrics if m.timestamp > time.time() - 60]
        throughput = len(recent_calls) / 60
        
        error_rate = (failed_calls / total_calls) * 100
        
        return PerformanceStats(
            total_calls=total_calls,
            successful_calls=successful_calls,
            failed_calls=failed_calls,
            avg_duration_ms=avg_duration,
            min_duration_ms=min_duration,
            max_duration_ms=max_duration,
            total_duration_ms=total_duration,
            throughput_per_second=throughput,
            error_rate_percent=error_rate
        )
    
    def get_memory_stats(self) -> dict:
        """Get memory usage statistics"""
        if not self.memory_usage_history:
            return {
                'current_mb': 0,
                'avg_mb': 0,
                'max_mb': 0,
                'min_mb': 0
            }
        
        current = self.memory_usage_history[-1]
        avg = sum(self.memory_usage_history) / len(self.memory_usage_history)
        max_mem = max(self.memory_usage_history)
        min_mem = min(self.memory_usage_history)
        
        return {
            'current_mb': current,
            'avg_mb': avg,
            'max_mb': max_mem,
            'min_mb': min_mem
        }
    
    def get_cpu_stats(self) -> dict:
        """Get CPU usage statistics"""
        if not self.cpu_usage_history:
            return {
                'current_percent': 0,
                'avg_percent': 0,
                'max_percent': 0,
                'min_percent': 0
            }
        
        current = self.cpu_usage_history[-1]
        avg = sum(self.cpu_usage_history) / len(self.cpu_usage_history)
        max_cpu = max(self.cpu_usage_history)
        min_cpu = min(self.cpu_usage_history)
        
        return {
            'current_percent': current,
            'avg_percent': avg,
            'max_percent': max_cpu,
            'min_percent': min_cpu
        }
    
    def get_detailed_metrics(self) -> dict:
        """Get comprehensive performance metrics"""
        uptime_seconds = time.time() - self._start_time
        
        return {
            'uptime_seconds': uptime_seconds,
            'overall_stats': self.get_overall_stats().__dict__,
            'service_stats': {
                service: stats.__dict__ 
                for service, stats in self.service_stats.items()
            },
            'memory_stats': self.get_memory_stats(),
            'cpu_stats': self.get_cpu_stats(),
            'active_operations': len(self.active_operations),
            'total_metrics_recorded': len(self.metrics),
            'thresholds': self.thresholds
        }
    
    def print_dashboard(self):
        """Print a formatted performance dashboard"""
        print("\n" + "="*80)
        print("🔧 TWITTER BOT PERFORMANCE DASHBOARD")
        print("="*80)
        
        # Overall stats
        overall = self.get_overall_stats()
        print(f"📊 OVERALL PERFORMANCE")
        print(f"   Total API Calls: {overall.total_calls}")
        print(f"   Success Rate: {(overall.successful_calls/max(overall.total_calls,1)*100):.1f}%")
        print(f"   Error Rate: {overall.error_rate_percent:.1f}%")
        print(f"   Average Latency: {overall.avg_duration_ms:.1f}ms")
        print(f"   Throughput: {overall.throughput_per_second:.2f} calls/sec")
        
        # Service breakdown
        print(f"\n📋 SERVICE BREAKDOWN")
        for service, stats in self.service_stats.items():
            print(f"   {service.upper()}: {stats.total_calls} calls, "
                  f"{stats.avg_duration_ms:.1f}ms avg, "
                  f"{stats.error_rate_percent:.1f}% errors")
        
        # System resources
        memory = self.get_memory_stats()
        cpu = self.get_cpu_stats()
        print(f"\n💾 SYSTEM RESOURCES")
        print(f"   Memory: {memory['current_mb']:.1f}MB "
              f"(avg: {memory['avg_mb']:.1f}MB, max: {memory['max_mb']:.1f}MB)")
        print(f"   CPU: {cpu['current_percent']:.1f}% "
              f"(avg: {cpu['avg_percent']:.1f}%, max: {cpu['max_percent']:.1f}%)")
        
        print("="*80)
    
    async def save_metrics(self):
        """Save metrics to file for persistence"""
        try:
            metrics_data = {
                'timestamp': datetime.now().isoformat(),
                'detailed_metrics': self.get_detailed_metrics(),
                'recent_api_calls': [
                    {
                        'timestamp': m.timestamp,
                        'service': m.service,
                        'operation': m.operation,
                        'duration_ms': m.duration_ms,
                        'success': m.success,
                        'response_size': m.response_size,
                        'error': m.error
                    }
                    for m in list(self.metrics)[-1000:]  # Last 1000 calls
                ]
            }
            
            # Ensure logs directory exists
            Path('logs').mkdir(exist_ok=True)
            
            import aiofiles
            async with aiofiles.open(self.metrics_file, 'w') as f:
                await f.write(json.dumps(metrics_data, indent=2))
            
            logger.info(f"💾 Performance metrics saved to {self.metrics_file}")
            
        except Exception as e:
            logger.error(f"❌ Error saving metrics: {str(e)}")
    
    async def load_metrics(self):
        """Load metrics from file"""
        try:
            if not self.metrics_file.exists():
                return
            
            import aiofiles
            async with aiofiles.open(self.metrics_file, 'r') as f:
                content = await f.read()
                data = json.loads(content)
            
            # Restore recent API calls
            for call_data in data.get('recent_api_calls', []):
                metric = ApiCallMetric(
                    timestamp=call_data['timestamp'],
                    service=call_data['service'],
                    operation=call_data['operation'],
                    duration_ms=call_data['duration_ms'],
                    success=call_data['success'],
                    response_size=call_data.get('response_size', 0),
                    error=call_data.get('error')
                )
                self.metrics.append(metric)
                self._update_service_stats(metric.service, metric)
            
            logger.info(f"📂 Performance metrics loaded from {self.metrics_file}")
            
        except Exception as e:
            logger.error(f"❌ Error loading metrics: {str(e)}")
    
    def get_benchmarks(self) -> dict:
        """Get performance benchmarks for comparison"""
        overall = self.get_overall_stats()
        
        # Define performance tiers
        def get_performance_tier(metric_value: float, thresholds: List[float]) -> str:
            if metric_value <= thresholds[0]:
                return "Excellent"
            elif metric_value <= thresholds[1]:
                return "Good"
            elif metric_value <= thresholds[2]:
                return "Fair"
            else:
                return "Poor"
        
        return {
            'api_latency_tier': get_performance_tier(
                overall.avg_duration_ms, [1000, 2000, 5000]
            ),
            'error_rate_tier': get_performance_tier(
                overall.error_rate_percent, [1, 5, 10]
            ),
            'throughput_tier': get_performance_tier(
                -overall.throughput_per_second, [-10, -5, -1]  # Negative for "higher is better"
            ),
            'memory_tier': get_performance_tier(
                self.get_memory_stats()['current_mb'], [100, 250, 500]
            )
        }

# Global performance monitor instance
performance_monitor = PerformanceMonitor()
