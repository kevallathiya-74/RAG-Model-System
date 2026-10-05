from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000, description="Natural language user question", example="What is the policy guidelines summary?")

class Citation(BaseModel):
    source_id: str
    chunk_id: Optional[str] = None
    source_type: str
    filename: Optional[str] = None
    page_number: Optional[int] = None
    image_id: Optional[str] = None
    table: Optional[str] = None
    query_type: Optional[str] = None
    record_ids: Optional[List[str]] = None
    fields: Optional[List[str]] = None
    tenant_id: Optional[str] = None
    authorized: Optional[bool] = None

class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
    retrieval_count: int
    grounded: bool
    latencies: Dict[str, float]
