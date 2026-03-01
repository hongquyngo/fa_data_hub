# utils/legal_entity_performance/backlog/fragments.py
"""
Streamlit Fragments for Legal Entity Performance - Backlog Tab.
Adapted from kpi_center_performance/backlog/fragments.py

VERSION: 2.0.0
Contains:
- backlog_tab_fragment: Tab-level wrapper with filters + 3 sub-tabs
- backlog_list_fragment: Backlog transaction list with 7 metric cards
- backlog_by_etd_fragment: Backlog by ETD month (Timeline/Stacked/Single Year)
- backlog_risk_analysis_fragment: Risk analysis (Overdue/This Week/This Month/On Track)
"""

import logging
import calendar
from typing import Dict
from datetime import date
import pandas as pd
import streamlit as st

from .charts import (
    build_backlog_by_month_chart,
    build_backlog_by_month_chart_multiyear,
    build_backlog_by_month_stacked,
)
from ..constants import MONTH_ORDER

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def _format_product_display(row) -> str:
    parts = []
    if pd.notna(row.get('pt_code')) and row.get('pt_code'):
        parts.append(str(row['pt_code']))
    if pd.notna(row.get('product_pn')) and row.get('product_pn'):
        parts.append(str(row['product_pn']))
    if pd.notna(row.get('package_size')) and row.get('package_size'):
        parts.append(str(row['package_size']))
    return ' | '.join(parts) if parts else ''


def _format_oc_po(row) -> str:
    oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
    po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
    if oc and po:
        return f"{oc}\n(PO: {po})"
    return oc or po or ''


def _get_backlog_period_end(filter_values: Dict) -> date:
    """Calculate correct end date for In-Period Backlog ETD filter."""
    if not filter_values:
        return date.today()
    
    period_type = filter_values.get('period_type', 'YTD')
    year = filter_values.get('year', date.today().year)
    start_date = filter_values.get('start_date', date(year, 1, 1))
    end_date = filter_values.get('end_date', date.today())
    
    if period_type == 'YTD':
        return date(year, 12, 31)
    elif period_type == 'QTD':
        quarter = (start_date.month - 1) // 3 + 1
        quarter_end_month = quarter * 3
        last_day = calendar.monthrange(year, quarter_end_month)[1]
        return date(year, quarter_end_month, last_day)
    elif period_type == 'MTD':
        last_day = calendar.monthrange(year, start_date.month)[1]
        return date(year, start_date.month, last_day)
    elif period_type == 'LY':
        return date(year, 12, 31)
    else:
        return end_date


def _get_period_label(filter_values: Dict) -> str:
    """Human-readable label for period boundary."""
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
        return f"{start_date.strftime('%b')} {year}"
    elif period_type == 'LY':
        return f"Full Year {year}"
    else:
        return f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"


def _detect_value_columns(df: pd.DataFrame):
    """Detect backlog value and GP columns from available columns."""
    value_col = None
    gp_col = None
    for col in ['total_backlog_amount_usd', 'outstanding_amount_usd', 'max_pending_amount_usd',
                 'backlog_usd', 'backlog_revenue']:
        if col in df.columns:
            value_col = col
            break
    for col in ['outstanding_gross_profit_usd', 'pending_delivery_gross_profit_usd',
                 'backlog_gp_usd', 'backlog_gp']:
        if col in df.columns:
            gp_col = col
            break
    return value_col, gp_col


