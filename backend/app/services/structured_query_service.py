"""
Secure structured query execution service.
Enforces:
- Pre-execution authorization policy checks
- Strict parameterized SQL query generation (psycopg2.sql)
- Row-level access control before result exposure
- Column-level filtering to prevent data leakage
- Grounded citations for database sources
- Uniform safe refusal on any authorization or empty authorized match
"""
import time
from typing import Dict, Any, List, Optional
from decimal import Decimal
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from database.connection import get_db_connection
from backend.app.schemas.structured_query import StructuredQueryIntent
from backend.app.schemas.chat import ChatResponse, Citation
from backend.app.services.structured_authorization import (
    get_allowed_columns_for_user,
    is_field_authorized_for_aggregation,
    build_row_authorization_clause,
    ALL_EMPLOYEE_COLUMNS
)

from backend.app.services.audit_service import record_audit_event

SAFE_REFUSAL = "I don't have enough authorized information to answer that."

def format_currency(val: Any) -> str:
    try:
        f = float(val)
        return f"${f:,.2f}"
    except (ValueError, TypeError):
        return str(val)

def execute_structured_query(
    intent: StructuredQueryIntent,
    auth_ctx: Dict[str, Any],
    raw_question: str
) -> ChatResponse:
    t_start = time.time()
    resp = _execute_structured_query_internal(intent, auth_ctx, raw_question, t_start)
    lat_ms = int((time.time() - t_start) * 1000)
    
    # Audit log structured query outcome
    record_audit_event(
        user_id=auth_ctx.get("user_id", "unknown"),
        action="structured_query",
        resource_type="structured_data",
        result="authorized" if resp.grounded else "denied",
        query=raw_question,
        latency_ms=lat_ms,
        metadata={
            "route": "structured",
            "entity": intent.entity,
            "operation": intent.operation,
            "table": "employees" if intent.entity == "employees" else intent.entity,
            "fields": intent.fields,
            "citation_count": len(resp.citations),
            "grounded": resp.grounded,
            "tenant_id": auth_ctx.get("tenant_id")
        }
    )
    return resp

