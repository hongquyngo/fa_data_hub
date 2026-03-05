# utils/inbound_cost/cost_service.py
# Business logic for Inbound Logistic Cost module.
# Pattern mirrors utils/vendor_invoice/invoice_service.py

import pandas as pd
import logging
from typing import Dict, Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class CostService:
    """Business logic for inbound logistic cost entries."""

    # ── Validation ────────────────────────────────────────────────────────────

    @staticmethod
    def validate_new_entry(
        cost_type_id: Optional[int],
        arrival_id:   Optional[int],
        amount:       float,
    ) -> Tuple[bool, str]:
        """
        Validate inputs before creating a cost entry.
        Returns (is_valid, error_message).
        """
        if not cost_type_id:
            return False, "Please select a charge type."
        if not arrival_id:
            return False, "Please select a Cargo Arrival Note (CAN)."
        if amount is None or amount <= 0:
            return False, "Amount must be greater than 0."
        return True, ""

    @staticmethod
    def validate_edit(
        cost_type_id: Optional[int],
        amount:       float,
        original:     Dict,
    ) -> Tuple[bool, str, list]:
        """
        Validate edit inputs and build human-readable change list.
        Returns (is_valid, error_message, changes_list).
        """
        if not cost_type_id:
            return False, "Charge type is required.", []
        if amount is None or amount <= 0:
            return False, "Amount must be greater than 0.", []

        changes = []
        if cost_type_id != original.get("cost_type_id"):
            changes.append(
                f"Charge type: **{original.get('logistic_charge','—')}** → updated"
            )
        orig_amount = float(original.get("amount", 0) or 0)
        if abs(amount - orig_amount) > 0.001:
            cur = original.get("currency_code", "")
            changes.append(
                f"Amount: **{orig_amount:,.2f} {cur}** → **{amount:,.2f} {cur}**"
            )

        return True, "", changes

    # ── Summary calculations ──────────────────────────────────────────────────

    @staticmethod
    def compute_kpis(df: pd.DataFrame) -> Dict:
        """
        Compute summary KPIs from the filtered cost DataFrame.
        Used by the page header metrics row.
        """
        if df.empty:
            return {
                "total_entries": 0,
                "unique_cans":   0,
                "total_usd":     0.0,
                "intl_usd":      0.0,
                "local_usd":     0.0,
                "unique_couriers": 0,
            }

        usd = df["amount_usd"].fillna(0)
        intl  = df[df["category"] == "INTERNATIONAL"]["amount_usd"].fillna(0).sum()
        local = df[df["category"] == "LOCAL"]["amount_usd"].fillna(0).sum()

        return {
            "total_entries":   len(df),
            "unique_cans":     df["can_number"].nunique(),
            "total_usd":       round(usd.sum(), 2),
            "intl_usd":        round(intl, 2),
            "local_usd":       round(local, 2),
            "unique_couriers": df["courier"].nunique(),
        }

    # ── Display formatting ────────────────────────────────────────────────────

    @staticmethod
    def prepare_display_df(df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare the DataFrame for st.dataframe display.
        Keeps cost_id as hidden id column (dropped in the dataframe call).
        """
        if df.empty:
            return df

        d = df.copy()

        # Date
        if "arrival_date" in d.columns:
            d["arrival_date"] = pd.to_datetime(d["arrival_date"]).dt.strftime("%Y-%m-%d")

        # Category badge
        d["cat_badge"] = d["category"].map({
            "INTERNATIONAL": "🟦 INTL",
            "LOCAL":         "🟩 LOCAL",
        }).fillna(d["category"])

        # Amount display
        d["amount_display"] = d.apply(
            lambda r: f"{r['amount']:,.2f} {r.get('currency_code','')}"
            if pd.notna(r.get("amount")) else "—",
            axis=1,
        )
        d["usd_display"] = d["amount_usd"].apply(
            lambda x: f"${x:,.2f}" if pd.notna(x) else "—"
        )
        d["cpu_display"] = d["cost_per_unit_usd"].apply(
            lambda x: f"${x:,.4f}" if pd.notna(x) else "—"
        )
        d["doc_count"] = d["doc_count"].fillna(0).astype(int)

        col_map = {
            "cost_id":         "cost_id",
            "can_number":      "CAN #",
            "cat_badge":       "Category",
            "logistic_charge": "Charge Type",
            "courier":         "Courier",
            "amount_display":  "Amount",
            "usd_display":     "USD",
            "cpu_display":     "$/Unit",
            "arrival_date":    "Date",
            "warehouse_name":  "Warehouse",
            "ship_method":     "Ship Method",
            "shipment_type":   "Shipment",
            "doc_count":       "Docs",
        }
        existing = {k: v for k, v in col_map.items() if k in d.columns}
        return d[list(existing.keys())].rename(columns=existing)
