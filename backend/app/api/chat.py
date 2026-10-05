import sys
import os
from fastapi import APIRouter, Depends, HTTPException, Request, status
from backend.app.schemas.chat import ChatRequest, ChatResponse, Citation
from backend.app.schemas.auth import AuthenticatedUser
from backend.app.auth.dependencies import get_current_user
from scripts.secure_rag import run_secure_rag_pipeline
from backend.app.services.audit_service import record_audit_event
from backend.app.middleware.request_context import get_request_id

from backend.app.services.query_router import route_query
from backend.app.services.structured_query_service import execute_structured_query
from backend.app.services.hybrid_rag_service import execute_hybrid_query
from backend.app.services.rate_limiter import rate_limit_chat

router = APIRouter(prefix="/api", tags=["Secure RAG Chat"])

@router.post("/chat", response_model=ChatResponse, summary="Execute authenticated & authorized RAG query", dependencies=[Depends(rate_limit_chat)])
def chat(
    req: ChatRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    req_id = get_request_id(request)
    question = req.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question cannot be empty."
        )
        
    auth_ctx = {
        "user_id": current_user.user_id,
        "name": current_user.name,
        "role": current_user.role,
        "tenant_id": current_user.tenant_id,
        "department": current_user.department,
        "db_id": current_user.db_id,
        "employee_id": current_user.employee_id,
        "employee_code": current_user.employee_code,
        "request_id": req_id
    }
    
    try:
        route_res = route_query(question, auth_ctx)
        
        if route_res.route == "hybrid" and route_res.hybrid_intent:
            return execute_hybrid_query(route_res.hybrid_intent, auth_ctx, question)
            
        if route_res.route == "structured" and route_res.intent:
            return execute_structured_query(route_res.intent, auth_ctx, question)
            
        # Semantic RAG path
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
        
        tot_lat = res.get("latencies", {}).get("total_sec", 0.0)
        lat_ms = int(tot_lat * 1000)
        
        # Audit semantic query
        record_audit_event(
            user_id=current_user.user_id,
            action="semantic_query",
            resource_type="semantic_vector",
            result="authorized" if res.get("grounded") else "denied",
            query=question,
            latency_ms=lat_ms,
            metadata={
                "route": "semantic",
                "retrieval_count": res.get("retrieval_count", 0),
                "citation_count": len(citations),
                "grounded": res.get("grounded", False),
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        
        return ChatResponse(
            answer=res["answer"],
            citations=citations,
            retrieval_count=res["retrieval_count"],
            grounded=res["grounded"],
            latencies=res["latencies"]
        )
    except HTTPException:
        raise
    except Exception as e:
        record_audit_event(
            user_id=current_user.user_id,
            action="chat_error",
            resource_type="chat",
            result="failed",
            query=question,
            metadata={
                "error_type": type(e).__name__,
                "tenant_id": current_user.tenant_id,
                "request_id": req_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing secure RAG query."
        )
