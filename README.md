# Secure Multi-Modal RAG System with Access Control

A production-grade, multi-tenant Retrieval-Augmented Generation (RAG) system built with FastAPI, PostgreSQL, Qdrant Cloud, and React. Enforces granular access control at both the relational database layer and vector search retrieval layer, with grounded citation verification, multi-modal PDF and PNG/JPG OCR ingestion, and administrative governance.

---

## Architecture Overview

```
                      +-----------------------------+
                      | React + Vite Web Frontend   |
                      | (Student/Faculty/Finance/   |
                      |  Administrator UI)          |
                      +--------------+--------------+
                                     |
                          JWT Auth / JSON API
                                     v
                 +---------------------------------------+
                 |         FastAPI Backend Core          |
                 | - JWT Claim & Canonical Role Checks   |
                 | - Tenant Isolation Middleware         |
                 | - Administrative Governance Routes    |
                 | - Multi-Modal Ingestion & ACL Engine  |
                 |   * PDF: PyMuPDF Page-Aware Extraction|
                 |   * Image: PaddleOCR & File Validation|
                 +----------+-----------------+----------+
                            |                 |
                Relational / Auth      Vector Retrieval (ACL Filter)
                            v                 v
            +---------------------+     +-----------------------+
            |  PostgreSQL 16      |     |  Qdrant Vector DB     |
            | - Canonical Roles   |     | - Pre-filtered ACLs   |
            | - Users & Accounts  |     | - Tenant-scoped       |
            | - Receipts & Grants |     | - Chunk Embeddings    |
            | - Audit Logs        |     +-----------+-----------+
            +---------------------+                 |
                                                    v
                                        +-----------------------+
                                        | Local Ollama / Gemma  |
                                        | - Grounded Citations  |
                                        | - Prompt Injection Def|
                                        +-----------------------+
```

---

## Authoritative Role Model

The application strictly enforces **exactly four canonical application roles**:

| Canonical Role | System Identifier | Scope & Capabilities | Security Guardrails |
|---|---|---|---|
| **Student** | `student` | Access permitted student directory and personal academic records only. | Strictly denied access to other students' academic/attendance records, fee ledgers, receipts, and institutional document uploads. |
| **Faculty** | `faculty` | Access permitted teaching assignments, timetables, and authorized academic records. | Denied financial records, fee ledgers, and receipts unless explicit grant exists. |
| **Finance Manager** | `finance_manager` | Single canonical role for finance personnel and fee collectors. | Access to specific receipts is authoritatively resolved via database grants (`fee_collector_assignments` table). Role alone does not grant access to all receipts. |
| **Administrator** | `admin` | User management, active status toggles, role assignments, document ACL permission grants, and security audit log inspection. | **Does not automatically bypass document ACLs** (administrative privileges $\neq$ unrestricted business data access). Self-deactivation, self-demotion, and deactivation of the last active admin are blocked. |

---

## Multi-Modal Ingestion Pipeline (PDF & PNG/JPG OCR)

The system supports live and batch multi-modal document ingestion:

```
Upload / File -> File Validation (Magic Bytes & Size) -> Text/OCR Extraction -> ACL & Metadata Resolution -> Token Chunking -> Ollama Embeddings -> Qdrant Upsert (UUIDv5) -> Grounded RAG
```

1. **File Validation:**
   - PDF files verified with `%PDF-` signature.
   - PNG files verified with `\x89PNG\r\n\x1a\n` signature.
   - JPEG files verified with `\xff\xd8\xff` (SOI) signature.
   - File size enforced against `MAX_UPLOAD_SIZE_MB` (default 20MB).
   - Empty files (0 bytes) and unsupported extensions rejected with standard HTTP status codes.

2. **OCR Engine & Isolation:**
   - Image OCR powered by PaddleOCR 2.9.1 (`PP-OCRv4`).
   - Configurable for isolated execution or delegation via `.venv311` subprocess to prevent library conflicts.
   - `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` configured to guarantee compatibility.
   - Pre-extracted OCR results (`dataset/processed/ocr/ocr_results.jsonl`) cached for the 25 receipt dataset.

