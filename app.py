import os
import re
import redis
import secrets
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Redis client initialization
redis_client = None
try:
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        redis_client = redis.from_url(redis_url, decode_responses=True)
        # Test connection
        redis_client.ping()
        print(f"✅ Redis connected: {redis_url[:20]}...")
    else:
        print("⚠️  No REDIS_URL found - rate limiting disabled")
except Exception as e:
    print(f"❌ Redis connection failed: {e}")
    redis_client = None

# Rate limiting configuration
DAILY_LIMIT = int(os.environ.get('DAILY_LIMIT', '5'))
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN')

def get_client_ip():
    """Extract real client IP from X-Forwarded-For header (Heroku) or fallback"""
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # Get leftmost IP (the real client IP)
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr

def get_rate_limit_key(ip):
    """Generate Redis key for daily rate limiting"""
    today = datetime.now(timezone.utc).strftime('%Y%m%d')
    return f"rl:ip:{ip}:{today}"

def get_bypass_key():
    """Check for bypass key in request headers"""
    return request.headers.get('X-Bypass-Key')

def check_rate_limit(ip):
    """Check and increment rate limit for IP"""
    if not redis_client:
        return True, 0, DAILY_LIMIT  # No Redis = no limiting
    
    # Check for bypass key first
    bypass_key = get_bypass_key()
    if bypass_key:
        bypass_exists = redis_client.exists(f"bp:{bypass_key}")
        if bypass_exists:
            return True, 0, DAILY_LIMIT  # Bypass active
    
    key = get_rate_limit_key(ip)
    
    try:
        # Increment counter
        current_count = redis_client.incr(key)
        
        # Set expiration to end of day (UTC midnight) if this is the first request
        if current_count == 1:
            # Calculate seconds until UTC midnight
            now = datetime.now(timezone.utc)
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            ttl = int((midnight - now).total_seconds())
            redis_client.expire(key, ttl)
        
        remaining = max(0, DAILY_LIMIT - current_count)
        rate_limited = current_count > DAILY_LIMIT
        
        return not rate_limited, current_count, remaining
        
    except Exception as e:
        print(f"Redis error during rate limiting: {e}")
        return True, 0, DAILY_LIMIT  # Fail open

def rate_limit_middleware():
    """Global rate limiting middleware"""
    # Skip rate limiting for certain endpoints
    if request.endpoint in ['health', 'admin_issue_bypass', 'admin_revoke_bypass']:
        return
    
    ip = get_client_ip()
    allowed, current_count, remaining = check_rate_limit(ip)
    
    if not allowed:
        # Calculate reset time (next UTC midnight)
        now = datetime.now(timezone.utc)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        reset_timestamp = int(midnight.timestamp())
        
        response = jsonify({
            'error': 'Rate limit exceeded',
            'message': f'Daily limit of {DAILY_LIMIT} requests exceeded. Try again tomorrow.',
            'retry_after': reset_timestamp
        })
        response.status_code = 429
        response.headers['X-RateLimit-Limit'] = str(DAILY_LIMIT)
        response.headers['X-RateLimit-Remaining'] = '0'
        response.headers['X-RateLimit-Reset'] = str(reset_timestamp)
        response.headers['Retry-After'] = str(int((midnight - now).total_seconds()))
        
        return response

def add_rate_limit_headers(response):
    """Add rate limit headers to successful responses"""
    if not redis_client or response.status_code >= 400:
        return response
        
    # Skip for bypassed requests
    bypass_key = get_bypass_key()
    if bypass_key and redis_client.exists(f"bp:{bypass_key}"):
        return response
    
    ip = get_client_ip()
    key = get_rate_limit_key(ip)
    
    try:
        current_count = redis_client.get(key) or 0
        current_count = int(current_count)
        remaining = max(0, DAILY_LIMIT - current_count)
        
        # Calculate reset time
        now = datetime.now(timezone.utc)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        reset_timestamp = int(midnight.timestamp())
        
        response.headers['X-RateLimit-Limit'] = str(DAILY_LIMIT)
        response.headers['X-RateLimit-Remaining'] = str(remaining)
        response.headers['X-RateLimit-Reset'] = str(reset_timestamp)
        
    except Exception as e:
        print(f"Error adding rate limit headers: {e}")
    
    return response