def _analyze_in_period(backlog_df: pd.DataFrame, start_date, end_date):
    """Analyze in-period backlog metrics."""
    result = {
        'total_value': 0, 'total_gp': 0, 'total_count': 0,
        'on_track_value': 0, 'on_track_count': 0,
        'overdue_value': 0, 'overdue_count': 0,
        'status': 'healthy', 'overdue_warning': None,
    }
    
    if backlog_df.empty or 'etd' not in backlog_df.columns:
        return result
    
    df = backlog_df.copy()
    df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
    
    value_col, gp_col = _detect_value_columns(df)
    if not value_col:
        return result
    
    # Filter in-period
    mask = (df['etd'] >= pd.Timestamp(start_date)) & (df['etd'] <= pd.Timestamp(end_date))
    in_period = df[mask]
    
    result['total_value'] = in_period[value_col].sum() if not in_period.empty else 0
    result['total_gp'] = in_period[gp_col].sum() if gp_col and not in_period.empty else 0
    result['total_count'] = len(in_period)
    
    today = pd.Timestamp(date.today())
    overdue = in_period[in_period['etd'] < today]
    on_track = in_period[in_period['etd'] >= today]
    
    result['overdue_value'] = overdue[value_col].sum() if not overdue.empty else 0
    result['overdue_count'] = len(overdue)
    result['on_track_value'] = on_track[value_col].sum() if not on_track.empty else 0
    result['on_track_count'] = len(on_track)
    
    if result['overdue_count'] > 0:
        result['status'] = 'has_overdue'
        result['overdue_warning'] = (
            f"⚠️ {result['overdue_count']} orders past ETD. "
            f"Value: ${result['overdue_value']:,.0f}"
        )
    
    return result


# =============================================================================
# TAB-LEVEL FRAGMENT
# =============================================================================

@st.fragment
def backlog_tab_fragment(
    backlog_df: pd.DataFrame,
    filter_values: Dict = None,
    key_prefix: str = "le_backlog_tab"
):
    """
    Fragment wrapper for Backlog tab with filters + 3 sub-tabs.
    """
    if backlog_df.empty:
        st.info("📦 No backlog data available")
        return
    
    total_count = len(backlog_df)
    
    start_date = filter_values.get('start_date', date.today()) if filter_values else date.today()
    backlog_period_end = _get_backlog_period_end(filter_values)
    period_label = _get_period_label(filter_values)
    
    in_period_analysis = _analyze_in_period(backlog_df, start_date, backlog_period_end)
    if in_period_analysis.get('overdue_warning'):
        st.warning(in_period_analysis['overdue_warning'])
    
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
        customer_options = sorted(backlog_df['customer'].dropna().unique().tolist())
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
        brand_options = sorted(backlog_df['brand'].dropna().unique().tolist()) if 'brand' in backlog_df.columns else []
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
        product_options = sorted(backlog_df['product_pn'].dropna().unique().tolist()) if 'product_pn' in backlog_df.columns else []
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
            key=f"{key_prefix}_oc_search", placeholder="Search...",
            label_visibility="collapsed"
        )
    with col_f5:
        _lbl5, _excl5 = st.columns([3, 1])
        with _lbl5:
            st.markdown("**Status**")
        with _excl5:
            excl_status = st.checkbox("Excl", key=f"{key_prefix}_excl_status")
        pending_col = 'pending_type' if 'pending_type' in backlog_df.columns else 'status'
        status_options = backlog_df[pending_col].dropna().unique().tolist() if pending_col in backlog_df.columns else []
        selected_statuses = st.multiselect(
            "Status", status_options,
            key=f"{key_prefix}_status", placeholder="Choose options",
            label_visibility="collapsed"
        )
    
    # =========================================================================
    # APPLY FILTERS (with Excl logic)
    # =========================================================================
    filtered_df = backlog_df.copy()
    if selected_customers:
        if excl_customer:
            filtered_df = filtered_df[~filtered_df['customer'].isin(selected_customers)]
        else:
            filtered_df = filtered_df[filtered_df['customer'].isin(selected_customers)]
    if selected_brands and 'brand' in filtered_df.columns:
        if excl_brand:
            filtered_df = filtered_df[~filtered_df['brand'].isin(selected_brands)]
        else:
            filtered_df = filtered_df[filtered_df['brand'].isin(selected_brands)]
    if selected_products and 'product_pn' in filtered_df.columns:
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
    if selected_statuses and pending_col in filtered_df.columns:
        if excl_status:
            filtered_df = filtered_df[~filtered_df[pending_col].isin(selected_statuses)]
        else:
            filtered_df = filtered_df[filtered_df[pending_col].isin(selected_statuses)]
    
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
    if selected_statuses:
        mode = "excl" if excl_status else "incl"
        active_filters.append(f"Status: {len(selected_statuses)} ({mode})")
    if active_filters:
        st.caption(f"🔍 Active filters: {' | '.join(active_filters)}")
    
    st.divider()
    
    # =========================================================================
    # SUB-TABS
    # =========================================================================
    current_year = filter_values.get('year', date.today().year) if filter_values else date.today().year
    
    bt1, bt2, bt3 = st.tabs(["📋 Backlog List", "📅 By ETD", "⚠️ Risk Analysis"])
    
    with bt1:
        backlog_list_fragment(
            backlog_df=filtered_df,
            filter_values=filter_values,
            total_count=total_count,
            period_label=period_label
        )
    with bt2:
        backlog_by_etd_fragment(
            backlog_detail_df=filtered_df,
            current_year=current_year,
            fragment_key=f"{key_prefix}_etd"
        )
    with bt3:
        backlog_risk_analysis_fragment(
            backlog_df=filtered_df,
            fragment_key=f"{key_prefix}_risk"
        )


