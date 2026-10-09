-- Migration: 003_canonical_four_roles_and_admin.sql
-- Description: Establish canonical four-role model ('student', 'faculty', 'finance_manager', 'admin'),
--              migrate System Admin user (U001) to authoritative 'admin' role, and create
--              database-backed fee_collector_assignments table to eliminate hardcoded receipt mappings.
-- Safety: Non-destructive, idempotent, preserves all existing tables, foreign keys, and audit logs.

-- 1. Ensure all four canonical roles exist in roles table
INSERT INTO roles (name, description)
VALUES 
    ('student', 'Student Role - Access permitted student records only'),
    ('faculty', 'Faculty Role - Academic, timetable, and teaching records'),
    ('finance_manager', 'Finance Manager Role - Financial records & assigned receipts'),
    ('admin', 'Administrator Role - System administration, access control, audit inspection')
ON CONFLICT (name) DO UPDATE 
SET description = EXCLUDED.description;

-- 2. Migrate System Admin (U001) from legacy/temporary role to authoritative 'admin' role
-- Note: Carefully scoped to user_id = 'U001' and name = 'System Admin'
UPDATE users
SET role_id = (SELECT id FROM roles WHERE name = 'admin')
WHERE user_id = 'U001' AND name = 'System Admin';

-- 3. Create fee_collector_assignments table to persist receipt authorizations in PostgreSQL
CREATE TABLE IF NOT EXISTS fee_collector_assignments (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receipt_id VARCHAR(50) NOT NULL,
    tenant_id VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_receipt UNIQUE (user_id, receipt_id)
);

CREATE INDEX IF NOT EXISTS idx_fc_assign_user ON fee_collector_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_fc_assign_receipt ON fee_collector_assignments(receipt_id);
CREATE INDEX IF NOT EXISTS idx_fc_assign_tenant ON fee_collector_assignments(tenant_id);

-- 4. Seed initial receipt assignments for fee collector accounts into database
-- U_FC_01 -> REC-3001, REC-3002, REC-3008, REC-3009
INSERT INTO fee_collector_assignments (user_id, receipt_id, tenant_id)
SELECT u.id, rec.receipt_id, u.tenant_id
FROM users u
CROSS JOIN (
    VALUES ('REC-3001'), ('REC-3002'), ('REC-3008'), ('REC-3009')
) AS rec(receipt_id)
WHERE u.user_id = 'U_FC_01'
ON CONFLICT (user_id, receipt_id) DO NOTHING;

-- U_FC_02 -> REC-3003, REC-3004, REC-3005, REC-3010, REC-3011
INSERT INTO fee_collector_assignments (user_id, receipt_id, tenant_id)
SELECT u.id, rec.receipt_id, u.tenant_id
FROM users u
CROSS JOIN (
    VALUES ('REC-3003'), ('REC-3004'), ('REC-3005'), ('REC-3010'), ('REC-3011')
) AS rec(receipt_id)
WHERE u.user_id = 'U_FC_02'
ON CONFLICT (user_id, receipt_id) DO NOTHING;

-- U_FC_03 -> REC-3006, REC-3007, REC-3012
INSERT INTO fee_collector_assignments (user_id, receipt_id, tenant_id)
SELECT u.id, rec.receipt_id, u.tenant_id
FROM users u
CROSS JOIN (
    VALUES ('REC-3006'), ('REC-3007'), ('REC-3012')
) AS rec(receipt_id)
WHERE u.user_id = 'U_FC_03'
ON CONFLICT (user_id, receipt_id) DO NOTHING;
