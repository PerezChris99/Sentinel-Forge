"""REST helper for SentinelForge dashboard data needs."""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from requests import Response, Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .config import DashboardConfig

JsonDict = Dict[str, Any]


class APIClientError(RuntimeError):
    """Raised when the backend API returns an unexpected response."""


class BaseSentinelForgeAPI:
    """Abstract base for real or mocked API clients."""

    def fetch_overview_stats(self) -> JsonDict:
        raise NotImplementedError

    def fetch_persons(self) -> List[JsonDict]:
        raise NotImplementedError

    def fetch_person_timeline(self, person_id: Optional[str]) -> List[JsonDict]:
        raise NotImplementedError

    def fetch_unknown_clusters(self, page: int = 1, flag_level: Optional[int] = None) -> JsonDict:
        raise NotImplementedError


class SentinelForgeAPI(BaseSentinelForgeAPI):
    """Requests-backed client that talks to the FastAPI service."""

    def __init__(self, config: DashboardConfig) -> None:
        self.base_url = config.api_url.rstrip("/") + "/"
        self.timeout = config.request_timeout
        self.session: Session = requests.Session()
        headers = {
            "Accept": "application/json",
            "User-Agent": "SentinelForgeDashboard/0.1",
        }
        token = config.optional_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.verify = config.verify_tls
        self.session.headers.update(headers)

    def _handle_response(self, response: Response) -> Any:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - network dependent
            raise APIClientError(str(exc)) from exc
        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - unexpected backend issue
            raise APIClientError("Backend did not return JSON") from exc

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_fixed(0.4),
        retry=retry_if_exception_type((requests.RequestException, APIClientError)),
    )
    def _get(self, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        url = urljoin(self.base_url, path)
        response = self.session.get(url, params=params, timeout=self.timeout, verify=self.verify)
        return self._handle_response(response)

    def fetch_overview_stats(self) -> JsonDict:
        return self._get("api/dashboard/overview")

    def fetch_persons(self) -> List[JsonDict]:
        payload = self._get("api/persons", params={"status": "known"})
        return payload.get("items", payload)

    def fetch_person_timeline(self, person_id: Optional[str]) -> List[JsonDict]:
        if not person_id:
            return []
        payload = self._get("api/sightings", params={"person_id": person_id, "range": "7d"})
        return payload.get("items", payload)

    def fetch_unknown_clusters(self, page: int = 1, flag_level: Optional[int] = None) -> JsonDict:
        params: Dict[str, Any] = {"page": page}
        if flag_level is not None:
            params["flag_level"] = flag_level
        return self._get("api/unknown-clusters", params=params)


class MockSentinelForgeAPI(BaseSentinelForgeAPI):
    """Offline-friendly mock that manufactures deterministic sample data."""

    def __init__(self) -> None:
        self._start = datetime.utcnow() - timedelta(hours=12)
        self._persons = self._build_persons()

    def _build_persons(self) -> List[JsonDict]:
        return [
            {
                "id": f"person-{idx:02d}",
                "name": f"Employee {idx:02d}",
                "role": random.choice(["Engineer", "Security", "Facilities"]),
                "consent_given": True,
                "last_seen": (self._start + timedelta(minutes=idx * 7)).isoformat(),
            }
            for idx in range(1, 6)
        ]

    def fetch_overview_stats(self) -> JsonDict:
        now = datetime.utcnow()
        unknown_count = random.randint(1, 5)
        return {
            "active_cameras": 4,
            "sightings_last_hour": random.randint(20, 60),
            "unknowns_pending": unknown_count,
            "flagged_events": random.randint(0, unknown_count),
            "heatmap": self._build_heatmap_matrix(now),
        }

    def _build_heatmap_matrix(self, now: datetime) -> List[List[int]]:
        base = [[random.randint(0, 5) for _ in range(7)] for _ in range(4)]
        base[0][now.weekday()] += 3
        return base

    def fetch_persons(self) -> List[JsonDict]:
        return self._persons

    def fetch_person_timeline(self, person_id: Optional[str]) -> List[JsonDict]:
        if not person_id:
            return []
        seed = sum(ord(c) for c in person_id)
        random.seed(seed)
        now = datetime.utcnow()
        return [
            {
                "timestamp": (now - timedelta(hours=idx)).isoformat(),
                "camera_id": f"cam-{random.randint(1,4):02d}",
                "confidence": round(random.uniform(0.82, 0.97), 2),
            }
            for idx in range(6)
        ]

    def fetch_unknown_clusters(self, page: int = 1, flag_level: Optional[int] = None) -> JsonDict:
        clusters = []
        for idx in range(1, 7):
            clusters.append(
                {
                    "cluster_id": f"unknown-{page}-{idx}",
                    "flag_level": flag_level or random.randint(0, 3),
                    "last_seen": (datetime.utcnow() - timedelta(minutes=idx * 5)).isoformat(),
                    "camera_id": f"cam-{idx:02d}",
                    "thumbnail_b64": self._random_thumbnail_stub(),
                }
            )
        return {"items": clusters, "page": page, "total": 60}

    def _random_thumbnail_stub(self) -> str:
        return "data:image/jpeg;base64," + "".join(random.choices(string.ascii_letters + string.digits, k=24))


def build_api_client(config: DashboardConfig) -> BaseSentinelForgeAPI:
    if config.use_mocks:
        return MockSentinelForgeAPI()
    return SentinelForgeAPI(config)
