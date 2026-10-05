from typing import Optional
from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    username: str = Field(..., description="User ID or username (e.g. U001, U002)", example="U001")
    password: str = Field(..., description="User password", example="Password123!")

class UserSummary(BaseModel):
    user_id: str
    name: str
    role: str
    tenant_id: str
    department: Optional[str] = None

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserSummary

class AuthenticatedUser(BaseModel):
    user_id: str
    name: str
    role: str
    tenant_id: str
    department: Optional[str] = None
    is_active: bool = True
    db_id: Optional[int] = None
    employee_id: Optional[int] = None
    employee_code: Optional[str] = None
