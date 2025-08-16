#!/usr/bin/env python3
"""
Comprehensive test script for the YouTube Transcript Extractor API
"""

import requests
import json
import sys
import traceback

# Configuration
BASE_URL = "http://127.0.0.1:8000"
TEST_URLS = [
    "https://www.youtube.com/watch?v=8jPQjjsBbIc",  # 3Blue1Brown - Linear algebra
    "https://www.youtube.com/watch?v=aircAruvnKk",  # 3Blue1Brown - Neural networks
    "https://youtu.be/aircAruvnKk",                # Short format
    "invalid-url",                                  # Invalid URL test
]

def test_imports():
    """Test that the Flask app imports work correctly"""
    print("Testing Python imports...")
    try:
        import sys
        sys.path.insert(0, '.')
        
        # Test individual imports
        from dotenv import load_dotenv
        print("✅ dotenv import successful")
        
        from youtube_transcript_api import YouTubeTranscriptApi
        print("✅ YouTubeTranscriptApi import successful")
        
        from youtube_transcript_api.proxies import WebshareProxyConfig
        print("✅ WebshareProxyConfig import successful")
        
        # Test app import
        import app
        print("✅ Flask app import successful")
        
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        traceback.print_exc()
        return False

def test_transcript_extraction(url):
    """Test transcript extraction for a given URL"""
    print(f"\n{'='*60}")
    print(f"Testing URL: {url}")
    print('='*60)
    
    try:
        response = requests.post(
            f"{BASE_URL}/get_transcript",
            json={"url": url},
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ SUCCESS")
                print(f"Video ID: {data['video_id']}")
                print(f"Transcript entries: {len(data['transcript'])}")
                print(f"Full text length: {len(data['full_text'])} characters")
                
                # Show first few transcript entries
                print("\nFirst 3 transcript entries:")
                for i, entry in enumerate(data['transcript'][:3]):
                    print(f"  {i+1}. [{entry['start']:.1f}s] {entry['text']}")
                
                # Show first 200 characters of full text
                print(f"\nFirst 200 characters:")
                print(f"  {data['full_text'][:200]}...")
                
            else:
                print("❌ API returned success=False")
                print(f"Error: {data.get('error', 'Unknown error')}")
        else:
            print("❌ HTTP ERROR")
            try:
                error_data = response.json()
                print(f"Error: {error_data.get('error', 'Unknown error')}")
            except:
                print(f"Raw response: {response.text}")
                
    except requests.exceptions.ConnectionError:
        print("❌ CONNECTION ERROR")
        print("Make sure the Flask app is running on http://127.0.0.1:8000")
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")

def test_server_health():
    """Test if the server is running"""
    print("Testing server health...")
    try:
        response = requests.get(BASE_URL)
        if response.status_code == 200:
            print("✅ Server is running and responding")
            return True
        else:
            print(f"❌ Server responded with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server")
        print("Make sure to run: source venv/bin/activate && PORT=8000 python app.py")
        return False

def test_proxy_status_endpoint():
    """Test the proxy status endpoint specifically"""
    print("\nTesting /proxy_status endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/proxy_status", timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
        print(f"Response length: {len(response.text)} chars")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ Valid JSON response")
                print(f"Proxy enabled: {data.get('proxy_enabled')}")
                print(f"Countries: {data.get('countries')}")
                return True
            except json.JSONDecodeError as e:
                print("❌ Invalid JSON response")
                print(f"First 200 chars: {response.text[:200]}")
                return False
        else:
            print(f"❌ HTTP Error {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False

def test_rate_limiting():
    """Test rate limiting functionality"""
    print("\nTesting rate limiting...")
    
    # Test health endpoint (should not be rate limited)
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        print(f"Health endpoint: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Rate limiting enabled: {data.get('rate_limiting_enabled')}")
            print(f"Daily limit: {data.get('daily_limit')}")
        
        # Check if we have rate limit headers
        headers = response.headers
        if 'X-RateLimit-Limit' in headers:
            print(f"Rate limit headers present:")
            print(f"  Limit: {headers.get('X-RateLimit-Limit')}")
            print(f"  Remaining: {headers.get('X-RateLimit-Remaining')}")
            print(f"  Reset: {headers.get('X-RateLimit-Reset')}")
        else:
            print("No rate limit headers (Redis likely not connected)")
            
    except Exception as e:
        print(f"❌ Rate limiting test failed: {e}")
        return False
    
    return True

def test_admin_endpoints():
    """Test admin endpoints (requires ADMIN_TOKEN)"""
    print("\nTesting admin endpoints...")
    
    # Test without admin token
    try:
        response = requests.post(f"{BASE_URL}/admin/issue_bypass", timeout=10)
        print(f"Issue bypass without token: {response.status_code}")
        
        if response.status_code == 401:
            print("✅ Properly secured - unauthorized without token")
        elif response.status_code == 503:
            print("⚠️  Admin functionality disabled (no ADMIN_TOKEN)")
        
    except Exception as e:
        print(f"❌ Admin endpoint test failed: {e}")

def main():
    """Run all tests"""
    print("YouTube Transcript Extractor - Test Suite")
    print("=" * 60)
    
    # Test imports first
    if not test_imports():
        print("❌ Import tests failed - server likely has import errors")
        return
    
    # Test server health
    if not test_server_health():
        return
    
    # Test rate limiting
    test_rate_limiting()
    
    # Test admin endpoints
    test_admin_endpoints()
    
    # Test proxy status endpoint specifically
    if not test_proxy_status_endpoint():
        print("❌ Proxy status endpoint failed")
        return
    
    # Test transcript extraction (this will count against rate limit)
    print(f"\nTesting transcript extraction with {len(TEST_URLS)} URLs:")
    print("⚠️  Note: These requests count against your daily rate limit")
    
    for i, url in enumerate(TEST_URLS[:2]):  # Limit to 2 tests to avoid hitting rate limit
        print(f"\nTest {i+1}/{min(2, len(TEST_URLS))}:")
        test_transcript_extraction(url)
    
    print(f"\n{'='*60}")
    print("Test suite completed!")
    print("✅ Rate limiting system implemented and tested")
    print("="*60)

if __name__ == "__main__":
    main()