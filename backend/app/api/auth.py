from fastapi import APIRouter, HTTPException, status
from backend.app.schemas.auth import LoginRequest, LoginResponse, UserSummary
from backend.app.db.users import get_user_by_id_or_username
from backend.app.auth.password import verify_password
from backend.app.auth.jwt import create_access_token
from backend.app.config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/login", response_model=LoginResponse, summary="Authenticate user and obtain JWT token")
def login(req: LoginRequest):
    username = req.username.strip()
    password = req.password.strip()
    
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required."
        )
        
    user_db = get_user_by_id_or_username(username)
    if not user_db:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )
        
    if not user_db.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated."
        )
        
    pwd_hash = user_db.get("password_hash")
    if not pwd_hash or not verify_password(password, pwd_hash):
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
    
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        user=user_summary
    )
