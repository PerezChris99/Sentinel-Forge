"""
Analytics Engine for SentinelForge
Phase 4: Pattern mining, anomaly detection, clustering, and bias auditing

Features:
- Isolation Forest for anomaly detection
- DBSCAN clustering for unknown embeddings
- Pattern extraction from temporal data
- Bias audit using LFW/RFW datasets
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """
    Core analytics engine for pattern detection and anomaly scoring.
    """

    def __init__(
        self,
        anomaly_contamination: float = 0.1,
        clustering_eps: float = 0.3,
        clustering_min_samples: int = 3,
        use_pca: bool = True,
        pca_components: int = 50,
    ):
        """
        Initialize analytics engine.

        Args:
            anomaly_contamination: Expected proportion of outliers (0.0-0.5)
            clustering_eps: DBSCAN epsilon (max distance between samples)
            clustering_min_samples: DBSCAN minimum samples per cluster
            use_pca: Whether to reduce embedding dimensions with PCA
            pca_components: Target dimensions for PCA (if use_pca=True)
        """
        self.contamination = anomaly_contamination
        self.eps = clustering_eps
        self.min_samples = clustering_min_samples
        self.use_pca = use_pca
        self.pca_components = pca_components

        # Models
        self.anomaly_detector: Optional[IsolationForest] = None
        self.scaler = StandardScaler()
        self.pca: Optional[PCA] = None

        logger.info(
            f"AnalyticsEngine initialized: contamination={anomaly_contamination}, "
            f"eps={clustering_eps}, PCA={use_pca}"
        )

    def extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract temporal and behavioral features from sightings data.

        Args:
            df: DataFrame with columns: person_id, timestamp, camera_id, confidence, flag_level

        Returns:
            DataFrame with engineered features
        """
        features = df.copy()

        # Temporal features
        features["hour"] = pd.to_datetime(features["timestamp"]).dt.hour
        features["day_of_week"] = pd.to_datetime(features["timestamp"]).dt.dayofweek
        features["is_weekend"] = features["day_of_week"].isin([5, 6]).astype(int)
        features["is_night"] = features["hour"].between(22, 6).astype(int)

        # Aggregated features per person
        person_stats = (
            features.groupby("person_id")
            .agg(
                {
                    "timestamp": "count",  # sighting_count
                    "confidence": ["mean", "std"],
                    "flag_level": "max",
                    "camera_id": "nunique",  # unique cameras
                }
            )
            .reset_index()
        )

        person_stats.columns = [
            "person_id",
            "sighting_count",
            "avg_confidence",
            "std_confidence",
            "max_flag_level",
            "unique_cameras",
        ]

        features = features.merge(person_stats, on="person_id", how="left")

        # Time since last sighting
        features = features.sort_values(["person_id", "timestamp"])
        features["time_since_last"] = features.groupby("person_id")["timestamp"].diff().dt.total_seconds()
        features["time_since_last"] = features["time_since_last"].fillna(0)

        return features

    def train_anomaly_detector(self, embeddings: np.ndarray) -> None:
        """
        Train Isolation Forest on embedding vectors.

        Args:
            embeddings: Array of shape (n_samples, embedding_dim)
        """
        if len(embeddings) < 10:
            logger.warning("Insufficient data for training anomaly detector (need ≥10 samples)")
            return

        # Apply PCA if enabled
        processed = embeddings
        if self.use_pca:
            self.pca = PCA(n_components=min(self.pca_components, embeddings.shape[1]))
            processed = self.pca.fit_transform(embeddings)
            logger.info(
                f"PCA reduced dimensions: {embeddings.shape[1]} → {processed.shape[1]} "
                f"(explained variance: {self.pca.explained_variance_ratio_.sum():.2%})"
            )

        # Scale features
        processed = self.scaler.fit_transform(processed)

        # Train Isolation Forest
        self.anomaly_detector = IsolationForest(
            contamination=self.contamination, random_state=42, n_jobs=-1
        )
        self.anomaly_detector.fit(processed)

        logger.info(f"Anomaly detector trained on {len(embeddings)} samples")

    def predict_anomaly_score(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Calculate anomaly scores for embeddings.

        Args:
            embeddings: Array of shape (n_samples, embedding_dim)

        Returns:
            Anomaly scores in range [0, 1], where higher = more anomalous
        """
        if self.anomaly_detector is None:
            logger.warning("Anomaly detector not trained, returning zeros")
            return np.zeros(len(embeddings))

        # Apply same preprocessing
        processed = embeddings
        if self.use_pca and self.pca is not None:
            processed = self.pca.transform(embeddings)
        processed = self.scaler.transform(processed)

        # Get raw scores and normalize to [0, 1]
        raw_scores = self.anomaly_detector.score_samples(processed)
        normalized = 1 - (raw_scores - raw_scores.min()) / (raw_scores.max() - raw_scores.min() + 1e-8)

        return normalized

    def cluster_unknowns(
        self, embeddings: np.ndarray, min_cluster_size: int = 3
    ) -> Tuple[np.ndarray, int, float]:
        """
        Cluster unknown embeddings using DBSCAN.

        Args:
            embeddings: Array of shape (n_samples, embedding_dim)
            min_cluster_size: Minimum samples to form a cluster

        Returns:
            Tuple of (cluster_labels, n_clusters, silhouette_score)
        """
        if len(embeddings) < min_cluster_size:
            logger.warning(f"Insufficient unknowns for clustering: {len(embeddings)} < {min_cluster_size}")
            return np.array([-1] * len(embeddings)), 0, 0.0

        # Apply PCA if enabled
        processed = embeddings
        if self.use_pca:
            if self.pca is None:
                self.pca = PCA(n_components=min(self.pca_components, embeddings.shape[1]))
                processed = self.pca.fit_transform(embeddings)
            else:
                processed = self.pca.transform(embeddings)

        # DBSCAN clustering
        clusterer = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric="cosine", n_jobs=-1)
        labels = clusterer.fit_predict(processed)

        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = list(labels).count(-1)

        # Calculate silhouette score (skip if too few clusters)
        silhouette = 0.0
        if n_clusters > 1:
            try:
                silhouette = silhouette_score(processed, labels, metric="cosine")
            except Exception as e:
                logger.warning(f"Silhouette score calculation failed: {e}")

        logger.info(
            f"DBSCAN clustering: {n_clusters} clusters, {n_noise} noise points, "
            f"silhouette={silhouette:.3f}"
        )

        return labels, n_clusters, silhouette

    def detect_patterns(
        self, df: pd.DataFrame, lookback_days: int = 30
    ) -> List[Dict]:
        """
        Detect behavioral patterns from sighting data.

        Args:
            df: Sightings DataFrame
            lookback_days: Number of days to analyze

        Returns:
            List of detected patterns with metadata
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        recent_df = df[pd.to_datetime(df["timestamp"]) >= cutoff].copy()

        if len(recent_df) < 10:
            logger.warning("Insufficient data for pattern detection")
            return []

        patterns = []

        # Pattern 1: Frequent visitors (>10 sightings in window)
        frequent = (
            recent_df.groupby("person_id")
            .size()
            .reset_index(name="count")
            .query("count > 10")
        )

        for _, row in frequent.iterrows():
            patterns.append(
                {
                    "pattern_type": "frequent_visitor",
                    "person_id": row["person_id"],
                    "sighting_count": int(row["count"]),
                    "confidence": 0.9,
                    "metadata": {"lookback_days": lookback_days},
                }
            )

        # Pattern 2: Unusual hours (nighttime activity)
        recent_df["hour"] = pd.to_datetime(recent_df["timestamp"]).dt.hour
        night_activity = recent_df[(recent_df["hour"] >= 22) | (recent_df["hour"] <= 6)]

        night_persons = night_activity.groupby("person_id").size().reset_index(name="night_count")
        for _, row in night_persons.iterrows():
            if row["night_count"] >= 3:
                patterns.append(
                    {
                        "pattern_type": "unusual_hours",
                        "person_id": row["person_id"],
                        "sighting_count": int(row["night_count"]),
                        "confidence": 0.7,
                        "metadata": {"hours": "22:00-06:00"},
                    }
                )

        # Pattern 3: Multi-camera presence (>3 unique cameras)
        multi_cam = (
            recent_df.groupby("person_id")["camera_id"]
            .nunique()
            .reset_index(name="camera_count")
            .query("camera_count > 3")
        )

        for _, row in multi_cam.iterrows():
            patterns.append(
                {
                    "pattern_type": "multi_camera",
                    "person_id": row["person_id"],
                    "sighting_count": int(row["camera_count"]),
                    "confidence": 0.8,
                    "metadata": {"unique_cameras": int(row["camera_count"])},
                }
            )

        logger.info(f"Detected {len(patterns)} patterns in {lookback_days}-day window")
        return patterns

    def save_model(self, filepath: str) -> None:
        """Save trained models to disk."""
        state = {
            "anomaly_detector": self.anomaly_detector,
            "scaler": self.scaler,
            "pca": self.pca,
            "config": {
                "contamination": self.contamination,
                "eps": self.eps,
                "min_samples": self.min_samples,
                "use_pca": self.use_pca,
                "pca_components": self.pca_components,
            },
        }
        joblib.dump(state, filepath)
        logger.info(f"Model saved to {filepath}")

    def load_model(self, filepath: str) -> None:
        """Load trained models from disk."""
        state = joblib.load(filepath)
        self.anomaly_detector = state["anomaly_detector"]
        self.scaler = state["scaler"]
        self.pca = state["pca"]

        config = state["config"]
        self.contamination = config["contamination"]
        self.eps = config["eps"]
        self.min_samples = config["min_samples"]
        self.use_pca = config["use_pca"]
        self.pca_components = config["pca_components"]

        logger.info(f"Model loaded from {filepath}")


class BiasAuditor:
    """
    Audit detection system for demographic bias using standardized face datasets.
    """

    def __init__(self, detection_engine):
        """
        Initialize bias auditor.

        Args:
            detection_engine: Instance of DetectionEngine to audit
        """
        self.detection_engine = detection_engine
        self.results = {}

    def audit_on_dataset(
        self, images: List[np.ndarray], labels: List[str]
    ) -> Dict[str, Dict]:
        """
        Run detection on labeled dataset and calculate performance by group.

        Args:
            images: List of face images (RGB arrays)
            labels: List of demographic labels (e.g., "asian_male", "white_female")

        Returns:
            Dict mapping labels to performance metrics
        """
        results = {}

        for label in set(labels):
            label_indices = [i for i, lbl in enumerate(labels) if lbl == label]
            label_images = [images[i] for i in label_indices]

            detections = 0
            confidences = []

            for img in label_images:
                # Run detection
                faces = self.detection_engine.detect_and_process(img)
                if faces:
                    detections += 1
                    confidences.append(max(f.get("confidence", 0.0) for f in faces))

            detection_rate = detections / len(label_images) if label_images else 0.0
            avg_confidence = np.mean(confidences) if confidences else 0.0

            results[label] = {
                "total_samples": len(label_images),
                "detections": detections,
                "detection_rate": detection_rate,
                "avg_confidence": avg_confidence,
            }

        self.results = results
        logger.info(f"Bias audit completed for {len(results)} demographic groups")
        return results

    def calculate_disparate_impact(self) -> Dict[str, float]:
        """
        Calculate disparate impact ratios between groups.

        Returns:
            Dict mapping group pairs to disparate impact ratios
        """
        if not self.results:
            logger.warning("No audit results available")
            return {}

        detection_rates = {
            label: metrics["detection_rate"]
            for label, metrics in self.results.items()
        }

        # Calculate max/min ratio
        max_rate = max(detection_rates.values())
        min_rate = min(detection_rates.values())

        disparate_impact = {}
        for label, rate in detection_rates.items():
            if max_rate > 0:
                disparate_impact[label] = rate / max_rate

        logger.info(
            f"Disparate impact range: {min_rate:.2%} - {max_rate:.2%} "
            f"(ratio: {min_rate/max_rate if max_rate > 0 else 0:.2f})"
        )

        return disparate_impact

    def generate_report(self) -> str:
        """
        Generate human-readable bias audit report.

        Returns:
            Formatted report string
        """
        if not self.results:
            return "No audit data available."

        report = ["=== BIAS AUDIT REPORT ===\n"]

        for label, metrics in sorted(self.results.items()):
            report.append(f"\n{label.upper()}:")
            report.append(f"  Samples: {metrics['total_samples']}")
            report.append(f"  Detection Rate: {metrics['detection_rate']:.2%}")
            report.append(f"  Avg Confidence: {metrics['avg_confidence']:.3f}")

        disparate = self.calculate_disparate_impact()
        report.append("\n\nDISPARATE IMPACT RATIOS:")
        for label, ratio in sorted(disparate.items()):
            report.append(f"  {label}: {ratio:.3f}")

        # Flag potential issues (80% rule)
        issues = [label for label, ratio in disparate.items() if ratio < 0.8]
        if issues:
            report.append(f"\n⚠ WARNING: Groups below 80% threshold: {', '.join(issues)}")
        else:
            report.append("\n✓ All groups meet 80% disparate impact threshold")

        return "\n".join(report)
