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

class UserAdminItem(BaseModel):
    user_id: str
    name: str
    role: str
    department: Optional[str] = None
    tenant_id: str
    is_active: bool
    created_at: Optional[str] = None

class UserStatusUpdateRequest(BaseModel):
    is_active: bool

class UserRoleUpdateRequest(BaseModel):
    role: str

class DocumentAdminItem(BaseModel):
    document_id: str
    filename: str
    source_type: str
    department: Optional[str] = None
    sensitivity: str
    status: str
    chunk_count: int
    allowed_roles: List[str] = Field(default_factory=list)
    allowed_users: List[str] = Field(default_factory=list)
    owner_user_id: Optional[str] = None

class DocumentPermissionGrantRequest(BaseModel):
    target_role: Optional[str] = None
    target_user_id: Optional[str] = None

