"""Boundary tests for externally supplied API models."""

from pydantic import ValidationError
import pytest

from api.main import SightingEvent


def _event(**overrides):
    payload = {
        "timestamp": "2026-10-08T12:00:00Z",
        "camera_id": "cam-01",
        "confidence": 0.9,
        "embedding": [0.0] * 128,
        "cropped_b64": "data:image/jpeg;base64,AA==",
    }
    payload.update(overrides)
    return payload


def test_sighting_event_defaults_metadata_without_shared_mutable_state():
    a = SightingEvent(**_event())
    b = SightingEvent(**_event())
    a.metadata["source"] = "camera"
    assert b.metadata == {}


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_sighting_confidence_is_bounded(confidence):
    with pytest.raises(ValidationError):
        SightingEvent(**_event(confidence=confidence))


@pytest.mark.parametrize("size", [0, 127, 129])
def test_embedding_length_is_exactly_128(size):
    with pytest.raises(ValidationError):
        SightingEvent(**_event(embedding=[0.0] * size))


@pytest.mark.parametrize("flag_level", [-1, 4])
def test_flag_level_is_bounded(flag_level):
    with pytest.raises(ValidationError):
        SightingEvent(**_event(flag_level=flag_level))
