import os
import re
from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
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

def get_proxy_config():
    """Get proxy configuration from environment variables"""
    webshare_username = os.environ.get('WEBSHARE_USERNAME')
    webshare_password = os.environ.get('WEBSHARE_PASSWORD')
    webshare_endpoint = os.environ.get('WEBSHARE_ENDPOINT')
    
    if all([webshare_username, webshare_password, webshare_endpoint]):
        return {
            'http': f'http://{webshare_username}:{webshare_password}@{webshare_endpoint}',
            'https': f'http://{webshare_username}:{webshare_password}@{webshare_endpoint}'
        }
    return None

@app.route('/')
def index():
    return render_template('index.html')

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
        
        # Configure proxy if available
        proxy_config = get_proxy_config()
        if proxy_config:
            # Set proxy for requests (used by youtube-transcript-api)
            os.environ['HTTP_PROXY'] = proxy_config['http']
            os.environ['HTTPS_PROXY'] = proxy_config['https']
        
        # Get transcript
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        
        # Format transcript
        formatted_transcript = []
        for entry in transcript_list:
            formatted_transcript.append({
                'start': entry['start'],
                'duration': entry['duration'],
                'text': entry['text']
            })
        
        # Create full text version
        full_text = ' '.join([entry['text'] for entry in transcript_list])
        
        return jsonify({
            'success': True,
            'video_id': video_id,
            'transcript': formatted_transcript,
            'full_text': full_text
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)