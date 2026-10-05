import sys
import os
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.schemas.chat import ChatRequest, ChatResponse, Citation
from backend.app.schemas.auth import AuthenticatedUser
from backend.app.auth.dependencies import get_current_user
from scripts.secure_rag import run_secure_rag_pipeline

router = APIRouter(prefix="/api", tags=["Secure RAG Chat"])

@router.post("/chat", response_model=ChatResponse, summary="Execute authenticated & authorized RAG query")
def chat(req: ChatRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    question = req.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question cannot be empty."
        )
        
    auth_ctx = {
        "user_id": current_user.user_id,
        "role": current_user.role,
        "tenant_id": current_user.tenant_id,
        "department": current_user.department
    }
    
    try:
        res = run_secure_rag_pipeline(
            user_question=question,
            auth_ctx=auth_ctx,
            top_k=8
        )
        
        citations = [
            Citation(
                source_id=c["source_id"],
                chunk_id=c["chunk_id"],
                source_type=c["source_type"],
                filename=c["filename"],
                page_number=c.get("page_number"),
                image_id=c.get("image_id")
            ) for c in res.get("citations", [])
        ]
        
        return ChatResponse(
            answer=res["answer"],
            citations=citations,
            retrieval_count=res["retrieval_count"],
            grounded=res["grounded"],
            latencies=res["latencies"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing secure RAG query."
        )
