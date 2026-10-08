"""Camera source validation and factory tests."""

import pytest

cv2 = pytest.importorskip("cv2")

from detection.sources import CameraType, create_source, detect_camera_type, validate_stream_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("0", CameraType.USB),
        ("rtsp://10.0.0.5:554/stream", CameraType.RTSP),
        ("http://192.168.1.10:8080/video", CameraType.IP_WEBCAM),
        ("http://example.test/live.mjpeg", CameraType.HTTP),
        ("sample.mp4", CameraType.FILE),
    ],
)
def test_detect_camera_type(url, expected):
    assert detect_camera_type(url) == expected


def test_unknown_network_scheme_is_rejected():
    valid, reason = validate_stream_url("ftp://example.test/camera")
    assert not valid
    assert "scheme" in reason.lower()


def test_localhost_can_be_rejected_for_untrusted_validation():
    valid, reason = validate_stream_url("http://localhost:8080/video", allow_private=False)
    assert not valid
    assert "localhost" in reason.lower()


def test_factory_creates_expected_source():
    source = create_source("rtsp://10.0.0.5:554/stream", "cam-1")
    assert source.camera_id == "cam-1"
    assert isinstance(source.stream_url, str)
