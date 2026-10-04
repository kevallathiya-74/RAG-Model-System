-- PostgreSQL Schema for Secure Multi-Modal RAG System with Access Control
-- Target: PostgreSQL 14+

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    employee_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    date_of_birth DATE,
    nationality VARCHAR(50),
    sex VARCHAR(20),
    contact_numbers JSONB,
    emergency_contacts JSONB,
    address JSONB,
    bank_details JSONB,
    tax_code VARCHAR(20),
    manager_id VARCHAR(50),
    hire_date DATE,
    grade VARCHAR(20),
    department_id INT REFERENCES departments(id) ON DELETE SET NULL,
    salary_amount NUMERIC(12, 2),
    salary_bonus NUMERIC(12, 2),
    work_location VARCHAR(100),
    original_department VARCHAR(100),
    tenant_id VARCHAR(50) NOT NULL,
    sensitivity VARCHAR(50) NOT NULL DEFAULT 'confidential',
    data_classification VARCHAR(50) NOT NULL DEFAULT 'employee_financial',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    department_id INT REFERENCES departments(id) ON DELETE SET NULL,
    employee_id INT REFERENCES employees(id) ON DELETE SET NULL,
    tenant_id VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(50) UNIQUE NOT NULL,
    filename VARCHAR(255) NOT NULL,
    source_type VARCHAR(20) NOT NULL DEFAULT 'pdf',
    source_path TEXT NOT NULL,
    department_id INT REFERENCES departments(id) ON DELETE CASCADE,
    owner_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    tenant_id VARCHAR(50) NOT NULL,
    sensitivity VARCHAR(50) NOT NULL DEFAULT 'internal',
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
    department_id INT REFERENCES departments(id) ON DELETE CASCADE,
    owner_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    tenant_id VARCHAR(50) NOT NULL,
    sensitivity VARCHAR(50) NOT NULL DEFAULT 'confidential',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employee_permissions (
    id SERIAL PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    role_id INT REFERENCES roles(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    permission VARCHAR(20) NOT NULL DEFAULT 'read' CHECK (permission = 'read'),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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

-- INDEXES
CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_dept_id ON users(department_id);

CREATE INDEX IF NOT EXISTS idx_employees_emp_id ON employees(employee_id);
CREATE INDEX IF NOT EXISTS idx_employees_tenant_id ON employees(tenant_id);
CREATE INDEX IF NOT EXISTS idx_employees_dept_id ON employees(department_id);
CREATE INDEX IF NOT EXISTS idx_employees_manager_id ON employees(manager_id);

CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents(document_id);
CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_dept_id ON documents(department_id);

CREATE INDEX IF NOT EXISTS idx_images_img_id ON images(image_id);
CREATE INDEX IF NOT EXISTS idx_images_tenant_id ON images(tenant_id);
CREATE INDEX IF NOT EXISTS idx_images_dept_id ON images(department_id);

CREATE INDEX IF NOT EXISTS idx_doc_perm_doc_id ON document_permissions(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_perm_role_id ON document_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_emp_perm_emp_id ON employee_permissions(employee_id);
CREATE INDEX IF NOT EXISTS idx_emp_perm_role_id ON employee_permissions(role_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
