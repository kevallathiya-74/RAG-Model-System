from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class AuditRecordItem(BaseModel):
    id: int
    timestamp: str
    user_id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    query: Optional[str] = None
    result: str
    latency_ms: Optional[int] = None
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class PaginatedAuditResponse(BaseModel):
    items: List[AuditRecordItem]
    page: int
    page_size: int
    total_items: int
    total_pages: int
