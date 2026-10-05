"""
Server-side authorization policy for structured queries.
Enforces:
1. Column allowlist filtering based on authoritative role and ownership
2. Row-level access control with parameterized SQL predicates
3. Aggregation security (target field authorization & pre-aggregation row filtering)
4. Information-leakage prevention (safe refusals for unauthorized rows or columns)
"""
from typing import Dict, Any, List, Set, Optional, Tuple
from psycopg2 import sql

# Column definitions
PUBLIC_COLUMNS: Set[str] = {"employee_id", "name", "department", "work_location"}
INTERNAL_COLUMNS: Set[str] = {"grade", "hire_date", "manager_id", "nationality", "sex"}
CONFIDENTIAL_HR_COLUMNS: Set[str] = {"date_of_birth", "contact_numbers", "address", "emergency_contacts"}
CONFIDENTIAL_FINANCIAL_COLUMNS: Set[str] = {"salary_amount", "salary_bonus"}
HIGHLY_CONFIDENTIAL_COLUMNS: Set[str] = {"bank_details", "tax_code"}

ALL_EMPLOYEE_COLUMNS: Set[str] = (
    PUBLIC_COLUMNS
    | INTERNAL_COLUMNS
    | CONFIDENTIAL_HR_COLUMNS
    | CONFIDENTIAL_FINANCIAL_COLUMNS
    | HIGHLY_CONFIDENTIAL_COLUMNS
)

def get_allowed_columns_for_user(auth_ctx: Dict[str, Any], is_self: bool = False) -> Set[str]:
    """
    Returns the allowlist of columns the user is permitted to view.
    """
    role = auth_ctx.get("role", "employee")
    
    # Self-access grants access to user's own data
    if is_self:
        return ALL_EMPLOYEE_COLUMNS.copy()
        
    if role == "admin":
        return ALL_EMPLOYEE_COLUMNS.copy()
        
    if role == "finance_manager":
        return PUBLIC_COLUMNS | INTERNAL_COLUMNS | CONFIDENTIAL_FINANCIAL_COLUMNS
        
    if role == "hr_manager":
        return PUBLIC_COLUMNS | INTERNAL_COLUMNS | CONFIDENTIAL_HR_COLUMNS
        
    if role == "engineering_manager":
        return PUBLIC_COLUMNS | INTERNAL_COLUMNS
        
    # Regular employee querying other records: only public directory columns
    return PUBLIC_COLUMNS.copy()


def is_field_authorized_for_aggregation(
    target_field: Optional[str],
    auth_ctx: Dict[str, Any]
) -> bool:
    """
    Validates whether the user is authorized to aggregate over target_field.
    """
    if not target_field or target_field == "*":
        return True
        
    role = auth_ctx.get("role", "employee")
    
    # Salary aggregations only allowed for admin and finance_manager
    if target_field in ("salary_amount", "salary_bonus"):
        return role in ("admin", "finance_manager")
        
    # Confidential HR aggregations only allowed for admin and hr_manager
    if target_field in CONFIDENTIAL_HR_COLUMNS:
        return role in ("admin", "hr_manager")
        
    # Highly confidential fields cannot be aggregated
    if target_field in HIGHLY_CONFIDENTIAL_COLUMNS:
        return role == "admin"
        
    return True


def build_row_authorization_clause(
    auth_ctx: Dict[str, Any],
    table_alias: str = "e"
) -> Tuple[sql.Composable, List[Any]]:
    """
    Builds the parameterized SQL predicate enforcing row-level access control.
    Enforces:
    1. Tenant isolation
    2. Admin bypass within tenant
    3. Employee self-match
    4. Role-based employee_permissions
    5. User-specific employee_permissions
    """
    tenant_id = auth_ctx.get("tenant_id", "TENANT-001")
    role = auth_ctx.get("role", "employee")
    user_db_id = auth_ctx.get("db_id") or -1
    employee_pk = auth_ctx.get("employee_id") or -1
    
    clause = sql.SQL(
        """
        {alias}.tenant_id = %s
        AND (
            %s = 'admin'
            OR (%s = 'employee' AND {alias}.id = %s)
            OR EXISTS (
                SELECT 1 FROM employee_permissions ep
                JOIN roles r ON ep.role_id = r.id
                WHERE ep.employee_id = {alias}.id AND r.name = %s
            )
            OR EXISTS (
                SELECT 1 FROM employee_permissions ep
                WHERE ep.employee_id = {alias}.id AND ep.user_id = %s
            )
        )
        """
    ).format(alias=sql.Identifier(table_alias))
    
    params = [tenant_id, role, role, employee_pk, role, user_db_id]
    return clause, params
