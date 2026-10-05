"""
Audit logging service for Secure Multi-Modal RAG System.
Reuses existing PostgreSQL audit_logs table with JSONB metadata.
Enforces strict sanitization boundaries to prevent secret and PII leakage.
"""
import json
import logging
import re
from typing import Dict, Any, Optional
from database.connection import get_db_connection

logger = logging.getLogger("audit")

# Denied keys: never persist values of these fields in audit metadata
SENSITIVE_KEYS = {
    "password", "token", "access_token", "authorization", "api_key",
    "secret", "jwt_secret", "postgres_password", "qdrant_api_key",
    "bank_details", "tax_code", "contact_numbers", "emergency_contacts",
    "address", "salary_amount", "salary_bonus", "pwd_hash", "password_hash"
}

def sanitize_metadata(data: Any, depth: int = 0) -> Any:
    """
    Recursively sanitize dictionary/list metadata to redact sensitive values
    and strip full prompt/document text payloads.
    """
    if depth > 5:
        return "[DEPTH_EXCEEDED]"
        
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            key_lower = str(k).lower().strip()
            if key_lower in SENSITIVE_KEYS or any(s in key_lower for s in ("password", "secret", "token", "api_key")):
                sanitized[k] = "[REDACTED]"
            elif key_lower in ("full_document_text", "document_text", "prompt", "full_prompt", "raw_context"):
                sanitized[k] = "[OMITTED_TEXT]"
            elif isinstance(v, (dict, list)):
                sanitized[k] = sanitize_metadata(v, depth + 1)
            elif isinstance(v, (str, int, float, bool)) or v is None:
                if isinstance(v, str) and len(v) > 500:
                    sanitized[k] = v[:500] + "... [TRUNCATED]"
                else:
                    sanitized[k] = v
            else:
                sanitized[k] = str(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_metadata(item, depth + 1) for item in data[:50]]
    elif isinstance(data, str) and len(data) > 500:
        return data[:500] + "... [TRUNCATED]"
    return data

def sanitize_query(query: Optional[str]) -> Optional[str]:
    """Sanitize and truncate query string to prevent storing excessive or sensitive text."""
    if not query:
        return None
    q = query.strip()
    # Redact common credential patterns in query if present
    q = re.sub(r'(?i)(password|token|bearer|api[_-]?key)\s*[:=]\s*\S+', r'\1=[REDACTED]', q)
    if len(q) > 500:
        return q[:500] + "..."
    return q

def record_audit_event(
    user_id: str,
    action: str,
    resource_type: str,
    result: str,
    resource_id: Optional[str] = None,
    query: Optional[str] = None,
    latency_ms: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Writes an audit event into PostgreSQL audit_logs table.
    Fail-safe: Logs warning on failure but does not raise exception to calling workflow.
    """
    safe_user_id = str(user_id)[:50] if user_id else "anonymous"
    safe_action = str(action)[:50]
    safe_resource_type = str(resource_type)[:50]
    safe_result = str(result)[:20]
    safe_resource_id = str(resource_id)[:50] if resource_id else None
    safe_query = sanitize_query(query)
    safe_meta = sanitize_metadata(metadata or {})
    
    insert_sql = """
        INSERT INTO audit_logs (
            user_id, action, resource_type, resource_id,
            query, result, latency_ms, metadata
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s::jsonb
        );
    """
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                insert_sql,
                (
                    safe_user_id,
                    safe_action,
                    safe_resource_type,
                    safe_resource_id,
                    safe_query,
                    safe_result,
                    latency_ms,
                    json.dumps(safe_meta)
                )
            )
        conn.commit()
        return True
    except Exception as e:
        logger.warning(f"Audit log write failed for user {safe_user_id}, action {safe_action}: {e}")
        return False
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
