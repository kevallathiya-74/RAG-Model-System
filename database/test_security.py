import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.connection import get_db_connection

def check_db_document_permission(user_id: str, document_id: str):
    """
    Executes actual PostgreSQL database query enforcing document ACL authorization.
    Returns document row if permitted, or None if DENIED.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT d.document_id, d.filename, d.sensitivity
    FROM documents d
    LEFT JOIN document_permissions dp ON d.id = dp.document_id
    LEFT JOIN roles r ON dp.role_id = r.id
    LEFT JOIN users u ON dp.user_id = u.id
    LEFT JOIN users owner ON d.owner_user_id = owner.id
    WHERE d.document_id = %s
      AND d.tenant_id = (SELECT tenant_id FROM users WHERE user_id = %s AND is_active = TRUE)
      AND (
          owner.user_id = %s
          OR r.name = (SELECT r2.name FROM users u2 JOIN roles r2 ON u2.role_id = r2.id WHERE u2.user_id = %s)
          OR u.user_id = %s
      )
    GROUP BY d.id;
    """
    cursor.execute(query, (document_id, user_id, user_id, user_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row

def check_db_fee_assignment(user_id: str, receipt_id: str):
    """
    Executes actual PostgreSQL database query checking fee collector receipt assignment.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
    SELECT fca.receipt_id
    FROM fee_collector_assignments fca
    JOIN users u ON fca.user_id = u.id
    WHERE u.user_id = %s AND fca.receipt_id = %s;
    """
    cursor.execute(query, (user_id, receipt_id))
    row = cursor.fetchone()
    conn.close()
    return row

def run_postgresql_security_tests():
    print("--- RUNNING REAL POSTGRESQL DATABASE COLLEGE ACL SECURITY TESTS ---")

    # Document Access Control Matrix
    # EDU-STU-001 (student directory): Student ALLOW, Faculty ALLOW, Admin ALLOW
    # EDU-FIN-001 (fee ledger): Student DENY, Faculty DENY, Finance Manager ALLOW
    # EDU-POL-001 (policy): Admin ALLOW, Student DENY
    tests = [
        ("U1001", "EDU-STU-001", "ALLOW", "Student (U1001) -> Student Directory (EDU-STU-001)"),
        ("U1001", "EDU-FIN-001", "DENY",  "Student (U1001) -> Fee Ledger (EDU-FIN-001)"),
        ("U1001", "EDU-EVAL-001", "DENY", "Student (U1001) -> Eval Test Cases (EDU-EVAL-001)"),
        ("U2001", "EDU-TCH-001", "ALLOW", "Faculty (U2001) -> Teacher Directory (EDU-TCH-001)"),
        ("U2001", "EDU-STU-001", "ALLOW", "Faculty (U2001) -> Student Directory (EDU-STU-001)"),
        ("U2001", "EDU-FIN-001", "DENY",  "Faculty (U2001) -> Fee Ledger (EDU-FIN-001)"),
        ("U_FC_01", "EDU-FIN-001", "ALLOW", "Finance Manager (U_FC_01) -> Fee Ledger (EDU-FIN-001)"),
        ("U_FC_01", "EDU-FIN-002", "ALLOW", "Finance Manager (U_FC_01) -> Finance Summary (EDU-FIN-002)"),
        ("U001", "EDU-POL-001", "ALLOW", "Admin (U001) -> Security Policy (EDU-POL-001)"),
        ("U001", "EDU-EVAL-001", "ALLOW", "Admin (U001) -> Eval Test Cases (EDU-EVAL-001)")
    ]

    passed = 0
    failed = 0
    unauthorized_breaches = 0

    for idx, (uid, doc_id, expected, desc) in enumerate(tests, 1):
        row = check_db_document_permission(uid, doc_id)
        actual = "ALLOW" if row is not None else "DENY"
        is_pass = actual == expected
        status = "PASS" if is_pass else "FAIL"

        if is_pass:
            passed += 1
        else:
            failed += 1
            if expected == "DENY" and actual == "ALLOW":
                unauthorized_breaches += 1

        print(f"[{status}] Test {idx:02d}: {desc} | Expected: {expected} | Actual: {actual}")

    # Receipt Assignment Tests
    print("\n--- RUNNING FEE COLLECTOR RECEIPT ASSIGNMENT TESTS ---")
    fc_tests = [
        ("U_FC_01", "REC-3001", "ALLOW", "Finance Manager (U_FC_01) -> Assigned Receipt REC-3001"),
        ("U_FC_01", "REC-3004", "DENY",  "Finance Manager (U_FC_01) -> Unassigned Receipt REC-3004")
    ]
    for idx, (uid, rec_id, expected, desc) in enumerate(fc_tests, 1):
        row = check_db_fee_assignment(uid, rec_id)
        actual = "ALLOW" if row is not None else "DENY"
        is_pass = actual == expected
        status = "PASS" if is_pass else "FAIL"
        if is_pass:
            passed += 1
        else:
            failed += 1
        print(f"[{status}] FC Test {idx:02d}: {desc} | Expected: {expected} | Actual: {actual}")

    # Tenant Isolation Test
    print("\n--- RUNNING TENANT ISOLATION TEST ---")
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO documents (document_id, filename, source_type, source_path, tenant_id, sensitivity)
    VALUES ('EDU-T2-001', 'foreign_tenant.pdf', 'pdf', 'dummy_path', 'TENANT-002', 'confidential')
    ON CONFLICT (document_id) DO NOTHING;
    """)

    tenant_test_row = check_db_document_permission("U001", "EDU-T2-001")
    cur.execute("DELETE FROM documents WHERE document_id = 'EDU-T2-001';")
    conn.close()

    tenant_isolation_pass = tenant_test_row is None
    print(f"[{'PASS' if tenant_isolation_pass else 'FAIL'}] Tenant Isolation Test: TENANT-001 Admin -> TENANT-002 Document | Expected: DENY | Actual: {'ALLOW' if tenant_test_row else 'DENY'}")
    assert tenant_isolation_pass, "CRITICAL: Cross-Tenant Breach Detected!"
    if tenant_isolation_pass:
        passed += 1
    else:
        failed += 1

    total_tests = len(tests) + len(fc_tests) + 1
    print("\n--- POSTGRESQL COLLEGE SECURITY MATRIX SUMMARY ---")
    print(f"Total Security Tests: {total_tests}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Unauthorized Breaches: {unauthorized_breaches}")
    assert unauthorized_breaches == 0, "CRITICAL: Unauthorized access detected!"
    assert failed == 0, "CRITICAL: Some security tests failed!"
    print("REAL POSTGRESQL COLLEGE SECURITY TESTS PASSED (100% SUCCESS, Breaches = 0).")

if __name__ == "__main__":
    run_postgresql_security_tests()
