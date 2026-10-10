-- Migration: 005_cleanup_and_optimize_schema.sql
-- Description: Permanently remove obsolete employees, employee_permissions, and departments tables.
--              Remove department_id and employee_id foreign keys and columns from users, documents, images.
--              Reduce users to exactly four canonical accounts with college demo Indian identities.
--              Reassign document and image ownership to canonical college users.
--              Add optimized composite indexes for login, tenant lookups, fee assignments, and audit logs.
-- Safety: Transactional DDL (BEGIN ... COMMIT). Preserves all college assets, audit logs, and ACL guarantees.

BEGIN;

-- 1. Reassign document and image ownership to surviving canonical users before user removal
-- Academic documents -> Faculty (U2001)
UPDATE documents
SET owner_user_id = (SELECT id FROM users WHERE user_id = 'U2001')
WHERE owner_user_id IN (SELECT id FROM users WHERE user_id IN ('U002', 'U004', 'U005'));

-- Financial documents and receipt images -> Finance Manager (U_FC_01)
UPDATE documents
SET owner_user_id = (SELECT id FROM users WHERE user_id = 'U_FC_01')
WHERE owner_user_id IN (SELECT id FROM users WHERE user_id = 'U003');

UPDATE images
SET owner_user_id = (SELECT id FROM users WHERE user_id = 'U_FC_01')
WHERE owner_user_id IN (SELECT id FROM users WHERE user_id = 'U003');

-- Ensure U_FC_01 has permission on financial documents previously restricted to U003
INSERT INTO document_permissions (document_id, user_id, permission)
SELECT d.id, u.id, 'read'
FROM documents d
CROSS JOIN users u
WHERE d.document_id = 'EDU-FIN-003' AND u.user_id = 'U_FC_01'
ON CONFLICT DO NOTHING;

-- 2. Update surviving four users to canonical Indian demo identities
UPDATE users
SET name = 'Rajesh Sharma (Admin)',
    role_id = (SELECT id FROM roles WHERE name = 'admin'),
    is_active = TRUE
WHERE user_id = 'U001';

UPDATE users
SET name = 'Aarav Mehta (Student)',
    role_id = (SELECT id FROM roles WHERE name = 'student'),
    is_active = TRUE
WHERE user_id = 'U1001';

UPDATE users
SET name = 'Prof. Nisha Rao (Faculty)',
    role_id = (SELECT id FROM roles WHERE name = 'faculty'),
    is_active = TRUE
WHERE user_id = 'U2001';

UPDATE users
SET name = 'Leena Shah (Finance Manager)',
    role_id = (SELECT id FROM roles WHERE name = 'finance_manager'),
    is_active = TRUE
WHERE user_id = 'U_FC_01';

-- 3. Permanently remove obsolete non-target user accounts
-- Cascades remove their rows from fee_collector_assignments, document_permissions, image_permissions
DELETE FROM users
WHERE user_id NOT IN ('U001', 'U1001', 'U2001', 'U_FC_01');

-- 4. Remove obsolete foreign keys and columns from surviving operational tables
-- Remove employee_id from users
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_employee_id_fkey;
ALTER TABLE users DROP COLUMN IF EXISTS employee_id;

-- Remove department_id from users
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_department_id_fkey;
ALTER TABLE users DROP COLUMN IF EXISTS department_id;

-- Remove department_id from documents
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_department_id_fkey;
ALTER TABLE documents DROP COLUMN IF EXISTS department_id;

-- Remove department_id from images
ALTER TABLE images DROP CONSTRAINT IF EXISTS images_department_id_fkey;
ALTER TABLE images DROP COLUMN IF EXISTS department_id;

-- 5. Permanently drop obsolete domain tables
DROP TABLE IF EXISTS employee_permissions CASCADE;
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS departments CASCADE;

-- 6. Add performance-optimized indexes for production college RAG queries
-- A. Fast user login lookup
CREATE INDEX IF NOT EXISTS idx_users_login ON users(user_id, is_active);

-- B. Composite tenant and owner lookups for documents & images
CREATE INDEX IF NOT EXISTS idx_docs_tenant_owner ON documents(tenant_id, owner_user_id);
CREATE INDEX IF NOT EXISTS idx_imgs_tenant_owner ON images(tenant_id, owner_user_id);

-- C. Composite fee collector assignment lookups by user and tenant
CREATE INDEX IF NOT EXISTS idx_fc_assign_user_tenant ON fee_collector_assignments(user_id, tenant_id);

-- D. Fast audit log queries by user ordered by timestamp descending
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_timestamp ON audit_logs(user_id, timestamp DESC);

COMMIT;
