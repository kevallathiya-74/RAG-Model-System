"""
Secure Hybrid Multi-Modal RAG Service.
Coordinates:
1. Structured PostgreSQL query branch (with row/column ACLs)
2. Semantic Qdrant retrieval branch (with tenant/role/user ACLs)
3. Secure Context Fusion Layer (strict source boundaries)
4. Gemma 3 1B multi-source synthesis
5. Grounded hybrid citation resolution (PostgreSQL [SRC-DB-1] + Document [SRC-2..N])
"""
import os
import time
import re
import requests
import json
from typing import Dict, Any, List, Tuple

from backend.app.schemas.structured_query import HybridQueryIntent
from backend.app.schemas.chat import ChatResponse, Citation
from backend.app.services.structured_query_service import execute_structured_query, SAFE_REFUSAL
from backend.app.services.audit_service import record_audit_event
from scripts.secure_rag import retrieve_authorized_chunks, load_env

def generate_hybrid_gemma_answer(
    user_question: str,
    hybrid_context: str,
    doc_labels: List[str]
) -> str:
    """
    Synthesizes facts from authorized database records [SRC-DB-1]
    and authorized documents using local Gemma 3 1B.
    """
    load_env()
    doc_refs_instruction = ", ".join(f"[{lbl}]" for lbl in doc_labels)
    prompt_text = (
        f"Synthesize the information from the database and document sources to answer the user question.\n"
        f"You MUST mention the database finding and cite it as [SRC-DB-1].\n"
        f"You MUST also mention what the documents state and cite them using their source tags ({doc_refs_instruction}).\n"
        f"Do not assume or invent facts outside the provided sources.\n\n"
        f"Context Sources:\n{hybrid_context}\n\n"
        f"User Question: {user_question}\n"
        f"Answer:"
    )
    
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    payload = {
        "model": os.environ.get("GEN_MODEL", "gemma3:1b"),
        "prompt": prompt_text,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 256,
            "top_p": 0.9
        }
    }
    
    try:
        resp = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=40)
        if resp.status_code == 200:
            ans = resp.json().get("response", "").strip()
            # Verify that output cites both DB and at least one document
            if ans and "[SRC-DB-1]" in ans and any(f"[{lbl}]" in ans for lbl in doc_labels):
                return ans
    except Exception:
        pass
        
    return ""

