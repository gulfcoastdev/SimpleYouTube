#!/usr/bin/env python3
"""
Unit tests for YouTube Transcript Extractor
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os
from datetime import datetime, timezone, timedelta
import sys

# Add the current directory to Python path so we can import app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestRateLimiting(unittest.TestCase):
    """Test rate limiting functionality"""
    
    def setUp(self):
        """Set up test environment"""
        # Mock Redis client
        self.mock_redis = Mock()
        
        # Import app module with mocked Redis
        with patch('app.redis') as mock_redis_module:
            with patch.dict(os.environ, {
                'REDIS_URL': 'redis://localhost:6379',
                'DAILY_LIMIT': '5',
                'ADMIN_TOKEN': 'test_token'
            }):
                import app
                self.app_module = app
                self.app_module.redis_client = self.mock_redis
                self.app = app.app.test_client()
    
    def test_get_client_ip_with_forwarded_header(self):
        """Test IP extraction from X-Forwarded-For header"""
        with self.app_module.app.test_request_context(
            headers={'X-Forwarded-For': '203.0.113.195, 192.168.1.1, 10.0.0.1'}
        ):
            ip = self.app_module.get_client_ip()
            self.assertEqual(ip, '203.0.113.195')
    
    def test_get_client_ip_fallback(self):
        """Test IP fallback to remote_addr"""
        with self.app_module.app.test_request_context(environ_base={'REMOTE_ADDR': '192.168.1.100'}):
            ip = self.app_module.get_client_ip()
            self.assertEqual(ip, '192.168.1.100')
    
    def test_rate_limit_key_generation(self):
        """Test rate limit key generation"""
        test_ip = '192.168.1.1'
        with patch('app.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = '20250816'
            key = self.app_module.get_rate_limit_key(test_ip)
            self.assertEqual(key, 'rl:ip:192.168.1.1:20250816')
    
    def test_check_rate_limit_no_redis(self):
        """Test rate limiting when Redis is unavailable"""
        self.app_module.redis_client = None
        allowed, current, remaining = self.app_module.check_rate_limit('192.168.1.1')
        self.assertTrue(allowed)
        self.assertEqual(current, 0)
        self.assertEqual(remaining, 5)  # DAILY_LIMIT
    
    def test_check_rate_limit_first_request(self):
        """Test rate limiting for first request"""
        self.mock_redis.incr.return_value = 1
        self.mock_redis.exists.return_value = False
        
        with self.app_module.app.test_request_context():
            allowed, current, remaining = self.app_module.check_rate_limit('192.168.1.1')
            
        self.assertTrue(allowed)
        self.assertEqual(current, 1)
        self.assertEqual(remaining, 4)
        self.mock_redis.incr.assert_called_once()
        self.mock_redis.expire.assert_called_once()
    
    def test_check_rate_limit_exceeded(self):
        """Test rate limiting when limit is exceeded"""
        self.mock_redis.incr.return_value = 6  # Over limit of 5
        self.mock_redis.exists.return_value = False
        
        with self.app_module.app.test_request_context():
            allowed, current, remaining = self.app_module.check_rate_limit('192.168.1.1')
            
        self.assertFalse(allowed)
        self.assertEqual(current, 6)
        self.assertEqual(remaining, 0)
    
    def test_bypass_key_functionality(self):
        """Test bypass key bypasses rate limiting"""
        self.mock_redis.exists.return_value = True  # Bypass key exists
        
        with self.app_module.app.test_request_context(
            headers={'X-Bypass-Key': 'test_bypass_key'}
        ):
            allowed, current, remaining = self.app_module.check_rate_limit('192.168.1.1')
            
        self.assertTrue(allowed)
        self.assertEqual(current, 0)
        self.assertEqual(remaining, 5)
        self.mock_redis.exists.assert_called_with('bp:test_bypass_key')

class TestVideoIdExtraction(unittest.TestCase):
    """Test YouTube video ID extraction"""
    
    def setUp(self):
        """Set up test environment"""
        import app
        self.app_module = app
    
    def test_youtube_watch_url(self):
        """Test standard YouTube watch URL"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        video_id = self.app_module.extract_video_id(url)
        self.assertEqual(video_id, "dQw4w9WgXcQ")
    
    def test_youtube_short_url(self):
        """Test YouTube short URL (youtu.be)"""
        url = "https://youtu.be/dQw4w9WgXcQ"
        video_id = self.app_module.extract_video_id(url)
        self.assertEqual(video_id, "dQw4w9WgXcQ")
    
    def test_youtube_embed_url(self):
        """Test YouTube embed URL"""
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        video_id = self.app_module.extract_video_id(url)
        self.assertEqual(video_id, "dQw4w9WgXcQ")
    
    def test_youtube_url_with_parameters(self):
        """Test YouTube URL with additional parameters"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PLrAXtmRdnEQy"
        video_id = self.app_module.extract_video_id(url)
        self.assertEqual(video_id, "dQw4w9WgXcQ")
    
    def test_invalid_url(self):
        """Test invalid URL returns None"""
        url = "https://example.com/invalid"
        video_id = self.app_module.extract_video_id(url)
        self.assertIsNone(video_id)
    
    def test_malformed_youtube_url(self):
        """Test malformed YouTube URL"""
        url = "https://youtube.com/watch?invalid=123"
        video_id = self.app_module.extract_video_id(url)
        self.assertIsNone(video_id)

class TestWebshareProxyConfig(unittest.TestCase):
    """Test Webshare proxy configuration"""
    
    def setUp(self):
        """Set up test environment"""
        import app
        self.app_module = app
    
    @patch.dict(os.environ, {
        'WEBSHARE_USERNAME': 'test_user',
        'WEBSHARE_PASSWORD': 'test_pass',
        'WEBSHARE_COUNTRIES': 'us,de'
    })
    def test_webshare_config_with_countries(self):
        """Test Webshare config with country filtering"""
        config = self.app_module.get_webshare_proxy_config()
        self.assertIsNotNone(config)
        self.assertEqual(config.proxy_username, 'test_user')
        self.assertEqual(config.proxy_password, 'test_pass')
    
    @patch.dict(os.environ, {
        'WEBSHARE_USERNAME': 'test_user',
        'WEBSHARE_PASSWORD': 'test_pass'
    }, clear=True)
    def test_webshare_config_no_countries(self):
        """Test Webshare config without country filtering"""
        config = self.app_module.get_webshare_proxy_config()
        self.assertIsNotNone(config)
        self.assertEqual(config.proxy_username, 'test_user')
        self.assertEqual(config.proxy_password, 'test_pass')
    
    @patch.dict(os.environ, {}, clear=True)
    def test_webshare_config_missing_credentials(self):
        """Test Webshare config with missing credentials"""
        config = self.app_module.get_webshare_proxy_config()
        self.assertIsNone(config)

class TestAPIEndpoints(unittest.TestCase):
    """Test API endpoints"""
    
    def setUp(self):
        """Set up test environment"""
        with patch.dict(os.environ, {
            'REDIS_URL': 'redis://localhost:6379',
            'DAILY_LIMIT': '5',
            'ADMIN_TOKEN': 'test_token'
        }):
            import app
            self.app_module = app
            self.app = app.app.test_client()
            self.app_module.redis_client = Mock()
    
    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('redis_connected', data)
        self.assertIn('rate_limiting_enabled', data)
        self.assertIn('daily_limit', data)
    
    def test_proxy_status_endpoint(self):
        """Test proxy status endpoint"""
        response = self.app.get('/proxy_status')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn('proxy_enabled', data)
        self.assertIn('countries', data)
    
    @patch.dict(os.environ, {'ADMIN_TOKEN': 'test_token'})
    def test_admin_issue_bypass_unauthorized(self):
        """Test admin bypass endpoint without token"""
        response = self.app.post('/admin/issue_bypass')
        self.assertEqual(response.status_code, 401)
    
    @patch.dict(os.environ, {'ADMIN_TOKEN': 'test_token'})
    def test_admin_issue_bypass_authorized(self):
        """Test admin bypass endpoint with valid token"""
        self.app_module.redis_client.setex.return_value = True
        
        response = self.app.post('/admin/issue_bypass', 
                               headers={'X-Admin-Token': 'test_token'},
                               json={'ttl_hours': 6})
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('bypass_key', data)
        self.assertIn('expires_at', data)
    
    def test_get_transcript_invalid_url(self):
        """Test transcript endpoint with invalid URL"""
        response = self.app.post('/get_transcript', 
                               json={'url': 'invalid-url'})
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertIn('error', data)
        self.assertIn('Invalid YouTube URL', data['error'])
    
    def test_get_transcript_missing_url(self):
        """Test transcript endpoint with missing URL"""
        response = self.app.post('/get_transcript', json={})
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertIn('error', data)

class TestSummarizationEndpoint(unittest.TestCase):
    """Test summarization functionality"""
    
    def setUp(self):
        """Set up test environment"""
        with patch.dict(os.environ, {
            'REDIS_URL': 'redis://localhost:6379',
            'DAILY_LIMIT': '5',
            'ADMIN_TOKEN': 'test_token',
            'OPENAI_API_KEY': 'test_openai_key'
        }):
            import app
            self.app_module = app
            self.app = app.app.test_client()
            self.app_module.redis_client = Mock()
            
            # Mock OpenAI client
            self.mock_openai = Mock()
            self.app_module.openai_client = self.mock_openai
    
    def test_summarize_missing_text(self):
        """Test summarization endpoint with missing text"""
        response = self.app.post('/summarize_transcript', json={})
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertIn('error', data)
        self.assertIn('Please provide transcript text', data['error'])
    
    def test_summarize_empty_text(self):
        """Test summarization endpoint with empty text"""
        response = self.app.post('/summarize_transcript', json={'text': ''})
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertIn('error', data)
    
    def test_summarize_no_openai_client(self):
        """Test summarization when OpenAI client is not available"""
        self.app_module.openai_client = None
        
        response = self.app.post('/summarize_transcript', json={'text': 'Test transcript'})
        self.assertEqual(response.status_code, 503)
        
        data = json.loads(response.data)
        self.assertIn('OpenAI summarization not available', data['error'])
    
    @patch('app.openai_client')
    def test_summarize_success(self, mock_openai_instance):
        """Test successful summarization"""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "This is a test summary"
        mock_response.usage.total_tokens = 150
        
        mock_openai_instance.chat.completions.create.return_value = mock_response
        self.app_module.openai_client = mock_openai_instance
        
        response = self.app.post('/summarize_transcript', 
                               json={'text': 'This is a test transcript about testing.'})
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['summary'], "This is a test summary")
        self.assertEqual(data['model_used'], 'gpt-4o-mini')
        self.assertEqual(data['tokens_used'], 150)
    
    @patch('app.openai_client')
    def test_summarize_openai_error(self, mock_openai_instance):
        """Test OpenAI API error handling"""
        mock_openai_instance.chat.completions.create.side_effect = Exception("API Error")
        self.app_module.openai_client = mock_openai_instance
        
        response = self.app.post('/summarize_transcript', 
                               json={'text': 'Test transcript'})
        self.assertEqual(response.status_code, 500)
        
        data = json.loads(response.data)
        self.assertIn('OpenAI API error', data['error'])
    
    def test_summarize_text_truncation(self):
        """Test that very long text gets truncated"""
        # Create text longer than max_chars (30000)
        long_text = "A" * 35000
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Summary of truncated text"
        mock_response.usage.total_tokens = 100
        
        self.mock_openai.chat.completions.create.return_value = mock_response
        
        response = self.app.post('/summarize_transcript', json={'text': long_text})
        self.assertEqual(response.status_code, 200)
        
        # Verify OpenAI was called with truncated text
        call_args = self.mock_openai.chat.completions.create.call_args
        messages = call_args[1]['messages']
        user_message = messages[1]['content']
        
        # Should include truncation indicator
        self.assertIn('...', user_message)
        # Should be shorter than original
        self.assertLess(len(user_message), len(long_text))

class TestRateLimitMiddleware(unittest.TestCase):
    """Test rate limiting middleware"""
    
    def setUp(self):
        """Set up test environment"""
        with patch.dict(os.environ, {
            'REDIS_URL': 'redis://localhost:6379',
            'DAILY_LIMIT': '2',  # Low limit for testing
            'ADMIN_TOKEN': 'test_token'
        }):
            import app
            self.app_module = app
            self.app = app.app.test_client()
            self.app_module.redis_client = Mock()
    
    def test_rate_limit_middleware_skips_non_transcript_endpoints(self):
        """Test middleware skips non-transcript endpoints"""
        # Health endpoint should not be rate limited
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        
        # Proxy status should not be rate limited
        response = self.app.get('/proxy_status')
        self.assertEqual(response.status_code, 200)
    
    @patch('app.check_rate_limit')
    def test_rate_limit_middleware_applies_to_transcript(self, mock_check):
        """Test middleware applies to transcript endpoint"""
        # Mock rate limit check to allow request
        mock_check.return_value = (True, 1, 4)
        
        # This will fail due to missing transcript API, but middleware should be called
        response = self.app.post('/get_transcript', json={'url': 'https://youtube.com/watch?v=test123'})
        
        # Should have called rate limit check
        mock_check.assert_called_once()
    
    @patch('app.check_rate_limit')
    def test_rate_limit_middleware_applies_to_summarize(self, mock_check):
        """Test middleware applies to summarize endpoint"""
        # Mock rate limit check to allow request
        mock_check.return_value = (True, 1, 4)
        
        # This will fail due to missing OpenAI client, but middleware should be called
        response = self.app.post('/summarize_transcript', json={'text': 'test'})
        
        # Should have called rate limit check
        mock_check.assert_called_once()
    
    @patch('app.check_rate_limit')
    def test_rate_limit_middleware_blocks_exceeded(self, mock_check):
        """Test middleware blocks when rate limit exceeded"""
        # Mock rate limit check to deny request
        mock_check.return_value = (False, 6, 0)
        
        response = self.app.post('/get_transcript', json={'url': 'https://youtube.com/watch?v=test123'})
        self.assertEqual(response.status_code, 429)
        
        data = json.loads(response.data)
        self.assertIn('Rate limit exceeded', data['error'])

if __name__ == '__main__':
    # Run all tests with detailed output
    unittest.main(verbosity=2, exit=False)
    
    # Alternative: Run specific test suites
    # python -m unittest test_unit.TestRateLimiting -v
    # python -m unittest test_unit.TestVideoIdExtraction -v