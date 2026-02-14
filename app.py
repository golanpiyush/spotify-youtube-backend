from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import re
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
CORS(app)  # Enable CORS for Flutter

# Configure yt-dlp options
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': True,  # Don't download, just get metadata
    'default_search': 'ytsearch1',  # Search YouTube and get first result
    'format': 'bestaudio/best',
}

def extract_video_id(url_or_id):
    """Extract YouTube video ID from various formats"""
    if len(url_or_id) == 11 and url_or_id.isalnum():
        return url_or_id
    
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    
    return None

@app.route('/')
def home():
    return jsonify({
        'status': 'API is running!',
        'version': '3.0 (yt-dlp)',
        'endpoints': {
            '/api/convert': 'POST - Convert tracks to YouTube IDs',
            '/api/playlist': 'POST - Import Spotify playlist and convert',
        }
    })

@app.route('/api/convert', methods=['POST', 'OPTIONS'])
def convert_tracks():
    """Convert tracks to YouTube video IDs"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        tracks = data.get('tracks', [])
        
        if not tracks:
            return jsonify({'error': 'No tracks provided'}), 400
        
        print(f"🔍 Converting {len(tracks)} tracks...")
        results = []
        
        for i, track in enumerate(tracks, 1):
            try:
                title = track.get('title', '')
                artists = track.get('artists', [])
                
                # Build search query
                query = f"{' '.join(artists)} {title} official audio"
                print(f"[{i}/{len(tracks)}] Searching: {query}")
                
                # Search YouTube using yt-dlp
                with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                    info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                    
                    if info and 'entries' in info and len(info['entries']) > 0:
                        video = info['entries'][0]
                        video_id = video.get('id')
                        
                        print(f"✅ Found: {video.get('title')} -> {video_id}")
                        
                        results.append({
                            'title': title,
                            'artists': artists,
                            'youtubeId': video_id,
                            'youtubeTitle': video.get('title'),
                            'duration': video.get('duration'),
                            'thumbnail': f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                            'success': True,
                        })
                    else:
                        print(f"❌ No results for: {title}")
                        results.append({
                            'title': title,
                            'artists': artists,
                            'youtubeId': None,
                            'success': False,
                            'error': 'No results found',
                        })
                        
            except Exception as e:
                print(f"❌ Error: {title} - {str(e)}")
                results.append({
                    'title': title,
                    'artists': artists,
                    'youtubeId': None,
                    'success': False,
                    'error': str(e),
                })
        
        successful = sum(1 for r in results if r['success'])
        print(f"🎉 Complete: {successful}/{len(tracks)}")
        
        return jsonify({
            'results': results,
            'summary': {
                'total': len(tracks),
                'successful': successful,
                'failed': len(tracks) - successful,
            }
        })
        
    except Exception as e:
        print(f"❌ Server error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlist', methods=['POST', 'OPTIONS'])
def import_playlist():
    """Import Spotify playlist with HQ album art for each track"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        spotify_url = data.get('url')
        
        if not spotify_url:
            return jsonify({'error': 'No Spotify URL provided'}), 400
        
        print(f"🎵 Importing playlist: {spotify_url}")
        
        # Extract playlist ID
        playlist_id_match = re.search(r'playlist/([a-zA-Z0-9]+)', spotify_url)
        if not playlist_id_match:
            return jsonify({'error': 'Invalid Spotify playlist URL'}), 400
        
        playlist_id = playlist_id_match.group(1)
        
        # Scrape Spotify embed page
        import requests
        from bs4 import BeautifulSoup
        import json
        
        embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
        response = requests.get(embed_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        if response.status_code != 200:
            return jsonify({'error': f'Failed to fetch playlist: {response.status_code}'}), 400
        
        # Parse JSON from __NEXT_DATA__
        soup = BeautifulSoup(response.text, 'html.parser')
        script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
        
        if not script_tag:
            return jsonify({'error': 'Could not parse playlist data'}), 400
        
        playlist_data = json.loads(script_tag.string)
        entity = playlist_data['props']['pageProps']['state']['data']['entity']
        
        # Extract playlist metadata
        playlist_name = entity.get('name', 'Unknown Playlist')
        playlist_description = entity.get('description')
        
        # Extract HQ playlist cover art
        cover_image_url = None
        cover_art = entity.get('coverArt', {})
        sources = cover_art.get('sources', [])
        if sources:
            # Get the LARGEST image (last in array)
            cover_image_url = sources[-1].get('url')
        
        print(f"🖼️ Playlist cover: {cover_image_url}")
        
        # Extract owner name with fallbacks
        owner_name = 'Spotify User'
        
        # Try subtitle field
        subtitle = entity.get('subtitle', '')
        if subtitle and ' · ' in subtitle:
            parts = subtitle.split(' · ')
            if len(parts) >= 2:
                owner_name = parts[1].strip()
        
        # Try ownerV2
        if owner_name == 'Spotify User':
            owner_v2 = entity.get('ownerV2', {})
            owner_data = owner_v2.get('data', {})
            if owner_data.get('name'):
                owner_name = owner_data['name']
        
        print(f"👤 Owner: {owner_name}")
        
        # Extract tracks with individual album art
        track_list = entity.get('trackList', [])
        print(f"📝 Found {len(track_list)} tracks")
        
        tracks = []
        for i, track in enumerate(track_list):
            track_title = track.get('title', 'Unknown')
            track_subtitle = track.get('subtitle', '')
            track_artists = [a.strip() for a in track_subtitle.split(',')] if track_subtitle else ['Unknown Artist']
            
            # Extract INDIVIDUAL track album art
            track_album_art = None
            track_image = track.get('image', {})
            track_image_sources = track_image.get('sources', [])
            if track_image_sources:
                # Get the LARGEST image for HQ quality
                track_album_art = track_image_sources[-1].get('url')
            
            print(f"  [{i+1}] {track_title}")
            print(f"      Album art: {track_album_art if track_album_art else 'None - will use playlist cover'}")
            
            tracks.append({
                'title': track_title,
                'artists': track_artists,
                'albumArt': track_album_art or cover_image_url,  # Fallback to playlist cover
            })
        
        # Convert to YouTube IDs
        results = []
        for i, track in enumerate(tracks, 1):
            try:
                query = f"{' '.join(track['artists'])} {track['title']} official audio"
                print(f"🔍 [{i}/{len(tracks)}] Searching: {query}")
                
                with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                    info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                    
                    if info and 'entries' in info and len(info['entries']) > 0:
                        video = info['entries'][0]
                        video_id = video.get('id')
                        
                        print(f"   ✅ Found: {video_id}")
                        
                        results.append({
                            'title': track['title'],
                            'artists': track['artists'],
                            'youtubeId': video_id,
                            'youtubeTitle': video.get('title'),
                            'duration': video.get('duration'),
                            'albumArt': track['albumArt'],  # Use Spotify album art, NOT YouTube thumbnail
                            'success': True,
                        })
                    else:
                        print(f"   ❌ No results")
                        results.append({
                            'title': track['title'],
                            'artists': track['artists'],
                            'youtubeId': None,
                            'albumArt': track['albumArt'],
                            'success': False,
                            'error': 'No results found',
                        })
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
                results.append({
                    'title': track['title'],
                    'artists': track['artists'],
                    'youtubeId': None,
                    'albumArt': track['albumArt'],
                    'success': False,
                    'error': str(e),
                })
        
        successful = sum(1 for r in results if r['success'])
        print(f"🎉 Complete: {successful}/{len(tracks)} tracks")
        
        return jsonify({
            'playlist': {
                'name': playlist_name,
                'id': playlist_id,
                'description': playlist_description,
                'coverImageUrl': cover_image_url,  # HQ playlist cover
                'ownerName': owner_name,
            },
            'results': results,
            'summary': {
                'total': len(tracks),
                'successful': successful,
                'failed': len(tracks) - successful,
            }
        })
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)