# =============================================================================
# BACKLOG LIST FRAGMENT
# =============================================================================

def backlog_list_fragment(
    backlog_df: pd.DataFrame,
    filter_values: Dict = None,
    fragment_key: str = "le_backlog",
    total_count: int = None,
    period_label: str = None,
):
    """Backlog transaction list with 7 summary metric cards."""
    if backlog_df.empty:
        st.info("📦 No backlog data available")
        return
    
    original_count = total_count if total_count is not None else len(backlog_df)
    
    # In-period analysis
    start_date = filter_values.get('start_date', date.today()) if filter_values else date.today()
    backlog_period_end = _get_backlog_period_end(filter_values)
    if not period_label:
        period_label = _get_period_label(filter_values)
    
    in_period = _analyze_in_period(backlog_df, start_date, backlog_period_end)
    
    value_col, gp_col = _detect_value_columns(backlog_df)
    
    # =========================================================================
    # 7 METRIC CARDS (synced with KPI center)
    # =========================================================================
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    total_value = backlog_df[value_col].sum() if value_col else 0
    total_gp = backlog_df[gp_col].sum() if gp_col else 0
    total_orders = backlog_df['oc_number'].nunique() if 'oc_number' in backlog_df.columns else len(backlog_df)
    total_customers = backlog_df['customer_id'].nunique() if 'customer_id' in backlog_df.columns else (
        backlog_df['customer'].nunique() if 'customer' in backlog_df.columns else 0
    )
    
    with col_s1:
        st.metric("💰 Total Backlog", f"${total_value:,.0f}",
                   f"{total_orders:,} orders", delta_color="off")
    with col_s2:
        st.metric("📈 Total GP", f"${total_gp:,.0f}",
                   f"{total_customers:,} customers", delta_color="off")
    with col_s3:
        st.metric("📅 In-Period", f"${in_period['total_value']:,.0f}",
                   f"{in_period['total_count']:,} orders", delta_color="off",
                   help=f"Backlog with ETD within {period_label}")
    with col_s4:
        st.metric("📊 In-Period GP", f"${in_period['total_gp']:,.0f}",
                   delta_color="off", help=f"GP from in-period backlog ({period_label})")
    with col_s5:
        st.metric("✅ On Track", f"${in_period['on_track_value']:,.0f}",
                   f"{in_period['on_track_count']:,} orders", delta_color="off",
                   help="In-period orders with ETD ≥ today")
    with col_s6:
        st.metric("⚠️ Overdue", f"${in_period['overdue_value']:,.0f}",
                   f"{in_period['overdue_count']:,} orders",
                   delta_color="inverse" if in_period['overdue_count'] > 0 else "off",
                   help="In-period orders with ETD < today")
    with col_s7:
        status_display = "HEALTHY ✅" if in_period['status'] == 'healthy' else "HAS OVERDUE ⚠️"
        st.metric("📊 Status", status_display)
    
    st.divider()
    
    # =========================================================================
    # DATA TABLE
    # =========================================================================
    display_df = backlog_df.copy()
    display_df['product_display'] = display_df.apply(_format_product_display, axis=1)
    if 'oc_number' in display_df.columns:
        display_df['oc_po_display'] = display_df.apply(_format_oc_po, axis=1)
    
    st.markdown(f"**Showing {len(display_df):,} backlog items** (of {original_count:,} total)")
    
    pending_col = 'pending_type' if 'pending_type' in display_df.columns else 'status'
    
    display_columns = ['oc_po_display', 'oc_date', 'etd',
                        'legal_entity', 'customer', 'product_display', 'brand']
    if value_col:
        display_columns.append(value_col)
    if gp_col:
        display_columns.append(gp_col)
    display_columns.extend(['days_until_etd', pending_col])
    
    available_cols = [c for c in display_columns if c in display_df.columns]
    display_bl = display_df[available_cols].head(500).copy()
    
    # Pre-format currency columns
    if value_col and value_col in display_bl.columns:
        display_bl[value_col] = display_bl[value_col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
    if gp_col and gp_col in display_bl.columns:
        display_bl[gp_col] = display_bl[gp_col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
    
    column_config = {
        'oc_po_display': st.column_config.TextColumn("OC / PO", width="medium"),
        'oc_date': st.column_config.DateColumn("OC Date"),
        'etd': st.column_config.DateColumn("ETD"),
        'legal_entity': st.column_config.TextColumn("Entity"),
        'customer': st.column_config.TextColumn("Customer", width="medium"),
        'product_display': st.column_config.TextColumn("Product", width="large"),
        'brand': "Brand",
        'days_until_etd': st.column_config.NumberColumn("Days to ETD"),
        'pending_type': "Status",
        'status': "Status",
    }
    if value_col:
        column_config[value_col] = st.column_config.TextColumn("Amount")
    if gp_col:
        column_config[gp_col] = st.column_config.TextColumn("GP")
    
    st.dataframe(
        display_bl,
        column_config=column_config,
        width="stretch",
        hide_index=True,
        height=400
    )


# =============================================================================
# BACKLOG BY ETD FRAGMENT (Timeline / Stacked / Single Year)
# =============================================================================

def backlog_by_etd_fragment(
    backlog_detail_df: pd.DataFrame,
    current_year: int = None,
    fragment_key: str = "le_backlog_etd"
):
    """Backlog by ETD month with multi-year support."""
    st.markdown("#### 📅 Backlog by ETD Month")
    
    if backlog_detail_df.empty:
        st.info("No backlog data available")
        return
    
    df = backlog_detail_df.copy()
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
    
    value_col, gp_col = _detect_value_columns(df)
    if not value_col:
        st.warning("Missing backlog value column")
        return
    
    # Aggregate by year and month
    agg_dict = {value_col: 'sum'}
    if gp_col:
        agg_dict[gp_col] = 'sum'
    if 'oc_number' in df.columns:
        agg_dict['oc_number'] = pd.Series.nunique
    
    df_years = df.groupby(['etd_year', 'etd_month']).agg(agg_dict).reset_index()
    rename_map = {value_col: 'backlog_revenue'}
    if gp_col:
        rename_map[gp_col] = 'backlog_gp'
    if 'oc_number' in agg_dict:
        rename_map['oc_number'] = 'order_count'
    df_years = df_years.rename(columns=rename_map)
    
    unique_years = sorted([y for y in df_years['etd_year'].unique() if y > 2000])
    if not unique_years:
        st.info("No valid ETD dates in backlog")
        return
    
    if len(unique_years) > 1:
        st.info(f"📆 Backlog spans {len(unique_years)} years: {', '.join(map(str, unique_years))}")
    
    # View mode
    col_view, _ = st.columns([2, 4])
    with col_view:
        view_mode = st.radio(
            "View Mode",
            options=["Timeline", "Stacked by Month", "Single Year"],
            horizontal=True,
            key=f"{fragment_key}_view_mode"
        )
    
    revenue_col = 'backlog_revenue'
    gp_agg_col = 'backlog_gp' if 'backlog_gp' in df_years.columns else None
    
    if view_mode == "Timeline":
        df_timeline = df_years.copy()
        df_timeline['year_month'] = df_timeline['etd_month'] + "'" + df_timeline['etd_year'].astype(str).str[-2:]
        month_to_num = {m: i for i, m in enumerate(MONTH_ORDER)}
        df_timeline['sort_key'] = df_timeline['etd_year'] * 100 + df_timeline['etd_month'].map(month_to_num)
        df_timeline = df_timeline.sort_values('sort_key')
        
        if df_timeline[revenue_col].sum() > 0:
            chart = build_backlog_by_month_chart_multiyear(df_timeline, revenue_col, title="")
            st.altair_chart(chart, width="stretch")
            
            display_cols = [c for c in ['year_month', 'etd_year', revenue_col, gp_agg_col, 'order_count']
                            if c and c in df_timeline.columns]
            fmt = {revenue_col: '${:,.0f}'}
            if gp_agg_col:
                fmt[gp_agg_col] = '${:,.0f}'
            st.dataframe(df_timeline[display_cols].style.format(fmt),
                          width="stretch", hide_index=True, height=400)
    
    elif view_mode == "Stacked by Month":
        if df_years[revenue_col].sum() > 0:
            chart = build_backlog_by_month_stacked(df_years, revenue_col, title="")
            st.altair_chart(chart, width="stretch")
            
            pivot_df = df_years.pivot_table(
                index='etd_month', columns='etd_year',
                values=revenue_col, aggfunc='sum', fill_value=0
            )
            pivot_df = pivot_df.reindex(MONTH_ORDER).dropna(how='all')
            pivot_df['Total'] = pivot_df.sum(axis=1)
            st.dataframe(pivot_df.style.format('${:,.0f}'), width="stretch")
    
    else:  # Single Year
        col_year, _ = st.columns([2, 4])
        with col_year:
            default_idx = unique_years.index(current_year) if current_year in unique_years else len(unique_years) - 1
            selected_year = st.selectbox(
                "Select Year", options=unique_years, index=default_idx,
                key=f"{fragment_key}_year_select"
            )
        
        year_data = df_years[df_years['etd_year'] == selected_year].copy()
        if not year_data.empty and year_data[revenue_col].sum() > 0:
            month_to_num = {m: i for i, m in enumerate(MONTH_ORDER)}
            year_data['month_order'] = year_data['etd_month'].map(month_to_num)
            year_data = year_data.sort_values('month_order')
            
            chart = build_backlog_by_month_chart(
                year_data, revenue_col, gp_agg_col, 'etd_month',
                title=f"Backlog by ETD Month - {selected_year}"
            )
            st.altair_chart(chart, width="stretch")
            
            display_cols = [c for c in ['etd_month', revenue_col, gp_agg_col, 'order_count']
                            if c and c in year_data.columns]
            fmt = {revenue_col: '${:,.0f}'}
            if gp_agg_col:
                fmt[gp_agg_col] = '${:,.0f}'
            st.dataframe(year_data[display_cols].style.format(fmt),
                          width="stretch", hide_index=True)
        else:
            st.info(f"No backlog data for {selected_year}")


# =============================================================================
# BACKLOG RISK ANALYSIS FRAGMENT
# =============================================================================

def backlog_risk_analysis_fragment(
    backlog_df: pd.DataFrame,
    fragment_key: str = "le_backlog_risk"
):
    """Risk analysis: Overdue / This Week / This Month / On Track."""
    st.markdown("#### ⚠️ Backlog Risk Analysis")
    
    if backlog_df.empty:
        st.info("No backlog data for risk analysis")
        return
    
    df = backlog_df.copy()
    if 'days_until_etd' not in df.columns:
        st.warning("Missing days_until_etd column for risk analysis")
        return
    
    df['days_until_etd'] = pd.to_numeric(df['days_until_etd'], errors='coerce')
    
    value_col, gp_col = _detect_value_columns(df)
    if not value_col:
        st.warning("Missing backlog value column")
        return
    
    overdue = df[df['days_until_etd'] < 0]
    this_week = df[(df['days_until_etd'] >= 0) & (df['days_until_etd'] <= 7)]
    this_month = df[(df['days_until_etd'] > 7) & (df['days_until_etd'] <= 30)]
    on_track = df[df['days_until_etd'] > 30]
    
    # 4 risk cards
    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    with col_r1:
        st.metric("🔴 Overdue", f"${overdue[value_col].sum():,.0f}",
                   delta=f"{len(overdue)} orders", delta_color="inverse")
    with col_r2:
        st.metric("🟠 This Week", f"${this_week[value_col].sum():,.0f}",
                   delta=f"{len(this_week)} orders", delta_color="off")
    with col_r3:
        st.metric("🟡 This Month", f"${this_month[value_col].sum():,.0f}",
                   delta=f"{len(this_month)} orders", delta_color="off")
    with col_r4:
        st.metric("🟢 On Track", f"${on_track[value_col].sum():,.0f}",
                   delta=f"{len(on_track)} orders", delta_color="off")
    
    st.divider()
    
    # Overdue detail table
    if not overdue.empty:
        st.markdown("##### 🔴 Overdue Orders (ETD Passed)")
        overdue_sorted = overdue.sort_values('days_until_etd', ascending=True).copy()
        overdue_sorted['days_overdue'] = -overdue_sorted['days_until_etd']
        
        display_cols = ['oc_number', 'etd', 'legal_entity', 'customer',
                         'product_pn', 'brand', value_col, 'days_overdue']
        if gp_col:
            display_cols.insert(-1, gp_col)
        if 'pending_type' in overdue_sorted.columns:
            display_cols.append('pending_type')
        elif 'status' in overdue_sorted.columns:
            display_cols.append('status')
        
        available_cols = [c for c in display_cols if c in overdue_sorted.columns]
        
        # Pre-format currency columns
        display_overdue = overdue_sorted[available_cols].head(100).copy()
        if value_col and value_col in display_overdue.columns:
            display_overdue[value_col] = display_overdue[value_col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
        if gp_col and gp_col in display_overdue.columns:
            display_overdue[gp_col] = display_overdue[gp_col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
        
        column_config = {
            'oc_number': "OC#",
            'etd': st.column_config.DateColumn("ETD"),
            'legal_entity': "Entity",
            'customer': st.column_config.TextColumn("Customer", width="medium"),
            'product_pn': st.column_config.TextColumn("Product", width="large"),
            'brand': "Brand",
            'days_overdue': st.column_config.NumberColumn("Days Overdue"),
            'pending_type': "Status", 'status': "Status",
        }
        if value_col:
            column_config[value_col] = st.column_config.TextColumn("Amount")
        if gp_col:
            column_config[gp_col] = st.column_config.TextColumn("GP")
        
        st.dataframe(
            display_overdue,
            column_config=column_config,
            width="stretch", hide_index=True, height=400
        )
    else:
        st.success("✅ No overdue orders - all backlog is on track!")