3. **Granular ACL Propagation:**
   - Extracted chunks tagged with `tenant_id`, `department`, `allowed_roles`, and `allowed_users`.
   - Authoritative PostgreSQL permissions stored in `document_permissions` and `image_permissions`.
   - Qdrant payloads indexed on keyword fields for hardware-accelerated pre-filtering.

4. **Grounded Citations:**
   - Citations return source labels (`[SRC-k]`), filenames, chunk IDs, and page numbers (PDF) or `image_id` (OCR images).
   - Strict abstention (`"I don't have enough authorized information to answer that."`) when authorized evidence is insufficient.

---

## Database Schema & Migrations

### Migrations Inventory

1. `database/migrations/002_add_document_metadata.sql`:
   - Adds `content_hash`, `file_size`, `mime_type`, `status`, and `chunk_count` to `documents` and `images` tables.
2. `database/migrations/003_canonical_four_roles_and_admin.sql`:
   - Establishes canonical 4 roles (`student`, `faculty`, `finance_manager`, `admin`).
   - Migrates System Admin (`U001`) to the `admin` role.
   - Creates `fee_collector_assignments` table with unique constraint `uq_user_receipt (user_id, receipt_id)`.
   - Seeds initial receipt assignments (`REC-3001` through `REC-3012`).
3. `database/migrations/004_add_image_permissions_and_indexes.sql`:
   - Creates `image_permissions` table for granular image role/user ACL grants.
   - Adds unique partial indexes on `document_permissions` and `image_permissions` to prevent duplicate permission rows.

### Safe, Non-Destructive Seeding

`database/seed.py` is **100% non-destructive and idempotent**:
- Destructive `TRUNCATE TABLE ... CASCADE;` has been completely eliminated.
- Preserves all audit history (`audit_logs`), user accounts, passwords, and custom receipt assignments.
- Uses `ON CONFLICT DO UPDATE` or `ON CONFLICT DO NOTHING` for all core tables.
- Uses existence checks (`WHERE NOT EXISTS`) to prevent duplicate permission records.

---

## Setup & Operational Instructions

### 1. Environment Configuration

Copy `.env.example` to `.env` and configure appropriate values:

```bash
cp .env.example .env
```

Key environment settings:
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: PostgreSQL database credentials.
- `JWT_SECRET_KEY`: Minimum 32-character secret key for signing tokens.
- `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`: Qdrant Cloud or local vector database.
- `OLLAMA_URL`, `EMBEDDING_MODEL`, `GEN_MODEL`: Local Ollama embedding and generation models (`embeddinggemma:300m`, `gemma3:1b`).
- `CHUNK_SIZE` (default 500), `CHUNK_OVERLAP` (default 75).
- `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python`.

### 2. Database Migrations & Seeding

> **Important:** Do not execute database migrations or seed scripts until authorized.

When authorized, execute in order:

```bash
# Apply migrations
psql -U postgres -d RAG_System -f database/migrations/002_add_document_metadata.sql
psql -U postgres -d RAG_System -f database/migrations/003_canonical_four_roles_and_admin.sql
psql -U postgres -d RAG_System -f database/migrations/004_add_image_permissions_and_indexes.sql

# Run safe idempotent seed
python database/seed.py
```

### 3. Ingestion & Indexing Workflow

```bash
# Ingest and chunk PDFs
python scripts/ingest_pdf.py

# Ingest and chunk OCR images
python scripts/ingest_ocr.py

# Combine PDF and Image chunks into unified vector contract
python scripts/create_unified_chunks.py

# Generate embeddings and index into Qdrant Cloud
python scripts/ingest_qdrant.py
```

### 4. Running the Application

Backend:
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

---

## Verification & Testing Status

**Testing is currently paused awaiting authorization.**

No live database migrations, production builds, or test commands have been run without explicit approval. All changes have been statically verified across schema alignment, authorization logic, and pipeline consistency.
