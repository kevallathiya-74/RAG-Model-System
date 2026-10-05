from typing import List, Optional
from pydantic import BaseModel, Field

class DocumentUploadResponse(BaseModel):
    document_id: str = Field(..., description="Unique document or image identifier")
    status: str = Field(..., description="Ingestion lifecycle status: pending, processing, completed, or failed")
    filename: str = Field(..., description="Original sanitized filename")
    source_type: str = Field(..., description="Source format: pdf or image")
    chunk_count: int = Field(0, description="Total chunks indexed into Qdrant")
    message: Optional[str] = Field(None, description="Optional diagnostic message")

class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    source_type: str
    tenant_id: str
    status: str
    chunk_count: int
    created_at: Optional[str] = None

class DocumentDetail(BaseModel):
    document_id: str
    filename: str
    source_type: str
    tenant_id: str
    department: Optional[str] = None
    sensitivity: str = "internal"
    status: str
    chunk_count: int
    file_size: Optional[int] = None
    content_hash: Optional[str] = None
    created_at: Optional[str] = None

class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentSummary]
