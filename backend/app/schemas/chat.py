from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000, description="Natural language user question", example="What is the policy guidelines summary?")

class Citation(BaseModel):
    source_id: str
    chunk_id: str
    source_type: str
    filename: str
    page_number: Optional[int] = None
    image_id: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
    retrieval_count: int
    grounded: bool
    latencies: Dict[str, float]
