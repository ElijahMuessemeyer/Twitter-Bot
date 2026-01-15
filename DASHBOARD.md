# 🌐 Twitter Bot Web Dashboard

A lightweight, real-time monitoring dashboard for the Twitter Translation Bot, built with Flask.

## Features

### 🏥 Health Monitoring
- Real-time system health status
- Service uptime tracking
- Error count and recovery statistics
- Last successful run timestamp

### 📊 Performance Metrics
- Translation cache performance (hit rate, memory usage)
- API usage estimation and limits
- Request/response statistics
- Top translated content

### 🔧 Service Status
- Individual circuit breaker health
- Service failure rates and states
- Recent request statistics
- Last failure times

### 📝 Draft Management
- Pending drafts count and status
- Draft age and language distribution
- Draft management health indicators

### ⚙️ Configuration Display
- Current bot configuration (secrets masked)
- Environment variable status
- Target language configuration

## Quick Start

### 1. Enable Dashboard

```bash
# Enable API endpoints only
export ENABLE_DASHBOARD=true

# Enable with web UI
export ENABLE_DASHBOARD=true
export ENABLE_DASHBOARD_UI=true

# Custom port (default: 8080)
export DASHBOARD_PORT=8080
```

### 2. Start Bot with Dashboard

```bash
# Start bot normally (dashboard will auto-start if enabled)
python main.py

# Or run once with dashboard
python main.py once
```

### 3. Access Dashboard

**API Endpoints** (always available when dashboard enabled):
- `http://localhost:8080/health` - System health status
- `http://localhost:8080/metrics` - Performance metrics  
- `http://localhost:8080/config` - Configuration status
- `http://localhost:8080/drafts` - Draft management
- `http://localhost:8080/services` - Service health
- `http://localhost:8080/api/status` - Combined status

**Web Interface** (when `ENABLE_DASHBOARD_UI=true`):
- `http://localhost:8080/` - Interactive dashboard

## API Reference

### GET /health
Returns overall system health status.

```json
{
  "status": "healthy|degraded|error",
  "uptime_hours": 12.5,
  "uptime_formatted": "12h 30m",
  "services_healthy": "3/3",
  "last_successful_run": "2025-01-19T10:30:00Z",
  "translations_24h": 45,
  "error_count_24h": 2
}
```

### GET /metrics
Returns performance and cache metrics.

```json
{
  "cache_performance": {
    "hit_rate_percent": 78.5,
    "total_requests": 120,
    "requests_per_hour": 24.0
  },
  "cache_status": {
    "current_size": 89,
    "max_size": 1000,
    "memory_usage_mb": 15.2,
    "fill_percentage": 8.9
  },
  "api_usage": {
    "daily_requests_estimated": 26,
    "daily_limit": 10000,
    "monthly_posts_estimated": 780,
    "monthly_limit": 300000
  }
}
```

### GET /services
Returns individual service health from circuit breakers.

```json
{
  "services": {
    "twitter_api": {
      "status": "healthy",
      "state": "closed",
      "failure_rate": 0.0,
      "recent_requests": 15,
      "recent_failures": 0
    },
    "gemini_api": {
      "status": "healthy", 
      "state": "closed",
      "failure_rate": 0.1,
      "recent_requests": 25,
      "recent_failures": 2
    }
  },
  "healthy_services": 2,
  "total_services": 2
}
```

### GET /drafts
Returns draft management status.

```json
{
  "pending_drafts_count": 3,
  "oldest_draft_age_hours": 2.5,
  "newest_draft_age_hours": 0.3,
  "draft_languages": ["es", "fr", "de"],
  "status": "ok|warning|critical"
}
```

### GET /config
Returns configuration status with masked secrets.

```json
{
  "status": "configured",
  "configuration": {
    "twitter_api_configured": true,
    "gemini_api_configured": true,
    "target_languages_count": 5,
    "target_languages": ["es", "fr", "de", "it", "pt"],
    "cache_enabled": true,
    "circuit_breaker_enabled": true,
    "environment_variables": {
      "TWITTER_CONSUMER_KEY": "***CONFIGURED***",
      "GEMINI_API_KEY": "***CONFIGURED***",
      "ENABLE_DASHBOARD": "true",
      "DASHBOARD_PORT": "8080"
    }
  }
}
```

## Web Interface

The optional web UI provides:
- **Real-time monitoring** with 30-second auto-refresh
- **Mobile-friendly** responsive design
- **Status indicators** with color-coded health states
- **Clean layout** showing key metrics at a glance

### Status Indicators
- 🟢 **Green** - Healthy/OK
- 🟡 **Yellow** - Warning/Degraded
- 🔴 **Red** - Error/Critical/Unhealthy

## Security Considerations

### 🔒 Safe by Default
- **Disabled by default** - Must be explicitly enabled
- **Secrets masked** - API keys never exposed in responses
- **Local binding** - Listens on localhost only by default
- **No authentication** - Should not be exposed to public internet

### 🛡️ Production Deployment
For production use, consider:
- Adding authentication/authorization
- Using a reverse proxy with SSL
- Restricting network access
- Implementing rate limiting

## CLI Commands

```bash
# Show dashboard status and configuration
python main.py dashboard

# Example output:
# 🌐 Dashboard Information:
# ✅ Dashboard is ENABLED
# 🔗 API Endpoints: http://localhost:8080
# 🎨 Web UI: http://localhost:8080
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_DASHBOARD` | `false` | Enable/disable dashboard |
| `ENABLE_DASHBOARD_UI` | `false` | Enable web interface |
| `DASHBOARD_PORT` | `8080` | Dashboard server port |

## Integration

The dashboard integrates seamlessly with existing bot components:

- **Cache Monitor** - Real-time cache performance
- **Circuit Breakers** - Service health status  
- **Structured Logger** - Event tracking
- **Draft Manager** - Draft statistics
- **Configuration** - Settings validation

## Troubleshooting

### Dashboard Won't Start
```bash
# Check if enabled
python main.py dashboard

# Check port availability
lsof -i :8080

# Check logs for startup errors
tail -f logs/twitter_bot_$(date +%Y-%m-%d).log
```

### API Returns Errors
- Verify Flask is installed: `pip install Flask==3.1.0`
- Check bot components are initialized
- Review structured logs for component errors

### UI Not Loading
- Ensure `ENABLE_DASHBOARD_UI=true`
- Check browser console for errors
- Verify dashboard is running: `curl http://localhost:8080/health`

## Development

The dashboard is built with:
- **Flask** - Lightweight web framework
- **JSON APIs** - Machine-readable endpoints  
- **Vanilla JavaScript** - No frontend dependencies
- **Responsive CSS** - Mobile-friendly design

To extend the dashboard:
1. Add new endpoints in `src/web/dashboard.py`
2. Update the HTML template for UI changes
3. Add corresponding CLI commands if needed

## Performance Impact

The dashboard is designed to be lightweight:
- **Minimal overhead** - Separate thread, non-blocking
- **Efficient data collection** - Uses existing monitoring components
- **Optional UI** - API-only mode available
- **Auto-disabled** - No impact when disabled

Memory usage: ~5-10MB additional when enabled
CPU usage: <1% additional load during normal operation
