"""
Page: Landed Cost Lookup & Analysis (v3.0)

Version: 3.0.0
Changes:
- v3.0: Landing Charges decomposition across all tabs
  + Purchase Cost vs Landing Charges breakdown
  + Landing Ratio analysis (= landing charges / purchase cost)
  + Cost decomposition in detail dialog (stacked bar + donut)
  + YoY comparison with purchase/landing decomposition + root-cause classification
  + Analytics: cost composition, ratio trend, ship method, vendor country, ratio heatmaps
  + Arrival sources with PO cost & landing charge per unit
  + Excel export with full breakdown columns

Features:
- Tab 1: Cost Lookup — main table, breakdown toggle, detail dialog with decomposition
- Tab 2: YoY Comparison — purchase vs landing YoY, root-cause classification
- Tab 3: Analytics — trends, distribution, heatmaps, landing charges analysis
"""

import logging
from datetime import datetime

import pandas as pd
import streamlit as st

from utils.auth import AuthManager
from utils.landed_cost.data import LandedCostData
from utils.landed_cost.common import (
    LandedCostConstants,
    format_usd,
    format_usd_smart,
    format_quantity,
    format_pct_change,
    format_pct,
    format_rate,
    format_date,
    safe_get,
    build_cost_trend_chart,
    build_cost_distribution_chart,
    build_source_breakdown_chart,
    build_yoy_comparison_table,
    build_yoy_breakdown_table,
    build_brand_year_heatmap,
    build_entity_year_heatmap,
    build_cost_composition_chart,
    build_landing_ratio_trend_chart,
    build_landing_by_ship_method_chart,
    build_landing_by_country_chart,
    build_cost_decomposition_bar,
    build_landing_donut_chart,
    build_landing_ratio_heatmap,
    create_excel_download,
)

logger = logging.getLogger(__name__)

# ============================================================
# AUTH & CONFIG
# ============================================================

st.set_page_config(
    page_title="Landed Cost",
    page_icon="💲",
    layout="wide",
    initial_sidebar_state="collapsed",
)

auth = AuthManager()
auth.require_auth()

# ============================================================
# SESSION STATE
# ============================================================

