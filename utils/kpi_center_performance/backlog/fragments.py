# utils/kpi_center_performance/backlog/fragments.py
"""
Streamlit Fragments for KPI Center Performance - Backlog Tab.

VERSION: 4.2.1
CHANGELOG:
- v4.2.1: BUGFIX - In-Period Backlog uses period boundary
  - Fixed: Use period boundary for ETD filter (not filter date range)
  - YTD: ETD in Jan 1 - Dec 31 (full year)
  - QTD: ETD in quarter start - quarter end
  - MTD: ETD in month start - month end
  - Added: _get_backlog_period_end() helper function
  - Updated: Labels clarify the period boundary
- v4.2.0: Tab-level wrapper with filters

Contains:
- backlog_tab_fragment: Tab-level wrapper with filters
- backlog_list_fragment: Backlog transaction list
- backlog_by_etd_fragment: Backlog by ETD month
- backlog_risk_analysis_fragment: Risk analysis
"""

import logging
import calendar
from typing import Dict, Optional
from datetime import date
import pandas as pd
import streamlit as st

from .charts import (
    build_backlog_by_month_chart,
    build_backlog_by_month_chart_multiyear,
    build_backlog_by_month_stacked,
)
from ..constants import MONTH_ORDER
from ..common.fragments import format_product_display, format_oc_po

