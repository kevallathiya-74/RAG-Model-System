"""
Request Context & Security Headers Middleware.
Attaches validated X-Request-ID, calculates process latency, and injects HTTP security headers.
"""
import time
import uuid
import re
from typing import Callable, Awaitable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

SAFE_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # 1. Validate or generate request correlation ID
        incoming_id = request.headers.get("X-Request-ID")
        if incoming_id and SAFE_REQUEST_ID_RE.match(incoming_id):
            request_id = incoming_id
        else:
            request_id = uuid.uuid4().hex
            
        request.state.request_id = request_id
        
        # 2. Timing
        start_time = time.perf_counter()
        
        # 3. Process request
        response = await call_next(request)
        
        # 4. Attach Traceability & Latency headers
        process_time = time.perf_counter() - start_time
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.6f}"
        
        # 5. Production Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            
        return response

def get_request_id(request: Request) -> str:
    """Safely retrieves request_id from request.state or returns a fallback."""
    return getattr(request.state, "request_id", "unknown_request_id")
