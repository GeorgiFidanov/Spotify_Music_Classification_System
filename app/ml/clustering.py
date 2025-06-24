import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
import umap
from typing import Dict, List, Tuple, Any

class MusicClusterer:
    def __init__(self, n_clusters: int = 5):
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=0.95)  # Keep 95% of variance
        self.umap = umap.UMAP(n_components=2, random_state=42)
        self.kmeans = KMeans(n_clusters=n_clusters, random_state=42)

    def prepare_features(self, features_df: pd.DataFrame) -> np.ndarray:
        """Prepare audio features for clustering."""
        # Select relevant features
        feature_columns = [
            'danceability', 'energy', 'valence', 'tempo',
            'acousticness', 'instrumentalness', 'liveness',
            'speechiness', 'loudness'
        ]
        # Check if all required columns are present
        missing = [col for col in feature_columns if col not in features_df.columns]
        if missing:
            import logging
            logging.warning(f"Clustering skipped: missing audio feature columns: {missing}")
            raise ValueError(f"Clustering cannot be performed: missing audio feature columns: {missing}")
        # Scale features
        scaled_features = self.scaler.fit_transform(features_df[feature_columns])
        # Reduce dimensionality
        reduced_features = self.pca.fit_transform(scaled_features)
        return reduced_features

    def cluster_songs(self, features_df: pd.DataFrame) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Cluster songs and return cluster assignments and metadata."""
        try:
            # Prepare features
            prepared_features = self.prepare_features(features_df)
            # Apply UMAP for visualization
            umap_features = self.umap.fit_transform(prepared_features)
            # Perform clustering
            cluster_labels = self.kmeans.fit_predict(prepared_features)
            # Calculate cluster centers
            cluster_centers = self.kmeans.cluster_centers_
            # Create cluster metadata
            cluster_metadata = {
                'cluster_centers': cluster_centers.tolist(),
                'umap_features': umap_features.tolist(),
                'feature_importance': dict(zip(
                    features_df.columns,
                    np.abs(self.pca.components_[0])
                ))
            }
            return cluster_labels, cluster_metadata
        except ValueError as e:
            import logging
            logging.warning(f"Clustering not performed: {e}")
            # Return empty results and a message
            return np.array([]), {'error': str(e)}

    def get_cluster_summary(self, features_df: pd.DataFrame, cluster_labels: np.ndarray) -> List[Dict[str, Any]]:
        """Generate summary statistics for each cluster."""
        if cluster_labels is None or len(cluster_labels) == 0:
            return [{
                'cluster_id': None,
                'size': 0,
                'avg_energy': None,
                'avg_valence': None,
                'avg_tempo': None,
                'avg_danceability': None,
                'mood': 'Clustering not performed: missing audio features'
            }]
        summaries = []
        for cluster_id in range(self.n_clusters):
            cluster_mask = cluster_labels == cluster_id
            cluster_features = features_df[cluster_mask]
            summary = {
                'cluster_id': int(cluster_id),
                'size': int(cluster_mask.sum()),
                'avg_energy': float(cluster_features['energy'].mean()),
                'avg_valence': float(cluster_features['valence'].mean()),
                'avg_tempo': float(cluster_features['tempo'].mean()),
                'avg_danceability': float(cluster_features['danceability'].mean()),
                'avg_acousticness': float(cluster_features['acousticness'].mean()),
                'mood': self._determine_mood(
                    cluster_features['valence'].mean(),
                    cluster_features['energy'].mean()
                )
            }
            summaries.append(summary)
        return summaries

    def _determine_mood(self, valence: float, energy: float) -> str:
        """Determine the mood based on valence and energy."""
        if valence > 0.5:
            if energy > 0.5:
                return "Happy & Energetic"
            else:
                return "Happy & Calm"
        else:
            if energy > 0.5:
                return "Sad & Energetic"
            else:
                return "Sad & Calm" 