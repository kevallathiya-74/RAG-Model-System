import os
import sys
import json

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.connection import get_db_connection
from backend.app.auth.password import get_password_hash

METADATA_DIR = os.path.join(BASE_DIR, "dataset", "metadata")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")

def load_jsonl(filename):
    path = os.path.join(METADATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def seed_postgresql():
    """
    Safe, non-destructive, idempotent PostgreSQL seed script.
    Preserves all existing audit logs, user accounts, receipt assignments,
    and runtime permissions. Uses ON CONFLICT and existence checks.
    """
    print("Connecting to PostgreSQL 'RAG_System' database for safe idempotent seeding...")
    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    # Apply schema.sql safely (CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS)
    if os.path.exists(SCHEMA_PATH):
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        cursor.execute(schema_sql)
        print("Schema verified / tables ensured (non-destructive).")

    # 1. Seed Roles (Authoritative Four Canonical Roles)
    roles = [
        ("student", "Student Role - Access permitted student records only"),
        ("faculty", "Faculty Role - Academic, timetable, and teaching records"),
        ("finance_manager", "Finance Manager Role - Financial records & assigned receipts"),
        ("admin", "Administrator Role - System administration, access control, audit inspection")
    ]
    role_map = {}
    for r_name, r_desc in roles:
        cursor.execute("""
            INSERT INTO roles (name, description)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description
            RETURNING id;
        """, (r_name, r_desc))
        role_map[r_name] = cursor.fetchone()[0]

    # 2. Seed Departments
    depts = ["HR", "Finance", "Engineering", "Operations"]
    dept_map = {}
    for d in depts:
        cursor.execute("""
            INSERT INTO departments (name, description)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description
            RETURNING id;
        """, (d, f"{d} Department"))
        dept_map[d] = cursor.fetchone()[0]

    # 3. Seed Employees
    emp_list = load_jsonl("employees.jsonl")
    emp_db_map = {}
    for emp in emp_list:
        dept_id = dept_map.get(emp["department"])
        cursor.execute("""
            INSERT INTO employees (
                employee_id, name, date_of_birth, nationality, sex, contact_numbers,
                emergency_contacts, address, bank_details, tax_code, manager_id,
                hire_date, grade, department_id, salary_amount, salary_bonus,
                work_location, original_department, tenant_id, sensitivity, data_classification
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (employee_id) DO UPDATE SET
                name = EXCLUDED.name,
                department_id = EXCLUDED.department_id,
                grade = EXCLUDED.grade,
                work_location = EXCLUDED.work_location,
                sensitivity = EXCLUDED.sensitivity,
                data_classification = EXCLUDED.data_classification
            RETURNING id;
        """, (
            emp["employee_id"], emp["name"], emp["date_of_birth"], emp["nationality"], emp["sex"],
            json.dumps(emp["contact_numbers"]), json.dumps(emp["emergency_contacts"]), json.dumps(emp["address"]),
            json.dumps(emp["bank_details"]), emp["tax_code"], emp["manager_id"], emp["hire_date"],
            emp["grade"], dept_id, emp["salary_amount"], emp["salary_bonus"], emp["work_location"],
            emp.get("original_department", emp["department"]), emp.get("tenant_id", "TENANT-001"), emp["sensitivity"], emp["data_classification"]
        ))
        emp_db_map[emp["employee_id"]] = cursor.fetchone()[0]

    # 4. Seed Users
    user_list = load_jsonl("users.jsonl")
    user_map = {}
    for u in user_list:
        assigned_role = u["role"]
        if u["user_id"] == "U001" and "Admin" in u.get("name", ""):
            assigned_role = "admin"
        role_id = role_map[assigned_role]
        dept_id = dept_map.get(u.get("department")) if u.get("department") else None
        emp_fk = emp_db_map.get(u.get("employee_id")) if u.get("employee_id") else None
        pwd_hash = get_password_hash(u.get("password", "Password123!"))
        
        cursor.execute("""
            INSERT INTO users (user_id, name, role_id, department_id, employee_id, tenant_id, password_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                name = EXCLUDED.name,
                role_id = EXCLUDED.role_id,
                department_id = EXCLUDED.department_id,
                employee_id = EXCLUDED.employee_id,
                tenant_id = EXCLUDED.tenant_id
            RETURNING id;
        """, (u["user_id"], u["name"], role_id, dept_id, emp_fk, u.get("tenant_id", "TENANT-001"), pwd_hash))
        user_map[u["user_id"]] = cursor.fetchone()[0]

    # Query all users into map to handle users existing only in DB
    cursor.execute("SELECT user_id, id FROM users;")
    for uid, pk in cursor.fetchall():
        user_map[uid] = pk

    # 5. Seed Documents
    doc_list = load_jsonl("documents.jsonl")
    doc_map = {}
    for doc in doc_list:
        dept_id = dept_map.get(doc["department"])
        owner_fk = user_map.get(doc.get("owner_id"))
        cursor.execute("""
            INSERT INTO documents (document_id, filename, source_type, source_path, department_id, owner_user_id, tenant_id, sensitivity)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                filename = EXCLUDED.filename,
                source_path = EXCLUDED.source_path,
                department_id = EXCLUDED.department_id,
                owner_user_id = EXCLUDED.owner_user_id,
                sensitivity = EXCLUDED.sensitivity
            RETURNING id;
        """, (doc["document_id"], doc["filename"], doc["source_type"], doc["source_path"], dept_id, owner_fk, doc.get("tenant_id", "TENANT-001"), doc["sensitivity"]))
        doc_map[doc["document_id"]] = cursor.fetchone()[0]

    # 6. Seed Images
    img_list = load_jsonl("images.jsonl")
    img_map = {}
    for img in img_list:
        dept_id = dept_map.get(img["department"])
        owner_fk = user_map.get(img.get("owner_id"))
        cursor.execute("""
            INSERT INTO images (image_id, filename, source_type, source_path, department_id, owner_user_id, tenant_id, sensitivity)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (image_id) DO UPDATE SET
                filename = EXCLUDED.filename,
                source_path = EXCLUDED.source_path,
                department_id = EXCLUDED.department_id,
                owner_user_id = EXCLUDED.owner_user_id,
                sensitivity = EXCLUDED.sensitivity
            RETURNING id;
        """, (img["image_id"], img["filename"], img["source_type"], img["source_path"], dept_id, owner_fk, img.get("tenant_id", "TENANT-001"), img["sensitivity"]))
        img_map[img["image_id"]] = cursor.fetchone()[0]

    # 7. Seed ACL Permissions (Deduplicated, idempotent insertion)
    acls = load_jsonl("access_control.jsonl")
    doc_perm_count = 0
    img_perm_count = 0
    emp_perm_count = 0

    for acl in acls:
        res_id = acl["resource_id"]
        res_type = acl.get("resource_type", "document")
        
        for r_name in acl.get("allowed_roles", []):
            r_id = role_map.get(r_name)
            if not r_id:
                continue
            if res_type == "document" and res_id in doc_map:
                cursor.execute("""
                    INSERT INTO document_permissions (document_id, role_id, permission)
                    SELECT %s, %s, 'read'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM document_permissions
                        WHERE document_id = %s AND role_id = %s AND user_id IS NULL
                    );
                """, (doc_map[res_id], r_id, doc_map[res_id], r_id))
                doc_perm_count += cursor.rowcount
            elif res_type == "image" and res_id in img_map:
                cursor.execute("""
                    INSERT INTO image_permissions (image_id, role_id, permission)
                    SELECT %s, %s, 'read'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM image_permissions
                        WHERE image_id = %s AND role_id = %s AND user_id IS NULL
                    );
                """, (img_map[res_id], r_id, img_map[res_id], r_id))
                img_perm_count += cursor.rowcount
            elif res_type == "employee_row" and res_id in emp_db_map:
                cursor.execute("""
                    INSERT INTO employee_permissions (employee_id, role_id, permission)
                    SELECT %s, %s, 'read'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM employee_permissions
                        WHERE employee_id = %s AND role_id = %s AND user_id IS NULL
                    );
                """, (emp_db_map[res_id], r_id, emp_db_map[res_id], r_id))
                emp_perm_count += cursor.rowcount

        for u_id in acl.get("allowed_users", []):
            u_fk = user_map.get(u_id)
            if u_fk:
                if res_type == "document" and res_id in doc_map:
                    cursor.execute("""
                        INSERT INTO document_permissions (document_id, user_id, permission)
                        SELECT %s, %s, 'read'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM document_permissions
                            WHERE document_id = %s AND user_id = %s AND role_id IS NULL
                        );
                    """, (doc_map[res_id], u_fk, doc_map[res_id], u_fk))
                    doc_perm_count += cursor.rowcount
                elif res_type == "image" and res_id in img_map:
                    cursor.execute("""
                        INSERT INTO image_permissions (image_id, user_id, permission)
                        SELECT %s, %s, 'read'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM image_permissions
                            WHERE image_id = %s AND user_id = %s AND role_id IS NULL
                        );
                    """, (img_map[res_id], u_fk, img_map[res_id], u_fk))
                    img_perm_count += cursor.rowcount
                elif res_type == "employee_row" and res_id in emp_db_map:
                    cursor.execute("""
                        INSERT INTO employee_permissions (employee_id, user_id, permission)
                        SELECT %s, %s, 'read'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM employee_permissions
                            WHERE employee_id = %s AND user_id = %s AND role_id IS NULL
                        );
                    """, (emp_db_map[res_id], u_fk, emp_db_map[res_id], u_fk))
                    emp_perm_count += cursor.rowcount

    # 8. Seed Fee Collector Assignments (Preserves manually granted receipt permissions)
    fc_assignments = {
        "U_FC_01": ["REC-3001", "REC-3002", "REC-3008", "REC-3009"],
        "U_FC_02": ["REC-3003", "REC-3004", "REC-3005", "REC-3010", "REC-3011"],
        "U_FC_03": ["REC-3006", "REC-3007", "REC-3012"]
    }
    fc_count = 0
    for u_id, recs in fc_assignments.items():
        u_fk = user_map.get(u_id)
        if u_fk:
            for rec_id in recs:
                cursor.execute("""
                    INSERT INTO fee_collector_assignments (user_id, receipt_id, tenant_id)
                    VALUES (%s, %s, 'TENANT-001')
                    ON CONFLICT (user_id, receipt_id) DO NOTHING;
                """, (u_fk, rec_id))
                fc_count += cursor.rowcount

    conn.commit()
    conn.close()
    
    print("--- POSTGRESQL IDEMPOTENT SEED SUMMARY ---")
    print(f"Roles Verified: {len(role_map)}")
    print(f"Departments Verified: {len(dept_map)}")
    print(f"Users Verified: {len(user_map)}")
    print(f"Employees Verified: {len(emp_db_map)}")
    print(f"Documents Verified: {len(doc_map)}")
    print(f"Images Verified: {len(img_map)}")
    print(f"Document Permissions Upserted: {doc_perm_count}")
    print(f"Image Permissions Upserted: {img_perm_count}")
    print(f"Employee Permissions Upserted: {emp_perm_count}")
    print(f"Fee Collector Assignments Inserted (new): {fc_count}")
    print("SAFE IDEMPOTENT POSTGRESQL SEEDING COMPLETED.")

if __name__ == "__main__":
    seed_postgresql()
