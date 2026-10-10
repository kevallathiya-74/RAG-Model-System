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
    DocumentPermissionGrantRequest,
    ReceiptAssignmentItem,
    ReceiptAssignmentCreateRequest,
    FacultyAssignmentItem,
    FacultyAssignmentCreateRequest
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


@router.delete(
    "/documents/{document_id}/permissions",
    summary="Revoke Document or Image Permission",
    description="Authorized for admin role only. Revokes role or user permission grant from a document or image.",
    dependencies=[Depends(rate_limit_admin)]
)
def revoke_document_permission(
    document_id: str,
    request: Request,
    target_role: Optional[str] = Query(None, description="Role to revoke permission from"),
    target_user_id: Optional[str] = Query(None, description="User ID to revoke permission from"),
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    if not target_role and not target_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must specify either 'target_role' or 'target_user_id'."
        )

    if target_role and target_role not in settings.CANONICAL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid target role '{target_role}'. Must be one of: {', '.join(settings.CANONICAL_ROLES)}"
        )

    is_image = document_id.startswith("IMG-")
    target_table = "images" if is_image else "documents"
    id_col = "image_id" if is_image else "document_id"
    perm_table = "image_permissions" if is_image else "document_permissions"
    fk_col = "image_id" if is_image else "document_id"

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT id FROM {target_table} WHERE {id_col} = %s AND tenant_id = %s;", (document_id, current_user.tenant_id))
            doc_row = cur.fetchone()
            if not doc_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Resource '{document_id}' not found.")
            record_pk = doc_row[0]

            deleted_count = 0
            if target_role:
                cur.execute("SELECT id FROM roles WHERE name = %s;", (target_role,))
                r_row = cur.fetchone()
                if r_row:
                    cur.execute(f"DELETE FROM {perm_table} WHERE {fk_col} = %s AND role_id = %s;", (record_pk, r_row[0]))
                    deleted_count += cur.rowcount

            if target_user_id:
                cur.execute("SELECT id FROM users WHERE user_id = %s AND tenant_id = %s;", (target_user_id, current_user.tenant_id))
                u_row = cur.fetchone()
                if not u_row:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{target_user_id}' not found.")
                cur.execute(f"DELETE FROM {perm_table} WHERE {fk_col} = %s AND user_id = %s;", (record_pk, u_row[0]))
                deleted_count += cur.rowcount

        conn.commit()

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_revoke_permission",
            resource_type="image" if is_image else "document",
            resource_id=document_id,
            result="authorized",
            metadata={
                "revoked_role": target_role,
                "revoked_user": target_user_id,
                "deleted_count": deleted_count,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        return {
            "status": "success",
            "document_id": document_id,
            "revoked_role": target_role,
            "revoked_user": target_user_id,
            "deleted_count": deleted_count
        }
    finally:
        conn.close()


@router.get(
    "/receipt-assignments",
    response_model=List[ReceiptAssignmentItem],
    summary="List Receipt Assignments",
    description="Authorized for admin role only. Lists fee collector assignments for the current tenant.",
    dependencies=[Depends(rate_limit_admin)]
)
def list_receipt_assignments(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT fca.id, u.user_id, u.name, fca.receipt_id, fca.tenant_id, fca.created_at
                FROM fee_collector_assignments fca
                JOIN users u ON fca.user_id = u.id
                WHERE fca.tenant_id = %s
                ORDER BY fca.id ASC;
            """, (current_user.tenant_id,))
            rows = cur.fetchall()

        items = [
            ReceiptAssignmentItem(
                id=r[0],
                user_id=r[1],
                user_name=r[2],
                receipt_id=r[3],
                tenant_id=r[4],
                created_at=r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5])
            )
            for r in rows
        ]

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_list_receipt_assignments",
            resource_type="receipt_assignment",
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
    "/receipt-assignments",
    response_model=ReceiptAssignmentItem,
    summary="Create Receipt Assignment",
    description="Authorized for admin role only. Assigns a fee receipt to a finance manager within the tenant.",
    dependencies=[Depends(rate_limit_admin)]
)
def create_receipt_assignment(
    req: ReceiptAssignmentCreateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    receipt_id = req.receipt_id.strip()
    target_user_id = req.user_id.strip()

    if not receipt_id or not target_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fields 'user_id' and 'receipt_id' must be non-empty."
        )

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.name, r.name 
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.user_id = %s AND u.tenant_id = %s;
            """, (target_user_id, current_user.tenant_id))
            u_row = cur.fetchone()
            if not u_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{target_user_id}' not found in this tenant."
                )
            u_pk, u_name, u_role = u_row
            if u_role != "finance_manager":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User '{target_user_id}' has role '{u_role}'. Receipt assignments require 'finance_manager' role."
                )

            cur.execute("""
                INSERT INTO fee_collector_assignments (user_id, receipt_id, tenant_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, receipt_id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id
                RETURNING id, created_at;
            """, (u_pk, receipt_id, current_user.tenant_id))
            assign_id, created_at = cur.fetchone()
        conn.commit()

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_assign_receipt",
            resource_type="receipt_assignment",
            resource_id=receipt_id,
            result="authorized",
            metadata={
                "assigned_to_user_id": target_user_id,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )

        return ReceiptAssignmentItem(
            id=assign_id,
            user_id=target_user_id,
            user_name=u_name,
            receipt_id=receipt_id,
            tenant_id=current_user.tenant_id,
            created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
        )
    finally:
        conn.close()


