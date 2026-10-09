from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.app.auth.jwt import decode_access_token
from backend.app.db.users import get_user_by_id_or_username
from backend.app.schemas.auth import AuthenticatedUser
from backend.app.services.audit_service import record_audit_event
from backend.app.middleware.request_context import get_request_id

security = HTTPBearer(auto_error=False)

def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AuthenticatedUser:
    req_id = get_request_id(request)
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"}
        )
        
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        record_audit_event(
            user_id="anonymous",
            action="authorization_denied",
            resource_type="auth",
            result="denied",
            metadata={"reason": "invalid_or_expired_token", "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"}
        )
        
    user_id = payload.get("sub")
    if not user_id:
        record_audit_event(
            user_id="anonymous",
            action="authorization_denied",
            resource_type="auth",
            result="denied",
            metadata={"reason": "malformed_token_claims", "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token claims.",
            headers={"WWW-Authenticate": "Bearer"}
        )
        
    # Resolve authoritative identity from DB
    db_user = get_user_by_id_or_username(user_id)
    if not db_user:
        record_audit_event(
            user_id=str(user_id)[:50],
            action="authorization_denied",
            resource_type="auth",
            result="denied",
            metadata={"reason": "user_not_found_in_db", "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity no longer exists.",
            headers={"WWW-Authenticate": "Bearer"}
        )
        
    if not db_user.get("is_active", True):
        record_audit_event(
            user_id=db_user["user_id"],
            action="authorization_denied",
            resource_type="auth",
            result="denied",
            metadata={"reason": "account_deactivated", "tenant_id": db_user.get("tenant_id"), "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated."
        )

    user_role = db_user.get("role")
    from backend.app.config import settings
    if user_role not in settings.CANONICAL_ROLES:
        record_audit_event(
            user_id=db_user["user_id"],
            action="authorization_denied",
            resource_type="auth",
            result="denied",
            metadata={"reason": "invalid_or_obsolete_role", "role": user_role, "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account has an obsolete or unrecognized role. Contact administrator."
        )

    return AuthenticatedUser(
        user_id=db_user["user_id"],
        name=db_user["name"],
        role=db_user["role"],
        tenant_id=db_user["tenant_id"],
        department=db_user.get("department"),
        is_active=db_user.get("is_active", True),
        db_id=db_user.get("db_id"),
        employee_id=db_user.get("employee_id"),
        employee_code=db_user.get("employee_code")
    )


def require_admin_user(
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> AuthenticatedUser:
    """Enforces authoritative Administrator role requirement on protected admin endpoints."""
    if current_user.role != "admin":
        req_id = get_request_id(request)
        record_audit_event(
            user_id=current_user.user_id,
            action="authorization_denied",
            resource_type="admin",
            result="denied",
            metadata={
                "reason": "admin_role_required",
                "attempted_role": current_user.role,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator authorization required."
        )
    return current_user

