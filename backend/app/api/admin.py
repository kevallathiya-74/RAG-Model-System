"""
Secure Admin Audit Inspection API.
Enforces admin-only RBAC, strict tenant isolation, pagination, stable ordering,
and re-applies sanitization boundaries to prevent secret and PII leakage.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from database.connection import get_db_connection
from backend.app.schemas.auth import AuthenticatedUser
from backend.app.auth.dependencies import get_current_user, require_admin_user
from backend.app.config import settings
from backend.app.schemas.admin import (
    PaginatedAuditResponse,
    AuditRecordItem,
    UserAdminItem,
    UserStatusUpdateRequest,
    UserRoleUpdateRequest,
    DocumentAdminItem,
    DocumentPermissionGrantRequest
)
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
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)

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


@router.get(
    "/users",
    response_model=List[UserAdminItem],
    summary="List Tenant Users",
    description="Authorized for admin role only. Lists users belonging to current administrator's tenant.",
    dependencies=[Depends(rate_limit_admin)]
)
def list_admin_users(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
            SELECT u.user_id, u.name, r.name as role_name, NULL as dept_name,
                   u.tenant_id, u.is_active, u.created_at
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.tenant_id = %s
            ORDER BY u.id ASC;
            """
            cur.execute(query, (current_user.tenant_id,))
            rows = cur.fetchall()

        items = [
            UserAdminItem(
                user_id=r[0],
                name=r[1],
                role=r[2],
                department=r[3],
                tenant_id=r[4],
                is_active=r[5],
                created_at=r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6])
            )
            for r in rows
        ]

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_users_list",
            resource_type="admin_users",
            result="authorized",
            metadata={
                "returned_count": len(items),
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        return items
    finally:
        conn.close()


@router.patch(
    "/users/{target_user_id}/status",
    summary="Update User Active Status",
    description="Authorized for admin role only. Activates or deactivates a user account within the tenant.",
    dependencies=[Depends(rate_limit_admin)]
)
def update_user_status(
    target_user_id: str,
    req: UserStatusUpdateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    if target_user_id == current_user.user_id and not req.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot deactivate their own account."
        )

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Prevent deactivation of the last active administrator in the tenant
            if not req.is_active:
                cur.execute("""
                    SELECT r.name FROM users u
                    JOIN roles r ON u.role_id = r.id
                    WHERE u.user_id = %s AND u.tenant_id = %s;
                """, (target_user_id, current_user.tenant_id))
                t_role = cur.fetchone()
                if t_role and t_role[0] == "admin":
                    cur.execute("""
                        SELECT COUNT(*) FROM users u
                        JOIN roles r ON u.role_id = r.id
                        WHERE r.name = 'admin' AND u.tenant_id = %s AND u.is_active = TRUE;
                    """, (current_user.tenant_id,))
                    active_admins = cur.fetchone()[0]
                    if active_admins <= 1:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Cannot deactivate the last remaining active administrator in this tenant."
                        )

            cur.execute(
                "UPDATE users SET is_active = %s WHERE user_id = %s AND tenant_id = %s RETURNING id;",
                (req.is_active, target_user_id, current_user.tenant_id)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{target_user_id}' not found in this tenant."
                )
        conn.commit()

        action_desc = "activate_user" if req.is_active else "deactivate_user"
        record_audit_event(
            user_id=current_user.user_id,
            action=action_desc,
            resource_type="user",
            resource_id=target_user_id,
            result="authorized",
            metadata={
                "is_active": req.is_active,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        return {"status": "success", "user_id": target_user_id, "is_active": req.is_active}
    finally:
        conn.close()


@router.patch(
    "/users/{target_user_id}/role",
    summary="Update User Role",
    description="Authorized for admin role only. Changes role of a user to one of the canonical 4 roles.",
    dependencies=[Depends(rate_limit_admin)]
)
def update_user_role(
    target_user_id: str,
    req: UserRoleUpdateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    new_role = req.role.strip().lower()

    if new_role not in settings.CANONICAL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{new_role}'. Must be one of: {', '.join(settings.CANONICAL_ROLES)}"
        )

    if target_user_id == current_user.user_id and new_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot demote their own account role."
        )

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Prevent demoting the last active administrator in the tenant
            if new_role != "admin":
                cur.execute("""
                    SELECT r.name FROM users u
                    JOIN roles r ON u.role_id = r.id
                    WHERE u.user_id = %s AND u.tenant_id = %s;
                """, (target_user_id, current_user.tenant_id))
                t_role = cur.fetchone()
                if t_role and t_role[0] == "admin":
                    cur.execute("""
                        SELECT COUNT(*) FROM users u
                        JOIN roles r ON u.role_id = r.id
                        WHERE r.name = 'admin' AND u.tenant_id = %s AND u.is_active = TRUE;
                    """, (current_user.tenant_id,))
                    active_admins = cur.fetchone()[0]
                    if active_admins <= 1:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Cannot demote the last remaining active administrator in this tenant."
                        )

            cur.execute("SELECT id FROM roles WHERE name = %s;", (new_role,))
            r_row = cur.fetchone()
            if not r_row:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Role '{new_role}' does not exist in roles table."
                )
            role_id = r_row[0]

            cur.execute(
                "UPDATE users SET role_id = %s WHERE user_id = %s AND tenant_id = %s RETURNING id;",
                (role_id, target_user_id, current_user.tenant_id)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{target_user_id}' not found in this tenant."
                )
        conn.commit()

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_change_role",
            resource_type="user",
            resource_id=target_user_id,
            result="authorized",
            metadata={
                "new_role": new_role,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        return {"status": "success", "user_id": target_user_id, "role": new_role}
    finally:
        conn.close()


@router.get(
    "/documents",
    response_model=List[DocumentAdminItem],
    summary="List Tenant Documents & Images with ACLs",
    description="Authorized for admin role only. Lists PDF documents and image assets with their associated ACL grants.",
    dependencies=[Depends(rate_limit_admin)]
)
def list_admin_documents(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'image_permissions' LIMIT 1;")
            has_img_perm = cur.fetchone() is not None

            if has_img_perm:
                cur.execute("""
                SELECT 
                    d.document_id,
                    d.filename,
                    d.source_type,
                    NULL as department,
                    d.sensitivity,
                    d.status,
                    d.chunk_count,
                    owner.user_id as owner_id,
                    COALESCE(array_agg(DISTINCT r.name) FILTER (WHERE r.name IS NOT NULL), '{}') as allowed_roles,
                    COALESCE(array_agg(DISTINCT u.user_id) FILTER (WHERE u.user_id IS NOT NULL), '{}') as allowed_users
                FROM documents d
                LEFT JOIN users owner ON d.owner_user_id = owner.id
                LEFT JOIN document_permissions dp ON d.id = dp.document_id
                LEFT JOIN roles r ON dp.role_id = r.id
                LEFT JOIN users u ON dp.user_id = u.id
                WHERE d.tenant_id = %s
                GROUP BY d.id, owner.user_id
                UNION ALL
                SELECT 
                    i.image_id as document_id,
                    i.filename,
                    i.source_type,
                    NULL as department,
                    i.sensitivity,
                    i.status,
                    i.chunk_count,
                    owner.user_id as owner_id,
                    COALESCE(array_agg(DISTINCT r.name) FILTER (WHERE r.name IS NOT NULL), '{}') as allowed_roles,
                    COALESCE(array_agg(DISTINCT u.user_id) FILTER (WHERE u.user_id IS NOT NULL), '{}') as allowed_users
                FROM images i
                LEFT JOIN users owner ON i.owner_user_id = owner.id
                LEFT JOIN image_permissions ip ON i.id = ip.image_id
                LEFT JOIN roles r ON ip.role_id = r.id
                LEFT JOIN users u ON ip.user_id = u.id
                WHERE i.tenant_id = %s
                GROUP BY i.id, owner.user_id
                ORDER BY document_id ASC;
                """, (current_user.tenant_id, current_user.tenant_id))
            else:
                cur.execute("""
                SELECT 
                    d.document_id,
                    d.filename,
                    d.source_type,
                    NULL as department,
                    d.sensitivity,
                    d.status,
                    d.chunk_count,
                    owner.user_id as owner_id,
                    COALESCE(array_agg(DISTINCT r.name) FILTER (WHERE r.name IS NOT NULL), '{}') as allowed_roles,
                    COALESCE(array_agg(DISTINCT u.user_id) FILTER (WHERE u.user_id IS NOT NULL), '{}') as allowed_users
                FROM documents d
                LEFT JOIN users owner ON d.owner_user_id = owner.id
                LEFT JOIN document_permissions dp ON d.id = dp.document_id
                LEFT JOIN roles r ON dp.role_id = r.id
                LEFT JOIN users u ON dp.user_id = u.id
                WHERE d.tenant_id = %s
                GROUP BY d.id, owner.user_id
                UNION ALL
                SELECT 
                    i.image_id as document_id,
                    i.filename,
                    i.source_type,
                    NULL as department,
                    i.sensitivity,
                    i.status,
                    i.chunk_count,
                    owner.user_id as owner_id,
                    '{}'::varchar[] as allowed_roles,
                    '{}'::varchar[] as allowed_users
                FROM images i
                LEFT JOIN users owner ON i.owner_user_id = owner.id
                WHERE i.tenant_id = %s
                GROUP BY i.id, owner.user_id
                ORDER BY document_id ASC;
                """, (current_user.tenant_id, current_user.tenant_id))
            rows = cur.fetchall()

        items = [
            DocumentAdminItem(
                document_id=r[0],
                filename=r[1],
                source_type=r[2],
                department=r[3],
                sensitivity=r[4],
                status=r[5],
                chunk_count=r[6],
                owner_user_id=r[7],
                allowed_roles=list(r[8]),
                allowed_users=list(r[9])
            )
            for r in rows
        ]

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_documents_list",
            resource_type="admin_documents",
            result="authorized",
            metadata={
                "returned_count": len(items),
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        return items
    finally:
        conn.close()


@router.post(
    "/documents/{document_id}/permissions",
    summary="Grant Document or Image Permission",
    description="Authorized for admin role only. Adds role or user permission grant to a document or image without duplicates.",
    dependencies=[Depends(rate_limit_admin)]
)
def grant_document_permission(
    document_id: str,
    req: DocumentPermissionGrantRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    if not req.target_role and not req.target_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must specify either 'target_role' or 'target_user_id'."
        )

    if req.target_role and req.target_role not in settings.CANONICAL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid target role '{req.target_role}'. Must be one of: {', '.join(settings.CANONICAL_ROLES)}"
        )

    is_image = document_id.startswith("IMG-")
    target_table = "images" if is_image else "documents"
    id_col = "image_id" if is_image else "document_id"
    perm_table = "image_permissions" if is_image else "document_permissions"
    fk_col = "image_id" if is_image else "document_id"

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if is_image:
                cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'image_permissions' LIMIT 1;")
                if not cur.fetchone():
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Image permissions table is pending database migration 004."
                    )

            cur.execute(f"SELECT id FROM {target_table} WHERE {id_col} = %s AND tenant_id = %s;", (document_id, current_user.tenant_id))
            doc_row = cur.fetchone()
            if not doc_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Resource '{document_id}' not found.")
            record_pk = doc_row[0]

            role_fk = None
            if req.target_role:
                cur.execute("SELECT id FROM roles WHERE name = %s;", (req.target_role,))
                r_row = cur.fetchone()
                if r_row:
                    role_fk = r_row[0]

            user_fk = None
            if req.target_user_id:
                cur.execute("SELECT id FROM users WHERE user_id = %s AND tenant_id = %s;", (req.target_user_id, current_user.tenant_id))
                u_row = cur.fetchone()
                if not u_row:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{req.target_user_id}' not found.")
                user_fk = u_row[0]

            # Idempotent permission insertion preventing duplicate grants
            cur.execute(
                f"""
                INSERT INTO {perm_table} ({fk_col}, role_id, user_id, permission)
                SELECT %s, %s, %s, 'read'
                WHERE NOT EXISTS (
                    SELECT 1 FROM {perm_table}
                    WHERE {fk_col} = %s
                      AND (role_id = %s OR (role_id IS NULL AND %s IS NULL))
                      AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
                );
                """,
                (record_pk, role_fk, user_fk, record_pk, role_fk, role_fk, user_fk, user_fk)
            )
        conn.commit()

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_grant_permission",
            resource_type="image" if is_image else "document",
            resource_id=document_id,
            result="authorized",
            metadata={
                "granted_role": req.target_role,
                "granted_user": req.target_user_id,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        return {"status": "success", "document_id": document_id, "granted_role": req.target_role, "granted_user": req.target_user_id}
    finally:
        conn.close()

