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
        d.name as department_name,
        u.tenant_id,
        u.is_active,
        u.password_hash,
        u.id as db_id,
        u.employee_id as emp_fk,
        e.employee_id as emp_code
    FROM users u
    JOIN roles r ON u.role_id = r.id
    LEFT JOIN departments d ON u.department_id = d.id
    LEFT JOIN employees e ON u.employee_id = e.id
    WHERE u.user_id = %s OR LOWER(u.name) = LOWER(%s);
    """
    
    try:
        cursor.execute(query, (identifier, identifier))
        row = cursor.fetchone()
        if not row:
            return None
            
        u_id, u_name, u_role, u_dept, u_tenant, u_active, u_pass, db_id, emp_fk, emp_code = row
        return {
            "user_id": u_id,
            "name": u_name,
            "role": u_role,
            "department": u_dept,
            "tenant_id": u_tenant,
            "is_active": u_active,
            "password_hash": u_pass,
            "db_id": db_id,
            "employee_id": emp_fk,
            "employee_code": emp_code
        }
    finally:
        conn.close()
