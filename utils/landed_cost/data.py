"""
Landed Cost - Data Layer
Queries avg_landed_cost_looker_view for cost lookup and analysis.

Uses utils.db patterns:
- execute_query_df() for simple SELECT → DataFrame
- get_db_engine() + pd.read_sql(text()) for parameterized queries
"""

import pandas as pd
import streamlit as st
from sqlalchemy import text
from utils.db import get_db_engine, execute_query_df


# ============================================================
# Filter Options
# ============================================================

@st.cache_data(ttl=300)
def get_filter_options():
    """Fetch distinct filter values for dropdowns."""
    entities = execute_query_df("""
        SELECT DISTINCT entity_id, legal_entity 
        FROM avg_landed_cost_looker_view 
        ORDER BY legal_entity
    """)

    brands = execute_query_df("""
        SELECT DISTINCT brand 
        FROM avg_landed_cost_looker_view 
        WHERE brand IS NOT NULL 
        ORDER BY brand
    """)

    years = execute_query_df("""
        SELECT DISTINCT cost_year 
        FROM avg_landed_cost_looker_view 
        ORDER BY cost_year DESC
    """)

    products = execute_query_df("""
        SELECT DISTINCT product_id, pt_code, product_pn 
        FROM avg_landed_cost_looker_view 
        ORDER BY pt_code
    """)

    return {
        "entities": entities,
        "brands": brands["brand"].tolist() if not brands.empty else [],
        "years": years["cost_year"].tolist() if not years.empty else [],
        "products": products,
    }


# ============================================================
# Main Data Query
# ============================================================

@st.cache_data(ttl=120)
def get_landed_cost_data(
    entity_ids: list = None,
    brand_list: list = None,
    year_list: list = None,
    product_search: str = None,
):
    """
    Fetch landed cost data with optional filters.
    Returns DataFrame from avg_landed_cost_looker_view.
    """
    conditions = ["1=1"]
    params = {}

    if entity_ids:
        placeholders = ", ".join([f":eid_{i}" for i in range(len(entity_ids))])
        conditions.append(f"entity_id IN ({placeholders})")
        for i, eid in enumerate(entity_ids):
            params[f"eid_{i}"] = eid

    if brand_list:
        placeholders = ", ".join([f":brand_{i}" for i in range(len(brand_list))])
        conditions.append(f"brand IN ({placeholders})")
        for i, b in enumerate(brand_list):
            params[f"brand_{i}"] = b

    if year_list:
        placeholders = ", ".join([f":year_{i}" for i in range(len(year_list))])
        conditions.append(f"cost_year IN ({placeholders})")
        for i, y in enumerate(year_list):
            params[f"year_{i}"] = y

    if product_search:
        conditions.append("(pt_code LIKE :p_search OR product_pn LIKE :p_search)")
        params["p_search"] = f"%{product_search}%"

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT 
            cost_year,
            is_current_year,
            entity_id,
            legal_entity,
            product_id,
            pt_code,
            product_pn,
            brand,
            standard_uom,
            total_landed_value_usd,
            total_quantity,
            average_landed_cost_usd,
            min_landed_cost_usd,
            max_landed_cost_usd,
            earliest_source_date,
            latest_source_date,
            source_count,
            arrival_quantity,
            opening_balance_quantity,
            transaction_count
        FROM avg_landed_cost_looker_view
        WHERE {where_clause}
        ORDER BY cost_year DESC, legal_entity, pt_code
    """

    engine = get_db_engine()
    df = pd.read_sql(text(query), engine, params=params)
    return df


# ============================================================
# Year-over-Year Comparison
# ============================================================

@st.cache_data(ttl=120)
def get_yoy_comparison(entity_ids: list = None, brand_list: list = None):
    """
    Get year-over-year cost comparison for products.
    Returns data for current year and 2 previous years.
    """
    conditions = ["v.cost_year >= YEAR(CURDATE()) - 2"]
    params = {}

    if entity_ids:
        placeholders = ", ".join([f":eid_{i}" for i in range(len(entity_ids))])
        conditions.append(f"v.entity_id IN ({placeholders})")
        for i, eid in enumerate(entity_ids):
            params[f"eid_{i}"] = eid

    if brand_list:
        placeholders = ", ".join([f":brand_{i}" for i in range(len(brand_list))])
        conditions.append(f"v.brand IN ({placeholders})")
        for i, b in enumerate(brand_list):
            params[f"brand_{i}"] = b

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT 
            v.cost_year,
            v.legal_entity,
            v.pt_code,
            v.product_pn,
            v.brand,
            v.standard_uom,
            v.average_landed_cost_usd,
            v.total_quantity,
            v.total_landed_value_usd
        FROM avg_landed_cost_looker_view v
        WHERE {where_clause}
        ORDER BY v.pt_code, v.cost_year DESC
    """

    engine = get_db_engine()
    df = pd.read_sql(text(query), engine, params=params)
    return df


# ============================================================
# Product Cost History (for detail drill-down)
# ============================================================

@st.cache_data(ttl=120)
def get_product_cost_history(product_id: int, entity_id: int = None):
    """Get full cost history for a specific product across all years."""
    conditions = ["product_id = :product_id"]
    params = {"product_id": product_id}

    if entity_id:
        conditions.append("entity_id = :entity_id")
        params["entity_id"] = entity_id

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT *
        FROM avg_landed_cost_looker_view
        WHERE {where_clause}
        ORDER BY cost_year ASC
    """

    engine = get_db_engine()
    df = pd.read_sql(text(query), engine, params=params)
    return df


# ============================================================
# Summary Statistics
# ============================================================

@st.cache_data(ttl=120)
def get_summary_stats(entity_ids: list = None, cost_year: int = None):
    """Get high-level summary stats for KPI cards."""
    conditions = ["1=1"]
    params = {}

    if entity_ids:
        placeholders = ", ".join([f":eid_{i}" for i in range(len(entity_ids))])
        conditions.append(f"entity_id IN ({placeholders})")
        for i, eid in enumerate(entity_ids):
            params[f"eid_{i}"] = eid

    if cost_year:
        conditions.append("cost_year = :cost_year")
        params["cost_year"] = cost_year
    else:
        conditions.append("is_current_year = 1")

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT 
            COUNT(DISTINCT product_id) AS total_products,
            COUNT(DISTINCT brand) AS total_brands,
            ROUND(SUM(total_landed_value_usd), 2) AS total_value_usd,
            ROUND(AVG(average_landed_cost_usd), 4) AS avg_cost_usd,
            COUNT(*) AS total_records,
            SUM(transaction_count) AS total_transactions
        FROM avg_landed_cost_looker_view
        WHERE {where_clause}
    """

    engine = get_db_engine()
    df = pd.read_sql(text(query), engine, params=params)
    return df.iloc[0] if not df.empty else None