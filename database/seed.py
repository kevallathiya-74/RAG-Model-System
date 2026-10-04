import os
import json
from connection import get_db_connection

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
METADATA_DIR = os.path.join(BASE_DIR, "dataset", "metadata")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")

def load_jsonl(filename):
    path = os.path.join(METADATA_DIR, filename)
    with open(path, "r") as f:
        return [json.loads(line) for line in f if line.strip()]

def seed_postgresql():
    print("Connecting to PostgreSQL 'RAG_System' database...")
    conn = get_db_connection()
    conn.autocommit = True
    cursor = conn.cursor()

    # Drop existing tables to ensure clean seed
    print("Resetting database schema...")
    cursor.execute("""
    DROP TABLE IF EXISTS audit_logs CASCADE;
    DROP TABLE IF EXISTS employee_permissions CASCADE;
    DROP TABLE IF EXISTS document_permissions CASCADE;
    DROP TABLE IF EXISTS images CASCADE;
    DROP TABLE IF EXISTS documents CASCADE;
    DROP TABLE IF EXISTS users CASCADE;
    DROP TABLE IF EXISTS employees CASCADE;
    DROP TABLE IF EXISTS departments CASCADE;
    DROP TABLE IF EXISTS roles CASCADE;
    """)

    # Apply schema.sql
    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()
    cursor.execute(schema_sql)
    print("PostgreSQL Schema applied.")

    # 1. Seed Roles
    roles = ["admin", "hr_manager", "finance_manager", "engineering_manager", "employee"]
    role_map = {}
    for r in roles:
        cursor.execute("INSERT INTO roles (name, description) VALUES (%s, %s) RETURNING id;", (r, f"{r.replace('_', ' ').title()} Role"))
        role_map[r] = cursor.fetchone()[0]

    # 2. Seed Departments
    depts = ["HR", "Finance", "Engineering", "Operations"]
    dept_map = {}
    for d in depts:
        cursor.execute("INSERT INTO departments (name, description) VALUES (%s, %s) RETURNING id;", (d, f"{d} Department"))
        dept_map[d] = cursor.fetchone()[0]

    # 3. Seed Employees
    emp_list = load_jsonl("employees.jsonl")
    emp_db_map = {}
    for emp in emp_list:
        dept_id = dept_map[emp["department"]]
        cursor.execute("""
        INSERT INTO employees (
            employee_id, name, date_of_birth, nationality, sex, contact_numbers,
            emergency_contacts, address, bank_details, tax_code, manager_id,
            hire_date, grade, department_id, salary_amount, salary_bonus,
            work_location, original_department, tenant_id, sensitivity, data_classification
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        role_id = role_map[u["role"]]
        dept_id = dept_map[u["department"]] if u.get("department") else None
        emp_fk = emp_db_map.get(u.get("employee_id")) if u.get("employee_id") else None
        cursor.execute("""
        INSERT INTO users (user_id, name, role_id, department_id, employee_id, tenant_id)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
        """, (u["user_id"], u["name"], role_id, dept_id, emp_fk, u.get("tenant_id", "TENANT-001")))
        user_map[u["user_id"]] = cursor.fetchone()[0]

    # 5. Seed Documents
    doc_list = load_jsonl("documents.jsonl")
    doc_map = {}
    for doc in doc_list:
        dept_id = dept_map[doc["department"]]
        owner_fk = user_map.get(doc.get("owner_id"))
        cursor.execute("""
        INSERT INTO documents (document_id, filename, source_type, source_path, department_id, owner_user_id, tenant_id, sensitivity)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """, (doc["document_id"], doc["filename"], doc["source_type"], doc["source_path"], dept_id, owner_fk, doc.get("tenant_id", "TENANT-001"), doc["sensitivity"]))
        doc_map[doc["document_id"]] = cursor.fetchone()[0]

    # 6. Seed Images
    img_list = load_jsonl("images.jsonl")
    img_map = {}
    for img in img_list:
        dept_id = dept_map[img["department"]]
        owner_fk = user_map.get(img.get("owner_id"))
        cursor.execute("""
        INSERT INTO images (image_id, filename, source_type, source_path, department_id, owner_user_id, tenant_id, sensitivity)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """, (img["image_id"], img["filename"], img["source_type"], img["source_path"], dept_id, owner_fk, img.get("tenant_id", "TENANT-001"), img["sensitivity"]))
        img_map[img["image_id"]] = cursor.fetchone()[0]

    # 7. Seed ACL Permissions
    acls = load_jsonl("access_control.jsonl")
    doc_perm_count = 0
    emp_perm_count = 0

    for acl in acls:
        res_id = acl["resource_id"]
        res_type = acl["resource_type"]
        
        for r_name in acl["allowed_roles"]:
            r_id = role_map[r_name]
            if res_type == "document" and res_id in doc_map:
                cursor.execute("INSERT INTO document_permissions (document_id, role_id, permission) VALUES (%s, %s, 'read');", (doc_map[res_id], r_id))
                doc_perm_count += 1
            elif res_type == "employee_row" and res_id in emp_db_map:
                cursor.execute("INSERT INTO employee_permissions (employee_id, role_id, permission) VALUES (%s, %s, 'read');", (emp_db_map[res_id], r_id))
                emp_perm_count += 1

        for u_id in acl["allowed_users"]:
            u_fk = user_map.get(u_id)
            if u_fk:
                if res_type == "document" and res_id in doc_map:
                    cursor.execute("INSERT INTO document_permissions (document_id, user_id, permission) VALUES (%s, %s, 'read');", (doc_map[res_id], u_fk))
                    doc_perm_count += 1
                elif res_type == "employee_row" and res_id in emp_db_map:
                    cursor.execute("INSERT INTO employee_permissions (employee_id, user_id, permission) VALUES (%s, %s, 'read');", (emp_db_map[res_id], u_fk))
                    emp_perm_count += 1

    conn.close()
    
    print("--- POSTGRESQL SEED SUMMARY ---")
    print(f"Roles Loaded: {len(role_map)}")
    print(f"Departments Loaded: {len(dept_map)}")
    print(f"Users Loaded: {len(user_map)}")
    print(f"Employees Loaded: {len(emp_db_map)}")
    print(f"Documents Loaded: {len(doc_map)}")
    print(f"Images Loaded: {len(img_map)}")
    print(f"Document Permissions Seeded: {doc_perm_count}")
    print(f"Employee Permissions Seeded: {emp_perm_count}")
    print("REAL POSTGRESQL SEEDING COMPLETED SUCCESSFULLY.")

if __name__ == "__main__":
    seed_postgresql()
