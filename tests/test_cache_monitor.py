# =============================================================================
# CACHE MONITOR TESTS
# =============================================================================

import pytest
import sys
import os
import json
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock, mock_open
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils.cache_monitor import CacheMonitor

class TestCacheMonitor:
    def setup_method(self):
        """Set up test fixtures"""
        self.monitor = CacheMonitor()
    
    @patch('src.utils.cache_monitor.gemini_translator')
    def test_get_performance_report_basic(self, mock_translator):
        """Test basic performance report generation"""
        # Mock the cache metrics
        mock_cache_info = {
            'metrics': {
                'hit_rate': 75.0,
                'hits': 15,
                'misses': 5,
                'evictions': 2,
                'size': 10,
                'memory_usage_mb': 1.5
            },
            'config': {
                'max_size': 100,
                'ttl_hours': 24,
                'cleanup_interval_minutes': 30
            },
            'top_entries': [
                {
                    'cache_key': 'trans_Spanish_abc123',
                    'access_count': 5,
                    'age_hours': 2.5,
                    'target_language': 'Spanish',
                    'character_count': 45
                }
            ]
        }
        
        mock_translator.get_cache_metrics.return_value = mock_cache_info
        
        report = self.monitor.get_performance_report()
        
        assert 'performance' in report
        assert 'cache_status' in report
        assert 'configuration' in report
        assert 'top_entries' in report
        assert 'system' in report
        
        # Check performance metrics
        assert report['performance']['hit_rate_percent'] == 75.0
        assert report['performance']['total_requests'] == 20  # 15 + 5
        assert report['performance']['cache_hits'] == 15
        assert report['performance']['cache_misses'] == 5
        
        # Check cache status
        assert report['cache_status']['current_size'] == 10
        assert report['cache_status']['max_size'] == 100
        assert report['cache_status']['memory_usage_mb'] == 1.5
        assert report['cache_status']['fill_percentage'] == 10.0  # 10/100 * 100
        
        # Check configuration
        assert report['configuration']['ttl_hours'] == 24
        
        # Check system info
        assert 'uptime_hours' in report['system']
        assert 'last_report' in report['system']
    
    @patch('src.utils.cache_monitor.gemini_translator')
    def test_get_performance_report_zero_division_safety(self, mock_translator):
        """Test performance report handles zero division safely"""
        mock_cache_info = {
            'metrics': {
                'hit_rate': 0.0,
                'hits': 0,
                'misses': 0,
                'evictions': 0,
                'size': 0,
                'memory_usage_mb': 0.0
            },
            'config': {
                'max_size': 100,
                'ttl_hours': 24,
                'cleanup_interval_minutes': 30
            },
            'top_entries': []
        }
        
        mock_translator.get_cache_metrics.return_value = mock_cache_info
        
        report = self.monitor.get_performance_report()
        
        # Should handle zero requests gracefully
        assert report['performance']['total_requests'] == 0
        assert report['performance']['requests_per_hour'] == 0
        assert report['cache_status']['fill_percentage'] == 0.0
    
    @patch('src.utils.cache_monitor.gemini_translator')
    @patch('builtins.print')
    def test_print_performance_summary_excellent(self, mock_print, mock_translator):
        """Test performance summary with excellent hit rate"""
        mock_cache_info = {
            'metrics': {
                'hit_rate': 85.0,
                'hits': 85,
                'misses': 15,
                'evictions': 5,
                'size': 50,
                'memory_usage_mb': 2.3
            },
            'config': {
                'max_size': 100,
                'ttl_hours': 24,
                'cleanup_interval_minutes': 30
            },
            'top_entries': [
                {
                    'cache_key': 'trans_Spanish_abc123',
                    'access_count': 25,
                    'age_hours': 5.2,
                    'target_language': 'Spanish',
                    'character_count': 45
                },
                {
                    'cache_key': 'trans_French_def456',
                    'access_count': 18,
                    'age_hours': 3.1,
                    'target_language': 'French',
                    'character_count': 38
                }
            ]
        }
        
        mock_translator.get_cache_metrics.return_value = mock_cache_info
        
        self.monitor.print_performance_summary()
        
        # Verify print was called (summary was generated)
        assert mock_print.called
        
        # Check that excellent performance message would be shown
        printed_text = ' '.join([str(call[0][0]) for call in mock_print.call_args_list])
        assert "EXCELLENT" in printed_text or "excellent" in printed_text.lower()
    
    @patch('src.utils.cache_monitor.gemini_translator')
    @patch('builtins.print')
    def test_print_performance_summary_poor(self, mock_print, mock_translator):
        """Test performance summary with poor hit rate"""
        mock_cache_info = {
            'metrics': {
                'hit_rate': 20.0,
                'hits': 2,
                'misses': 8,
                'evictions': 0,
                'size': 5,
                'memory_usage_mb': 0.5
            },
            'config': {
                'max_size': 100,
                'ttl_hours': 24,
                'cleanup_interval_minutes': 30
            },
            'top_entries': []
        }
        
        mock_translator.get_cache_metrics.return_value = mock_cache_info
        
        self.monitor.print_performance_summary()
        
        # Verify print was called
        assert mock_print.called
        
        # Check that poor performance message would be shown
        printed_text = ' '.join([str(call[0][0]) for call in mock_print.call_args_list])
        assert "POOR" in printed_text or "poor" in printed_text.lower()
    
    @patch('src.utils.cache_monitor.gemini_translator')
    def test_log_cache_stats_periodically_first_time(self, mock_translator):
        """Test periodic logging runs on first call"""
        mock_cache_info = {
            'metrics': {
                'hit_rate': 60.0,
                'hits': 12,
                'misses': 8,
                'evictions': 1,
                'size': 15,
                'memory_usage_mb': 1.2
            },
            'config': {
                'max_size': 100,
                'ttl_hours': 24,
                'cleanup_interval_minutes': 30
            },
            'top_entries': []
        }
        
        mock_translator.get_cache_metrics.return_value = mock_cache_info
        
        with patch('src.utils.cache_monitor.logger') as mock_logger:
            # Reset last report time to force logging
            self.monitor.last_report_time = 0
            
            # Should log on first call (no previous report time)
            self.monitor.log_cache_stats_periodically(interval_minutes=60)
            
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0][0]
            assert "60.0%" in call_args
            assert "15/100" in call_args
            assert "1.2MB" in call_args
    
    @patch('src.utils.cache_monitor.gemini_translator') 
    @patch('src.utils.cache_monitor.time')
    def test_log_cache_stats_periodically_interval_not_reached(self, mock_time, mock_translator):
        """Test periodic logging doesn't run if interval not reached"""
        mock_time.time.return_value = 1000.0
        
        # Set last report time to recent
        self.monitor.last_report_time = 990.0  # 10 seconds ago
        
        with patch('src.utils.cache_monitor.logger') as mock_logger:
            # Should not log (interval is 60 minutes = 3600 seconds)
            self.monitor.log_cache_stats_periodically(interval_minutes=60)
            
            mock_logger.info.assert_not_called()
    
    @patch('src.utils.cache_monitor.gemini_translator')
    def test_save_performance_report_default_filename(self, mock_translator):
        """Test saving performance report with default filename"""
        mock_cache_info = {
            'metrics': {
                'hit_rate': 50.0,
                'hits': 10,
                'misses': 10,
                'evictions': 0,
                'size': 8,
                'memory_usage_mb': 0.8
            },
            'config': {
                'max_size': 100,
                'ttl_hours': 24,
                'cleanup_interval_minutes': 30
            },
            'top_entries': []
        }
        
        mock_translator.get_cache_metrics.return_value = mock_cache_info
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('json.dump') as mock_json_dump:
                with patch('src.utils.cache_monitor.logger') as mock_logger:
                    filename = self.monitor.save_performance_report()
                    
                    # Should generate a filename
                    assert filename is not None
                    assert filename.startswith('cache_report_')
                    assert filename.endswith('.json')
                    
                    # Should have opened file and dumped JSON
                    mock_file.assert_called_once()
                    mock_json_dump.assert_called_once()
                    
                    # Should have logged success
                    mock_logger.info.assert_called_once()
    
    @patch('src.utils.cache_monitor.gemini_translator')
    def test_save_performance_report_custom_filename(self, mock_translator):
        """Test saving performance report with custom filename"""
        mock_cache_info = {
            'metrics': {'hit_rate': 50.0, 'hits': 10, 'misses': 10, 'evictions': 0, 'size': 8, 'memory_usage_mb': 0.8},
            'config': {'max_size': 100, 'ttl_hours': 24, 'cleanup_interval_minutes': 30},
            'top_entries': []
        }
        
        mock_translator.get_cache_metrics.return_value = mock_cache_info
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('json.dump') as mock_json_dump:
                filename = self.monitor.save_performance_report('custom_report.json')
                
                assert filename == 'custom_report.json'
                mock_file.assert_called_once_with('custom_report.json', 'w')
    
    @patch('src.utils.cache_monitor.gemini_translator')
    def test_save_performance_report_error_handling(self, mock_translator):
        """Test error handling in save performance report"""
        mock_translator.get_cache_metrics.side_effect = Exception("Cache error")
        
        with patch('src.utils.cache_monitor.logger') as mock_logger:
            filename = self.monitor.save_performance_report()
            
            assert filename is None
            mock_logger.error.assert_called_once()
    
    @patch('src.utils.cache_monitor.gemini_translator')
    @patch('src.utils.cache_monitor.logger')
    def test_print_performance_summary_error_handling(self, mock_logger, mock_translator):
        """Test error handling in print performance summary"""
        mock_translator.get_cache_metrics.side_effect = Exception("Metrics error")
        
        with patch('builtins.print') as mock_print:
            self.monitor.print_performance_summary()
            
            # Should log error and print error message
            mock_logger.error.assert_called_once()
            mock_print.assert_called_with("❌ Unable to generate cache performance report")
    
    def test_monitor_initialization(self):
        """Test cache monitor initialization"""
        monitor = CacheMonitor()
        
        assert hasattr(monitor, 'start_time')
        assert hasattr(monitor, 'last_report_time')
        assert monitor.start_time > 0
        assert monitor.last_report_time > 0
    
    @patch('src.utils.cache_monitor.gemini_translator')
    def test_performance_categories(self, mock_translator):
        """Test performance categorization in different scenarios"""
        test_scenarios = [
            (95.0, "EXCELLENT"),  # Excellent performance
            (65.0, "GOOD"),       # Good performance  
            (40.0, "FAIR"),       # Fair performance
            (15.0, "POOR")        # Poor performance
        ]
        
        for hit_rate, expected_category in test_scenarios:
            mock_cache_info = {
                'metrics': {
                    'hit_rate': hit_rate,
                    'hits': int(hit_rate),
                    'misses': int(100 - hit_rate),
                    'evictions': 0,
                    'size': 10,
                    'memory_usage_mb': 1.0
                },
                'config': {
                    'max_size': 100,
                    'ttl_hours': 24,
                    'cleanup_interval_minutes': 30
                },
                'top_entries': []
            }
            
            mock_translator.get_cache_metrics.return_value = mock_cache_info
            
            with patch('builtins.print') as mock_print:
                self.monitor.print_performance_summary()
                
                # Check that appropriate performance category was printed
                printed_text = ' '.join([str(call[0][0]) for call in mock_print.call_args_list])
                assert expected_category in printed_text
    
    @patch('src.utils.cache_monitor.gemini_translator')
    def test_top_entries_display(self, mock_translator):
        """Test display of top accessed cache entries"""
        mock_cache_info = {
            'metrics': {
                'hit_rate': 70.0,
                'hits': 70,
                'misses': 30,
                'evictions': 2,
                'size': 25,
                'memory_usage_mb': 2.1
            },
            'config': {
                'max_size': 100,
                'ttl_hours': 24,
                'cleanup_interval_minutes': 30
            },
            'top_entries': [
                {
                    'cache_key': 'trans_Spanish_abc123',
                    'access_count': 15,
                    'age_hours': 4.2,
                    'target_language': 'Spanish',
                    'character_count': 45
                },
                {
                    'cache_key': 'trans_French_def456',
                    'access_count': 12,
                    'age_hours': 2.8,
                    'target_language': 'French',
                    'character_count': 38
                },
                {
                    'cache_key': 'trans_German_ghi789',
                    'access_count': 9,
                    'age_hours': 1.5,
                    'target_language': 'German',
                    'character_count': 52
                }
            ]
        }
        
        mock_translator.get_cache_metrics.return_value = mock_cache_info
        
        with patch('builtins.print') as mock_print:
            self.monitor.print_performance_summary()
            
            printed_text = ' '.join([str(call[0][0]) for call in mock_print.call_args_list])
            
            # Should display top 3 entries
            assert "Spanish" in printed_text
            assert "French" in printed_text  
            assert "German" in printed_text
            assert "15 hits" in printed_text  # Spanish access count
            assert "4.2h" in printed_text    # Spanish age
    
    @patch('src.utils.cache_monitor.time')
    def test_uptime_calculation(self, mock_time):
        """Test uptime calculation in reports"""
        # Mock start time to 1 hour ago
        start_time = 1000.0
        current_time = 1000.0 + 3600.0  # 1 hour later
        
        mock_time.time.return_value = current_time
        
        monitor = CacheMonitor()
        monitor.start_time = start_time
        
        with patch('src.utils.cache_monitor.gemini_translator') as mock_translator:
            mock_translator.get_cache_metrics.return_value = {
                'metrics': {'hit_rate': 0, 'hits': 0, 'misses': 0, 'evictions': 0, 'size': 0, 'memory_usage_mb': 0},
                'config': {'max_size': 100, 'ttl_hours': 24, 'cleanup_interval_minutes': 30},
                'top_entries': []
            }
            
            report = monitor.get_performance_report()
            
            # Should show 1.0 hours uptime
            assert report['system']['uptime_hours'] == 1.0
