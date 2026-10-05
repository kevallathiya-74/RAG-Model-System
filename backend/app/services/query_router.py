"""
Natural language query router.
Deterministically classifies questions into:
1. 'structured' (PostgreSQL database operations)
2. 'semantic' (Unstructured document/image RAG)
3. 'hybrid' (Cross-modal queries correlating DB and documents)
"""
import re
from typing import Dict, Any, Optional, Tuple
from backend.app.schemas.structured_query import (
    StructuredQueryIntent,
    HybridQueryIntent,
    QueryRouteResult
)

# Departments present in DB
VALID_DEPARTMENTS = {"finance", "engineering", "hr", "operations"}
DEPARTMENT_NAME_MAP = {
    "finance": "Finance",
    "engineering": "Engineering",
    "hr": "HR",
    "operations": "Operations"
}

# Hybrid keywords indicators
HYBRID_PATTERNS = [
    r"compare.*with\s+(?:the\s+)?(?:annual|report|document|policy|pdf|statement|financial)",
    r"cross[- ]reference.*with",
    r"correlate.*(?:employee|salary|database|headcount).*(?:report|document|pdf|policy)",
    r"(?:what\s+does\s+the\s+.*(?:policy|report|document)\s+say.*and\s+how\s+does\s+it\s+compare)",
    r"(?:how\s+many\s+.*employees.*and\s+what\s+does\s+the\s+.*(?:report|document|policy)\s+say)",
    r"(?:show\s+.*employees.*and\s+what\s+does\s+the\s+.*(?:report|document|policy)\s+say)"
]

# Field extraction mapping
FIELD_SYNONYMS = {
    "department": "department",
    "dept": "department",
    "salary": "salary_amount",
    "pay": "salary_amount",
    "compensation": "salary_amount",
    "bonus": "salary_bonus",
    "manager": "manager_id",
    "manager id": "manager_id",
    "grade": "grade",
    "hire date": "hire_date",
    "date of birth": "date_of_birth",
    "dob": "date_of_birth",
    "location": "work_location",
    "work location": "work_location",
    "bank": "bank_details",
    "bank details": "bank_details",
    "tax code": "tax_code",
    "contact": "contact_numbers",
    "emergency contact": "emergency_contacts",
    "nationality": "nationality",
    "sex": "sex",
    "name": "name"
}

def extract_department(text: str) -> Optional[str]:
    text_lower = text.lower()
    for d_key, d_val in DEPARTMENT_NAME_MAP.items():
        if re.search(r"\b" + re.escape(d_key) + r"\b", text_lower):
            return d_val
    return None

