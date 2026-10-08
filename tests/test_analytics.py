"""
Unit tests for Analytics Engine
Tests for pattern detection, anomaly scoring, clustering, and bias auditing
"""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from analytics.engine import AnalyticsEngine, BiasAuditor


class TestAnalyticsEngine:
    """Test cases for AnalyticsEngine class."""

    def test_initialization(self):
        """Test engine initialization with default parameters."""
        engine = AnalyticsEngine()
        assert engine.contamination == 0.1
        assert engine.eps == 0.3
        assert engine.min_samples == 3
        assert engine.use_pca is True
        assert engine.pca_components == 50

    def test_initialization_custom_params(self):
        """Test engine initialization with custom parameters."""
        engine = AnalyticsEngine(
            anomaly_contamination=0.05,
            clustering_eps=0.5,
            use_pca=False
        )
        assert engine.contamination == 0.05
        assert engine.eps == 0.5
        assert engine.use_pca is False

    def test_extract_features(self):
        """Test feature extraction from sightings data."""
        # Create sample data
        now = datetime.utcnow()
        df = pd.DataFrame([
            {
                "person_id": "person_1",
                "timestamp": now - timedelta(hours=i),
                "camera_id": f"CAM-{i % 3}",
                "confidence": 0.9 - (i * 0.01),
                "flag_level": 0
            }
            for i in range(10)
        ])

        engine = AnalyticsEngine()
        features = engine.extract_features(df)

        # Verify new columns exist
        assert "hour" in features.columns
        assert "day_of_week" in features.columns
        assert "is_weekend" in features.columns
        assert "is_night" in features.columns
        assert "sighting_count" in features.columns
        assert "avg_confidence" in features.columns
        assert "unique_cameras" in features.columns

        # Verify aggregations
        assert features["sighting_count"].iloc[0] == 10  # All for same person
        assert features["unique_cameras"].iloc[0] == 3  # 3 unique cameras

    def test_train_anomaly_detector(self):
        """Test anomaly detector training."""
        # Create synthetic embeddings
        np.random.seed(42)
        embeddings = np.random.randn(100, 128)  # 100 samples, 128 dims

        engine = AnalyticsEngine(use_pca=True, pca_components=50)
        engine.train_anomaly_detector(embeddings)

        assert engine.anomaly_detector is not None
        assert engine.pca is not None
        assert engine.pca.n_components_ == 50

    def test_train_anomaly_detector_insufficient_data(self):
        """Test anomaly detector with insufficient data."""
        embeddings = np.random.randn(5, 128)  # Only 5 samples

        engine = AnalyticsEngine()
        engine.train_anomaly_detector(embeddings)

        # Should warn and not train
        assert engine.anomaly_detector is None

    def test_predict_anomaly_score(self):
        """Test anomaly score prediction."""
        np.random.seed(42)
        
        # Train on normal data
        train_embeddings = np.random.randn(100, 128)
        engine = AnalyticsEngine(use_pca=False)  # Disable PCA for simplicity
        engine.train_anomaly_detector(train_embeddings)

        # Test on new data
        test_embeddings = np.random.randn(10, 128)
        scores = engine.predict_anomaly_score(test_embeddings)

        assert len(scores) == 10
        assert all(0 <= s <= 1 for s in scores)  # Scores in [0, 1]

    def test_predict_anomaly_score_untrained(self):
        """Test anomaly score prediction without training."""
        engine = AnalyticsEngine()
        embeddings = np.random.randn(10, 128)
        scores = engine.predict_anomaly_score(embeddings)

        assert len(scores) == 10
        assert all(s == 0 for s in scores)  # Should return zeros

    def test_cluster_unknowns(self):
        """Test DBSCAN clustering on unknowns."""
        np.random.seed(42)
        
        # Create 3 clusters + noise
        base1 = np.tile([1.0, 0.0], 64)
        base2 = np.tile([0.0, 1.0], 64)
        base3 = np.tile([-1.0, -1.0], 64)
        cluster1 = base1 + np.random.randn(20, 128) * 0.02
        cluster2 = base2 + np.random.randn(20, 128) * 0.02
        cluster3 = base3 + np.random.randn(20, 128) * 0.02
        noise = np.random.randn(5, 128) * 5
        
        embeddings = np.vstack([cluster1, cluster2, cluster3, noise])

        engine = AnalyticsEngine(
            clustering_eps=1.0,
            clustering_min_samples=5,
            use_pca=False
        )
        labels, n_clusters, silhouette = engine.cluster_unknowns(embeddings)

        assert len(labels) == 65
        assert n_clusters >= 2  # Should find at least 2 clusters
        assert -1 <= silhouette <= 1  # Valid silhouette score

    def test_cluster_unknowns_insufficient_data(self):
        """Test clustering with insufficient data."""
        embeddings = np.random.randn(2, 128)

        engine = AnalyticsEngine()
        labels, n_clusters, silhouette = engine.cluster_unknowns(embeddings)

        assert len(labels) == 2
        assert all(l == -1 for l in labels)  # All noise
        assert n_clusters == 0
        assert silhouette == 0.0

    def test_detect_patterns_frequent_visitor(self):
        """Test frequent visitor pattern detection."""
        now = datetime.utcnow()
        
        # Create data with one frequent visitor
        df = pd.DataFrame([
            {
                "person_id": "frequent_person",
                "timestamp": now - timedelta(days=i),
                "camera_id": "CAM-01",
                "confidence": 0.9,
                "flag_level": 0
            }
            for i in range(15)  # 15 sightings
        ] + [
            {
                "person_id": "normal_person",
                "timestamp": now - timedelta(days=i),
                "camera_id": "CAM-02",
                "confidence": 0.85,
                "flag_level": 0
            }
            for i in range(5)  # Only 5 sightings
        ])

        engine = AnalyticsEngine()
        patterns = engine.detect_patterns(df, lookback_days=30)

        # Should detect frequent visitor pattern
        frequent_patterns = [p for p in patterns if p["pattern_type"] == "frequent_visitor"]
        assert len(frequent_patterns) > 0
        assert frequent_patterns[0]["person_id"] == "frequent_person"

    def test_detect_patterns_unusual_hours(self):
        """Test unusual hours pattern detection."""
        now = datetime.utcnow()
        night_hour = now.replace(hour=23, minute=0, second=0, microsecond=0)
        
        # Create nighttime activity
        df = pd.DataFrame([
            {
                "person_id": "night_person",
                "timestamp": night_hour - timedelta(days=i),
                "camera_id": "CAM-01",
                "confidence": 0.9,
                "flag_level": 0
            }
            for i in range(10)  # enough observations for the analytics minimum
        ])

        engine = AnalyticsEngine()
        patterns = engine.detect_patterns(df, lookback_days=30)

        # Should detect unusual hours pattern
        night_patterns = [p for p in patterns if p["pattern_type"] == "unusual_hours"]
        assert len(night_patterns) > 0

    def test_detect_patterns_multi_camera(self):
        """Test multi-camera pattern detection."""
        now = datetime.utcnow()
        
        # Create multi-camera presence
        df = pd.DataFrame([
            {
                "person_id": "roaming_person",
                "timestamp": now - timedelta(hours=i),
                "camera_id": f"CAM-{i % 5}",  # 5 different cameras
                "confidence": 0.9,
                "flag_level": 0
            }
            for i in range(10)
        ])

        engine = AnalyticsEngine()
        patterns = engine.detect_patterns(df, lookback_days=30)

        # Should detect multi-camera pattern
        multi_cam_patterns = [p for p in patterns if p["pattern_type"] == "multi_camera"]
        assert len(multi_cam_patterns) > 0
        assert multi_cam_patterns[0]["metadata"]["unique_cameras"] >= 4

    def test_detect_patterns_insufficient_data(self):
        """Test pattern detection with insufficient data."""
        df = pd.DataFrame([
            {
                "person_id": "person_1",
                "timestamp": datetime.utcnow(),
                "camera_id": "CAM-01",
                "confidence": 0.9,
                "flag_level": 0
            }
            for _ in range(5)  # Only 5 rows
        ])

        engine = AnalyticsEngine()
        patterns = engine.detect_patterns(df, lookback_days=30)

        assert patterns == []

    def test_save_and_load_model(self, tmp_path):
        """Test model persistence."""
        np.random.seed(42)
        embeddings = np.random.randn(100, 128)

        # Train and save
        engine1 = AnalyticsEngine(use_pca=True)
        engine1.train_anomaly_detector(embeddings)
        
        model_path = tmp_path / "test_model.joblib"
        engine1.save_model(str(model_path))

        # Load and verify
        engine2 = AnalyticsEngine()
        engine2.load_model(str(model_path))

        assert engine2.anomaly_detector is not None
        assert engine2.pca is not None
        assert engine2.contamination == engine1.contamination

        # Verify predictions match
        test_embeddings = np.random.randn(10, 128)
        scores1 = engine1.predict_anomaly_score(test_embeddings)
        scores2 = engine2.predict_anomaly_score(test_embeddings)

        np.testing.assert_array_almost_equal(scores1, scores2)


