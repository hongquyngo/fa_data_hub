# utils/inbound_cost/cost_data.py
# All DB queries for Inbound Logistic Cost module.
# Primary source: inbound_logistic_charge_full_view
# Write target:   arrival_delivery_cost_entity
# Pattern mirrors utils/vendor_invoice/invoice_data.py

import pandas as pd
from sqlalchemy import text
import streamlit as st
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

from ..db import get_db_engine

logger = logging.getLogger(__name__)


# ============================================================================
# READ — MAIN LIST
# ============================================================================

@st.cache_data(ttl=60, show_spinner=False)
def get_recent_costs(limit: int = 500) -> pd.DataFrame:
    """
    Load cost entries from inbound_logistic_charge_full_view.
    Returns flat DataFrame ready for display/filtering.
    """
    try:
        engine = get_db_engine()
        query = text("""
        SELECT
            cost_id,
            cost_type_id,
            logistic_charge,
            category,
            arrival_id,
            can_number,
            arrival_date,
            arrival_year,
            arrival_month,
            is_date_adjusted,
            arrival_status,
            ship_method,
            ttl_weight,
            dimension,
            warehouse_id,
            warehouse_name,
            warehouse_country,
            warehouse_state,
            sender_id,
            sender,
            sender_code,
            sender_country,
            receiver_id,
            receiver,
            receiver_code,
            receiver_country,
            shipment_type,
            logistics_vendor_id,
            courier,
            courier_code,
            amount,
            currency_code,
            usd_exchange_rate,
            amount_usd,
            total_arrival_qty,
            arrival_line_count,
            cost_per_unit_usd,
            product_codes,
            product_names,
            doc_count,
            doc_paths,
            doc_names,
            cost_created_by,
            cost_created_date,
            cost_modified_date
        FROM inbound_logistic_charge_full_view
        ORDER BY arrival_date DESC, cost_id ASC
        LIMIT :lim
        """)
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"lim": limit})
        return df
    except Exception as e:
        logger.error(f"Error loading inbound costs: {e}")
        return pd.DataFrame()


# ============================================================================
# READ — FILTER OPTIONS
# ============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_filter_options() -> Dict:
    """
    Distinct filter values — derived from view, cached 5 min.
    Pattern mirrors invoice_data.get_filter_options().
    """
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            def _distinct(col):
                rows = conn.execute(text(
                    f"SELECT DISTINCT {col} FROM inbound_logistic_charge_full_view "
                    f"WHERE {col} IS NOT NULL ORDER BY {col}"
                )).fetchall()
                return [r[0] for r in rows]

            return {
                "categories":    _distinct("category"),
                "charge_types":  _distinct("logistic_charge"),
                "couriers":      _distinct("courier"),
                "warehouses":    _distinct("warehouse_name"),
                "senders":       _distinct("sender"),
                "ship_methods":  _distinct("ship_method"),
            }
    except Exception as e:
        logger.error(f"Error loading filter options: {e}")
        return {k: [] for k in ["categories", "charge_types", "couriers",
                                 "warehouses", "senders", "ship_methods"]}


# ============================================================================
# READ — SINGLE ENTRY (for dialogs)
# ============================================================================

def get_cost_by_id(cost_id: int) -> Optional[Dict]:
    """Fetch single cost entry by ID. Used by view/edit dialogs."""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT *
        FROM inbound_logistic_charge_full_view
        WHERE cost_id = :cost_id
        """)
        with engine.connect() as conn:
            row = conn.execute(query, {"cost_id": cost_id}).mappings().fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error loading cost #{cost_id}: {e}")
        return None


# ============================================================================
# READ — DROPDOWN SOURCES FOR CREATE/EDIT DIALOGS
# ============================================================================

@st.cache_data(ttl=120, show_spinner=False)
def get_cost_type_options() -> pd.DataFrame:
    """
    Master list from delivery_cost_entity.
    Returns DataFrame with columns: id, name, type (INTERNATIONAL | LOCAL).
    """
    try:
        engine = get_db_engine()
        query = text("""
        SELECT id, name, type
        FROM delivery_cost_entity
        WHERE delete_flag = b'0'
        ORDER BY type, name
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Error loading cost types: {e}")
        return pd.DataFrame(columns=["id", "name", "type"])


