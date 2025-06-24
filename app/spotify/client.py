import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from typing import List, Dict, Any, Tuple
import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class SpotifyClient:
    def __init__(self, access_token: str = None):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
        
        if access_token:
            self.sp = spotipy.Spotify(auth=access_token)
        else:
            self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope="user-library-read user-top-read playlist-modify-public user-read-recently-played"
            ))

    def get_user_data(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Get all required user data for clustering and visualization."""
        try:
            # Get recently played tracks
            recent_tracks = self.get_recent_tracks(limit=50)
            logger.info(f"Retrieved {len(recent_tracks)} recent tracks")
            
            # Get top tracks
            top_tracks = self.get_top_tracks(limit=50)
            logger.info(f"Retrieved {len(top_tracks)} top tracks")
            
            # Combine tracks and remove duplicates
            all_tracks = self._combine_tracks(recent_tracks, top_tracks)
            logger.info(f"Combined tracks: {len(all_tracks)} unique tracks")
            
            # Get track IDs
            track_ids = [track['track']['id'] for track in all_tracks]
            logger.info(f"Extracted {len(track_ids)} track IDs")
            
            # Get audio features
            audio_features = []  # Disabled
            logger.info(f"Audio features fetching is disabled, skipping.")
            
            # Get artist information
            artist_ids = self._extract_artist_ids(all_tracks)
            logger.info(f"Extracted {len(artist_ids)} unique artist IDs")
            artist_info = self.get_artist_info(artist_ids)
            
            # Create track dataframe
            track_df = self.get_track_dataframe(all_tracks)
            logger.info(f"Created track dataframe with {len(track_df)} rows")
            
            # Add audio features to track dataframe
            track_df = self._add_audio_features(track_df, audio_features)
            logger.info("Added audio features to dataframe")
            
            # Add artist genres to track dataframe
            track_df = self._add_artist_genres(track_df, artist_info)
            logger.info("Added artist genres to dataframe")
            
            # Add time-based features
            track_df = self._add_time_features(track_df)
            logger.info("Added time features to dataframe")
            
            # Create metadata dictionary
            metadata = {
                'total_tracks': len(track_df),
                'time_period': {
                    'start': track_df['played_at'].min(),
                    'end': track_df['played_at'].max()
                },
                'genres': self._get_genre_distribution(track_df),
                'mood_distribution': self._get_mood_distribution(track_df)
            }
            
            return track_df, metadata
            
        except Exception as e:
            logger.error(f"Error getting user data: {str(e)}")
            logger.exception("Full traceback:")
            raise

    def _combine_tracks(self, recent_tracks: List[Dict], top_tracks: List[Dict]) -> List[Dict]:
        """Combine recent and top tracks, removing duplicates."""
        seen_ids = set()
        combined = []
        
        for track in recent_tracks + top_tracks:
            if not isinstance(track, dict) or 'track' not in track:
                logger.warning(f"Skipping invalid track data: {track}")
                continue
                
            track_id = track['track']['id']
            if track_id not in seen_ids:
                seen_ids.add(track_id)
                combined.append(track)
        
        return combined

    def _extract_artist_ids(self, tracks: List[Dict]) -> List[str]:
        """Extract unique artist IDs from tracks."""
        artist_ids = set()
        for track in tracks:
            if not isinstance(track, dict) or 'track' not in track:
                continue
            for artist in track['track']['artists']:
                artist_ids.add(artist['id'])
        return list(artist_ids)

    def get_artist_info(self, artist_ids: List[str]) -> Dict[str, Dict]:
        """Get detailed information about artists."""
        artist_info = {}
        for i in range(0, len(artist_ids), 50):
            batch = artist_ids[i:i + 50]
            results = self.sp.artists(batch)
            for artist in results['artists']:
                artist_info[artist['id']] = {
                    'name': artist['name'],
                    'genres': artist['genres'],
                    'popularity': artist['popularity']
                }
        return artist_info

    def _add_audio_features(self, df: pd.DataFrame, features: List[Dict]) -> pd.DataFrame:
        """Add audio features to the track dataframe."""
        if not features:
            logger.warning("No audio features provided")
            return df
            
        feature_df = pd.DataFrame(features)
        if 'id' not in feature_df.columns:
            logger.error("Audio features missing 'id' column")
            return df
            
        feature_df = feature_df.set_index('id')
        return df.join(feature_df, on='id')

    def _add_artist_genres(self, df: pd.DataFrame, artist_info: Dict[str, Dict]) -> pd.DataFrame:
        """Add artist genres to the track dataframe."""
        df['genres'] = df['artist_id'].apply(
            lambda x: artist_info.get(x, {}).get('genres', [])
        )
        return df

    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add time-based features to the track dataframe."""
        if 'played_at' not in df.columns:
            logger.warning("No 'played_at' column found, using current time")
            df['played_at'] = datetime.now()
            
        df['played_at'] = pd.to_datetime(df['played_at'])
        df['hour'] = df['played_at'].dt.hour
        df['day_of_week'] = df['played_at'].dt.day_name()
        df['is_weekend'] = df['played_at'].dt.dayofweek >= 5
        return df

    def _get_genre_distribution(self, df: pd.DataFrame) -> Dict[str, int]:
        """Get distribution of genres across tracks."""
        genre_counts = {}
        for genres in df['genres']:
            if isinstance(genres, list):
                for genre in genres:
                    genre_counts[genre] = genre_counts.get(genre, 0) + 1
        return dict(sorted(genre_counts.items(), key=lambda x: x[1], reverse=True))

    def _get_mood_distribution(self, df: pd.DataFrame) -> Dict[str, int]:
        """Get distribution of moods based on valence and energy."""
        def get_mood(valence: float, energy: float) -> str:
            if valence > 0.5:
                return "Happy" if energy > 0.5 else "Calm"
            return "Energetic" if energy > 0.5 else "Sad"
        
        if 'valence' not in df.columns or 'energy' not in df.columns:
            logger.warning("Missing valence or energy columns for mood calculation")
            return {}
            
        df['mood'] = df.apply(lambda x: get_mood(x['valence'], x['energy']), axis=1)
        return df['mood'].value_counts().to_dict()

    def get_recent_tracks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recently played tracks (only keep essential fields after fetch)."""
        try:
            results = self.sp.current_user_recently_played(limit=limit)
            items = results.get('items', [])
            filtered = []
            for item in items:
                track = item.get('track', {})
                artists = track.get('artists', [])
                artist_id = artists[0]['id'] if artists else None
                filtered.append({
                    'track': {
                        'id': track.get('id'),
                        'name': track.get('name'),
                        'artists': [{'id': a.get('id'), 'name': a.get('name')} for a in artists],
                        'artist_id': artist_id,
                        'album': {'name': track.get('album', {}).get('name')},
                        'popularity': track.get('popularity'),
                        'duration_ms': track.get('duration_ms')
                    },
                    'played_at': item.get('played_at')
                })
            return filtered
        except Exception as e:
            logger.error(f"Error getting recent tracks: {str(e)}")
            return []

    def get_top_tracks(self, limit: int = 50, time_range: str = 'medium_term') -> List[Dict[str, Any]]:
        """Get user's top tracks (only keep essential fields after fetch)."""
        try:
            results = self.sp.current_user_top_tracks(limit=limit, time_range=time_range)
            items = results.get('items', [])
            filtered = []
            for track in items:
                artists = track.get('artists', [])
                artist_id = artists[0]['id'] if artists else None
                filtered.append({
                    'track': {
                        'id': track.get('id'),
                        'name': track.get('name'),
                        'artists': [{'id': a.get('id'), 'name': a.get('name')} for a in artists],
                        'artist_id': artist_id,
                        'album': {'name': track.get('album', {}).get('name')},
                        'popularity': track.get('popularity'),
                        'duration_ms': track.get('duration_ms')
                    },
                    'played_at': None  # Top tracks don't have played_at
                })
            return filtered
        except Exception as e:
            logger.error(f"Error getting top tracks: {str(e)}")
            return []

    def get_audio_features(self, track_ids: List[str]) -> List[Dict[str, Any]]:
        """Get audio features for multiple tracks, with debug logging."""
        features = []
        try:
            # Log access token (partially masked for security)
            token_str = str(getattr(self.sp, '_auth', ''))
            logger.info(f"Access token (first 10 chars): {token_str[:10]}... | Total track IDs: {len(track_ids)}")
            for i in range(0, len(track_ids), 100):
                batch = track_ids[i:i + 100]
                logger.info(f"Requesting audio features for batch: {batch}")
                batch_features = self.sp.audio_features(batch)
                if batch_features:
                    features.extend(batch_features)
        except Exception as e:
            logger.error(f"Error getting audio features: {str(e)}")
        return features

    def create_playlist(self, name: str, description: str, track_ids: List[str]) -> str:
        """Create a new playlist and add tracks."""
        try:
            user_id = self.sp.current_user()['id']
            playlist = self.sp.user_playlist_create(
                user=user_id,
                name=name,
                description=description
            )
            
            # Add tracks in batches of 100
            for i in range(0, len(track_ids), 100):
                batch = track_ids[i:i + 100]
                self.sp.playlist_add_items(playlist['id'], batch)
            
            return playlist['id']
        except Exception as e:
            logger.error(f"Error creating playlist: {str(e)}")
            raise

    def get_track_dataframe(self, tracks: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert track data to a pandas DataFrame."""
        track_data = []
        for track in tracks:
            if not isinstance(track, dict) or 'track' not in track:
                continue
            track_info = track['track']
            track_data.append({
                'id': track_info.get('id'),
                'name': track_info.get('name'),
                'artist': track_info.get('artists', [{}])[0].get('name') if track_info.get('artists') else None,
                'artist_id': track_info.get('artist_id'),
                'album': track_info.get('album', {}).get('name'),
                'popularity': track_info.get('popularity'),
                'duration_ms': track_info.get('duration_ms'),
                'played_at': track.get('played_at', None)
            })
        return pd.DataFrame(track_data)

    def get_playlist_tracks(self, playlist_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get tracks from a playlist, only requesting essential fields from Spotify."""
        try:
            # Only fetch track name, artists, and album name
            fields = "items(track(id,name,artists(id,name),album(name))),next"
            results = self.sp.playlist_items(playlist_id, fields=fields, limit=limit, offset=offset)
            return results.get('items', [])
        except Exception as e:
            logger.error(f"Error getting playlist tracks: {str(e)}")
            return [] 