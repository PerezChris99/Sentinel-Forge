"""
Camera Source Abstraction Layer for SentinelForge.
Supports IP Webcam Pro, RTSP, USB, and file-based camera sources.
Auto-detects source type from URL pattern when not specified.
"""
import enum
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from urllib.parse import urlparse

import cv2
import numpy as np
import urllib.request
import urllib.error

LOGGER = logging.getLogger("SentinelForge.Sources")

# Private network ranges for SSRF validation
_PRIVATE_RANGES = re.compile(
    r"^(127\.|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|0\.|169\.254\.|::1|fc|fd|fe80)"
)


class CameraType(str, enum.Enum):
    IP_WEBCAM = "ip_webcam"
    RTSP = "rtsp"
    USB = "usb"
    FILE = "file"
    HTTP = "http"


def detect_camera_type(stream_url: str) -> CameraType:
    """Auto-detect camera type from stream URL pattern."""
    url = stream_url.strip()

    # USB camera (integer device index)
    if url.isdigit():
        return CameraType.USB

    # File path
    if url.endswith((".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv")):
        return CameraType.FILE

    # RTSP
    if url.startswith("rtsp://"):
        return CameraType.RTSP

    # IP Webcam Pro signatures
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    if any(
        seg in path_lower
        for seg in ("/video", "/videofeed", "/shot.jpg", "/photo.jpg", "/sensor")
    ):
        return CameraType.IP_WEBCAM
    if parsed.port and parsed.port == 8080 and parsed.scheme in ("http", "https"):
        return CameraType.IP_WEBCAM

    # Generic HTTP stream (MJPEG etc.)
    if url.startswith(("http://", "https://")):
        return CameraType.HTTP

    return CameraType.FILE


def validate_stream_url(stream_url: str, allow_private: bool = True) -> Tuple[bool, str]:
    """Validate a stream URL. Returns (is_valid, reason)."""
    url = stream_url.strip()

    # USB index
    if url.isdigit():
        return True, "USB device"

    # File paths are accepted for local playback/testing.
    if not url.startswith(("http://", "https://", "rtsp://")):
        if "://" in url:
            return False, "Unsupported stream scheme"
        return True, "File path"

    parsed = urlparse(url)
    if parsed.scheme == "rtsp" and parsed.port is not None and not 1 <= parsed.port <= 65535:
        return False, "Invalid port"
    if parsed.scheme in {"http", "https"} and parsed.port is not None and not 1 <= parsed.port <= 65535:
        return False, "Invalid port"
    if not parsed.hostname:
        return False, "Missing hostname"
    if parsed.hostname.lower() in {"localhost", "ip6-localhost"}:
        if not allow_private:
            return False, "Localhost is not allowed"

    # SSRF protection in production: block private IPs unless allowed
    if not allow_private and _PRIVATE_RANGES.match(parsed.hostname):
        return False, "Private network addresses not allowed in production mode"

    return True, "OK"


class CameraSource(ABC):
    """Abstract base class for all camera sources."""

    CONNECT_TIMEOUT_SEC = 5  # Max seconds to wait for connection

    def __init__(self, stream_url: str, camera_id: str):
        self.stream_url = stream_url
        self.camera_id = camera_id
        self._cap: Optional[cv2.VideoCapture] = None

    def _set_timeouts(self, cap: cv2.VideoCapture):
        """Apply connection/read timeouts to a VideoCapture instance."""
        timeout_ms = self.CONNECT_TIMEOUT_SEC * 1000
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)

    @abstractmethod
    def open(self) -> bool:
        """Open the camera stream. Returns True on success."""

    @abstractmethod
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a single frame. Returns (success, frame)."""

    def release(self):
        """Release the camera resource."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def health_check(self) -> dict:
        """Check if the camera stream is reachable and returning frames."""
        start = time.time()
        try:
            if not self.is_opened():
                ok = self.open()
                if not ok:
                    return {"status": "error", "detail": "Failed to open stream", "latency_ms": 0}

            ret, frame = self.read()
            latency = round((time.time() - start) * 1000, 1)

            if ret and frame is not None:
                h, w = frame.shape[:2]
                return {
                    "status": "online",
                    "latency_ms": latency,
                    "resolution": f"{w}x{h}",
                    "detail": "OK",
                }
            return {"status": "error", "detail": "No frame received", "latency_ms": latency}
        except Exception as e:
            latency = round((time.time() - start) * 1000, 1)
            return {"status": "error", "detail": str(e), "latency_ms": latency}

    def get_snapshot(self) -> Optional[np.ndarray]:
        """Grab a single frame (convenience method)."""
        was_closed = not self.is_opened()
        if was_closed:
            if not self.open():
                return None
        ret, frame = self.read()
        if was_closed:
            self.release()
        return frame if ret else None


