from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

class StructuredQueryIntent(BaseModel):
    """
    Constrained structured query intent.
    Never allows arbitrary SQL or write operations.
    """
    entity: Literal["employees", "departments"] = "employees"
    operation: Literal["count", "list", "lookup", "aggregate", "group_by"] = "list"
    filters: Dict[str, Any] = Field(default_factory=dict)
    fields: List[str] = Field(default_factory=list)
    aggregation: Optional[Literal["avg", "count", "sum", "min", "max"]] = None
    target_field: Optional[str] = None
    group_by_field: Optional[str] = None
    limit: int = 50

class HybridQueryIntent(BaseModel):
    """
    Constrained hybrid query intent binding structured database intent
    with an authorized semantic query string.
    """
    structured_intent: StructuredQueryIntent
    semantic_query: str

class QueryRouteResult(BaseModel):
    route: Literal["structured", "semantic", "hybrid", "hybrid_unsupported"]
    intent: Optional[StructuredQueryIntent] = None
    hybrid_intent: Optional[HybridQueryIntent] = None
    raw_question: str
