# Secure Multi-Modal RAG System with Access Control & Grounded Citations

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3+-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-6.2+-646CFF?style=flat&logo=vite&logoColor=white)](https://vitejs.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-DC2626?style=flat&logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000?style=flat&logo=ollama&logoColor=white)](https://ollama.ai/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A production-grade, multi-tenant Retrieval-Augmented Generation (RAG) system engineered for high-security academic and enterprise environments. Built with **FastAPI**, **PostgreSQL**, **Qdrant Vector Database**, **Ollama**, and **React + Vite**, this architecture enforces strict **dual-layer access control** across relational and vector retrieval tiers, verifiable **grounded citations**, multi-modal **PDF and OCR image ingestion**, and full **administrative governance**.

---

## Table of Contents

1. [Key Features & Highlights](#key-features--highlights)
2. [System Architecture](#system-architecture)
3. [Authoritative 4-Role Model & Access Matrix](#authoritative-4-role-model--access-matrix)
4. [Demo Accounts & Credentials](#demo-accounts--credentials)
5. [Prerequisites & System Requirements](#prerequisites--system-requirements)
6. [Step-by-Step Installation & Setup](#step-by-step-installation--setup)
   - [Step 1: Clone Repository & Virtual Environment](#step-1-clone-repository--virtual-environment)
   - [Step 2: Install Python Dependencies](#step-2-install-python-dependencies)
   - [Step 3: Environment Configuration (.env)](#step-3-environment-configuration-env)
   - [Step 4: Database Schema & Migrations](#step-4-database-schema--migrations)
   - [Step 5: Non-Destructive Database Seeding](#step-5-non-destructive-database-seeding)
   - [Step 6: Multi-Modal Ingestion & Vector Indexing](#step-6-multi-modal-ingestion--vector-indexing)
   - [Step 7: Frontend Setup](#step-7-frontend-setup)
7. [How to Run the Project](#how-to-run-the-project)
8. [Health Verification & Readiness Checks](#health-verification--readiness-checks)
9. [REST API Documentation & Endpoints](#rest-api-documentation--endpoints)
10. [Multi-Modal Ingestion Pipeline](#multi-modal-ingestion-pipeline)
11. [Mandatory Security Rules & Operational Guardrails](#mandatory-security-rules--operational-guardrails)
12. [Verification, Quality Assurance & Testing](#verification-quality-assurance--testing)
13. [Troubleshooting & FAQ](#troubleshooting--faq)
14. [Project Directory Layout](#project-directory-layout)

---

## Key Features & Highlights

- **Dual-Layer Access Control (ACL) Enforcement:** Access controls are evaluated at both the relational level (PostgreSQL session claims) and the vector retrieval level (Qdrant payload pre-filtering before cosine similarity calculation). Users can never retrieve embeddings outside their tenant, role, or user grants.
- **Strict Grounded Citations & Hallucination Elimination:** Responses cite exact document references (`[SRC-k]`) containing filename, page number, image ID, and chunk ID. If no authorized evidence exists, the model strictly abstains (`"I don't have enough authorized information to answer that."`).
- **Multi-Modal Document Processing:**
  - **PDF Documents:** Page-aware textual chunking with PyMuPDF.
  - **Scanned Receipts & Images:** Optical Character Recognition (OCR) powered by PaddleOCR (`PP-OCRv4`).
  - **Binary Validation:** Magic byte signatures (`%PDF-`, `\x89PNG`, `\xff\xd8\xff`) and strict payload size checks.
- **4 Canonical Role Architecture:** Exactly four authoritative roles (`student`, `faculty`, `finance_manager`, `admin`).
- **Administrative Privileges $\neq$ Document Access:** Admins govern accounts, status toggles, and ACL permissions, but **cannot bypass document ACLs** to read confidential business or academic records without explicit grants.
- **Defense-in-Depth Hardening:**
  - Prompt injection and jailbreak sanitization patterns.
  - Tenant isolation on all queries, vector payloads, and audit logs.
  - Granular in-memory rate limiting with `Retry-After` headers.
  - Non-destructive, idempotent database migrations and seeding.
  - PostgreSQL driver fallback (native `psycopg2` with pure-Python `pg8000` shim for restricted OS policies).

---

## System Architecture

```
                                    +-----------------------------------+
                                    |    React + Vite Web Dashboard     |
                                    | (Student, Faculty, Finance, Admin)|
                                    +-----------------+-----------------+
                                                      |
                                             JWT Bearer Auth / JSON
                                                      v
                        +-------------------------------------------------------------+
                        |                    FastAPI Backend Core                     |
                        | - JWT Verification & Canonical Role Claims (HS256)          |
                        | - Tenant Context Middleware & Correlation ID (X-Request-ID) |
                        | - Sliding Window In-Memory Rate Limiter                     |
                        | - Prompt Injection & Jailbreak Defense Sanitizer            |
                        +--------------+-------------------------------+--------------+
                                       |                               |
                     Relational / RBAC |                               | Pre-Filtered Vector ACLs
                                       v                               v
            +------------------------------------+   +------------------------------------+
            |       PostgreSQL 16 Database       |   |      Qdrant Vector Database        |
            | - Canonical Roles & Indian Demo    |   | - Hardware-Accelerated Payloads    |
            |   User Identities                  |   | - Tenant Isolation (tenant_id)     |
            | - Documents & Images Metadata      |   | - Allowed Roles & Allowed Users    |
            | - Granular Document/Image ACLs     |   | - UUIDv5 Deterministic Chunk IDs   |
            | - Fee Collector & Faculty Grants   |   | - 768-dim Cosine Similarity Index  |
            | - Immutable Tamper-Evident Audits  |   +-----------------+------------------+
            +------------------------------------+                     |
                                                                       | Authorized Chunks
                                                                       v
                                                     +------------------------------------+
                                                     |        Local Ollama Service        |
                                                     | - Embedding: embeddinggemma:300m   |
                                                     | - Generation: gemma3:1b            |
                                                     | - Grounded Citation Synthesizer    |
                                                     +------------------------------------+
```

### Retrieval & Verification Workflow

```
User Query ──> JWT Validation ──> Build Dynamic Qdrant ACL Filter (tenant_id + role + user_id)
                                          │
                                          ▼
                                Qdrant Vector Search (Cosine Similarity)
                                          │
                 ┌────────────────────────┴────────────────────────┐
                 ▼ (0 chunks retrieved)                            ▼ (Authorized chunks retrieved)
    Strict Refusal Response                            Format Augmented System Prompt with [SRC-k]
   "I don't have enough authorized                                 │
    information to answer that."                                   ▼
                                                      Local Ollama LLM Generation (gemma3:1b)
                                                                   │
                                                                   ▼
                                                      Citation Resolution & Audit Trail Logging
```

---

## Authoritative 4-Role Model & Access Matrix

The system strictly enforces **exactly four canonical roles**. System administrators, developers, and endpoints cannot invent or bypass these roles:

| Canonical Role | System Identifier | Authorized Access Scope | Security Guardrails & Restrictions |
|---|---|---|---|
| **Student** | `student` | Authorized student directory entry and personal academic records (`STU-1001`). | Strictly denied access to other students' personal records, attendance registers, fee ledgers, receipts, and institutional document uploads. |
| **Faculty** | `faculty` | Assigned departmental teaching schedules, class timetables, and authorized academic records. | Strictly denied financial records, fee ledgers, and financial receipts unless an explicit database permission grant exists. |
| **Finance Manager** | `finance_manager` | Institutional fee structures and assigned fee receipts. | Access to individual fee receipts is authoritatively governed via `fee_collector_assignments`. Possessing the role alone does **not** grant access to all receipts. |
| **Administrator** | `admin` | User management, active status toggles, role updates, permission grants/revocations, and audit log inspection. | **Does not automatically bypass document ACLs.** Administrative governance $\neq$ unrestricted business data access. Self-deactivation and self-demotion are blocked. |

---

## Demo Accounts & Credentials

The database comes pre-seeded with clean canonical college accounts. All pre-configured accounts share the same demonstration password:

> **Universal Demo Password:** `Password123!`  
> **Default Tenant:** `TENANT-001`

| User ID | Full Name | Canonical Role | Assigned Scope / Permissions |
|---|---|---|---|
| `U1001` | Aarav Mehta | `student` | Personal academic record `STU-1001` in Student Directory. |
| `U2001` | Prof. Nisha Rao | `faculty` | Faculty schedules, class timetables, and academic records. |
| `U_FC_01` | Leena Shah | `finance_manager` | Institutional fee ledger and assigned receipts: `REC-3001`, `REC-3002`, `REC-3008`, `REC-3009`. |
| `U001` | Rajesh Sharma | `admin` | Administrative governance, audit inspection, and user management. *(Document reading requires explicit ACL grant)*. |

---

## Prerequisites & System Requirements

Ensure the following tools are installed on your workstation before starting:

1. **Python:** Version `3.10` or higher (`3.11` recommended).
2. **Node.js:** Version `18.x` or higher and `npm`.
3. **PostgreSQL:** Version `14` or higher (`PostgreSQL 16` recommended), running on port `5432`.
4. **Qdrant Vector Database:**
   - **Option A (Qdrant Cloud):** Cluster URL and API key from [cloud.qdrant.io](https://cloud.qdrant.io).
   - **Option B (Local Docker):**
     ```bash
     docker run -d -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage qdrant/qdrant:latest
     ```
5. **Ollama:** Installed locally from [ollama.ai](https://ollama.ai) with models pulled:
   ```bash
   ollama pull embeddinggemma:300m
   ollama pull gemma3:1b
   ```

---

## Step-by-Step Installation & Setup

### Step 1: Clone Repository & Virtual Environment

Clone the repository and set up an isolated Python virtual environment:

#### Windows (PowerShell):
```powershell
cd E:\RAG-Model-System
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### Linux / macOS (Bash):
```bash
cd /path/to/RAG-Model-System
python3 -m venv .venv
source .venv/bin/activate
```

---

### Step 2: Install Python Dependencies

Install the core backend, database, vector search, and document processing packages:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **OCR Installation Note:** If PaddleOCR or PaddlePaddle requires isolated dependency resolution, verify:
> ```bash
> pip install paddlepaddle==2.6.2 paddleocr==2.9.1 pyclipper==1.3.0.post6 scikit-learn==1.4.2
> ```

---

### Step 3: Environment Configuration (.env)

Create your `.env` configuration file from the template:

#### Windows (PowerShell):
```powershell
Copy-Item .env.example .env
```

#### Linux / macOS:
```bash
cp .env.example .env
```

Open `.env` and configure your credentials:

```dotenv
# PostgreSQL Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=RAG_System
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_postgres_password_here

# JWT Authentication (Minimum 32 characters in production)
JWT_SECRET_KEY=secure_rag_super_secret_jwt_key_2026_change_in_prod
ENVIRONMENT=development

# Vector Database (Qdrant Cloud or Local Docker)
QDRANT_URL=https://your-cluster-id.qdrant.tech
QDRANT_API_KEY=your_qdrant_api_key_here
QDRANT_COLLECTION=secure_rag_chunks

# Local Ollama LLM & Embeddings
OLLAMA_URL=http://localhost:11434
EMBEDDING_MODEL=embeddinggemma:300m
GEN_MODEL=gemma3:1b

# Application & Upload Limits
MAX_UPLOAD_SIZE_MB=20
MAX_PDF_PAGES=50
CHUNK_SIZE=500
CHUNK_OVERLAP=75
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173

# OCR & Protobuf Runtime Settings
PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

# Security Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_LOGIN=10
RATE_LIMIT_CHAT=30
RATE_LIMIT_UPLOAD=10
RATE_LIMIT_API=120
RATE_LIMIT_ADMIN=60
```

---

### Step 4: Database Schema & Migrations

Ensure your PostgreSQL service is running and the database `RAG_System` exists:

```sql
-- In psql or pgAdmin:
CREATE DATABASE "RAG_System";
```

Apply the base schema and incremental migrations in sequential order:

#### Windows (PowerShell):
```powershell
psql -U postgres -d RAG_System -f database/schema.sql
psql -U postgres -d RAG_System -f database/migrations/002_add_document_metadata.sql
psql -U postgres -d RAG_System -f database/migrations/003_canonical_four_roles_and_admin.sql
psql -U postgres -d RAG_System -f database/migrations/004_add_image_permissions_and_indexes.sql
psql -U postgres -d RAG_System -f database/migrations/005_cleanup_and_optimize_schema.sql
psql -U postgres -d RAG_System -f database/migrations/006_add_faculty_assignments.sql
```

#### Linux / macOS:
```bash
psql -U postgres -d RAG_System -f database/schema.sql
psql -U postgres -d RAG_System -f database/migrations/002_add_document_metadata.sql
psql -U postgres -d RAG_System -f database/migrations/003_canonical_four_roles_and_admin.sql
psql -U postgres -d RAG_System -f database/migrations/004_add_image_permissions_and_indexes.sql
psql -U postgres -d RAG_System -f database/migrations/005_cleanup_and_optimize_schema.sql
psql -U postgres -d RAG_System -f database/migrations/006_add_faculty_assignments.sql
```

---

### Step 5: Non-Destructive Database Seeding

Execute the safe, idempotent database seeder. This populates canonical roles, demo users, documents, images, ACL grants, and fee collector assignments:

```bash
python database/seed.py
```

> **Safety Notice:** `database/seed.py` uses `ON CONFLICT DO UPDATE/NOTHING` and conditional inserts. It does **not** truncate tables or delete historical audit logs.

---

### Step 6: Multi-Modal Ingestion & Vector Indexing

If you are initializing or refreshing the vector database with the pre-generated college dataset (10 PDF documents and 25 receipt images), run the ingestion scripts in sequence:

```bash
# 1. Ingest and extract text from college PDF documents
python scripts/ingest_pdf.py

# 2. Ingest and extract OCR text from scanned receipt images
python scripts/ingest_ocr.py

# 3. Consolidate PDF and image chunks into unified vector format
python scripts/create_unified_chunks.py

# 4. Generate embeddings via Ollama and index into Qdrant collection
python scripts/ingest_qdrant.py
```

---

### Step 7: Frontend Setup

Install the React and Vite frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

---

## How to Run the Project

Running the system locally requires three processes (or separate terminal tabs):

### Terminal 1: Ollama Service & Models

Make sure Ollama is running and has the required embedding and generation models loaded:

```bash
ollama serve
```

In another terminal, ensure the models are available:
```bash
ollama run gemma3:1b
```

---

### Terminal 2: FastAPI Backend Server

Activate your virtual environment and launch the backend with auto-reload:

#### Windows (PowerShell):
```powershell
cd E:\RAG-Model-System
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Linux / macOS (Bash):
```bash
cd /path/to/RAG-Model-System
source .venv/bin/activate
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

The API will be available at: **`http://127.0.0.1:8000`**  
Interactive Swagger API documentation: **`http://127.0.0.1:8000/docs`** (when `DEBUG=true`).

---

### Terminal 3: React + Vite Web Client

Start the frontend development server:

```bash
cd frontend
npm run dev
```

The web client will be available at: **`http://localhost:5173`** (or `http://localhost:3000`).

---

## Health Verification & Readiness Checks

Verify that all backend subsystems (PostgreSQL, Qdrant, Ollama) are operational:

### 1. Process Liveness Probe
```bash
curl http://127.0.0.1:8000/api/health
```
**Expected Response:**
```json
{
  "status": "healthy",
  "services": {
    "api": "healthy"
  }
}
```

### 2. Dependency Readiness Probe
```bash
curl http://127.0.0.1:8000/api/health/ready
```
**Expected Response:**
```json
{
  "status": "healthy",
  "services": {
    "database": "healthy",
    "qdrant": "healthy",
    "ollama": "healthy"
  }
}
```

---

## REST API Documentation & Endpoints

### 1. Authentication (`/api/auth`)

#### `POST /api/auth/login`
Authenticates a user and issues an access token.
- **Rate Limit:** 10 requests / 60 seconds.
- **Request Body:**
  ```json
  {
    "username": "U1001",
    "password": "Password123!"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "user": {
      "user_id": "U1001",
      "name": "Aarav Mehta (Student)",
      "role": "student",
      "tenant_id": "TENANT-001"
    }
  }
  ```

---

### 2. Secure RAG Chat (`/api/chat`)

#### `POST /api/chat`
Performs an authenticated and authorized query against the RAG system.
- **Headers:** `Authorization: Bearer <access_token>`
- **Rate Limit:** 30 requests / 60 seconds.
- **Request Body:**
  ```json
  {
    "question": "What is STU-1001 Aarav Mehta's grade and academic reference code?"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "answer": "Aarav Mehta (STU-1001) is enrolled in Grade 8 A with academic reference SCI-08 [SRC-1].",
    "citations": [
      {
        "source_id": "SRC-1",
        "document_id": "EDU-STU-001",
        "filename": "01_student_directory.pdf",
        "chunk_id": "DOC-EDU-STU-001-P01-C01",
        "page_number": 1,
        "score": 0.884,
        "snippet": "Student ID: STU-1001 | Name: Aarav Mehta | Grade: 8 A | Section: A | Reference: SCI-08"
      }
    ],
    "model": "gemma3:1b",
    "chunks_retrieved": 1
  }
  ```

---

### 3. Document Ingestion & Management (`/api/documents`)

- **`POST /api/documents/upload`**: Multipart file upload (`.pdf`, `.png`, `.jpg`, `.jpeg`). Validates file signature, extracts content/OCR, embeds tokens via Ollama, and indexes points directly into Qdrant with tenant and ACL tags. *(Students are forbidden from uploading)*.
- **`GET /api/documents`**: Lists all documents and images that the authenticated user is authorized to view.
- **`GET /api/documents/{document_id}`**: Retrieves specific document metadata if authorized.

---

### 4. Administrative Operations (`/api/admin`)

*All administrative endpoints require the `admin` canonical role and are subject to audit logging.*

- **`GET /api/admin/audit`**: Inspect tenant-isolated, paginated audit logs with action and result filters.
- **`GET /api/admin/users`**: List all users within the admin's tenant.
- **`PATCH /api/admin/users/{user_id}/status`**: Activate or deactivate an account (self-deactivation and deactivating the last active admin are prohibited).
- **`PATCH /api/admin/users/{user_id}/role`**: Update a user's role to one of the 4 canonical roles.
- **`GET /api/admin/documents`**: Inspect documents, owners, and permissions within the tenant.
- **`POST /api/admin/permissions/grant`**: Grant document or image access to a role or user.
- **`DELETE /api/admin/permissions/revoke`**: Revoke document or image permissions.
- **`GET /api/admin/receipt-assignments`**: List fee collector receipt grants.
- **`POST /api/admin/receipt-assignments`**: Assign a receipt ID to a finance manager user.
- **`DELETE /api/admin/receipt-assignments/{assignment_id}`**: Revoke receipt assignment.
- **`GET /api/admin/faculty-assignments`**: List faculty-student teaching assignments.
- **`POST /api/admin/faculty-assignments`**: Create faculty-student course mapping.
- **`DELETE /api/admin/faculty-assignments/{assignment_id}`**: Delete faculty assignment.

---

## Multi-Modal Ingestion Pipeline

```
Raw File Upload (.pdf / .png / .jpg)
       │
       ▼
Magic Byte Validation & Size Check (<20MB)
       │
       ├─────────────────────────────────┬─────────────────────────────────┐
       ▼ (PDF)                           ▼ (Image/Receipt)                 ▼ (Invalid)
PyMuPDF Page-Aware Text Extraction     PaddleOCR (PP-OCRv4) Text Engine   Reject (400 Bad Request)
       │                                 │
       └─────────────────────────────────┴─────────────────────────────────┘
                                         │
                                         ▼
                   Token Chunking (Chunk Size: 500, Overlap: 75)
                                         │
                                         ▼
                     ACL Resolution (Tenant, Roles, User Grants)
                                         │
                                         ▼
                   Ollama Embeddings Generation (embeddinggemma:300m)
                                         │
                                         ▼
                   Deterministic Qdrant Upsert (UUIDv5 Point IDs)
                                         │
                                         ▼
                              Ready for Grounded RAG
```

1. **Magic Byte Verification:**
   - PDF: Must start with `%PDF-`.
   - PNG: Must start with `\x89PNG\r\n\x1a\n`.
   - JPEG: Must start with `\xff\xd8\xff`.
2. **Deterministic UUIDv5 IDs:** Vector points use deterministic UUIDv5 hashes derived from chunk content and IDs, preventing duplicate vector points upon re-ingestion.
3. **Payload Indexing:** Fields `tenant_id`, `department`, `allowed_roles`, and `allowed_users` are indexed as keywords in Qdrant for hardware-accelerated payload pre-filtering.

---

## Mandatory Security Rules & Operational Guardrails

1. **Administrative Privileges $\neq$ Document Bypass:**
   System administrators have administrative authority over user accounts, role assignments, and permission grants. However, **administrators cannot read confidential academic records or fee receipts unless an explicit permission row exists** in `document_permissions` or `image_permissions`.
2. **Strict Abstention Policy:**
   When a user asks a question for which their authorized context yields zero relevant chunks, the LLM is strictly prohibited from guessing. The system returns:
   > *"I don't have enough authorized information to answer that."*
3. **Authoritative Grounded Citations:**
   Every factual assertion in an answer must be backed by a corresponding citation (`[SRC-k]`) containing filename, chunk ID, and page number or receipt ID. Uncited factual claims trigger security audit flags.
4. **Tenant Isolation:**
   Every query and retrieval request enforces tenant filtering (`tenant_id = %s`). Cross-tenant access is structurally impossible.
5. **Prompt Injection & Adversarial Defense:**
   User questions are stripped of injection vectors (e.g., `"ignore previous instructions"`, `"system override"`, `"exfiltrate tokens"`). LLM system prompts strictly isolate context data from instructions.
6. **Immutable Audit Logging:**
   All authentication attempts (success and failure), RAG queries, document uploads, and administrative changes are recorded in the PostgreSQL `audit_logs` table with request correlation IDs (`X-Request-ID`).

---

## Verification, Quality Assurance & Testing

### 1. Automated Python Test Suite (Pytest)

Run the comprehensive security and functional test suite:

```bash
pytest tests/ -v
```

The test suite covers:
- `tests/test_rbac_matrix_complete.py`: Complete RBAC validation across all four canonical roles.
- `tests/test_strict_security_complete.py`: Strict document boundary enforcement, cross-tenant isolation, and abstention behavior.
- `tests/test_adversarial_security.py`: Prompt injection, jailbreak attempts, and token extraction attacks.
- `tests/test_qdrant_security.py`: Vector payload pre-filtering and Qdrant ACL filter generation.
- `tests/test_pdf_ingestion.py` & `tests/test_ocr_ingestion.py`: Magic byte validation and multi-modal extraction pipelines.
- `tests/test_audit_targeted.py`: Audit log schema, sanitization, and tenant filtering.
- `tests/test_image_permissions_focused.py`: Fee collector receipt assignments and granular image grants.

---

### 2. Empirical Verification Scripts

Run empirical verification scripts against the running database and vector index:

```bash
# Verify ACL boundaries and access refusal
python scripts/verify_acl_enforcement.py

# Run End-to-End API verification across roles (requires backend running)
python scripts/test_live_api.py

# Evaluate RAG baseline retrieval performance
python scripts/evaluate_colleage_rag.py
```

---

### 3. Frontend Unit & Component Tests (Vitest)

Execute the frontend unit test suite:

```bash
cd frontend
npm test
```

---

## Troubleshooting & FAQ

### 1. PostgreSQL Connection Error or Windows Smart App Control Block
- **Symptom:** `ImportError: DLL load failed while importing _psycopg` or `connection to server on socket failed`.
- **Solution:** 
  1. Confirm your PostgreSQL service is running (`Get-Service postgresql*` on Windows or `systemctl status postgresql` on Linux).
  2. Verify credentials in `.env`.
  3. If Windows Smart App Control blocks native C-extensions for `psycopg2`, the codebase automatically activates the pure-Python `pg8000` driver fallback inside `database/connection.py`. Ensure `pg8000` is installed (`pip install pg8000`).

### 2. Qdrant Connection or Collection Missing
- **Symptom:** `Collection secure_rag_chunks not found` or `ReadTimeout`.
- **Solution:**
  - If using Qdrant Cloud, confirm `QDRANT_URL` and `QDRANT_API_KEY` are correct.
  - If running locally via Docker, verify `docker ps` shows container `qdrant/qdrant:latest` mapped to port `6333`.
  - Re-run `python scripts/ingest_qdrant.py` to create the collection and payload indexes.

### 3. Ollama Timeouts or Models Not Found
- **Symptom:** `HTTP 503 Service Unavailable` on `/api/health/ready` or `model 'gemma3:1b' not found`.
- **Solution:**
  1. Confirm Ollama is running: `curl http://localhost:11434/api/tags`.
  2. Pull the required models:
     ```bash
     ollama pull embeddinggemma:300m
     ollama pull gemma3:1b
     ```

### 4. PaddleOCR Protobuf Version Incompatibility
- **Symptom:** `TypeError: Descriptors cannot not be created directly...`
- **Solution:** Set environment variable in `.env`:
  ```dotenv
  PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
  ```

### 5. Port Conflicts
- **Port 8000:** Check conflicting processes with `netstat -ano | findstr :8000` (Windows) or `lsof -i :8000` (Linux), and terminate any stale Uvicorn instances.
- **Port 5173:** Vite automatically selects the next available port (e.g., 5174). Verify `ALLOWED_ORIGINS` in `.env` includes your frontend origin.

---

## Project Directory Layout

```
E:\RAG-Model-System
├── backend/
│   ├── app/
│   │   ├── api/                     # REST API route handlers
│   │   │   ├── admin.py             # User management, ACL grants, audit logs
│   │   │   ├── auth.py              # JWT authentication & login
│   │   │   ├── chat.py              # Secure RAG chat query endpoint
│   │   │   ├── documents.py         # Multi-modal document upload & listings
│   │   │   └── health.py            # Liveness & readiness health probes
│   │   ├── auth/                    # JWT creation, decoding, & password hashing
│   │   ├── db/                      # Database query helpers
│   │   ├── middleware/              # Request ID, correlation, & CORS middleware
│   │   ├── schemas/                 # Pydantic v2 request/response schemas
│   │   ├── services/                # Rate limiter, audit logger, hybrid query router
│   │   ├── config.py                # Environment configuration loader
│   │   └── main.py                  # FastAPI application entrypoint
├── database/
│   ├── migrations/                  # Versioned, reversible SQL migrations (002 to 006)
│   ├── connection.py                # Dual-driver PostgreSQL connection (psycopg2/pg8000)
│   ├── schema.sql                   # Authoritative 8-table relational schema
│   ├── seed.py                      # Idempotent, safe database seed script
│   └── test_connection.py           # Connectivity verification script
├── dataset/
│   ├── raw/                         # Source PDF documents & scanned images
│   ├── metadata/                    # Canonical metadata JSONL files
│   ├── processed/                   # Extracted chunk JSONLs & OCR caches
│   └── uploads/                     # Live uploaded user documents
├── frontend/
│   ├── src/
│   │   ├── components/              # React UI (Login, Chat, Citations, Documents, Admin)
│   │   ├── api/                     # Axios/Fetch API client wrappers
│   │   ├── App.jsx                  # Main application state & role router
│   │   └── index.css                # Premium dark glassmorphism styling
│   ├── package.json                 # Node dependencies (React 18, Vite 6)
│   └── vite.config.js               # Vite bundler configuration
├── scripts/
│   ├── ingest_pdf.py                # Page-aware PDF text extraction & chunking
│   ├── ingest_ocr.py                # PaddleOCR text extraction for scanned images
│   ├── create_unified_chunks.py     # Schema consolidation for vector ingestion
│   ├── ingest_qdrant.py             # Ollama embeddings & Qdrant vector upsert
│   ├── secure_rag.py                # Core RAG retrieval, ACL filter, & LLM pipeline
│   ├── verify_acl_enforcement.py    # Policy boundary verification script
│   └── test_live_api.py             # End-to-end live API test runner
├── tests/                           # Pytest comprehensive test suite (RBAC, ACL, Injection)
├── docs/                            # Demonstration guides & benchmark reports
├── requirements.txt                 # Python package specifications
├── .env.example                     # Environment configuration template
└── README.md                        # Project documentation (this file)
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
