import os
import sys
import json
import requests
import random
import webbrowser
from threading import Timer
from flask import Flask, render_template, jsonify, request, Response, stream_with_context
from ytmusicapi import YTMusic
from yt_dlp import YoutubeDL
from flask_cors import CORS

# --- 1. RESOURCE HELPER (Crucial for .exe) ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

app = Flask(__name__, 
            template_folder=resource_path('templates'), 
            static_folder=resource_path('static'))
CORS(app)

# --- 2. LOCAL DATABASE (user_data.json) ---
# We store the file in the user's home folder so it persists even if they move the exe
USER_HOME = os.path.expanduser("~")
DATA_FILE = os.path.join(USER_HOME, 'neon_pulse_data.json')

def get_db():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump({'liked': [], 'playlists': {}}, f)
    try:
        with open(DATA_FILE, 'r') as f: return json.load(f)
    except: return {'liked': [], 'playlists': {}}

def save_db(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f, indent=4)

# --- 3. API SETUP ---
yt = YTMusic()

def parse_tracks(raw_list):
    cleaned = []
    for t in raw_list:
        if 'videoId' not in t: continue
        thumb = 'https://via.placeholder.com/200?text=NO_IMG'
        if 'thumbnails' in t and t['thumbnails']: thumb = t['thumbnails'][-1]['url']
        elif 'thumbnail' in t and t['thumbnail']: thumb = t['thumbnail'][-1]['url']
        
        artist = "Unknown"
        if 'artists' in t and t['artists']: artist = t['artists'][0]['name']
        
        cleaned.append({
            'id': t['videoId'],
            'title': t['title'],
            'artist': artist,
            'thumb': thumb,
            'duration': t.get('duration', '0:00')
        })
    return cleaned

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/home')
def home():
    genres = ["Cyberpunk", "Synthwave", "Phonk", "Dark Techno", "Future Garage"]
    try:
        results = yt.search(random.choice(genres), filter="songs")
        return jsonify(parse_tracks(results[:12]))
    except: return jsonify([])

@app.route('/api/search')
def search():
    try:
        results = yt.search(request.args.get('q'), filter="songs")
        return jsonify(parse_tracks(results[:20]))
    except: return jsonify([])

@app.route('/api/recommend')
def recommend():
    try:
        watch = yt.get_watch_playlist(videoId=request.args.get('id'), limit=10)
        return jsonify(parse_tracks(watch.get('tracks', [])))
    except: return jsonify([])

# --- STREAMING (Standard Local Mode) ---
@app.route('/api/play_proxy')
def play_proxy():
    vid = request.args.get('id')
    try:
        # Since this runs on the User's PC, we don't need proxies or cookies usually!
        opts = {'format': 'bestaudio[ext=m4a]/best', 'quiet': True}
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            url = info['url']
            
        req = requests.get(url, stream=True)
        return Response(stream_with_context(req.iter_content(chunk_size=1024*1024)), 
                        content_type=req.headers.get('content-type', 'audio/mp4'))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/lyrics')
def lyrics():
    try:
        watch = yt.get_watch_playlist(videoId=request.args.get('id'))
        if 'lyrics' in watch and watch['lyrics']:
            return jsonify({'lyrics': yt.get_lyrics(watch['lyrics'])['lyrics']})
    except: pass
    return jsonify({'lyrics': 'LYRICS_UNAVAILABLE'})

# --- LOCAL LIBRARY ROUTES ---
@app.route('/api/library')
def library(): 
    db = get_db()
    # Format it exactly how your frontend expects it
    return jsonify({'liked': db.get('liked', []), 'playlists': db.get('playlists', {})})

@app.route('/api/like', methods=['POST'])
def like():
    track = request.json
    db = get_db()
    
    # Check if already liked
    existing_index = next((index for (index, d) in enumerate(db['liked']) if d["id"] == track["id"]), None)
    
    status = 'liked'
    if existing_index is not None:
        db['liked'].pop(existing_index)
        status = 'unliked'
    else:
        db['liked'].append(track)
        
    save_db(db)
    # Return full DB object to update frontend
    return jsonify({'status': status, 'db': db['liked']})

@app.route('/api/playlist/create', methods=['POST'])
def create_pl():
    name = request.json.get('name')
    db = get_db()
    if name not in db['playlists']:
        db['playlists'][name] = []
        save_db(db)
    return jsonify({'status': 'ok'})

@app.route('/api/playlist/delete_all', methods=['POST'])
def delete_pl():
    name = request.json.get('name')
    db = get_db()
    if name in db['playlists']:
        del db['playlists'][name]
        save_db(db)
    return jsonify({'status': 'deleted'})

@app.route('/api/playlist/add', methods=['POST'])
def add_pl():
    data = request.json
    name = data.get('name')
    track = data.get('track')
    db = get_db()
    if name in db['playlists']:
        if not any(t['id'] == track['id'] for t in db['playlists'][name]):
            db['playlists'][name].append(track)
            save_db(db)
    return jsonify({'status': 'ok'})

@app.route('/api/playlist/remove', methods=['POST'])
def remove_pl():
    data = request.json
    name = data.get('name')
    track_id = data.get('track_id')
    db = get_db()
    if name in db['playlists']:
        db['playlists'][name] = [t for t in db['playlists'][name] if t['id'] != track_id]
        save_db(db)
    return jsonify({'status': 'removed'})

# --- 4. AUTO-OPEN BROWSER ---
def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")

if __name__ == '__main__':
    # When you run the exe, this opens the window automatically
    Timer(1, open_browser).start()
    app.run(port=5000)