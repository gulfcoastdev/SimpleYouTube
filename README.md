# YouTube Transcript Extractor

A web application that extracts transcripts from YouTube videos using the youtube-transcript-api with optional proxy support via Webshare.

## Features

- Extract transcripts from YouTube videos by URL
- Support for various YouTube URL formats
- Copy transcript to clipboard
- Clear transcript functionality
- Webshare proxy integration for enhanced reliability
- Responsive web interface
- Heroku deployment ready

## Setup

### Local Development

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) Configure proxy by copying `.env.example` to `.env` and filling in your Webshare credentials
4. Run the application:
   ```bash
   python app.py
   ```

### Heroku Deployment

1. Create a new Heroku app
2. Connect your repository
3. (Optional) Set environment variables in Heroku dashboard:
   - `WEBSHARE_USERNAME`
   - `WEBSHARE_PASSWORD` 
   - `WEBSHARE_ENDPOINT`
4. Deploy the app

## Environment Variables

- `WEBSHARE_USERNAME`: Your Webshare proxy username
- `WEBSHARE_PASSWORD`: Your Webshare proxy password
- `WEBSHARE_ENDPOINT`: Webshare proxy endpoint (e.g., proxy.webshare.io:80)
- `PORT`: Port number (automatically set by Heroku)

## Security

Passwords and credentials are handled securely using environment variables. Never commit sensitive information to the repository.

## Usage

1. Enter a YouTube video URL in the input field
2. Click "Extract Transcript" 
3. Use "Copy" to copy the transcript to clipboard
4. Use "Clear" to clear the current transcript and start over