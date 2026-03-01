# utils/legal_entity_performance/sales_detail/fragments.py
"""
Streamlit Fragments for Legal Entity Performance - Sales Detail Tab.
Adapted from kpi_center_performance/sales_detail/fragments.py

Contains:
- sales_detail_tab_fragment: Tab-level wrapper with filters
- sales_detail_fragment: Sales transaction list
- pivot_analysis_fragment: Configurable pivot table

VERSION: 2.0.0
"""

import logging
from typing import Dict, Optional
from datetime import datetime
import pandas as pd
import streamlit as st

from ..constants import MONTH_ORDER
from ..export_utils import LegalEntityExport

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER: Format product display
# =============================================================================

def _format_product_display(row) -> str:
    """Format product as 'PT Code | Name | Package Size'."""
    parts = []
    if pd.notna(row.get('pt_code')) and row.get('pt_code'):
        parts.append(str(row['pt_code']))
    if pd.notna(row.get('product_pn')) and row.get('product_pn'):
        parts.append(str(row['product_pn']))
    if pd.notna(row.get('package_size')) and row.get('package_size'):
        parts.append(str(row['package_size']))
    return ' | '.join(parts) if parts else ''


def _format_oc_po(row) -> str:
    """Format OC# with Customer PO."""
    oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
    po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
    if oc and po:
        return f"{oc}\n(PO: {po})"
    return oc or po or ''


# =============================================================================
# TAB-LEVEL FRAGMENT
# =============================================================================

@st.fragment
def sales_detail_tab_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    key_prefix: str = "le_sales_tab"
):
    """
    Fragment wrapper for Sales Detail tab.
    Includes filters + sub-tabs (Sales List + Pivot Analysis).
    """
    if sales_df.empty:
        st.info("No sales data for the selected period")
        return
    
    total_count = len(sales_df)
    
    # =========================================================================
    # FILTERS ROW (with Excl checkboxes - synced with KPI Center)
    # =========================================================================
    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
    
    with col_f1:
        _lbl1, _excl1 = st.columns([3, 1])
        with _lbl1:
            st.markdown("**Customer**")
        with _excl1:
            excl_customer = st.checkbox("Excl", key=f"{key_prefix}_excl_customer")
        customer_options = sorted(sales_df['customer'].dropna().unique().tolist())
        selected_customers = st.multiselect(
            "Customer", customer_options,
            key=f"{key_prefix}_customer", placeholder="Choose options",
            label_visibility="collapsed"
        )
    
    with col_f2:
        _lbl2, _excl2 = st.columns([3, 1])
        with _lbl2:
            st.markdown("**Brand**")
        with _excl2:
            excl_brand = st.checkbox("Excl", key=f"{key_prefix}_excl_brand")
        brand_options = sorted(sales_df['brand'].dropna().unique().tolist())
        selected_brands = st.multiselect(
            "Brand", brand_options,
            key=f"{key_prefix}_brand", placeholder="Choose options",
            label_visibility="collapsed"
        )
    
    with col_f3:
        _lbl3, _excl3 = st.columns([3, 1])
        with _lbl3:
            st.markdown("**Product**")
        with _excl3:
            excl_product = st.checkbox("Excl", key=f"{key_prefix}_excl_product")
        product_options = sorted(sales_df['product_pn'].dropna().unique().tolist()[:200])
        selected_products = st.multiselect(
            "Product", product_options,
            key=f"{key_prefix}_product", placeholder="Choose options",
            label_visibility="collapsed"
        )
    
    with col_f4:
        _lbl4, _excl4 = st.columns([3, 1])
        with _lbl4:
            st.markdown("**OC# / Customer PO**")
        with _excl4:
            excl_oc = st.checkbox("Excl", key=f"{key_prefix}_excl_oc")
        oc_search = st.text_input(
            "OC# / PO Search",
            key=f"{key_prefix}_oc_search",
            placeholder="Search...",
            label_visibility="collapsed"
        )
    
    with col_f5:
        _lbl5, _excl5 = st.columns([3, 1])
        with _lbl5:
            st.markdown("**Min Amount ($)**")
        with _excl5:
            excl_amount = st.checkbox("Excl", key=f"{key_prefix}_excl_amount")
        min_amount = st.number_input(
            "Min Amount ($)",
            min_value=0, value=0, step=1000,
            key=f"{key_prefix}_min_amount",
            label_visibility="collapsed"
        )
    
    # =========================================================================
    # APPLY FILTERS (with Excl logic)
    # =========================================================================
    filtered_df = sales_df.copy()
    
    if selected_customers:
        if excl_customer:
            filtered_df = filtered_df[~filtered_df['customer'].isin(selected_customers)]
        else:
            filtered_df = filtered_df[filtered_df['customer'].isin(selected_customers)]
    if selected_brands:
        if excl_brand:
            filtered_df = filtered_df[~filtered_df['brand'].isin(selected_brands)]
        else:
            filtered_df = filtered_df[filtered_df['brand'].isin(selected_brands)]
    if selected_products:
        if excl_product:
            filtered_df = filtered_df[~filtered_df['product_pn'].isin(selected_products)]
        else:
            filtered_df = filtered_df[filtered_df['product_pn'].isin(selected_products)]
    
    if oc_search:
        search_lower = oc_search.lower()
        mask = pd.Series(False, index=filtered_df.index)
        if 'oc_number' in filtered_df.columns:
            mask |= filtered_df['oc_number'].astype(str).str.lower().str.contains(search_lower, na=False)
        if 'customer_po_number' in filtered_df.columns:
            mask |= filtered_df['customer_po_number'].astype(str).str.lower().str.contains(search_lower, na=False)
        filtered_df = filtered_df[~mask] if excl_oc else filtered_df[mask]
    
    if min_amount > 0 and 'calculated_invoiced_amount_usd' in filtered_df.columns:
        if excl_amount:
            filtered_df = filtered_df[filtered_df['calculated_invoiced_amount_usd'] < min_amount]
        else:
            filtered_df = filtered_df[filtered_df['calculated_invoiced_amount_usd'] >= min_amount]
    
    # Filter summary
    active_filters = []
    if selected_customers:
        mode = "excl" if excl_customer else "incl"
        active_filters.append(f"Customer: {len(selected_customers)} ({mode})")
    if selected_brands:
        mode = "excl" if excl_brand else "incl"
        active_filters.append(f"Brand: {len(selected_brands)} ({mode})")
    if selected_products:
        mode = "excl" if excl_product else "incl"
        active_filters.append(f"Product: {len(selected_products)} ({mode})")
    if oc_search:
        mode = "excl" if excl_oc else "incl"
        active_filters.append(f"OC/PO: '{oc_search}' ({mode})")
    if min_amount > 0:
        mode = "excl" if excl_amount else "incl"
        active_filters.append(f"Amount: ≥${min_amount:,.0f} ({mode})")
    
    if active_filters:
        st.caption(f"🔍 Active filters: {' | '.join(active_filters)}")
    
    st.divider()
    
    # =========================================================================
    # SUB-TABS
    # =========================================================================
    sales_tab1, sales_tab2 = st.tabs(["📋 Sales List", "📊 Pivot Analysis"])
    
    with sales_tab1:
        sales_detail_fragment(
            sales_df=filtered_df,
            fragment_key=f"{key_prefix}_detail",
            total_count=total_count
        )
    
    with sales_tab2:
        pivot_analysis_fragment(
            sales_df=filtered_df,
            fragment_key=f"{key_prefix}_pivot"
        )