def _execute_structured_query_internal(
    intent: StructuredQueryIntent,
    auth_ctx: Dict[str, Any],
    raw_question: str,
    t_start: float
) -> ChatResponse:
    tenant_id = auth_ctx.get("tenant_id", "TENANT-001")
    
    # 1. Obsolete entities (employees, departments) have been retired permanently
    if intent.entity in ("departments", "employees"):
        return ChatResponse(
            answer=SAFE_REFUSAL,
            citations=[],
            retrieval_count=0,
            grounded=False,
            latencies={"database": 0.0, "total": round(time.time() - t_start, 4)}
        )

    # 2. Determine if this is a self-access query
    is_self = False
    if intent.filters.get("self"):
        is_self = True
    elif intent.filters.get("employee_id"):
        target_emp = str(intent.filters["employee_id"]).upper()
        user_emp_code = str(auth_ctx.get("employee_code") or "").upper()
        if user_emp_code and target_emp == user_emp_code:
            is_self = True
            
    # 3. Check field authorization for aggregations
    if intent.operation == "aggregate":
        if not is_field_authorized_for_aggregation(intent.target_field, auth_ctx):
            record_audit_event(
                user_id=auth_ctx.get("user_id", "unknown"),
                action="authorization_denied",
                resource_type="employee_field",
                result="denied",
                metadata={
                    "route": "structured",
                    "operation": "aggregate",
                    "field": intent.target_field,
                    "reason": "aggregation_acl",
                    "tenant_id": tenant_id
                }
            )
            return ChatResponse(
                answer=SAFE_REFUSAL,
                citations=[],
                retrieval_count=0,
                grounded=False,
                latencies={"database": 0.0, "total": round(time.time() - t_start, 4)}
            )

    # 4. Column allowlist verification for employees
    allowed_cols = get_allowed_columns_for_user(auth_ctx, is_self=is_self)
    if intent.fields:
        for f in intent.fields:
            if f not in allowed_cols:
                record_audit_event(
                    user_id=auth_ctx.get("user_id", "unknown"),
                    action="authorization_denied",
                    resource_type="employee_field",
                    result="denied",
                    metadata={
                        "route": "structured",
                        "operation": intent.operation,
                        "field": f,
                        "reason": "column_acl",
                        "tenant_id": tenant_id
                    }
                )
                return ChatResponse(
                    answer=SAFE_REFUSAL,
                    citations=[],
                    retrieval_count=0,
                    grounded=False,
                    latencies={"database": 0.0, "total": round(time.time() - t_start, 4)}
                )

    # 5. Build parameterized query for employees
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Build WHERE clause
            row_clause, row_params = build_row_authorization_clause(auth_ctx, table_alias="e")
            where_conditions = [row_clause]
            query_params = list(row_params)
            
            # Filter: Department
            if "department" in intent.filters:
                where_conditions.append(sql.SQL("LOWER(d.name) = LOWER(%s)"))
                query_params.append(intent.filters["department"])
                
            # Filter: Manager ID
            if "manager_id" in intent.filters:
                where_conditions.append(sql.SQL("LOWER(e.manager_id) = LOWER(%s)"))
                query_params.append(intent.filters["manager_id"])
                
            # Filter: Employee ID
            if "employee_id" in intent.filters:
                where_conditions.append(sql.SQL("LOWER(e.employee_id) = LOWER(%s)"))
                query_params.append(intent.filters["employee_id"])
                
            # Filter: Self
            if intent.filters.get("self"):
                emp_pk = auth_ctx.get("employee_id")
                emp_code = auth_ctx.get("employee_code")
                if emp_pk:
                    where_conditions.append(sql.SQL("e.id = %s"))
                    query_params.append(emp_pk)
                elif emp_code:
                    where_conditions.append(sql.SQL("LOWER(e.employee_id) = LOWER(%s)"))
                    query_params.append(emp_code)
                else:
                    # User is not linked to any employee record
                    return ChatResponse(
                        answer=SAFE_REFUSAL,
                        citations=[],
                        retrieval_count=0,
                        grounded=False,
                        latencies={"database": 0.0, "total": round(time.time() - t_start, 4)}
                    )

            combined_where = sql.SQL(" AND ").join(where_conditions)

            # -------------------------------------------------------------
            # OPERATION: COUNT
            # -------------------------------------------------------------
            if intent.operation == "count":
                query = sql.SQL(
                    """
                    SELECT COUNT(*)::int as emp_count
                    FROM employees e
                    LEFT JOIN departments d ON e.department_id = d.id
                    WHERE {where_clause}
                    """
                ).format(where_clause=combined_where)
                
                t_q = time.time()
                cur.execute(query, query_params)
                row = cur.fetchone()
                db_lat = round(time.time() - t_q, 4)
                
                count_val = row["emp_count"] if row else 0
                
                # If filtered by department and 0 authorized rows found
                if count_val == 0 and ("department" in intent.filters or "manager_id" in intent.filters):
                    # To avoid leaking existence vs non-existence of restricted departments/managers
                    return ChatResponse(
                        answer=SAFE_REFUSAL,
                        citations=[],
                        retrieval_count=0,
                        grounded=False,
                        latencies={"database": db_lat, "total": round(time.time() - t_start, 4)}
                    )
                    
                dept_desc = f" in {intent.filters['department']}" if "department" in intent.filters else ""
                answer_text = f"There are {count_val} authorized employees{dept_desc} [SRC-DB-1]."
                
                citation = Citation(
                    source_id="[SRC-DB-1]",
                    chunk_id="db_employees_count",
                    source_type="postgresql",
                    filename="postgresql://employees",
                    table="employees",
                    query_type="count",
                    fields=["*"],
                    tenant_id=tenant_id,
                    authorized=True
                )
                
                return ChatResponse(
                    answer=answer_text,
                    citations=[citation],
                    retrieval_count=1,
                    grounded=True,
                    latencies={"database": db_lat, "total": round(time.time() - t_start, 4)}
                )

            # -------------------------------------------------------------
            # OPERATION: AGGREGATE (AVG, SUM, MIN, MAX)
            # -------------------------------------------------------------
            elif intent.operation == "aggregate":
                agg_fn = (intent.aggregation or "avg").upper()
                if agg_fn not in ("AVG", "SUM", "MIN", "MAX"):
                    agg_fn = "AVG"
                    
                target_col = intent.target_field or "salary_amount"
                # Safe identifier mapping
                valid_agg_cols = {"salary_amount": "salary_amount", "salary_bonus": "salary_bonus"}
                db_col = valid_agg_cols.get(target_col, "salary_amount")
                
                query = sql.SQL(
                    """
                    SELECT {agg_fn}(e.{col}) as agg_result, COUNT(e.{col}) as row_count
                    FROM employees e
                    LEFT JOIN departments d ON e.department_id = d.id
                    WHERE {where_clause}
                    """
                ).format(
                    agg_fn=sql.SQL(agg_fn),
                    col=sql.Identifier(db_col),
                    where_clause=combined_where
                )
                
                t_q = time.time()
                cur.execute(query, query_params)
                row = cur.fetchone()
                db_lat = round(time.time() - t_q, 4)
                
                if not row or row["agg_result"] is None or row["row_count"] == 0:
                    return ChatResponse(
                        answer=SAFE_REFUSAL,
                        citations=[],
                        retrieval_count=0,
                        grounded=False,
                        latencies={"database": db_lat, "total": round(time.time() - t_start, 4)}
                    )
                    
                agg_val = row["agg_result"]
                formatted_val = format_currency(agg_val)
                dept_desc = f" {intent.filters['department']}" if "department" in intent.filters else ""
                op_desc = "average" if agg_fn == "AVG" else agg_fn.lower()
                field_desc = "salary" if db_col == "salary_amount" else "salary bonus"
                
                answer_text = f"The {op_desc} {field_desc} of authorized{dept_desc} employees is {formatted_val} [SRC-DB-1]."
                
                citation = Citation(
                    source_id="[SRC-DB-1]",
                    chunk_id=f"db_employees_{op_desc}_{db_col}",
                    source_type="postgresql",
                    filename="postgresql://employees",
                    table="employees",
                    query_type="aggregate",
                    fields=[db_col],
                    tenant_id=tenant_id,
                    authorized=True
                )
                
                return ChatResponse(
                    answer=answer_text,
                    citations=[citation],
                    retrieval_count=row["row_count"],
                    grounded=True,
                    latencies={"database": db_lat, "total": round(time.time() - t_start, 4)}
                )

            # -------------------------------------------------------------
            # OPERATION: LOOKUP (Specific Employee or Self)
            # -------------------------------------------------------------
            elif intent.operation == "lookup":
                # Select authorized columns
                select_items = [
                    sql.SQL("e.employee_id"),
                    sql.SQL("e.name"),
                    sql.SQL("d.name as department"),
                    sql.SQL("e.work_location")
                ]
                
                extra_candidates = [
                    ("grade", "e.grade"),
                    ("hire_date", "e.hire_date"),
                    ("manager_id", "e.manager_id"),
                    ("nationality", "e.nationality"),
                    ("sex", "e.sex"),
                    ("date_of_birth", "e.date_of_birth"),
                    ("contact_numbers", "e.contact_numbers"),
                    ("emergency_contacts", "e.emergency_contacts"),
                    ("address", "e.address"),
                    ("salary_amount", "e.salary_amount"),
                    ("salary_bonus", "e.salary_bonus"),
                    ("bank_details", "e.bank_details"),
                    ("tax_code", "e.tax_code")
                ]
                
                included_fields = ["employee_id", "name", "department", "work_location"]
                for f_name, col_sql in extra_candidates:
                    if f_name in allowed_cols:
                        select_items.append(sql.SQL(f"{col_sql} as {f_name}"))
                        included_fields.append(f_name)
                        
                query = sql.SQL(
                    """
                    SELECT {cols}
                    FROM employees e
                    LEFT JOIN departments d ON e.department_id = d.id
                    WHERE {where_clause}
                    LIMIT 1
                    """
                ).format(
                    cols=sql.SQL(", ").join(select_items),
                    where_clause=combined_where
                )
                
                t_q = time.time()
                cur.execute(query, query_params)
                row = cur.fetchone()
                db_lat = round(time.time() - t_q, 4)
                
                if not row:
                    return ChatResponse(
                        answer=SAFE_REFUSAL,
                        citations=[],
                        retrieval_count=0,
                        grounded=False,
                        latencies={"database": db_lat, "total": round(time.time() - t_start, 4)}
                    )
                    
                # Format response
                emp_code = row["employee_id"]
                emp_name = row["name"]
                dept_name = row.get("department", "Unknown")
                
                # If a specific field was requested (e.g. "What is employee E006's department?")
                if intent.fields and len(intent.fields) == 1:
                    target = intent.fields[0]
                    val = row.get(target)
                    if target in ("salary_amount", "salary_bonus") and val is not None:
                        val = format_currency(val)
                    answer_text = f"Employee {emp_code}'s {target.replace('_', ' ')} is {val} [SRC-DB-1]."
                else:
                    lines = [f"Employee Information for {emp_name} ({emp_code}) [SRC-DB-1]:"]
                    lines.append(f"- Department: {dept_name}")
                    if "work_location" in row and row["work_location"]:
                        lines.append(f"- Location: {row['work_location']}")
                    if "grade" in row and row["grade"]:
                        lines.append(f"- Grade: {row['grade']}")
                    if "manager_id" in row and row["manager_id"]:
                        lines.append(f"- Manager: {row['manager_id']}")
                    if "hire_date" in row and row["hire_date"]:
                        lines.append(f"- Hire Date: {row['hire_date']}")
                    if "salary_amount" in row and row["salary_amount"] is not None:
                        lines.append(f"- Salary: {format_currency(row['salary_amount'])}")
                    if "salary_bonus" in row and row["salary_bonus"] is not None:
                        lines.append(f"- Bonus: {format_currency(row['salary_bonus'])}")
                    if "tax_code" in row and row["tax_code"]:
                        lines.append(f"- Tax Code: {row['tax_code']}")
                    answer_text = "\n".join(lines)
                    
                citation = Citation(
                    source_id="[SRC-DB-1]",
                    chunk_id=f"db_employee_{emp_code}",
                    source_type="postgresql",
                    filename="postgresql://employees",
                    table="employees",
                    query_type="lookup",
                    record_ids=[emp_code],
                    fields=included_fields,
                    tenant_id=tenant_id,
                    authorized=True
                )
                
                return ChatResponse(
                    answer=answer_text,
                    citations=[citation],
                    retrieval_count=1,
                    grounded=True,
                    latencies={"database": db_lat, "total": round(time.time() - t_start, 4)}
                )

            # -------------------------------------------------------------
            # OPERATION: LIST (Employees in Department or Manager Reportees)
            # -------------------------------------------------------------
            else: # list
                select_items = [
                    sql.SQL("e.employee_id"),
                    sql.SQL("e.name"),
                    sql.SQL("d.name as department"),
                    sql.SQL("e.work_location")
                ]
                
                included_fields = ["employee_id", "name", "department", "work_location"]
                if "grade" in allowed_cols:
                    select_items.append(sql.SQL("e.grade as grade"))
                    included_fields.append("grade")
                if "manager_id" in allowed_cols:
                    select_items.append(sql.SQL("e.manager_id as manager_id"))
                    included_fields.append("manager_id")
                    
                query = sql.SQL(
                    """
                    SELECT {cols}
                    FROM employees e
                    LEFT JOIN departments d ON e.department_id = d.id
                    WHERE {where_clause}
                    ORDER BY e.employee_id ASC
                    LIMIT %s
                    """
                ).format(
                    cols=sql.SQL(", ").join(select_items),
                    where_clause=combined_where
                )
                
                t_q = time.time()
                cur.execute(query, query_params + [intent.limit])
                rows = cur.fetchall()
                db_lat = round(time.time() - t_q, 4)
                
                if not rows:
                    return ChatResponse(
                        answer=SAFE_REFUSAL,
                        citations=[],
                        retrieval_count=0,
                        grounded=False,
                        latencies={"database": db_lat, "total": round(time.time() - t_start, 4)}
                    )
                    
                record_ids = [r["employee_id"] for r in rows]
                
                if "manager_id" in intent.filters:
                    header = f"Employees reporting to manager {intent.filters['manager_id']} ({len(rows)} found) [SRC-DB-1]:"
                elif "department" in intent.filters:
                    header = f"Authorized employees in {intent.filters['department']} ({len(rows)} found) [SRC-DB-1]:"
                else:
                    header = f"Authorized employees ({len(rows)} found) [SRC-DB-1]:"
                    
                lines = [header]
                for r in rows:
                    dept = r.get("department", "Unknown")
                    loc = r.get("work_location", "")
                    loc_str = f", {loc}" if loc else ""
                    lines.append(f"- {r['employee_id']}: {r['name']} ({dept}{loc_str})")
                    
                answer_text = "\n".join(lines)
                
                citation = Citation(
                    source_id="[SRC-DB-1]",
                    chunk_id="db_employees_list",
                    source_type="postgresql",
                    filename="postgresql://employees",
                    table="employees",
                    query_type="list",
                    record_ids=record_ids,
                    fields=included_fields,
                    tenant_id=tenant_id,
                    authorized=True
                )
                
                return ChatResponse(
                    answer=answer_text,
                    citations=[citation],
                    retrieval_count=len(rows),
                    grounded=True,
                    latencies={"database": db_lat, "total": round(time.time() - t_start, 4)}
                )
    finally:
        conn.close()