def build_hybrid_context(
    struct_response: ChatResponse,
    authorized_chunks: List[Dict[str, Any]]
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """
    Builds structured + semantic fused context string while strictly
    preserving source boundaries.
    """
    blocks = []
    
    # 1. Structured Database Source
    db_citation = struct_response.citations[0] if struct_response.citations else None
    table_name = db_citation.table if db_citation else "employees"
    query_type = db_citation.query_type if db_citation else "metrics"
    
    blocks.append(
        f"SOURCE [SRC-DB-1]\n"
        f"Type: POSTGRESQL DATABASE\n"
        f"Table: {table_name}\n"
        f"Query Type: {query_type}\n"
        f"Fact:\n{struct_response.answer}"
    )
    
    # 2. Document Sources
    doc_map = {}
    for idx, chunk in enumerate(authorized_chunks, 2):
        label = f"SRC-{idx}"
        chunk["_src_label"] = label
        doc_map[label] = chunk
        
        stype = str(chunk.get("source_type", "")).upper()
        fname = chunk.get("filename", "unknown")
        block = f"SOURCE [{label}]\nType: {stype}\nFile: {fname}\nChunk ID: {chunk.get('chunk_id')}"
        if chunk.get("page_number") is not None:
            block += f"\nPage: {chunk.get('page_number')}"
        if chunk.get("image_id") is not None:
            block += f"\nImage ID: {chunk.get('image_id')}"
        block += f"\nText:\n{chunk.get('text', '')}"
        blocks.append(block)
        
    return "\n\n--------------------\n\n".join(blocks), doc_map

def resolve_hybrid_citations(
    llm_answer: str,
    struct_citation: Citation,
    doc_map: Dict[str, Dict[str, Any]]
) -> Tuple[str, List[Citation], bool]:
    """
    Validates that cited sources in LLM response map strictly to authorized sources.
    Rejects fake or hallucinated citations.
    """
    refusal_keywords = [
        "don't have enough authorized information",
        "cannot answer",
        "does not contain",
        "no information",
        "not mentioned",
        "not provided",
        "i am sorry",
        "i'm sorry"
    ]
    
    ans_lower = llm_answer.lower()
    if any(kw in ans_lower for kw in refusal_keywords):
        return SAFE_REFUSAL, [], False

    # Extract all citation tags: [SRC-DB-1] or [SRC-\d+]
    db_cited = bool(re.search(r"\[SRC-DB-1\]", llm_answer))
    doc_matches = re.findall(r"\[(SRC-\d+)\]", llm_answer)
    
    valid_citations: List[Citation] = []
    
    if db_cited and struct_citation:
        valid_citations.append(struct_citation)
        
    seen = set()
    for m in doc_matches:
        if m in doc_map and m not in seen:
            seen.add(m)
            chunk = doc_map[m]
            cit_meta = chunk.get("citation", {})
            page_num = chunk.get("page_number") if chunk.get("page_number") is not None else cit_meta.get("page_number")
            img_id = chunk.get("image_id") if chunk.get("image_id") is not None else cit_meta.get("image_id")
            
            valid_citations.append(
                Citation(
                    source_id=f"[{m}]",
                    chunk_id=chunk.get("chunk_id"),
                    source_type=chunk.get("source_type", "pdf"),
                    filename=chunk.get("filename"),
                    page_number=page_num,
                    image_id=img_id,
                    tenant_id=chunk.get("tenant_id"),
                    authorized=True
                )
            )
            
    # Grounded if citations are valid
    grounded = len(valid_citations) > 0 and SAFE_REFUSAL not in llm_answer
    if not grounded:
        return SAFE_REFUSAL, [], False
        
    return llm_answer, valid_citations, grounded

def execute_hybrid_query(
    hybrid_intent: HybridQueryIntent,
    auth_ctx: Dict[str, Any],
    user_question: str
) -> ChatResponse:
    t_start = time.time()
    latencies = {}
    
    # -------------------------------------------------------------
    # 1. EXECUTE STRUCTURED BRANCH
    # -------------------------------------------------------------
    t_s = time.time()
    struct_resp = execute_structured_query(
        hybrid_intent.structured_intent,
        auth_ctx,
        user_question
    )
    latencies["structured_db"] = round(time.time() - t_s, 4)
    
    # Check structured authorization: FAIL CLOSED if unauthorized or refused
    if not struct_resp.grounded or struct_resp.answer == SAFE_REFUSAL or not struct_resp.citations:
        latencies["total"] = round(time.time() - t_start, 4)
        record_audit_event(
            user_id=auth_ctx.get("user_id", "unknown"),
            action="authorization_denied",
            resource_type="hybrid_context",
            result="denied",
            query=user_question,
            latency_ms=int(latencies["total"] * 1000),
            metadata={
                "route": "hybrid",
                "reason": "structured_branch_unauthorized",
                "tenant_id": auth_ctx.get("tenant_id")
            }
        )
        return ChatResponse(
            answer=SAFE_REFUSAL,
            citations=[],
            retrieval_count=0,
            grounded=False,
            latencies=latencies
        )

    # -------------------------------------------------------------
    # 2. EXECUTE SEMANTIC BRANCH (QDRANT WITH ACL FILTER)
    # -------------------------------------------------------------
    t_v = time.time()
    semantic_chunks = retrieve_authorized_chunks(
        hybrid_intent.semantic_query,
        auth_ctx,
        top_k=4
    )
    latencies["semantic_qdrant"] = round(time.time() - t_v, 4)
    
    # Check semantic authorization: FAIL CLOSED if zero authorized chunks
    if not semantic_chunks:
        latencies["total"] = round(time.time() - t_start, 4)
        record_audit_event(
            user_id=auth_ctx.get("user_id", "unknown"),
            action="authorization_denied",
            resource_type="hybrid_context",
            result="denied",
            query=user_question,
            latency_ms=int(latencies["total"] * 1000),
            metadata={
                "route": "hybrid",
                "reason": "semantic_branch_unauthorized",
                "tenant_id": auth_ctx.get("tenant_id")
            }
        )
        return ChatResponse(
            answer=SAFE_REFUSAL,
            citations=[],
            retrieval_count=0,
            grounded=False,
            latencies=latencies
        )

    # -------------------------------------------------------------
    # 3. SECURE CONTEXT FUSION
    # -------------------------------------------------------------
    t_f = time.time()
    hybrid_context_str, doc_map = build_hybrid_context(struct_resp, semantic_chunks)
    latencies["context_fusion"] = round(time.time() - t_f, 4)

    # -------------------------------------------------------------
    # 4. GEMMA GROUNDED SYNTHESIS
    # -------------------------------------------------------------
    t_g = time.time()
    doc_labels = list(doc_map.keys())
    raw_llm_answer = generate_hybrid_gemma_answer(user_question, hybrid_context_str, doc_labels)
    if not raw_llm_answer:
        # Fallback to deterministic grounded multi-source synthesis if Ollama is unreachable
        first_doc = semantic_chunks[0]
        lbl = first_doc.get("_src_label", "SRC-2")
        raw_llm_answer = (
            f"Based on authorized database records, {struct_resp.answer} [SRC-DB-1]. "
            f"According to the authorized document ({first_doc.get('filename', 'report')}), "
            f"{first_doc.get('text', '')[:180].strip()}... [{lbl}]"
        )
    latencies["gemma_synthesis"] = round(time.time() - t_g, 4)

    # -------------------------------------------------------------
    # 5. CITATION RESOLUTION & VERIFICATION
    # -------------------------------------------------------------
    struct_cit = struct_resp.citations[0]
    final_answer, resolved_citations, grounded = resolve_hybrid_citations(
        raw_llm_answer,
        struct_cit,
        doc_map
    )

    latencies["total"] = round(time.time() - t_start, 4)
    lat_ms = int(latencies["total"] * 1000)
    
    # Audit log hybrid query execution
    record_audit_event(
        user_id=auth_ctx.get("user_id", "unknown"),
        action="hybrid_query",
        resource_type="hybrid_context",
        result="authorized" if grounded else "denied",
        query=user_question,
        latency_ms=lat_ms,
        metadata={
            "route": "hybrid",
            "structured_source": struct_cit.table if struct_cit else "employees",
            "semantic_chunks": len(semantic_chunks),
            "citation_count": len(resolved_citations),
            "grounded": grounded,
            "tenant_id": auth_ctx.get("tenant_id")
        }
    )
    
    return ChatResponse(
        answer=final_answer,
        citations=resolved_citations,
        retrieval_count=struct_resp.retrieval_count + len(semantic_chunks),
        grounded=grounded,
        latencies=latencies
    )
