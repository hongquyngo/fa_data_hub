# utils/inbound_cost/cost_calculator.py
# Recalculates arrival_details.landed_cost after any change to
# arrival_delivery_cost_entity (create / update / delete).
#
# ── Formula (from spec) ────────────────────────────────────────────────────
#
# NORMAL PATH  (Total Cost > 0):
#   UC_landed         = ppo.unit_price × ad.exchange_rate
#   Total Cost        = Σ (UC_landed × arrival_qty)
#   Intl / Unit       = UC_landed × (Total Intl Charge / Total Cost)
#   Cost Before Tax   = UC_landed + Intl / Unit
#   Taxed Cost        = Cost Before Tax × (1 + import_tax / 100)
#   Total Taxed Cost  = Σ (Taxed Cost × arrival_qty)
#   Local / Unit      = Taxed Cost × (Total Local Charge / Total Taxed Cost)
#   Landed Cost       = Taxed Cost + Local / Unit
#
# FALLBACK  (Total Cost = 0, i.e. all unit prices are zero):
#   Intl / Unit       = (arrival_qty × Total Intl Charge) / Total Qty
#   Local / Unit      = (arrival_qty × Total Local Charge) / Total Qty
#   Landed Cost       = Taxed Cost + Local / Unit
#   (Taxed Cost still applies import_tax to Cost Before Tax = 0 + Intl/Unit)
#
# All monetary values are in the arrival's *landed cost currency*.
# Charges come from arrival_delivery_cost_entity (summed in USD then converted).
# ──────────────────────────────────────────────────────────────────────────

import logging
from typing import Tuple, Dict, List, Optional
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ============================================================================
# PUBLIC ENTRY POINT
# ============================================================================

def recalculate_landed_cost(arrival_id: int) -> Tuple[bool, str, Dict]:
    """
    Recalculate and persist landed_cost for every active arrival_detail
    belonging to the given arrival.

    Triggered after create / update / delete of arrival_delivery_cost_entity.

    Returns:
        (success, message, stats)
        stats = {
            "arrival_id":        int,
            "details_updated":   int,
            "total_intl_usd":    float,
            "total_local_usd":   float,
            "allocation_method": "cost_based" | "quantity_based",
        }
    """
    from ..db import get_db_engine          # lazy to avoid circular import

    stats: Dict = {"arrival_id": arrival_id, "details_updated": 0,
                   "total_intl_usd": 0.0, "total_local_usd": 0.0,
                   "allocation_method": "cost_based"}
    try:
        engine = get_db_engine()
        with engine.begin() as conn:
            # ── 1. Arrival exchange rate ───────────────────────────────────
            arrival_row = _fetch_arrival(conn, arrival_id)
            if arrival_row is None:
                return False, f"Arrival #{arrival_id} not found.", stats

            usd_to_landed: float = float(
                arrival_row.get("usd_landed_cost_currency_exchange_rate") or 1.0
            )

            # ── 2. Charge totals (USD) from view ──────────────────────────
            charges = _fetch_charge_totals(conn, arrival_id)
            total_intl_usd   = float(charges.get("total_intl_usd")  or 0.0)
            total_local_usd  = float(charges.get("total_local_usd") or 0.0)
            stats["total_intl_usd"]  = total_intl_usd
            stats["total_local_usd"] = total_local_usd

            # Convert to landed cost currency
            total_intl_landed  = total_intl_usd  * usd_to_landed
            total_local_landed = total_local_usd * usd_to_landed

            # ── 3. Arrival details with unit cost ─────────────────────────
            details = _fetch_arrival_details(conn, arrival_id)
            if not details:
                logger.info(f"No arrival_details found for arrival #{arrival_id}.")
                return True, "No details to update.", stats

            # ── 4. Enrich with UC in landed cost currency ─────────────────
            for d in details:
                unit_price = float(d.get("unit_price") or 0.0)
                exch_rate  = float(d.get("exchange_rate") or 1.0)
                d["uc_landed"] = unit_price * exch_rate   # PO ccy → landed ccy

            # ── 5. Decide allocation method ────────────────────────────────
            total_cost = sum(d["uc_landed"] * float(d["arrival_quantity"])
                             for d in details)
            total_qty  = sum(float(d["arrival_quantity"]) for d in details)

            use_qty_based = (total_cost <= 0.0)
            stats["allocation_method"] = "quantity_based" if use_qty_based else "cost_based"

            logger.info(
                f"Arrival #{arrival_id}: total_cost={total_cost:.4f}, "
                f"total_qty={total_qty:.0f}, method={stats['allocation_method']}, "
                f"intl_landed={total_intl_landed:.4f}, local_landed={total_local_landed:.4f}"
            )

            # ── 6. Calculate new landed_cost per detail ────────────────────
            _calculate_landed_costs(
                details, total_cost, total_qty,
                total_intl_landed, total_local_landed,
                use_qty_based,
            )

            # ── 7. Persist ────────────────────────────────────────────────
            updated = _persist_landed_costs(conn, details)
            stats["details_updated"] = updated

        msg = (
            f"✅ Recalculated landed cost for arrival #{arrival_id}: "
            f"{updated} detail(s) updated "
            f"[{stats['allocation_method']}]."
        )
        logger.info(msg)
        return True, msg, stats

    except Exception as exc:
        err = f"Landed cost recalculation failed for arrival #{arrival_id}: {exc}"
        logger.exception(err)
        return False, err, stats


