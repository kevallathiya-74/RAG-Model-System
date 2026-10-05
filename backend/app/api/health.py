import urllib.request
import json
from fastapi import APIRouter, Response, status
from backend.app.schemas.common import HealthResponse
from backend.app.config import settings
from database.connection import get_db_connection
from scripts.secure_rag import get_qdrant_client

router = APIRouter(prefix="/api", tags=["Health Checks"])

@router.get("/health", response_model=HealthResponse, summary="Check API services status")
def health_check(response: Response):
    services = {
        "database": "unknown",
        "qdrant": "unknown",
        "ollama": "unknown"
    }
    
    # 1. Check PostgreSQL
    try:
        conn = get_db_connection()
        conn.close()
        services["database"] = "healthy"
    except Exception:
        services["database"] = "unhealthy"
        
    # 2. Check Qdrant Cloud
    try:
        qc = get_qdrant_client()
        if qc.collection_exists(settings.QDRANT_COLLECTION):
            services["qdrant"] = "healthy"
        else:
            services["qdrant"] = "degraded"
    except Exception:
        services["qdrant"] = "unhealthy"
        
    # 3. Check local Ollama
    try:
        url = f"{settings.OLLAMA_URL}/api/tags"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            if resp.status == 200:
                services["ollama"] = "healthy"
            else:
                services["ollama"] = "unhealthy"
    except Exception:
        services["ollama"] = "unhealthy"
        
    all_healthy = all(v == "healthy" for v in services.values())
    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        services=services
    )

@router.get("/health/ready", response_model=HealthResponse, summary="Check if API is ready to accept requests")
def readiness_check(response: Response):
    return health_check(response)