@st.cache_data(ttl=120, show_spinner=False)
def get_arrival_options(limit: int = 500) -> pd.DataFrame:
    """
    Recent arrivals for CAN selection in create dialog.
    Returns id, arrival_note_number, arrival_date, sender, receiver, warehouse_name.
    """
    try:
        engine = get_db_engine()
        query = text("""
        SELECT
            a.id,
            a.arrival_note_number,
            DATE(COALESCE(a.adjust_arrival_date, a.arrival_date)) AS arrival_date,
            a.status,
            s.english_name          AS sender,
            r.english_name          AS receiver,
            wh.name                 AS warehouse_name,
            ic.id                   AS intl_currency_id,
            ic.code                 AS intl_currency_code,
            lc.id                   AS local_currency_id,
            lc.code                 AS local_currency_code,
            a.usd_international_cost_currency_exchange_rate,
            a.usd_local_cost_currency_exchange_rate
        FROM arrivals a
        LEFT JOIN companies  s  ON a.sender_id            = s.id
        LEFT JOIN companies  r  ON a.receiver_id          = r.id
        LEFT JOIN warehouses wh ON a.warehouse_id         = wh.id
        LEFT JOIN currencies ic ON a.internal_currency_id = ic.id
        LEFT JOIN currencies lc ON a.local_currency_id    = lc.id
        WHERE a.delete_flag = b'0'
          AND a.status != 'REQUEST_STATUS'
        ORDER BY a.arrival_date DESC
        LIMIT :lim
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn, params={"lim": limit})
    except Exception as e:
        logger.error(f"Error loading arrivals: {e}")
        return pd.DataFrame()


# ============================================================================
# READ — CURRENCY OPTIONS
# ============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def get_currency_options() -> pd.DataFrame:
    """Load all active currencies. Returns DataFrame: id, code, name."""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT id, code, name
        FROM currencies
        WHERE delete_flag = 0 OR delete_flag IS NULL
        ORDER BY code
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Error loading currencies: {e}")
        return pd.DataFrame(columns=["id", "code", "name"])


# ============================================================================
# WRITE — UPDATE ARRIVAL CURRENCY
# ============================================================================

def update_arrival_currency(
    arrival_id:    int,
    category:      str,    # 'INTERNATIONAL' | 'LOCAL'
    currency_id:   int,
    exchange_rate: float,  # 1 unit of currency = exchange_rate USD
) -> Tuple[bool, str]:
    """
    Update currency + USD exchange rate on arrivals record.
    INTERNATIONAL → internal_currency_id  + usd_international_cost_currency_exchange_rate
    LOCAL         → local_currency_id     + usd_local_cost_currency_exchange_rate
    WARNING: affects ALL cost entries for this arrival.
    """
    try:
        engine = get_db_engine()
        col_id   = "internal_currency_id"   if category == "INTERNATIONAL" else "local_currency_id"
        col_rate = "usd_international_cost_currency_exchange_rate" if category == "INTERNATIONAL" \
                   else "usd_local_cost_currency_exchange_rate"
        with engine.begin() as conn:
            conn.execute(text(f"""
            UPDATE arrivals
            SET    {col_id}   = :cid,
                   {col_rate} = :rate,
                   modified_date = NOW()
            WHERE  id = :aid AND delete_flag = b'0'
            """), {"cid": currency_id, "rate": exchange_rate, "aid": arrival_id})
        logger.info(f"Updated arrival #{arrival_id} {category} currency → id={currency_id}, rate={exchange_rate:.8f}")
        return True, ""
    except Exception as e:
        err = f"Failed to update arrival currency: {e}"
        logger.error(err)
        return False, err


# ============================================================================
# READ — GOODS VALUE FOR ANOMALY DETECTION
# ============================================================================

def get_arrival_goods_value_usd(arrival_id: int) -> float:
    """Total goods value in USD: SUM(unit_cost × qty × exchange_rate) / usd_landed_rate."""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT COALESCE(
            SUM(COALESCE(ppo.unit_cost, 0) * ad.arrival_quantity * ad.exchange_rate)
            / NULLIF(a.usd_landed_cost_currency_exchange_rate, 0),
            0
        ) AS goods_value_usd
        FROM arrival_details ad
        JOIN arrivals a ON ad.arrival_id = a.id AND a.delete_flag = b'0'
        LEFT JOIN product_purchase_orders ppo
               ON ad.product_purchase_order_id = ppo.id AND ppo.delete_flag = 0
        WHERE ad.arrival_id = :aid AND ad.delete_flag = b'0'
        """)
        with engine.connect() as conn:
            row = conn.execute(query, {"aid": arrival_id}).fetchone()
        return float(row[0]) if row and row[0] else 0.0
    except Exception as e:
        logger.error(f"Error getting goods value for arrival #{arrival_id}: {e}")
        return 0.0


@st.cache_data(ttl=300, show_spinner=False)
def get_vendor_options() -> pd.DataFrame:
    """Logistics vendor / courier options from companies table."""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT id, english_name AS name, company_code
        FROM companies
        WHERE delete_flag = b'0'
        ORDER BY english_name
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Error loading vendors: {e}")
        return pd.DataFrame(columns=["id", "name", "company_code"])


# ============================================================================
# WRITE — CREATE
# ============================================================================

