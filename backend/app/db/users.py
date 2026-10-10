import os
from typing import Optional, Dict, Any
from database.connection import get_db_connection

def get_user_by_id_or_username(identifier: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
    SELECT 
        u.user_id,
        u.name,
        r.name as role_name,
        u.tenant_id,
        u.is_active,
        u.password_hash,
        u.id as db_id
    FROM users u
    JOIN roles r ON u.role_id = r.id
    WHERE u.user_id = %s OR LOWER(u.name) = LOWER(%s);
    """
    
    try:
        cursor.execute(query, (identifier, identifier))
        row = cursor.fetchone()
        if not row:
            return None
            
        u_id, u_name, u_role, u_tenant, u_active, u_pass, db_id = row
        return {
            "user_id": u_id,
            "name": u_name,
            "role": u_role,
            "department": None,
            "tenant_id": u_tenant,
            "is_active": u_active,
            "password_hash": u_pass,
            "db_id": db_id,
            "employee_id": None,
            "employee_code": None
        }
    finally:
        conn.close()