def _init_session_state():
    defaults = {
        "lc_selected_idx": None,
        "lc_show_detail": False,
        "lc_detail_data": None,
        "lc_show_breakdown": True,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

_init_session_state()
data_loader = LandedCostData()


# ============================================================
# HEADER
# ============================================================

def render_header():
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("💲 Landed Cost Lookup")
        st.caption("Weighted average landed cost (USD) per product per entity per year")
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.session_state["lc_selected_idx"] = None
            st.rerun()


# ============================================================
# INLINE FILTERS
# ============================================================

def render_filters():
    """Render inline filters (2 rows). Returns filter dict."""
    options = data_loader.get_filter_options()
    current_year = datetime.now().year

    # Row 1: Entity | Year | Brand | Clear
    col1, col2, col3, col4 = st.columns([2.5, 2, 2.5, 1])

    with col1:
        entity_df = options["entities"]
        selected_entities = st.multiselect(
            "Legal Entity",
            options=entity_df["entity_id"].tolist() if not entity_df.empty else [],
            format_func=lambda x: entity_df[entity_df["entity_id"] == x]["legal_entity"].iloc[0],
            placeholder="All Entities",
            key="lc_entity",
        )

    with col2:
        available_years = options["years"]
        default_years = [y for y in available_years if y >= current_year - 1][:2]
        selected_years = st.multiselect(
            "Cost Year",
            options=available_years,
            default=default_years if default_years else available_years[:2],
            key="lc_year",
        )

    with col3:
        selected_brands = st.multiselect(
            "Brand",
            options=options["brands"],
            placeholder="All Brands",
            key="lc_brand",
        )

    with col4:
        st.write("")
        st.write("")
        if st.button("🔄 Clear", use_container_width=True, key="lc_clear_filters"):
            for k in ["lc_entity", "lc_year", "lc_brand",
                       "lc_vendor_country", "lc_vendor", "lc_product"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.session_state["lc_selected_idx"] = None
            st.rerun()

    # Row 2: Vendor Country | Vendor | Product
    vc_col, v_col, p_col = st.columns([1.5, 2, 4.5])

    with vc_col:
        country_df = options["vendor_countries"]
        selected_countries = st.multiselect(
            "🌐 Vendor Country",
            options=country_df["country_id"].tolist() if not country_df.empty else [],
            format_func=lambda x: country_df[country_df["country_id"] == x]["country_name"].iloc[0],
            placeholder="All Countries",
            key="lc_vendor_country",
        )

    with v_col:
        vendor_df = options["vendors"]
        selected_vendors = st.multiselect(
            "🏢 Vendor",
            options=vendor_df["vendor_id"].tolist() if not vendor_df.empty else [],
            format_func=lambda x: vendor_df[vendor_df["vendor_id"] == x]["label"].iloc[0],
            placeholder="All Vendors",
            key="lc_vendor",
        )

    with p_col:
        product_df = options["products"]
        if not product_df.empty:
            product_label_map = dict(zip(product_df["product_id"], product_df["label"]))
            selected_products = st.multiselect(
                "📦 Product",
                options=product_df["product_id"].tolist(),
                format_func=lambda x: product_label_map.get(x, str(x)),
                placeholder="All Products — search by PT Code or Product Name...",
                key="lc_product",
            )
        else:
            selected_products = []

    # --- Build filter dict ---
    # Pre-filter product_ids when vendor/country is selected
    final_product_ids = tuple(selected_products) if selected_products else None

    if selected_countries or selected_vendors:
        vendor_product_ids = data_loader.get_product_ids_by_vendor(
            vendor_country_ids=tuple(selected_countries) if selected_countries else None,
            vendor_ids=tuple(selected_vendors) if selected_vendors else None,
            entity_ids=tuple(selected_entities) if selected_entities else None,
            year_list=tuple(selected_years) if selected_years else None,
        )
        if vendor_product_ids:
            if final_product_ids:
                # Intersect: user product selection ∩ vendor-matched products
                final_product_ids = tuple(
                    pid for pid in final_product_ids if pid in vendor_product_ids
                )
            else:
                final_product_ids = tuple(vendor_product_ids)
        else:
            # Vendor selected but no products matched → force empty result
            final_product_ids = (-1,)

        st.caption(
            "ℹ️ Vendor/Country filter active — only products with arrival-based "
            "PO linkage from the selected vendor(s) are shown."
        )

    return {
        "entity_ids": tuple(selected_entities) if selected_entities else None,
        "brand_list": tuple(selected_brands) if selected_brands else None,
        "year_list": tuple(selected_years) if selected_years else None,
        "product_ids": final_product_ids,
    }


# ============================================================
# TAB 1: COST LOOKUP
# ============================================================

def render_kpi_cards(df: pd.DataFrame, bd_df: pd.DataFrame):
    """KPI cards — 3 rows: overview, cost insight, landing charges."""
    if df.empty:
        return

    # Row 1 — Overview
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "📦 Products", f"{df['product_id'].nunique():,}",
            help="Number of distinct products in the filtered result.\n\n"
                 "**Formula:** `COUNT(DISTINCT product_id)`",
        )
    with c2:
        st.metric(
            "🏷️ Brands", f"{df['brand'].nunique():,}",
            help="Number of distinct brands in the filtered result.\n\n"
                 "**Formula:** `COUNT(DISTINCT brand)`",
        )
    with c3:
        total_val = df["total_landed_value_usd"].sum()
        st.metric(
            "💰 Total Value", format_usd(total_val),
            help="Total landed cost value (USD) across all products.\n\n"
                 "**Formula:** `SUM(total_landed_value_usd)`",
        )
    with c4:
        txn_count = df["transaction_count"].sum() if "transaction_count" in df.columns else len(df)
        st.metric(
            "📝 Transactions", f"{int(txn_count):,}",
            help="Total number of source transactions (Arrivals + Opening Balances).\n\n"
                 "**Formula:** `SUM(transaction_count)`",
        )

    # Row 2 — Cost Insight
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        total_qty = df["total_quantity"].sum()
        w_avg = total_val / total_qty if total_qty > 0 else 0
        st.metric(
            "📊 Weighted Avg Cost", format_usd_smart(w_avg),
            help="Quantity-weighted average landed cost per unit.\n\n"
                 "**Formula:** `SUM(total_landed_value_usd) / SUM(total_quantity)`",
        )
    with c6:
        if not df.empty:
            top = df.nlargest(1, "average_landed_cost_usd").iloc[0]
            st.metric(
                "📈 Highest Cost",
                format_usd_smart(top["average_landed_cost_usd"]),
                delta=top.get("pt_code", ""),
                delta_color="off",
                help="Product with the highest average landed unit cost.\n\n"
                     "**Formula:** `MAX(average_landed_cost_usd)`",
            )
    with c7:
        if "cost_year" in df.columns and df["cost_year"].nunique() >= 2:
            years = sorted(df["cost_year"].unique(), reverse=True)
            curr_df = df[df["cost_year"] == years[0]]
            prev_df = df[df["cost_year"] == years[1]]
            curr_qty = curr_df["total_quantity"].sum()
            prev_qty = prev_df["total_quantity"].sum()
            curr_avg = curr_df["total_landed_value_usd"].sum() / curr_qty if curr_qty > 0 else 0
            prev_avg = prev_df["total_landed_value_usd"].sum() / prev_qty if prev_qty > 0 else 0
            if prev_avg and prev_avg > 0:
                change = (curr_avg - prev_avg) / prev_avg * 100
                st.metric(
                    "🔄 YoY Avg Change", format_pct_change(change),
                    help=f"Year-over-year change in average landed unit cost "
                         f"between {years[0]} and {years[1]}.\n\n"
                         f"**Formula:** `(avg_{years[0]} - avg_{years[1]}) / avg_{years[1]} × 100`",
                )
            else:
                st.metric("🔄 YoY Avg Change", "-")
        else:
            st.metric("🔄 YoY Avg Change", "-")
    with c8:
        if "cost_year" in df.columns and df["cost_year"].nunique() >= 2:
            years = sorted(df["cost_year"].unique(), reverse=True)
            curr = df[df["cost_year"] == years[0]]
            prev = df[df["cost_year"] == years[1]]
            merged = curr.merge(prev[["product_id", "entity_id", "average_landed_cost_usd"]],
                                on=["product_id", "entity_id"], suffixes=("_c", "_p"), how="inner")
            if not merged.empty:
                merged["pct"] = (
                    (merged["average_landed_cost_usd_c"] - merged["average_landed_cost_usd_p"])
                    / merged["average_landed_cost_usd_p"].replace(0, float("nan")) * 100
                )
                alert_count = (merged["pct"].abs() > LandedCostConstants.SIGNIFICANT_CHANGE_PCT).sum()
                st.metric(
                    "⚠️ Products >10%", f"{alert_count}",
                    help=f"Products with cost change exceeding "
                         f"±{LandedCostConstants.SIGNIFICANT_CHANGE_PCT:.0f}% YoY.",
                )
            else:
                st.metric("⚠️ Products >10%", "0")
        else:
            st.metric("⚠️ Products >10%", "-")

    # Row 3 — Landing Charges Overview (from breakdown data)
    # Always show row 3, with N/A when breakdown data unavailable
    has_breakdown = not bd_df.empty

    c9, c10, c11, c12 = st.columns(4)
    if has_breakdown:
        total_purchase = bd_df["total_purchase_value_usd"].sum()
        total_landing = bd_df["total_landing_charges_usd"].sum()
        avg_ratio = (total_landing / total_purchase * 100) if total_purchase > 0 else 0
    else:
        total_purchase = total_landing = avg_ratio = None

    no_bd_help = ("\n\n⚠️ *No arrival-based breakdown data for current filter. "
                  "This data requires arrivals with PO linkage (excludes Opening Balances).*")

    with c9:
        st.metric(
            "📦 Purchase Cost",
            format_usd(total_purchase) if has_breakdown else "N/A",
            help="Total purchase cost from PO (arrival-based only, excl. OB).\n\n"
                 "**Formula:** `SUM(total_purchase_value_usd)`\n\n"
                 "Source: `landed_cost_breakdown_view`"
                 + ("" if has_breakdown else no_bd_help),
        )
    with c10:
        st.metric(
            "🚢 Landing Charges",
            format_usd(total_landing) if has_breakdown else "N/A",
            help="Total landing charges = Landed Cost − Purchase Cost.\n\n"
                 "Includes: International charges, Local charges, Import tax.\n\n"
                 "**Formula:** `SUM(total_landed_value_usd - total_purchase_value_usd)`"
                 + ("" if has_breakdown else no_bd_help),
        )
    with c11:
        st.metric(
            "📊 Landing Ratio",
            format_pct(avg_ratio) if has_breakdown else "N/A",
            help="Weighted average landing charge ratio.\n\n"
                 "**Formula:** `Total Landing Charges / Total Purchase Cost × 100`\n\n"
                 "Indicates how much extra cost is added on top of purchase price "
                 "for logistics, customs, and taxes."
                 + ("" if has_breakdown else no_bd_help),
        )
    with c12:
        if has_breakdown and "landing_ratio_pct" in bd_df.columns:
            top_ratio = bd_df.dropna(subset=["landing_ratio_pct"])
            if not top_ratio.empty:
                highest = top_ratio.nlargest(1, "landing_ratio_pct").iloc[0]
                st.metric(
                    "🔺 Highest Ratio",
                    format_pct(highest["landing_ratio_pct"]),
                    delta=highest.get("pt_code", ""),
                    delta_color="off",
                    help="Product with the highest landing charge ratio.\n\n"
                         "May indicate inefficient shipping or high customs duty.",
                )
            else:
                st.metric("🔺 Highest Ratio", "-")
        else:
            st.metric("🔺 Highest Ratio", "N/A",
                      help="No breakdown data available for current filter." + no_bd_help)

    if not has_breakdown and not df.empty:
        st.caption(
            "ℹ️ Cost breakdown (Purchase vs Landing) not available for the current filter. "
            "Breakdown requires arrivals with PO linkage — "
            "products with only Opening Balance data will not have breakdown."
        )


@st.fragment
def render_data_table(df: pd.DataFrame, bd_df: pd.DataFrame):
    """Cost lookup table with single-row checkbox selection and optional breakdown."""
    if df.empty:
        st.info("📭 No data found for the selected filters.")
        return

    # Toggle for breakdown columns
    show_bd = st.checkbox(
        "📊 Show Cost Breakdown (Purchase vs Landing)",
        value=st.session_state.get("lc_show_breakdown", False),
        key="lc_show_breakdown_toggle",
    )
    st.session_state["lc_show_breakdown"] = show_bd

    if show_bd and bd_df.empty:
        st.caption("ℹ️ Breakdown columns unavailable — no arrival-based PO data for current filter.")

    st.markdown(f"**{len(df):,} records** | 💡 Tick checkbox to select a row and view details")

    display_df = df.reset_index(drop=True).copy()

    # Merge breakdown data if available and toggle is on
    if show_bd and not bd_df.empty:
        bd_merge = bd_df[["product_id", "entity_id", "cost_year",
                          "avg_purchase_cost_usd", "avg_landing_charge_usd",
                          "landing_ratio_pct",
                          "total_international_charge_usd",
                          "total_local_charge_usd",
                          "total_import_tax_usd"]].copy()
        display_df = display_df.merge(bd_merge, on=["product_id", "entity_id", "cost_year"], how="left")

    # Checkbox column
    display_df["Select"] = False
    if (st.session_state.lc_selected_idx is not None
            and st.session_state.lc_selected_idx < len(display_df)):
        display_df.loc[st.session_state.lc_selected_idx, "Select"] = True

    # Build columns list
    show_cols = [
        "Select", "cost_year", "legal_entity", "pt_code", "product_pn", "brand",
        "standard_uom", "average_landed_cost_usd", "total_quantity",
        "total_landed_value_usd", "min_landed_cost_usd", "max_landed_cost_usd",
        "arrival_quantity", "opening_balance_quantity", "transaction_count",
    ]

    # Add breakdown columns if toggled
    if show_bd:
        bd_extra = [
            "avg_purchase_cost_usd", "avg_landing_charge_usd", "landing_ratio_pct",
            "total_international_charge_usd", "total_local_charge_usd", "total_import_tax_usd",
        ]
        show_cols = show_cols[:8] + bd_extra + show_cols[8:]

    show_cols = [c for c in show_cols if c in display_df.columns]

    col_config = {
        "Select": st.column_config.CheckboxColumn("✓", help="Select to view details",
                                                    default=False, width="small"),
        "cost_year": st.column_config.NumberColumn("Year", format="%d", width="small"),
        "legal_entity": st.column_config.TextColumn("Entity", width="medium"),
        "pt_code": st.column_config.TextColumn("PT Code", width="medium"),
        "product_pn": st.column_config.TextColumn("Product", width="large"),
        "brand": st.column_config.TextColumn("Brand", width="medium"),
        "standard_uom": st.column_config.TextColumn("UOM", width="small"),
        "average_landed_cost_usd": st.column_config.NumberColumn("Avg Landed", format="$%.4f", width="small"),
        "total_quantity": st.column_config.NumberColumn("Total Qty", format="%.2f", width="small"),
        "total_landed_value_usd": st.column_config.NumberColumn("Total Value", format="$%.2f", width="small"),
        "min_landed_cost_usd": st.column_config.NumberColumn("Min", format="$%.4f", width="small"),
        "max_landed_cost_usd": st.column_config.NumberColumn("Max", format="$%.4f", width="small"),
        "arrival_quantity": st.column_config.NumberColumn("Arr Qty", format="%.2f", width="small"),
        "opening_balance_quantity": st.column_config.NumberColumn("OB Qty", format="%.2f", width="small"),
        "transaction_count": st.column_config.NumberColumn("Txn", format="%d", width="small"),
        # Breakdown columns
        "avg_purchase_cost_usd": st.column_config.NumberColumn("PO Cost", format="$%.4f", width="small"),
        "avg_landing_charge_usd": st.column_config.NumberColumn("Landing/Unit", format="$%.4f", width="small"),
        "landing_ratio_pct": st.column_config.NumberColumn("Ratio %", format="%.1f%%", width="small"),
        "total_international_charge_usd": st.column_config.NumberColumn("Intl $", format="$%.2f", width="small"),
        "total_local_charge_usd": st.column_config.NumberColumn("Local $", format="$%.2f", width="small"),
        "total_import_tax_usd": st.column_config.NumberColumn("Tax $", format="$%.2f", width="small"),
    }

    disabled_cols = [c for c in show_cols if c != "Select"]

    edited_df = st.data_editor(
        display_df[show_cols],
        column_config=col_config,
        disabled=disabled_cols,
        width="stretch",
        hide_index=True,
        height=min(len(display_df) * 35 + 40, 550),
        key="lc_table_editor",
    )

    # Handle single selection
    selected_indices = edited_df[edited_df["Select"] == True].index.tolist()

    if selected_indices:
        if len(selected_indices) > 1:
            new_sel = [i for i in selected_indices if i != st.session_state.lc_selected_idx]
            if new_sel:
                st.session_state.lc_selected_idx = new_sel[0]
                st.rerun()
        else:
            st.session_state.lc_selected_idx = selected_indices[0]
    else:
        st.session_state.lc_selected_idx = None

    # Action buttons
    if (st.session_state.lc_selected_idx is not None
            and st.session_state.lc_selected_idx < len(df)):
        sel = df.iloc[st.session_state.lc_selected_idx]

        st.markdown("---")
        st.markdown(
            f"**Selected:** `{sel.get('pt_code', '')}` | {sel.get('product_pn', '')} | "
            f"{sel.get('legal_entity', '')} | {int(sel.get('cost_year', 0))} | "
            f"Avg: {format_usd_smart(sel.get('average_landed_cost_usd'))}"
        )

        bc1, bc2, bc3, bc4 = st.columns(4)
        with bc1:
            if st.button("🔍 View Details", type="primary", use_container_width=True,
                         key="btn_view_detail"):
                st.session_state["lc_detail_data"] = sel.to_dict()
                st.session_state["lc_show_detail"] = True
                st.rerun(scope="app")
        with bc2:
            if st.button("❌ Deselect", use_container_width=True, key="btn_deselect"):
                st.session_state["lc_selected_idx"] = None
                st.rerun()
    else:
        st.info("💡 Tick checkbox to select a row and perform actions")


@st.fragment
def render_export(df: pd.DataFrame):
    """Export to Excel."""
    if df.empty:
        return

    col1, col2 = st.columns([1, 4])
    with col1:
        try:
            export_df = data_loader.get_export_data(
                entity_ids=st.session_state.get("lc_entity") or None,
                brand_list=st.session_state.get("lc_brand") or None,
                year_list=st.session_state.get("lc_year") or None,
                product_ids=tuple(st.session_state.get("lc_product", [])) or None,
            )
            if not export_df.empty:
                excel_data = create_excel_download(export_df)
                st.download_button(
                    "📥 Export Excel",
                    data=excel_data,
                    file_name=f"landed_cost_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="lc_export",
                )
        except Exception as e:
            st.error(f"Export failed: {e}")


# ============================================================
# DETAIL DIALOG
# ============================================================

@st.dialog("📋 Cost Detail", width="large")
def show_detail_dialog(row_data: dict):
    """Detail popup: summary → decomposition → cost history → source records."""
    pt_code = safe_get(row_data, "pt_code", "")
    product_name = safe_get(row_data, "product_pn", "")
    brand = safe_get(row_data, "brand", "")
    entity = safe_get(row_data, "legal_entity", "")
    entity_id = safe_get(row_data, "entity_id")
    product_id = safe_get(row_data, "product_id")
    cost_year = safe_get(row_data, "cost_year")
    uom = safe_get(row_data, "standard_uom", "")

    # --- Header ---
    st.markdown(f"### {pt_code} - {product_name}")
    st.markdown(f"Brand: **{brand}** | Entity: **{entity}** | "
                f"Year: **{int(cost_year) if cost_year else '-'}** | UOM: {uom}")
    st.markdown("---")

    # --- Cost Summary ---
    st.markdown("#### 📊 Cost Summary")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        st.metric("Avg Cost", format_usd_smart(safe_get(row_data, "average_landed_cost_usd")))
        st.metric("Min Cost", format_usd_smart(safe_get(row_data, "min_landed_cost_usd")))
    with sc2:
        st.metric("Max Cost", format_usd_smart(safe_get(row_data, "max_landed_cost_usd")))
        st.metric("Total Value", format_usd(safe_get(row_data, "total_landed_value_usd")))
    with sc3:
        st.metric("Total Qty", format_quantity(safe_get(row_data, "total_quantity")))
        arr = safe_get(row_data, "arrival_quantity", 0) or 0
        ob = safe_get(row_data, "opening_balance_quantity", 0) or 0
        st.metric("Arrivals / OB", f"{format_quantity(arr)} / {format_quantity(ob)}")

    st.markdown("---")

    # --- Cost Decomposition (from breakdown view) ---
    if product_id and entity_id and cost_year:
        breakdown = data_loader.get_product_breakdown(
            product_id=int(product_id),
            entity_id=int(entity_id),
            cost_year=int(cost_year),
        )

        if breakdown:
            st.markdown("#### 💰 Cost Decomposition")

            # Stacked bar
            decomp_bar = build_cost_decomposition_bar(breakdown)
            if decomp_bar:
                st.plotly_chart(decomp_bar, width="stretch")

            # Metrics
            dm1, dm2, dm3 = st.columns(3)
            with dm1:
                st.metric("Purchase Cost/Unit",
                          format_usd_smart(breakdown.get("avg_purchase_cost_usd")),
                          help="Average PO purchase price per unit (USD)")
            with dm2:
                st.metric("Landing Charges/Unit",
                          format_usd_smart(breakdown.get("avg_landing_charge_usd")),
                          help="Average landing charge per unit (USD)\n\n"
                               "= Avg Landed Cost − Avg Purchase Cost")
            with dm3:
                st.metric("Landing Ratio",
                          format_pct(breakdown.get("landing_ratio_pct")),
                          help="Landing Charges / Purchase Cost × 100%\n\n"
                               "Indicates the % cost added by logistics, customs, and taxes.")

            # Charge breakdown detail + donut
            intl = breakdown.get("total_international_charge_usd") or 0
            local = breakdown.get("total_local_charge_usd") or 0
            tax = breakdown.get("total_import_tax_usd") or 0
            total_charges = intl + local + tax

            if total_charges > 0:
                dl, dr = st.columns([1, 1])
                with dl:
                    st.markdown("**Landing Charges Breakdown:**")
                    st.markdown(
                        f"- 🌐 International: {format_usd(intl)} "
                        f"({intl / total_charges * 100:.1f}%)"
                    )
                    st.markdown(
                        f"- 🏠 Local: {format_usd(local)} "
                        f"({local / total_charges * 100:.1f}%)"
                    )
                    st.markdown(
                        f"- 📋 Import Tax: {format_usd(tax)} "
                        f"({tax / total_charges * 100:.1f}%)"
                    )
                with dr:
                    donut = build_landing_donut_chart(breakdown)
                    if donut:
                        st.plotly_chart(donut, width="stretch")

            st.markdown("---")
        else:
            st.markdown("#### 💰 Cost Decomposition")
            st.caption(
                "ℹ️ No cost decomposition available — "
                "this product/entity/year has no arrivals with PO linkage in the breakdown view."
            )
            st.markdown("---")
    if product_id and entity_id:
        st.markdown("#### 📈 Cost History")
        with st.spinner("Loading history..."):
            history = data_loader.get_product_cost_history(
                product_id=int(product_id), entity_id=int(entity_id)
            )
            bd_history = data_loader.get_product_breakdown_history(
                product_id=int(product_id), entity_id=int(entity_id)
            )

        if not history.empty:
            # Merge breakdown into history
            if not bd_history.empty:
                history = history.merge(
                    bd_history[["cost_year", "avg_purchase_cost_usd",
                                "avg_landing_charge_usd", "landing_ratio_pct"]],
                    on="cost_year", how="left",
                )

            hist_cols = [c for c in [
                "cost_year", "average_landed_cost_usd",
                "avg_purchase_cost_usd", "avg_landing_charge_usd", "landing_ratio_pct",
                "total_quantity", "total_landed_value_usd",
                "arrival_quantity", "opening_balance_quantity",
            ] if c in history.columns]

            st.dataframe(
                history[hist_cols],
                column_config={
                    "cost_year": st.column_config.NumberColumn("Year", format="%d"),
                    "average_landed_cost_usd": st.column_config.NumberColumn("Avg Landed", format="$%.4f"),
                    "avg_purchase_cost_usd": st.column_config.NumberColumn("PO Cost", format="$%.4f"),
                    "avg_landing_charge_usd": st.column_config.NumberColumn("Landing/Unit", format="$%.4f"),
                    "landing_ratio_pct": st.column_config.NumberColumn("Ratio %", format="%.1f%%"),
                    "total_quantity": st.column_config.NumberColumn("Qty", format="%.2f"),
                    "total_landed_value_usd": st.column_config.NumberColumn("Value", format="$%.2f"),
                    "arrival_quantity": st.column_config.NumberColumn("Arr Qty", format="%.2f"),
                    "opening_balance_quantity": st.column_config.NumberColumn("OB Qty", format="%.2f"),
                },
                width="stretch",
                hide_index=True,
                height=min(len(history) * 35 + 38, 250),
            )

            if len(history) > 1:
                fig = build_cost_trend_chart(history)
                if fig:
                    fig.update_layout(title=f"Cost Trend: {pt_code}", height=280)
                    st.plotly_chart(fig, width="stretch")
        else:
            st.info("No history data found.")

        st.markdown("---")

        # --- Source Records ---
        st.markdown("#### 📦 Source Records")
        _render_source_tabs(int(product_id), int(entity_id), int(cost_year))

    # --- Close ---
    st.markdown("---")
    cc1, cc2, cc3 = st.columns([1, 1, 1])
    with cc2:
        if st.button("✖️ Close", use_container_width=True, key="btn_close_dialog"):
            st.session_state["lc_show_detail"] = False
            st.session_state["lc_detail_data"] = None
            st.rerun()


def _render_source_tabs(product_id: int, entity_id: int, cost_year: int):
    """Tabs for Arrivals and Opening Balances within the dialog."""

    with st.spinner("Loading source records..."):
        arr_df = data_loader.get_arrival_sources(product_id, entity_id, cost_year)
        ob_df = data_loader.get_ob_sources(product_id, entity_id, cost_year)

    arr_count = len(arr_df) if not arr_df.empty else 0
    ob_count = len(ob_df) if not ob_df.empty else 0

    tab_arr, tab_ob = st.tabs([
        f"📦 Arrivals ({arr_count})",
        f"📋 Opening Balance ({ob_count})",
    ])

    # --- Arrivals Tab ---
    with tab_arr:
        if arr_df.empty:
            st.info("No arrival records found for this product/entity/year.")
        else:
            arr_show = [c for c in [
                "arrival_note_number", "arrival_date", "po_number",
                "vendor_name", "arrival_quantity",
                "po_unit_cost_usd", "landed_cost_usd",
                "landing_charge_per_unit_usd",
                "total_value_usd", "warehouse_name", "ship_method",
            ] if c in arr_df.columns]

            st.dataframe(
                arr_df[arr_show] if arr_show else arr_df,
                column_config={
                    "arrival_note_number": st.column_config.TextColumn("CAN#", width="medium"),
                    "arrival_date": st.column_config.TextColumn("Date", width="medium"),
                    "po_number": st.column_config.TextColumn("PO#", width="medium"),
                    "vendor_name": st.column_config.TextColumn("Vendor", width="medium"),
                    "arrival_quantity": st.column_config.NumberColumn("Qty", format="%.2f", width="small"),
                    "po_unit_cost_usd": st.column_config.NumberColumn("PO $/Unit", format="$%.4f", width="small"),
                    "landed_cost_usd": st.column_config.NumberColumn("Landed $/Unit", format="$%.4f", width="small"),
                    "landing_charge_per_unit_usd": st.column_config.NumberColumn(
                        "Landing/Unit", format="$%.4f", width="small"),
                    "total_value_usd": st.column_config.NumberColumn("Total USD", format="$%.2f", width="small"),
                    "warehouse_name": st.column_config.TextColumn("Warehouse", width="medium"),
                    "ship_method": st.column_config.TextColumn("Ship", width="small"),
                },
                width="stretch",
                hide_index=True,
                height=min(arr_count * 35 + 38, 300),
            )

            _render_arrival_detail_selector(arr_df)

    # --- OB Tab ---
    with tab_ob:
        if ob_df.empty:
            st.info("No opening balance records found for this product/entity/year.")
        else:
            ob_show = [c for c in [
                "created_date", "batch_no", "expiry_date",
                "quantity", "unit_cost_usd", "total_value_usd",
                "currency", "exchange_rate_used", "rate_source",
                "warehouse_name", "is_approved",
            ] if c in ob_df.columns]

            display_ob = ob_df[ob_show].copy() if ob_show else ob_df.copy()
            if "is_approved" in display_ob.columns:
                display_ob["is_approved"] = display_ob["is_approved"].apply(
                    lambda x: "✅" if x else "⏳"
                )

            st.dataframe(
                display_ob,
                column_config={
                    "created_date": st.column_config.TextColumn("Date", width="medium"),
                    "batch_no": st.column_config.TextColumn("Batch", width="medium"),
                    "expiry_date": st.column_config.TextColumn("Expiry", width="medium"),
                    "quantity": st.column_config.NumberColumn("Qty", format="%.2f", width="small"),
                    "unit_cost_usd": st.column_config.NumberColumn("Unit USD", format="$%.4f", width="small"),
                    "total_value_usd": st.column_config.NumberColumn("Total USD", format="$%.2f", width="small"),
                    "currency": st.column_config.TextColumn("Cur", width="small"),
                    "exchange_rate_used": st.column_config.NumberColumn("Rate", format="%.4f", width="small"),
                    "rate_source": st.column_config.TextColumn("Rate Type", width="medium"),
                    "warehouse_name": st.column_config.TextColumn("Warehouse", width="medium"),
                    "is_approved": st.column_config.TextColumn("Approved", width="small"),
                },
                width="stretch",
                hide_index=True,
                height=min(ob_count * 35 + 38, 300),
            )


@st.fragment
def _render_arrival_detail_selector(arr_df: pd.DataFrame):
    """Selectbox + expander to drill into a single arrival record."""
    st.markdown("---")
    st.caption("Select an arrival record to view full PO traceability")

    labels = ["-- Select an arrival --"]
    for _, row in arr_df.iterrows():
        can = row.get("arrival_note_number", "-")
        dt = row.get("arrival_date", "")
        po = row.get("po_number", "-")
        vendor = row.get("vendor_name", "-")
        labels.append(f"{can} | {dt} | PO: {po} | {vendor}")

    sel_idx = st.selectbox(
        "Arrival",
        options=range(len(labels)),
        format_func=lambda i: labels[i],
        key="lc_arrival_select",
        label_visibility="collapsed",
    )

    if sel_idx and sel_idx > 0:
        detail_id = int(arr_df.iloc[sel_idx - 1]["arrival_detail_id"])

        with st.spinner("Loading arrival detail..."):
            detail = data_loader.get_arrival_detail(detail_id)

        if detail:
            with st.expander(
                f"📄 Arrival Detail — {detail.get('arrival_note_number', '')}",
                expanded=True,
            ):
                dc1, dc2, dc3 = st.columns(3)

                with dc1:
                    st.markdown("**📋 Purchase Order**")
                    st.markdown(f"PO Number: `{detail.get('po_number', '-')}`")
                    st.markdown(f"PO Date: {format_date(detail.get('po_date'))}")
                    st.markdown(f"PO Type: {detail.get('po_type', '-')}")
                    if detail.get("external_ref_number"):
                        st.markdown(f"Ext Ref: `{detail['external_ref_number']}`")
                    st.markdown(f"PO Currency: {detail.get('po_currency', '-')}")
                    st.markdown(f"Trade Term: {detail.get('trade_term', '-')}")
                    st.markdown(f"Payment Term: {detail.get('payment_term', '-')}")

                with dc2:
                    st.markdown("**📦 Arrival**")
                    st.markdown(f"CAN#: `{detail.get('arrival_note_number', '-')}`")
                    st.markdown(f"Date: {format_date(detail.get('arrival_date'))}")
                    st.markdown(f"Status: {detail.get('arrival_status', '-')}")
                    st.markdown(f"Ship Method: {detail.get('ship_method', '-')}")
                    st.markdown(f"Warehouse: {detail.get('warehouse_name', '-')}")
                    st.markdown(f"Entity: {detail.get('receiver_entity', '-')}")
                    if detail.get("ttl_weight"):
                        st.markdown(f"Weight: {detail['ttl_weight']}")

                with dc3:
                    st.markdown("**💰 Cost & Vendor**")
                    st.markdown(f"Vendor: {detail.get('vendor_name', '-')}")
                    if detail.get("vendor_country"):
                        st.markdown(f"Country: {detail['vendor_country']}")
                    lc_val = detail.get("landed_cost_local")
                    lc_cur = detail.get("landed_cost_currency", "")
                    st.markdown(f"Landed Cost: {format_rate(lc_val)} {lc_cur}")
                    st.markdown(f"USD Rate: {format_rate(detail.get('usd_landed_cost_currency_exchange_rate'))}")
                    st.markdown(f"Unit USD: {format_usd_smart(detail.get('unit_cost_usd'))}")
                    st.markdown(f"Arr Qty: {format_quantity(detail.get('arrival_quantity'))}")
                    st.markdown(f"Stocked In: {format_quantity(detail.get('stocked_in_qty'))}")

                # PO Line detail
                if detail.get("po_quantity") or detail.get("po_unit_cost"):
                    st.markdown("---")
                    st.markdown("**📝 PO Line Detail**")
                    pc1, pc2, pc3 = st.columns(3)
                    with pc1:
                        st.markdown(f"PO Qty: {format_quantity(detail.get('po_quantity'))}")
                        st.markdown(f"PO Unit Cost: {format_rate(detail.get('po_unit_cost'))}")
                    with pc2:
                        st.markdown(f"Buying Qty: {format_quantity(detail.get('po_buying_quantity'))}")
                        st.markdown(f"Buying Cost: {format_rate(detail.get('po_buying_unit_cost'))}")
                        st.markdown(f"Buying UOM: {detail.get('buying_uom', '-')}")
                    with pc3:
                        st.markdown(f"Conversion: {detail.get('uom_conversion', '-')}")
                        st.markdown(f"ETD: {format_date(detail.get('etd'))}")
                        st.markdown(f"ETA: {format_date(detail.get('eta'))}")
                        if detail.get("vat_gst"):
                            st.markdown(f"VAT/GST: {detail['vat_gst']}%")
        else:
            st.warning("Could not load detail for this arrival record.")


# ============================================================
# TAB 2: YoY COMPARISON
# ============================================================

def render_tab_yoy(filters: dict):
    """Year-over-year cost comparison with purchase/landing decomposition."""
    with st.spinner("Loading YoY data..."):
        yoy_df = data_loader.get_yoy_comparison(
            entity_ids=filters["entity_ids"],
            brand_list=filters["brand_list"],
            product_ids=filters["product_ids"],
        )
        yoy_bd = data_loader.get_yoy_breakdown(
            entity_ids=filters["entity_ids"],
            brand_list=filters["brand_list"],
            product_ids=filters["product_ids"],
        )

    if yoy_df.empty:
        st.info("No data available for YoY comparison.")
        return

    comparison = build_yoy_comparison_table(yoy_df)
    if comparison.empty:
        st.info("Need at least 2 years of data for comparison.")
        return

    years = sorted(yoy_df["cost_year"].unique(), reverse=True)
    current_year, prev_year = years[0], years[1]

    # Build enriched comparison if breakdown data available
    if not yoy_bd.empty:
        comparison_full = build_yoy_breakdown_table(yoy_df, yoy_bd)
    else:
        comparison_full = comparison

    # --- Row 1: Landed Cost Summary ---
    has_change = comparison["yoy_change_pct"].dropna()
    if not has_change.empty:
        UNCHANGED_THRESHOLD = 0.5  # <0.5% considered unchanged
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric(
                "🔺 Cost Increased",
                f"{(has_change > UNCHANGED_THRESHOLD).sum()} products",
            )
        with c2:
            st.metric(
                "🔻 Cost Decreased",
                f"{(has_change < -UNCHANGED_THRESHOLD).sum()} products",
            )
        with c3:
            st.metric(
                "➡️ Unchanged",
                f"{(has_change.abs() <= UNCHANGED_THRESHOLD).sum()} products",
            )
        with c4:
            # Weighted avg change: consistent with Tab 1
            val_c = comparison[f"value_{current_year}"].sum()
            qty_c = comparison[f"qty_{current_year}"].sum()
            val_p = comparison[f"value_{prev_year}"].sum()
            qty_p = comparison[f"qty_{prev_year}"].sum()
            wavg_c = val_c / qty_c if qty_c > 0 else 0
            wavg_p = val_p / qty_p if qty_p > 0 else 0
            wavg_chg = (wavg_c - wavg_p) / wavg_p * 100 if wavg_p > 0 else 0
            st.metric(
                "Avg Change", format_pct_change(wavg_chg),
                help=f"Weighted avg cost change ({prev_year}→{current_year}).\n\n"
                     f"Compared {len(has_change)} products in both years.",
            )

    # --- Row 2: Landing Charges YoY Summary ---
    if not yoy_bd.empty and f"landing_{current_year}" in comparison_full.columns:
        st.markdown("")
        d1, d2, d3, d4 = st.columns(4)

        with d1:
            p_cc = f"purchase_{current_year}"
            p_pp = f"purchase_{prev_year}"
            if p_cc in comparison_full.columns and p_pp in comparison_full.columns:
                bd_v = comparison_full.dropna(subset=[p_cc, p_pp])
                if not bd_v.empty:
                    wpc = (bd_v[p_cc] * bd_v[f"qty_{current_year}"]).sum()
                    wpp = (bd_v[p_pp] * bd_v[f"qty_{prev_year}"]).sum()
                    qc = bd_v[f"qty_{current_year}"].sum()
                    qp = bd_v[f"qty_{prev_year}"].sum()
                    apc = wpc / qc if qc > 0 else 0
                    app = wpp / qp if qp > 0 else 0
                    p_yoy = (apc - app) / app * 100 if app > 0 else 0
                    st.metric("📦 Avg Purchase Change", format_pct_change(p_yoy),
                              help="Weighted avg YoY change in purchase cost (PO price)")

        with d2:
            l_cc = f"landing_{current_year}"
            l_pp = f"landing_{prev_year}"
            if l_cc in comparison_full.columns and l_pp in comparison_full.columns:
                bd_v = comparison_full.dropna(subset=[l_cc, l_pp])
                if not bd_v.empty:
                    wlc = (bd_v[l_cc] * bd_v[f"qty_{current_year}"]).sum()
                    wlp = (bd_v[l_pp] * bd_v[f"qty_{prev_year}"]).sum()
                    qc = bd_v[f"qty_{current_year}"].sum()
                    qp = bd_v[f"qty_{prev_year}"].sum()
                    alc = wlc / qc if qc > 0 else 0
                    alp = wlp / qp if qp > 0 else 0
                    l_yoy = (alc - alp) / alp * 100 if alp > 0 else 0
                    st.metric("🚢 Avg Landing Change", format_pct_change(l_yoy),
                              help="Weighted avg YoY change in landing charges")

        with d3:
            pc_col = f"purchase_{current_year}"
            lc_col = f"landing_{current_year}"
            pp_col = f"purchase_{prev_year}"
            lp_col = f"landing_{prev_year}"
            has_cols = all(c in comparison_full.columns for c in [pc_col, lc_col, pp_col, lp_col])
            if has_cols:
                bv = comparison_full.dropna(subset=[pc_col, lc_col])
                tp_c = (bv[pc_col] * bv[f"qty_{current_year}"]).sum()
                tl_c = (bv[lc_col] * bv[f"qty_{current_year}"]).sum()
                avg_ratio_curr = tl_c / tp_c * 100 if tp_c > 0 else 0
                bv2 = comparison_full.dropna(subset=[pp_col, lp_col])
                tp_p = (bv2[pp_col] * bv2[f"qty_{prev_year}"]).sum()
                tl_p = (bv2[lp_col] * bv2[f"qty_{prev_year}"]).sum()
                avg_ratio_prev = tl_p / tp_p * 100 if tp_p > 0 else 0
                st.metric("📊 Landing Ratio Shift",
                          f"{avg_ratio_curr:.1f}% ← {avg_ratio_prev:.1f}%",
                          help=f"Average landing ratio: {prev_year} → {current_year}")

        with d4:
            if "ratio_shift" in comparison_full.columns:
                alert_threshold = LandedCostConstants.LANDING_RATIO_ALERT_SHIFT
                ratio_alerts = (comparison_full["ratio_shift"].abs() > alert_threshold).sum()
                st.metric(f"⚠️ Ratio Shift >{alert_threshold:.0f}pp", f"{ratio_alerts}",
                          help=f"Products where landing ratio shifted more than "
                               f"±{alert_threshold:.0f} percentage points.")
    else:
        st.caption(
            "ℹ️ Purchase vs Landing decomposition unavailable — "
            "no arrival-based PO data for the selected filter/years."
        )

    st.markdown("---")

    # --- Significant Changes with Root-Cause Classification ---
    threshold = LandedCostConstants.SIGNIFICANT_CHANGE_PCT
    significant = comparison_full[comparison_full["yoy_change_pct"].abs() > threshold].copy()

    if not significant.empty:
        st.markdown(f"**⚠️ Significant changes (>{threshold:.0f}%) — {prev_year} → {current_year}:**")

        # Classify root cause if breakdown data is available
        has_decomp = (f"purchase_{current_year}" in significant.columns
                      and "purchase_yoy_pct" in significant.columns)

        if has_decomp:
            def _classify_cause(row):
                p_yoy = row.get("purchase_yoy_pct")
                l_yoy = row.get("landing_yoy_pct")
                if pd.isna(p_yoy) or pd.isna(l_yoy):
                    return "❓ Insufficient Data"
                total_change = abs(p_yoy) + abs(l_yoy)
                if total_change == 0:
                    return "➡️ No Change"
                p_share = abs(p_yoy) / total_change
                if p_share >= 0.7:
                    return "📦 Purchase Price Driven"
                elif p_share <= 0.3:
                    return "🚢 Logistics Cost Driven"
                else:
                    return "↔️ Mixed Impact"

            significant["change_driver"] = significant.apply(_classify_cause, axis=1)

            # Show by category
            for driver in ["📦 Purchase Price Driven", "🚢 Logistics Cost Driven",
                           "↔️ Mixed Impact", "❓ Insufficient Data"]:
                group = significant[significant["change_driver"] == driver]
                if group.empty:
                    continue
                with st.expander(f"{driver} ({len(group)} products)", expanded=(driver != "❓ Insufficient Data")):
                    display_cols = [c for c in [
                        "pt_code", "product_pn", "brand", "legal_entity",
                        f"cost_{current_year}", f"cost_{prev_year}",
                        "yoy_change_pct",
                        f"purchase_{current_year}", f"purchase_{prev_year}", "purchase_yoy_pct",
                        f"landing_{current_year}", f"landing_{prev_year}", "landing_yoy_pct",
                        f"ratio_{current_year}", "ratio_shift",
                    ] if c in group.columns]

                    st.dataframe(
                        group[display_cols],
                        column_config={
                            f"cost_{current_year}": st.column_config.NumberColumn(
                                f"Landed {current_year}", format="$%.4f"),
                            f"cost_{prev_year}": st.column_config.NumberColumn(
                                f"Landed {prev_year}", format="$%.4f"),
                            "yoy_change_pct": st.column_config.NumberColumn("Landed YoY%", format="%.1f%%"),
                            f"purchase_{current_year}": st.column_config.NumberColumn(
                                f"PO {current_year}", format="$%.4f"),
                            f"purchase_{prev_year}": st.column_config.NumberColumn(
                                f"PO {prev_year}", format="$%.4f"),
                            "purchase_yoy_pct": st.column_config.NumberColumn("PO YoY%", format="%.1f%%"),
                            f"landing_{current_year}": st.column_config.NumberColumn(
                                f"Landing {current_year}", format="$%.4f"),
                            f"landing_{prev_year}": st.column_config.NumberColumn(
                                f"Landing {prev_year}", format="$%.4f"),
                            "landing_yoy_pct": st.column_config.NumberColumn("Landing YoY%", format="%.1f%%"),
                            f"ratio_{current_year}": st.column_config.NumberColumn(
                                f"Ratio {current_year}", format="%.1f%%"),
                            "ratio_shift": st.column_config.NumberColumn("Ratio Δ pp", format="%.1f"),
                        },
                        width="stretch",
                        hide_index=True,
                    )
        else:
            # Fallback: show without decomposition
            st.dataframe(
                significant,
                column_config={
                    f"cost_{current_year}": st.column_config.NumberColumn(
                        f"Cost {current_year}", format="$%.4f"),
                    f"cost_{prev_year}": st.column_config.NumberColumn(
                        f"Cost {prev_year}", format="$%.4f"),
                    "yoy_change_pct": st.column_config.NumberColumn("YoY %", format="%.1f%%"),
                    "yoy_change_usd": st.column_config.NumberColumn("YoY Δ", format="$%.4f"),
                },
                width="stretch",
                hide_index=True,
            )
    else:
        st.success(f"No significant cost changes (>{threshold:.0f}%) detected.")

    # Full table
    with st.expander(f"📋 Full Comparison ({len(comparison_full)} products)", expanded=False):
        st.dataframe(comparison_full, width="stretch", hide_index=True)


# ============================================================
# TAB 3: ANALYTICS
# ============================================================

def render_tab_analytics(df: pd.DataFrame, bd_df: pd.DataFrame, filters: dict):
    """Charts and visual analysis including landing charges analysis."""
    if df.empty:
        st.info("No data for analytics. Adjust filters.")
        return

    # --- Row 1: Cost Trend ---
    st.markdown("##### 📈 Cost Trend")
    trend_chart = build_cost_trend_chart(df)
    if trend_chart:
        st.plotly_chart(trend_chart, width="stretch")

    st.markdown("---")

    # --- Row 2: Cost Composition + Landing Ratio Trend ---
    if not bd_df.empty:
        col_comp, col_ratio = st.columns(2)

        with col_comp:
            st.markdown("##### 📊 Cost Composition by Year")
            comp_chart = build_cost_composition_chart(bd_df)
            if comp_chart:
                st.plotly_chart(comp_chart, width="stretch")
            else:
                st.info("Not enough data for composition chart.")

        with col_ratio:
            st.markdown("##### 📉 Landing Ratio Trend")
            ratio_chart = build_landing_ratio_trend_chart(bd_df)
            if ratio_chart:
                st.plotly_chart(ratio_chart, width="stretch")
            else:
                st.info("Need at least 2 years for ratio trend.")

        st.markdown("---")
    else:
        st.caption(
            "ℹ️ Cost Composition & Landing Ratio charts unavailable — "
            "no arrival-based PO data for current filter."
        )
        st.markdown("---")

    # --- Row 3: Distribution + Source Breakdown ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("##### 📊 Cost Distribution by Brand")
        year_for_dist = filters["year_list"][0] if filters["year_list"] else None
        dist_chart = build_cost_distribution_chart(df, year=year_for_dist)
        if dist_chart:
            st.plotly_chart(dist_chart, width="stretch")
        else:
            st.info("Not enough data for distribution chart.")

    with col_right:
        st.markdown("##### 📦 Source Breakdown (Arrival vs OB)")
        source_chart = build_source_breakdown_chart(df)
        if source_chart:
            st.plotly_chart(source_chart, width="stretch")
        else:
            st.info("Not enough data for source chart.")

    st.markdown("---")

    # --- Row 4: Landing by Ship Method + Vendor Country ---
    if not bd_df.empty:
        st.markdown("##### 🚢 Landing Charges Analysis")

        with st.spinner("Loading landing charges breakdown..."):
            sm_df = data_loader.get_landing_by_ship_method(**filters)
            country_df = data_loader.get_landing_by_country(**filters)

        col_sm, col_vc = st.columns(2)

        with col_sm:
            st.markdown("**By Ship Method**")
            if not sm_df.empty:
                sm_chart = build_landing_by_ship_method_chart(sm_df)
                if sm_chart:
                    st.plotly_chart(sm_chart, width="stretch")
                else:
                    st.info("Not enough data.")
            else:
                st.info("No ship method data available.")

        with col_vc:
            st.markdown("**By Vendor Country (Landing Ratio)**")
            if not country_df.empty:
                vc_chart = build_landing_by_country_chart(country_df)
                if vc_chart:
                    st.plotly_chart(vc_chart, width="stretch")
                else:
                    st.info("Not enough data.")
            else:
                st.info("No vendor country data available.")

        st.markdown("---")

    # --- Row 5: Heatmaps ---
    st.markdown("##### 🔥 Brand × Year Heatmap (Weighted Avg Cost)")
    heatmap1 = build_brand_year_heatmap(df)
    if heatmap1:
        st.plotly_chart(heatmap1, width="stretch")
    else:
        st.info("Need at least 2 brands and 2 years for heatmap.")

    st.markdown("---")

    st.markdown("##### 🔥 Entity × Year Heatmap (Total Value)")
    heatmap2 = build_entity_year_heatmap(df)
    if heatmap2:
        st.plotly_chart(heatmap2, width="stretch")
    else:
        st.info("Need at least 2 entities and 2 years for heatmap.")

    st.markdown("---")

    # --- Row 6: Landing Ratio Heatmaps (NEW) ---
    if not bd_df.empty:
        st.markdown("##### 🔥 Brand × Year Landing Ratio (%)")
        lr_heatmap1 = build_landing_ratio_heatmap(bd_df, index_col="brand", title_label="Brand")
        if lr_heatmap1:
            st.plotly_chart(lr_heatmap1, width="stretch")
        else:
            st.info("Need at least 2 brands and 2 years for landing ratio heatmap.")

        st.markdown("---")

        st.markdown("##### 🔥 Entity × Year Landing Ratio (%)")
        lr_heatmap2 = build_landing_ratio_heatmap(bd_df, index_col="legal_entity", title_label="Entity")
        if lr_heatmap2:
            st.plotly_chart(lr_heatmap2, width="stretch")
        else:
            st.info("Need at least 2 entities and 2 years for landing ratio heatmap.")

        st.markdown("---")

    # --- Top Products ---
    st.markdown("##### 💰 Top 20 Highest Cost Products")
    latest_year = df["cost_year"].max()
    top_df = (
        df[df["cost_year"] == latest_year]
        .nlargest(LandedCostConstants.TOP_PRODUCTS_N, "average_landed_cost_usd")[
            ["pt_code", "product_pn", "brand", "legal_entity",
             "average_landed_cost_usd", "total_quantity", "total_landed_value_usd"]
        ]
    )
    if not top_df.empty:
        st.dataframe(
            top_df,
            column_config={
                "average_landed_cost_usd": st.column_config.NumberColumn("Avg Cost", format="$%.4f"),
                "total_landed_value_usd": st.column_config.NumberColumn("Value", format="$%.2f"),
                "total_quantity": st.column_config.NumberColumn("Qty", format="%.2f"),
            },
            width="stretch",
            hide_index=True,
        )

    # --- Top Landing Ratio Products (NEW) ---
    if not bd_df.empty:
        st.markdown("---")
        st.markdown("##### 🚢 Top 20 Highest Landing Ratio Products")
        latest_bd = bd_df[bd_df["cost_year"] == bd_df["cost_year"].max()]
        top_ratio_df = (
            latest_bd
            .dropna(subset=["landing_ratio_pct"])
            .nlargest(LandedCostConstants.TOP_PRODUCTS_N, "landing_ratio_pct")[
                ["pt_code", "product_pn", "brand", "legal_entity",
                 "avg_purchase_cost_usd", "avg_landed_cost_usd",
                 "avg_landing_charge_usd", "landing_ratio_pct",
                 "total_quantity"]
            ]
        )
        if not top_ratio_df.empty:
            st.dataframe(
                top_ratio_df,
                column_config={
                    "avg_purchase_cost_usd": st.column_config.NumberColumn("PO Cost", format="$%.4f"),
                    "avg_landed_cost_usd": st.column_config.NumberColumn("Landed Cost", format="$%.4f"),
                    "avg_landing_charge_usd": st.column_config.NumberColumn("Landing/Unit", format="$%.4f"),
                    "landing_ratio_pct": st.column_config.NumberColumn("Ratio %", format="%.1f%%"),
                    "total_quantity": st.column_config.NumberColumn("Qty", format="%.2f"),
                },
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No landing ratio data available for the latest year.")


# ============================================================
# MAIN APPLICATION
# ============================================================

def main():
    try:
        render_header()
        st.markdown("---")

        # Inline filters
        filters = render_filters()
        st.markdown("---")

        # Load main data + breakdown data
        with st.spinner("Loading cost data..."):
            df = data_loader.get_landed_cost_data(**filters)
            bd_df = data_loader.get_cost_breakdown_data(**filters)

        # === Three tabs ===
        tab_lookup, tab_yoy, tab_analytics = st.tabs([
            "📋 Cost Lookup",
            "📊 YoY Comparison",
            "📈 Analytics",
        ])

        # --- Tab 1: Cost Lookup ---
        with tab_lookup:
            render_kpi_cards(df, bd_df)
            st.markdown("---")
            render_data_table(df, bd_df)
            if not df.empty:
                st.markdown("---")
                render_export(df)

            # Trigger dialog
            if (st.session_state.get("lc_show_detail")
                    and st.session_state.get("lc_detail_data")):
                show_detail_dialog(st.session_state["lc_detail_data"])

        # --- Tab 2: YoY ---
        with tab_yoy:
            render_tab_yoy(filters)

        # --- Tab 3: Analytics ---
        with tab_analytics:
            render_tab_analytics(df, bd_df, filters)

    except Exception as e:
        st.error(f"Error loading Landed Cost page: {str(e)}")
        logger.error(f"Application error: {e}", exc_info=True)

        if st.button("🔄 Reload"):
            st.cache_data.clear()
            st.session_state["lc_selected_idx"] = None
            st.rerun()

    # Footer
    st.markdown("---")
    st.caption("Landed Cost v3.0")


main()