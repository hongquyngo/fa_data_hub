# utils/kpi_center_performance/sales_detail/fragments.py
"""
Streamlit Fragments for KPI Center Performance - Sales Detail Tab.

Contains:
- sales_detail_tab_fragment: Tab-level wrapper with filters
- sales_detail_fragment: Sales transaction list
- pivot_analysis_fragment: Configurable pivot table
"""

import logging
from typing import Dict, Optional
from datetime import datetime
import pandas as pd
import streamlit as st

from ..constants import MONTH_ORDER
from ..common.fragments import format_product_display, format_oc_po

from ..filters import (
    render_multiselect_filter,
    apply_multiselect_filter,
    render_text_search_filter,
    apply_text_search_filter,
    render_number_filter,
    apply_number_filter,
)

logger = logging.getLogger(__name__)


# =============================================================================
# TAB-LEVEL FRAGMENT - v4.2.0
# =============================================================================

@st.fragment
def sales_detail_tab_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    key_prefix: str = "sales_tab"
):
    """
    Fragment wrapper for Sales Detail tab.
    
    Includes filters + sub-tabs. Changes to filters only rerun this fragment,
    not the entire page.
    
    Args:
        sales_df: Raw sales DataFrame
        filter_values: Filter values from sidebar
        key_prefix: Unique key prefix for widgets
    """
    if sales_df.empty:
        st.info("No sales data for the selected period")
        return
    
    # Store original count
    total_count = len(sales_df)
    
    # =========================================================================
    # FILTERS ROW
    # =========================================================================
    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
    
    with col_f1:
        customer_options = sorted(sales_df['customer'].dropna().unique().tolist())
        customer_filter = render_multiselect_filter(
            label="Customer",
            options=customer_options,
            key=f"{key_prefix}_customer"
        )
    
    with col_f2:
        brand_options = sorted(sales_df['brand'].dropna().unique().tolist())
        brand_filter = render_multiselect_filter(
            label="Brand",
            options=brand_options,
            key=f"{key_prefix}_brand"
        )
    
    with col_f3:
        product_options = sorted(sales_df['product_pn'].dropna().unique().tolist())
        product_filter = render_multiselect_filter(
            label="Product",
            options=product_options,
            key=f"{key_prefix}_product"
        )
    
    with col_f4:
        oc_po_filter = render_text_search_filter(
            label="OC# / Customer PO",
            key=f"{key_prefix}_oc_po",
            placeholder="Search..."
        )
    
    with col_f5:
        amount_filter = render_number_filter(
            label="Min Amount ($)",
            key=f"{key_prefix}_min_amount",
            default_min=0,
            step=1000
        )
    
    # =========================================================================
    # APPLY FILTERS
    # =========================================================================
    filtered_df = sales_df.copy()
    filtered_df = apply_multiselect_filter(filtered_df, 'customer', customer_filter)
    filtered_df = apply_multiselect_filter(filtered_df, 'brand', brand_filter)
    filtered_df = apply_multiselect_filter(filtered_df, 'product_pn', product_filter)
    
    # Text search
    search_columns = []
    if 'oc_number' in filtered_df.columns:
        search_columns.append('oc_number')
    if 'customer_po_number' in filtered_df.columns:
        search_columns.append('customer_po_number')
    if search_columns:
        filtered_df = apply_text_search_filter(filtered_df, columns=search_columns, search_result=oc_po_filter)
    
    # Number filter
    filtered_df = apply_number_filter(filtered_df, 'sales_by_kpi_center_usd', amount_filter)
    
    # =========================================================================
    # FILTER SUMMARY
    # =========================================================================
    active_filters = []
    if customer_filter.is_active:
        mode = "excl" if customer_filter.excluded else "incl"
        active_filters.append(f"Customer: {len(customer_filter.selected)} ({mode})")
    if brand_filter.is_active:
        mode = "excl" if brand_filter.excluded else "incl"
        active_filters.append(f"Brand: {len(brand_filter.selected)} ({mode})")
    if product_filter.is_active:
        mode = "excl" if product_filter.excluded else "incl"
        active_filters.append(f"Product: {len(product_filter.selected)} ({mode})")
    if oc_po_filter.is_active:
        mode = "excl" if oc_po_filter.excluded else "incl"
        active_filters.append(f"OC/PO: '{oc_po_filter.query}' ({mode})")
    if amount_filter.is_active:
        mode = "excl" if amount_filter.excluded else "incl"
        active_filters.append(f"Amount: ≥${amount_filter.min_value:,.0f} ({mode})")
    
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
# SALES DETAIL FRAGMENT - REFACTORED v2.6.0 (SYNCED with Salesperson)
# =============================================================================