# =============================================================================
# SALES DETAIL FRAGMENT
# =============================================================================

def sales_detail_fragment(
    sales_df: pd.DataFrame,
    fragment_key: str = "le_sales",
    total_count: int = None
):
    """Sales transaction list with summary metrics and formatted columns."""
    if sales_df.empty:
        st.info("No sales data for selected period")
        return
    
    original_count = total_count if total_count is not None else len(sales_df)
    
    # =========================================================================
    # SUMMARY METRICS (7 columns - synced with KPI center)
    # =========================================================================
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    total_revenue = sales_df['calculated_invoiced_amount_usd'].sum() if 'calculated_invoiced_amount_usd' in sales_df.columns else 0
    total_gp = sales_df['invoiced_gross_profit_usd'].sum() if 'invoiced_gross_profit_usd' in sales_df.columns else 0
    total_gp1 = sales_df['invoiced_gp1_usd'].sum() if 'invoiced_gp1_usd' in sales_df.columns else 0
    gp_percent = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
    total_invoices = sales_df['inv_number'].nunique() if 'inv_number' in sales_df.columns else 0
    total_orders = sales_df['oc_number'].nunique() if 'oc_number' in sales_df.columns else total_invoices
    total_customers = sales_df['customer_id'].nunique() if 'customer_id' in sales_df.columns else 0
    
    with col_s1:
        st.metric("💰 Revenue", f"${total_revenue:,.0f}",
                   delta=f"{total_invoices:,} invoices", delta_color="off")
    with col_s2:
        st.metric("📈 GP", f"${total_gp:,.0f}",
                   delta=f"{gp_percent:.1f}% margin", delta_color="off")
    with col_s3:
        st.metric("📊 GP1", f"${total_gp1:,.0f}", delta_color="off")
    with col_s4:
        st.metric("📋 Orders", f"{total_orders:,}", delta_color="off")
    with col_s5:
        st.metric("👥 Customers", f"{total_customers:,}", delta_color="off")
    with col_s6:
        avg_order = total_revenue / total_orders if total_orders > 0 else 0
        st.metric("📦 Avg Order", f"${avg_order:,.0f}", delta_color="off")
    with col_s7:
        avg_gp = total_gp / total_orders if total_orders > 0 else 0
        st.metric("💵 Avg GP", f"${avg_gp:,.0f}", delta_color="off")
    
    st.divider()
    
    # =========================================================================
    # PREPARE DISPLAY DATA
    # =========================================================================
    display_df = sales_df.copy()
    
    # Format product display
    display_df['product_display'] = display_df.apply(_format_product_display, axis=1)
    
    # Format OC/PO display
    if 'oc_number' in display_df.columns:
        display_df['oc_po_display'] = display_df.apply(_format_oc_po, axis=1)
    
    # =========================================================================
    # DISPLAY COLUMNS
    # =========================================================================
    display_columns = [
        'inv_date', 'inv_number', 'oc_po_display',
        'legal_entity', 'customer', 'customer_type',
        'product_display', 'brand',
        'calculated_invoiced_amount_usd', 'invoiced_gross_profit_usd',
        'gross_profit_percent', 'invoiced_gp1_usd', 'broker_commission_usd',
        'payment_status', 'cost_source',
    ]
    available_cols = [c for c in display_columns if c in display_df.columns]
    
    st.markdown(f"**Showing {len(display_df):,} transactions** (of {original_count:,} total)")
    
    display_detail = display_df[available_cols].head(500).copy()
    
    # =========================================================================
    # COLUMN CONFIG WITH TOOLTIPS
    # =========================================================================
    # Pre-format currency columns for reliable display
    for col in ['calculated_invoiced_amount_usd', 'invoiced_gross_profit_usd',
                'invoiced_gp1_usd', 'broker_commission_usd']:
        if col in display_detail.columns:
            display_detail[col] = display_detail[col].apply(
                lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
            )
    if 'gross_profit_percent' in display_detail.columns:
        display_detail['gross_profit_percent'] = display_detail['gross_profit_percent'].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "0.0%"
        )
    
    column_config = {
        'inv_date': st.column_config.DateColumn("Date", help="Invoice date"),
        'inv_number': st.column_config.TextColumn("Invoice#", help="Invoice number"),
        'oc_po_display': st.column_config.TextColumn(
            "OC / PO", help="Order Confirmation & Customer PO", width="medium"
        ),
        'legal_entity': st.column_config.TextColumn("Entity", help="Legal Entity"),
        'customer': st.column_config.TextColumn("Customer", width="medium"),
        'customer_type': st.column_config.TextColumn("Type", help="Internal/External"),
        'product_display': st.column_config.TextColumn(
            "Product", help="PT Code | Name | Package", width="large"
        ),
        'brand': st.column_config.TextColumn("Brand"),
        'calculated_invoiced_amount_usd': st.column_config.TextColumn(
            "Revenue", help="Invoiced amount (USD)"
        ),
        'invoiced_gross_profit_usd': st.column_config.TextColumn(
            "GP", help="Gross Profit (USD) = Revenue - COGS"
        ),
        'gross_profit_percent': st.column_config.TextColumn(
            "GP%", help="Gross Profit Margin %"
        ),
        'invoiced_gp1_usd': st.column_config.TextColumn(
            "GP1", help="GP after broker commission deduction"
        ),
        'broker_commission_usd': st.column_config.TextColumn(
            "Commission", help="Broker commission (USD)"
        ),
        'payment_status': st.column_config.TextColumn("Payment", help="Payment status"),
        'cost_source': st.column_config.TextColumn("Cost Source", help="Source of cost data"),
    }
    
    st.dataframe(
        display_detail,
        column_config=column_config,
        width="stretch",
        hide_index=True,
        height=500
    )
    
    # Legend
    with st.expander("📖 Column Legend", expanded=False):
        st.markdown("""
| Column | Description |
|--------|-------------|
| **OC / PO** | Order Confirmation & Customer PO |
| **Product** | PT Code \\| Name \\| Package Size |
| **Revenue** | Total invoiced amount (USD) |
| **GP** | Gross Profit = Revenue - COGS |
| **GP%** | Gross Profit Margin |
| **GP1** | GP after deducting broker commission |
| **Commission** | Broker commission amount |

> 💡 **Tip:** Hover over column headers to see detailed tooltips.
        """)
    
    # Export
    st.caption("💡 For full report, use **Export Report** in Overview tab")
    if st.button("📥 Export Filtered View", key=f"{fragment_key}_export"):
        from io import BytesIO
        
        export_columns = {
            'inv_date': 'Date',
            'inv_number': 'Invoice#',
            'oc_number': 'OC#',
            'legal_entity': 'Entity',
            'customer': 'Customer',
            'customer_type': 'Type',
            'product_pn': 'Product',
            'brand': 'Brand',
            'calculated_invoiced_amount_usd': 'Revenue (USD)',
            'invoiced_gross_profit_usd': 'GP (USD)',
            'gross_profit_percent': 'GP%',
            'invoiced_gp1_usd': 'GP1 (USD)',
            'broker_commission_usd': 'Commission (USD)',
            'payment_status': 'Payment',
        }
        
        export_df = sales_df.copy()
        available_export = {k: v for k, v in export_columns.items() if k in export_df.columns}
        export_df = export_df[list(available_export.keys())].rename(columns=available_export)
        
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='Filtered Sales', index=False)
        
        st.download_button(
            label="⬇️ Download Filtered Data",
            data=buffer.getvalue(),
            file_name=f"le_filtered_sales_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# =============================================================================
# PIVOT ANALYSIS FRAGMENT
# =============================================================================

def pivot_analysis_fragment(
    sales_df: pd.DataFrame,
    fragment_key: str = "le_pivot"
):
    """
    Configurable pivot table analysis.
    Synced with KPI center: same layout, month ordering, gradient styling.
    """
    if sales_df.empty:
        st.info("No data for pivot analysis")
        return
    
    st.subheader("📊 Pivot Analysis")
    
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        row_options = ['customer', 'brand', 'legal_entity', 'product_pn', 'customer_type']
        row_options = [r for r in row_options if r in sales_df.columns]
        pivot_rows = st.selectbox("Rows", row_options, index=0, key=f"{fragment_key}_rows")
    
    with col_p2:
        col_options = ['invoice_month', 'brand', 'customer', 'legal_entity', 'customer_type']
        col_options = [c for c in col_options if c in sales_df.columns or c == 'invoice_month']
        pivot_cols = st.selectbox("Columns", col_options, index=0, key=f"{fragment_key}_cols")
    
    with col_p3:
        value_options = [
            'calculated_invoiced_amount_usd',
            'invoiced_gross_profit_usd',
            'invoiced_gp1_usd',
        ]
        value_options = [v for v in value_options if v in sales_df.columns]
        default_idx = 1 if len(value_options) > 1 else 0
        
        pivot_values = st.selectbox(
            "Values", value_options, index=default_idx,
            key=f"{fragment_key}_values",
            format_func=lambda x: x.replace('_usd', '').replace('calculated_invoiced_amount', 'Revenue')
                .replace('invoiced_gross_profit', 'Gross Profit')
                .replace('invoiced_gp1', 'GP1')
                .replace('_', ' ').title()
        )
    
    # Ensure month column
    df = sales_df.copy()
    if 'invoice_month' not in df.columns and 'inv_date' in df.columns:
        df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
        df['invoice_month'] = df['inv_date'].dt.strftime('%b')
    
    # Create pivot
    if pivot_rows in df.columns and (pivot_cols in df.columns or pivot_cols == 'invoice_month'):
        pivot_df = df.pivot_table(
            values=pivot_values,
            index=pivot_rows,
            columns=pivot_cols,
            aggfunc='sum',
            fill_value=0
        )
        
        pivot_df['Total'] = pivot_df.sum(axis=1)
        pivot_df = pivot_df.sort_values('Total', ascending=False)
        
        # Reorder months Jan → Dec
        if pivot_cols == 'invoice_month':
            month_cols = [m for m in MONTH_ORDER if m in pivot_df.columns]
            other_cols = [c for c in pivot_df.columns if c not in MONTH_ORDER and c != 'Total']
            pivot_df = pivot_df[month_cols + other_cols + ['Total']]
        
        st.dataframe(
            pivot_df.style.format("${:,.0f}").background_gradient(cmap='Blues', subset=['Total']),
            width="stretch",
            height=500
        )
    else:
        st.warning("Selected columns not available in data")