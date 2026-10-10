-- Migration: 006_add_faculty_assignments.sql
-- Description: Add authoritative PostgreSQL table for faculty-to-student teaching and supervision assignments.
-- Safety: Non-destructive, idempotent, backward-compatible, transaction-safe.

BEGIN;

CREATE TABLE IF NOT EXISTS faculty_student_assignments (
    id SERIAL PRIMARY KEY,
    faculty_user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    student_user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_code VARCHAR(50),
    tenant_id VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_faculty_student_tenant UNIQUE (faculty_user_id, student_user_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_fsa_faculty_tenant ON faculty_student_assignments(faculty_user_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_fsa_student_tenant ON faculty_student_assignments(student_user_id, tenant_id);

COMMIT;
