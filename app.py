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


@app.route('/api/debug-playlist', methods=['POST', 'OPTIONS'])
def debug_playlist():
    """Debug endpoint to see raw Spotify data"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        spotify_url = data.get('url')
        
        if not spotify_url:
            return jsonify({'error': 'No Spotify URL provided'}), 400
        
        # Extract playlist ID
        playlist_id_match = re.search(r'playlist/([a-zA-Z0-9]+)', spotify_url)
        if not playlist_id_match:
            return jsonify({'error': 'Invalid Spotify playlist URL'}), 400
        
        playlist_id = playlist_id_match.group(1)
        
        # Scrape embed page
        import requests
        from bs4 import BeautifulSoup
        import json
        
        embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
        response = requests.get(embed_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        soup = BeautifulSoup(response.text, 'html.parser')
        script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
        
        if not script_tag:
            return jsonify({'error': 'Could not parse playlist data'}), 400
        
        playlist_data = json.loads(script_tag.string)
        entity = playlist_data['props']['pageProps']['state']['data']['entity']
        
        # Return RAW data for inspection
        return jsonify({
            'entity_keys': list(entity.keys()),
            'subtitle': entity.get('subtitle'),
            'ownerV2': entity.get('ownerV2'),
            'owner': entity.get('owner'),
            'first_track': entity.get('trackList', [])[0] if entity.get('trackList') else None,
            'first_track_keys': list(entity.get('trackList', [])[0].keys()) if entity.get('trackList') else None,
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
@app.route('/api/playlist', methods=['POST', 'OPTIONS'])
def import_playlist():
    """Import Spotify playlist - FAST version for free tier"""
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
        
        # Fetch playlist embed page
        import requests
        from bs4 import BeautifulSoup
        import json
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
        print(f"🌐 Fetching playlist: {embed_url}")
        
        response = requests.get(embed_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }, timeout=10)
        
        if response.status_code != 200:
            return jsonify({'error': f'Failed to fetch playlist: {response.status_code}'}), 400
        
        soup = BeautifulSoup(response.text, 'html.parser')
        script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
        
        if not script_tag:
            return jsonify({'error': 'Could not parse playlist data'}), 400
        
        page_data = json.loads(script_tag.string)
        entity = page_data['props']['pageProps']['state']['data']['entity']
        
        # Extract metadata
        playlist_name = entity.get('name', 'Unknown Playlist')
        playlist_description = entity.get('description')
        owner_name = entity.get('subtitle', 'Spotify User').strip() or 'Spotify User'
        
        print(f"📋 Playlist: {playlist_name}")
        print(f"👤 Owner: {owner_name}")
        
        # Playlist cover
        cover_art = entity.get('coverArt', {})
        sources = cover_art.get('sources', [])
        cover_image_url = sources[-1].get('url') if sources else None
        
        # Extract tracks
        track_list = entity.get('trackList', [])
        print(f"📝 Found {len(track_list)} tracks")
        
        tracks = []
        for track_data in track_list:
            track_title = track_data.get('title', 'Unknown')
            subtitle = track_data.get('subtitle', '')
            track_artists = [a.strip() for a in subtitle.split(',')] if subtitle else ['Unknown Artist']
            
            tracks.append({
                'title': track_title,
                'artists': track_artists,
                'albumArt': cover_image_url,  # Use playlist cover for all tracks
            })
        
        # Convert to YouTube IDs in parallel
        print(f"\n🔍 Converting {len(tracks)} tracks to YouTube IDs...\n")
        
        def fetch_youtube_id(track_info):
            """Fetch YouTube ID for a single track"""
            try:
                query = f"{' '.join(track_info['artists'])} {track_info['title']} official audio"
                
                with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                    info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                    
                    if info and 'entries' in info and len(info['entries']) > 0:
                        video = info['entries'][0]
                        return {
                            'youtubeId': video.get('id'),
                            'youtubeTitle': video.get('title'),
                            'duration': video.get('duration'),
                            'success': True,
                        }
                    return {'youtubeId': None, 'success': False, 'error': 'No results'}
            except Exception as e:
                return {'youtubeId': None, 'success': False, 'error': str(e)}
        
        # Parallel YouTube search
        youtube_results = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(fetch_youtube_id, track) for track in tracks]
            youtube_results = [f.result() for f in futures]
        
        # Combine results
        results = []
        for i, track in enumerate(tracks):
            yt_data = youtube_results[i]
            results.append({
                'title': track['title'],
                'artists': track['artists'],
                'youtubeId': yt_data.get('youtubeId'),
                'youtubeTitle': yt_data.get('youtubeTitle'),
                'duration': yt_data.get('duration'),
                'albumArt': track['albumArt'],
                'success': yt_data.get('success', False),
            })
        
        successful = sum(1 for r in results if r['success'])
        print(f"✅ Complete: {successful}/{len(tracks)} tracks")
        
        return jsonify({
            'playlist': {
                'name': playlist_name,
                'id': playlist_id,
                'description': playlist_description,
                'coverImageUrl': cover_image_url,
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