class IPWebcamSource(CameraSource):
    """
    IP Webcam Pro (Android) camera source.

    Supported endpoints:
      - /video       MJPEG stream (browser-native)
      - /videofeed   Alternative MJPEG feed
      - /shot.jpg    Single JPEG snapshot
      - /photo.jpg   High-quality photo
      - /sensors.json Sensor data (accelerometer, light, etc.)
    """

    def __init__(self, stream_url: str, camera_id: str):
        super().__init__(stream_url, camera_id)
        self._base_url = self._derive_base_url(stream_url)

    @staticmethod
    def _derive_base_url(url: str) -> str:
        """Extract base URL (http://IP:port) from any IP Webcam endpoint."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def video_url(self) -> str:
        return f"{self._base_url}/video"

    @property
    def snapshot_url(self) -> str:
        return f"{self._base_url}/shot.jpg"

    @property
    def sensors_url(self) -> str:
        return f"{self._base_url}/sensors.json"

    def open(self) -> bool:
        self.release()
        self._cap = cv2.VideoCapture(self.video_url)
        self._set_timeouts(self._cap)
        # IP Webcam streams benefit from a small buffer
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        opened = self._cap.isOpened()
        if opened:
            LOGGER.info("IPWebcam opened for %s at %s", self.camera_id, self.video_url)
        else:
            LOGGER.warning("IPWebcam failed to open for %s at %s", self.camera_id, self.video_url)
        return opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cap is None or not self._cap.isOpened():
            return False, None
        return self._cap.read()

    def get_snapshot(self) -> Optional[np.ndarray]:
        """Grab snapshot via /shot.jpg with HTTP timeout."""
        try:
            req = urllib.request.Request(self.snapshot_url, method="GET")
            resp = urllib.request.urlopen(req, timeout=self.CONNECT_TIMEOUT_SEC)
            data = resp.read()
            arr = np.frombuffer(data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return frame
        except Exception as e:
            LOGGER.error("Snapshot failed for %s: %s", self.camera_id, e)
            return None

    def health_check(self) -> dict:
        """Check reachability via snapshot endpoint (lightweight HTTP probe first)."""
        start = time.time()
        try:
            # Quick HTTP HEAD/GET with short timeout before cv2
            req = urllib.request.Request(self.snapshot_url, method="GET")
            resp = urllib.request.urlopen(req, timeout=self.CONNECT_TIMEOUT_SEC)
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
            latency = round((time.time() - start) * 1000, 1)

            if len(data) > 0 and "image" in content_type:
                # Decode the JPEG to get resolution
                arr = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    h, w = frame.shape[:2]
                    return {
                        "status": "online",
                        "latency_ms": latency,
                        "resolution": f"{w}x{h}",
                        "source_type": "ip_webcam",
                        "base_url": self._base_url,
                        "detail": "OK",
                    }
            return {"status": "error", "detail": "No valid image from snapshot", "latency_ms": latency}
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            latency = round((time.time() - start) * 1000, 1)
            return {"status": "error", "detail": str(e), "latency_ms": latency}
        except Exception as e:
            latency = round((time.time() - start) * 1000, 1)
            return {"status": "error", "detail": str(e), "latency_ms": latency}


class RTSPSource(CameraSource):
    """Standard RTSP camera source (e.g. IP cameras, NVRs)."""

    def open(self) -> bool:
        self.release()
        # Use TCP transport for reliability
        self._cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
        self._set_timeouts(self._cap)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
        opened = self._cap.isOpened()
        if opened:
            LOGGER.info("RTSP opened for %s at %s", self.camera_id, self.stream_url)
        else:
            LOGGER.warning("RTSP failed to open for %s", self.camera_id)
        return opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cap is None or not self._cap.isOpened():
            return False, None
        return self._cap.read()


class USBSource(CameraSource):
    """Local USB / built-in webcam source (device index)."""

    def __init__(self, stream_url: str, camera_id: str):
        super().__init__(stream_url, camera_id)
        self._device_index = int(stream_url)

    def open(self) -> bool:
        self.release()
        self._cap = cv2.VideoCapture(self._device_index)
        opened = self._cap.isOpened()
        if opened:
            LOGGER.info("USB camera %d opened for %s", self._device_index, self.camera_id)
        return opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cap is None or not self._cap.isOpened():
            return False, None
        return self._cap.read()


class FileSource(CameraSource):
    """Video file source for testing / playback."""

    def open(self) -> bool:
        self.release()
        self._cap = cv2.VideoCapture(self.stream_url)
        opened = self._cap.isOpened()
        if opened:
            LOGGER.info("File source opened for %s: %s", self.camera_id, self.stream_url)
        return opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cap is None or not self._cap.isOpened():
            return False, None
        ret, frame = self._cap.read()
        if not ret:
            # Loop video files for continuous testing
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()
        return ret, frame


class HTTPSource(CameraSource):
    """Generic HTTP MJPEG stream source."""

    def open(self) -> bool:
        self.release()
        self._cap = cv2.VideoCapture(self.stream_url)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        opened = self._cap.isOpened()
        if opened:
            LOGGER.info("HTTP stream opened for %s at %s", self.camera_id, self.stream_url)
        return opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cap is None or not self._cap.isOpened():
            return False, None
        return self._cap.read()


# ── Factory ──────────────────────────────────────────────────────────

_SOURCE_MAP = {
    CameraType.IP_WEBCAM: IPWebcamSource,
    CameraType.RTSP: RTSPSource,
    CameraType.USB: USBSource,
    CameraType.FILE: FileSource,
    CameraType.HTTP: HTTPSource,
}


def create_source(
    stream_url: str,
    camera_id: str,
    camera_type: Optional[str] = None,
) -> CameraSource:
    """
    Factory: create the right CameraSource for a given URL.

    If *camera_type* is ``None``, auto-detects from the URL pattern.
    """
    if camera_type:
        ct = CameraType(camera_type)
    else:
        ct = detect_camera_type(stream_url)

    cls = _SOURCE_MAP.get(ct, HTTPSource)
    LOGGER.debug("Creating %s source for %s (%s)", ct.value, camera_id, stream_url)
    return cls(stream_url, camera_id)
