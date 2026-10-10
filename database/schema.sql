-- PostgreSQL Schema for Secure Multi-Modal College RAG System with Access Control
-- Target: PostgreSQL 14+
-- Canonical Roles: student, faculty, finance_manager, admin
-- Clean Operational Schema: Exactly 8 College Operational Tables

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    tenant_id VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    password_hash VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(50) UNIQUE NOT NULL,
    filename VARCHAR(255) NOT NULL,
    source_type VARCHAR(20) NOT NULL DEFAULT 'pdf',
    source_path TEXT NOT NULL,
    owner_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    tenant_id VARCHAR(50) NOT NULL,
    sensitivity VARCHAR(50) NOT NULL DEFAULT 'internal',
    content_hash VARCHAR(64),
    file_size BIGINT,
    mime_type VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    chunk_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_permissions (
    id SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    role_id INT REFERENCES roles(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    permission VARCHAR(20) NOT NULL DEFAULT 'read' CHECK (permission = 'read'),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS images (
    id SERIAL PRIMARY KEY,
    image_id VARCHAR(50) UNIQUE NOT NULL,
    filename VARCHAR(255) NOT NULL,
    source_type VARCHAR(20) NOT NULL DEFAULT 'image',
    source_path TEXT NOT NULL,
    owner_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    tenant_id VARCHAR(50) NOT NULL,
    sensitivity VARCHAR(50) NOT NULL DEFAULT 'confidential',
    content_hash VARCHAR(64),
    file_size BIGINT,
    mime_type VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    chunk_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS image_permissions (
    id SERIAL PRIMARY KEY,
    image_id INT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    role_id INT REFERENCES roles(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    permission VARCHAR(20) NOT NULL DEFAULT 'read' CHECK (permission = 'read'),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fee_collector_assignments (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receipt_id VARCHAR(50) NOT NULL,
    tenant_id VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_receipt UNIQUE (user_id, receipt_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(50),
    query TEXT,
    result VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    latency_ms INT,
    metadata JSONB
);

-- ============================================================================
-- PERFORMANCE & INTEGRITY INDEXES
-- ============================================================================

-- Users Indexes
CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_login ON users(user_id, is_active);

-- Fee Collector Assignments Indexes
CREATE INDEX IF NOT EXISTS idx_fc_assign_user ON fee_collector_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_fc_assign_receipt ON fee_collector_assignments(receipt_id);
CREATE INDEX IF NOT EXISTS idx_fc_assign_tenant ON fee_collector_assignments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_fc_assign_user_tenant ON fee_collector_assignments(user_id, tenant_id);

-- Documents Indexes
CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents(document_id);
CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_docs_tenant_owner ON documents(tenant_id, owner_user_id);

-- Images Indexes
CREATE INDEX IF NOT EXISTS idx_images_img_id ON images(image_id);
CREATE INDEX IF NOT EXISTS idx_images_tenant_id ON images(tenant_id);
CREATE INDEX IF NOT EXISTS idx_images_content_hash ON images(content_hash);
CREATE INDEX IF NOT EXISTS idx_imgs_tenant_owner ON images(tenant_id, owner_user_id);

-- Document Permissions Indexes
CREATE INDEX IF NOT EXISTS idx_doc_perm_doc_id ON document_permissions(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_perm_role_id ON document_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_doc_perm_user_id ON document_permissions(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_doc_perm_role ON document_permissions (document_id, role_id) WHERE user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_doc_perm_user ON document_permissions (document_id, user_id) WHERE role_id IS NULL;

-- Image Permissions Indexes
CREATE INDEX IF NOT EXISTS idx_img_perm_img_id ON image_permissions(image_id);
CREATE INDEX IF NOT EXISTS idx_img_perm_role_id ON image_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_img_perm_user_id ON image_permissions(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_img_perm_role ON image_permissions (image_id, role_id) WHERE user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_img_perm_user ON image_permissions (image_id, user_id) WHERE role_id IS NULL;

-- Audit Logs Indexes
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_timestamp ON audit_logs(user_id, timestamp DESC);
