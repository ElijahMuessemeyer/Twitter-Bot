#!/usr/bin/env python3
"""
Test script for the Twitter Bot Dashboard
Tests all endpoints to ensure they return valid responses
"""

import json
import time
import threading
import requests
from urllib3.exceptions import InsecureRequestWarning

# Suppress SSL warnings for testing
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def test_dashboard_endpoints():
    """Test all dashboard endpoints"""
    base_url = "http://localhost:8080"
    
    endpoints = [
        "/health",
        "/metrics", 
        "/config",
        "/drafts",
        "/services",
        "/api/status"
    ]
    
    print("🧪 Testing Dashboard Endpoints")
    print("=" * 50)
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            status = "✅ PASS" if response.status_code == 200 else f"❌ FAIL ({response.status_code})"
            
            print(f"{endpoint:<20} {status}")
            
            if response.status_code == 200:
                data = response.json()
                if 'error' in data:
                    print(f"  ⚠️  Warning: {data['error']}")
                else:
                    # Print some key fields for verification
                    if endpoint == "/health":
                        print(f"  Status: {data.get('status', 'N/A')}")
                        print(f"  Uptime: {data.get('uptime_formatted', 'N/A')}")
                    elif endpoint == "/metrics":
                        cache = data.get('cache_performance', {})
                        print(f"  Cache Hit Rate: {cache.get('hit_rate_percent', 0)}%")
                    elif endpoint == "/services":
                        services = data.get('services', {})
                        print(f"  Services: {len(services)} configured")
                    elif endpoint == "/drafts":
                        count = data.get('pending_drafts_count', 0)
                        print(f"  Pending Drafts: {count}")
            else:
                print(f"  Error: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"{endpoint:<20} ❌ FAIL (Connection Error)")
            print(f"  Error: {str(e)}")
    
    # Test UI endpoint
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        if response.status_code == 200 and "Twitter Bot Dashboard" in response.text:
            print(f"{'/':<20} ✅ PASS (UI)")
        else:
            print(f"{'/':<20} ⚠️  UI Disabled or Error")
    except:
        print(f"{'/':<20} ❌ FAIL (UI Connection Error)")
        
    print("\n✅ Dashboard endpoint testing complete!")

if __name__ == "__main__":
    print("Starting dashboard endpoint tests...")
    print("Make sure dashboard is running: ENABLE_DASHBOARD=true python main.py")
    print("Waiting 3 seconds for dashboard to start...\n")
    
    time.sleep(3)
    test_dashboard_endpoints()
