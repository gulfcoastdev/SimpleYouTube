#!/usr/bin/env python3
"""
Simple test script for the YouTube Transcript Extractor API
"""

import requests
import json

# Configuration
BASE_URL = "http://127.0.0.1:8000"
TEST_URLS = [
    "https://www.youtube.com/watch?v=8jPQjjsBbIc",  # 3Blue1Brown - Linear algebra
    "https://www.youtube.com/watch?v=aircAruvnKk",  # 3Blue1Brown - Neural networks
    "https://youtu.be/aircAruvnKk",                # Short format
    "invalid-url",                                  # Invalid URL test
]

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

def main():
    """Run all tests"""
    print("YouTube Transcript Extractor - Test Suite")
    print("=" * 60)
    
    # Test server health first
    if not test_server_health():
        return
    
    # Test transcript extraction
    print(f"\nTesting transcript extraction with {len(TEST_URLS)} URLs:")
    
    for url in TEST_URLS:
        test_transcript_extraction(url)
    
    print(f"\n{'='*60}")
    print("Test suite completed!")
    print("="*60)

if __name__ == "__main__":
    main()