from ..filters import (
    render_multiselect_filter,
    apply_multiselect_filter,
    render_text_search_filter,
    apply_text_search_filter,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTION - v4.2.1
# =============================================================================

def _get_backlog_period_end(filter_values: Dict) -> date:
    """
    Calculate the correct end date for In-Period Backlog ETD filter.
    
    NEW v4.2.1: Aligns with Overview tab logic.
    
    Logic:
    - Backlog = pending orders (not yet invoiced)
    - ETD = Expected delivery date (should be in future)
    - "In-Period" = orders expected to be delivered within the KPI period
    
    Period boundaries:
    - YTD: Jan 1 → Dec 31 of selected year
    - QTD: Quarter start → Quarter end
    - MTD: Month start → Month end
    - LY: Jan 1 → Dec 31 of previous year
    - Custom: Use filter dates as-is
    
    Args:
        filter_values: Dict with period_type, year, start_date, end_date
        
    Returns:
        Correct end date for backlog ETD filter
    """
    if not filter_values:
        return date.today()
    
    period_type = filter_values.get('period_type', 'YTD')
    year = filter_values.get('year', date.today().year)
    start_date = filter_values.get('start_date', date(year, 1, 1))
    end_date = filter_values.get('end_date', date.today())
    
    if period_type == 'YTD':
        # Full year
        return date(year, 12, 31)
    
    elif period_type == 'QTD':
        # End of quarter containing start_date
        quarter = (start_date.month - 1) // 3 + 1
        quarter_end_month = quarter * 3
        last_day = calendar.monthrange(year, quarter_end_month)[1]
        return date(year, quarter_end_month, last_day)
    
    elif period_type == 'MTD':
        # End of month containing start_date
        last_day = calendar.monthrange(year, start_date.month)[1]
        return date(year, start_date.month, last_day)
    
    elif period_type == 'LY':
        # Full year (previous year is already in 'year' variable)
        return date(year, 12, 31)
    
    else:  # Custom or unknown
        # Use filter end_date as-is
        return end_date


def _get_period_label(filter_values: Dict) -> str:
    """
    Get human-readable label for the period boundary.
    
    Returns label like "YTD 2026 (Jan 1 - Dec 31)" or "Q1 2026 (Jan 1 - Mar 31)"
    """
    if not filter_values:
        return "Current Period"
    
    period_type = filter_values.get('period_type', 'YTD')
    year = filter_values.get('year', date.today().year)
    start_date = filter_values.get('start_date', date(year, 1, 1))
    end_date = _get_backlog_period_end(filter_values)
    
    if period_type == 'YTD':
        return f"YTD {year} (Jan 1 - Dec 31)"
    elif period_type == 'QTD':
        quarter = (start_date.month - 1) // 3 + 1
        return f"Q{quarter} {year} ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d')})"
    elif period_type == 'MTD':
        return f"{start_date.strftime('%b')} {year} ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d')})"
    elif period_type == 'LY':
        return f"Full Year {year}"
    else:
        return f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"


# =============================================================================
# TAB-LEVEL FRAGMENT - v4.2.0
# =============================================================================

@st.fragment
def backlog_tab_fragment(
    backlog_df: pd.DataFrame,
    filter_values: Dict = None,
    key_prefix: str = "backlog_tab"
):
    """
    Fragment wrapper for Backlog tab.
    
    Includes filters + sub-tabs. Changes to filters only rerun this fragment,
    not the entire page.
    
    Args:
        backlog_df: Raw backlog DataFrame
        filter_values: Filter values from sidebar (for date range)
        key_prefix: Unique key prefix for widgets
    """
    from ..metrics import KPICenterMetrics
    
    if backlog_df.empty:
        st.info("📦 No backlog data available")
        return
    
    # Store original count
    total_count = len(backlog_df)
    
    # FIXED v4.2.1: Use period boundary for In-Period analysis (not filter date range)
    # This aligns with Overview tab's Backlog & Forecast section
    start_date = filter_values.get('start_date', date.today()) if filter_values else date.today()
    backlog_period_end = _get_backlog_period_end(filter_values)
    period_label = _get_period_label(filter_values)
    
    in_period_analysis = KPICenterMetrics.analyze_in_period_backlog(
        backlog_detail_df=backlog_df,
        start_date=start_date,
        end_date=backlog_period_end  # Use period boundary, not filter end_date
    )
    
    if in_period_analysis.get('overdue_warning'):
        st.warning(in_period_analysis['overdue_warning'])
    
    # =========================================================================
    # FILTERS ROW
    # =========================================================================
    col_bf1, col_bf2, col_bf3, col_bf4, col_bf5 = st.columns(5)
    
    with col_bf1:
        customer_options = sorted(backlog_df['customer'].dropna().unique().tolist())
        customer_filter = render_multiselect_filter(
            label="Customer",
            options=customer_options,
            key=f"{key_prefix}_customer"
        )
    
    with col_bf2:
        brand_options = sorted(backlog_df['brand'].dropna().unique().tolist()) if 'brand' in backlog_df.columns else []
        brand_filter = render_multiselect_filter(
            label="Brand",
            options=brand_options,
            key=f"{key_prefix}_brand"
        )
    
    with col_bf3:
        product_options = sorted(backlog_df['product_pn'].dropna().unique().tolist()) if 'product_pn' in backlog_df.columns else []
        product_filter = render_multiselect_filter(
            label="Product",
            options=product_options,
            key=f"{key_prefix}_product"
        )
    
    with col_bf4:
        oc_po_filter = render_text_search_filter(
            label="OC# / Customer PO",
            key=f"{key_prefix}_oc_po",
            placeholder="Search..."
        )
    
    with col_bf5:
        pending_col = 'pending_type' if 'pending_type' in backlog_df.columns else 'status'
        status_options = backlog_df[pending_col].dropna().unique().tolist() if pending_col in backlog_df.columns else []
        status_filter = render_multiselect_filter(
            label="Status",
            options=status_options,
            key=f"{key_prefix}_status"
        )
    
    # =========================================================================
    # APPLY FILTERS
    # =========================================================================
    filtered_df = backlog_df.copy()
    filtered_df = apply_multiselect_filter(filtered_df, 'customer', customer_filter)
    filtered_df = apply_multiselect_filter(filtered_df, 'brand', brand_filter)
    filtered_df = apply_multiselect_filter(filtered_df, 'product_pn', product_filter)
    filtered_df = apply_multiselect_filter(filtered_df, pending_col, status_filter)
    
    # Text search
    search_columns = ['oc_number']
    if 'customer_po_number' in filtered_df.columns:
        search_columns.append('customer_po_number')
    elif 'customer_po' in filtered_df.columns:
        search_columns.append('customer_po')
    filtered_df = apply_text_search_filter(filtered_df, columns=search_columns, search_result=oc_po_filter)
    
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
    if status_filter.is_active:
        mode = "excl" if status_filter.excluded else "incl"
        active_filters.append(f"Status: {len(status_filter.selected)} ({mode})")
    
    if active_filters:
        st.caption(f"🔍 Active filters: {' | '.join(active_filters)}")
    
    st.divider()
    
    # =========================================================================
    # SUB-TABS
    # =========================================================================
    backlog_tab1, backlog_tab2, backlog_tab3 = st.tabs([
        "📋 Backlog List",
        "📅 By ETD",
        "⚠️ Risk Analysis"
    ])
    
    current_year = filter_values.get('year', date.today().year) if filter_values else date.today().year
    
    with backlog_tab1:
        backlog_list_fragment(
            backlog_df=filtered_df,
            filter_values=filter_values,
            total_count=total_count,
            period_label=period_label  # NEW v4.2.1
        )
    
    with backlog_tab2:
        backlog_by_etd_fragment(
            backlog_detail_df=filtered_df,
            current_year=current_year,
            fragment_key=f"{key_prefix}_etd"
        )
    
    with backlog_tab3:
        backlog_risk_analysis_fragment(
            backlog_df=filtered_df,
            fragment_key=f"{key_prefix}_risk"
        )


# =============================================================================
# BACKLOG LIST FRAGMENT - SYNCED v3.0.0 with Salesperson module
# =============================================================================

@st.fragment
def backlog_list_fragment(
    backlog_df: pd.DataFrame,
    filter_values: Dict = None,
    total_backlog_df: pd.DataFrame = None,  # DEPRECATED v4.2.0 - kept for backward compatibility
    fragment_key: str = "kpc_backlog",
    total_count: int = None,
    period_label: str = None  # NEW v4.2.1: Label for period boundary
):
    """
    Backlog List fragment - displays backlog data table.
    
    UPDATED v4.2.1: Uses period boundary for In-Period analysis.
    UPDATED v4.2.0: Filters moved to tab level.
    - Receives pre-filtered data
    - Metrics calculated from filtered backlog_df
    - Formatted data table with column config
    
    Args:
        backlog_df: Pre-filtered backlog records (line items)
        filter_values: Current filter values (for date range)
        total_backlog_df: DEPRECATED - no longer used, kept for backward compatibility
        fragment_key: Unique key prefix for widgets
        total_count: Original total count before filtering (for display)
        period_label: Human-readable label for period boundary (e.g., "YTD 2026 (Jan 1 - Dec 31)")
    """
    from ..metrics import KPICenterMetrics
    
    if backlog_df.empty:
        st.info("📦 No backlog data available")
        return
    
    # Use total_count if provided, else use current df length
    original_count = total_count if total_count is not None else len(backlog_df)
    
    # =========================================================================
    # CALCULATE IN-PERIOD BACKLOG ANALYSIS
    # FIXED v4.2.1: Use period boundary (not filter date range)
    # =========================================================================
    start_date = filter_values.get('start_date', date.today()) if filter_values else date.today()
    backlog_period_end = _get_backlog_period_end(filter_values)
    
    # Generate period_label if not provided
    if not period_label:
        period_label = _get_period_label(filter_values)
    
    in_period_analysis = KPICenterMetrics.analyze_in_period_backlog(
        backlog_detail_df=backlog_df,
        start_date=start_date,
        end_date=backlog_period_end  # Use period boundary, not filter end_date
    )
    
    # =========================================================================
    # SUMMARY CARDS - 7 columns (synced with Salesperson)
    # UPDATED v4.2.1: Labels clarify period boundary
    # =========================================================================
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    # Detect column names (KPI Center uses different column names than Salesperson)
    value_col = None
    gp_col = None
    for col_name in ['backlog_by_kpi_center_usd', 'backlog_usd', 'backlog_revenue']:
        if col_name in backlog_df.columns:
            value_col = col_name
            break
    for col_name in ['backlog_gp_by_kpi_center_usd', 'backlog_gp_usd', 'backlog_gp']:
        if col_name in backlog_df.columns:
            gp_col = col_name
            break
    
    # FIXED v4.2.0: Always calculate from filtered backlog_df (not from total_backlog_df)
    total_backlog_value = backlog_df[value_col].sum() if value_col else 0
    total_backlog_gp = backlog_df[gp_col].sum() if gp_col else 0
    total_orders = backlog_df['oc_number'].nunique() if 'oc_number' in backlog_df.columns else len(backlog_df)
    total_customers = backlog_df['customer_id'].nunique() if 'customer_id' in backlog_df.columns else backlog_df['customer'].nunique()
    
    with col_s1:
        st.metric(
            "💰 Total Backlog", 
            f"${total_backlog_value:,.0f}", 
            f"{total_orders:,} orders",
            delta_color="off",
            help="Total backlog value (all pending orders)"
        )
    with col_s2:
        st.metric(
            "📈 Total GP", 
            f"${total_backlog_gp:,.0f}",
            f"{total_customers:,} customers",
            delta_color="off",
            help="Total gross profit from all backlog"
        )
    with col_s3:
        in_period_value = in_period_analysis.get('total_value', 0)
        in_period_count = in_period_analysis.get('total_count', 0)
        st.metric(
            "📅 In-Period",
            f"${in_period_value:,.0f}",
            f"{in_period_count:,} orders",
            delta_color="off",
            help=f"Backlog with ETD within {period_label}"
        )
    with col_s4:
        in_period_gp = in_period_analysis.get('total_gp', 0)
        st.metric(
            "📊 In-Period GP",
            f"${in_period_gp:,.0f}",
            delta_color="off",
            help=f"Gross profit from in-period backlog ({period_label})"
        )
    with col_s5:
        on_track_value = in_period_analysis.get('on_track_value', 0)
        on_track_count = in_period_analysis.get('on_track_count', 0)
        st.metric(
            "✅ On Track",
            f"${on_track_value:,.0f}",
            f"{on_track_count:,} orders",
            delta_color="off",
            help="In-period orders with ETD ≥ today (future delivery)"
        )
    with col_s6:
        overdue_value = in_period_analysis.get('overdue_value', 0)
        overdue_count = in_period_analysis.get('overdue_count', 0)
        st.metric(
            "⚠️ Overdue",
            f"${overdue_value:,.0f}",
            f"{overdue_count:,} orders",
            delta_color="inverse" if overdue_count > 0 else "off",
            help="In-period orders with ETD < today (past due)"
        )
    with col_s7:
        status = in_period_analysis.get('status', 'unknown')
        status_display = "HEALTHY ✅" if status == 'healthy' else "HAS OVERDUE ⚠️"
        st.metric(
            "📊 Status",
            status_display,
            help="HEALTHY = no overdue orders"
        )
    
    st.divider()
    
    # =========================================================================
    # FORMAT DISPLAY COLUMNS
    # =========================================================================
    
    # Format Product as "pt_code | Name | Package size"
    display_df = backlog_df.copy()
    display_df['product_display'] = display_df.apply(format_product_display, axis=1)
    
    # Format OC with Customer PO
    display_df['oc_po_display'] = display_df.apply(format_oc_po, axis=1)
    
    st.markdown(f"**Showing {len(display_df):,} backlog items** (of {original_count:,} total)")
    
    # =========================================================================
    # DATA TABLE WITH COLUMN CONFIG
    # =========================================================================
    
    # Determine status column
    pending_col = 'pending_type' if 'pending_type' in display_df.columns else 'status'
    
    # Determine which columns to display based on what's available
    oc_date_col = 'oc_date' if 'oc_date' in display_df.columns else None
    etd_col = 'etd' if 'etd' in display_df.columns else None
    kpi_center_col = 'kpi_center' if 'kpi_center' in display_df.columns else 'kpi_center_name'
    
    backlog_display_cols = ['oc_po_display']
    if oc_date_col:
        backlog_display_cols.append(oc_date_col)
    if etd_col:
        backlog_display_cols.append(etd_col)
    backlog_display_cols.extend(['customer', 'product_display', 'brand'])
    if value_col:
        backlog_display_cols.append(value_col)
    if gp_col:
        backlog_display_cols.append(gp_col)
    backlog_display_cols.append('days_until_etd')
    backlog_display_cols.append(pending_col)
    if kpi_center_col in display_df.columns:
        backlog_display_cols.append(kpi_center_col)
    
    available_bl_cols = [c for c in backlog_display_cols if c in display_df.columns]
    
    display_bl = display_df[available_bl_cols].head(500).copy()
    
    # Column configuration
    column_config = {
        'oc_po_display': st.column_config.TextColumn(
            "OC / PO",
            help="Order Confirmation and Customer PO",
            width="medium"
        ),
        'oc_date': st.column_config.DateColumn(
            "OC Date",
            help="Order confirmation date"
        ),
        'etd': st.column_config.DateColumn(
            "ETD",
            help="Estimated time of departure"
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
        'days_until_etd': st.column_config.NumberColumn(
            "Days to ETD",
            help="Days until ETD (negative = overdue)"
        ),
        'pending_type': st.column_config.TextColumn(
            "Status",
            help="Both Pending / Delivery Pending / Invoice Pending"
        ),
        'status': st.column_config.TextColumn(
            "Status",
            help="Order status"
        ),
        'kpi_center': st.column_config.TextColumn(
            "KPI Center",
            help="KPI Center receiving credit"
        ),
        'kpi_center_name': st.column_config.TextColumn(
            "KPI Center",
            help="KPI Center receiving credit"
        ),
    }
    
    # Add dynamic column configs for value columns
    if value_col:
        column_config[value_col] = st.column_config.NumberColumn(
            "Amount",
            help="Backlog amount (split-adjusted)",
            format="$%.0f"
        )
    if gp_col:
        column_config[gp_col] = st.column_config.NumberColumn(
            "GP",
            help="Backlog gross profit (split-adjusted)",
            format="$%.0f"
        )
    
    st.dataframe(
        display_bl,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=400
    )


# =============================================================================
# BACKLOG BY ETD FRAGMENT - NEW v3.0.0 (synced with Salesperson)
# FIX v3.0.1: Use backlog_detail_df and aggregate in fragment to fix filter bug
# =============================================================================

@st.fragment
def backlog_by_etd_fragment(
    backlog_detail_df: pd.DataFrame,
    current_year: int = None,
    fragment_key: str = "kpc_backlog_etd"
):
    """
    Fragment for Backlog by ETD Month with multi-year support.
    
    SYNCED v3.0.0 with Salesperson module:
    - Timeline view: Chronological across all years
    - Stacked by Month: Compare same months across years
    - Single Year: One year only with selector
    
    FIX v3.0.1: Changed from backlog_by_month_df to backlog_detail_df
    - Previous: Used pre-aggregated data that wasn't filtered by KPI Center
    - Now: Uses detail data (already filtered) and aggregates in fragment
    
    Args:
        backlog_detail_df: Detailed backlog records (already filtered by KPI Center)
        current_year: Current filter year (for Single Year default)
        fragment_key: Unique key prefix for widgets
    """
    from datetime import datetime
    
    st.markdown("#### 📅 Backlog by ETD Month")
    
    if backlog_detail_df.empty:
        st.info("No backlog data available")
        return
    
    # =========================================================================
    # AGGREGATE FROM DETAIL DATA (FIX for filter bug)
    # =========================================================================
    df = backlog_detail_df.copy()
    
    # Ensure ETD is datetime and extract year/month
    if 'etd' not in df.columns:
        st.warning("Missing ETD column in backlog data")
        return
    
    df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
    df = df.dropna(subset=['etd'])
    
    if df.empty:
        st.info("No valid ETD dates in backlog")
        return
    
    df['etd_year'] = df['etd'].dt.year
    df['etd_month'] = df['etd'].dt.strftime('%b')
    
    # Detect value columns
    value_col = None
    gp_col_detail = None
    for col_name in ['backlog_by_kpi_center_usd', 'backlog_usd', 'backlog_revenue', 'backlog_sales_by_split_usd']:
        if col_name in df.columns:
            value_col = col_name
            break
    for col_name in ['backlog_gp_by_kpi_center_usd', 'backlog_gp_usd', 'backlog_gp', 'backlog_gp_by_split_usd']:
        if col_name in df.columns:
            gp_col_detail = col_name
            break
    
    if not value_col:
        st.warning("Missing backlog value column")
        return
    
    # Aggregate by year and month
    agg_dict = {value_col: 'sum'}
    if gp_col_detail:
        agg_dict[gp_col_detail] = 'sum'
    if 'oc_number' in df.columns:
        agg_dict['oc_number'] = pd.Series.nunique
    
    df_years = df.groupby(['etd_year', 'etd_month']).agg(agg_dict).reset_index()
    
    # Rename columns for consistency
    df_years = df_years.rename(columns={
        value_col: 'backlog_revenue',
        gp_col_detail: 'backlog_gp' if gp_col_detail else None,
        'oc_number': 'order_count'
    })
    df_years = df_years.dropna(axis=1, how='all')  # Remove None columns
    
    # =========================================================================
    # REST OF FRAGMENT LOGIC
    # =========================================================================
    
    unique_years = sorted(df_years['etd_year'].unique())
    unique_years = [y for y in unique_years if y > 2000]  # Filter valid years
    
    if not unique_years:
        st.info("No valid ETD dates in backlog")
        return
    
    # Show year info if multi-year
    if len(unique_years) > 1:
        year_list = ', '.join(map(str, unique_years))
        st.info(f"📆 Backlog spans {len(unique_years)} years: {year_list}")
    
    # View mode selector
    col_view, col_spacer = st.columns([2, 4])
    with col_view:
        view_mode = st.radio(
            "View Mode",
            options=["Timeline", "Stacked by Month", "Single Year"],
            horizontal=True,
            key=f"{fragment_key}_view_mode",
            help="Timeline: Chronological view | Stacked: Compare months across years | Single Year: One year only"
        )
    
    # Column names after aggregation
    revenue_col = 'backlog_revenue'
    gp_col = 'backlog_gp' if 'backlog_gp' in df_years.columns else None
    order_col = 'order_count' if 'order_count' in df_years.columns else None
    
    if view_mode == "Timeline":
        # =============================================================
        # TIMELINE VIEW - Chronological across all years
        # =============================================================
        
        # Create year_month label for timeline
        df_timeline = df_years.copy()
        df_timeline['year_month'] = df_timeline['etd_month'] + "'" + df_timeline['etd_year'].astype(str).str[-2:]
        
        # Sort chronologically
        month_to_num = {m: i for i, m in enumerate(MONTH_ORDER)}
        df_timeline['sort_key'] = df_timeline['etd_year'] * 100 + df_timeline['etd_month'].map(month_to_num)
        df_timeline = df_timeline.sort_values('sort_key')
        
        if revenue_col and df_timeline[revenue_col].sum() > 0:
            # Build chart
            chart = build_backlog_by_month_chart_multiyear(
                monthly_df=df_timeline,
                revenue_col=revenue_col,
                title=""
            )
            st.altair_chart(chart, use_container_width=True)
            
            # Data table
            display_cols = ['year_month', 'etd_year']
            if revenue_col:
                display_cols.append(revenue_col)
            if gp_col:
                display_cols.append(gp_col)
            if order_col in df_timeline.columns:
                display_cols.append(order_col)
            
            display_cols = [c for c in display_cols if c in df_timeline.columns]
            
            format_dict = {}
            if revenue_col:
                format_dict[revenue_col] = '${:,.0f}'
            if gp_col:
                format_dict[gp_col] = '${:,.0f}'
            
            st.dataframe(
                df_timeline[display_cols].style.format(format_dict),
                use_container_width=True,
                hide_index=True,
                height=400
            )
        else:
            st.info("No backlog data to display")
    
    elif view_mode == "Stacked by Month":
        # =============================================================
        # STACKED VIEW - Compare same months across years
        # =============================================================
        
        if revenue_col and df_years[revenue_col].sum() > 0:
            chart = build_backlog_by_month_stacked(
                monthly_df=df_years,
                revenue_col=revenue_col,
                title=""
            )
            st.altair_chart(chart, use_container_width=True)
            
            # Pivot table: months as rows, years as columns
            pivot_df = df_years.pivot_table(
                index='etd_month',
                columns='etd_year',
                values=revenue_col,
                aggfunc='sum',
                fill_value=0
            )
            # Reorder months
            pivot_df = pivot_df.reindex(MONTH_ORDER)
            pivot_df = pivot_df.dropna(how='all')
            
            # Add total column
            pivot_df['Total'] = pivot_df.sum(axis=1)
            
            st.dataframe(
                pivot_df.style.format('${:,.0f}'),
                use_container_width=True
            )
        else:
            st.info("No backlog data to display")
    
    else:  # Single Year
        # =============================================================
        # SINGLE YEAR VIEW - Original behavior with year selector
        # =============================================================
        col_year, _ = st.columns([2, 4])
        with col_year:
            # Default to current_year if available, else first year
            default_idx = 0
            if current_year and current_year in unique_years:
                default_idx = unique_years.index(current_year)
            elif unique_years:
                # Default to latest year
                default_idx = len(unique_years) - 1
            
            selected_year = st.selectbox(
                "Select Year",
                options=unique_years,
                index=default_idx,
                key=f"{fragment_key}_year_select"
            )
        
        year_data = df_years[df_years['etd_year'] == selected_year].copy()
        
        if not year_data.empty and revenue_col and year_data[revenue_col].sum() > 0:
            # Sort by month order
            month_to_num = {m: i for i, m in enumerate(MONTH_ORDER)}
            year_data['month_order'] = year_data['etd_month'].map(month_to_num)
            year_data = year_data.sort_values('month_order')
            
            chart = build_backlog_by_month_chart(
                monthly_df=year_data,
                revenue_col=revenue_col,
                gp_col=gp_col,
                month_col='etd_month',
                title=f"Backlog by ETD Month - {selected_year}"
            )
            st.altair_chart(chart, use_container_width=True)
            
            # Monthly table
            display_cols = ['etd_month']
            if revenue_col:
                display_cols.append(revenue_col)
            if gp_col:
                display_cols.append(gp_col)
            if order_col in year_data.columns:
                display_cols.append(order_col)
            
            display_cols = [c for c in display_cols if c in year_data.columns]
            
            format_dict = {}
            if revenue_col:
                format_dict[revenue_col] = '${:,.0f}'
            if gp_col:
                format_dict[gp_col] = '${:,.0f}'
            
            st.dataframe(
                year_data[display_cols].style.format(format_dict),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info(f"No backlog data for {selected_year}")


# =============================================================================
# BACKLOG RISK ANALYSIS FRAGMENT - NEW v3.0.0 (synced with Salesperson)
# =============================================================================

@st.fragment
def backlog_risk_analysis_fragment(
    backlog_df: pd.DataFrame,
    fragment_key: str = "kpc_backlog_risk"
):
    """
    Fragment for Backlog Risk Analysis.
    
    SYNCED v3.0.0 with Salesperson module:
    - 4 risk category cards: Overdue, This Week, This Month, On Track
    - Overdue orders detail table
    
    Args:
        backlog_df: Detailed backlog records with days_until_etd column
        fragment_key: Unique key prefix for widgets
    """
    st.markdown("#### ⚠️ Backlog Risk Analysis")
    
    if backlog_df.empty:
        st.info("No backlog data for risk analysis")
        return
    
    # Ensure days_until_etd is numeric
    backlog_risk = backlog_df.copy()
    if 'days_until_etd' not in backlog_risk.columns:
        st.warning("Missing days_until_etd column for risk analysis")
        return
    
    backlog_risk['days_until_etd'] = pd.to_numeric(
        backlog_risk['days_until_etd'], errors='coerce'
    )
    
    # Detect value column
    value_col = None
    gp_col = None
    for col in ['backlog_by_kpi_center_usd', 'backlog_usd', 'backlog_revenue']:
        if col in backlog_risk.columns:
            value_col = col
            break
    for col in ['backlog_gp_by_kpi_center_usd', 'backlog_gp_usd', 'backlog_gp']:
        if col in backlog_risk.columns:
            gp_col = col
            break
    
    if not value_col:
        st.warning("Missing backlog value column")
        return
    
    # Categorize by risk level
    overdue = backlog_risk[backlog_risk['days_until_etd'] < 0]
    this_week = backlog_risk[
        (backlog_risk['days_until_etd'] >= 0) & 
        (backlog_risk['days_until_etd'] <= 7)
    ]
    this_month = backlog_risk[
        (backlog_risk['days_until_etd'] > 7) & 
        (backlog_risk['days_until_etd'] <= 30)
    ]
    on_track = backlog_risk[backlog_risk['days_until_etd'] > 30]
    
    # =========================================================================
    # RISK SUMMARY CARDS - 4 columns
    # =========================================================================
    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    
    with col_r1:
        st.metric(
            "🔴 Overdue",
            f"${overdue[value_col].sum():,.0f}",
            delta=f"{len(overdue)} orders",
            delta_color="inverse"
        )
    
    with col_r2:
        st.metric(
            "🟠 This Week",
            f"${this_week[value_col].sum():,.0f}",
            delta=f"{len(this_week)} orders",
            delta_color="off"
        )
    
    with col_r3:
        st.metric(
            "🟡 This Month",
            f"${this_month[value_col].sum():,.0f}",
            delta=f"{len(this_month)} orders",
            delta_color="off"
        )
    
    with col_r4:
        st.metric(
            "🟢 On Track",
            f"${on_track[value_col].sum():,.0f}",
            delta=f"{len(on_track)} orders",
            delta_color="off"
        )
    
    st.divider()
    
    # =========================================================================
    # OVERDUE ORDERS TABLE
    # =========================================================================
    if not overdue.empty:
        st.markdown("##### 🔴 Overdue Orders (ETD Passed)")
        
        # Sort by most overdue first
        overdue_sorted = overdue.sort_values('days_until_etd', ascending=True)
        
        # Calculate days overdue (positive number)
        overdue_sorted['days_overdue'] = -overdue_sorted['days_until_etd']
        
        # Determine display columns
        kpi_center_col = 'kpi_center' if 'kpi_center' in overdue_sorted.columns else 'kpi_center_name'
        oc_col = 'oc_number' if 'oc_number' in overdue_sorted.columns else None
        
        display_cols = []
        if oc_col:
            display_cols.append(oc_col)
        display_cols.extend(['etd', 'customer', 'product_pn', 'brand', value_col])
        if gp_col:
            display_cols.append(gp_col)
        display_cols.append('days_overdue')
        if 'pending_type' in overdue_sorted.columns:
            display_cols.append('pending_type')
        elif 'status' in overdue_sorted.columns:
            display_cols.append('status')
        if kpi_center_col in overdue_sorted.columns:
            display_cols.append(kpi_center_col)
        
        available_cols = [c for c in display_cols if c in overdue_sorted.columns]
        
        column_config = {
            'oc_number': st.column_config.TextColumn("OC / PO", width="medium"),
            'etd': st.column_config.DateColumn("ETD"),
            'customer': st.column_config.TextColumn("Customer", width="medium"),
            'product_pn': st.column_config.TextColumn("Product", width="large"),
            'brand': "Brand",
            'days_overdue': st.column_config.NumberColumn("Days Overdue"),
            'pending_type': "Status",
            'status': "Status",
            'kpi_center': "KPI Center",
            'kpi_center_name': "KPI Center",
        }
        
        # Add value column config
        column_config[value_col] = st.column_config.NumberColumn("Amount", format="$%.0f")
        if gp_col:
            column_config[gp_col] = st.column_config.NumberColumn("GP", format="$%.0f")
        
        st.dataframe(
            overdue_sorted[available_cols].head(100),
            column_config=column_config,
            use_container_width=True,
            hide_index=True,
            height=400
        )
    else:
        st.success("✅ No overdue orders - all backlog is on track!")