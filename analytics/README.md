# SentinelForge Analytics Engine

Phase 4 implementation: Pattern mining, anomaly detection, clustering, and bias auditing.

## Overview

The Analytics Engine provides advanced machine learning capabilities for the SentinelForge platform:

- **Anomaly Detection**: Isolation Forest to identify unusual sighting patterns
- **Pattern Mining**: Temporal and behavioral pattern extraction
- **Clustering**: DBSCAN to group unknown faces and find repeat offenders
- **Bias Auditing**: Fairness metrics across demographic groups

## Components

### 1. AnalyticsEngine (`analytics/engine.py`)

Main class for ML-based analytics.

**Features**:
- Feature extraction from temporal data
- Isolation Forest anomaly detection
- DBSCAN clustering for unknowns
- Pattern detection (frequent visitors, unusual hours, multi-camera)
- Model persistence (save/load)

**Example Usage**:
```python
from analytics.engine import AnalyticsEngine
import numpy as np

# Initialize engine
engine = AnalyticsEngine(
    anomaly_contamination=0.1,
    clustering_eps=0.3,
    use_pca=True
)

# Train anomaly detector
embeddings = np.random.randn(1000, 128)
engine.train_anomaly_detector(embeddings)

# Predict anomaly scores
new_embeddings = np.random.randn(10, 128)
scores = engine.predict_anomaly_score(new_embeddings)

# Cluster unknowns
labels, n_clusters, silhouette = engine.cluster_unknowns(embeddings)

# Save model
engine.save_model("models/anomaly_detector.joblib")
```

### 2. BiasAuditor (`analytics/engine.py`)

Audit detection system for demographic bias.

**Features**:
- Performance metrics by demographic group
- Disparate impact ratio calculation
- Compliance with 80% rule
- Human-readable audit reports

**Example Usage**:
```python
from analytics.engine import BiasAuditor
from detection.engine import DetectionEngine

# Initialize
detection_engine = DetectionEngine()
auditor = BiasAuditor(detection_engine)

# Run audit
images = [...]  # List of face images
labels = ["asian_male", "white_female", ...]  # Demographics
results = auditor.audit_on_dataset(images, labels)

# Generate report
print(auditor.generate_report())
```

### 3. Celery Tasks (`analytics/tasks.py`)

Scheduled background jobs for periodic analytics.

**Tasks**:
- `detect_patterns_task`: Daily pattern detection (02:00 UTC)
- `train_anomaly_detector_task`: Weekly model retraining (Sunday 03:00 UTC)
- `score_recent_sightings_task`: Anomaly scoring every 6 hours
- `cluster_unknowns_task`: Daily unknown clustering (04:00 UTC)

**Example Usage**:
```python
from analytics.tasks import detect_patterns_task

# Run manually
result = detect_patterns_task.delay(lookback_days=30)

# Check result
print(result.get())
```

## Patterns Detected

### 1. Frequent Visitor
- **Criteria**: >10 sightings in 30-day window
- **Confidence**: 0.9
- **Use Case**: Identify regular customers, employees, or suspects

### 2. Unusual Hours
- **Criteria**: ≥3 sightings between 22:00-06:00
- **Confidence**: 0.7
- **Use Case**: After-hours activity monitoring

### 3. Multi-Camera
- **Criteria**: >3 unique cameras in window
- **Confidence**: 0.8
- **Use Case**: Track movement patterns, loitering detection

### 4. Anomaly
- **Criteria**: Anomaly score >0.7 from Isolation Forest
- **Confidence**: Variable (score value)
- **Use Case**: Flag unusual embedding patterns, potential attacks

### 5. Unknown Cluster
- **Criteria**: DBSCAN cluster of ≥3 unknown faces
- **Confidence**: Silhouette score
- **Use Case**: Identify repeat unknowns for manual review

## Database Schema

Patterns are stored in the `patterns` table:

```sql
CREATE TABLE patterns (
    id UUID PRIMARY KEY,
    person_id UUID REFERENCES persons(id),  -- NULL for unknown clusters
    pattern_type VARCHAR(50),
    confidence FLOAT,
    sighting_count INT,
    metadata JSONB,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Configuration

### Environment Variables

```bash
# Analytics settings (optional)
ANALYTICS_CONTAMINATION=0.1        # Anomaly contamination rate
ANALYTICS_CLUSTERING_EPS=0.3       # DBSCAN epsilon
ANALYTICS_USE_PCA=true             # Enable PCA preprocessing
ANALYTICS_PCA_COMPONENTS=50        # PCA target dimensions
```

### Celery Beat Schedule

Add to `api/celery_app.py`:

```python
from celery.schedules import crontab
from datetime import timedelta

