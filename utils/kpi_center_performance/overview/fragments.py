# utils/kpi_center_performance/overview/fragments.py
"""
Streamlit Fragments for KPI Center Performance - Overview Tab.

"""

import logging
from typing import Dict, List, Optional
from datetime import date
import pandas as pd
import streamlit as st

from .charts import (
    render_kpi_cards,
    build_monthly_trend_dual_chart,
    build_cumulative_dual_chart,
    build_multi_year_monthly_chart,
    build_multi_year_cumulative_chart,
    build_yoy_comparison_chart,
    build_yoy_cumulative_chart,
    build_forecast_waterfall_chart,
    build_gap_analysis_chart
)
from ..constants import MONTH_ORDER
from ..common.fragments import prepare_monthly_summary
from ..common.charts import convert_pipeline_to_backlog_metrics
from ..filters import analyze_period

logger = logging.getLogger(__name__)


# =============================================================================
# MONTHLY TREND FRAGMENT - UPDATED v2.4.0 to match SP page
# =============================================================================

@st.fragment
def monthly_trend_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    targets_df: pd.DataFrame = None,
    fragment_key: str = "kpc_trend"
):
    """
    Monthly trend chart with Customer/Brand/Product Excl filters.
    SYNCED with Salesperson page (Image 1 & 2).
    
    Shows:
    - Monthly Trend: Revenue + GP bars with GP% line
    - Cumulative Performance: Cumulative Revenue + GP lines
    """
    if sales_df.empty:
        st.info("No sales data for trend analysis")
        return
    
    # Header with Help button
    col_header, col_help = st.columns([6, 1])
    with col_header:
        st.subheader("📊 Monthly Trend & Cumulative")
    with col_help:
        with st.popover("ℹ️"):
            st.markdown("""
**📊 Monthly Trend & Cumulative**

**Charts:**
- **Monthly Trend**: Revenue (orange) and Gross Profit (blue) bars with GP% line overlay
- **Cumulative Performance**: Running total of Revenue and GP over the year

**Filters:**
- **Customer/Brand/Product**: Filter data by specific selections
- **Excl**: Exclude selected items instead of including them
            """)
    
    # =========================================================================
    # FILTERS ROW - SYNCED with SP page
    # =========================================================================
    
    # Customer filter with Excl checkbox
    col_cust, col_brand, col_prod = st.columns(3)
    
    with col_cust:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Customer**")
        with subcol2:
            excl_customer = st.checkbox("Excl", key=f"{fragment_key}_excl_customer")
        
        customers = ['All customers...'] + sorted(sales_df['customer'].dropna().unique().tolist())
        selected_customer = st.selectbox(
            "Customer", 
            customers, 
            key=f"{fragment_key}_customer",
            label_visibility="collapsed"
        )
    
    with col_brand:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Brand**")
        with subcol2:
            excl_brand = st.checkbox("Excl", key=f"{fragment_key}_excl_brand")
        
        brands = ['All brands...'] + sorted(sales_df['brand'].dropna().unique().tolist())
        selected_brand = st.selectbox(
            "Brand", 
            brands, 
            key=f"{fragment_key}_brand",
            label_visibility="collapsed"
        )
    
    with col_prod:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Product**")
        with subcol2:
            excl_product = st.checkbox("Excl", key=f"{fragment_key}_excl_product")
        
        products = ['All products...'] + sorted(sales_df['product_pn'].dropna().unique().tolist()[:100])
        selected_product = st.selectbox(
            "Product", 
            products, 
            key=f"{fragment_key}_product",
            label_visibility="collapsed"
        )
    
    # =========================================================================
    # APPLY FILTERS
    # =========================================================================
    
    filtered_df = sales_df.copy()
    
    # Customer filter
    if selected_customer != 'All customers...':
        if excl_customer:
            filtered_df = filtered_df[filtered_df['customer'] != selected_customer]
        else:
            filtered_df = filtered_df[filtered_df['customer'] == selected_customer]
    
    # Brand filter
    if selected_brand != 'All brands...':
        if excl_brand:
            filtered_df = filtered_df[filtered_df['brand'] != selected_brand]
        else:
            filtered_df = filtered_df[filtered_df['brand'] == selected_brand]
    
    # Product filter
    if selected_product != 'All products...':
        if excl_product:
            filtered_df = filtered_df[filtered_df['product_pn'] != selected_product]
        else:
            filtered_df = filtered_df[filtered_df['product_pn'] == selected_product]
    
    if filtered_df.empty:
        st.warning("No data matches the selected filters")
        return
    
    # =========================================================================
    # PREPARE MONTHLY DATA
    # =========================================================================
    
    monthly_df = prepare_monthly_summary(filtered_df)
    
    if monthly_df.empty:
        st.warning("Could not prepare monthly summary")
        return
    
    # =========================================================================
    # CHARTS - 2 columns like SP page
    # =========================================================================
    
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown("**📊 Monthly Trend**")
        trend_chart = build_monthly_trend_dual_chart(
            monthly_df=monthly_df,
            show_gp_percent_line=True
        )
        st.altair_chart(trend_chart, use_container_width=True)
    
    with chart_col2:
        st.markdown("**📈 Cumulative Performance**")
        cumulative_chart = build_cumulative_dual_chart(
            monthly_df=monthly_df
        )
        st.altair_chart(cumulative_chart, use_container_width=True)