@router.delete(
    "/receipt-assignments/{target_user_id}/{receipt_id}",
    summary="Revoke Receipt Assignment",
    description="Authorized for admin role only. Revokes a fee receipt assignment from a finance manager.",
    dependencies=[Depends(rate_limit_admin)]
)
def delete_receipt_assignment(
    target_user_id: str,
    receipt_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM fee_collector_assignments fca
                USING users u
                WHERE fca.user_id = u.id
                  AND u.user_id = %s
                  AND fca.receipt_id = %s
                  AND fca.tenant_id = %s
                RETURNING fca.id;
            """, (target_user_id, receipt_id, current_user.tenant_id))
            row = cur.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Assignment for user '{target_user_id}' and receipt '{receipt_id}' not found."
                )
        conn.commit()

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_revoke_receipt_assignment",
            resource_type="receipt_assignment",
            resource_id=receipt_id,
            result="authorized",
            metadata={
                "revoked_from_user_id": target_user_id,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        return {"status": "success", "user_id": target_user_id, "receipt_id": receipt_id}
    finally:
        conn.close()


@router.get(
    "/faculty-assignments",
    response_model=List[FacultyAssignmentItem],
    summary="List Faculty Student Assignments",
    description="Authorized for admin role only. Lists faculty supervision and course assignments for the current tenant.",
    dependencies=[Depends(rate_limit_admin)]
)
def list_faculty_assignments(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT fsa.id, fac.user_id, fac.name, stu.user_id, stu.name, fsa.course_code, fsa.tenant_id, fsa.created_at
                FROM faculty_student_assignments fsa
                JOIN users fac ON fsa.faculty_user_id = fac.id
                JOIN users stu ON fsa.student_user_id = stu.id
                WHERE fsa.tenant_id = %s
                ORDER BY fsa.id ASC;
            """, (current_user.tenant_id,))
            rows = cur.fetchall()

        items = [
            FacultyAssignmentItem(
                id=r[0],
                faculty_user_id=r[1],
                faculty_name=r[2],
                student_user_id=r[3],
                student_name=r[4],
                course_code=r[5],
                tenant_id=r[6],
                created_at=r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7])
            )
            for r in rows
        ]

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_list_faculty_assignments",
            resource_type="faculty_assignment",
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
    "/faculty-assignments",
    response_model=FacultyAssignmentItem,
    summary="Create Faculty Student Assignment",
    description="Authorized for admin role only. Links a faculty member to a student within the tenant.",
    dependencies=[Depends(rate_limit_admin)]
)
def create_faculty_assignment(
    req: FacultyAssignmentCreateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    faculty_user_id = req.faculty_user_id.strip()
    student_user_id = req.student_user_id.strip()
    course_code = req.course_code.strip() if req.course_code else None

    if not faculty_user_id or not student_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fields 'faculty_user_id' and 'student_user_id' must be non-empty."
        )

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Validate faculty
            cur.execute("""
                SELECT u.id, u.name, r.name 
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.user_id = %s AND u.tenant_id = %s;
            """, (faculty_user_id, current_user.tenant_id))
            fac_row = cur.fetchone()
            if not fac_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Faculty user '{faculty_user_id}' not found in this tenant."
                )
            fac_pk, fac_name, fac_role = fac_row
            if fac_role != "faculty":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User '{faculty_user_id}' has role '{fac_role}'. Expected 'faculty'."
                )

            # Validate student
            cur.execute("""
                SELECT u.id, u.name, r.name 
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.user_id = %s AND u.tenant_id = %s;
            """, (student_user_id, current_user.tenant_id))
            stu_row = cur.fetchone()
            if not stu_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Student user '{student_user_id}' not found in this tenant."
                )
            stu_pk, stu_name, stu_role = stu_row
            if stu_role != "student":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User '{student_user_id}' has role '{stu_role}'. Expected 'student'."
                )

            # Insert assignment
            cur.execute("""
                INSERT INTO faculty_student_assignments (faculty_user_id, student_user_id, course_code, tenant_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (faculty_user_id, student_user_id, tenant_id) DO UPDATE SET course_code = EXCLUDED.course_code
                RETURNING id, created_at;
            """, (fac_pk, stu_pk, course_code, current_user.tenant_id))
            assign_id, created_at = cur.fetchone()
        conn.commit()

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_assign_faculty_student",
            resource_type="faculty_assignment",
            resource_id=f"{faculty_user_id}:{student_user_id}",
            result="authorized",
            metadata={
                "faculty_user_id": faculty_user_id,
                "student_user_id": student_user_id,
                "course_code": course_code,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )

        return FacultyAssignmentItem(
            id=assign_id,
            faculty_user_id=faculty_user_id,
            faculty_name=fac_name,
            student_user_id=student_user_id,
            student_name=stu_name,
            course_code=course_code,
            tenant_id=current_user.tenant_id,
            created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
        )
    finally:
        conn.close()