# ============================================================================
# CALCULATION CORE  (pure Python — no DB access)
# ============================================================================

def _calculate_landed_costs(
    details:             List[Dict],
    total_cost:          float,
    total_qty:           float,
    total_intl_landed:   float,
    total_local_landed:  float,
    use_qty_based:       bool,
) -> None:
    """
    Mutates each detail dict in-place, adding 'new_landed_cost'.
    All monetary values are in the arrival's landed cost currency.
    """
    # ── Pass 1: Intl charge + Taxed Cost ─────────────────────────────────────
    for d in details:
        uc    = d["uc_landed"]
        qty   = float(d["arrival_quantity"])
        tax   = float(d.get("import_tax") or 0.0) / 100.0   # DB stores as percent: 14 → 0.14

        if use_qty_based:
            # Quantity-proportional allocation (fallback when UC = 0)
            intl_per_unit = (qty * total_intl_landed / total_qty) if total_qty > 0 else 0.0
        else:
            # Cost-proportional allocation (normal path)
            intl_per_unit = uc * (total_intl_landed / total_cost)

        cost_before_tax = uc + intl_per_unit
        taxed_cost      = cost_before_tax * (1.0 + tax)

        d["intl_per_unit"] = intl_per_unit
        d["taxed_cost"]    = taxed_cost

    # ── Pass 2: Local charge allocation ──────────────────────────────────────
    total_taxed_cost = sum(
        d["taxed_cost"] * float(d["arrival_quantity"]) for d in details
    )
    use_qty_based_local = use_qty_based or (total_taxed_cost <= 0.0)

    for d in details:
        qty        = float(d["arrival_quantity"])
        taxed_cost = d["taxed_cost"]

        if use_qty_based_local:
            local_per_unit = (qty * total_local_landed / total_qty) if total_qty > 0 else 0.0
        else:
            # Proportional to taxed cost
            local_per_unit = taxed_cost * (total_local_landed / total_taxed_cost)

        d["local_per_unit"]     = local_per_unit
        d["new_landed_cost"]    = taxed_cost + local_per_unit


# ============================================================================
# DATABASE HELPERS
# ============================================================================

def _fetch_arrival(conn, arrival_id: int) -> Optional[Dict]:
    row = conn.execute(text("""
        SELECT usd_landed_cost_currency_exchange_rate
        FROM   arrivals
        WHERE  id          = :aid
          AND  delete_flag = b'0'
    """), {"aid": arrival_id}).mappings().fetchone()
    return dict(row) if row else None


def _fetch_charge_totals(conn, arrival_id: int) -> Dict:
    """
    Sum INTL and LOCAL charges (USD) from inbound_logistic_charge_full_view.
    The view already resolves arrival_id from intl_arrival_id / local_arrival_id.
    """
    row = conn.execute(text("""
        SELECT
            COALESCE(SUM(CASE WHEN category = 'INTERNATIONAL'
                         THEN COALESCE(amount_usd, 0) ELSE 0 END), 0) AS total_intl_usd,
            COALESCE(SUM(CASE WHEN category = 'LOCAL'
                         THEN COALESCE(amount_usd, 0) ELSE 0 END), 0) AS total_local_usd
        FROM inbound_logistic_charge_full_view
        WHERE arrival_id = :aid
    """), {"aid": arrival_id}).mappings().fetchone()
    return dict(row) if row else {"total_intl_usd": 0.0, "total_local_usd": 0.0}


def _fetch_arrival_details(conn, arrival_id: int) -> List[Dict]:
    """
    Fetch arrival_details with unit cost from product_purchase_orders.

    Column mapping (confirmed from can_tracking_full_view):
        ppo.unit_cost          = standard unit cost in PO currency (same UOM as arrival_quantity)
        ppo.purchase_unit_cost = buying unit cost in PO currency   (buying UOM)
        ad.exchange_rate       = PO currency → landed cost currency
        ad.import_tax          = import tax as percent (e.g. 14 = 14%) — divided by 100 in calc

    We use ppo.unit_cost because arrival_quantity is in standard UOM.
    """
    rows = conn.execute(text("""
        SELECT
            ad.id                           AS detail_id,
            ad.arrival_quantity,
            ad.exchange_rate,
            COALESCE(ad.import_tax, 0)      AS import_tax,
            COALESCE(ppo.unit_cost, 0)      AS unit_price
        FROM arrival_details ad
        LEFT JOIN product_purchase_orders ppo
               ON ad.product_purchase_order_id = ppo.id
              AND ppo.delete_flag = 0
        WHERE ad.arrival_id  = :aid
          AND ad.delete_flag = b'0'
    """), {"aid": arrival_id}).mappings().fetchall()
    return [dict(r) for r in rows]


def _persist_landed_costs(conn, details: List[Dict]) -> int:
    """
    Batch UPDATE arrival_details.landed_cost.
    Returns number of rows updated.
    """
    count = 0
    for d in details:
        new_lc = round(d.get("new_landed_cost", 0.0), 10)  # keep precision
        result = conn.execute(text("""
            UPDATE arrival_details
            SET    landed_cost   = :lc,
                   version       = version + 1
            WHERE  id            = :did
              AND  delete_flag   = b'0'
        """), {"lc": new_lc, "did": d["detail_id"]})
        count += result.rowcount
    return count
