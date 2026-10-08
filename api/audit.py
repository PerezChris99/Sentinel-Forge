"""Request-level audit middleware for security-sensitive API activity."""

from __future__ import annotations

from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from api.auth import decode_token
from db.models import AuditLog


class RequestAuditMiddleware(BaseHTTPMiddleware):
    """Persist a compact audit event for mutating and sensitive API requests."""

    SENSITIVE_GET_PREFIXES = (
        "/api/persons",
        "/api/search",
        "/api/export",
        "/api/audit",
        "/api/privacy",
    )
    MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app, session_factory: Callable):
        super().__init__(app)
        self.session_factory = session_factory

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        should_log = request.method in self.MUTATING_METHODS or any(
            path.startswith(prefix) for prefix in self.SENSITIVE_GET_PREFIXES
        )
        if not should_log or path in {"/api/audit/logs"}:
            return response

        user_id = None
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                payload = decode_token(auth[7:].strip())
                user_id = payload.get("sub")
            except Exception:
                user_id = None

        try:
            from uuid import UUID

            async with self.session_factory() as session:
                session.add(
                    AuditLog(
                        user_id=UUID(user_id) if user_id else None,
                        action=f"http_{request.method.lower()}",
                        resource_type="api",
                        resource_id=path,
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"),
                        details={
                            "status_code": response.status_code,
                            "query": request.url.query[:500],
                        },
                    )
                )
                await session.commit()
        except Exception:
            # Audit failures must never turn a successful security operation
            # into a 500 response. Infrastructure logs should capture DB errors.
            pass

        return response
