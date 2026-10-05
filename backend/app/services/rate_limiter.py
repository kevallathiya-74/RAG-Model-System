"""
Production-safe In-Process Rate Limiter Service.
Enforces memory-bounded, sliding-window rate limiting with authoritative identity resolution.
Reuses existing audit_service for denial logging. Zero external dependencies (No Redis).
"""
import math
import time
import threading
from collections import OrderedDict
from typing import Dict, List, Tuple, Optional
from fastapi import Request, HTTPException, Depends, status

from backend.app.config import settings
from backend.app.schemas.auth import AuthenticatedUser
from backend.app.auth.dependencies import get_current_user
from backend.app.services.audit_service import record_audit_event
from backend.app.middleware.request_context import get_request_id


class RateLimitException(HTTPException):
    """Specific exception for HTTP 429 Rate Limit exceeded."""
    def __init__(
        self,
        detail: str = "Too many requests. Please try again later.",
        retry_after: int = 60,
        request_id: str = ""
    ):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={
                "Retry-After": str(retry_after),
                "X-Request-ID": request_id
            }
        )
        self.retry_after = retry_after
        self.request_id = request_id


class InMemoryRateLimiter:
    """
    Sliding window in-process rate limiter with memory bounding and LRU eviction.
    Thread-safe via threading.Lock.
    """
    def __init__(self, max_keys: int = 10000):
        self._lock = threading.Lock()
        self._storage: OrderedDict[str, List[float]] = OrderedDict()
        self._max_keys = max_keys

    def is_rate_limited(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Check if request exceeds rate limit.
        Returns:
            (is_limited, retry_after_seconds)
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # 1. Clean storage if approaching key limit
            if len(self._storage) >= self._max_keys:
                self._prune_expired(now, window_seconds)

            # 2. Retrieve history for key
            timestamps = self._storage.get(key, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]

            if len(valid_timestamps) >= max_requests:
                oldest_valid = valid_timestamps[0]
                retry_after = max(1, math.ceil(oldest_valid + window_seconds - now))
                self._storage[key] = valid_timestamps
                self._storage.move_to_end(key)
                return True, retry_after

            # Under limit: record current timestamp
            valid_timestamps.append(now)
            self._storage[key] = valid_timestamps
            self._storage.move_to_end(key)
            return False, 0

    def _prune_expired(self, now: float, window_seconds: int) -> None:
        """Removes expired entries and enforces max_keys ceiling."""
        cutoff = now - window_seconds
        expired = [k for k, ts in self._storage.items() if not ts or ts[-1] <= cutoff]
        for k in expired:
            del self._storage[k]

        # If still over limit, pop oldest keys (LRU)
        while len(self._storage) >= self._max_keys:
            self._storage.popitem(last=False)

    def reset(self) -> None:
        """Clear all rate limit records (useful for testing)."""
        with self._lock:
            self._storage.clear()


# Global in-process rate limiter instance
limiter = InMemoryRateLimiter(max_keys=10000)


def extract_client_ip(request: Request) -> str:
    """
    Safely extract client IP address without blindly trusting spoofed X-Forwarded-For headers.
    Uses request.client.host with fallback.
    """
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def apply_rate_limit(
    request: Request,
    tier: str,
    max_requests: int,
    window_seconds: int,
    identity_key: str,
    audit_user_id: str
) -> None:
    """
    Core rate limit enforcement helper.
    Throws RateLimitException and logs audit denial if exceeded.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return

    req_id = get_request_id(request)
    is_limited, retry_after = limiter.is_rate_limited(identity_key, max_requests, window_seconds)

    if is_limited:
        # Audit rate limit breach using existing audit service
        record_audit_event(
            user_id=audit_user_id,
            action="rate_limit_exceeded",
            resource_type="rate_limiter",
            result="denied",
            metadata={
                "reason": "rate_limit_exceeded",
                "tier": tier,
                "limit": max_requests,
                "window_seconds": window_seconds,
                "request_id": req_id
            }
        )
        raise RateLimitException(
            detail="Too many requests. Please try again later.",
            retry_after=retry_after,
            request_id=req_id
        )


# FastAPI Dependency callables for each endpoint tier
def rate_limit_login(request: Request):
    """Rate limit for unauthenticated login attempts based strictly on client IP."""
    client_ip = extract_client_ip(request)
    key = f"ip:login:{client_ip}"
    apply_rate_limit(
        request=request,
        tier="login",
        max_requests=settings.RATE_LIMIT_LOGIN,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        identity_key=key,
        audit_user_id="anonymous"
    )


def rate_limit_chat(request: Request, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Rate limit for RAG/chat queries using authoritative authenticated identity."""
    key = f"user:chat:{current_user.user_id}:{current_user.tenant_id}"
    apply_rate_limit(
        request=request,
        tier="chat",
        max_requests=settings.RATE_LIMIT_CHAT,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        identity_key=key,
        audit_user_id=current_user.user_id
    )


def rate_limit_upload(request: Request, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Rate limit for document/image uploads using authoritative authenticated identity."""
    key = f"user:upload:{current_user.user_id}:{current_user.tenant_id}"
    apply_rate_limit(
        request=request,
        tier="upload",
        max_requests=settings.RATE_LIMIT_UPLOAD,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        identity_key=key,
        audit_user_id=current_user.user_id
    )


def rate_limit_api(request: Request, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Rate limit for general authenticated endpoints."""
    key = f"user:api:{current_user.user_id}:{current_user.tenant_id}"
    apply_rate_limit(
        request=request,
        tier="api",
        max_requests=settings.RATE_LIMIT_API,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        identity_key=key,
        audit_user_id=current_user.user_id
    )


def rate_limit_admin(request: Request, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Rate limit for administrative endpoints."""
    key = f"user:admin:{current_user.user_id}:{current_user.tenant_id}"
    apply_rate_limit(
        request=request,
        tier="admin",
        max_requests=settings.RATE_LIMIT_ADMIN,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        identity_key=key,
        audit_user_id=current_user.user_id
    )
