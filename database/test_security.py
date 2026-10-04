import os
from connection import get_db_connection

def check_db_acl_permission(user_id, target_employee_id):
    """
    Executes actual PostgreSQL database query enforcing ACL authorization.
    Returns matching authorized employee record row if permitted, or None if DENIED.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Fetch requesting user context
    cursor.execute("""
    SELECT u.id, u.tenant_id, r.name as role_name, u.employee_id as u_emp_pk
    FROM users u
    JOIN roles r ON u.role_id = r.id
    WHERE u.user_id = %s AND u.is_active = TRUE;
    """, (user_id,))
    
    user = cursor.fetchone()
    if not user:
        conn.close()
        return None
        
    u_pk, u_tenant, u_role, u_emp_pk = user

    # 2. Database ACL Query: Admin or Tenant match + Role ACL or User Self match
    query = """
    SELECT e.employee_id, e.name, e.salary_amount, e.salary_bonus, e.bank_details, e.tax_code
    FROM employees e
    WHERE e.employee_id = %s
      AND e.tenant_id = %s
      AND (
          %s = 'admin'
          OR (%s = 'employee' AND e.id = %s)
          OR EXISTS (
              SELECT 1 FROM employee_permissions ep
              JOIN roles r ON ep.role_id = r.id
              WHERE ep.employee_id = e.id AND r.name = %s
          )
      );
    """
    
    cursor.execute(query, (target_employee_id, u_tenant, u_role, u_role, u_emp_pk, u_role))
    row = cursor.fetchone()
    conn.close()
    return row

def run_postgresql_security_tests():
    print("--- RUNNING REAL POSTGRESQL DATABASE ACL SECURITY TESTS ---")
    
    # E001 = HR, E004 = Finance, E002 = Engineering, E006 = Engineering
    tests = [
        ("U001", "E001", "ALLOW", "Admin (U001) -> HR Employee (E001)"),
        ("U001", "E004", "ALLOW", "Admin (U001) -> Finance Employee (E004)"),
        ("U002", "E001", "ALLOW", "HR Manager (U002) -> HR Employee (E001)"),
        ("U002", "E004", "DENY",  "HR Manager (U002) -> Finance Employee (E004)"),
        ("U003", "E004", "ALLOW", "Finance Manager (U003) -> Finance Employee (E004)"),
        ("U003", "E002", "DENY",  "Finance Manager (U003) -> Engineering Employee (E002)"),
        ("U004", "E002", "ALLOW", "Engineering Manager (U004) -> Engineering Employee (E002)"),
        ("U004", "E004", "DENY",  "Engineering Manager (U004) -> Finance Employee (E004)"),
        ("U006", "E006", "ALLOW", "Employee U006 -> Own Record (E006)"),
        ("U006", "E001", "DENY",  "Employee U006 -> Other Employee Record (E001)")
    ]

    passed = 0
    failed = 0
    unauthorized_breaches = 0

    for idx, (uid, emp_id, expected, desc) in enumerate(tests, 1):
        row = check_db_acl_permission(uid, emp_id)
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

    # Tenant Isolation Test (TENANT-001 vs TENANT-002)
    print("\n--- RUNNING TENANT ISOLATION TEST ---")
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()
    
    # Temporarily create test record in TENANT-002
    cur.execute("SELECT id FROM departments WHERE name = 'Engineering';")
    dept_id = cur.fetchone()[0]
    cur.execute("""
    INSERT INTO employees (employee_id, name, department_id, tenant_id)
    VALUES ('E999_T2', 'Foreign Tenant Emp', %s, 'TENANT-002')
    ON CONFLICT (employee_id) DO NOTHING;
    """, (dept_id,))
    
    tenant_test_row = check_db_acl_permission("U001", "E999_T2") # Admin of TENANT-001
    cur.execute("DELETE FROM employees WHERE employee_id = 'E999_T2';")
    conn.close()
    
    tenant_isolation_pass = tenant_test_row is None
    print(f"[{'PASS' if tenant_isolation_pass else 'FAIL'}] Tenant Isolation Test: TENANT-001 Admin -> TENANT-002 Record | Expected: DENY | Actual: {'ALLOW' if tenant_test_row else 'DENY'}")
    assert tenant_isolation_pass, "CRITICAL: Cross-Tenant Breach Detected!"

    print("\n--- POSTGRESQL SECURITY MATRIX SUMMARY ---")
    print(f"Total Security Tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Unauthorized Breaches: {unauthorized_breaches}")
    assert unauthorized_breaches == 0, "CRITICAL: Unauthorized access detected!"
    assert failed == 0, "CRITICAL: Some security tests failed!"
    print("REAL POSTGRESQL SECURITY TESTS PASSED (100% SUCCESS, Breaches = 0).")

if __name__ == "__main__":
    run_postgresql_security_tests()