# =============================================================================
# YOY COMPARISON FRAGMENT - UPDATED v2.5.0 with Multi-Year support
# =============================================================================

@st.fragment
def yoy_comparison_fragment(
    queries,
    filter_values: Dict,
    current_year: int = None,
    sales_df: pd.DataFrame = None,
    raw_cached_data: dict = None,
    fragment_key: str = "kpc_yoy"
):
    """
    Year-over-Year / Multi-Year comparison with tabs and filters.
    
    UPDATED v2.5.0: Added Multi-Year Comparison (synced with Salesperson page)
    - Detects actual years in data
    - If >= 2 years → Multi-Year Comparison (grouped bars, cumulative lines)
    - If 0-1 years → YoY Comparison (current vs previous year)
    
    Shows:
    - Tabs: Revenue / Gross Profit / GP1
    - Summary metrics (yearly totals with YoY growth)
    - Monthly comparison charts
    - Cumulative performance charts
    """
    # Header with explanation
    col_header, col_help = st.columns([6, 1])
    with col_header:
        st.subheader("📊 Year-over-Year Comparison")
    with col_help:
        with st.popover("ℹ️"):
            st.markdown("""
**📊 Year-over-Year Comparison**

This section shows **full year** trends for context:
- **Current Year**: YTD performance (selected period)
- **Previous Year**: Full 12-month performance

**Note:** The YoY % in KPI Cards above compares the **same period** 
(e.g., Jan 1-27, 2026 vs Jan 1-27, 2025) for accurate growth measurement.

This section shows full previous year to visualize monthly patterns and seasonality.
            """)
    
    if current_year is None:
        current_year = filter_values.get('year', date.today().year)
    
    # =========================================================================
    # FILTERS ROW - SYNCED with SP page
    # =========================================================================
    
    col_cust, col_brand, col_prod = st.columns(3)
    
    with col_cust:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Customer**")
        with subcol2:
            excl_customer = st.checkbox("Excl", key=f"{fragment_key}_excl_customer")
        
        if sales_df is not None and not sales_df.empty:
            customers = ['All customers...'] + sorted(sales_df['customer'].dropna().unique().tolist())
        else:
            customers = ['All customers...']
        
        selected_customer = st.selectbox(
            "Customer",
            customers,
            key=f"{fragment_key}_customer",
            label_visibility="collapsed"
        )
    
    with col_brand:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Brand**")
        with subcol2:
            excl_brand = st.checkbox("Excl", key=f"{fragment_key}_excl_brand")
        
        if sales_df is not None and not sales_df.empty:
            brands = ['All brands...'] + sorted(sales_df['brand'].dropna().unique().tolist())
        else:
            brands = ['All brands...']
        
        selected_brand = st.selectbox(
            "Brand",
            brands,
            key=f"{fragment_key}_brand",
            label_visibility="collapsed"
        )
    
    with col_prod:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Product**")
        with subcol2:
            excl_product = st.checkbox("Excl", key=f"{fragment_key}_excl_product")
        
        if sales_df is not None and not sales_df.empty:
            products = ['All products...'] + sorted(sales_df['product_pn'].dropna().unique().tolist()[:100])
        else:
            products = ['All products...']
        
        selected_product = st.selectbox(
            "Product",
            products,
            key=f"{fragment_key}_product",
            label_visibility="collapsed"
        )
    
    # =========================================================================
    # LOCAL FILTER FUNCTION
    # =========================================================================
    
    def apply_local_filters(df):
        """Apply local filters to dataframe."""
        if df.empty:
            return df
        
        filtered = df.copy()
        
        if selected_customer != 'All customers...' and 'customer' in filtered.columns:
            if excl_customer:
                filtered = filtered[filtered['customer'] != selected_customer]
            else:
                filtered = filtered[filtered['customer'] == selected_customer]
        
        if selected_brand != 'All brands...' and 'brand' in filtered.columns:
            if excl_brand:
                filtered = filtered[filtered['brand'] != selected_brand]
            else:
                filtered = filtered[filtered['brand'] == selected_brand]
        
        if selected_product != 'All products...' and 'product_pn' in filtered.columns:
            if excl_product:
                filtered = filtered[filtered['product_pn'] != selected_product]
            else:
                filtered = filtered[filtered['product_pn'] == selected_product]
        
        return filtered
    
    # =========================================================================
    # DETECT MULTI-YEAR DATA
    # =========================================================================
    
    if sales_df is None or sales_df.empty:
        st.info("No sales data available for comparison")
        return
    
    # Ensure inv_date is datetime
    df_check = sales_df.copy()
    if 'inv_date' in df_check.columns:
        df_check['inv_date'] = pd.to_datetime(df_check['inv_date'], errors='coerce')
        df_check['inv_year'] = df_check['inv_date'].dt.year
        unique_years = sorted(df_check['inv_year'].dropna().unique())
        unique_years = [int(y) for y in unique_years if y > 2000]
    else:
        unique_years = [current_year]
    
    # =========================================================================
    # MULTI-YEAR vs YOY COMPARISON
    # =========================================================================
    
    # FIXED v4.6.1: Use correct filter keys (sync with data_processor)
    exclude_internal = filter_values.get('exclude_internal_revenue', True)  # Was 'exclude_internal'
    kpi_center_ids = filter_values.get('kpi_center_ids_expanded', [])
    entity_ids = filter_values.get('entity_ids', [])
    kpi_type = filter_values.get('kpi_type_filter')  # NEW: Add KPI type filter
    
    if len(unique_years) >= 2:
        # =================================================================
        # MULTI-YEAR COMPARISON (like Salesperson page)
        # =================================================================
        
        st.info(f"📆 Data spans {len(unique_years)} years: {', '.join(map(str, unique_years))}")
        
        # Apply local filters
        multi_year_df = apply_local_filters(sales_df)
        
        if multi_year_df.empty:
            st.warning("No data matches the selected filters")
            return
        
        # Ensure year column
        multi_year_df['inv_date'] = pd.to_datetime(multi_year_df['inv_date'], errors='coerce')
        multi_year_df['inv_year'] = multi_year_df['inv_date'].dt.year
        multi_year_df['invoice_month'] = multi_year_df['inv_date'].dt.strftime('%b')
        
        # Aggregate by year and month
        monthly_by_year = multi_year_df.groupby(['inv_year', 'invoice_month']).agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in multi_year_df.columns else 'first',
            'inv_number': pd.Series.nunique
        }).reset_index()
        
        monthly_by_year.columns = ['year', 'month', 'revenue', 'gross_profit', 'gp1', 'orders']
        
        # Add month order for sorting
        monthly_by_year['month_order'] = monthly_by_year['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
        monthly_by_year = monthly_by_year.sort_values(['year', 'month_order'])
        
        # Tabs: Revenue / Gross Profit / GP1
        tab_rev, tab_gp, tab_gp1 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        for tab, metric_name, metric_col in [
            (tab_rev, "Revenue", "revenue"),
            (tab_gp, "Gross Profit", "gross_profit"),
            (tab_gp1, "GP1", "gp1")
        ]:
            with tab:
                # Summary metrics per year
                yearly_totals = monthly_by_year.groupby('year')[metric_col].sum().sort_index()
                
                # Display yearly totals with YoY change
                cols = st.columns(len(yearly_totals))
                prev_value = None
                for i, (year, value) in enumerate(yearly_totals.items()):
                    with cols[i]:
                        if prev_value is not None and prev_value > 0:
                            yoy_change = ((value - prev_value) / prev_value * 100)
                            color = "green" if yoy_change > 0 else "red"
                            arrow = "↑" if yoy_change > 0 else "↓"
                            delta_str = f":{color}[{arrow} {yoy_change:+.1f}% YoY]"
                        else:
                            delta_str = ""
                        
                        st.markdown(f"**{int(year)} {metric_name}**")
                        st.markdown(f"### ${value:,.0f}")
                        if delta_str:
                            st.markdown(delta_str)
                    
                    prev_value = value
                
                st.markdown("")
                
                # Charts
                chart_col1, chart_col2 = st.columns(2)
                
                with chart_col1:
                    st.markdown(f"**📊 Monthly {metric_name} by Year**")
                    chart = build_multi_year_monthly_chart(
                        monthly_df=monthly_by_year,
                        metric_col=metric_col,
                        years=unique_years
                    )
                    st.altair_chart(chart, use_container_width=True)
                
                with chart_col2:
                    st.markdown(f"**📈 Cumulative {metric_name}**")
                    chart = build_multi_year_cumulative_chart(
                        monthly_df=monthly_by_year,
                        metric_col=metric_col,
                        years=unique_years
                    )
                    st.altair_chart(chart, use_container_width=True)
    
    else:
        # =================================================================
        # TRADITIONAL YOY COMPARISON (current year vs previous year)
        # =================================================================
        
        primary_year = current_year
        previous_year = current_year - 1
        
        # Apply local filters to current year
        yoy_sales_df = apply_local_filters(sales_df)
        
        if yoy_sales_df.empty:
            st.warning("No data matches the selected filters")
            return
        
        # Get previous year data (FULL YEAR for context)
        # NOTE: This intentionally shows full previous year for comparison context
        # KPI Cards show same-period YoY, this section shows full year trend
        prev_start = date(previous_year, 1, 1)
        prev_end = date(previous_year, 12, 31)
        
        previous_df = pd.DataFrame()
        cache_hit = False
        
        # Check raw_cached_data for previous year data
        # FIXED v4.6.1: Use correct key 'sales_raw_df' (was 'sales_raw')
        if raw_cached_data and 'sales_raw_df' in raw_cached_data:
            cached_sales = raw_cached_data['sales_raw_df']
            if not cached_sales.empty and 'inv_date' in cached_sales.columns:
                cached_sales['inv_date'] = pd.to_datetime(cached_sales['inv_date'], errors='coerce')
                cached_sales['inv_year'] = cached_sales['inv_date'].dt.year
                
                if previous_year in cached_sales['inv_year'].values:
                    previous_df = cached_sales[cached_sales['inv_year'] == previous_year].copy()
                    
                    # Apply KPI Center filter
                    if kpi_center_ids and 'kpi_center_id' in previous_df.columns:
                        previous_df = previous_df[previous_df['kpi_center_id'].isin(kpi_center_ids)]
                    
                    # FIXED v4.6.1: Use correct column name 'legal_entity_id' (was 'entity_id')
                    if entity_ids and 'legal_entity_id' in previous_df.columns:
                        previous_df = previous_df[previous_df['legal_entity_id'].isin(entity_ids)]
                    
                    # FIXED v4.6.1: Add KPI type filter (was missing)
                    if kpi_type and 'kpi_type' in previous_df.columns:
                        previous_df = previous_df[previous_df['kpi_type'] == kpi_type]
                    
                    cache_hit = True
        
        # If not in cache, query DB
        if not cache_hit:
            try:
                previous_df = queries.get_sales_data(
                    start_date=prev_start,
                    end_date=prev_end,
                    kpi_center_ids=kpi_center_ids if kpi_center_ids else None,
                    entity_ids=entity_ids if entity_ids else None
                )
            except Exception as e:
                logger.error(f"Error querying previous year data: {e}")
                previous_df = pd.DataFrame()
        
        # FIXED v4.6.1: Exclude internal revenue - set to 0, don't remove rows (sync with data_processor)
        if exclude_internal and not previous_df.empty and 'customer_type' in previous_df.columns:
            internal_mask = previous_df['customer_type'].str.lower() == 'internal'
            if internal_mask.any():
                previous_df = previous_df.copy()
                previous_df.loc[internal_mask, 'sales_by_kpi_center_usd'] = 0
        
        # Apply local filters to previous year
        previous_filtered = apply_local_filters(previous_df)
        
        # Prepare monthly summaries
        current_monthly = prepare_monthly_summary(yoy_sales_df, debug_label="current")
        previous_monthly = prepare_monthly_summary(previous_filtered, debug_label="previous")
        
        if previous_monthly.empty:
            st.info(f"No data available for {previous_year} comparison")
            return
        
        # Tabs: Revenue / Gross Profit / GP1
        tab_rev, tab_gp, tab_gp1 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        for tab, metric_name, metric_col in [
            (tab_rev, "Revenue", "revenue"),
            (tab_gp, "Gross Profit", "gross_profit"),
            (tab_gp1, "GP1", "gp1")
        ]:
            with tab:
                current_total = current_monthly[metric_col].sum() if not current_monthly.empty and metric_col in current_monthly.columns else 0
                previous_total = previous_monthly[metric_col].sum() if not previous_monthly.empty and metric_col in previous_monthly.columns else 0
                
                if previous_total > 0:
                    yoy_change = ((current_total - previous_total) / previous_total * 100)
                    yoy_diff = current_total - previous_total
                else:
                    yoy_change = 0
                    yoy_diff = current_total
                
                col_curr, col_prev = st.columns(2)
                
                with col_curr:
                    st.markdown(f"**{primary_year} {metric_name} (YTD)**")
                    st.markdown(f"### ${current_total:,.0f}")
                    if yoy_change != 0:
                        color = "green" if yoy_change > 0 else "red"
                        arrow = "↑" if yoy_change > 0 else "↓"
                        st.markdown(f":{color}[{arrow} {yoy_change:+.1f}% vs Full Year]")
                
                with col_prev:
                    st.markdown(f"**{previous_year} {metric_name} (Full Year)**")
                    st.markdown(f"### ${previous_total:,.0f}")
                    st.caption(f"Difference: ${yoy_diff:+,.0f}" if yoy_diff != 0 else "")
                
                st.markdown("")
                
                chart_col1, chart_col2 = st.columns(2)
                
                with chart_col1:
                    st.markdown(f"**📊 Monthly {metric_name} Comparison**")
                    comparison_chart = build_yoy_comparison_chart(
                        current_df=current_monthly,
                        previous_df=previous_monthly,
                        metric=metric_name,
                        current_year=primary_year,
                        previous_year=previous_year
                    )
                    st.altair_chart(comparison_chart, use_container_width=True)
                
                with chart_col2:
                    st.markdown(f"**📈 Cumulative {metric_name}**")
                    cumulative_chart = build_yoy_cumulative_chart(
                        current_df=current_monthly,
                        previous_df=previous_monthly,
                        metric=metric_name,
                        current_year=primary_year,
                        previous_year=previous_year
                    )
                    st.altair_chart(cumulative_chart, use_container_width=True)


# =============================================================================
# EXPORT REPORT FRAGMENT
# =============================================================================

@st.fragment
def export_report_fragment(
    metrics: Dict,
    complex_kpis: Dict,
    pipeline_metrics: Dict,
    filter_values: Dict,
    yoy_metrics: Dict = None,
    kpi_center_summary_df: pd.DataFrame = None,
    monthly_df: pd.DataFrame = None,
    sales_detail_df: pd.DataFrame = None,
    backlog_summary_df: pd.DataFrame = None,
    backlog_detail_df: pd.DataFrame = None,
    backlog_by_month_df: pd.DataFrame = None
):
    """Excel report generation fragment."""
    from ..export import KPICenterExport
    
    st.subheader("📥 Export Report")
    
    with st.expander("ℹ️ Export Options"):
        st.markdown("""
**Excel Report includes:**
- Summary sheet with all KPI metrics
- KPI Center breakdown
- Monthly trend data
- Sales transaction details (up to 10,000 rows)
- Backlog summary and details
        """)
    
    if st.button("🔄 Generate Excel Report", key="generate_report_btn", type="primary"):
        with st.spinner("Generating report..."):
            try:
                exporter = KPICenterExport()
                excel_bytes = exporter.create_comprehensive_report(
                    metrics=metrics,
                    complex_kpis=complex_kpis,
                    pipeline_metrics=pipeline_metrics,
                    filters=filter_values,
                    yoy_metrics=yoy_metrics,
                    kpi_center_summary_df=kpi_center_summary_df,
                    monthly_df=monthly_df,
                    sales_detail_df=sales_detail_df,
                    backlog_summary_df=backlog_summary_df,
                    backlog_detail_df=backlog_detail_df,
                    backlog_by_month_df=backlog_by_month_df,
                )
                st.session_state['kpi_center_export_data'] = excel_bytes
                st.success("✅ Report generated! Click download below.")
            except Exception as e:
                logger.error(f"Export error: {e}")
                st.error(f"Failed to generate report: {e}")
    
    if 'kpi_center_export_data' in st.session_state:
        year = filter_values.get('year', 2025)
        period = filter_values.get('period_type', 'YTD')
        filename = f"kpi_center_performance_{year}_{period}.xlsx"
        st.download_button(
            label="⬇️ Download Excel Report",
            data=st.session_state['kpi_center_export_data'],
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_report_btn"
        )


# =============================================================================
# BACKLOG FORECAST SECTION - MOVED FROM MAIN PAGE v4.6.0
# =============================================================================

def _render_backlog_forecast_section(
    summary_metrics: Dict,
    kpi_metrics: Dict,
    metric_type: str,
    chart_backlog_metrics: Dict = None,
    gp1_gp_ratio: float = 1.0
):
    """
    Render backlog forecast metrics AND charts for a specific tab (revenue/gp/gp1).
    
    MOVED from main page v4.6.0 (was _render_backlog_forecast_tab)
    
    Args:
        summary_metrics: Overall summary metrics (total_backlog_revenue, etc.)
        kpi_metrics: KPI-specific metrics (in_period_backlog, target, forecast, gap)
        metric_type: 'revenue', 'gp', or 'gp1'
        chart_backlog_metrics: Dict for chart rendering (optional)
        gp1_gp_ratio: Ratio for GP1 estimation (default 1.0)
    """
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    
    # Labels and keys based on type
    if metric_type == 'revenue':
        total_key = 'total_backlog_revenue'
        label_total = "Total Backlog"
        help_suffix = "revenue"
        kpi_name = "Revenue"
    elif metric_type == 'gp':
        total_key = 'total_backlog_gp'
        label_total = "Total GP Backlog"
        help_suffix = "GP"
        kpi_name = "GP"
    else:  # gp1
        total_key = 'total_backlog_gp1'
        label_total = "Total GP1 Backlog"
        help_suffix = "GP1"
        kpi_name = "GP1"
    
    with col_m1:
        help_text = f"All outstanding {help_suffix} from pending orders"
        if metric_type == 'gp1' and gp1_gp_ratio != 1.0:
            help_text = f"Estimated GP1 backlog (GP × {gp1_gp_ratio:.2%})"
        st.metric(
            label=label_total,
            value=f"${summary_metrics.get(total_key, 0):,.0f}",
            delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
            delta_color="off",
            help=help_text
        )
    
    with col_m2:
        in_period = kpi_metrics.get('in_period_backlog', 0)
        target = kpi_metrics.get('target')
        pct = (in_period / target * 100) if target and target > 0 else None
        kpc_count = kpi_metrics.get('kpi_center_count', 0)
        st.metric(
            label="In-Period (KPI)",
            value=f"${in_period:,.0f}",
            delta=f"{pct:.0f}% of target" if pct else None,
            delta_color="off",
            help=f"Backlog with ETD in period. Only from {kpc_count} KPI Centers with {kpi_name} KPI."
        )
    
    with col_m3:
        target = kpi_metrics.get('target')
        kpc_count = kpi_metrics.get('kpi_center_count', 0)
        if target and target > 0:
            st.metric(
                label="Target",
                value=f"${target:,.0f}",
                delta=f"{kpc_count} KPI Centers",
                delta_color="off",
                help=f"Sum of prorated {kpi_name} targets from {kpc_count} KPI Centers"
            )
        else:
            st.metric(
                label="Target",
                value="N/A",
                delta="No KPI assigned",
                delta_color="off",
                help="No KPI target assigned"
            )
    
    with col_m4:
        forecast = kpi_metrics.get('forecast')
        achievement = kpi_metrics.get('forecast_achievement')
        if forecast is not None:
            delta_color = "normal" if achievement and achievement >= 100 else "inverse"
            st.metric(
                label="Forecast (KPI)",
                value=f"${forecast:,.0f}",
                delta=f"{achievement:.0f}% of target" if achievement else None,
                delta_color=delta_color if achievement else "off",
                help="Invoiced + In-Period Backlog"
            )
        else:
            st.metric(
                label="Forecast (KPI)",
                value="N/A",
                delta="No target",
                delta_color="off",
                help="No KPI target assigned"
            )
    
    with col_m5:
        gap = kpi_metrics.get('gap')
        gap_pct = kpi_metrics.get('gap_percent')
        if gap is not None:
            gap_label = "Surplus ✅" if gap >= 0 else "GAP ⚠️"
            delta_color = "normal" if gap >= 0 else "inverse"
            st.metric(
                label=gap_label,
                value=f"${gap:+,.0f}",
                delta=f"{gap_pct:+.1f}%" if gap_pct else None,
                delta_color=delta_color,
                help="Forecast - Target. Positive = ahead, Negative = behind."
            )
        else:
            st.metric(
                label="GAP",
                value="N/A",
                delta="No target",
                delta_color="off",
                help="No KPI target assigned"
            )
    
    # =========================================================================
    # CHARTS ROW
    # =========================================================================
    if chart_backlog_metrics:
        col_bf1, col_bf2 = st.columns(2)
        with col_bf1:
            st.markdown(f"**{kpi_name} Forecast vs Target**")
            forecast_chart = build_forecast_waterfall_chart(
                backlog_metrics=chart_backlog_metrics,
                metric=metric_type,
                title=""
            )
            st.altair_chart(forecast_chart, use_container_width=True)
        with col_bf2:
            st.markdown(f"**{kpi_name}: Target vs Forecast**")
            gap_chart = build_gap_analysis_chart(
                backlog_metrics=chart_backlog_metrics,
                metrics_to_show=[metric_type],
                title=""
            )
            st.altair_chart(gap_chart, use_container_width=True)


# =============================================================================
# OVERVIEW TAB FRAGMENT - NEW v4.6.0
# =============================================================================

def overview_tab_fragment(
    # Data
    sales_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    data: Dict,
    
    # Metrics
    overview_metrics: Dict,
    yoy_metrics: Optional[Dict],
    complex_kpis: Dict,
    pipeline_metrics: Dict,
    overall_achievement: Dict,
    
    # Filters & Config
    active_filters: Dict,
    queries,
    unified_cache: Dict,
    
    # Summaries (pre-calculated)
    monthly_df: pd.DataFrame,
    kpi_center_summary_df: pd.DataFrame,
):
    """
    Render the complete Overview tab.
    
    NEW v4.6.0: Centralizes all Overview tab rendering logic.
    Replaces inline code in main page.
    
    Args:
        sales_df: Filtered sales data
        targets_df: Filtered targets data
        data: Processed data dict from DataProcessor
        overview_metrics: Overview metrics from KPICenterMetrics
        yoy_metrics: Year-over-Year metrics (optional)
        complex_kpis: Complex KPI values (new customers, products, business)
        pipeline_metrics: Pipeline/forecast metrics
        overall_achievement: Overall KPI achievement dict
        active_filters: Currently applied filters
        queries: KPICenterQueries instance (for YoY fragment)
        unified_cache: Unified raw data cache (for YoY fragment)
        monthly_df: Pre-calculated monthly summary
        kpi_center_summary_df: Pre-calculated KPI Center summary
    """
    # =========================================================================
    # SECTION 1: KPI CARDS
    # =========================================================================
    render_kpi_cards(
        metrics=overview_metrics,
        yoy_metrics=yoy_metrics,
        complex_kpis=complex_kpis,
        overall_achievement=overall_achievement,
        new_customers_df=data.get('new_customers_detail_df'),
        new_products_df=data.get('new_products_detail_df'),
        new_combos_detail_df=data.get('new_combos_detail_df'),  # FIXED v5.3.2: Use deduplicated new_combos_detail_df
        new_business_df=data.get('new_business_df'),
        new_business_detail_df=data.get('new_business_detail_df')
    )
    
    st.divider()
    
    # =========================================================================
    # SECTION 2: BACKLOG & FORECAST (MOVED UP v4.6.2)
    # =========================================================================
    period_info = analyze_period(active_filters)
    
    if period_info.get('show_backlog', True):
        col_bf_header, col_bf_help = st.columns([6, 1])
        with col_bf_header:
            st.subheader("📦 Backlog & Forecast")
        with col_bf_help:
            with st.popover("ℹ️ Help"):
                st.markdown("""
**📦 Backlog & Forecast**

| Metric | Formula | Description |
|--------|---------|-------------|
| **Total Backlog** | `Σ backlog_by_kpi_center_usd` | All outstanding orders |
| **In-Period (KPI)** | `Σ backlog WHERE ETD in period` | Backlog expected to ship in period |
| **Target** | `Σ prorated_target` | Sum of prorated annual targets |
| **Forecast (KPI)** | `Invoiced + In-Period` | Projected total |
| **GAP/Surplus** | `Forecast - Target` | Positive = ahead, Negative = behind |
                """)
        
        # Overdue warning
        backlog_risk = data.get('backlog_risk', {})
        if backlog_risk and backlog_risk.get('overdue_orders', 0) > 0:
            overdue_orders = backlog_risk.get('overdue_orders', 0)
            overdue_revenue = backlog_risk.get('overdue_revenue', 0)
            st.warning(f"⚠️ {overdue_orders} orders are past ETD. Value: ${overdue_revenue:,.0f}")
        
        # Pipeline metrics display
        summary_metrics = pipeline_metrics.get('summary', {})
        gp1_gp_ratio = summary_metrics.get('gp1_gp_ratio', 1.0)
        if gp1_gp_ratio != 1.0:
            st.caption(f"📊 GP1 backlog estimated using GP1/GP ratio: {gp1_gp_ratio:.2%}")
        
        chart_backlog_metrics = convert_pipeline_to_backlog_metrics(pipeline_metrics)
        
        revenue_metrics = pipeline_metrics.get('revenue', {})
        gp_metrics = pipeline_metrics.get('gross_profit', {})
        gp1_metrics = pipeline_metrics.get('gp1', {})
        
        bf_tab1, bf_tab2, bf_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        with bf_tab1:
            _render_backlog_forecast_section(
                summary_metrics, revenue_metrics, 'revenue',
                chart_backlog_metrics=chart_backlog_metrics
            )
        
        with bf_tab2:
            _render_backlog_forecast_section(
                summary_metrics, gp_metrics, 'gp',
                chart_backlog_metrics=chart_backlog_metrics
            )
        
        with bf_tab3:
            _render_backlog_forecast_section(
                summary_metrics, gp1_metrics, 'gp1',
                chart_backlog_metrics=chart_backlog_metrics,
                gp1_gp_ratio=gp1_gp_ratio
            )
        
        st.divider()
    
    # =========================================================================
    # SECTION 3: MONTHLY TREND (WAS SECTION 2)
    # =========================================================================
    monthly_trend_fragment(
        sales_df=sales_df,
        filter_values=active_filters,
        targets_df=targets_df,
        fragment_key="kpc_trend"
    )
    
    st.divider()
    
    # =========================================================================
    # SECTION 4: YEAR-OVER-YEAR COMPARISON (WAS SECTION 3)
    # =========================================================================
    if active_filters.get('show_yoy', True):
        yoy_comparison_fragment(
            queries=queries,
            filter_values=active_filters,
            current_year=active_filters['year'],
            sales_df=sales_df,
            raw_cached_data=unified_cache,
            fragment_key="kpc_yoy"
        )
        
        st.divider()
    
    # =========================================================================
    # SECTION 5: EXPORT REPORT
    # =========================================================================
    export_report_fragment(
        metrics=overview_metrics,
        complex_kpis=complex_kpis,
        pipeline_metrics=pipeline_metrics,
        filter_values=active_filters,
        yoy_metrics=yoy_metrics,
        kpi_center_summary_df=kpi_center_summary_df,
        monthly_df=monthly_df,
        sales_detail_df=sales_df,
        backlog_summary_df=data.get('backlog_summary_df', pd.DataFrame()),
        backlog_detail_df=data.get('backlog_detail_df', pd.DataFrame()),
        backlog_by_month_df=data.get('backlog_by_month_df', pd.DataFrame())
    )