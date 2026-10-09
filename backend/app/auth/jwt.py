import time
import jwt
from typing import Dict, Any, Optional
from backend.app.config import settings

def create_access_token(user_id: str, role: str, tenant_id: str, department: Optional[str] = None) -> str:
    now = int(time.time())
    expires_at = now + (settings.JWT_EXPIRE_MINUTES * 60)
    
    payload = {
        "sub": user_id,
        "role": role,
        "tenant_id": tenant_id,
        "department": department,
        "iat": now,
        "exp": expires_at
    }
    
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or not isinstance(token, str):
        return None
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat"]}
        )
        return payload
    except Exception:
        return None

