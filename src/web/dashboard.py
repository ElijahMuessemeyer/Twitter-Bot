# =============================================================================
# TWITTER BOT WEB DASHBOARD
# =============================================================================
# A lightweight Flask-based health monitoring dashboard for the Twitter bot
# Features:
# - Real-time health status endpoints
# - Performance metrics and monitoring
# - Configuration display (with masked secrets)
# - Circuit breaker status
# - Translation cache performance
# - Draft management status
# =============================================================================

import os
import time
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from flask import Flask, jsonify, render_template_string, request

from ..utils.structured_logger import structured_logger
from ..utils.cache_monitor import cache_monitor
from ..utils.circuit_breaker import circuit_breaker_manager
from ..services.gemini_translator import gemini_translator
from ..config.settings import settings
from draft_manager import draft_manager


class TwitterBotDashboard:
    """Lightweight web dashboard for monitoring Twitter bot health and performance"""
    
    def __init__(self, port: int = 8080, debug: bool = False):
        self.port = port
        self.debug = debug
        self.app = Flask(__name__)
        self.start_time = time.time()
        self._setup_routes()
        
        # Dashboard state
        self.last_successful_run = None
        self.error_count_24h = 0
        self.total_translations_24h = 0
        
    def _setup_routes(self):
        """Setup Flask routes for API endpoints"""
        
        @self.app.route('/health')
        def health_endpoint():
            """System health status endpoint"""
            return jsonify(self._get_health_status())
            
        @self.app.route('/metrics')
        def metrics_endpoint():
            """Performance metrics endpoint"""
            return jsonify(self._get_performance_metrics())
            
        @self.app.route('/config')
        def config_endpoint():
            """Configuration status endpoint (secrets masked)"""
            return jsonify(self._get_configuration_status())
            
        @self.app.route('/drafts')
        def drafts_endpoint():
            """Draft management status endpoint"""
            return jsonify(self._get_drafts_status())
            
        @self.app.route('/services')
        def services_endpoint():
            """Individual service status endpoint"""
            return jsonify(self._get_services_status())
            
        @self.app.route('/')
        def dashboard_ui():
            """Simple HTML dashboard interface (optional)"""
            if not os.getenv('ENABLE_DASHBOARD_UI', 'false').lower() == 'true':
                return jsonify({"error": "Dashboard UI is disabled. Set ENABLE_DASHBOARD_UI=true to enable."})
            
            return render_template_string(self._get_dashboard_html())
            
        @self.app.route('/api/status')
        def api_status():
            """Combined status for dashboard UI"""
            return jsonify({
                'health': self._get_health_status(),
                'metrics': self._get_performance_metrics(),
                'services': self._get_services_status(),
                'drafts': self._get_drafts_status()
            })
    
    def _get_health_status(self) -> Dict[str, Any]:
        """Get overall system health status"""
        try:
            circuit_breakers = circuit_breaker_manager.get_all_health_status()
            healthy_breakers = sum(1 for cb in circuit_breakers if cb['healthy'])
            total_breakers = len(circuit_breakers)
            
            # Calculate uptime
            uptime_seconds = time.time() - self.start_time
            uptime_hours = uptime_seconds / 3600
            
            # Determine overall health
            overall_healthy = (
                total_breakers == 0 or  # No circuit breakers configured yet
                (healthy_breakers / total_breakers) >= 0.8  # 80% of services healthy
            )
            
            return {
                'status': 'healthy' if overall_healthy else 'degraded',
                'uptime_hours': round(uptime_hours, 2),
                'uptime_formatted': self._format_duration(uptime_seconds),
                'last_check': datetime.utcnow().isoformat() + 'Z',
                'services_healthy': f"{healthy_breakers}/{total_breakers}",
                'last_successful_run': self.last_successful_run.isoformat() + 'Z' if self.last_successful_run else None,
                'error_count_24h': self.error_count_24h,
                'translations_24h': self.total_translations_24h
            }
        except Exception as e:
            structured_logger.error("Error getting health status", error=str(e))
            return {
                'status': 'error',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat() + 'Z'
            }
    
    def _get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics and statistics"""
        try:
            # Cache performance
            cache_report = cache_monitor.get_performance_report()
            
            # API usage estimation (would need to be tracked in the main bot)
            daily_requests = cache_report.get('performance', {}).get('cache_misses', 0)
            
            return {
                'cache_performance': cache_report.get('performance', {}),
                'cache_status': cache_report.get('cache_status', {}),
                'api_usage': {
                    'daily_requests_estimated': daily_requests,
                    'daily_limit': 10000,  # Example limit
                    'monthly_posts_estimated': daily_requests * 30,
                    'monthly_limit': 300000  # Example limit
                },
                'system': cache_report.get('system', {}),
                'top_translations': cache_report.get('top_entries', [])
            }
        except Exception as e:
            structured_logger.error("Error getting performance metrics", error=str(e))
            return {'error': str(e)}
    
    def _get_configuration_status(self) -> Dict[str, Any]:
        """Get configuration status with secrets masked"""
        try:
            config_status = {
                'twitter_api_configured': bool(os.getenv('TWITTER_CONSUMER_KEY')),
                'gemini_api_configured': bool(os.getenv('GEMINI_API_KEY')),
                'target_languages_count': len(settings.target_languages),
                'target_languages': list(settings.target_languages.keys()),
                'cache_enabled': True,  # Assumption based on cache monitor existence
                'structured_logging_enabled': True,
                'circuit_breaker_enabled': True,
                'environment_variables': {
                    'ENABLE_DASHBOARD': os.getenv('ENABLE_DASHBOARD', 'false'),
                    'ENABLE_DASHBOARD_UI': os.getenv('ENABLE_DASHBOARD_UI', 'false'),
                    'DASHBOARD_PORT': os.getenv('DASHBOARD_PORT', '8080'),
                    'TWITTER_CONSUMER_KEY': '***CONFIGURED***' if os.getenv('TWITTER_CONSUMER_KEY') else 'NOT_SET',
                    'GEMINI_API_KEY': '***CONFIGURED***' if os.getenv('GEMINI_API_KEY') else 'NOT_SET'
                }
            }
            
            return {
                'status': 'configured',
                'configuration': config_status,
                'last_check': datetime.utcnow().isoformat() + 'Z'
            }
        except Exception as e:
            structured_logger.error("Error getting configuration status", error=str(e))
            return {
                'status': 'error',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat() + 'Z'
            }
    
    def _get_drafts_status(self) -> Dict[str, Any]:
        """Get draft management status"""
        try:
            pending_count = draft_manager.get_draft_count()
            drafts = draft_manager.get_pending_drafts()
            
            # Get draft age information
            if drafts:
                oldest_draft = min(drafts, key=lambda d: d['created_at'])
                newest_draft = max(drafts, key=lambda d: d['created_at'])
                
                oldest_age = datetime.now() - datetime.fromisoformat(oldest_draft['created_at'])
                newest_age = datetime.now() - datetime.fromisoformat(newest_draft['created_at'])
            else:
                oldest_age = newest_age = None
            
            return {
                'pending_drafts_count': pending_count,
                'oldest_draft_age_hours': oldest_age.total_seconds() / 3600 if oldest_age else None,
                'newest_draft_age_hours': newest_age.total_seconds() / 3600 if newest_age else None,
                'draft_languages': list(set(d['target_language'] for d in drafts)) if drafts else [],
                'status': 'ok' if pending_count < 100 else 'warning' if pending_count < 500 else 'critical',
                'last_check': datetime.utcnow().isoformat() + 'Z'
            }
        except Exception as e:
            structured_logger.error("Error getting drafts status", error=str(e))
            return {
                'status': 'error',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat() + 'Z'
            }
    
    def _get_services_status(self) -> Dict[str, Any]:
        """Get individual service status from circuit breakers"""
        try:
            circuit_breakers = circuit_breaker_manager.get_all_health_status()
            
            services = {}
            for cb in circuit_breakers:
                services[cb['name']] = {
                    'status': 'healthy' if cb['healthy'] else 'unhealthy',
                    'state': cb['state'],
                    'failure_rate': cb['failure_rate'],
                    'recent_requests': cb['recent_requests'],
                    'recent_failures': cb['recent_failures'],
                    'last_failure_time': cb['last_failure_time'],
                    'time_since_last_failure': cb['time_since_last_failure']
                }
            
            return {
                'services': services,
                'total_services': len(services),
                'healthy_services': sum(1 for s in services.values() if s['status'] == 'healthy'),
                'last_check': datetime.utcnow().isoformat() + 'Z'
            }
        except Exception as e:
            structured_logger.error("Error getting services status", error=str(e))
            return {
                'services': {},
                'error': str(e),
                'last_check': datetime.utcnow().isoformat() + 'Z'
            }
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
        else:
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            return f"{days}d {hours}h"
    
    def update_stats(self, successful_run: bool = True, error_occurred: bool = False, translations_count: int = 0):
        """Update dashboard statistics (to be called from main bot)"""
        if successful_run:
            self.last_successful_run = datetime.utcnow()
        
        if error_occurred:
            self.error_count_24h += 1
        
        self.total_translations_24h += translations_count
    
    def _get_dashboard_html(self) -> str:
        """Simple HTML dashboard template"""
        return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Twitter Bot Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5; padding: 20px; line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header h1 { color: #333; margin-bottom: 10px; }
        .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card h3 { color: #333; margin-bottom: 15px; border-bottom: 2px solid #eee; padding-bottom: 10px; }
        .status-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
        .status-healthy { background: #28a745; }
        .status-warning { background: #ffc107; }
        .status-error { background: #dc3545; }
        .metric { margin: 8px 0; }
        .metric-label { font-weight: 600; color: #666; }
        .metric-value { color: #333; }
        .refresh-info { text-align: center; margin: 20px 0; color: #666; font-size: 14px; }
        .timestamp { font-size: 12px; color: #999; }
        @media (max-width: 768px) {
            .status-grid { grid-template-columns: 1fr; }
            body { padding: 10px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Twitter Translation Bot Dashboard</h1>
            <p>Real-time monitoring and health status</p>
            <div class="timestamp">Last updated: <span id="lastUpdated">Loading...</span></div>
        </div>
        
        <div class="status-grid">
            <div class="card">
                <h3>🏥 System Health</h3>
                <div id="healthStatus">Loading...</div>
            </div>
            
            <div class="card">
                <h3>📊 Performance Metrics</h3>
                <div id="metricsStatus">Loading...</div>
            </div>
            
            <div class="card">
                <h3>🔧 Services Status</h3>
                <div id="servicesStatus">Loading...</div>
            </div>
            
            <div class="card">
                <h3>📝 Draft Management</h3>
                <div id="draftsStatus">Loading...</div>
            </div>
        </div>
        
        <div class="refresh-info">
            🔄 Auto-refresh every 30 seconds
        </div>
    </div>

    <script>
        function updateDashboard() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    updateHealthStatus(data.health);
                    updateMetrics(data.metrics);
                    updateServices(data.services);
                    updateDrafts(data.drafts);
                    document.getElementById('lastUpdated').textContent = new Date().toLocaleString();
                })
                .catch(error => {
                    console.error('Error updating dashboard:', error);
                    document.getElementById('lastUpdated').textContent = 'Error loading data';
                });
        }
        
        function getStatusIndicator(status) {
            const statusMap = {
                'healthy': 'status-healthy',
                'ok': 'status-healthy', 
                'warning': 'status-warning',
                'degraded': 'status-warning',
                'error': 'status-error',
                'critical': 'status-error',
                'unhealthy': 'status-error'
            };
            return statusMap[status] || 'status-warning';
        }
        
        function updateHealthStatus(health) {
            const container = document.getElementById('healthStatus');
            container.innerHTML = `
                <div class="metric">
                    <span class="status-indicator ${getStatusIndicator(health.status)}"></span>
                    <span class="metric-label">Status:</span> 
                    <span class="metric-value">${health.status}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Uptime:</span> 
                    <span class="metric-value">${health.uptime_formatted || 'N/A'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Services:</span> 
                    <span class="metric-value">${health.services_healthy || '0/0'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">24h Translations:</span> 
                    <span class="metric-value">${health.translations_24h || 0}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">24h Errors:</span> 
                    <span class="metric-value">${health.error_count_24h || 0}</span>
                </div>
            `;
        }
        
        function updateMetrics(metrics) {
            const container = document.getElementById('metricsStatus');
            const cache = metrics.cache_performance || {};
            const cacheStatus = metrics.cache_status || {};
            
            container.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Cache Hit Rate:</span> 
                    <span class="metric-value">${cache.hit_rate_percent || 0}%</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Total Requests:</span> 
                    <span class="metric-value">${cache.total_requests || 0}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Cache Usage:</span> 
                    <span class="metric-value">${cacheStatus.current_size || 0}/${cacheStatus.max_size || 0}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Memory Usage:</span> 
                    <span class="metric-value">${cacheStatus.memory_usage_mb || 0} MB</span>
                </div>
            `;
        }
        
        function updateServices(services) {
            const container = document.getElementById('servicesStatus');
            const serviceList = services.services || {};
            
            if (Object.keys(serviceList).length === 0) {
                container.innerHTML = '<div class="metric">No services configured yet</div>';
                return;
            }
            
            let html = `
                <div class="metric">
                    <span class="metric-label">Healthy Services:</span> 
                    <span class="metric-value">${services.healthy_services || 0}/${services.total_services || 0}</span>
                </div>
            `;
            
            for (const [name, service] of Object.entries(serviceList)) {
                html += `
                    <div class="metric">
                        <span class="status-indicator ${getStatusIndicator(service.status)}"></span>
                        <span class="metric-label">${name}:</span> 
                        <span class="metric-value">${service.state} (${service.failure_rate * 100}% fail rate)</span>
                    </div>
                `;
            }
            
            container.innerHTML = html;
        }
        
        function updateDrafts(drafts) {
            const container = document.getElementById('draftsStatus');
            container.innerHTML = `
                <div class="metric">
                    <span class="status-indicator ${getStatusIndicator(drafts.status)}"></span>
                    <span class="metric-label">Pending Drafts:</span> 
                    <span class="metric-value">${drafts.pending_drafts_count || 0}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Languages:</span> 
                    <span class="metric-value">${(drafts.draft_languages || []).join(', ') || 'None'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Oldest Draft:</span> 
                    <span class="metric-value">${drafts.oldest_draft_age_hours ? Math.round(drafts.oldest_draft_age_hours) + 'h' : 'N/A'}</span>
                </div>
            `;
        }
        
        // Initial load and set up auto-refresh
        updateDashboard();
        setInterval(updateDashboard, 30000); // Refresh every 30 seconds
    </script>
</body>
</html>
        '''
    
    def run(self):
        """Start the dashboard server"""
        try:
            structured_logger.info(
                f"Starting Twitter Bot Dashboard on port {self.port}",
                event="dashboard_starting",
                port=self.port,
                debug=self.debug
            )
            
            # Run Flask in production mode unless debug is enabled
            self.app.run(
                host='0.0.0.0',
                port=self.port,
                debug=self.debug,
                threaded=True,
                use_reloader=False  # Prevent double startup in debug mode
            )
        except Exception as e:
            structured_logger.error(
                f"Failed to start dashboard: {str(e)}",
                event="dashboard_startup_failed",
                error=str(e)
            )
            raise
    
    def start_in_thread(self) -> threading.Thread:
        """Start dashboard in a separate thread"""
        thread = threading.Thread(
            target=self.run,
            name="DashboardThread",
            daemon=True
        )
        thread.start()
        return thread


# Global dashboard instance
dashboard = None

def start_dashboard(port: int = None, debug: bool = False) -> Optional[threading.Thread]:
    """Start the dashboard if enabled via environment variable"""
    global dashboard
    
    # Check if dashboard is enabled
    if not os.getenv('ENABLE_DASHBOARD', 'false').lower() == 'true':
        structured_logger.info("Dashboard is disabled. Set ENABLE_DASHBOARD=true to enable.")
        return None
    
    # Get port from environment or parameter
    dashboard_port = port or int(os.getenv('DASHBOARD_PORT', '8080'))
    
    try:
        dashboard = TwitterBotDashboard(port=dashboard_port, debug=debug)
        thread = dashboard.start_in_thread()
        
        structured_logger.info(
            f"Dashboard started on http://localhost:{dashboard_port}",
            event="dashboard_started",
            port=dashboard_port,
            endpoints=['/health', '/metrics', '/config', '/drafts', '/services'],
            ui_enabled=os.getenv('ENABLE_DASHBOARD_UI', 'false').lower() == 'true'
        )
        
        return thread
    except Exception as e:
        structured_logger.error(
            f"Failed to start dashboard: {str(e)}",
            event="dashboard_startup_error",
            error=str(e)
        )
        return None

def update_dashboard_stats(**kwargs):
    """Update dashboard statistics (convenience function)"""
    global dashboard
    if dashboard:
        dashboard.update_stats(**kwargs)
