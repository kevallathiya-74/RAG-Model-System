import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.middleware.request_context import RequestContextMiddleware, get_request_id
from backend.app.api.auth import router as auth_router
from backend.app.api.chat import router as chat_router
from backend.app.api.health import router as health_router
from backend.app.api.documents import router as documents_router
from backend.app.api.admin import router as admin_router

logger = logging.getLogger("api")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Production-grade Secure Multi-Modal RAG API with Retrieval-Layer JWT Authorization & Grounded Citations.",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None
)

# 1. Request context, timing, and security headers middleware
app.add_middleware(RequestContextMiddleware)

# 2. Hardened CORS configuration (configuration-driven allowed origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"]
)

# Include Routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(admin_router)

from backend.app.services.rate_limiter import RateLimitException

@app.exception_handler(RateLimitException)
async def rate_limit_exception_handler(request: Request, exc: RateLimitException):
    req_id = exc.request_id or get_request_id(request)
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": exc.detail,
            "request_id": req_id
        },
        headers={
            "Retry-After": str(exc.retry_after),
            "X-Request-ID": req_id
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    req_id = get_request_id(request)
    logger.error(f"Unhandled exception on {request.method} {request.url.path} [Request-ID: {req_id}]: {exc}", exc_info=settings.DEBUG)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error.",
            "request_id": req_id
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True, reload_dirs=["backend", "database"])
