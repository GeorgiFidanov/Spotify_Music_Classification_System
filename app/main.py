from fastapi import FastAPI, HTTPException, Request, Body, Depends, Path
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
from dotenv import load_dotenv
from urllib.parse import urlencode
import logging
import base64
import httpx
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from app.spotify.client import SpotifyClient
from app.ml.clustering import MusicClusterer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI(title="Spotify Music Classification System")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Spotify configuration
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SPOTIFY_SCOPES = [
    "user-library-read",
    "user-top-read",
    "playlist-modify-public",
    "user-read-recently-played"
]

# Validate configuration
if not SPOTIFY_CLIENT_ID:
    logger.error("SPOTIFY_CLIENT_ID is not set in environment variables")
if not SPOTIFY_CLIENT_SECRET:
    logger.error("SPOTIFY_CLIENT_SECRET is not set in environment variables")
if not SPOTIFY_REDIRECT_URI:
    logger.error("SPOTIFY_REDIRECT_URI is not set in environment variables")
    SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8000/callback"
    logger.info(f"Using default redirect URI: {SPOTIFY_REDIRECT_URI}")

class TokenRequest(BaseModel):
    code: str

class PlaylistRequest(BaseModel):
    cluster_id: int
    name: Optional[str] = None
    description: Optional[str] = None

def get_spotify_client(access_token: str) -> SpotifyClient:
    """Create a Spotify client instance with the given access token."""
    return SpotifyClient(access_token=access_token)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Render the main application page."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "spotify_config": {
            "client_id_set": bool(SPOTIFY_CLIENT_ID),
            "client_secret_set": bool(SPOTIFY_CLIENT_SECRET),
            "redirect_uri": SPOTIFY_REDIRECT_URI
        }
    }

@app.get("/api/spotify/auth-url")
async def get_spotify_auth_url():
    """Generate Spotify authorization URL."""
    if not SPOTIFY_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Spotify client ID not configured")
    
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": " ".join(SPOTIFY_SCOPES),
        "show_dialog": "true"
    }
    
    auth_url = f"https://accounts.spotify.com/authorize?{urlencode(params)}"
    logger.info(f"Generated auth URL with redirect URI: {SPOTIFY_REDIRECT_URI}")
    return {"auth_url": auth_url}

