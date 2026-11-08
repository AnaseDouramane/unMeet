"""Request id, access log and rate limiting for the public API."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("unmeet.api")

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_EXEMPT_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class SlidingWindowRateLimiter:
    """Per-key sliding window kept in process memory.

    Good for one API instance. Behind several instances each one enforces its own window, so
    the effective limit is multiplied; move this to Redis when scaling horizontally.
    """

    def __init__(self, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_prune = clock()

    def check(self, key: str, limit: int) -> RateLimitDecision:
        now = self._clock()
        with self._lock:
            if now - self._last_prune > self._window:
                self._prune(now)
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= limit:
                retry = max(1, int(self._window - (now - hits[0])) + 1)
                return RateLimitDecision(False, limit, 0, retry)
            hits.append(now)
            return RateLimitDecision(True, limit, limit - len(hits), 0)

    def _prune(self, now: float) -> None:
        for key in [
            k for k, hits in self._hits.items() if not hits or now - hits[-1] >= self._window
        ]:
            del self._hits[key]
        self._last_prune = now


def client_identity(request: Request, trust_proxy: bool) -> str:
    """A stable, non-reversible id for rate limiting and logs (API key hash, else IP)."""
    key = request.headers.get("X-API-Key")
    authorization = request.headers.get("Authorization", "")
    if key is None and authorization.lower().startswith("bearer "):
        key = authorization[7:].strip()
    if key:
        return "key:" + hashlib.sha256(key.encode()).hexdigest()[:16]
    host = request.client.host if request.client else "unknown"
    if trust_proxy:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            host = forwarded.split(",")[0].strip() or host
    return "ip:" + host


class ApiMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        read_limit_per_minute: int,
        write_limit_per_minute: int,
        trust_proxy: bool = False,
        limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:
        super().__init__(app)
        self._read_limit = read_limit_per_minute
        self._write_limit = write_limit_per_minute
        self._trust_proxy = trust_proxy
        self._limiter = limiter or SlidingWindowRateLimiter()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        identity = client_identity(request, self._trust_proxy)
        request.state.request_id = request_id
        request.state.client_identity = identity
        started = time.perf_counter()
        response: Response

        decision = None
        if request.url.path not in _EXEMPT_PATHS and request.method != "OPTIONS":
            is_write = request.method in _WRITE_METHODS
            limit = self._write_limit if is_write else self._read_limit
            if limit > 0:
                decision = self._limiter.check(f"{'w' if is_write else 'r'}:{identity}", limit)

        if decision is not None and not decision.allowed:
            response = JSONResponse(
                status_code=429,
                content={
                    "code": "rate_limited",
                    "message": "too many requests, slow down",
                    "details": {"retry_after_seconds": decision.retry_after_seconds},
                },
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
        else:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception(
                    "unhandled error",
                    extra={"request_id": request_id, "path": request.url.path},
                )
                raise
        if decision is not None:
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "client": identity,
            },
        )
        return response
