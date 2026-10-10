import os
import sys
import re
import json
import uuid
import time
import hashlib
import subprocess
import urllib.request
from typing import List, Optional, Dict, Any, Tuple
from fastapi import HTTPException, status
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from backend.app.config import settings
from backend.app.schemas.auth import AuthenticatedUser
from database.connection import get_db_connection
from scripts.secure_rag import get_qdrant_client

NAMESPACE_UUID = uuid.UUID("6ba7b810-9ed0-11d1-80b4-00c04fd430c8")

def clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r'[ \t]+', ' ', text)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()

def clean_ocr_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r'[ \t]+', ' ', text)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()

def classify_ocr_quality(avg_conf: float) -> str:
    if avg_conf >= 0.85:
        return "HIGH"
    elif avg_conf >= 0.70:
        return "MEDIUM"
    else:
        return "LOW"

def chunk_text_tokens(text: str, chunk_size: int = 500, overlap: int = 75) -> List[str]:
    if not text or not text.strip():
        return []
    
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]
        
    chunks = []
    current_chunk = []
    current_len = 0
    
    for para in paragraphs:
        para_words = para.split()
        if not para_words:
            continue
            
        # If single paragraph is larger than chunk_size, split by sliding word windows
        if len(para_words) > chunk_size:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_len = 0
            step = chunk_size - overlap
            if step <= 0:
                step = chunk_size
            for i in range(0, len(para_words), step):
                chunks.append(" ".join(para_words[i:i + chunk_size]))
                if i + chunk_size >= len(para_words):
                    break
            continue
            
        if current_len + len(para_words) <= chunk_size:
            current_chunk.extend(para_words)
            current_len += len(para_words)
        else:
            chunks.append(" ".join(current_chunk))
            overlap_words = current_chunk[-overlap:] if overlap < len(current_chunk) else []
            current_chunk = overlap_words + para_words
            current_len = len(current_chunk)
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks

def sanitize_filename(filename: str) -> str:
    # Strip paths, directory traversals, null bytes, special characters
    base = os.path.basename(filename)
    base = re.sub(r'[\\/:\*\?"<>\|\x00]', '_', base)
    return base.strip()