celery_app.conf.beat_schedule = {
    'detect-patterns-daily': {
        'task': 'analytics.detect_patterns',
        'schedule': crontab(hour=2, minute=0),
    },
    'train-anomaly-detector-weekly': {
        'task': 'analytics.train_anomaly_detector',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),
    },
    'score-recent-sightings': {
        'task': 'analytics.score_recent_sightings',
        'schedule': timedelta(hours=6),
    },
    'cluster-unknowns-daily': {
        'task': 'analytics.cluster_unknowns',
        'schedule': crontab(hour=4, minute=0),
    },
}
```

## Dependencies

```toml
[project.optional-dependencies]
analytics = [
    "scikit-learn>=1.3.0",
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "joblib>=1.3.0",
]
```

Install with:
```bash
pip install -e ".[analytics]"
```

## Testing

Run unit tests:
```bash
pytest tests/test_analytics.py -v
```

Expected output:
```
tests/test_analytics.py::TestAnalyticsEngine::test_initialization PASSED
tests/test_analytics.py::TestAnalyticsEngine::test_train_anomaly_detector PASSED
tests/test_analytics.py::TestAnalyticsEngine::test_cluster_unknowns PASSED
tests/test_analytics.py::TestAnalyticsEngine::test_detect_patterns_frequent_visitor PASSED
tests/test_analytics.py::TestBiasAuditor::test_audit_on_dataset PASSED
```

## Performance

### Anomaly Detection
- Training: ~5-10s for 1,000 samples (with PCA)
- Inference: ~0.1s per batch of 100 samples
- Memory: ~50 MB model size

### Clustering
- Runtime: ~2-5s for 1,000 unknowns
- Silhouette score: >0.5 indicates good clustering

### Pattern Detection
- Daily run: ~10-30s for 30-day window
- Scales linearly with sighting count

## Bias Auditing

### Datasets

Recommended public datasets for bias testing:

1. **LFW (Labeled Faces in the Wild)**
   - URL: http://vis-www.cs.umass.edu/lfw/
   - Labels: Name, ethnicity (inferred)

2. **RFW (Racial Faces in the Wild)**
   - URL: http://www.whdeng.cn/RFW/index.html
   - Labels: African, Asian, Caucasian, Indian

3. **UTKFace**
   - URL: https://susanqq.github.io/UTKFace/
   - Labels: Age, gender, ethnicity

### Running Audit

```python
from analytics.engine import BiasAuditor
from detection.engine import DetectionEngine

# Load dataset
images, labels = load_rfw_dataset()  # Your loader

# Initialize
engine = DetectionEngine()
auditor = BiasAuditor(engine)

# Run audit
results = auditor.audit_on_dataset(images, labels)

# Check compliance
disparate = auditor.calculate_disparate_impact()
for group, ratio in disparate.items():
    if ratio < 0.8:
        print(f"WARNING: {group} fails 80% rule (ratio={ratio:.2f})")

# Generate report
print(auditor.generate_report())
```

### Interpreting Results

- **Detection Rate**: % of faces successfully detected
- **Avg Confidence**: Mean confidence score for detections
- **Disparate Impact Ratio**: Group rate / max rate
  - **≥0.8**: Compliant with 80% rule (EEOC guideline)
  - **<0.8**: Potential bias, investigate further

## Troubleshooting

### Model Training Fails

**Issue**: `ValueError: Insufficient data for training`

**Solution**: 
- Ensure ≥100 samples in database
- Check embedding column is populated
- Verify date range in query

### Clustering Returns No Clusters

**Issue**: All unknowns labeled as noise (-1)

**Solution**:
- Decrease `clustering_eps` (try 0.2)
- Increase `clustering_min_samples` (try 2)
- Verify embeddings are normalized

### Patterns Not Saving to Database

**Issue**: Patterns detected but not in DB

**Solution**:
- Check async session is committed
- Verify Person.id exists for pattern.person_id
- Review Celery logs for errors

### Bias Audit Shows No Detections

**Issue**: All detection rates are 0%

**Solution**:
- Verify images are valid RGB arrays
- Check DetectionEngine initialization
- Test with single image first

## Future Enhancements

- [ ] Incremental training for large datasets
- [ ] LSTM for temporal sequence prediction
- [ ] Graph analysis for person relationships
- [ ] Privacy-preserving federated learning
- [ ] Automated bias mitigation techniques
- [ ] Real-time anomaly alerting via webhooks
- [ ] Advanced clustering (HDBSCAN, Spectral)

## References

- **Isolation Forest**: Liu et al. (2008) - "Isolation Forest"
- **DBSCAN**: Ester et al. (1996) - "A density-based algorithm"
- **Disparate Impact**: EEOC (1978) - "Uniform Guidelines on Employee Selection"
- **Fairness in ML**: Mehrabi et al. (2021) - "A Survey on Bias and Fairness"