def create_cost_entry(
    cost_type_id:  int,
    arrival_type:  str,          # 'INTERNATIONAL' | 'LOCAL'
    arrival_id:    int,
    vendor_id:     Optional[int],
    amount:        float,
    created_by:    str,
) -> Tuple[bool, int, str]:
    """
    Insert new record into arrival_delivery_cost_entity.

    DDL-confirmed columns:
        id, amount, intl_arrival_id, local_arrival_id,
        type_id, created_by, created_date, delete_flag,
        modified_date, vendor_id

    Returns (success, new_id, error_message).
    """
    try:
        engine = get_db_engine()
        intl_id  = arrival_id if arrival_type == "INTERNATIONAL" else None
        local_id = arrival_id if arrival_type == "LOCAL"         else None

        with engine.begin() as conn:
            result = conn.execute(text("""
            INSERT INTO arrival_delivery_cost_entity (
                type_id,
                intl_arrival_id,
                local_arrival_id,
                vendor_id,
                amount,
                delete_flag,
                created_by,
                created_date,
                modified_date
            ) VALUES (
                :type_id,
                :intl_arrival_id,
                :local_arrival_id,
                :vendor_id,
                :amount,
                b'0',
                :created_by,
                NOW(),
                NOW()
            )
            """), {
                "type_id":          cost_type_id,
                "intl_arrival_id":  intl_id,
                "local_arrival_id": local_id,
                "vendor_id":        vendor_id,
                "amount":           amount,
                "created_by":       created_by,
            })
            new_id = result.lastrowid

        logger.info(f"Created cost entry #{new_id}")
        return True, new_id, ""
    except Exception as e:
        err = f"Failed to create cost entry: {e}"
        logger.error(err)
        return False, 0, err


# ============================================================================
# WRITE — UPDATE
# ============================================================================

def update_cost_entry(
    cost_id:      int,
    cost_type_id: int,
    vendor_id:    Optional[int],
    amount:       float,
    updated_by:   str,
) -> Tuple[bool, str]:
    """
    Update amount, type_id, vendor_id on an existing cost entry.
    Returns (success, error_message).
    """
    try:
        engine = get_db_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
            UPDATE arrival_delivery_cost_entity
            SET type_id       = :type_id,
                vendor_id     = :vendor_id,
                amount        = :amount,
                modified_date = NOW()
            WHERE id          = :cost_id
              AND delete_flag = b'0'
            """), {
                "cost_id":   cost_id,
                "type_id":   cost_type_id,
                "vendor_id": vendor_id,
                "amount":    amount,
            })
            if result.rowcount == 0:
                return False, "Cost entry not found or already deleted"

        logger.info(f"Updated cost entry #{cost_id}")
        return True, ""
    except Exception as e:
        err = f"Failed to update cost entry: {e}"
        logger.error(err)
        return False, err


# ============================================================================
# WRITE — DELETE (soft)
# ============================================================================

def delete_cost_entry(cost_id: int, deleted_by: str) -> Tuple[bool, str]:
    """
    Soft-delete a cost entry (delete_flag = b'1').
    Returns (success, message).
    """
    try:
        engine = get_db_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
            UPDATE arrival_delivery_cost_entity
            SET delete_flag   = b'1',
                modified_date = NOW()
            WHERE id          = :cost_id
              AND delete_flag = b'0'
            """), {"cost_id": cost_id})
            if result.rowcount == 0:
                return False, "Cost entry not found or already deleted"

        logger.info(f"Soft-deleted cost entry #{cost_id} by {deleted_by}")
        return True, "Cost entry deleted successfully"
    except Exception as e:
        err = f"Failed to delete cost entry: {e}"
        logger.error(err)
        return False, err


# ============================================================================
# ATTACHMENTS — arrival_cost_medias + medias
# ============================================================================

