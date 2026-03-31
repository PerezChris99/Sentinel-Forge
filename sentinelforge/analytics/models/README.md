# Analytics Models Directory

This directory stores trained machine learning models for the SentinelForge analytics engine.

## Model Files

### anomaly_detector.joblib
- **Type**: Isolation Forest + PCA + StandardScaler
- **Purpose**: Detect anomalous sighting patterns
- **Input**: 128-dimensional face embeddings
- **Output**: Anomaly score [0, 1], where higher = more anomalous
- **Training Schedule**: Weekly (Sunday 03:00 UTC)
- **Contamination**: 0.1 (10% expected outliers)

## Directory Structure

```
models/
├── anomaly_detector.joblib    # Current production model
├── .gitkeep                    # Keep directory in git
└── README.md                   # This file
```

## Model Versioning

Production models are retrained weekly via Celery beat schedule. To enable versioning:

1. **Backup before retrain**:
   ```bash
   cp anomaly_detector.joblib anomaly_detector_$(date +%Y%m%d).joblib
   ```

2. **Rollback if needed**:
   ```bash
   cp anomaly_detector_20240101.joblib anomaly_detector.joblib
   ```

## Model Details

### Isolation Forest Parameters
- `contamination`: 0.1
- `n_estimators`: 100 (default)
- `max_samples`: "auto"
- `random_state`: 42

### PCA Preprocessing
- Target dimensions: 50
- Explained variance: >85%
- Reduces 128-dim embeddings for faster processing

### StandardScaler
- Applied after PCA
- Ensures zero mean, unit variance

## Training Data Requirements

- **Minimum samples**: 100
- **Recommended**: 1,000+
- **Data source**: Known persons' sightings (past 90 days)
- **Exclusions**: Unknown/flagged sightings

## Performance Metrics

Track these metrics after retraining:

- Number of training samples
- PCA explained variance ratio
- Sample predictions on validation set
- Anomaly score distribution

## Usage

### Load Model
```python
from analytics.engine import AnalyticsEngine

engine = AnalyticsEngine()
engine.load_model("analytics/models/anomaly_detector.joblib")
```

### Predict Scores
```python
import numpy as np

embeddings = np.array([...])  # Shape: (n_samples, 128)
scores = engine.predict_anomaly_score(embeddings)
```

## Git Policy

**DO NOT** commit model files to git:
- Models are large (10-50 MB)
- Retrained frequently
- Environment-specific

Instead:
- Store in S3/blob storage for production
- Regenerate in each environment
- Use `.gitignore` to exclude `*.joblib`

## Troubleshooting

### Model not found
- Run training task manually: `celery -A api.celery_app call analytics.train_anomaly_detector`
- Check Celery beat schedule is active

### Poor performance
- Increase training samples
- Adjust `contamination` parameter
- Review PCA components (may need more/less)

### Memory issues
- Reduce max training samples (currently 10,000)
- Enable PCA to reduce dimensions
- Use incremental training (not yet implemented)
