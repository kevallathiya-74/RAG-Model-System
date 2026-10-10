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
    Safe, idempotent PostgreSQL seed script for Secure College RAG System.
    Seeds exactly the 4 canonical roles, 4 canonical Indian demo users,
    10 college documents, 25 receipt images, document/image ACL permissions,
    and fee collector receipt assignments.
    """
    print("Connecting to PostgreSQL 'RAG_System' database for clean college schema seeding...")
    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    # Apply schema.sql safely
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

    # 2. Seed Exactly Four Canonical College Users
    canonical_users = [
        ("U001", "Rajesh Sharma (Admin)", "admin", "TENANT-001", "Password123!"),
        ("U1001", "Aarav Mehta (Student)", "student", "TENANT-001", "Password123!"),
        ("U2001", "Prof. Nisha Rao (Faculty)", "faculty", "TENANT-001", "Password123!"),
        ("U_FC_01", "Leena Shah (Finance Manager)", "finance_manager", "TENANT-001", "Password123!")
    ]
    user_map = {}
    for u_id, u_name, u_role, u_tenant, u_pwd in canonical_users:
        r_id = role_map[u_role]
        pwd_hash = get_password_hash(u_pwd)
        cursor.execute("""
            INSERT INTO users (user_id, name, role_id, tenant_id, is_active, password_hash)
            VALUES (%s, %s, %s, %s, TRUE, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                name = EXCLUDED.name,
                role_id = EXCLUDED.role_id,
                tenant_id = EXCLUDED.tenant_id,
                is_active = TRUE
            RETURNING id;
        """, (u_id, u_name, r_id, u_tenant, pwd_hash))
        user_map[u_id] = cursor.fetchone()[0]

    # Query all users into map
    cursor.execute("SELECT user_id, id FROM users;")
    for uid, pk in cursor.fetchall():
        user_map[uid] = pk

    # 3. Seed Documents (10 College Documents)
    doc_list = load_jsonl("documents.jsonl")
    doc_map = {}
    for doc in doc_list:
        # Map ownership cleanly to canonical users
        doc_id = doc["document_id"]
        if doc_id.startswith("EDU-STU") or doc_id.startswith("EDU-TCH") or doc_id.startswith("EDU-CLS"):
            owner_uid = "U2001"
        elif doc_id.startswith("EDU-FIN"):
            owner_uid = "U_FC_01"
        else:
            owner_uid = "U001"
        owner_fk = user_map.get(owner_uid)

        cursor.execute("""
            INSERT INTO documents (document_id, filename, source_type, source_path, owner_user_id, tenant_id, sensitivity)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                filename = EXCLUDED.filename,
                source_path = EXCLUDED.source_path,
                owner_user_id = EXCLUDED.owner_user_id,
                sensitivity = EXCLUDED.sensitivity
            RETURNING id;
        """, (doc["document_id"], doc["filename"], doc["source_type"], doc["source_path"], owner_fk, doc.get("tenant_id", "TENANT-001"), doc["sensitivity"]))
        doc_map[doc["document_id"]] = cursor.fetchone()[0]

    # 4. Seed Images (25 Receipt Images)
    img_list = load_jsonl("images.jsonl")
    img_map = {}
    for img in img_list:
        owner_fk = user_map.get("U_FC_01")
        cursor.execute("""
            INSERT INTO images (image_id, filename, source_type, source_path, owner_user_id, tenant_id, sensitivity)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (image_id) DO UPDATE SET
                filename = EXCLUDED.filename,
                source_path = EXCLUDED.source_path,
                owner_user_id = EXCLUDED.owner_user_id,
                sensitivity = EXCLUDED.sensitivity
            RETURNING id;
        """, (img["image_id"], img["filename"], img["source_type"], img["source_path"], owner_fk, img.get("tenant_id", "TENANT-001"), img["sensitivity"]))
        img_map[img["image_id"]] = cursor.fetchone()[0]

    # 5. Seed ACL Permissions
    acls = load_jsonl("access_control.jsonl")
    doc_perm_count = 0
    img_perm_count = 0

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

        for u_id in acl.get("allowed_users", []):
            # Only map surviving canonical users
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

    # 6. Seed Fee Collector Assignments for U_FC_01
    fc_assignments = {
        "U_FC_01": ["REC-3001", "REC-3002", "REC-3008", "REC-3009"]
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

    print("--- POSTGRESQL CLEAN COLLEGE SCHEMA SEED SUMMARY ---")
    print(f"Roles Verified: {len(role_map)}")
    print(f"Canonical Users Verified: {len(user_map)}")
    print(f"Documents Verified: {len(doc_map)}")
    print(f"Images Verified: {len(img_map)}")
    print(f"Document Permissions Upserted: {doc_perm_count}")
    print(f"Image Permissions Upserted: {img_perm_count}")
    print(f"Fee Collector Assignments Verified: {fc_count}")
    print("CLEAN COLLEGE POSTGRESQL SEEDING COMPLETED.")

if __name__ == "__main__":
    seed_postgresql()