@router.delete(
    "/faculty-assignments/{faculty_user_id}/{student_user_id}",
    summary="Revoke Faculty Student Assignment",
    description="Authorized for admin role only. Removes faculty supervision or course assignment for a student.",
    dependencies=[Depends(rate_limit_admin)]
)
def delete_faculty_assignment(
    faculty_user_id: str,
    student_user_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin_user)
):
    req_id = get_request_id(request)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM faculty_student_assignments fsa
                USING users fac, users stu
                WHERE fsa.faculty_user_id = fac.id
                  AND fsa.student_user_id = stu.id
                  AND fac.user_id = %s
                  AND stu.user_id = %s
                  AND fsa.tenant_id = %s
                RETURNING fsa.id;
            """, (faculty_user_id, student_user_id, current_user.tenant_id))
            row = cur.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Assignment between faculty '{faculty_user_id}' and student '{student_user_id}' not found."
                )
        conn.commit()

        record_audit_event(
            user_id=current_user.user_id,
            action="admin_revoke_faculty_student_assignment",
            resource_type="faculty_assignment",
            resource_id=f"{faculty_user_id}:{student_user_id}",
            result="authorized",
            metadata={
                "faculty_user_id": faculty_user_id,
                "student_user_id": student_user_id,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        return {
            "status": "success",
            "faculty_user_id": faculty_user_id,
            "student_user_id": student_user_id
        }
    finally:
        conn.close()


