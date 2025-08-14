import os
import re
from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
import requests

app = Flask(__name__)

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
        
        return WebshareProxyConfig(
            proxy_username=webshare_username,
            proxy_password=webshare_password,
            filter_ip_locations=filter_countries
        )
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/proxy_status')
def proxy_status():
    """Get current proxy configuration status"""
    proxy_config = get_webshare_proxy_config()
    proxy_enabled = proxy_config is not None
    
    countries = []
    if proxy_config and proxy_config.filter_ip_locations:
        countries = proxy_config.filter_ip_locations
    
    return jsonify({
        'proxy_enabled': proxy_enabled,
        'countries': countries
    })

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
        if proxy_config and proxy_config.filter_ip_locations:
            countries = proxy_config.filter_ip_locations
        
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