def get_cost_attachments(cost_id: int) -> pd.DataFrame:
    """
    Get all attachments for a cost entry.

    DDL-confirmed:
        arrival_cost_medias: id, cost_id, media_id, created_by, created_date, delete_flag
        medias:              id, name, path, created_by, created_date, updated_date
    """
    try:
        engine = get_db_engine()
        query = text("""
        SELECT
            acm.id          AS link_id,
            acm.cost_id,
            m.id            AS media_id,
            m.name          AS filename,
            m.path          AS s3_key,
            m.created_by,
            m.created_date,
            CONCAT(e.first_name, ' ', e.last_name) AS uploaded_by
        FROM arrival_cost_medias acm
        JOIN  medias    m ON acm.media_id   = m.id
        LEFT JOIN employees e ON m.created_by = e.keycloak_id
        WHERE acm.cost_id     = :cost_id
          AND acm.delete_flag = b'0'
        ORDER BY m.created_date DESC
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn, params={"cost_id": cost_id})
    except Exception as e:
        logger.error(f"Error loading attachments for cost #{cost_id}: {e}")
        return pd.DataFrame()


def save_cost_media_records(
    cost_id:    int,
    s3_keys:    List[str],
    keycloak_id: str,
) -> Tuple[bool, List[int], str]:
    """
    Insert media records and link them to cost entry via arrival_cost_medias.

    medias DDL columns: id, created_by, created_date, name, path, updated_date, version
    arrival_cost_medias DDL columns: id, version, cost_id, media_id, created_by,
                                      created_date, delete_flag, modified_date
    Returns (success, media_ids, error_message).
    """
    if not s3_keys:
        return True, [], ""

    media_ids = []
    try:
        engine = get_db_engine()
        with engine.begin() as conn:
            for s3_key in s3_keys:
                filename = s3_key.split("/")[-1]

                # Insert into medias
                res = conn.execute(text("""
                INSERT INTO medias (
                    created_by, created_date, name, path, updated_date, version
                ) VALUES (
                    :created_by, NOW(), :name, :path, NOW(), 0
                )
                """), {"created_by": keycloak_id, "name": filename, "path": s3_key})
                media_id = res.lastrowid
                media_ids.append(media_id)

                # Link to cost entry
                conn.execute(text("""
                INSERT INTO arrival_cost_medias (
                    cost_id, media_id, created_by, created_date,
                    delete_flag, modified_date, version
                ) VALUES (
                    :cost_id, :media_id, :created_by, NOW(),
                    b'0', NOW(), 0
                )
                """), {"cost_id": cost_id, "media_id": media_id, "created_by": keycloak_id})

                logger.info(f"Linked media #{media_id} → cost #{cost_id}")

        return True, media_ids, ""
    except Exception as e:
        err = f"Failed to save media records: {e}"
        logger.error(err)
        return False, [], err


def delete_cost_attachment(link_id: int) -> Tuple[bool, str]:
    """Soft-delete an arrival_cost_medias link."""
    try:
        engine = get_db_engine()
        with engine.begin() as conn:
            result = conn.execute(text("""
            UPDATE arrival_cost_medias
            SET delete_flag   = b'1',
                modified_date = NOW()
            WHERE id          = :link_id
              AND delete_flag = b'0'
            """), {"link_id": link_id})
            if result.rowcount == 0:
                return False, "Attachment not found or already deleted"
        return True, "Attachment removed"
    except Exception as e:
        err = f"Error deleting attachment: {e}"
        logger.error(err)
        return False, err


# ============================================================================
# ANALYTICS
# ============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_cost_trend_monthly() -> pd.DataFrame:
    """Monthly cost trend split by INTERNATIONAL / LOCAL."""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT
            arrival_year,
            arrival_month,
            category,
            CONCAT(arrival_year, '-', LPAD(arrival_month, 2, '0')) AS month_label,
            COUNT(*)          AS entry_count,
            SUM(amount_usd)   AS total_usd
        FROM inbound_logistic_charge_full_view
        WHERE amount_usd   IS NOT NULL
          AND arrival_year IS NOT NULL
        GROUP BY arrival_year, arrival_month, category
        ORDER BY arrival_year DESC, arrival_month DESC
        LIMIT 36
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Error in cost_trend_monthly: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def get_cost_by_courier() -> pd.DataFrame:
    """Aggregate cost USD by courier."""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT
            COALESCE(courier, 'Unknown') AS courier,
            category,
            COUNT(*)          AS entry_count,
            SUM(amount_usd)   AS total_usd,
            AVG(amount_usd)   AS avg_usd
        FROM inbound_logistic_charge_full_view
        WHERE amount_usd IS NOT NULL
        GROUP BY courier, category
        ORDER BY total_usd DESC
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Error in cost_by_courier: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def get_cost_by_charge_type() -> pd.DataFrame:
    """Breakdown by individual charge type."""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT
            logistic_charge,
            category,
            COUNT(*)               AS entry_count,
            SUM(amount_usd)        AS total_usd,
            AVG(cost_per_unit_usd) AS avg_cost_per_unit
        FROM inbound_logistic_charge_full_view
        WHERE amount_usd IS NOT NULL
        GROUP BY logistic_charge, category
        ORDER BY total_usd DESC
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Error in cost_by_charge_type: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def get_cost_by_warehouse() -> pd.DataFrame:
    """Cost aggregated by destination warehouse."""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT
            COALESCE(warehouse_name, 'Unknown') AS warehouse,
            warehouse_country,
            category,
            COUNT(*)        AS entry_count,
            SUM(amount_usd) AS total_usd
        FROM inbound_logistic_charge_full_view
        WHERE amount_usd IS NOT NULL
        GROUP BY warehouse_name, warehouse_country, category
        ORDER BY total_usd DESC
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Error in cost_by_warehouse: {e}")
        return pd.DataFrame()