-- Migration: 004_add_image_permissions_and_indexes.sql
-- Description: Add image_permissions table for multi-modal image ACLs, and add unique
--              constraints/indexes on permissions to prevent duplicate ACL grants.
-- Safety: Non-destructive, idempotent, preserves all existing tables and data.

CREATE TABLE IF NOT EXISTS image_permissions (
    id SERIAL PRIMARY KEY,
    image_id INT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    role_id INT REFERENCES roles(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    permission VARCHAR(20) NOT NULL DEFAULT 'read' CHECK (permission = 'read'),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_img_perm_img_id ON image_permissions(image_id);
CREATE INDEX IF NOT EXISTS idx_img_perm_role_id ON image_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_img_perm_user_id ON image_permissions(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_img_perm_role ON image_permissions (image_id, role_id) WHERE user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_img_perm_user ON image_permissions (image_id, user_id) WHERE role_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_doc_perm_user_id ON document_permissions(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_doc_perm_role ON document_permissions (document_id, role_id) WHERE user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_doc_perm_user ON document_permissions (document_id, user_id) WHERE role_id IS NULL;