# Register middleware
app.before_request(rate_limit_middleware)
app.after_request(add_rate_limit_headers)

def extract_video_id(url):
    """Extract video ID from various YouTube URL formats"""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/.*[?&]v=([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_webshare_proxy_config():
    """Get Webshare proxy configuration from environment variables"""
    webshare_username = os.environ.get('WEBSHARE_USERNAME')
    webshare_password = os.environ.get('WEBSHARE_PASSWORD')
    webshare_countries = os.environ.get('WEBSHARE_COUNTRIES', '').strip()
    
    if all([webshare_username, webshare_password]):
        # Parse countries filter if provided (comma-separated)
        filter_countries = None
        if webshare_countries:
            filter_countries = [country.strip().lower() for country in webshare_countries.split(',')]
        
        config = WebshareProxyConfig(
            proxy_username=webshare_username,
            proxy_password=webshare_password
        )
        
        # Set filter_ip_locations if provided (this sets the private _filter_ip_locations attribute)
        if filter_countries:
            # Check if the constructor accepts filter_ip_locations
            try:
                config = WebshareProxyConfig(
                    proxy_username=webshare_username,
                    proxy_password=webshare_password,
                    filter_ip_locations=filter_countries
                )
            except TypeError:
                # If not supported, create without filtering
                config = WebshareProxyConfig(
                    proxy_username=webshare_username,
                    proxy_password=webshare_password
                )
        
        return config
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint (bypasses rate limiting)"""
    return jsonify({
        'status': 'healthy',
        'redis_connected': redis_client is not None,
        'rate_limiting_enabled': redis_client is not None,
        'daily_limit': DAILY_LIMIT
    })

@app.route('/proxy_status')
def proxy_status():
    """Get current proxy configuration status"""
    proxy_config = get_webshare_proxy_config()
    proxy_enabled = proxy_config is not None
    
    countries = []
    if proxy_config and hasattr(proxy_config, '_filter_ip_locations') and proxy_config._filter_ip_locations:
        countries = proxy_config._filter_ip_locations
    
    return jsonify({
        'proxy_enabled': proxy_enabled,
        'countries': countries
    })

@app.route('/admin/issue_bypass', methods=['POST'])
def admin_issue_bypass():
    """Admin endpoint to issue bypass keys"""
    if not ADMIN_TOKEN:
        return jsonify({'error': 'Admin functionality disabled'}), 503
    
    auth_token = request.headers.get('X-Admin-Token')
    if not auth_token or auth_token != ADMIN_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not redis_client:
        return jsonify({'error': 'Redis not available'}), 503
    
    try:
        # Generate secure bypass key
        bypass_key = secrets.token_urlsafe(32)
        
        # Get TTL from request (default 12 hours)
        data = request.get_json() or {}
        ttl_hours = data.get('ttl_hours', 12)
        ttl_seconds = ttl_hours * 3600
        
        # Store bypass key in Redis with expiration
        redis_key = f"bp:{bypass_key}"
        redis_client.setex(redis_key, ttl_seconds, "1")
        
        # Calculate expiration timestamp
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        
        return jsonify({
            'success': True,
            'bypass_key': bypass_key,
            'expires_at': expires_at.isoformat(),
            'ttl_seconds': ttl_seconds
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to issue bypass: {str(e)}'}), 500

@app.route('/admin/revoke_bypass', methods=['POST'])
def admin_revoke_bypass():
    """Admin endpoint to revoke bypass keys"""
    if not ADMIN_TOKEN:
        return jsonify({'error': 'Admin functionality disabled'}), 503
    
    auth_token = request.headers.get('X-Admin-Token')
    if not auth_token or auth_token != ADMIN_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not redis_client:
        return jsonify({'error': 'Redis not available'}), 503
    
    try:
        data = request.get_json() or {}
        bypass_key = data.get('bypass_key')
        
        if not bypass_key:
            return jsonify({'error': 'bypass_key required'}), 400
        
        # Delete bypass key from Redis
        redis_key = f"bp:{bypass_key}"
        deleted = redis_client.delete(redis_key)
        
        return jsonify({
            'success': True,
            'revoked': bool(deleted),
            'bypass_key': bypass_key
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to revoke bypass: {str(e)}'}), 500

@app.route('/admin/rate_limit_status')
def admin_rate_limit_status():
    """Admin endpoint to check rate limit status for an IP"""
    if not ADMIN_TOKEN:
        return jsonify({'error': 'Admin functionality disabled'}), 503
    
    auth_token = request.headers.get('X-Admin-Token')
    if not auth_token or auth_token != ADMIN_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not redis_client:
        return jsonify({'error': 'Redis not available'}), 503
    
    try:
        ip = request.args.get('ip')
        if not ip:
            return jsonify({'error': 'ip parameter required'}), 400
        
        key = get_rate_limit_key(ip)
        current_count = redis_client.get(key) or 0
        current_count = int(current_count)
        remaining = max(0, DAILY_LIMIT - current_count)
        
        # Get TTL
        ttl = redis_client.ttl(key)
        
        return jsonify({
            'ip': ip,
            'current_count': current_count,
            'daily_limit': DAILY_LIMIT,
            'remaining': remaining,
            'ttl_seconds': ttl,
            'rate_limited': current_count >= DAILY_LIMIT
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get status: {str(e)}'}), 500

@app.route('/get_transcript', methods=['POST'])
def get_transcript():
    try:
        data = request.get_json()
        youtube_url = data.get('url', '').strip()
        
        if not youtube_url:
            return jsonify({'error': 'Please provide a YouTube URL'}), 400
        
        video_id = extract_video_id(youtube_url)
        if not video_id:
            return jsonify({'error': 'Invalid YouTube URL'}), 400
        
        # Configure Webshare proxy if available
        proxy_config = get_webshare_proxy_config()
        proxy_enabled = proxy_config is not None
        countries = []
        if proxy_config and hasattr(proxy_config, '_filter_ip_locations') and proxy_config._filter_ip_locations:
            countries = proxy_config._filter_ip_locations
        
        # Get transcript using the correct API for version 1.2.2
        try:
            # Create YouTubeTranscriptApi instance with optional proxy
            if proxy_config:
                ytt_api = YouTubeTranscriptApi(proxy_config=proxy_config)
            else:
                ytt_api = YouTubeTranscriptApi()
            
            # Try to fetch transcript directly with language preferences
            try:
                fetched_transcript = ytt_api.fetch(video_id, languages=['en', 'en-US', 'en-GB'])
                transcript_list = fetched_transcript.snippets
            except:
                # If specific languages fail, try to get any available transcript
                transcript_list_obj = ytt_api.list(video_id)
                transcript = next(iter(transcript_list_obj))
                fetched_transcript = transcript.fetch()
                transcript_list = fetched_transcript.snippets
                
        except Exception as e:
            raise Exception(f"Could not retrieve transcript: {str(e)}")
        
        # Format transcript - transcript_list contains FetchedTranscriptSnippet objects
        formatted_transcript = []
        for entry in transcript_list:
            formatted_transcript.append({
                'start': entry.start,
                'duration': entry.duration,
                'text': entry.text
            })
        
        # Create full text version
        full_text = ' '.join([entry.text for entry in transcript_list])
        
        return jsonify({
            'success': True,
            'video_id': video_id,
            'transcript': formatted_transcript,
            'full_text': full_text,
            'proxy_enabled': proxy_enabled,
            'countries': countries
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)