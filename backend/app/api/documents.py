import json
from typing import Optional, List
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
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
    description="Uploads a PDF or image file, performs page-aware extraction/OCR, chunks text, generates embeddings via Ollama, and indexes vector points with retrieval-layer ACL into Qdrant Cloud. Immediate querying supported."
)
async def upload_document(
    file: UploadFile = File(..., description="PDF, PNG, JPG, or JPEG file to ingest"),
    allowed_roles: Optional[str] = Form(None, description="Optional roles authorized to read document (JSON array or comma-separated)"),
    allowed_users: Optional[str] = Form(None, description="Optional user IDs authorized to read document (JSON array or comma-separated)"),
    sensitivity: str = Form("internal", description="Document sensitivity: internal, confidential, or restricted"),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    roles_list = parse_string_list(allowed_roles)
    users_list = parse_string_list(allowed_users)

    # Read binary stream
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {str(e)}"
        )

    res = ingest_document(
        file_bytes=file_bytes,
        original_filename=file.filename or "upload.bin",
        content_type=file.content_type or "application/octet-stream",
        current_user=current_user,
        allowed_roles=roles_list,
        allowed_users=users_list,
        sensitivity=sensitivity
    )
    return DocumentUploadResponse(**res)

@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List Authorized Documents",
    description="Returns list of documents and images the current authenticated user is authorized to access within their tenant."
)
def list_documents(current_user: AuthenticatedUser = Depends(get_current_user)):
    docs = get_authorized_documents(current_user)
    summaries = [DocumentSummary(**d) for d in docs]
    return DocumentListResponse(total=len(summaries), documents=summaries)

@router.get(
    "/{document_id}",
    response_model=DocumentDetail,
    summary="Get Authorized Document Metadata",
    description="Returns detailed metadata for a specific document or image. Returns 404 if the document does not exist or user lacks authorization."
)
def get_document_details(
    document_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    doc = get_authorized_document_by_id(document_id, current_user)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or access denied."
        )
    return DocumentDetail(**doc)
