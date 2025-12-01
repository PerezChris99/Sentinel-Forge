"""Socket.IO utilities for streaming live SentinelForge events to Dash."""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Optional

import socketio

from .config import DashboardConfig

LOGGER = logging.getLogger(__name__)

EventDict = Dict[str, str]


class LiveEventBuffer:
    """Thread-safe ring buffer for the most recent live events."""

    def __init__(self, max_events: int = 200) -> None:
        self._buffer: Deque[EventDict] = deque(maxlen=max_events)
        self._lock = threading.Lock()

    def append(self, event: EventDict) -> None:
        with self._lock:
            self._buffer.append(event)

    def snapshot(self) -> List[EventDict]:
        with self._lock:
            return list(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


class LiveEventStream:
    """Background Socket.IO client that pushes events into the buffer."""

    def __init__(self, config: DashboardConfig, buffer: LiveEventBuffer) -> None:
        self._config = config
        self._buffer = buffer
        self._client = socketio.Client(reconnection=True)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self._client.event
        def connect() -> None:  # pragma: no cover - network dependent
            LOGGER.info("Connected to SentinelForge Socket.IO server")

        @self._client.event
        def disconnect() -> None:  # pragma: no cover - network dependent
            LOGGER.warning("Disconnected from SentinelForge Socket.IO server")

        @self._client.on("sighting")
        def handle_sighting(data: EventDict) -> None:
            self._buffer.append(data)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="SentinelForgeSocket", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._client.connected:
            self._client.disconnect()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                extra_headers = {}
                token = self._config.optional_token()
                if token:
                    extra_headers["Authorization"] = f"Bearer {token}"
                self._client.connect(
                    self._config.socket_url,
                    transports=["websocket"],
                    headers=extra_headers,
                )
                self._client.wait()
            except Exception as exc:  # pragma: no cover - network dependent
                LOGGER.error("Socket connection failed: %s", exc)
                time.sleep(2)


@dataclass(slots=True)
class MockEventEmitter:
    """Simple loop that generates fake events for local development."""

    buffer: LiveEventBuffer
    interval_seconds: float = 3.0

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while True:
            now = datetime.utcnow()
            payload = {
                "event": "sighting",
                "person_id": "unknown" if now.second % 2 else "person-01",
                "camera_id": f"cam-{(now.second % 4) + 1:02d}",
                "flag_level": 2 if now.second % 5 == 0 else 0,
                "thumbnail_b64": "data:image/jpeg;base64,placeholder",
                "timestamp": now.isoformat(),
            }
            self.buffer.append(payload)
            time.sleep(self.interval_seconds)


def seed_mock_data(buffer: LiveEventBuffer) -> None:
    base = datetime.utcnow() - timedelta(minutes=5)
    for idx in range(5):
        buffer.append(
            {
                "event": "sighting",
                "person_id": f"person-{idx:02d}",
                "camera_id": f"cam-{idx+1:02d}",
                "flag_level": idx % 3,
                "thumbnail_b64": "data:image/jpeg;base64,placeholder",
                "timestamp": (base + timedelta(seconds=idx * 30)).isoformat(),
            }
        )