def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    endpoint = f"{settings.OLLAMA_URL}/api/embed"
    payload = json.dumps({"model": settings.EMBEDDING_MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["embeddings"]
    except Exception as e:
        raise RuntimeError(f"Ollama embedding generation failed: {e}")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

def run_paddle_ocr(image_path: str) -> List[Any]:
    """Execute PaddleOCR extraction with delegation to isolated .venv311 runtime."""
    os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
    try:
        from paddleocr import PaddleOCR
        engine = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
        res = engine.ocr(image_path, cls=True)
        return res[0] if res and res[0] else []
    except Exception:
        # Fallback to isolated OCR environment (.venv311)
        ocr_candidates = [
            os.path.join(BASE_DIR, ".venv311", "Scripts", "python.exe"),
            os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
        ]
        venv_python = None
        for candidate in ocr_candidates:
            if candidate and os.path.exists(candidate) and candidate != sys.executable:
                venv_python = candidate
                break

        if venv_python:
            img_path_json = json.dumps(image_path)
            script = f"""
import os, sys, json
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
try:
    from paddleocr import PaddleOCR
    engine = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
    res = engine.ocr({img_path_json}, cls=True)
    lines = res[0] if res and res[0] else []
    print(json.dumps(lines))
except Exception as e:
    sys.stderr.write(str(e))
    sys.exit(1)
"""
            try:
                proc = subprocess.run([venv_python, "-c", script], capture_output=True, text=True, check=True)
                for line in reversed(proc.stdout.strip().split("\n")):
                    if line.startswith("[") and line.endswith("]"):
                        return json.loads(line)
            except subprocess.SubprocessError as sub_err:
                raise RuntimeError(f"OCR subprocess execution failed on {venv_python}: {sub_err}")

        raise RuntimeError("PaddleOCR engine is not installed or available in .venv or .venv311.")

def get_db_user_id(user_id: str) -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE user_id = %s;", (user_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"User {user_id} not found in database.")
        return row[0]
    finally:
        conn.close()

def check_table_exists(cur, table_name: str) -> bool:
    try:
        cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s LIMIT 1;", (table_name,))
        return cur.fetchone() is not None
    except Exception:
        return False

def find_duplicate_document(content_hash: str, tenant_id: str, is_image: bool) -> Optional[Dict[str, Any]]:
    table = "images" if is_image else "documents"
    id_col = "image_id" if is_image else "document_id"
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = f"SELECT {id_col}, filename, source_type, status, chunk_count FROM {table} WHERE content_hash = %s AND tenant_id = %s AND status = 'completed';"
        cur.execute(query, (content_hash, tenant_id))
        row = cur.fetchone()
        if row:
            return {
                "document_id": row[0],
                "filename": row[1],
                "source_type": row[2],
                "status": row[3],
                "chunk_count": row[4],
                "message": "Document with identical content already ingested for this tenant (idempotent)."
            }
        return None
    finally:
        conn.close()

def ingest_document(
    file_bytes: bytes,
    original_filename: str,
    content_type: str,
    current_user: AuthenticatedUser,
    allowed_roles: Optional[List[str]] = None,
    allowed_users: Optional[List[str]] = None,
    sensitivity: str = "internal"
) -> Dict[str, Any]:
    # 1. File Validation
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)."
        )
        
    file_size = len(file_bytes)
    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB."
        )

    clean_name = sanitize_filename(original_filename)
    ext = os.path.splitext(clean_name)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}"
        )

    is_image = ext in {".png", ".jpg", ".jpeg"}
    source_type = "image" if is_image else "pdf"

    # Format magic bytes validation (corrupted or spoofed file detection)
    if ext == ".pdf" and not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrupted or invalid PDF document: missing '%PDF-' file signature."
        )
    if ext == ".png" and not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrupted or invalid PNG image: missing PNG file signature."
        )
    if ext in (".jpg", ".jpeg") and not file_bytes.startswith(b"\xff\xd8\xff"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrupted or invalid JPEG image: missing JPEG SOI file signature."
        )

    # 2. SHA-256 Content Hash & Duplicate Detection
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    existing = find_duplicate_document(content_hash, current_user.tenant_id, is_image)
    if existing:
        return existing

    # 3. Secure Storage
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    doc_uuid = uuid.uuid4().hex[:12].upper()
    doc_id = f"IMG-{doc_uuid}" if is_image else f"DOC-{doc_uuid}"
    stored_filename = f"{doc_id}{ext}"
    stored_path = os.path.join(settings.UPLOAD_DIR, stored_filename)

    with open(stored_path, "wb") as f:
        f.write(file_bytes)

    # Resolve DB User
    user_db_id = get_db_user_id(current_user.user_id)

    # Validate and filter allowed roles against canonical role model
    roles_acl = set()
    if allowed_roles:
        for r in allowed_roles:
            clean_r = str(r).strip().lower()
            if clean_r in settings.CANONICAL_ROLES:
                roles_acl.add(clean_r)
    roles_acl.add(current_user.role)
    roles_acl = sorted(list(roles_acl))

    users_acl = set(allowed_users or [])
    users_acl.add(current_user.user_id)
    users_acl = sorted(list(users_acl))

    # 4. Insert Initial DB Record with 'processing' status
    conn = get_db_connection()
    cur = conn.cursor()
    table = "images" if is_image else "documents"
    id_col = "image_id" if is_image else "document_id"
    perm_table = "image_permissions" if is_image else "document_permissions"
    fk_col = "image_id" if is_image else "document_id"

    try:
        insert_query = f"""
        INSERT INTO {table} (
            {id_col}, filename, source_type, source_path, owner_user_id,
            tenant_id, sensitivity, content_hash, file_size, mime_type, status, chunk_count
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'processing', 0)
        RETURNING id;
        """
        cur.execute(insert_query, (
            doc_id, clean_name, source_type, stored_path, user_db_id,
            current_user.tenant_id, sensitivity, content_hash, file_size, content_type
        ))
        db_record_id = cur.fetchone()[0]

        # Insert permissions for documents or images (if perm_table exists in DB)
        if check_table_exists(cur, perm_table):
            for r in roles_acl:
                cur.execute("SELECT id FROM roles WHERE name = %s;", (r,))
                r_row = cur.fetchone()
                if r_row:
                    cur.execute(
                        f"""
                        INSERT INTO {perm_table} ({fk_col}, role_id, permission)
                        SELECT %s, %s, 'read'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM {perm_table}
                            WHERE {fk_col} = %s AND role_id = %s AND user_id IS NULL
                        );
                        """,
                        (db_record_id, r_row[0], db_record_id, r_row[0])
                    )
            for u in users_acl:
                cur.execute("SELECT id FROM users WHERE user_id = %s;", (u,))
                u_row = cur.fetchone()
                if u_row:
                    cur.execute(
                        f"""
                        INSERT INTO {perm_table} ({fk_col}, user_id, permission)
                        SELECT %s, %s, 'read'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM {perm_table}
                            WHERE {fk_col} = %s AND user_id = %s AND role_id IS NULL
                        );
                        """,
                        (db_record_id, u_row[0], db_record_id, u_row[0])
                    )
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        if os.path.exists(stored_path):
            os.remove(stored_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize document in database: {e}"
        )

    # 5. Extraction & Chunking
    chunks = []
    try:
        if not is_image:
            # PyMuPDF processing
            import pymupdf
            pdf_doc = pymupdf.open(stored_path)
            page_count = len(pdf_doc)
            if page_count > settings.MAX_PDF_PAGES:
                raise ValueError(f"Document has {page_count} pages, exceeding maximum limit of {settings.MAX_PDF_PAGES}.")

            for p_idx in range(page_count):
                page_num = p_idx + 1
                raw_page_text = pdf_doc[p_idx].get_text()
                cleaned = clean_text(raw_page_text)
                if not cleaned:
                    continue
                
                page_chunks = chunk_text_tokens(cleaned, chunk_size=settings.CHUNK_SIZE, overlap=settings.CHUNK_OVERLAP)
                for c_idx, c_text in enumerate(page_chunks, 1):
                    chunk_id = f"{doc_id}-P{page_num:03d}-C{c_idx:03d}"
                    chunks.append({
                        "chunk_id": chunk_id,
                        "source_type": "pdf",
                        "source_id": doc_id,
                        "filename": clean_name,
                        "text": c_text,
                        "tenant_id": current_user.tenant_id,
                        "department": current_user.department or "General",
                        "sensitivity": sensitivity,
                        "allowed_roles": roles_acl,
                        "allowed_users": users_acl,
                        "citation": {
                            "source_type": "pdf",
                            "source_id": doc_id,
                            "filename": clean_name,
                            "page_number": page_num,
                            "chunk_index": c_idx,
                            "ocr_line_ids": []
                        }
                    })
            pdf_doc.close()
        else:
            # Image OCR processing via PaddleOCR
            ocr_lines = run_paddle_ocr(stored_path)
            lines_data = []
            line_texts = []
            img_confidences = []

            for line in ocr_lines:
                bbox = line[0]
                raw_txt, conf = line[1]
                clean_line = clean_ocr_text(raw_txt)
                if clean_line:
                    lines_data.append({"text": clean_line, "confidence": round(float(conf), 4), "bbox": bbox})
                    line_texts.append(clean_line)
                    img_confidences.append(float(conf))

            full_ocr_text = "\n".join(line_texts)
            if not full_ocr_text.strip():
                raise ValueError("No extractable text found in uploaded image.")

            text_chunks = chunk_text_tokens(full_ocr_text, chunk_size=settings.CHUNK_SIZE, overlap=settings.CHUNK_OVERLAP)
            for c_idx, c_txt in enumerate(text_chunks, 1):
                chunk_id = f"{doc_id}-C{c_idx:03d}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "source_type": "image",
                    "source_id": doc_id,
                    "filename": clean_name,
                    "text": c_txt,
                    "tenant_id": current_user.tenant_id,
                    "department": current_user.department or "General",
                    "sensitivity": sensitivity,
                    "allowed_roles": roles_acl,
                    "allowed_users": users_acl,
                    "citation": {
                        "source_type": "image",
                        "source_id": doc_id,
                        "image_id": doc_id,
                        "filename": clean_name,
                        "page_number": None,
                        "chunk_index": c_idx,
                        "ocr_line_ids": []
                    }
                })

        if not chunks:
            raise ValueError("No readable text content extracted from document.")

        # 6. Embedding Generation via Ollama
        texts = [c["text"] for c in chunks]
        embeddings = get_embeddings_batch(texts)
        if len(embeddings) != len(chunks):
            raise ValueError(f"Embedding count mismatch: expected {len(chunks)}, got {len(embeddings)}.")

        # 7. Qdrant Upsert with Deterministic UUIDv5 IDs and ACL Payload
        q_client = get_qdrant_client()
        points = []
        for c, vec in zip(chunks, embeddings):
            pt_id = str(uuid.uuid5(NAMESPACE_UUID, c["chunk_id"]))
            points.append(PointStruct(id=pt_id, vector=vec, payload=c))

        q_client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)

        # 8. Mark Complete in Database
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {table} SET status = 'completed', chunk_count = %s WHERE id = %s;",
            (len(chunks), db_record_id)
        )
        conn.commit()
        conn.close()

        return {
            "document_id": doc_id,
            "status": "completed",
            "filename": clean_name,
            "source_type": source_type,
            "chunk_count": len(chunks),
            "message": f"Successfully ingested {len(chunks)} chunks into vector index."
        }

    except Exception as e:
        # Failure cleanup & state recording
        try:
            cur = conn.cursor()
            cur.execute(f"UPDATE {table} SET status = 'failed' WHERE id = %s;", (db_record_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document processing failed: {str(e)}"
        )

def get_authorized_documents(current_user: AuthenticatedUser) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
        SELECT 
            d.document_id, d.filename, d.source_type, d.tenant_id, d.status, d.chunk_count, d.created_at
        FROM documents d
        LEFT JOIN document_permissions dp ON d.id = dp.document_id
        LEFT JOIN roles r ON dp.role_id = r.id
        LEFT JOIN users u ON dp.user_id = u.id
        LEFT JOIN users owner ON d.owner_user_id = owner.id
        WHERE d.tenant_id = %s
          AND (
              owner.user_id = %s
              OR u.user_id = %s
              OR (
                  r.name = %s
                  -- Faculty cannot access financial documents
                  AND NOT (%s = 'faculty' AND (d.filename ILIKE '%%fee_ledger%%' OR d.filename ILIKE '%%finance_summary%%' OR d.filename ILIKE '%%receipt%%'))
                  -- Students cannot access financial documents
                  AND NOT (%s = 'student' AND (d.filename ILIKE '%%fee_ledger%%' OR d.filename ILIKE '%%finance_summary%%' OR d.filename ILIKE '%%receipt%%'))
                  -- Finance managers cannot access academic teaching records
                  AND NOT (%s = 'finance_manager' AND (d.filename ILIKE '%%syllabus%%' OR d.filename ILIKE '%%teaching%%' OR d.filename ILIKE '%%curriculum%%'))
              )
          )
        GROUP BY d.id
        ORDER BY d.created_at DESC;
        """
        cur.execute(query, (
            current_user.tenant_id,
            current_user.user_id,
            current_user.user_id,
            current_user.role,
            current_user.role,
            current_user.role,
            current_user.role
        ))
        docs = [
            {
                "document_id": r[0],
                "filename": r[1],
                "source_type": r[2],
                "tenant_id": r[3],
                "status": r[4],
                "chunk_count": r[5],
                "created_at": str(r[6]) if r[6] else None
            }
            for r in cur.fetchall()
        ]

        # Also retrieve accessible images enforcing owner, role, user ACLs, and receipt assignments
        if check_table_exists(cur, "image_permissions"):
            img_query = """
            SELECT 
                i.image_id, i.filename, i.source_type, i.tenant_id, i.status, i.chunk_count, i.created_at
            FROM images i
            LEFT JOIN image_permissions ip ON i.id = ip.image_id
            LEFT JOIN roles r ON ip.role_id = r.id
            LEFT JOIN users u ON ip.user_id = u.id
            LEFT JOIN users owner ON i.owner_user_id = owner.id
            WHERE i.tenant_id = %s
              AND (
                  owner.user_id = %s
                  OR u.user_id = %s
                  OR (
                      -- Finance manager can access receipts assigned in fee_collector_assignments
                      %s = 'finance_manager'
                      AND EXISTS (
                          SELECT 1 FROM fee_collector_assignments fca
                          JOIN users fcu ON fca.user_id = fcu.id
                          WHERE fcu.user_id = %s AND fca.tenant_id = %s
                            AND (i.filename ILIKE '%%' || fca.receipt_id || '%%' OR i.image_id ILIKE '%%' || fca.receipt_id || '%%')
                      )
                  )
                  OR (
                      r.name = %s
                      -- Role grant cannot be used to bypass receipt assignment for finance manager on receipt images
                      AND NOT (%s = 'finance_manager' AND i.filename ILIKE '%%receipt%%')
                      -- Faculty and student cannot access receipt images via role grant
                      AND NOT (%s = 'faculty' AND i.filename ILIKE '%%receipt%%')
                      AND NOT (%s = 'student' AND i.filename ILIKE '%%receipt%%')
                  )
              )
            GROUP BY i.id
            ORDER BY i.created_at DESC;
            """
            cur.execute(img_query, (
                current_user.tenant_id,
                current_user.user_id,
                current_user.user_id,
                current_user.role,
                current_user.user_id,
                current_user.tenant_id,
                current_user.role,
                current_user.role,
                current_user.role,
                current_user.role
            ))
        else:
            # Fallback when image_permissions is pending: strictly deny-by-default for non-owners
            img_query = """
            SELECT 
                i.image_id, i.filename, i.source_type, i.tenant_id, i.status, i.chunk_count, i.created_at
            FROM images i
            LEFT JOIN users owner ON i.owner_user_id = owner.id
            WHERE i.tenant_id = %s
              AND owner.user_id = %s
            GROUP BY i.id
            ORDER BY i.created_at DESC;
            """
            cur.execute(img_query, (
                current_user.tenant_id,
                current_user.user_id
            ))
        for r in cur.fetchall():
            docs.append({
                "document_id": r[0],
                "filename": r[1],
                "source_type": r[2],
                "tenant_id": r[3],
                "status": r[4],
                "chunk_count": r[5],
                "created_at": str(r[6]) if r[6] else None
            })

        return docs
    finally:
        conn.close()

def get_authorized_document_by_id(document_id: str, current_user: AuthenticatedUser) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if document_id.startswith("IMG-"):
            if check_table_exists(cur, "image_permissions"):
                query = """
                SELECT 
                    i.image_id, i.filename, i.source_type, i.tenant_id, i.sensitivity,
                    i.status, i.chunk_count, i.file_size, i.content_hash, i.created_at
                FROM images i
                LEFT JOIN image_permissions ip ON i.id = ip.image_id
                LEFT JOIN roles r ON ip.role_id = r.id
                LEFT JOIN users u ON ip.user_id = u.id
                LEFT JOIN users owner ON i.owner_user_id = owner.id
                WHERE i.image_id = %s AND i.tenant_id = %s
                  AND (
                      owner.user_id = %s
                      OR u.user_id = %s
                      OR (
                          %s = 'finance_manager'
                          AND EXISTS (
                              SELECT 1 FROM fee_collector_assignments fca
                              JOIN users fcu ON fca.user_id = fcu.id
                              WHERE fcu.user_id = %s AND fca.tenant_id = %s
                                AND (i.filename ILIKE '%%' || fca.receipt_id || '%%' OR i.image_id ILIKE '%%' || fca.receipt_id || '%%')
                          )
                      )
                      OR (
                          r.name = %s
                          AND NOT (%s = 'finance_manager' AND i.filename ILIKE '%%receipt%%')
                          AND NOT (%s = 'faculty' AND i.filename ILIKE '%%receipt%%')
                          AND NOT (%s = 'student' AND i.filename ILIKE '%%receipt%%')
                      )
                  )
                GROUP BY i.id;
                """
                cur.execute(query, (
                    document_id,
                    current_user.tenant_id,
                    current_user.user_id,
                    current_user.user_id,
                    current_user.role,
                    current_user.user_id,
                    current_user.tenant_id,
                    current_user.role,
                    current_user.role,
                    current_user.role,
                    current_user.role
                ))
            else:
                query = """
                SELECT 
                    i.image_id, i.filename, i.source_type, i.tenant_id, i.sensitivity,
                    i.status, i.chunk_count, i.file_size, i.content_hash, i.created_at
                FROM images i
                LEFT JOIN users owner ON i.owner_user_id = owner.id
                WHERE i.image_id = %s AND i.tenant_id = %s
                  AND owner.user_id = %s
                GROUP BY i.id;
                """
                cur.execute(query, (
                    document_id,
                    current_user.tenant_id,
                    current_user.user_id
                ))
        else:
            query = """
            SELECT 
                d.document_id, d.filename, d.source_type, d.tenant_id, d.sensitivity,
                d.status, d.chunk_count, d.file_size, d.content_hash, d.created_at
            FROM documents d
            LEFT JOIN document_permissions dp ON d.id = dp.document_id
            LEFT JOIN roles r ON dp.role_id = r.id
            LEFT JOIN users u ON dp.user_id = u.id
            LEFT JOIN users owner ON d.owner_user_id = owner.id
            WHERE d.document_id = %s AND d.tenant_id = %s
              AND (
                  owner.user_id = %s
                  OR u.user_id = %s
                  OR (
                      r.name = %s
                      AND NOT (%s = 'faculty' AND (d.filename ILIKE '%%fee_ledger%%' OR d.filename ILIKE '%%finance_summary%%' OR d.filename ILIKE '%%receipt%%'))
                      AND NOT (%s = 'student' AND (d.filename ILIKE '%%fee_ledger%%' OR d.filename ILIKE '%%finance_summary%%' OR d.filename ILIKE '%%receipt%%'))
                      AND NOT (%s = 'finance_manager' AND (d.filename ILIKE '%%syllabus%%' OR d.filename ILIKE '%%teaching%%' OR d.filename ILIKE '%%curriculum%%'))
                  )
              )
            GROUP BY d.id;
            """
            cur.execute(query, (
                document_id,
                current_user.tenant_id,
                current_user.user_id,
                current_user.user_id,
                current_user.role,
                current_user.role,
                current_user.role,
                current_user.role
            ))
        
        row = cur.fetchone()
        if not row:
            return None

        return {
            "document_id": row[0],
            "filename": row[1],
            "source_type": row[2],
            "tenant_id": row[3],
            "department": None,
            "sensitivity": row[4],
            "status": row[5],
            "chunk_count": row[6],
            "file_size": row[7],
            "content_hash": row[8],
            "created_at": str(row[9]) if row[9] else None
        }
    finally:
        conn.close()
