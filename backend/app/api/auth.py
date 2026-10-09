from fastapi import APIRouter, HTTPException, Request, Depends, status
from backend.app.schemas.auth import LoginRequest, LoginResponse, UserSummary
from backend.app.db.users import get_user_by_id_or_username
from backend.app.auth.password import verify_password
from backend.app.auth.jwt import create_access_token
from backend.app.config import settings
from backend.app.services.audit_service import record_audit_event
from backend.app.middleware.request_context import get_request_id
from backend.app.services.rate_limiter import rate_limit_login

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/login", response_model=LoginResponse, summary="Authenticate user and obtain JWT token", dependencies=[Depends(rate_limit_login)])
def login(req: LoginRequest, request: Request):
    req_id = get_request_id(request)
    username = req.username.strip()
    password = req.password.strip()
    
    if not username or not password:
        record_audit_event(
            user_id="anonymous",
            action="login_failure",
            resource_type="auth",
            result="denied",
            metadata={"reason": "missing_credentials", "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required."
        )
        
    user_db = get_user_by_id_or_username(username)
    if not user_db:
        record_audit_event(
            user_id=username[:50],
            action="login_failure",
            resource_type="auth",
            result="denied",
            metadata={"reason": "user_not_found", "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )
        
    if not user_db.get("is_active", True):
        record_audit_event(
            user_id=user_db["user_id"],
            action="login_failure",
            resource_type="auth",
            result="denied",
            metadata={"reason": "account_deactivated", "tenant_id": user_db.get("tenant_id"), "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated."
        )

    if user_db.get("role") not in settings.CANONICAL_ROLES:
        record_audit_event(
            user_id=user_db["user_id"],
            action="login_failure",
            resource_type="auth",
            result="denied",
            metadata={"reason": "obsolete_or_invalid_role", "role": user_db.get("role"), "tenant_id": user_db.get("tenant_id"), "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account has an obsolete or unrecognized role. Contact administrator."
        )
        
    pwd_hash = user_db.get("password_hash")
    if not pwd_hash or not verify_password(password, pwd_hash):
        record_audit_event(
            user_id=user_db["user_id"],
            action="login_failure",
            resource_type="auth",
            result="denied",
            metadata={"reason": "invalid_password", "tenant_id": user_db.get("tenant_id"), "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )
        
    token = create_access_token(
        user_id=user_db["user_id"],
        role=user_db["role"],
        tenant_id=user_db["tenant_id"],
        department=user_db.get("department")
    )
    
    user_summary = UserSummary(
        user_id=user_db["user_id"],
        name=user_db["name"],
        role=user_db["role"],
        tenant_id=user_db["tenant_id"],
        department=user_db.get("department")
    )
    
    # Audit log success: NEVER log passwords or raw JWT tokens
    record_audit_event(
        user_id=user_db["user_id"],
        action="login_success",
        resource_type="auth",
        result="authorized",
        metadata={
            "tenant_id": user_db["tenant_id"],
            "role": user_db["role"],
            "department": user_db.get("department"),
            "request_id": req_id
        }
    )
    
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        user=user_summary
    )