class TestBiasAuditor:
    """Test cases for BiasAuditor class."""

    @pytest.fixture
    def mock_detection_engine(self):
        """Mock detection engine for testing."""
        class MockEngine:
            def detect_and_process(self, image):
                # Simulate detection with varying success rates
                h, w = image.shape[:2]
                if h > 100 and w > 100:  # "Good" images
                    return [{"confidence": 0.9}]
                else:  # "Poor" images
                    return []
        
        return MockEngine()

    def test_audit_on_dataset(self, mock_detection_engine):
        """Test bias audit on labeled dataset."""
        # Create mock images
        np.random.seed(42)
        good_images = [np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8) for _ in range(10)]
        poor_images = [np.random.randint(0, 255, (50, 50, 3), dtype=np.uint8) for _ in range(10)]
        
        images = good_images + poor_images
        labels = ["group_a"] * 10 + ["group_b"] * 10

        auditor = BiasAuditor(mock_detection_engine)
        results = auditor.audit_on_dataset(images, labels)

        assert "group_a" in results
        assert "group_b" in results
        assert results["group_a"]["total_samples"] == 10
        assert results["group_b"]["total_samples"] == 10
        
        # Group A should have higher detection rate
        assert results["group_a"]["detection_rate"] > results["group_b"]["detection_rate"]

    def test_calculate_disparate_impact(self, mock_detection_engine):
        """Test disparate impact calculation."""
        np.random.seed(42)
        images = [np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8) for _ in range(20)]
        labels = ["group_a"] * 10 + ["group_b"] * 10

        auditor = BiasAuditor(mock_detection_engine)
        auditor.audit_on_dataset(images, labels)
        
        disparate_impact = auditor.calculate_disparate_impact()

        assert "group_a" in disparate_impact
        assert "group_b" in disparate_impact
        assert all(0 <= ratio <= 1 for ratio in disparate_impact.values())

    def test_generate_report(self, mock_detection_engine):
        """Test report generation."""
        np.random.seed(42)
        images = [np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8) for _ in range(10)]
        labels = ["test_group"] * 10

        auditor = BiasAuditor(mock_detection_engine)
        auditor.audit_on_dataset(images, labels)
        
        report = auditor.generate_report()

        assert "BIAS AUDIT REPORT" in report
        assert "TEST_GROUP" in report
        assert "Detection Rate" in report
        assert "DISPARATE IMPACT RATIOS" in report

    def test_generate_report_no_data(self, mock_detection_engine):
        """Test report generation without audit data."""
        auditor = BiasAuditor(mock_detection_engine)
        report = auditor.generate_report()

        assert "No audit data available" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