def extract_manager_id(text: str) -> Optional[str]:
    m = re.search(r"\b(MGR-\d{7})\b", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m2 = re.search(r"(?:manager|reports\s+to)\s+([A-Za-z0-9_-]+)", text, re.IGNORECASE)
    if m2 and m2.group(1).lower() not in ("in", "of", "for", "the", "department"):
        return m2.group(1)
    return None

def extract_employee_id(text: str) -> Optional[str]:
    m = re.search(r"\b(E\d{3,4})\b", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None

def extract_field_name(text: str) -> Optional[str]:
    text_lower = text.lower()
    for term, col in FIELD_SYNONYMS.items():
        if re.search(r"\b" + re.escape(term) + r"\b", text_lower):
            return col
    return None

def extract_hybrid_intent(q: str) -> Optional[HybridQueryIntent]:
    """
    Parses a hybrid question into a constrained StructuredQueryIntent
    and a targeted semantic search query.
    """
    q_lower = q.lower()
    dept = extract_department(q)
    filters = {"department": dept} if dept else {}
    
    # 1. Determine structured intent
    if re.search(r"\b(?:salary|salaries|compensation|pay|bonus)\b", q_lower):
        struct_intent = StructuredQueryIntent(
            entity="employees",
            operation="aggregate",
            aggregation="avg",
            target_field="salary_amount",
            filters=filters
        )
    elif re.search(r"\b(?:how\s+many|count|number\s+of|headcount)\b", q_lower):
        struct_intent = StructuredQueryIntent(
            entity="employees",
            operation="count",
            aggregation="count",
            target_field="*",
            filters=filters
        )
    elif re.search(r"\b(?:show|list|find|who\s+are)\b", q_lower):
        struct_intent = StructuredQueryIntent(
            entity="employees",
            operation="list",
            filters=filters,
            fields=["employee_id", "name", "department", "work_location"]
        )
    else:
        # Default structured intent: summary list or count
        struct_intent = StructuredQueryIntent(
            entity="employees",
            operation="count",
            aggregation="count",
            target_field="*",
            filters=filters
        )
        
    # 2. Determine semantic query
    semantic_terms = []
    if "annual financial report" in q_lower or "financial report" in q_lower:
        semantic_terms.append("annual financial report financial statement revenue")
    elif "engineering report" in q_lower:
        semantic_terms.append("engineering report technical architecture department")
    elif "policy" in q_lower:
        semantic_terms.append("policy document guidelines compensation rules")
    else:
        # Extract general document keywords
        cleaned = re.sub(
            r"^(?:compare|cross[- ]reference|correlate|how\s+many|show\s+employees|what\s+does).*?(?:with|and)\s+",
            "",
            q,
            flags=re.IGNORECASE
        )
        semantic_terms.append(cleaned.strip())
        
    if dept and dept.lower() not in " ".join(semantic_terms).lower():
        semantic_terms.append(dept)
        
    semantic_query = " ".join(semantic_terms).strip() or q
    
    return HybridQueryIntent(
        structured_intent=struct_intent,
        semantic_query=semantic_query
    )

def route_query(question: str, auth_ctx: Dict[str, Any]) -> QueryRouteResult:
    """
    Analyzes the user question and routes to structured, semantic, or hybrid.
    """
    q = question.strip()
    q_lower = q.lower()
    
    # 1. Check for Hybrid patterns
    for pat in HYBRID_PATTERNS:
        if re.search(pat, q_lower):
            hybrid_intent = extract_hybrid_intent(q)
            if hybrid_intent:
                return QueryRouteResult(
                    route="hybrid",
                    intent=hybrid_intent.structured_intent,
                    hybrid_intent=hybrid_intent,
                    raw_question=q
                )
            
    # 2. Check for Self Lookup ("Show my employee information", "my salary", "my profile")
    if re.search(r"\b(?:my\s+employee|my\s+profile|my\s+details|my\s+info|my\s+information|my\s+salary|who\s+am\s+i)\b", q_lower):
        intent = StructuredQueryIntent(
            entity="employees",
            operation="lookup",
            filters={"self": True},
            fields=[]
        )
        if "salary" in q_lower:
            intent.fields = ["salary_amount", "salary_bonus"]
        return QueryRouteResult(route="structured", intent=intent, raw_question=q)
        
    # 3. Check for Manager Reports ("Who reports to manager MGR-1000001?")
    mgr_id = extract_manager_id(q)
    if mgr_id and re.search(r"\b(?:reports\s+to|reporting\s+to|reportees|under\s+manager)\b", q_lower):
        intent = StructuredQueryIntent(
            entity="employees",
            operation="list",
            filters={"manager_id": mgr_id},
            fields=["employee_id", "name", "department", "work_location", "grade"]
        )
        return QueryRouteResult(route="structured", intent=intent, raw_question=q)

    # 4. Check for Specific Employee Lookup ("What is employee E006's department?", "Show employee E006")
    emp_id = extract_employee_id(q)
    if emp_id:
        req_field = extract_field_name(q)
        fields = [req_field] if req_field else []
        intent = StructuredQueryIntent(
            entity="employees",
            operation="lookup",
            filters={"employee_id": emp_id},
            fields=fields
        )
        return QueryRouteResult(route="structured", intent=intent, raw_question=q)

    # 5. Check for Aggregations on Employees (Average salary, Total salary, Min/Max salary)
    agg_match = re.search(r"\b(average|avg|mean|total|sum|highest|max|maximum|lowest|min|minimum)\s+(salary|bonus|pay|compensation)\b", q_lower)
    if agg_match:
        agg_word = agg_match.group(1)
        field_word = agg_match.group(2)
        
        agg_op = "avg"
        if agg_word in ("total", "sum"):
            agg_op = "sum"
        elif agg_word in ("highest", "max", "maximum"):
            agg_op = "max"
        elif agg_word in ("lowest", "min", "minimum"):
            agg_op = "min"
            
        target_col = "salary_bonus" if "bonus" in field_word else "salary_amount"
        dept = extract_department(q)
        filters = {}
        if dept:
            filters["department"] = dept
            
        intent = StructuredQueryIntent(
            entity="employees",
            operation="aggregate",
            aggregation=agg_op,
            target_field=target_col,
            filters=filters
        )
        return QueryRouteResult(route="structured", intent=intent, raw_question=q)

    # 6. Check for Count ("How many employees are in Engineering?", "count of employees")
    if re.search(r"\b(?:how\s+many\s+employees|count\s+of\s+employees|number\s+of\s+employees|employee\s+count|headcount)\b", q_lower):
        dept = extract_department(q)
        filters = {}
        if dept:
            filters["department"] = dept
            
        intent = StructuredQueryIntent(
            entity="employees",
            operation="count",
            aggregation="count",
            target_field="*",
            filters=filters
        )
        return QueryRouteResult(route="structured", intent=intent, raw_question=q)

    # 7. Check for List Employees in Department ("Show employees in the Finance department.")
    if re.search(r"\b(?:show|list|find|get|all)\s+employees\b", q_lower) or (
        extract_department(q) and re.search(r"\bemployees\b", q_lower)
    ):
        dept = extract_department(q)
        filters = {}
        if dept:
            filters["department"] = dept
            
        intent = StructuredQueryIntent(
            entity="employees",
            operation="list",
            filters=filters,
            fields=["employee_id", "name", "department", "work_location"]
        )
        return QueryRouteResult(route="structured", intent=intent, raw_question=q)

    # 8. Check for Department list ("List departments", "show departments")
    if re.search(r"\b(?:list|show|all)\s+departments\b", q_lower):
        intent = StructuredQueryIntent(
            entity="departments",
            operation="list",
            fields=["name", "description"]
        )
        return QueryRouteResult(route="structured", intent=intent, raw_question=q)

    # 9. Default to Semantic RAG for unstructured/document queries
    return QueryRouteResult(route="semantic", intent=None, raw_question=q)
