from connection import get_db_connection

def test_postgresql_connection():
    print("--- POSTGRESQL CONNECTION & SCHEMA TEST ---")
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT version();")
    pg_version = cursor.fetchone()[0]
    print(f"PostgreSQL Version: {pg_version}")

    cursor.execute("SELECT current_database();")
    curr_db = cursor.fetchone()[0]
    print(f"Current Database: {curr_db}")
    assert curr_db == "RAG_System", f"Expected database RAG_System, got {curr_db}"

    # Verify table counts
    tables = ["users", "employees", "documents", "images", "document_permissions", "employee_permissions"]
    counts = {}
    for tbl in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
        counts[tbl] = cursor.fetchone()[0]
        print(f"Table '{tbl}': {counts[tbl]} records")

    assert counts["users"] >= 7, f"Expected at least 7 users, got {counts['users']}"
    assert counts["employees"] == 100, f"Expected 100 employees, got {counts['employees']}"
    assert counts["documents"] == 10, f"Expected 10 documents, got {counts['documents']}"
    assert counts["images"] >= 0, f"Expected image table present"

    conn.close()
    print("REAL POSTGRESQL CONNECTION & TABLE VERIFICATION PASSED.")

if __name__ == "__main__":
    test_postgresql_connection()
