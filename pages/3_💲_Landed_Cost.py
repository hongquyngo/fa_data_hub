"""
Page: Landed Cost Lookup & Analysis (Refactored)

Version: 2.0.0
Changes:
- v2.0: Full refactor following Inventory Quality pattern
  + Inline filters (removed sidebar)
  + Checkbox single-row selection with detail dialog
  + Deep-dive into Arrival and Opening Balance sources
  + Removed Tab 4 (merged into dialog)
  + KPI computed from loaded df (removed separate query)
  + Heatmaps in Analytics tab
  + Excel export with formatted header

Features:
- Tab 1: Cost Lookup — main table, checkbox select, detail dialog
- Tab 2: YoY Comparison — significant changes, full comparison
- Tab 3: Analytics — trends, distribution, heatmaps
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
    format_usd4,
    format_quantity,
    format_pct_change,
    format_rate,
    format_date,
    safe_get,
    build_cost_trend_chart,
    build_cost_distribution_chart,
    build_source_breakdown_chart,
    build_yoy_comparison_table,
    build_brand_year_heatmap,
    build_entity_year_heatmap,
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

    # Row 1
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
        st.write("")  # spacer
        st.write("")
        if st.button("🔄 Clear", use_container_width=True, key="lc_clear_filters"):
            for k in ["lc_entity", "lc_year", "lc_brand", "lc_product_search"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.session_state["lc_selected_idx"] = None
            st.rerun()

    # Row 2
    product_search = st.text_input(
        "🔍 Search Product",
        placeholder="PT Code or Product Name...",
        key="lc_product_search",
    )

    return {
        "entity_ids": tuple(selected_entities) if selected_entities else None,
        "brand_list": tuple(selected_brands) if selected_brands else None,
        "year_list": tuple(selected_years) if selected_years else None,
        "product_search": product_search.strip() or None,
    }


# ============================================================
# TAB 1: COST LOOKUP
# ============================================================

def render_kpi_cards(df: pd.DataFrame):
    """KPI cards computed from loaded DataFrame — no separate query."""
    if df.empty:
        return

    # Row 1
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("📦 Products", f"{df['product_id'].nunique():,}")
    with c2:
        st.metric("🏷️ Brands", f"{df['brand'].nunique():,}")
    with c3:
        total_val = df["total_landed_value_usd"].sum()
        st.metric("💰 Total Value", format_usd(total_val))
    with c4:
        txn_count = df["transaction_count"].sum() if "transaction_count" in df.columns else len(df)
        st.metric("📝 Transactions", f"{int(txn_count):,}")

    # Row 2 — Cost Insight
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        total_qty = df["total_quantity"].sum()
        w_avg = total_val / total_qty if total_qty > 0 else 0
        st.metric("📊 Weighted Avg Cost", format_usd4(w_avg))
    with c6:
        if not df.empty:
            top = df.nlargest(1, "average_landed_cost_usd").iloc[0]
            st.metric(
                "📈 Highest Cost",
                format_usd4(top["average_landed_cost_usd"]),
                delta=top.get("pt_code", ""),
                delta_color="off",
            )
    with c7:
        if "cost_year" in df.columns and df["cost_year"].nunique() >= 2:
            years = sorted(df["cost_year"].unique(), reverse=True)
            curr_avg = df[df["cost_year"] == years[0]]["average_landed_cost_usd"].mean()
            prev_avg = df[df["cost_year"] == years[1]]["average_landed_cost_usd"].mean()
            if prev_avg and prev_avg > 0:
                change = (curr_avg - prev_avg) / prev_avg * 100
                st.metric("🔄 YoY Avg Change", format_pct_change(change))
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
                    / merged["average_landed_cost_usd_p"].replace(0, pd.NA) * 100
                )
                alert_count = (merged["pct"].abs() > LandedCostConstants.SIGNIFICANT_CHANGE_PCT).sum()
                st.metric("⚠️ Products >10%", f"{alert_count}")
            else:
                st.metric("⚠️ Products >10%", "0")
        else:
            st.metric("⚠️ Products >10%", "-")


@st.fragment
def render_data_table(df: pd.DataFrame):
    """Cost lookup table with single-row checkbox selection.
    Wrapped in @st.fragment so checkbox/button interactions
    only rerun this section, not the entire page.
    """
    if df.empty:
        st.info("📭 No data found for the selected filters.")
        return

    st.markdown(f"**{len(df):,} records** | 💡 Tick checkbox to select a row and view details")

    display_df = df.reset_index(drop=True).copy()

    # Checkbox column
    display_df["Select"] = False
    if (st.session_state.lc_selected_idx is not None
            and st.session_state.lc_selected_idx < len(display_df)):
        display_df.loc[st.session_state.lc_selected_idx, "Select"] = True

    # Columns for display
    show_cols = [
        "Select", "cost_year", "legal_entity", "pt_code", "product_pn", "brand",
        "standard_uom", "average_landed_cost_usd", "total_quantity",
        "total_landed_value_usd", "min_landed_cost_usd", "max_landed_cost_usd",
        "arrival_quantity", "opening_balance_quantity", "transaction_count",
    ]
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
        "average_landed_cost_usd": st.column_config.NumberColumn("Avg Cost", format="$%.4f", width="small"),
        "total_quantity": st.column_config.NumberColumn("Total Qty", format="%.2f", width="small"),
        "total_landed_value_usd": st.column_config.NumberColumn("Total Value", format="$%.2f", width="small"),
        "min_landed_cost_usd": st.column_config.NumberColumn("Min", format="$%.4f", width="small"),
        "max_landed_cost_usd": st.column_config.NumberColumn("Max", format="$%.4f", width="small"),
        "arrival_quantity": st.column_config.NumberColumn("Arr Qty", format="%.2f", width="small"),
        "opening_balance_quantity": st.column_config.NumberColumn("OB Qty", format="%.2f", width="small"),
        "transaction_count": st.column_config.NumberColumn("Txn", format="%d", width="small"),
    }

    disabled_cols = [c for c in show_cols if c != "Select"]

    edited_df = st.data_editor(
        display_df[show_cols],
        column_config=col_config,
        disabled=disabled_cols,
        use_container_width=True,
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
                st.rerun()  # fragment-scoped: only reruns table
        else:
            st.session_state.lc_selected_idx = selected_indices[0]
    else:
        st.session_state.lc_selected_idx = None

    # Action buttons
    if (st.session_state.lc_selected_idx is not None
            and st.session_state.lc_selected_idx < len(display_df)):
        sel = display_df.iloc[st.session_state.lc_selected_idx]

        st.markdown("---")
        st.markdown(
            f"**Selected:** `{sel.get('pt_code', '')}` | {sel.get('product_pn', '')} | "
            f"{sel.get('legal_entity', '')} | {int(sel.get('cost_year', 0))} | "
            f"Avg: {format_usd4(sel.get('average_landed_cost_usd'))}"
        )

        bc1, bc2, bc3, bc4 = st.columns(4)
        with bc1:
            if st.button("🔍 View Details", type="primary", use_container_width=True,
                         key="btn_view_detail"):
                st.session_state["lc_detail_data"] = sel.to_dict()
                st.session_state["lc_show_detail"] = True
                st.rerun(scope="app")  # full page rerun to trigger dialog
        with bc2:
            if st.button("❌ Deselect", use_container_width=True, key="btn_deselect"):
                st.session_state["lc_selected_idx"] = None
                st.rerun()  # fragment-scoped
    else:
        st.info("💡 Tick checkbox to select a row and perform actions")


@st.fragment
def render_export(df: pd.DataFrame):
    """Export to Excel.
    Wrapped in @st.fragment so download button click
    doesn't trigger full page rerun.
    """
    if df.empty:
        return

    col1, col2 = st.columns([1, 4])
    with col1:
        try:
            export_df = data_loader.get_export_data(
                entity_ids=st.session_state.get("lc_entity") or None,
                brand_list=st.session_state.get("lc_brand") or None,
                year_list=st.session_state.get("lc_year") or None,
                product_search=st.session_state.get("lc_product_search") or None,
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
    """Detail popup: summary → cost history → source records (arrival/OB)."""
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
    st.markdown(f"Brand: **{brand}** | Entity: **{entity}** | Year: **{int(cost_year) if cost_year else '-'}** | UOM: {uom}")
    st.markdown("---")

    # --- Cost Summary (from selected row — no query) ---
    st.markdown("#### 📊 Cost Summary")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        st.metric("Avg Cost", format_usd4(safe_get(row_data, "average_landed_cost_usd")))
        st.metric("Min Cost", format_usd4(safe_get(row_data, "min_landed_cost_usd")))
    with sc2:
        st.metric("Max Cost", format_usd4(safe_get(row_data, "max_landed_cost_usd")))
        st.metric("Total Value", format_usd(safe_get(row_data, "total_landed_value_usd")))
    with sc3:
        st.metric("Total Qty", format_quantity(safe_get(row_data, "total_quantity")))
        arr = safe_get(row_data, "arrival_quantity", 0) or 0
        ob = safe_get(row_data, "opening_balance_quantity", 0) or 0
        st.metric("Arrivals / OB", f"{format_quantity(arr)} / {format_quantity(ob)}")

    st.markdown("---")

    # --- Cost History (all years — 1 query) ---
    if product_id and entity_id:
        st.markdown("#### 📈 Cost History")
        with st.spinner("Loading history..."):
            history = data_loader.get_product_cost_history(
                product_id=int(product_id), entity_id=int(entity_id)
            )

        if not history.empty:
            hist_cols = [c for c in [
                "cost_year", "average_landed_cost_usd", "total_quantity",
                "total_landed_value_usd", "arrival_quantity",
                "opening_balance_quantity",
            ] if c in history.columns]

            st.dataframe(
                history[hist_cols],
                column_config={
                    "cost_year": st.column_config.NumberColumn("Year", format="%d"),
                    "average_landed_cost_usd": st.column_config.NumberColumn("Avg Cost", format="$%.4f"),
                    "total_quantity": st.column_config.NumberColumn("Qty", format="%.2f"),
                    "total_landed_value_usd": st.column_config.NumberColumn("Value", format="$%.2f"),
                    "arrival_quantity": st.column_config.NumberColumn("Arr Qty", format="%.2f"),
                    "opening_balance_quantity": st.column_config.NumberColumn("OB Qty", format="%.2f"),
                },
                use_container_width=True,
                hide_index=True,
                height=min(len(history) * 35 + 38, 250),
            )

            if len(history) > 1:
                fig = build_cost_trend_chart(history)
                if fig:
                    fig.update_layout(title=f"Cost Trend: {pt_code}", height=280)
                    st.plotly_chart(fig, use_container_width=True)
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

    # Load both sources
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
                "vendor_name", "arrival_quantity", "landed_cost_usd",
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
                    "landed_cost_usd": st.column_config.NumberColumn("Unit USD", format="$%.4f", width="small"),
                    "total_value_usd": st.column_config.NumberColumn("Total USD", format="$%.2f", width="small"),
                    "warehouse_name": st.column_config.TextColumn("Warehouse", width="medium"),
                    "ship_method": st.column_config.TextColumn("Ship", width="small"),
                },
                use_container_width=True,
                hide_index=True,
                height=min(arr_count * 35 + 38, 300),
            )

            # Arrival detail drill-down
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
                use_container_width=True,
                hide_index=True,
                height=min(ob_count * 35 + 38, 300),
            )


@st.fragment
def _render_arrival_detail_selector(arr_df: pd.DataFrame):
    """Selectbox + expander to drill into a single arrival record.
    Wrapped in @st.fragment so changing the selectbox only reruns
    this section — avoids re-querying cost history + source tables.
    """
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
                    st.markdown(f"Unit USD: {format_usd4(detail.get('unit_cost_usd'))}")
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
    """Year-over-year cost comparison."""
    with st.spinner("Loading YoY data..."):
        yoy_df = data_loader.get_yoy_comparison(
            entity_ids=filters["entity_ids"],
            brand_list=filters["brand_list"],
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

    # Summary metrics
    has_change = comparison["yoy_change_pct"].dropna()
    if not has_change.empty:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("🔺 Cost Increased", f"{(has_change > 0).sum()} products")
        with c2:
            st.metric("🔻 Cost Decreased", f"{(has_change < 0).sum()} products")
        with c3:
            st.metric("➡️ Unchanged", f"{(has_change == 0).sum()} products")
        with c4:
            st.metric("Avg Change", format_pct_change(has_change.mean()))

    st.markdown("---")

    # Significant changes
    threshold = LandedCostConstants.SIGNIFICANT_CHANGE_PCT
    significant = comparison[comparison["yoy_change_pct"].abs() > threshold].copy()

    if not significant.empty:
        st.markdown(f"**⚠️ Significant changes (>{threshold:.0f}%) — {prev_year} → {current_year}:**")
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
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success(f"No significant cost changes (>{threshold:.0f}%) detected.")

    # Full table
    with st.expander(f"📋 Full Comparison ({len(comparison)} products)", expanded=False):
        st.dataframe(comparison, use_container_width=True, hide_index=True)


# ============================================================
# TAB 3: ANALYTICS
# ============================================================

def render_tab_analytics(df: pd.DataFrame, filters: dict):
    """Charts and visual analysis including heatmaps."""
    if df.empty:
        st.info("No data for analytics. Adjust filters.")
        return

    # --- Row 1: Cost Trend ---
    st.markdown("##### 📈 Cost Trend")
    trend_chart = build_cost_trend_chart(df)
    if trend_chart:
        st.plotly_chart(trend_chart, use_container_width=True)

    st.markdown("---")

    # --- Row 2: Distribution + Source Breakdown ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("##### 📊 Cost Distribution by Brand")
        year_for_dist = filters["year_list"][0] if filters["year_list"] else None
        dist_chart = build_cost_distribution_chart(df, year=year_for_dist)
        if dist_chart:
            st.plotly_chart(dist_chart, use_container_width=True)
        else:
            st.info("Not enough data for distribution chart.")

    with col_right:
        st.markdown("##### 📦 Source Breakdown (Arrival vs OB)")
        source_chart = build_source_breakdown_chart(df)
        if source_chart:
            st.plotly_chart(source_chart, use_container_width=True)
        else:
            st.info("Not enough data for source chart.")

    st.markdown("---")

    # --- Row 3: Heatmaps ---
    st.markdown("##### 🔥 Brand × Year Heatmap (Weighted Avg Cost)")
    heatmap1 = build_brand_year_heatmap(df)
    if heatmap1:
        st.plotly_chart(heatmap1, use_container_width=True)
    else:
        st.info("Need at least 2 brands and 2 years for heatmap.")

    st.markdown("---")

    st.markdown("##### 🔥 Entity × Year Heatmap (Total Value)")
    heatmap2 = build_entity_year_heatmap(df)
    if heatmap2:
        st.plotly_chart(heatmap2, use_container_width=True)
    else:
        st.info("Need at least 2 entities and 2 years for heatmap.")

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
            use_container_width=True,
            hide_index=True,
        )


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

        # Load main data
        with st.spinner("Loading cost data..."):
            df = data_loader.get_landed_cost_data(**filters)

        # === Three tabs ===
        tab_lookup, tab_yoy, tab_analytics = st.tabs([
            "📋 Cost Lookup",
            "📊 YoY Comparison",
            "📈 Analytics",
        ])

        # --- Tab 1: Cost Lookup ---
        with tab_lookup:
            render_kpi_cards(df)
            st.markdown("---")
            render_data_table(df)
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
            render_tab_analytics(df, filters)

    except Exception as e:
        st.error(f"Error loading Landed Cost page: {str(e)}")
        logger.error(f"Application error: {e}", exc_info=True)

        if st.button("🔄 Reload"):
            st.cache_data.clear()
            st.session_state["lc_selected_idx"] = None
            st.rerun()

    # Footer
    st.markdown("---")
    st.caption("Landed Cost v2.0")


main()