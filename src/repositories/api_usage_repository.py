# =============================================================================
# API USAGE REPOSITORY
# =============================================================================

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func, extract
from src.models.database_models import APIUsage as APIUsageModel
from src.repositories.base_repository import BaseRepository

class APIUsageRepository(BaseRepository[APIUsageModel]):
    """Repository for API usage tracking and analytics"""
    
    def __init__(self, session: Session):
        super().__init__(session, APIUsageModel)
    
    def log_api_call(
        self,
        service: str,
        endpoint: str,
        method: str = 'GET',
        response_time: Optional[float] = None,
        status_code: Optional[int] = None,
        success: bool = True,
        error_info: Optional[Dict[str, Any]] = None,
        request_metadata: Optional[Dict[str, Any]] = None
    ) -> APIUsageModel:
        """Log an API call"""
        now = datetime.now(timezone.utc)
        
        return self.create(
            service=service,
            endpoint=endpoint,
            method=method,
            timestamp=now,
            response_time=response_time,
            status_code=status_code,
            success=success,
            error_info=error_info or {},
            request_metadata=request_metadata or {},
            date=now.strftime('%Y-%m-%d'),
            month=now.strftime('%Y-%m')
        )
    
    def get_daily_usage(self, service: str, date: Optional[datetime] = None) -> Dict[str, Any]:
        """Get API usage statistics for a specific day"""
        if date is None:
            date = datetime.now(timezone.utc)
        
        date_str = date.strftime('%Y-%m-%d')
        
        try:
            # Total calls
            total_calls = self.session.query(APIUsageModel).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.date == date_str
                )
            ).count()
            
            # Successful calls
            successful_calls = self.session.query(APIUsageModel).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.date == date_str,
                    APIUsageModel.success == True
                )
            ).count()
            
            # Failed calls
            failed_calls = total_calls - successful_calls
            
            # Average response time
            avg_response_time = self.session.query(
                func.avg(APIUsageModel.response_time)
            ).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.date == date_str,
                    APIUsageModel.response_time.isnot(None)
                )
            ).scalar() or 0
            
            # Calls by endpoint
            endpoint_stats = self.session.query(
                APIUsageModel.endpoint,
                func.count(APIUsageModel.id).label('count')
            ).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.date == date_str
                )
            ).group_by(APIUsageModel.endpoint).all()
            
            return {
                'date': date_str,
                'service': service,
                'total_calls': total_calls,
                'successful_calls': successful_calls,
                'failed_calls': failed_calls,
                'success_rate': (successful_calls / total_calls * 100) if total_calls > 0 else 0,
                'average_response_time': round(float(avg_response_time), 3),
                'endpoint_breakdown': {endpoint: count for endpoint, count in endpoint_stats}
            }
        except Exception as e:
            self.logger.error(f"Error getting daily usage for {service}: {str(e)}")
            return {}
    
    def get_monthly_usage(self, service: str, month: Optional[datetime] = None) -> Dict[str, Any]:
        """Get API usage statistics for a specific month"""
        if month is None:
            month = datetime.now(timezone.utc)
        
        month_str = month.strftime('%Y-%m')
        
        try:
            # Total calls
            total_calls = self.session.query(APIUsageModel).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.month == month_str
                )
            ).count()
            
            # Daily breakdown
            daily_stats = self.session.query(
                APIUsageModel.date,
                func.count(APIUsageModel.id).label('count'),
                func.avg(APIUsageModel.response_time).label('avg_response_time'),
                func.count(APIUsageModel.id).filter(APIUsageModel.success == True).label('successful_calls')
            ).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.month == month_str
                )
            ).group_by(APIUsageModel.date).order_by(APIUsageModel.date).all()
            
            return {
                'month': month_str,
                'service': service,
                'total_calls': total_calls,
                'daily_breakdown': [
                    {
                        'date': date,
                        'calls': count,
                        'successful_calls': successful_calls,
                        'success_rate': (successful_calls / count * 100) if count > 0 else 0,
                        'avg_response_time': round(float(avg_response_time or 0), 3)
                    }
                    for date, count, avg_response_time, successful_calls in daily_stats
                ]
            }
        except Exception as e:
            self.logger.error(f"Error getting monthly usage for {service}: {str(e)}")
            return {}
    
    def get_current_limits(self, service: str) -> Dict[str, int]:
        """Get current daily and monthly usage counts"""
        now = datetime.now(timezone.utc)
        today = now.strftime('%Y-%m-%d')
        this_month = now.strftime('%Y-%m')
        
        try:
            daily_count = self.session.query(APIUsageModel).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.date == today
                )
            ).count()
            
            monthly_count = self.session.query(APIUsageModel).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.month == this_month
                )
            ).count()
            
            return {
                'daily_requests': daily_count,
                'monthly_requests': monthly_count,
                'date': today,
                'month': this_month
            }
        except Exception as e:
            self.logger.error(f"Error getting current limits for {service}: {str(e)}")
            return {'daily_requests': 0, 'monthly_requests': 0}
    
    def get_error_analysis(self, service: str, days_back: int = 7) -> Dict[str, Any]:
        """Analyze errors for a service over the past N days"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        try:
            # Get failed calls
            failed_calls = self.session.query(APIUsageModel).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.timestamp >= cutoff_date,
                    APIUsageModel.success == False
                )
            ).all()
            
            # Analyze error patterns
            error_by_endpoint = {}
            error_by_status_code = {}
            error_messages = {}
            
            for call in failed_calls:
                # Group by endpoint
                endpoint = call.endpoint
                if endpoint not in error_by_endpoint:
                    error_by_endpoint[endpoint] = 0
                error_by_endpoint[endpoint] += 1
                
                # Group by status code
                status_code = call.status_code or 'unknown'
                if status_code not in error_by_status_code:
                    error_by_status_code[status_code] = 0
                error_by_status_code[status_code] += 1
                
                # Collect error messages
                if call.error_info and 'message' in call.error_info:
                    message = call.error_info['message']
                    if message not in error_messages:
                        error_messages[message] = 0
                    error_messages[message] += 1
            
            return {
                'service': service,
                'analysis_period_days': days_back,
                'total_failed_calls': len(failed_calls),
                'error_by_endpoint': error_by_endpoint,
                'error_by_status_code': error_by_status_code,
                'common_error_messages': dict(sorted(error_messages.items(), key=lambda x: x[1], reverse=True)[:10])
            }
        except Exception as e:
            self.logger.error(f"Error analyzing errors for {service}: {str(e)}")
            return {}
    
    def get_performance_metrics(self, service: str, days_back: int = 30) -> Dict[str, Any]:
        """Get performance metrics for a service"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        try:
            # Response time statistics
            response_times = self.session.query(APIUsageModel.response_time).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.timestamp >= cutoff_date,
                    APIUsageModel.response_time.isnot(None)
                )
            ).all()
            
            if not response_times:
                return {}
            
            times = [rt[0] for rt in response_times]
            times.sort()
            
            # Calculate percentiles
            def percentile(data, p):
                index = int(len(data) * p / 100)
                return data[min(index, len(data) - 1)]
            
            # Hourly call distribution
            hourly_distribution = self.session.query(
                extract('hour', APIUsageModel.timestamp).label('hour'),
                func.count(APIUsageModel.id).label('count')
            ).filter(
                and_(
                    APIUsageModel.service == service,
                    APIUsageModel.timestamp >= cutoff_date
                )
            ).group_by('hour').all()
            
            return {
                'service': service,
                'analysis_period_days': days_back,
                'response_time_stats': {
                    'min': min(times),
                    'max': max(times),
                    'mean': sum(times) / len(times),
                    'median': percentile(times, 50),
                    'p95': percentile(times, 95),
                    'p99': percentile(times, 99)
                },
                'hourly_distribution': {int(hour): count for hour, count in hourly_distribution}
            }
        except Exception as e:
            self.logger.error(f"Error getting performance metrics for {service}: {str(e)}")
            return {}
    
    def cleanup_old_logs(self, days_old: int = 90) -> int:
        """Clean up old API usage logs"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            
            deleted_count = self.session.query(APIUsageModel).filter(
                APIUsageModel.timestamp < cutoff_date
            ).delete()
            
            self.session.flush()
            return deleted_count
        except Exception as e:
            self.logger.error(f"Error cleaning up old API logs: {str(e)}")
            self.session.rollback()
            return 0
    
    def get_service_overview(self) -> Dict[str, Any]:
        """Get overview of all services"""
        try:
            # Get unique services
            services = self.session.query(APIUsageModel.service).distinct().all()
            service_list = [s[0] for s in services]
            
            overview = {}
            for service in service_list:
                daily_usage = self.get_daily_usage(service)
                monthly_usage = self.get_monthly_usage(service)
                
                overview[service] = {
                    'daily_usage': daily_usage,
                    'monthly_total': monthly_usage.get('total_calls', 0)
                }
            
            return overview
        except Exception as e:
            self.logger.error(f"Error getting service overview: {str(e)}")
            return {}
    
    @property
    def logger(self):
        """Get logger for this repository"""
        from src.utils.logger import logger
        return logger