@st.fragment
def sales_detail_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    overview_metrics: Dict = None,
    fragment_key: str = "kpc_sales",
    total_count: int = None
):
    """
    Fragment for Sales Detail transaction list.
    
    UPDATED v4.2.0: Filters moved to tab level.
    - Receives pre-filtered data
    - 7 summary metrics cards
    - Original value calculation (pre-split)
    - Formatted Product and OC/PO display
    - Detailed column config with tooltips
    - Column Legend expander
    - Export Filtered View button
    
    Args:
        sales_df: Pre-filtered sales DataFrame
        filter_values: Filter values dict (for reference)
        overview_metrics: Optional pre-calculated metrics
        fragment_key: Unique key prefix for widgets
        total_count: Original total count before filtering (for display)
    """
    if sales_df.empty:
        st.info("No sales data for selected period")
        return
    
    # Use total_count if provided, else use current df length
    original_count = total_count if total_count is not None else len(sales_df)
    
    # =================================================================
    # SUMMARY METRICS CARDS (7 columns - SYNCED with Salesperson)
    # =================================================================
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    total_revenue = sales_df['sales_by_kpi_center_usd'].sum()
    total_gp = sales_df['gross_profit_by_kpi_center_usd'].sum()
    total_gp1 = sales_df['gp1_by_kpi_center_usd'].sum() if 'gp1_by_kpi_center_usd' in sales_df.columns else 0
    gp_percent = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
    total_invoices = sales_df['inv_number'].nunique()
    total_orders = sales_df['oc_number'].nunique() if 'oc_number' in sales_df.columns else total_invoices
    total_customers = sales_df['customer_id'].nunique()
    
    with col_s1:
        st.metric(
            "💰 Revenue",
            f"${total_revenue:,.0f}",
            delta=f"{total_invoices:,} invoices",
            delta_color="off",
            help="Total revenue from all transactions (split-adjusted)"
        )
    with col_s2:
        st.metric(
            "📈 Gross Profit",
            f"${total_gp:,.0f}",
            delta=f"{gp_percent:.1f}% margin",
            delta_color="off",
            help="Total gross profit (split-adjusted)"
        )
    with col_s3:
        st.metric(
            "📊 GP1",
            f"${total_gp1:,.0f}",
            delta_color="off",
            help="GP1 = GP - (Broker Commission × 1.2)"
        )
    with col_s4:
        st.metric(
            "📋 Orders",
            f"{total_orders:,}",
            delta_color="off",
            help="Number of unique order confirmations"
        )
    with col_s5:
        st.metric(
            "👥 Customers",
            f"{total_customers:,}",
            delta_color="off",
            help="Number of unique customers"
        )
    with col_s6:
        # Average order value
        avg_order = total_revenue / total_orders if total_orders > 0 else 0
        st.metric(
            "📦 Avg Order",
            f"${avg_order:,.0f}",
            delta_color="off",
            help="Average revenue per order"
        )
    with col_s7:
        # Average GP per order
        avg_gp = total_gp / total_orders if total_orders > 0 else 0
        st.metric(
            "💵 Avg GP",
            f"${avg_gp:,.0f}",
            delta_color="off",
            help="Average gross profit per order"
        )
    
    st.divider()
    
    # =================================================================
    # PREPARE DISPLAY DATA
    # =================================================================
    filtered_df = sales_df.copy()
    
    # Calculate original values (before split)
    if 'split_rate_percent' in filtered_df.columns:
        # Avoid division by zero
        split_factor = filtered_df['split_rate_percent'].replace(0, 100) / 100
        filtered_df['total_revenue_usd'] = (filtered_df['sales_by_kpi_center_usd'] / split_factor).round(2)
        filtered_df['total_gp_usd'] = (filtered_df['gross_profit_by_kpi_center_usd'] / split_factor).round(2)
    else:
        filtered_df['total_revenue_usd'] = filtered_df['sales_by_kpi_center_usd']
        filtered_df['total_gp_usd'] = filtered_df['gross_profit_by_kpi_center_usd']
    
    # =================================================================
    # Format Product as "pt_code | Name | Package size"
    # =================================================================
    filtered_df['product_display'] = filtered_df.apply(format_product_display, axis=1)
    
    # =================================================================
    # Format OC with Customer PO: "OC#\n(PO: xxx)"
    # =================================================================
    if 'oc_number' in filtered_df.columns:
        filtered_df['oc_po_display'] = filtered_df.apply(format_oc_po, axis=1)
    
    # =================================================================
    # Display columns - reordered with new formatted columns
    # =================================================================
    display_columns = [
        'inv_date', 'inv_number', 'oc_po_display', 'customer', 'product_display', 'brand',
        'total_revenue_usd', 'total_gp_usd',  # Original values (Revenue, GP only)
        'split_rate_percent',
        'sales_by_kpi_center_usd', 'gross_profit_by_kpi_center_usd', 'gp1_by_kpi_center_usd',  # Split values
        'kpi_center'
    ]
    available_cols = [c for c in display_columns if c in filtered_df.columns]
    
    st.markdown(f"**Showing {len(filtered_df):,} transactions** (of {original_count:,} total)")
    
    # Prepare display dataframe
    display_detail = filtered_df[available_cols].head(500).copy()
    
    # =================================================================
    # Configure columns with tooltips using st.column_config
    # =================================================================
    column_config = {
        'inv_date': st.column_config.DateColumn(
            "Date",
            help="Invoice date"
        ),
        'inv_number': st.column_config.TextColumn(
            "Invoice#",
            help="Invoice number"
        ),
        'oc_po_display': st.column_config.TextColumn(
            "OC / PO",
            help="Order Confirmation number and Customer PO",
            width="medium"
        ),
        'customer': st.column_config.TextColumn(
            "Customer",
            help="Customer name",
            width="medium"
        ),
        'product_display': st.column_config.TextColumn(
            "Product",
            help="Product: PT Code | Name | Package Size",
            width="large"
        ),
        'brand': st.column_config.TextColumn(
            "Brand",
            help="Product brand/manufacturer"
        ),
        # Original values (before split)
        'total_revenue_usd': st.column_config.NumberColumn(
            "Total Revenue",
            help="💰 ORIGINAL invoice revenue (100% of line item)\n\nThis is the full value BEFORE applying KPI Center split.",
            format="$%.0f"
        ),
        'total_gp_usd': st.column_config.NumberColumn(
            "Total GP",
            help="📈 ORIGINAL gross profit (100% of line item)\n\nFormula: Revenue - COGS\n\nThis is the full GP BEFORE applying KPI Center split.",
            format="$%.0f"
        ),
        # Split percentage
        'split_rate_percent': st.column_config.NumberColumn(
            "Split %",
            help="👥 KPI Center credit split percentage\n\nThis KPI Center receives this % of the total revenue/GP/GP1.\n\n100% = Full credit\n50% = Shared equally with another KPI Center",
            format="%.0f%%"
        ),
        # Split values (after split)
        'sales_by_kpi_center_usd': st.column_config.NumberColumn(
            "Revenue",
            help="💰 CREDITED revenue for this KPI Center\n\n📐 Formula: Total Revenue × Split %\n\nThis is the revenue credited to this KPI Center after applying their split percentage.",
            format="$%.0f"
        ),
        'gross_profit_by_kpi_center_usd': st.column_config.NumberColumn(
            "GP",
            help="📈 CREDITED gross profit for this KPI Center\n\n📐 Formula: Total GP × Split %\n\nThis is the GP credited to this KPI Center after applying their split percentage.",
            format="$%.0f"
        ),
        'gp1_by_kpi_center_usd': st.column_config.NumberColumn(
            "GP1",
            help="📊 CREDITED GP1 for this KPI Center\n\n📐 Formula: (GP - Broker Commission × 1.2) × Split %\n\nGP1 is calculated from GP after deducting commission, then split.",
            format="$%.0f"
        ),
        'kpi_center': st.column_config.TextColumn(
            "KPI Center",
            help="KPI Center receiving credit for this transaction"
        ),
    }
    
    # Display table with column configuration
    st.dataframe(
        display_detail,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=500
    )
    
    # Legend for quick reference
    with st.expander("📖 Column Legend", expanded=False):
        st.markdown("""
        | Column | Description | Formula |
        |--------|-------------|---------|
        | **OC / PO** | Order Confirmation & Customer PO | Combined display |
        | **Product** | PT Code \\| Name \\| Package Size | Formatted product info |
        | **Total Revenue** | Original invoice amount (100%) | Full line item value |
        | **Total GP** | Original gross profit (100%) | Revenue - COGS |
        | **Split %** | Credit allocation to KPI Center | Assigned by KPI split rules |
        | **Revenue** | Credited revenue | Total Revenue × Split % |
        | **GP** | Credited gross profit | Total GP × Split % |
        | **GP1** | Credited GP1 | (GP - Broker Commission × 1.2) × Split % |
        
        > 💡 **Note:** GP1 is a calculated field (GP minus commission), so there's no "original" GP1 value.
        
        > 💡 **Tip:** Hover over column headers to see detailed tooltips.
        """)
    
    # Export filtered view button
    st.caption("💡 For full report with all data, use **Export Report** section")
    if st.button("📥 Export Filtered View", key=f"{fragment_key}_export", help="Export only the filtered transactions shown above"):
        from io import BytesIO
        
        # Prepare export data
        export_df = filtered_df.copy()
        
        # Select and rename columns for export
        export_columns = {
            'inv_date': 'Date',
            'inv_number': 'Invoice#',
            'oc_number': 'OC#',
            'customer_po_number': 'Customer PO',
            'customer': 'Customer',
            'product_pn': 'Product Code',
            'product_name': 'Product Name',
            'brand': 'Brand',
            'total_revenue_usd': 'Total Revenue (USD)',
            'total_gp_usd': 'Total GP (USD)',
            'split_rate_percent': 'Split %',
            'sales_by_kpi_center_usd': 'Revenue (Split)',
            'gross_profit_by_kpi_center_usd': 'GP (Split)',
            'gp1_by_kpi_center_usd': 'GP1 (Split)',
            'kpi_center': 'KPI Center',
        }
        
        available_export_cols = {k: v for k, v in export_columns.items() if k in export_df.columns}
        export_df = export_df[list(available_export_cols.keys())].rename(columns=available_export_cols)
        
        # Create Excel file
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='Filtered Sales', index=False)
        
        st.download_button(
            label="⬇️ Download Filtered Data",
            data=buffer.getvalue(),
            file_name=f"kpi_center_filtered_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# =============================================================================
# PIVOT ANALYSIS FRAGMENT - UPDATED v2.6.0 (SYNCED with Salesperson)
# =============================================================================

@st.fragment
def pivot_analysis_fragment(
    sales_df: pd.DataFrame,
    fragment_key: str = "kpc_pivot"
):
    """
    Configurable pivot table analysis.
    
    SYNCED with Salesperson page:
    - Same layout: 3 columns for Rows/Columns/Values
    - Same default: customer / invoice_month / Gross Profit
    - Same styling: background_gradient on Total column
    - Same month ordering: Jan → Dec
    """
    if sales_df.empty:
        st.info("No data for pivot analysis")
        return
    
    st.subheader("📊 Pivot Analysis")
    
    # Pivot configuration - 3 columns like Salesperson
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        # Row options - kpi_center instead of sales_name
        row_options = ['customer', 'brand', 'kpi_center', 'product_pn', 'legal_entity']
        row_options = [r for r in row_options if r in sales_df.columns]
        pivot_rows = st.selectbox("Rows", row_options, index=0, key=f"{fragment_key}_rows")
    
    with col_p2:
        # Column options - kpi_center instead of sales_name
        col_options = ['invoice_month', 'brand', 'customer', 'kpi_center']
        pivot_cols = st.selectbox("Columns", col_options, index=0, key=f"{fragment_key}_cols")
    
    with col_p3:
        # Value options with friendly labels - DEFAULT index=1 (Gross Profit) like SP
        value_options = ['sales_by_kpi_center_usd', 'gross_profit_by_kpi_center_usd', 'gp1_by_kpi_center_usd']
        value_options = [v for v in value_options if v in sales_df.columns]
        
        # Default to Gross Profit (index=1) if available
        default_idx = 1 if len(value_options) > 1 else 0
        
        pivot_values = st.selectbox(
            "Values", 
            value_options, 
            index=default_idx, 
            key=f"{fragment_key}_values",
            format_func=lambda x: x.replace('_by_kpi_center_usd', '').replace('_', ' ').title()
        )
    
    # Ensure month column exists
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
        
        # Add totals
        pivot_df['Total'] = pivot_df.sum(axis=1)
        pivot_df = pivot_df.sort_values('Total', ascending=False)
        
        # Reorder columns (months) - Jan → Dec like Salesperson
        if pivot_cols == 'invoice_month':
            month_cols = [m for m in MONTH_ORDER if m in pivot_df.columns]
            other_cols = [c for c in pivot_df.columns if c not in MONTH_ORDER and c != 'Total']
            pivot_df = pivot_df[month_cols + other_cols + ['Total']]
        
        # Display with same styling as Salesperson
        st.dataframe(
            pivot_df.style.format("${:,.0f}").background_gradient(cmap='Blues', subset=['Total']),
            use_container_width=True,
            height=500
        )
    else:
        st.warning("Selected columns not available in data")