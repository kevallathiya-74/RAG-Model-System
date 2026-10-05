import json
from typing import Optional, List
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request, status
from backend.app.auth.dependencies import get_current_user
from backend.app.schemas.auth import AuthenticatedUser
from backend.app.schemas.documents import (
    DocumentUploadResponse,
    DocumentSummary,
    DocumentDetail,
    DocumentListResponse
)
from backend.app.services.document_service import (
    ingest_document,
    get_authorized_documents,
    get_authorized_document_by_id
)
from backend.app.services.audit_service import record_audit_event
from backend.app.middleware.request_context import get_request_id
from backend.app.services.rate_limiter import rate_limit_upload, rate_limit_api

router = APIRouter(prefix="/api/documents", tags=["Documents & Ingestion"])

def parse_string_list(param: Optional[str]) -> Optional[List[str]]:
    if not param:
        return None
    param = param.strip()
    if param.startswith("[") and param.endswith("]"):
        try:
            return json.loads(param)
        except Exception:
            pass
    return [item.strip() for item in param.split(",") if item.strip()]

@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload & Ingest Live PDF or Image Document",
    description="Uploads a PDF or image file, performs page-aware extraction/OCR, chunks text, generates embeddings via Ollama, and indexes vector points with retrieval-layer ACL into Qdrant Cloud. Immediate querying supported.",
    dependencies=[Depends(rate_limit_upload)]
)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="PDF, PNG, JPG, or JPEG file to ingest"),
    allowed_roles: Optional[str] = Form(None, description="Optional roles authorized to read document (JSON array or comma-separated)"),
    allowed_users: Optional[str] = Form(None, description="Optional user IDs authorized to read document (JSON array or comma-separated)"),
    sensitivity: str = Form("internal", description="Document sensitivity: internal, confidential, or restricted"),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    req_id = get_request_id(request)
    roles_list = parse_string_list(allowed_roles)
    users_list = parse_string_list(allowed_users)

    # Read binary stream
    try:
        file_bytes = await file.read()
    except Exception as e:
        record_audit_event(
            user_id=current_user.user_id,
            action="document_upload_failed",
            resource_type="document",
            result="failed",
            metadata={"filename": file.filename, "error": str(e), "tenant_id": current_user.tenant_id, "request_id": req_id}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {str(e)}"
        )

    try:
        res = ingest_document(
            file_bytes=file_bytes,
            original_filename=file.filename or "upload.bin",
            content_type=file.content_type or "application/octet-stream",
            current_user=current_user,
            allowed_roles=roles_list,
            allowed_users=users_list,
            sensitivity=sensitivity
        )
        
        record_audit_event(
            user_id=current_user.user_id,
            action="document_upload",
            resource_type="document",
            resource_id=res.get("document_id"),
            result="authorized",
            metadata={
                "filename": file.filename,
                "mime_type": file.content_type,
                "chunk_count": res.get("chunk_count", 0),
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        return DocumentUploadResponse(**res)
    except Exception as e:
        record_audit_event(
            user_id=current_user.user_id,
            action="document_upload_failed",
            resource_type="document",
            result="failed",
            metadata={"filename": file.filename, "error_type": type(e).__name__, "tenant_id": current_user.tenant_id, "request_id": req_id}
        )
        raise

@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List Authorized Documents",
    description="Returns list of documents and images the current authenticated user is authorized to access within their tenant.",
    dependencies=[Depends(rate_limit_api)]
)
def list_documents(
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    req_id = get_request_id(request)
    docs = get_authorized_documents(current_user)
    summaries = [DocumentSummary(**d) for d in docs]
    
    record_audit_event(
        user_id=current_user.user_id,
        action="document_list",
        resource_type="document",
        result="authorized",
        metadata={
            "document_count": len(summaries),
            "tenant_id": current_user.tenant_id,
            "request_id": req_id
        }
    )
    return DocumentListResponse(total=len(summaries), documents=summaries)

@router.get(
    "/{document_id}",
    response_model=DocumentDetail,
    summary="Get Authorized Document Metadata",
    description="Returns detailed metadata for a specific document or image. Returns 404 if the document does not exist or user lacks authorization."
)
def get_document_details(
    document_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    req_id = get_request_id(request)
    doc = get_authorized_document_by_id(document_id, current_user)
    if not doc:
        record_audit_event(
            user_id=current_user.user_id,
            action="authorization_denied",
            resource_type="document",
            resource_id=document_id,
            result="denied",
            metadata={
                "reason": "not_found_or_unauthorized",
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or access denied."
        )
        
    record_audit_event(
        user_id=current_user.user_id,
        action="document_access",
        resource_type="document",
        resource_id=document_id,
        result="authorized",
        metadata={
            "filename": doc.get("filename"),
            "tenant_id": current_user.tenant_id,
            "request_id": req_id
        }
    )
    return DocumentDetail(**doc)
