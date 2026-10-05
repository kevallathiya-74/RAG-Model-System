"""
Secure Admin Audit Inspection API.
Enforces admin-only RBAC, strict tenant isolation, pagination, stable ordering,
and re-applies sanitization boundaries to prevent secret and PII leakage.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from database.connection import get_db_connection
from backend.app.schemas.auth import AuthenticatedUser
from backend.app.auth.dependencies import get_current_user
from backend.app.schemas.admin import PaginatedAuditResponse, AuditRecordItem
from backend.app.services.audit_service import record_audit_event, sanitize_metadata, sanitize_query
from backend.app.middleware.request_context import get_request_id
from backend.app.services.rate_limiter import rate_limit_admin

router = APIRouter(prefix="/api/admin", tags=["Admin Operations"])


@router.get(
    "/audit",
    response_model=PaginatedAuditResponse,
    summary="Inspect Security Audit Logs",
    description="Authorized for admin role only. Provides tenant-isolated, paginated audit records with strict sanitization.",
    dependencies=[Depends(rate_limit_admin)]
)
def get_admin_audit_logs(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    action: Optional[str] = Query(None, max_length=50, description="Optional action filter"),
    result: Optional[str] = Query(None, max_length=20, description="Optional result filter (authorized/denied/failed)"),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    req_id = get_request_id(request)

    # 1. Authoritative Backend Role Enforcement
    if current_user.role != "admin":
        record_audit_event(
            user_id=current_user.user_id,
            action="authorization_denied",
            resource_type="admin_audit",
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
            detail="Admin authorization required."
        )

    # 2. Strict Parameterized SQL Query with Tenant Isolation
    base_where = "WHERE (a.metadata->>'tenant_id' = %s OR u.tenant_id = %s)"
    params: List[Any] = [current_user.tenant_id, current_user.tenant_id]

    if action:
        base_where += " AND a.action = %s"
        params.append(action.strip())

    if result:
        base_where += " AND a.result = %s"
        params.append(result.strip())

    count_sql = f"""
        SELECT COUNT(DISTINCT a.id)
        FROM audit_logs a
        LEFT JOIN users u ON a.user_id = u.user_id
        {base_where};
    """

    offset = (page - 1) * page_size
    fetch_sql = f"""
        SELECT 
            a.id,
            a.user_id,
            a.action,
            a.resource_type,
            a.resource_id,
            a.query,
            a.result,
            a.timestamp,
            a.latency_ms,
            a.metadata
        FROM audit_logs a
        LEFT JOIN users u ON a.user_id = u.user_id
        {base_where}
        ORDER BY a.timestamp DESC, a.id DESC
        LIMIT %s OFFSET %s;
    """
    fetch_params = list(params) + [page_size, offset]

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Execute Count
            cur.execute(count_sql, tuple(params))
            total_items = cur.fetchone()[0]

            # Execute Fetch
            cur.execute(fetch_sql, tuple(fetch_params))
            rows = cur.fetchall()

        items: List[AuditRecordItem] = []
        for r in rows:
            r_id, u_id, act, res_type, res_id, q_text, res_status, ts, lat_ms, meta = r
            
            # Apply secondary sanitization to prevent sensitive data leakage
            safe_meta = sanitize_metadata(meta or {})
            safe_q = sanitize_query(q_text)
            corr_id = safe_meta.get("request_id") if isinstance(safe_meta, dict) else None

            items.append(
                AuditRecordItem(
                    id=r_id,
                    timestamp=ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    user_id=u_id,
                    action=act,
                    resource_type=res_type,
                    resource_id=res_id,
                    query=safe_q,
                    result=res_status,
                    latency_ms=lat_ms,
                    request_id=corr_id,
                    metadata=safe_meta if isinstance(safe_meta, dict) else {}
                )
            )

        total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1

        # Audit successful admin audit view
        record_audit_event(
            user_id=current_user.user_id,
            action="admin_audit_inspect",
            resource_type="admin_audit",
            result="authorized",
            metadata={
                "page": page,
                "page_size": page_size,
                "returned_count": len(items),
                "total_items": total_items,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )

        return PaginatedAuditResponse(
            items=items,
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages
        )
    except HTTPException:
        raise
    except Exception as e:
        record_audit_event(
            user_id=current_user.user_id,
            action="admin_audit_inspect_failed",
            resource_type="admin_audit",
            result="failed",
            metadata={
                "error_type": type(e).__name__,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit records."
        )
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
