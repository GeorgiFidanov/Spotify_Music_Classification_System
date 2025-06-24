# Spotify Music Classification System

An interactive web application that visualizes and clusters your Spotify playlists using machine learning, with a modern, user-friendly interface.

## Features

- Spotify authentication and secure data retrieval
- Playlist-centric workflow: select a playlist, then analyze its tracks
- Machine learning-based song clustering (robust to missing audio features)
- Interactive tree and cluster summaries using D3.js
- Automatic playlist generation from clusters
- Responsive, modern login and UI
- Graceful handling of missing data (user-friendly messages if clustering is not possible)

## Setup

1. **Create a Spotify Developer account** and register a new application at https://developer.spotify.com/dashboard
2. **Set up environment variables:**
   ```
   SPOTIFY_CLIENT_ID=your_client_id
   SPOTIFY_CLIENT_SECRET=your_client_secret
   SPOTIFY_REDIRECT_URI=http://localhost:8000/callback
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Run the application:**
   ```bash
   uvicorn app.main:app --reload
   ```

## User Flow

1. **Login with Spotify:**
   - The user is greeted with a modern, centered login screen.
   - After login, only playlist names/IDs are loaded.
2. **Select a Playlist:**
   - The user selects a playlist from a dropdown.
   - Only the names and IDs of tracks in the playlist are fetched initially.
3. **Analyze Playlist:**
   - When the user clicks "Analyze Playlist," the app fetches track features and performs clustering (if possible).
   - If audio features are missing/disabled, the UI shows a clear message and does not attempt clustering.
4. **View Results:**
   - Cluster summaries and (if available) a tree visualization are shown.
   - The user can create a new playlist from a cluster.

## API Endpoints

- `GET /api/spotify/user-playlists` — List user's playlists (name, id)
- `GET /api/spotify/playlist-tracks/{playlist_id}` — List tracks (id, name, artists, album) for a playlist
- `POST /api/spotify/playlist-cluster/{playlist_id}` — Cluster tracks for a playlist (returns summaries, robust to missing features)
- `POST /api/playlist/create` — Create a new playlist from a cluster

## Project Structure

- `app/` — Main application directory
  - `main.py` — FastAPI application entry point and API
  - `spotify/` — Spotify API integration
  - `ml/` — Machine learning and clustering logic
  - `static/` — Static files (CSS, JS, D3)
  - `templates/` — HTML templates

## Technologies Used

- Backend: FastAPI
- Frontend: Plain JavaScript + D3.js
- ML: Scikit-learn, UMAP
- Authentication: OAuth2 (Spotify)
- Data Processing: Pandas, NumPy 