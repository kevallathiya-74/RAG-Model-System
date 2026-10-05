from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str
    services: Dict[str, str]

class ErrorResponse(BaseModel):
    detail: str