def _execute_departments_list(auth_ctx: Dict[str, Any], t_start: float) -> ChatResponse:
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            t_q = time.time()
            cur.execute("SELECT id, name, description FROM departments ORDER BY id ASC;")
            rows = cur.fetchall()
            db_lat = round(time.time() - t_q, 4)
            
            if not rows:
                return ChatResponse(
                    answer=SAFE_REFUSAL,
                    citations=[],
                    retrieval_count=0,
                    grounded=False,
                    latencies={"database": db_lat, "total": round(time.time() - t_start, 4)}
                )
                
            lines = [f"Departments ({len(rows)} total) [SRC-DB-1]:"]
            for r in rows:
                lines.append(f"- {r['name']}: {r.get('description', '')}")
                
            citation = Citation(
                source_id="[SRC-DB-1]",
                chunk_id="db_departments_list",
                source_type="postgresql",
                filename="postgresql://departments",
                table="departments",
                query_type="list",
                record_ids=[str(r["id"]) for r in rows],
                fields=["id", "name", "description"],
                tenant_id=auth_ctx.get("tenant_id", "TENANT-001"),
                authorized=True
            )
            
            return ChatResponse(
                answer="\n".join(lines),
                citations=[citation],
                retrieval_count=len(rows),
                grounded=True,
                latencies={"database": db_lat, "total": round(time.time() - t_start, 4)}
            )
    finally:
        conn.close()