@app.post("/api/spotify/token")
async def exchange_token(token_request: TokenRequest):
    """Exchange authorization code for access token."""
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Spotify credentials not configured")

    # Create Basic Auth header
    auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_bytes = auth_string.encode('ascii')
    base64_auth = base64.b64encode(auth_bytes).decode('ascii')

    # Prepare token request
    token_url = "https://accounts.spotify.com/api/token"
    headers = {
        "Authorization": f"Basic {base64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "authorization_code",
        "code": token_request.code,
        "redirect_uri": SPOTIFY_REDIRECT_URI
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            logger.info("Successfully exchanged code for token")
            return token_data
    except httpx.HTTPError as e:
        logger.error(f"Error exchanging token: {str(e)}")
        if hasattr(e, 'response'):
            logger.error(f"Response content: {e.response.text}")
        raise HTTPException(status_code=500, detail="Failed to exchange authorization code")

@app.get("/api/user-data")
async def get_user_data(request: Request):
    """Get user's music data and create visualization tree."""
    try:
        # Get access token from request header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        
        access_token = auth_header.split(' ')[1]
        
        # Create Spotify client
        spotify_client = get_spotify_client(access_token)
        
        # Get user data
        track_df, metadata = spotify_client.get_user_data()
        
        # Create clusterer
        clusterer = MusicClusterer(n_clusters=5)
        
        # Perform clustering
        cluster_labels, cluster_metadata = clusterer.cluster_songs(track_df)
        
        # Get cluster summaries
        cluster_summaries = clusterer.get_cluster_summary(track_df, cluster_labels)
        if cluster_labels is None or len(cluster_labels) == 0:
            return {
                "tree": None,
                "metadata": metadata,
                "cluster_summaries": cluster_summaries,
                "message": "Clustering could not be performed due to missing audio features."
            }
        # Get cluster summaries
        # Create visualization tree
        tree = create_visualization_tree(track_df, cluster_labels, cluster_summaries)
        
        return {
            "tree": tree,
            "metadata": metadata,
            "cluster_summaries": cluster_summaries
        }
        
    except Exception as e:
        logger.error(f"Error getting user data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/playlist/create")
async def create_playlist(request: Request, playlist_request: PlaylistRequest):
    """Create a playlist from a cluster."""
    try:
        # Get access token from request header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        
        access_token = auth_header.split(' ')[1]
        
        # Create Spotify client
        spotify_client = get_spotify_client(access_token)
        
        # Get user data
        track_df, _ = spotify_client.get_user_data()
        
        # Create clusterer
        clusterer = MusicClusterer(n_clusters=5)
        
        # Perform clustering
        cluster_labels, _ = clusterer.cluster_songs(track_df)
        
        # Get tracks for the selected cluster
        cluster_tracks = track_df[cluster_labels == playlist_request.cluster_id]
        
        # Generate playlist name and description if not provided
        if not playlist_request.name:
            playlist_request.name = f"Cluster {playlist_request.cluster_id + 1} Playlist"
        if not playlist_request.description:
            playlist_request.description = f"Automatically generated playlist from cluster {playlist_request.cluster_id + 1}"
        
        # Create playlist
        playlist_id = spotify_client.create_playlist(
            name=playlist_request.name,
            description=playlist_request.description,
            track_ids=cluster_tracks['id'].tolist()
        )
        
        return {"playlist_id": playlist_id}
        
    except Exception as e:
        logger.error(f"Error creating playlist: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def create_visualization_tree(track_df, cluster_labels, cluster_summaries):
    """Create a tree structure for visualization."""
    # Create root node
    root = {
        "name": "My Music",
        "children": []
    }
    
    # Add clusters as children
    for i, summary in enumerate(cluster_summaries):
        cluster_tracks = track_df[cluster_labels == i]
        
        cluster_node = {
            "name": f"Cluster {i + 1}",
            "cluster_id": i,
            "size": summary["size"],
            "mood": summary["mood"],
            "avg_energy": summary["avg_energy"],
            "avg_valence": summary["avg_valence"],
            "children": []
        }
        
        # Add tracks as leaves
        for _, track in cluster_tracks.iterrows():
            track_node = {
                "name": track["name"],
                "artist": track["artist"],
                "id": track["id"],
                "popularity": track["popularity"],
                "energy": track["energy"],
                "valence": track["valence"]
            }
            cluster_node["children"].append(track_node)
        
        root["children"].append(cluster_node)
    
    return root

@app.get("/callback")
async def spotify_callback(request: Request):
    """Handle Spotify OAuth callback."""
    # Log the full URL for debugging
    logger.info(f"Callback received with URL: {request.url}")
    return templates.TemplateResponse(
        "callback.html",
        {"request": request}
    )

@app.get("/api/spotify/user-playlists")
async def get_user_playlists(request: Request):
    """Get the user's playlists (only name and id)."""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        access_token = auth_header.split(' ')[1]
        spotify_client = get_spotify_client(access_token)
        playlists = spotify_client.sp.current_user_playlists(limit=50)
        # Only keep name and id
        simple_playlists = [{
            'id': p['id'],
            'name': p['name']
        } for p in playlists.get('items', [])]
        return {'items': simple_playlists}
    except Exception as e:
        logger.error(f"Error getting user playlists: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/spotify/playlist-tracks/{playlist_id}")
async def get_playlist_tracks_api(request: Request, playlist_id: str = Path(...)):
    """Get all tracks (id, name, artists, album) for the selected playlist."""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        access_token = auth_header.split(' ')[1]
        spotify_client = get_spotify_client(access_token)
        # Fetch all tracks (id, name, artists, album)
        fields = "items(track(id,name,artists(id,name),album(name))),next"
        tracks = []
        next_url = None
        results = spotify_client.sp.playlist_items(playlist_id, fields=fields, limit=100)
        tracks.extend(results.get('items', []))
        next_url = results.get('next')
        # Paginate if needed
        while next_url:
            results = spotify_client.sp.next(results)
            tracks.extend(results.get('items', []))
            next_url = results.get('next')
        return {'items': tracks}
    except Exception as e:
        logger.error(f"Error getting playlist tracks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/spotify/playlist-cluster/{playlist_id}")
async def cluster_playlist(request: Request, playlist_id: str = Path(...)):
    """Cluster tracks for the selected playlist only."""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        access_token = auth_header.split(' ')[1]
        spotify_client = get_spotify_client(access_token)
        # Fetch all tracks for the playlist
        fields = "items(track(id,name,artists(id,name),album(name))),next"
        tracks = []
        next_url = None
        results = spotify_client.sp.playlist_items(playlist_id, fields=fields, limit=100)
        tracks.extend(results.get('items', []))
        next_url = results.get('next')
        while next_url:
            results = spotify_client.sp.next(results)
            tracks.extend(results.get('items', []))
            next_url = results.get('next')
        # Get track IDs
        track_ids = [t['track']['id'] for t in tracks if t.get('track') and t['track'].get('id')]
        # Get audio features
        audio_features = spotify_client.get_audio_features(track_ids)
        # Build DataFrame
        track_df = spotify_client.get_track_dataframe(tracks)
        track_df = spotify_client._add_audio_features(track_df, audio_features)
        # Cluster
        clusterer = MusicClusterer(n_clusters=5)
        cluster_labels, cluster_metadata = clusterer.cluster_songs(track_df)
        cluster_summaries = clusterer.get_cluster_summary(track_df, cluster_labels)
        
        if cluster_labels is None or len(cluster_labels) == 0:
            return {
                'cluster_labels': [],
                'cluster_summaries': cluster_summaries,
                'track_df': track_df.to_dict(orient='records'),
                'message': 'Clustering could not be performed due to missing audio features.'
            }
        # Optionally, build a visualization tree or return cluster info
        return {
            'cluster_labels': cluster_labels.tolist(),
            'cluster_summaries': cluster_summaries,
            'track_df': track_df.to_dict(orient='records')
        }
    except Exception as e:
        logger.error(f"Error clustering playlist: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server with redirect URI: {SPOTIFY_REDIRECT_URI}")
    uvicorn.run(app, host="127.0.0.1", port=8000) 