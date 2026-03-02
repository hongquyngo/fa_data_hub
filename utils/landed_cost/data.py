"""
Landed Cost - Data Layer (Refactored)
Class-based data access for cost lookup, analysis, and drill-down.

Source view: avg_landed_cost_looker_view
Deep-dive: arrival_details, opening_balances, purchase_orders, etc.
"""

import logging
from typing import Optional, List, Dict, Any

import pandas as pd
import streamlit as st
from sqlalchemy import text

from utils.db import get_db_engine

logger = logging.getLogger(__name__)


class LandedCostData:
    """Data access layer for Landed Cost module."""

    def __init__(self):
        self.engine = get_db_engine()

    # ================================================================
    # Helpers
    # ================================================================

    @staticmethod
    def _build_in_clause(field: str, values: list, prefix: str) -> tuple:
        """Build parameterized IN clause.
        Returns (condition_str, params_dict).
        """
        placeholders = ", ".join([f":{prefix}_{i}" for i in range(len(values))])
        params = {f"{prefix}_{i}": v for i, v in enumerate(values)}
        return f"{field} IN ({placeholders})", params

    # ================================================================
    # Filter Options
    # ================================================================

    @st.cache_data(ttl=300, show_spinner=False)
    def get_filter_options(_self) -> Dict[str, Any]:
        """Fetch distinct filter values for dropdowns."""
        try:
            with _self.engine.connect() as conn:
                entities = pd.read_sql(text("""
                    SELECT DISTINCT entity_id, legal_entity
                    FROM avg_landed_cost_looker_view
                    ORDER BY legal_entity
                """), conn)

                brands = pd.read_sql(text("""
                    SELECT DISTINCT brand
                    FROM avg_landed_cost_looker_view
                    WHERE brand IS NOT NULL
                    ORDER BY brand
                """), conn)

                years = pd.read_sql(text("""
                    SELECT DISTINCT cost_year
                    FROM avg_landed_cost_looker_view
                    ORDER BY cost_year DESC
                """), conn)

            return {
                "entities": entities,
                "brands": brands["brand"].tolist() if not brands.empty else [],
                "years": years["cost_year"].tolist() if not years.empty else [],
            }
        except Exception as e:
            logger.error(f"Error loading filter options: {e}")
            return {"entities": pd.DataFrame(), "brands": [], "years": []}

    # ================================================================
    # Main Data Query
    # ================================================================

    @st.cache_data(ttl=120, show_spinner=False)
    def get_landed_cost_data(
        _self,
        entity_ids: tuple = None,
        brand_list: tuple = None,
        year_list: tuple = None,
        product_search: str = None,
    ) -> pd.DataFrame:
        """Fetch landed cost data with optional filters."""
        try:
            conditions = ["1=1"]
            params = {}

            if entity_ids:
                cond, p = _self._build_in_clause("entity_id", list(entity_ids), "eid")
                conditions.append(cond)
                params.update(p)

            if brand_list:
                cond, p = _self._build_in_clause("brand", list(brand_list), "brand")
                conditions.append(cond)
                params.update(p)

            if year_list:
                cond, p = _self._build_in_clause("cost_year", list(year_list), "year")
                conditions.append(cond)
                params.update(p)

            if product_search:
                conditions.append("(pt_code LIKE :p_search OR product_pn LIKE :p_search)")
                params["p_search"] = f"%{product_search}%"

            where_clause = " AND ".join(conditions)

            query = f"""
                SELECT
                    cost_year, is_current_year, entity_id, legal_entity,
                    product_id, pt_code, product_pn, brand, standard_uom,
                    total_landed_value_usd, total_quantity,
                    average_landed_cost_usd, min_landed_cost_usd, max_landed_cost_usd,
                    earliest_source_date, latest_source_date, source_count,
                    arrival_quantity, opening_balance_quantity, transaction_count
                FROM avg_landed_cost_looker_view
                WHERE {where_clause}
                ORDER BY cost_year DESC, legal_entity, pt_code
            """

            with _self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            return df
        except Exception as e:
            logger.error(f"Error loading landed cost data: {e}")
            return pd.DataFrame()

    # ================================================================
    # Year-over-Year Comparison
    # ================================================================

    @st.cache_data(ttl=120, show_spinner=False)
    def get_yoy_comparison(
        _self,
        entity_ids: tuple = None,
        brand_list: tuple = None,
    ) -> pd.DataFrame:
        """Get YoY cost comparison for current year and 2 previous years."""
        try:
            conditions = ["v.cost_year >= YEAR(CURDATE()) - 2"]
            params = {}

            if entity_ids:
                cond, p = _self._build_in_clause("v.entity_id", list(entity_ids), "eid")
                conditions.append(cond)
                params.update(p)

            if brand_list:
                cond, p = _self._build_in_clause("v.brand", list(brand_list), "brand")
                conditions.append(cond)
                params.update(p)

            where_clause = " AND ".join(conditions)

            query = f"""
                SELECT
                    v.cost_year, v.legal_entity, v.pt_code, v.product_pn,
                    v.brand, v.standard_uom, v.average_landed_cost_usd,
                    v.total_quantity, v.total_landed_value_usd
                FROM avg_landed_cost_looker_view v
                WHERE {where_clause}
                ORDER BY v.pt_code, v.cost_year DESC
            """

            with _self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            return df
        except Exception as e:
            logger.error(f"Error loading YoY comparison: {e}")
            return pd.DataFrame()

    # ================================================================
    # Product Cost History (all years for one product)
    # ================================================================

    @st.cache_data(ttl=120, show_spinner=False)
    def get_product_cost_history(
        _self,
        product_id: int,
        entity_id: int = None,
    ) -> pd.DataFrame:
        """Get full cost history for a specific product across all years."""
        try:
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

            with _self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            return df
        except Exception as e:
            logger.error(f"Error loading product cost history: {e}")
            return pd.DataFrame()

    # ================================================================
    # Deep-Dive: Arrival Sources
    # ================================================================

    @st.cache_data(ttl=120, show_spinner=False)
    def get_arrival_sources(
        _self,
        product_id: int,
        entity_id: int,
        cost_year: int,
    ) -> pd.DataFrame:
        """Get individual arrival records contributing to a product's
        landed cost in a given year + entity."""
        try:
            query = """
                SELECT
                    ad.id AS arrival_detail_id,
                    a.arrival_note_number,
                    DATE(COALESCE(a.adjust_arrival_date, a.arrival_date)) AS arrival_date,
                    a.status AS arrival_status,

                    po.po_number,
                    po.external_ref_number,
                    po.po_type,
                    DATE(po.po_date) AS po_date,

                    vendor.english_name AS vendor_name,
                    vendor.company_code AS vendor_code,

                    ad.arrival_quantity,
                    ad.stocked_in AS stocked_in_qty,
                    ad.landed_cost AS landed_cost_local,
                    lcc.code AS landed_cost_currency,
                    a.usd_landed_cost_currency_exchange_rate AS exchange_rate,
                    ROUND(ad.landed_cost
                        / NULLIF(a.usd_landed_cost_currency_exchange_rate, 0), 4)
                        AS landed_cost_usd,
                    ROUND(ad.landed_cost * ad.arrival_quantity
                        / NULLIF(a.usd_landed_cost_currency_exchange_rate, 0), 2)
                        AS total_value_usd,

                    wh.name AS warehouse_name,
                    a.ship_method,
                    CONCAT(emp.first_name, ' ', emp.last_name) AS created_by_name

                FROM arrival_details ad
                INNER JOIN arrivals a ON ad.arrival_id = a.id
                LEFT JOIN product_purchase_orders ppo ON ad.product_purchase_order_id = ppo.id
                LEFT JOIN purchase_orders po ON ppo.purchase_order_id = po.id
                LEFT JOIN companies vendor ON po.seller_company_id = vendor.id
                LEFT JOIN currencies lcc ON a.landed_cost_currency_id = lcc.id
                LEFT JOIN warehouses wh ON a.warehouse_id = wh.id
                LEFT JOIN employees emp ON a.created_by = emp.keycloak_id

                WHERE a.delete_flag = 0
                  AND COALESCE(ad.delete_flag, 0) = 0
                  AND a.status <> 'REQUEST_STATUS'
                  AND ad.landed_cost > 0
                  AND ad.arrival_quantity > 0
                  AND ad.product_id = :product_id
                  AND a.receiver_id = :entity_id
                  AND YEAR(a.arrival_date) = :cost_year
                ORDER BY a.arrival_date DESC
            """
            params = {
                "product_id": product_id,
                "entity_id": entity_id,
                "cost_year": cost_year,
            }

            with _self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            return df
        except Exception as e:
            logger.error(f"Error loading arrival sources: {e}")
            return pd.DataFrame()

    # ================================================================
    # Deep-Dive: Full Arrival Detail
    # ================================================================

    def get_arrival_detail(self, arrival_detail_id: int) -> Optional[Dict[str, Any]]:
        """Deep-dive into a single arrival detail line — full PO traceability."""
        try:
            query = """
                SELECT
                    ad.id AS arrival_detail_id,
                    ad.arrival_quantity,
                    ad.stocked_in AS stocked_in_qty,
                    ad.landed_cost AS landed_cost_local,
                    ad.import_tax,
                    ad.exchange_rate AS product_exchange_rate,

                    a.arrival_note_number,
                    DATE(COALESCE(a.adjust_arrival_date, a.arrival_date)) AS arrival_date,
                    a.status AS arrival_status,
                    a.ship_method,
                    a.ttl_weight,
                    a.dimension,
                    lcc.code AS landed_cost_currency,
                    a.usd_landed_cost_currency_exchange_rate,
                    ROUND(ad.landed_cost
                        / NULLIF(a.usd_landed_cost_currency_exchange_rate, 0), 4)
                        AS unit_cost_usd,

                    a.internal_charge,
                    ic.code AS internal_currency,
                    a.internal_exchange_rate,
                    a.local_charge,
                    lc.code AS local_currency,
                    a.local_exchange_rate,

                    receiver.english_name AS receiver_entity,
                    wh.name AS warehouse_name,

                    po.po_number,
                    po.external_ref_number,
                    po.po_type,
                    DATE(po.po_date) AS po_date,
                    po_cur.code AS po_currency,

                    ppo.quantity AS po_quantity,
                    ppo.unit_cost AS po_unit_cost,
                    ppo.purchase_quantity AS po_buying_quantity,
                    ppo.purchase_unit_cost AS po_buying_unit_cost,
                    ppo.purchaseuom AS buying_uom,
                    ppo.conversion AS uom_conversion,
                    ppo.vat_gst,
                    DATE(COALESCE(ppo.adjust_eta, ppo.eta)) AS eta,
                    DATE(COALESCE(ppo.adjust_etd, ppo.etd)) AS etd,

                    vendor.english_name AS vendor_name,
                    vendor.company_code AS vendor_code,
                    vendor_country.name AS vendor_country,

                    p.pt_code,
                    p.name AS product_name,
                    p.package_size,
                    p.uom AS standard_uom,
                    b.brand_name AS brand,

                    tt.name AS trade_term,
                    pt.name AS payment_term,
                    CONCAT(emp.first_name, ' ', emp.last_name) AS created_by_name

                FROM arrival_details ad
                INNER JOIN arrivals a ON ad.arrival_id = a.id
                INNER JOIN products p ON ad.product_id = p.id
                LEFT JOIN brands b ON p.brand_id = b.id
                LEFT JOIN currencies lcc ON a.landed_cost_currency_id = lcc.id
                LEFT JOIN currencies ic ON a.internal_currency_id = ic.id
                LEFT JOIN currencies lc ON a.local_currency_id = lc.id
                LEFT JOIN companies receiver ON a.receiver_id = receiver.id
                LEFT JOIN warehouses wh ON a.warehouse_id = wh.id
                LEFT JOIN employees emp ON a.created_by = emp.keycloak_id
                LEFT JOIN product_purchase_orders ppo ON ad.product_purchase_order_id = ppo.id
                LEFT JOIN purchase_orders po ON ppo.purchase_order_id = po.id
                LEFT JOIN currencies po_cur ON po.currency_id = po_cur.id
                LEFT JOIN companies vendor ON po.seller_company_id = vendor.id
                LEFT JOIN countries vendor_country ON vendor.country_id = vendor_country.id
                LEFT JOIN trade_terms tt ON po.trade_term_id = tt.id
                LEFT JOIN payment_terms pt ON po.payment_term_id = pt.id
                WHERE ad.id = :arrival_detail_id
            """

            with self.engine.connect() as conn:
                result = conn.execute(text(query), {"arrival_detail_id": arrival_detail_id})
                row = result.fetchone()

            if row:
                return dict(zip(result.keys(), row))
            return None
        except Exception as e:
            logger.error(f"Error loading arrival detail: {e}")
            return None

    # ================================================================
    # Deep-Dive: Opening Balance Sources
    # ================================================================

    @st.cache_data(ttl=120, show_spinner=False)
    def get_ob_sources(
        _self,
        product_id: int,
        entity_id: int,
        cost_year: int,
    ) -> pd.DataFrame:
        """Get individual opening balance records for a product/entity/year."""
        try:
            query = """
                SELECT
                    ob.id AS ob_id,
                    ob.opening_balance AS quantity,
                    ob.landed_cost AS landed_cost_local,
                    cur.code AS currency,
                    ob.batch_no,
                    DATE(ob.expired_date) AS expiry_date,

                    COALESCE(uer_y.usd_to_local_rate, uer_f.usd_to_local_rate)
                        AS exchange_rate_used,
                    CASE
                        WHEN uer_y.usd_to_local_rate IS NOT NULL THEN 'Yearly Avg'
                        WHEN uer_f.usd_to_local_rate IS NOT NULL THEN 'All-time Avg'
                        ELSE 'N/A'
                    END AS rate_source,
                    ROUND(ob.landed_cost
                        / NULLIF(COALESCE(uer_y.usd_to_local_rate,
                                          uer_f.usd_to_local_rate), 0), 4)
                        AS unit_cost_usd,
                    ROUND(ob.landed_cost * ob.opening_balance
                        / NULLIF(COALESCE(uer_y.usd_to_local_rate,
                                          uer_f.usd_to_local_rate), 0), 2)
                        AS total_value_usd,

                    wh.name AS warehouse_name,
                    ob.approval AS is_approved,
                    ob.created_date,
                    CONCAT(creator.first_name, ' ', creator.last_name)
                        AS created_by_name

                FROM opening_balances ob
                INNER JOIN currencies cur ON ob.currency_id = cur.id
                LEFT JOIN warehouses wh ON ob.warehouse_id = wh.id

                LEFT JOIN employees creator ON ob.created_by = creator.keycloak_id

                LEFT JOIN (
                    SELECT to_currency_code AS currency_code,
                           YEAR(rate_date) AS rate_year,
                           AVG(rate_value) AS usd_to_local_rate
                    FROM exchange_rates
                    WHERE from_currency_code = 'USD'
                      AND delete_flag = 0 AND rate_value > 0
                    GROUP BY to_currency_code, YEAR(rate_date)
                ) uer_y ON uer_y.currency_code = cur.code
                       AND uer_y.rate_year = YEAR(ob.created_date)

                LEFT JOIN (
                    SELECT to_currency_code AS currency_code,
                           AVG(rate_value) AS usd_to_local_rate
                    FROM exchange_rates
                    WHERE from_currency_code = 'USD'
                      AND delete_flag = 0 AND rate_value > 0
                    GROUP BY to_currency_code
                ) uer_f ON uer_f.currency_code = cur.code

                WHERE ob.delete_flag = 0
                  AND ob.landed_cost > 0
                  AND ob.opening_balance > 0
                  AND ob.product_id = :product_id
                  AND COALESCE(wh.company_id, 1) = :entity_id
                  AND YEAR(ob.created_date) = :cost_year
                ORDER BY ob.created_date DESC
            """
            params = {
                "product_id": product_id,
                "entity_id": entity_id,
                "cost_year": cost_year,
            }

            with _self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            return df
        except Exception as e:
            logger.error(f"Error loading OB sources: {e}")
            return pd.DataFrame()

    # ================================================================
    # Export Data
    # ================================================================

    def get_export_data(
        self,
        entity_ids: tuple = None,
        brand_list: tuple = None,
        year_list: tuple = None,
        product_search: str = None,
    ) -> pd.DataFrame:
        """Get data formatted for Excel export."""
        df = self.get_landed_cost_data(
            entity_ids=entity_ids,
            brand_list=brand_list,
            year_list=year_list,
            product_search=product_search,
        )
        if df.empty:
            return df

        export_columns = {
            "cost_year": "Year",
            "legal_entity": "Entity",
            "pt_code": "PT Code",
            "product_pn": "Product",
            "brand": "Brand",
            "standard_uom": "UOM",
            "average_landed_cost_usd": "Avg Cost (USD)",
            "total_quantity": "Total Qty",
            "total_landed_value_usd": "Total Value (USD)",
            "min_landed_cost_usd": "Min Cost (USD)",
            "max_landed_cost_usd": "Max Cost (USD)",
            "arrival_quantity": "Arrival Qty",
            "opening_balance_quantity": "OB Qty",
            "transaction_count": "Txn Count",
            "earliest_source_date": "Earliest Date",
            "latest_source_date": "Latest Date",
        }

        existing = [c for c in export_columns if c in df.columns]
        export_df = df[existing].copy()
        export_df.rename(
            columns={k: v for k, v in export_columns.items() if k in existing},
            inplace=True,
        )
        return export_df