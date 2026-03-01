# utils/salesperson_performance/fragments.py
"""
Streamlit Fragments for Salesperson Performance

Uses @st.fragment to enable partial reruns for filter-heavy sections.
Each fragment only reruns when its internal widgets change,
NOT when sidebar filters or other sections change.

VERSION: 3.4.0 - Combined fragments with filters above sub-tabs

CHANGELOG:
- v3.4.0: NEW Combined fragments with filters ABOVE sub-tabs (like KPI Center)
          - sales_detail_tab_fragment: Filters + Sales List + Pivot sub-tabs
          - backlog_tab_fragment: Filters + Backlog List + By ETD + Risk sub-tabs
          - When filter changes, ALL sub-tabs update (shared filter state)
          - Still uses @st.fragment to prevent full page rerun
- v2.10.0: UPDATED GP/GP1 display to separate columns (instead of inline)
          - Sales Detail: GP, GP%, GP1, GP1% as 4 separate columns
          - Backlog List: GP, GP% as 2 separate columns
          - Summary cards: Added GP%/GP1% in delta display
          - Increased display limit from 500/200 to 5000 rows
          - Increased dataframe height to 600px
- v2.9.0: ADDED inline margin % display for GP and GP1 columns (superseded by v2.10.0)
- v2.8.0: FIXED Backlog summary cards not filtering by selected salesperson
          - Bug: total_backlog_df (pre-aggregated) was not filtered by selected salesperson
          - Result: Summary cards showed $355K (19 orders) while table showed only 5 orders
          - Fix: Always calculate totals from backlog_df (detail) which is correctly filtered
          - Removed dependency on total_backlog_df parameter for summary calculation
          FIXED Status card showing "HAS OVERDUE" when there are no in-period orders
          - Bug: Any status != 'healthy' displayed "HAS OVERDUE" (including 'empty')
          - Result: When no orders have ETD in selected period, showed "HAS OVERDUE" incorrectly
          - Fix: Proper status logic - distinguish healthy/has_overdue/empty states
          - New status "NO IN-PERIOD" when no orders fall within date range
- v2.7.1: FIXED KPI name mismatch bug in kpi_progress_fragment Individual Performance
          - Bug: Database stores "Gross Profit 1" but kpi_column_map expects "gross_profit_1"
          - Result: GP1, New Business Revenue, New Customers not matched → actual = 0
          - Fix: Normalize kpi_name with .lower().replace(' ', '_') at line 2312
- v2.7.0: UPDATED team_ranking_fragment to use overall_achievement
          - Now uses overall_achievement directly if available
          - Falls back to average of revenue + GP achievement if not
          - Consistent with Overview Achievement and Performance table
- v2.6.0: FIXED Achievement % consistency in export_report_fragment
          - Bug: aggregate_by_salesperson() used ANNUAL target
          - Fix: Now passes period_type and year for prorated calculation
          - Table Achievement % now matches Overall Achievement
- v2.5.0: ADDED export_report_fragment
          - Generates Excel report without reloading entire page
          - Two-step: Generate → Download
          - All data passed as parameters for isolation
- v2.4.0: UPDATED export in sales_detail_fragment
          - Export button now labeled "Export Filtered View"
          - Added hint to use sidebar for full report
          - Comprehensive export moved to main page sidebar
- v2.3.0: ADDED summary metrics cards to sales_detail_fragment
          - Revenue, GP, GP1, Orders, Customers, Avg Order, Avg GP/Cust
          - Consistent pattern with Backlog List fragment
          - Professional dashboard appearance
- v2.2.0: IMPROVED help text in backlog_list_fragment
          - Consistent English help text for all metrics
          - Clarified scope: "all selected employees" vs KPI-filtered
- v2.1.0: FIXED backlog_list_fragment summary card accuracy
          - Added total_backlog_df parameter for accurate aggregated totals
          - Summary cards now use aggregated data instead of sum from detail
          - Fixes mismatch between Backlog Tab and Overview totals
- v2.0.0: Complete rewrite with 100% code from original file
          - Monthly Trend: Full filters + charts (lines 645-732)
          - YoY Comparison: Full multi-year + single-year logic (lines 742-1122)
          - Sales Detail: Full filters + formatting + export (lines 1611-1881)
          - Pivot Analysis: Full pivot config (lines 1883-1928)
          - Backlog List: Full filters + formatting (lines 1969-2237)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional, Any

from .metrics import SalespersonMetrics
from .charts import SalespersonCharts
from .export import SalespersonExport
from .constants import MONTH_ORDER

from .filters import (
    render_multiselect_filter,
    apply_multiselect_filter,
    render_text_search_filter,
    apply_text_search_filter,
    render_number_filter,
    apply_number_filter,
)


# =============================================================================
# FRAGMENT: MONTHLY TREND SECTION (Tab 1)
# Lines 645-732 from original file - 100% code preserved
# =============================================================================

@st.fragment
def monthly_trend_fragment(
    sales_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    fragment_key: str = "trend"
):
    """
    Fragment for Monthly Trend & Cumulative charts with drill-down filters.
    
    100% code from original file lines 645-732.
    """
    # ==========================================================================
    # MONTHLY TREND + CUMULATIVE - WITH DRILL-DOWN FILTERS
    # ==========================================================================
    col_trend_header, col_trend_help = st.columns([6, 1])
    with col_trend_header:
        st.subheader("📊 Monthly Trend & Cumulative")
    with col_trend_help:
        with st.popover("ℹ️"):
            st.markdown("""
            **Filter by Customer/Brand/Product** to drill-down into specific segments.
            
            Use **Excl** checkbox to exclude selected items instead of filtering to them.
            """)
    
    # --- Drill-down filters ---
    col_tf1, col_tf2, col_tf3 = st.columns(3)
    
    with col_tf1:
        trend_customer_options = sorted(sales_df['customer'].dropna().unique().tolist()) if not sales_df.empty else []
        trend_customer_filter = render_multiselect_filter(
            label="Customer",
            options=trend_customer_options,
            key=f"{fragment_key}_customer",
            placeholder="All customers..."
        )
    
    with col_tf2:
        trend_brand_options = sorted(sales_df['brand'].dropna().unique().tolist()) if not sales_df.empty else []
        trend_brand_filter = render_multiselect_filter(
            label="Brand",
            options=trend_brand_options,
            key=f"{fragment_key}_brand",
            placeholder="All brands..."
        )
    
    with col_tf3:
        trend_product_options = sorted(sales_df['product_pn'].dropna().unique().tolist())[:100] if not sales_df.empty else []
        trend_product_filter = render_multiselect_filter(
            label="Product",
            options=trend_product_options,
            key=f"{fragment_key}_product",
            placeholder="All products..."
        )
    
    # Apply filters to sales data for this section
    trend_sales_df = sales_df.copy() if not sales_df.empty else pd.DataFrame()
    trend_sales_df = apply_multiselect_filter(trend_sales_df, 'customer', trend_customer_filter)
    trend_sales_df = apply_multiselect_filter(trend_sales_df, 'brand', trend_brand_filter)
    trend_sales_df = apply_multiselect_filter(trend_sales_df, 'product_pn', trend_product_filter)
    
    # Show filter summary
    trend_active_filters = []
    if trend_customer_filter.is_active:
        mode = "excl" if trend_customer_filter.excluded else "incl"
        trend_active_filters.append(f"Customer: {len(trend_customer_filter.selected)} ({mode})")
    if trend_brand_filter.is_active:
        mode = "excl" if trend_brand_filter.excluded else "incl"
        trend_active_filters.append(f"Brand: {len(trend_brand_filter.selected)} ({mode})")
    if trend_product_filter.is_active:
        mode = "excl" if trend_product_filter.excluded else "incl"
        trend_active_filters.append(f"Product: {len(trend_product_filter.selected)} ({mode})")
    
    if trend_active_filters:
        st.caption(f"🔍 Filters: {' | '.join(trend_active_filters)}")
    
    # Calculate monthly summary with filtered data
    trend_metrics_calc = SalespersonMetrics(trend_sales_df, targets_df)
    monthly_summary = trend_metrics_calc.prepare_monthly_summary()
    
    # Monthly charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### 📊 Monthly Trend")
        monthly_chart = SalespersonCharts.build_monthly_trend_chart(
            monthly_df=monthly_summary,
            show_gp1=False,
            title=""
        )
        st.altair_chart(monthly_chart, use_container_width=True)
    
    with col2:
        st.markdown("##### 📈 Cumulative Performance")
        cumulative_chart = SalespersonCharts.build_cumulative_chart(
            monthly_df=monthly_summary,
            title=""
        )
        st.altair_chart(cumulative_chart, use_container_width=True)


# =============================================================================
# FRAGMENT: YOY COMPARISON SECTION (Tab 1)
# Lines 742-1122 from original file - 100% code preserved
# =============================================================================

@st.fragment
def yoy_comparison_fragment(
    sales_df: pd.DataFrame,
    queries,  # SalespersonQueries instance
    filter_values: Dict,
    fragment_key: str = "yoy"
):
    """
    Fragment for Year-over-Year comparison with drill-down filters.
    
    100% code from original file lines 742-1122.
    Includes both multi-year and single-year comparison logic.
    """
    # --- Header with help ---
    col_yc_header, col_yc_help = st.columns([6, 1])
    with col_yc_header:
        st.subheader("📊 Year-over-Year Comparison")
    with col_yc_help:
        with st.popover("ℹ️"):
            st.markdown("""
            **Filter by Customer/Brand/Product** to compare YoY performance for specific segments.
            
            Use **Excl** checkbox to exclude selected items instead of filtering to them.
            """)
    
    # --- Drill-down filters for YoY section ---
    col_yf1, col_yf2, col_yf3 = st.columns(3)
    
    with col_yf1:
        yoy_customer_options = sorted(sales_df['customer'].dropna().unique().tolist()) if not sales_df.empty else []
        yoy_customer_filter = render_multiselect_filter(
            label="Customer",
            options=yoy_customer_options,
            key=f"{fragment_key}_customer",
            placeholder="All customers..."
        )
    
    with col_yf2:
        yoy_brand_options = sorted(sales_df['brand'].dropna().unique().tolist()) if not sales_df.empty else []
        yoy_brand_filter = render_multiselect_filter(
            label="Brand",
            options=yoy_brand_options,
            key=f"{fragment_key}_brand",
            placeholder="All brands..."
        )
    
    with col_yf3:
        yoy_product_options = sorted(sales_df['product_pn'].dropna().unique().tolist())[:100] if not sales_df.empty else []
        yoy_product_filter = render_multiselect_filter(
            label="Product",
            options=yoy_product_options,
            key=f"{fragment_key}_product",
            placeholder="All products..."
        )
    
    # Apply filters to sales data for YoY section
    yoy_sales_df = sales_df.copy() if not sales_df.empty else pd.DataFrame()
    yoy_sales_df = apply_multiselect_filter(yoy_sales_df, 'customer', yoy_customer_filter)
    yoy_sales_df = apply_multiselect_filter(yoy_sales_df, 'brand', yoy_brand_filter)
    yoy_sales_df = apply_multiselect_filter(yoy_sales_df, 'product_pn', yoy_product_filter)
    
    # Show filter summary
    yoy_active_filters = []
    if yoy_customer_filter.is_active:
        mode = "excl" if yoy_customer_filter.excluded else "incl"
        yoy_active_filters.append(f"Customer: {len(yoy_customer_filter.selected)} ({mode})")
    if yoy_brand_filter.is_active:
        mode = "excl" if yoy_brand_filter.excluded else "incl"
        yoy_active_filters.append(f"Brand: {len(yoy_brand_filter.selected)} ({mode})")
    if yoy_product_filter.is_active:
        mode = "excl" if yoy_product_filter.excluded else "incl"
        yoy_active_filters.append(f"Product: {len(yoy_product_filter.selected)} ({mode})")
    
    if yoy_active_filters:
        st.caption(f"🔍 Filters: {' | '.join(yoy_active_filters)}")
    
    # Get years that actually have sales data (not just from date range)
    if not yoy_sales_df.empty and 'invoice_year' in yoy_sales_df.columns:
        actual_years = sorted(yoy_sales_df['invoice_year'].dropna().unique().astype(int).tolist())
    else:
        actual_years = []
    
    # Decide comparison type based on ACTUAL DATA, not date range
    if len(actual_years) >= 2:
        # =====================================================================
        # MULTI-YEAR COMPARISON (2+ years of actual data)
        # =====================================================================
        years_str = ', '.join(map(str, actual_years))
        st.subheader(f"📊 Multi-Year Comparison ({years_str})")
        st.caption(f"ℹ️ Comparing performance across years with actual data in selected date range.")
        
        # Create 3 tabs for each metric
        my_tab1, my_tab2, my_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        # Tab 1: Revenue
        with my_tab1:
            # Summary table
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='revenue'
            )
            
            if not summary_df.empty:
                # Display yearly totals
                cols = st.columns(len(actual_years) + 1)
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        st.metric(
                            label=f"{int(row['Year'])} Revenue",
                            value=f"${row['Total']:,.0f}",
                            delta=row['YoY Growth'] if row['YoY Growth'] != '-' else None,
                            delta_color="normal" if row['YoY Growth'] != '-' and '+' in str(row['YoY Growth']) else "inverse" if row['YoY Growth'] != '-' else "off"
                        )
            
            st.divider()
            
            # Charts side by side
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly Revenue by Year")
                monthly_chart = SalespersonCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='revenue',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative Revenue by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='revenue',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
        
        # Tab 2: Gross Profit
        with my_tab2:
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='gross_profit'
            )
            
            if not summary_df.empty:
                cols = st.columns(len(actual_years) + 1)
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        st.metric(
                            label=f"{int(row['Year'])} GP",
                            value=f"${row['Total']:,.0f}",
                            delta=row['YoY Growth'] if row['YoY Growth'] != '-' else None,
                            delta_color="normal" if row['YoY Growth'] != '-' and '+' in str(row['YoY Growth']) else "inverse" if row['YoY Growth'] != '-' else "off"
                        )
            
            st.divider()
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly Gross Profit by Year")
                monthly_chart = SalespersonCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gross_profit',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative Gross Profit by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gross_profit',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
        
        # Tab 3: GP1
        with my_tab3:
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='gp1'
            )
            
            if not summary_df.empty:
                cols = st.columns(len(actual_years) + 1)
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        st.metric(
                            label=f"{int(row['Year'])} GP1",
                            value=f"${row['Total']:,.0f}",
                            delta=row['YoY Growth'] if row['YoY Growth'] != '-' else None,
                            delta_color="normal" if row['YoY Growth'] != '-' and '+' in str(row['YoY Growth']) else "inverse" if row['YoY Growth'] != '-' else "off"
                        )
            
            st.divider()
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly GP1 by Year")
                monthly_chart = SalespersonCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gp1',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative GP1 by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gp1',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
    
    else:
        # =====================================================================
        # YOY COMPARISON (0 or 1 year of actual data)
        # =====================================================================
        
        # Determine primary year for comparison
        if len(actual_years) == 1:
            primary_year = actual_years[0]
        else:
            primary_year = filter_values['end_date'].year
        
        st.markdown(f"##### 📅 {primary_year} vs {primary_year - 1}")
        
        # Load previous year data - OPTIMIZATION v2.6.0: Cache in session_state
        yoy_frag_cache_key = f"yoy_frag_prev_{filter_values['start_date']}_{filter_values['end_date']}_{tuple(filter_values['employee_ids'] or [])}"
        
        if yoy_frag_cache_key not in st.session_state:
            previous_sales_df = queries.get_previous_year_data(
                start_date=filter_values['start_date'],
                end_date=filter_values['end_date'],
                employee_ids=filter_values['employee_ids'],
                entity_ids=filter_values['entity_ids'] if filter_values['entity_ids'] else None
            )
            st.session_state[yoy_frag_cache_key] = previous_sales_df
        else:
            previous_sales_df = st.session_state[yoy_frag_cache_key]
        
        # Apply same filters to previous year data
        if not previous_sales_df.empty:
            previous_sales_df = apply_multiselect_filter(previous_sales_df, 'customer', yoy_customer_filter)
            previous_sales_df = apply_multiselect_filter(previous_sales_df, 'brand', yoy_brand_filter)
            previous_sales_df = apply_multiselect_filter(previous_sales_df, 'product_pn', yoy_product_filter)
        
        if not previous_sales_df.empty:
            # Create 3 tabs for each metric
            yoy_tab1, yoy_tab2, yoy_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
            
            # Tab 1: Revenue
            with yoy_tab1:
                current_total = yoy_sales_df['sales_by_split_usd'].sum() if not yoy_sales_df.empty else 0
                previous_total = previous_sales_df['sales_by_split_usd'].sum() if not previous_sales_df.empty else 0
                yoy_change = ((current_total - previous_total) / previous_total * 100) if previous_total > 0 else 0
                yoy_abs = current_total - previous_total
                
                col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
                with col_s1:
                    st.metric(
                        label=f"{primary_year} Revenue",
                        value=f"${current_total:,.0f}",
                        delta=f"{yoy_change:+.1f}% YoY",
                        delta_color="normal" if yoy_change >= 0 else "inverse"
                    )
                with col_s2:
                    st.metric(
                        label=f"{primary_year - 1} Revenue",
                        value=f"${previous_total:,.0f}",
                        delta=f"${yoy_abs:+,.0f} difference",
                        delta_color="off"
                    )
                
                st.divider()
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("##### 📊 Monthly Revenue Comparison")
                    yoy_chart = SalespersonCharts.build_yoy_comparison_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='revenue',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative Revenue")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='revenue',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
            
            # Tab 2: Gross Profit
            with yoy_tab2:
                current_total = yoy_sales_df['gross_profit_by_split_usd'].sum() if not yoy_sales_df.empty else 0
                previous_total = previous_sales_df['gross_profit_by_split_usd'].sum() if not previous_sales_df.empty else 0
                yoy_change = ((current_total - previous_total) / previous_total * 100) if previous_total > 0 else 0
                yoy_abs = current_total - previous_total
                
                col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
                with col_s1:
                    st.metric(
                        label=f"{primary_year} Gross Profit",
                        value=f"${current_total:,.0f}",
                        delta=f"{yoy_change:+.1f}% YoY",
                        delta_color="normal" if yoy_change >= 0 else "inverse"
                    )
                with col_s2:
                    st.metric(
                        label=f"{primary_year - 1} Gross Profit",
                        value=f"${previous_total:,.0f}",
                        delta=f"${yoy_abs:+,.0f} difference",
                        delta_color="off"
                    )
                
                st.divider()
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("##### 📊 Monthly Gross Profit Comparison")
                    yoy_chart = SalespersonCharts.build_yoy_comparison_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gross_profit',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative Gross Profit")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gross_profit',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
            
            # Tab 3: GP1
            with yoy_tab3:
                current_total = yoy_sales_df['gp1_by_split_usd'].sum() if not yoy_sales_df.empty else 0
                previous_total = previous_sales_df['gp1_by_split_usd'].sum() if not previous_sales_df.empty else 0
                yoy_change = ((current_total - previous_total) / previous_total * 100) if previous_total > 0 else 0
                yoy_abs = current_total - previous_total
                
                col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
                with col_s1:
                    st.metric(
                        label=f"{primary_year} GP1",
                        value=f"${current_total:,.0f}",
                        delta=f"{yoy_change:+.1f}% YoY",
                        delta_color="normal" if yoy_change >= 0 else "inverse"
                    )
                with col_s2:
                    st.metric(
                        label=f"{primary_year - 1} GP1",
                        value=f"${previous_total:,.0f}",
                        delta=f"${yoy_abs:+,.0f} difference",
                        delta_color="off"
                    )
                
                st.divider()
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("##### 📊 Monthly GP1 Comparison")
                    yoy_chart = SalespersonCharts.build_yoy_comparison_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gp1',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative GP1")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gp1',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
        else:
            st.info(f"No data available for {primary_year - 1} comparison")


# =============================================================================
# FRAGMENT: SALES DETAIL TRANSACTION LIST (Tab 2)
# Lines 1611-1881 from original file - 100% code preserved
# UPDATED v2.3.0: Added summary metrics cards for consistency with Backlog List
# =============================================================================

@st.fragment
def sales_detail_fragment(
    sales_df: pd.DataFrame,
    overview_metrics: Dict,
    filter_values: Dict,
    fragment_key: str = "detail"
):
    """
    Fragment for Sales Detail transaction list with filters.
    
    100% code from original file lines 1611-1881.
    Includes: filters, original value calculation, formatting, export.
    
    UPDATED v2.3.0: Added summary metrics cards at top for consistency.
    """
    if sales_df.empty:
        st.info("No sales data for selected period")
        return
    
    # =================================================================
    # SUMMARY METRICS CARDS (UPDATED v2.10.0)
    # Added GP%/GP1% in delta display
    # =================================================================
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    total_revenue = sales_df['sales_by_split_usd'].sum()
    total_gp = sales_df['gross_profit_by_split_usd'].sum()
    total_gp1 = sales_df['gp1_by_split_usd'].sum()
    gp_percent = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
    gp1_percent = (total_gp1 / total_revenue * 100) if total_revenue > 0 else 0
    total_invoices = sales_df['inv_number'].nunique()
    total_orders = sales_df['oc_number'].nunique()
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
            delta=f"↑ {gp_percent:.1f}% margin",
            delta_color="off",
            help="Total gross profit (split-adjusted). Margin% = GP ÷ Revenue × 100"
        )
    with col_s3:
        st.metric(
            "📊 GP1",
            f"${total_gp1:,.0f}",
            delta=f"↑ {gp1_percent:.1f}% margin",
            delta_color="off",
            help="GP1 = GP - (Broker Commission × 1.2). Margin% = GP1 ÷ Revenue × 100"
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
        # Average GP per customer
        avg_gp_customer = total_gp / total_customers if total_customers > 0 else 0
        st.metric(
            "💵 Avg GP/Cust",
            f"${avg_gp_customer:,.0f}",
            delta_color="off",
            help="Average gross profit per customer"
        )
    
    st.divider()
    
    # =================================================================
    # IMPROVED FILTERS - MultiSelect with Excluded option
    # =================================================================
    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
    
    # Customer filter
    with col_f1:
        customer_options = sorted(sales_df['customer'].dropna().unique().tolist())
        customer_filter = render_multiselect_filter(
            label="Customer",
            options=customer_options,
            key=f"{fragment_key}_customer",
            placeholder="All customers..."
        )
    
    # Brand filter
    with col_f2:
        brand_options = sorted(sales_df['brand'].dropna().unique().tolist())
        brand_filter = render_multiselect_filter(
            label="Brand",
            options=brand_options,
            key=f"{fragment_key}_brand",
            placeholder="All brands..."
        )
    
    # Product filter
    with col_f3:
        product_options = sorted(sales_df['product_pn'].dropna().unique().tolist())[:100]
        product_filter = render_multiselect_filter(
            label="Product",
            options=product_options,
            key=f"{fragment_key}_product",
            placeholder="All products..."
        )
    
    # OC# / Customer PO search
    with col_f4:
        oc_po_filter = render_text_search_filter(
            label="OC# / Customer PO",
            key=f"{fragment_key}_oc_po",
            placeholder="Search..."
        )
    
    # Min Amount filter
    with col_f5:
        amount_filter = render_number_filter(
            label="Min Amount ($)",
            key=f"{fragment_key}_min_amount",
            default_min=0,
            step=1000
        )
    
    # =================================================================
    # APPLY ALL FILTERS
    # =================================================================
    filtered_df = sales_df.copy()
    
    # Apply multiselect filters
    filtered_df = apply_multiselect_filter(filtered_df, 'customer', customer_filter)
    filtered_df = apply_multiselect_filter(filtered_df, 'brand', brand_filter)
    filtered_df = apply_multiselect_filter(filtered_df, 'product_pn', product_filter)
    
    # Apply text search on multiple columns
    filtered_df = apply_text_search_filter(
        filtered_df, 
        columns=['oc_number', 'customer_po_number'],
        search_result=oc_po_filter
    )
    
    # Apply number filter
    filtered_df = apply_number_filter(filtered_df, 'sales_by_split_usd', amount_filter)
    
    # =================================================================
    # Show filter summary
    # =================================================================
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
    
    # =================================================================
    # Calculate Original (pre-split) values
    # Formula: Original = Split Value / (Split % / 100)
    # Note: GP1 is calculated field, no "original" value exists
    # =================================================================
    filtered_df = filtered_df.copy()
    
    # Avoid division by zero
    split_pct = filtered_df['split_rate_percent'].replace(0, 100) / 100
    
    # Calculate original values (before split) - only Revenue and GP
    filtered_df['total_revenue_usd'] = filtered_df['sales_by_split_usd'] / split_pct
    filtered_df['total_gp_usd'] = filtered_df['gross_profit_by_split_usd'] / split_pct
    
    # =================================================================
    # NEW: Format Product as "pt_code | Name | Package size"
    # =================================================================
    def format_product_display(row):
        parts = []
        if pd.notna(row.get('pt_code')) and row.get('pt_code'):
            parts.append(str(row['pt_code']))
        if pd.notna(row.get('product_pn')) and row.get('product_pn'):
            parts.append(str(row['product_pn']))
        if pd.notna(row.get('package_size')) and row.get('package_size'):
            parts.append(str(row['package_size']))
        return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))
    
    filtered_df['product_display'] = filtered_df.apply(format_product_display, axis=1)
    
    # =================================================================
    # NEW: Format OC with Customer PO
    # Format: OC#\n(PO: xxx)
    # =================================================================
    def format_oc_po(row):
        oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
        po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
        if oc and po:
            return f"{oc}\n(PO: {po})"
        elif oc:
            return oc
        elif po:
            return f"(PO: {po})"
        return ''
    
    filtered_df['oc_po_display'] = filtered_df.apply(format_oc_po, axis=1)
    
    # =================================================================
    # UPDATED v2.10.0: Calculate GP% and GP1% as separate columns
    # =================================================================
    def calc_gp_percent(row):
        """Calculate GP margin percentage."""
        gp = row.get('gross_profit_by_split_usd', 0) or 0
        revenue = row.get('sales_by_split_usd', 0) or 0
        if revenue > 0:
            return (gp / revenue) * 100
        return 0.0
    
    def calc_gp1_percent(row):
        """Calculate GP1 margin percentage."""
        gp1 = row.get('gp1_by_split_usd', 0) or 0
        revenue = row.get('sales_by_split_usd', 0) or 0
        if revenue > 0:
            return (gp1 / revenue) * 100
        return 0.0
    
    filtered_df['gp_percent'] = filtered_df.apply(calc_gp_percent, axis=1)
    filtered_df['gp1_percent'] = filtered_df.apply(calc_gp1_percent, axis=1)
    
    # Display columns - reordered with separate % columns
    # UPDATED v2.10.0: Separate GP%, GP1% columns instead of inline
    display_columns = [
        'inv_date', 'inv_number', 'oc_po_display', 'customer', 'product_display', 'brand',
        'total_revenue_usd', 'total_gp_usd',  # Original values (Revenue, GP only)
        'split_rate_percent',
        'sales_by_split_usd', 'gross_profit_by_split_usd', 'gp_percent', 'gp1_by_split_usd', 'gp1_percent',
        'sales_name'
    ]
    available_cols = [c for c in display_columns if c in filtered_df.columns]
    
    # Prepare display dataframe (UPDATED v2.10.0: increased limit to 5000)
    DISPLAY_LIMIT = 5000
    total_filtered = len(filtered_df)
    display_detail = filtered_df[available_cols].head(DISPLAY_LIMIT).copy()
    
    # Show transaction count with warning if truncated
    if total_filtered > DISPLAY_LIMIT:
        st.markdown(f"**Showing {DISPLAY_LIMIT:,} of {total_filtered:,} transactions** (filtered from {len(sales_df):,} total)")
        st.warning(f"⚠️ Display limited to {DISPLAY_LIMIT:,} rows for performance. Click **Export Filtered View** below to download all {total_filtered:,} transactions.")
    else:
        st.markdown(f"**Showing {total_filtered:,} transactions** (of {len(sales_df):,} total)")
    
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
            help="💰 ORIGINAL invoice revenue (100% of line item)\n\nThis is the full value BEFORE applying sales split.",
            format="$%.0f"
        ),
        'total_gp_usd': st.column_config.NumberColumn(
            "Total GP",
            help="📈 ORIGINAL gross profit (100% of line item)\n\nFormula: Revenue - COGS\n\nThis is the full GP BEFORE applying sales split.",
            format="$%.0f"
        ),
        # Split percentage
        'split_rate_percent': st.column_config.NumberColumn(
            "Split %",
            help="👥 Sales credit split percentage\n\nThis salesperson receives this % of the total revenue/GP/GP1.\n\n100% = Full credit\n50% = Shared equally with another salesperson",
            format="%.0f%%"
        ),
        # Split values (after split) - UPDATED v2.10.0: Separate columns
        'sales_by_split_usd': st.column_config.NumberColumn(
            "Revenue",
            help="💰 CREDITED revenue for this salesperson\n\n📐 Formula: Total Revenue × Split %",
            format="$%.0f"
        ),
        'gross_profit_by_split_usd': st.column_config.NumberColumn(
            "GP",
            help="📈 CREDITED gross profit for this salesperson\n\n📐 Formula: Total GP × Split %",
            format="$%.0f"
        ),
        'gp_percent': st.column_config.NumberColumn(
            "GP%",
            help="📈 Gross Profit Margin %\n\n📐 Formula: GP ÷ Revenue × 100\n\nHigher % = better margin",
            format="%.1f%%"
        ),
        'gp1_by_split_usd': st.column_config.NumberColumn(
            "GP1",
            help="📊 CREDITED GP1 for this salesperson\n\n📐 Formula: (GP - Broker Commission × 1.2) × Split %",
            format="$%.0f"
        ),
        'gp1_percent': st.column_config.NumberColumn(
            "GP1%",
            help="📊 GP1 Margin %\n\n📐 Formula: GP1 ÷ Revenue × 100\n\nGP1 = GP after broker commission deduction",
            format="%.1f%%"
        ),
        'sales_name': st.column_config.TextColumn(
            "Salesperson",
            help="Salesperson receiving credit for this transaction"
        ),
    }
    
    # Display table with column configuration
    st.dataframe(
        display_detail,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=600  # Increased height for more rows
    )
    
    # Legend for quick reference
    with st.expander("📖 Column Legend", expanded=False):
        st.markdown("""
        | Column | Description | Formula |
        |--------|-------------|---------|
        | **OC / PO** | Order Confirmation & Customer PO | Combined display |
        | **Product** | PT Code \| Name \| Package Size | Formatted product info |
        | **Total Revenue** | Original invoice amount (100%) | Full line item value |
        | **Total GP** | Original gross profit (100%) | Revenue - COGS |
        | **Split %** | Credit allocation to salesperson | Assigned by sales split rules |
        | **Revenue** | Credited revenue | Total Revenue × Split % |
        | **GP** | Credited gross profit | Total GP × Split % |
        | **GP%** | Gross profit margin | GP ÷ Revenue × 100 |
        | **GP1** | Credited GP1 | (GP - Broker Commission × 1.2) × Split % |
        | **GP1%** | GP1 margin | GP1 ÷ Revenue × 100 |
        
        > 💡 **Note:** Higher margin % = better profitability. GP1% accounts for broker commissions.
        
        > 💡 **Tip:** Hover over column headers to see detailed tooltips.
        """)
    
    # Export filtered view button (quick export of current filtered data)
    st.caption("💡 For full report with all data, use **Export Report** in Overview tab")
    
    # Dynamic help text based on whether data is truncated
    export_help = f"Export all {total_filtered:,} filtered transactions to Excel" if total_filtered > DISPLAY_LIMIT else "Export the filtered transactions shown above"
    
    if st.button("📥 Export Filtered View", key=f"{fragment_key}_export", help=export_help):
        exporter = SalespersonExport()
        excel_bytes = exporter.create_report(
            summary_df=pd.DataFrame(),
            monthly_df=pd.DataFrame(),
            metrics=overview_metrics,
            filters=filter_values,
            detail_df=filtered_df  # Export ALL filtered data, not just displayed 500
        )
        st.download_button(
            label=f"⬇️ Download {total_filtered:,} Transactions",
            data=excel_bytes,
            file_name=f"sales_filtered_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# =============================================================================
# FRAGMENT: PIVOT ANALYSIS (Tab 2)
# Lines 1883-1928 from original file - 100% code preserved
# =============================================================================

@st.fragment
def pivot_analysis_fragment(
    sales_df: pd.DataFrame,
    fragment_key: str = "pivot"
):
    """
    Fragment for Pivot Analysis with configurable rows/columns/metric.
    
    100% code from original file lines 1883-1928.
    """
    if sales_df.empty:
        st.info("No data for pivot analysis")
        return
    
    st.markdown("#### 📊 Pivot Analysis")
    
    # Pivot configuration
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        row_options = ['customer', 'brand', 'sales_name', 'product_pn', 'legal_entity']
        pivot_rows = st.selectbox("Rows", row_options, index=0, key=f"{fragment_key}_rows")
    
    with col_p2:
        col_options = ['invoice_month', 'brand', 'customer', 'sales_name']
        pivot_cols = st.selectbox("Columns", col_options, index=0, key=f"{fragment_key}_cols")
    
    with col_p3:
        value_options = ['sales_by_split_usd', 'gross_profit_by_split_usd', 'gp1_by_split_usd']
        pivot_values = st.selectbox("Values", value_options, index=1, key=f"{fragment_key}_values",
                                   format_func=lambda x: x.replace('_by_split_usd', '').replace('_', ' ').title())
    
    # Create pivot
    if pivot_rows in sales_df.columns and pivot_cols in sales_df.columns:
        pivot_df = sales_df.pivot_table(
            values=pivot_values,
            index=pivot_rows,
            columns=pivot_cols,
            aggfunc='sum',
            fill_value=0
        )
        
        # Add totals
        pivot_df['Total'] = pivot_df.sum(axis=1)
        pivot_df = pivot_df.sort_values('Total', ascending=False)
        
        # Reorder columns (months)
        if pivot_cols == 'invoice_month':
            month_cols = [m for m in MONTH_ORDER if m in pivot_df.columns]
            other_cols = [c for c in pivot_df.columns if c not in MONTH_ORDER and c != 'Total']
            pivot_df = pivot_df[month_cols + other_cols + ['Total']]
        
        st.dataframe(
            pivot_df.style.format("${:,.0f}").background_gradient(cmap='Blues', subset=['Total']),
            use_container_width=True,
            height=500
        )
    else:
        st.warning("Selected columns not available in data")


# =============================================================================
# FRAGMENT: BACKLOG LIST (Tab 3)
# Lines 1969-2237 from original file - 100% code preserved
# =============================================================================

@st.fragment
def backlog_list_fragment(
    backlog_df: pd.DataFrame,
    in_period_backlog_analysis: Dict,
    total_backlog_df: pd.DataFrame = None,  # NEW v2.1.0: for accurate totals
    fragment_key: str = "backlog"
):
    """
    Fragment for Backlog List with filters.
    
    100% code from original file lines 1969-2237.
    Includes: summary cards, filters, formatting, display.
    
    UPDATED v2.1.0: Added total_backlog_df parameter
    - When provided, uses aggregated values for summary cards
    - When not provided (backward compat), calculates from backlog_df
    """
    if backlog_df.empty:
        st.info("📦 No backlog data available")
        return
    
    # Summary cards - Combined Total + In-Period + Overdue info
    # UPDATED v2.10.0: Added GP% in delta display
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    # FIXED v2.8.0: Always calculate from backlog_df (backlog_detail) instead of total_backlog_df
    total_backlog_value = backlog_df['backlog_sales_by_split_usd'].sum()
    total_backlog_gp = backlog_df['backlog_gp_by_split_usd'].sum()
    total_backlog_gp_percent = (total_backlog_gp / total_backlog_value * 100) if total_backlog_value > 0 else 0
    total_orders = backlog_df['oc_number'].nunique()
    total_customers = backlog_df['customer_id'].nunique()
    
    with col_s1:
        st.metric(
            "💰 Total Backlog", 
            f"${total_backlog_value:,.0f}", 
            f"{total_orders:,} orders",
            delta_color="off",
            help="All pending orders from selected employees (not filtered by date)"
        )
    with col_s2:
        st.metric(
            "📈 Total GP", 
            f"${total_backlog_gp:,.0f}",
            f"↑ {total_backlog_gp_percent:.1f}% margin",
            delta_color="off",
            help="Total gross profit from all pending orders. Margin% = GP ÷ Backlog × 100"
        )
    with col_s3:
        in_period_value = in_period_backlog_analysis.get('total_value', 0)
        in_period_count = in_period_backlog_analysis.get('total_count', 0)
        st.metric(
            "📅 In-Period",
            f"${in_period_value:,.0f}",
            f"{in_period_count:,} orders",
            delta_color="off",
            help="Backlog with ETD within selected date range (all selected employees)"
        )
    with col_s4:
        in_period_gp = in_period_backlog_analysis.get('total_gp', 0)
        in_period_gp_percent = (in_period_gp / in_period_value * 100) if in_period_value > 0 else 0
        st.metric(
            "📊 In-Period GP",
            f"${in_period_gp:,.0f}",
            f"↑ {in_period_gp_percent:.1f}% margin",
            delta_color="off",
            help="Gross profit from in-period backlog. Margin% = GP ÷ In-Period × 100"
        )
    with col_s5:
        on_track_value = in_period_backlog_analysis.get('on_track_value', 0)
        on_track_count = in_period_backlog_analysis.get('on_track_count', 0)
        st.metric(
            "✅ On Track",
            f"${on_track_value:,.0f}",
            f"{on_track_count:,} orders",
            delta_color="off",
            help="In-period orders with ETD ≥ today (still on schedule)"
        )
    with col_s6:
        overdue_value = in_period_backlog_analysis.get('overdue_value', 0)
        overdue_count = in_period_backlog_analysis.get('overdue_count', 0)
        st.metric(
            "⚠️ Overdue",
            f"${overdue_value:,.0f}",
            f"{overdue_count:,} orders",
            delta_color="inverse" if overdue_count > 0 else "off",
            help="In-period orders with ETD < today (past due, needs attention)"
        )
    with col_s7:
        # FIXED v2.8.0: Proper status display based on actual status value
        # Previously: any status != 'healthy' showed "HAS OVERDUE" (including 'empty')
        # Now: properly distinguish between healthy, has_overdue, empty, and other states
        status = in_period_backlog_analysis.get('status', 'unknown')
        overdue_count = in_period_backlog_analysis.get('overdue_count', 0)
        in_period_count = in_period_backlog_analysis.get('total_count', 0)
        
        if status == 'has_overdue' or overdue_count > 0:
            status_display = "HAS OVERDUE ⚠️"
            help_text = "Some in-period orders have ETD < today (past due, needs attention)"
        elif status == 'healthy' or (in_period_count > 0 and overdue_count == 0):
            status_display = "HEALTHY ✅"
            help_text = "All in-period orders are on track (ETD ≥ today)"
        elif status == 'empty' or in_period_count == 0:
            status_display = "NO IN-PERIOD"
            help_text = "No orders with ETD within selected date range"
        else:
            status_display = "N/A"
            help_text = "Status could not be determined"
        
        st.metric(
            "📊 Status",
            status_display,
            help=help_text
        )
    
    st.divider()
    
    # =================================================================
    # IMPROVED FILTERS - MultiSelect with Excluded option
    # =================================================================
    col_bf1, col_bf2, col_bf3, col_bf4, col_bf5 = st.columns(5)
    
    # Customer filter
    with col_bf1:
        bl_customer_options = sorted(backlog_df['customer'].dropna().unique().tolist())
        bl_customer_filter = render_multiselect_filter(
            label="Customer",
            options=bl_customer_options,
            key=f"{fragment_key}_customer",
            placeholder="All customers..."
        )
    
    # Brand filter
    with col_bf2:
        bl_brand_options = sorted(backlog_df['brand'].dropna().unique().tolist())
        bl_brand_filter = render_multiselect_filter(
            label="Brand",
            options=bl_brand_options,
            key=f"{fragment_key}_brand",
            placeholder="All brands..."
        )
    
    # Product filter
    with col_bf3:
        bl_product_options = sorted(backlog_df['product_pn'].dropna().unique().tolist())[:100]
        bl_product_filter = render_multiselect_filter(
            label="Product",
            options=bl_product_options,
            key=f"{fragment_key}_product",
            placeholder="All products..."
        )
    
    # OC# / Customer PO search
    with col_bf4:
        bl_oc_po_filter = render_text_search_filter(
            label="OC# / Customer PO",
            key=f"{fragment_key}_oc_po",
            placeholder="Search..."
        )
    
    # Status filter
    with col_bf5:
        bl_status_options = backlog_df['pending_type'].dropna().unique().tolist()
        bl_status_filter = render_multiselect_filter(
            label="Status",
            options=bl_status_options,
            key=f"{fragment_key}_status",
            placeholder="All statuses..."
        )
    
    # =================================================================
    # APPLY ALL FILTERS
    # =================================================================
    filtered_backlog = backlog_df.copy()
    
    # Apply multiselect filters
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'customer', bl_customer_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'brand', bl_brand_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'product_pn', bl_product_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'pending_type', bl_status_filter)
    
    # Apply text search on multiple columns
    filtered_backlog = apply_text_search_filter(
        filtered_backlog, 
        columns=['oc_number', 'customer_po_number'] if 'customer_po_number' in backlog_df.columns else ['oc_number'],
        search_result=bl_oc_po_filter
    )
    
    # =================================================================
    # Show filter summary
    # =================================================================
    active_bl_filters = []
    if bl_customer_filter.is_active:
        mode = "excl" if bl_customer_filter.excluded else "incl"
        active_bl_filters.append(f"Customer: {len(bl_customer_filter.selected)} ({mode})")
    if bl_brand_filter.is_active:
        mode = "excl" if bl_brand_filter.excluded else "incl"
        active_bl_filters.append(f"Brand: {len(bl_brand_filter.selected)} ({mode})")
    if bl_product_filter.is_active:
        mode = "excl" if bl_product_filter.excluded else "incl"
        active_bl_filters.append(f"Product: {len(bl_product_filter.selected)} ({mode})")
    if bl_oc_po_filter.is_active:
        mode = "excl" if bl_oc_po_filter.excluded else "incl"
        active_bl_filters.append(f"OC/PO: '{bl_oc_po_filter.query}' ({mode})")
    if bl_status_filter.is_active:
        mode = "excl" if bl_status_filter.excluded else "incl"
        active_bl_filters.append(f"Status: {len(bl_status_filter.selected)} ({mode})")
    
    if active_bl_filters:
        st.caption(f"🔍 Active filters: {' | '.join(active_bl_filters)}")
    
    # =================================================================
    # NEW: Format Product as "pt_code | Name | Package size"
    # =================================================================
    def format_product_display(row):
        parts = []
        if pd.notna(row.get('pt_code')) and row.get('pt_code'):
            parts.append(str(row['pt_code']))
        if pd.notna(row.get('product_pn')) and row.get('product_pn'):
            parts.append(str(row['product_pn']))
        if pd.notna(row.get('package_size')) and row.get('package_size'):
            parts.append(str(row['package_size']))
        return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))
    
    filtered_backlog = filtered_backlog.copy()
    filtered_backlog['product_display'] = filtered_backlog.apply(format_product_display, axis=1)
    
    # =================================================================
    # NEW: Format OC with Customer PO
    # =================================================================
    def format_oc_po(row):
        oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
        po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
        if oc and po:
            return f"{oc}\n(PO: {po})"
        elif oc:
            return oc
        elif po:
            return f"(PO: {po})"
        return ''
    
    filtered_backlog['oc_po_display'] = filtered_backlog.apply(format_oc_po, axis=1)
    
    # =================================================================
    # UPDATED v2.10.0: Calculate GP% as separate column
    # =================================================================
    def calc_backlog_gp_percent(row):
        """Calculate backlog GP margin percentage."""
        gp = row.get('backlog_gp_by_split_usd', 0) or 0
        amount = row.get('backlog_sales_by_split_usd', 0) or 0
        if amount > 0:
            return (gp / amount) * 100
        return 0.0
    
    filtered_backlog['gp_percent'] = filtered_backlog.apply(calc_backlog_gp_percent, axis=1)
    
    # Display with column configuration (UPDATED v2.10.0: increased limit to 5000)
    BACKLOG_DISPLAY_LIMIT = 5000
    total_backlog_filtered = len(filtered_backlog)
    
    # UPDATED v2.10.0: Separate GP and GP% columns
    backlog_display_cols = ['oc_po_display', 'oc_date', 'etd', 'customer', 'product_display', 'brand',
                           'backlog_sales_by_split_usd', 'backlog_gp_by_split_usd', 'gp_percent',
                           'days_until_etd', 'pending_type', 'sales_name']
    available_bl_cols = [c for c in backlog_display_cols if c in filtered_backlog.columns]
    
    display_bl = filtered_backlog[available_bl_cols].head(BACKLOG_DISPLAY_LIMIT).copy()
    
    # Show count with warning if truncated
    if total_backlog_filtered > BACKLOG_DISPLAY_LIMIT:
        st.markdown(f"**Showing {BACKLOG_DISPLAY_LIMIT:,} of {total_backlog_filtered:,} backlog items** (filtered from {len(backlog_df):,} total)")
        st.warning(f"⚠️ Display limited to {BACKLOG_DISPLAY_LIMIT:,} rows. Use **Export Report** in Overview tab to download all {total_backlog_filtered:,} items.")
    else:
        st.markdown(f"**Showing {total_backlog_filtered:,} backlog items** (of {len(backlog_df):,} total)")
    
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
        'backlog_sales_by_split_usd': st.column_config.NumberColumn(
            "Amount",
            help="Backlog amount (split-adjusted)",
            format="$%.0f"
        ),
        # UPDATED v2.10.0: Separate GP and GP% columns
        'backlog_gp_by_split_usd': st.column_config.NumberColumn(
            "GP",
            help="📈 Backlog gross profit (split-adjusted)",
            format="$%.0f"
        ),
        'gp_percent': st.column_config.NumberColumn(
            "GP%",
            help="📈 Gross Profit Margin %\n\n📐 Formula: GP ÷ Amount × 100\n\nHigher % = better margin",
            format="%.1f%%"
        ),
        'days_until_etd': st.column_config.NumberColumn(
            "Days to ETD",
            help="Days until ETD (negative = overdue)"
        ),
        'pending_type': st.column_config.TextColumn(
            "Status",
            help="Both Pending / Delivery Pending / Invoice Pending"
        ),
        'sales_name': st.column_config.TextColumn(
            "Salesperson",
            help="Salesperson receiving credit"
        ),
    }
    
    st.dataframe(
        display_bl,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=600  # Increased height for more rows
    )

# =============================================================================
# FRAGMENT: BACKLOG BY ETD MONTH (NEW v2.5.0)
# Multi-year view with Timeline/Stacked/Single Year modes
# =============================================================================

@st.fragment
def backlog_by_etd_fragment(
    backlog_by_month_df: pd.DataFrame,
    metrics_calc,  # SalespersonMetrics instance
    current_year: int,
    fragment_key: str = "backlog_etd"
):
    """
    Fragment for Backlog by ETD Month with multi-year support.
    
    Runs independently - changing view mode won't reload entire page.
    
    Features:
    - Timeline: Chronological view "Jan'25, Feb'25, ..., Jan'26"
    - Stacked by Month: Compare same months across years
    - Single Year: Original behavior with year selector
    
    Args:
        backlog_by_month_df: Raw backlog data grouped by ETD year/month
        metrics_calc: SalespersonMetrics instance for data preparation
        current_year: Current filter year (for Single Year default)
        fragment_key: Unique key prefix for widgets
        
    CHANGELOG:
    - v1.0.0: Initial implementation for multi-year backlog view
    """
    from .charts import SalespersonCharts
    from .constants import MONTH_ORDER
    
    st.markdown("#### 📅 Backlog by ETD Month")
    
    # Check if we have backlog data
    if backlog_by_month_df.empty:
        st.info("No backlog data available")
        return
    
    # Get unique years
    df_years = backlog_by_month_df.copy()
    df_years['etd_year'] = pd.to_numeric(df_years['etd_year'], errors='coerce').fillna(0).astype(int)
    unique_years = sorted(df_years['etd_year'].unique())
    
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
    
    if view_mode == "Timeline":
        # =============================================================
        # TIMELINE VIEW - Chronological across all years
        # =============================================================
        backlog_monthly = metrics_calc.prepare_backlog_by_month_multiyear(
            backlog_by_month_df=backlog_by_month_df,
            include_empty_months=False
        )
        
        if not backlog_monthly.empty and backlog_monthly['backlog_revenue'].sum() > 0:
            chart = SalespersonCharts.build_backlog_by_month_chart_multiyear(
                monthly_df=backlog_monthly,
                title="",
                color_by_year=True,
                show_totals_by_year=True
            )
            st.altair_chart(chart, use_container_width=True)
            
            # Data table with year info
            display_cols = ['year_month', 'etd_year', 'backlog_revenue', 'backlog_gp', 'order_count']
            display_cols = [c for c in display_cols if c in backlog_monthly.columns]
            
            st.dataframe(
                backlog_monthly[display_cols].style.format({
                    'backlog_revenue': '${:,.0f}',
                    'backlog_gp': '${:,.0f}',
                    'order_count': '{:,.0f}'
                }),
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
        backlog_monthly = metrics_calc.prepare_backlog_by_month_multiyear(
            backlog_by_month_df=backlog_by_month_df,
            include_empty_months=False
        )
        
        if not backlog_monthly.empty and backlog_monthly['backlog_revenue'].sum() > 0:
            chart = SalespersonCharts.build_backlog_by_month_stacked(
                monthly_df=backlog_monthly,
                title=""
            )
            st.altair_chart(chart, use_container_width=True)
            
            # Pivot table: months as rows, years as columns
            pivot_df = backlog_monthly.pivot_table(
                index='etd_month',
                columns='etd_year',
                values='backlog_revenue',
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
            if current_year in unique_years:
                default_idx = unique_years.index(current_year)
            
            selected_year = st.selectbox(
                "Select Year",
                options=unique_years,
                index=default_idx,
                key=f"{fragment_key}_year_select"
            )
        
        backlog_monthly = metrics_calc.prepare_backlog_by_month(
            backlog_by_month_df=backlog_by_month_df,
            year=selected_year
        )
        
        if not backlog_monthly.empty and backlog_monthly['backlog_revenue'].sum() > 0:
            chart = SalespersonCharts.build_backlog_by_month_chart(
                monthly_df=backlog_monthly,
                title=f"Backlog by ETD Month - {selected_year}"
            )
            st.altair_chart(chart, use_container_width=True)
            
            # Monthly table
            st.dataframe(
                backlog_monthly[['month', 'backlog_revenue', 'backlog_gp', 'order_count']].style.format({
                    'backlog_revenue': '${:,.0f}',
                    'backlog_gp': '${:,.0f}',
                }),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info(f"No backlog data for {selected_year}")


# =============================================================================
# FRAGMENT: EXPORT REPORT (UPDATED v2.5.0)
# Generates Excel report fully synchronized with UI
# - v2.5.0: Added Overall Achievement, KPI Breakdown, Multi-year Backlog
# - v2.4.0: Initial fragment version
# =============================================================================

@st.fragment
def export_report_fragment(
    # Metrics data
    overview_metrics: Dict,
    complex_kpis: Dict,
    pipeline_forecast_metrics: Dict,
    yoy_metrics: Dict,
    in_period_backlog_analysis: Dict,
    # Filter settings
    filter_values: Dict,
    # Raw data for export
    sales_df: pd.DataFrame,
    total_backlog_df: pd.DataFrame,
    backlog_detail_df: pd.DataFrame,
    backlog_by_month_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    # NEW v2.7.0: Raw complex KPI dataframes for per-salesperson calculation
    new_customers_df: pd.DataFrame = None,
    new_products_df: pd.DataFrame = None,
    new_business_df: pd.DataFrame = None,
    # Metrics calculator
    metrics_calc = None,  # SalespersonMetrics instance
    # NEW v2.5.0: KPI type weights for Overall Achievement calculation
    kpi_type_weights: Dict[str, int] = None,
    fragment_key: str = "export"
):
    """
    Fragment for Excel export - runs independently without page reload.
    
    UPDATED v2.5.0: Full sync with UI - includes Overall Achievement & KPI Breakdown.
    """
    from .export import SalespersonExport
    
    with st.expander("📥 Export Report", expanded=False):
        st.markdown("""
**Export includes 9 sheets (synced with UI):**
- Summary & KPIs (with Overall Achievement) ✨
- KPI Breakdown (NEW) ✨
- Pipeline & Forecast  
- By Salesperson
- Monthly Trend
- Sales Detail
- Backlog Summary
- Backlog Detail
- Backlog by ETD (Multi-year) ✨
        """)
        
        col_exp1, col_exp2 = st.columns([1, 1])
        
        with col_exp1:
            generate_clicked = st.button(
                "📊 Generate Report", 
                use_container_width=True, 
                key=f"{fragment_key}_generate"
            )
        
        # Generate report when button clicked
        if generate_clicked:
            with st.spinner("Generating Excel report..."):
                try:
                    # ==========================================================
                    # STEP 1: Calculate Salesperson Summary
                    # ==========================================================
                    salesperson_summary_df = metrics_calc.aggregate_by_salesperson(
                        period_type=filter_values.get('period_type', 'YTD'),
                        year=filter_values.get('year', datetime.now().year),
                        new_customers_df=new_customers_df,
                        new_products_df=new_products_df,
                        new_business_df=new_business_df
                    )
                    monthly_df = metrics_calc.prepare_monthly_summary()
                    
                    # ==========================================================
                    # STEP 2: Calculate Overall Achievement (NEW v2.5.0)
                    # This syncs with UI's Overview tab KPI Progress
                    # ==========================================================
                    overall_achievement_data = None
                    try:
                        overall_achievement_data = metrics_calc.calculate_overall_kpi_achievement(
                            overview_metrics=overview_metrics,
                            complex_kpis=complex_kpis,
                            period_type=filter_values.get('period_type', 'YTD'),
                            year=filter_values.get('year', datetime.now().year),
                            kpi_type_weights=kpi_type_weights,
                            new_customers_df=new_customers_df,
                            new_products_df=new_products_df,
                            new_business_df=new_business_df
                        )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(f"Could not calculate overall achievement: {e}")
                    
                    # ==========================================================
                    # STEP 3: Prepare Backlog by Month (Multi-year support)
                    # ==========================================================
                    prepared_backlog_by_month = None
                    prepared_backlog_by_month_multiyear = None
                    
                    if not backlog_by_month_df.empty:
                        # Check if multi-year data exists
                        if 'etd_year' in backlog_by_month_df.columns:
                            unique_years = backlog_by_month_df['etd_year'].dropna().unique()
                            
                            if len(unique_years) > 1:
                                # Multi-year: use prepare_backlog_by_month_multiyear if available
                                if hasattr(metrics_calc, 'prepare_backlog_by_month_multiyear'):
                                    prepared_backlog_by_month_multiyear = metrics_calc.prepare_backlog_by_month_multiyear(
                                        backlog_by_month_df=backlog_by_month_df,
                                        include_empty_months=False
                                    )
                                else:
                                    # Fallback: create simple multi-year format
                                    prepared_backlog_by_month_multiyear = backlog_by_month_df.copy()
                                    if 'etd_month' in prepared_backlog_by_month_multiyear.columns:
                                        prepared_backlog_by_month_multiyear['year_month'] = (
                                            prepared_backlog_by_month_multiyear['etd_month'].astype(str) + "'" +
                                            prepared_backlog_by_month_multiyear['etd_year'].astype(str).str[-2:]
                                        )
                                        prepared_backlog_by_month_multiyear['sort_order'] = (
                                            prepared_backlog_by_month_multiyear['etd_year'] * 100 +
                                            prepared_backlog_by_month_multiyear['etd_month']
                                        )
                            else:
                                # Single year: use legacy method
                                prepared_backlog_by_month = metrics_calc.prepare_backlog_by_month(
                                    backlog_by_month_df=backlog_by_month_df,
                                    year=filter_values.get('year', datetime.now().year)
                                )
                        else:
                            # Fallback to single year
                            prepared_backlog_by_month = metrics_calc.prepare_backlog_by_month(
                                backlog_by_month_df=backlog_by_month_df,
                                year=filter_values.get('year', datetime.now().year)
                            )
                    
                    # ==========================================================
                    # STEP 4: Generate Comprehensive Report
                    # ==========================================================
                    exporter = SalespersonExport()
                    excel_bytes = exporter.create_comprehensive_report(
                        # Summary metrics
                        metrics=overview_metrics,
                        complex_kpis=complex_kpis,
                        pipeline_metrics=pipeline_forecast_metrics,
                        filters=filter_values,
                        yoy_metrics=yoy_metrics,
                        
                        # NEW v2.5.0: Overall Achievement (synced with UI)
                        overall_achievement_data=overall_achievement_data,
                        
                        # Salesperson & Monthly
                        salesperson_summary_df=salesperson_summary_df,
                        monthly_df=monthly_df,
                        
                        # Sales Detail
                        sales_detail_df=sales_df,
                        
                        # Backlog data
                        backlog_summary_df=total_backlog_df,
                        backlog_detail_df=backlog_detail_df,
                        backlog_by_month_df=prepared_backlog_by_month,
                        in_period_backlog_analysis=in_period_backlog_analysis,
                        
                        # NEW v2.5.0: Multi-year backlog support
                        backlog_by_month_multiyear_df=prepared_backlog_by_month_multiyear,
                    )
                    
                    # Store in session state for download button
                    st.session_state[f'{fragment_key}_excel_bytes'] = excel_bytes
                    st.session_state[f'{fragment_key}_ready'] = True
                    st.success("✅ Report generated with full UI sync!")
                    
                except Exception as e:
                    st.error(f"Error generating report: {str(e)}")
                    import logging
                    import traceback
                    logging.getLogger(__name__).error(f"Export error: {e}\n{traceback.format_exc()}")
        
        # Show download button if report is ready
        with col_exp2:
            if st.session_state.get(f'{fragment_key}_ready'):
                st.download_button(
                    label="⬇️ Download Excel",
                    data=st.session_state[f'{fragment_key}_excel_bytes'],
                    file_name=f"salesperson_performance_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key=f"{fragment_key}_download"
                )
            else:
                st.button(
                    "⬇️ Download Excel",
                    disabled=True,
                    use_container_width=True,
                    key=f"{fragment_key}_download_disabled",
                    help="Click 'Generate Report' first"
                )


# =============================================================================
# FRAGMENT: TEAM RANKING (NEW v2.6.0)
# Prevents page rerun when changing ranking dropdown
# =============================================================================

@st.fragment
def team_ranking_fragment(
    salesperson_summary_df: pd.DataFrame,
    fragment_key: str = "ranking"
):
    """
    Fragment for Team Ranking with dropdown selector.
    
    NEW v2.6.0: Prevents full page rerun when changing ranking criteria.
    
    Args:
        salesperson_summary_df: DataFrame from metrics_calc.aggregate_by_salesperson()
        fragment_key: Unique key prefix for widgets
    """
    st.markdown("#### 🏆 Team Ranking")
    
    if salesperson_summary_df.empty or len(salesperson_summary_df) <= 1:
        st.info("Need multiple salespeople to show ranking")
        return
    
    # --- Ranking Criteria Selector ---
    ranking_options = {
        'Revenue': 'revenue',
        'Gross Profit': 'gross_profit',
        'GP1': 'gp1',
        'GP %': 'gp_percent',
        'KPI Achievement %': 'kpi_achievement'
    }
    
    selected_ranking = st.selectbox(
        "📊 Rank by",
        options=list(ranking_options.keys()),
        index=4,  # Default: KPI Achievement %
        key=f"{fragment_key}_criteria"
    )
    
    sort_col = ranking_options[selected_ranking]
    
    # --- Prepare data with GP1% ---
    ranking_df = salesperson_summary_df.copy()
    
    # Calculate GP1%
    ranking_df['gp1_percent'] = (
        ranking_df['gp1'] / ranking_df['revenue'] * 100
    ).round(2).fillna(0)
    
    # UPDATED v2.7.0: Use overall_achievement directly if available
    # This is the weighted average of ALL KPIs (Revenue, GP, GP1) calculated in metrics
    if 'overall_achievement' in ranking_df.columns:
        ranking_df['kpi_achievement'] = ranking_df['overall_achievement'].fillna(0)
    elif 'revenue_achievement' in ranking_df.columns and 'gp_achievement' in ranking_df.columns:
        # Fallback: average of revenue & GP achievement
        ranking_df['kpi_achievement'] = ranking_df.apply(
            lambda row: (
                (row['revenue_achievement'] + row['gp_achievement']) / 2
                if row['revenue_achievement'] > 0 and row['gp_achievement'] > 0
                else row['revenue_achievement'] if row['revenue_achievement'] > 0
                else row['gp_achievement'] if row['gp_achievement'] > 0
                else 0
            ),
            axis=1
        ).round(1)
    elif 'revenue_achievement' in ranking_df.columns:
        ranking_df['kpi_achievement'] = ranking_df['revenue_achievement']
    elif 'gp_achievement' in ranking_df.columns:
        ranking_df['kpi_achievement'] = ranking_df['gp_achievement']
    else:
        ranking_df['kpi_achievement'] = 0
    
    # --- Sort by selected criteria ---
    ranking_df = ranking_df.sort_values(sort_col, ascending=False).reset_index(drop=True)
    ranking_df.index = ranking_df.index + 1  # Start from 1
    
    # Add rank emoji
    def get_rank_emoji(rank):
        if rank == 1: return "🥇"
        elif rank == 2: return "🥈"
        elif rank == 3: return "🥉"
        else: return f"#{rank}"
    
    ranking_df.insert(0, 'Rank', ranking_df.index.map(get_rank_emoji))
    
    # --- Select display columns ---
    display_cols = ['Rank', 'sales_name', 'revenue', 'gross_profit', 'gp1', 'gp_percent', 'gp1_percent', 'customers']
    
    # Add KPI Achievement if available
    if 'kpi_achievement' in ranking_df.columns and ranking_df['kpi_achievement'].sum() > 0:
        display_cols.append('kpi_achievement')
    
    # Filter to available columns only
    display_cols = [c for c in display_cols if c in ranking_df.columns]
    ranking_df = ranking_df[display_cols]
    
    # Rename columns for display
    column_rename = {
        'sales_name': 'Salesperson',
        'revenue': 'Revenue',
        'gross_profit': 'Gross Profit',
        'gp1': 'GP1',
        'gp_percent': 'GP %',
        'gp1_percent': 'GP1 %',
        'customers': 'Customers',
        'kpi_achievement': 'Achievement %'
    }
    ranking_df = ranking_df.rename(columns=column_rename)
    
    # --- Format & Display ---
    format_dict = {
        'Revenue': '${:,.0f}',
        'Gross Profit': '${:,.0f}',
        'GP1': '${:,.0f}',
        'GP %': '{:.1f}%',
        'GP1 %': '{:.1f}%',
    }
    
    if 'Achievement %' in ranking_df.columns:
        format_dict['Achievement %'] = '{:.1f}%'
    
    # Highlight the sort column
    sort_col_display = selected_ranking if selected_ranking != 'KPI Achievement %' else 'Achievement %'
    
    def highlight_sort_column(col):
        if col.name == sort_col_display:
            return ['background-color: #fff3cd'] * len(col)
        return [''] * len(col)
    
    st.dataframe(
        ranking_df.style
            .format(format_dict)
            .apply(highlight_sort_column),
        use_container_width=True,
        hide_index=True
    )
    
    # Show ranking info
    st.caption(f"📌 Ranked by **{selected_ranking}** (highest first)")


# =============================================================================
# FRAGMENT: KPI PROGRESS - Hierarchical Card Layout (NEW v3.3.0)
# =============================================================================

def _get_achievement_style(achievement: float) -> Dict[str, str]:
    """
    Get color and icon based on achievement percentage.
    
    Returns:
        Dict with 'color', 'icon', 'status', 'bg_color'
    """
    if achievement is None:
        return {
            'color': '#6c757d',  # Gray
            'icon': '⚪',
            'status': 'N/A',
            'bg_color': '#f8f9fa'
        }
    elif achievement >= 100:
        return {
            'color': '#28a745',  # Green
            'icon': '✅',
            'status': 'On Track',
            'bg_color': '#d4edda'
        }
    elif achievement >= 80:
        return {
            'color': '#ffc107',  # Yellow
            'icon': '🟡',
            'status': 'Needs Push',
            'bg_color': '#fff3cd'
        }
    elif achievement >= 50:
        return {
            'color': '#fd7e14',  # Orange
            'icon': '🟠',
            'status': 'At Risk',
            'bg_color': '#ffe5d0'
        }
    else:
        return {
            'color': '#dc3545',  # Red
            'icon': '🔴',
            'status': 'Critical',
            'bg_color': '#f8d7da'
        }


def _get_rank_emoji(rank: int) -> str:
    """Get emoji for rank position."""
    if rank == 1:
        return "🥇"
    elif rank == 2:
        return "🥈"
    elif rank == 3:
        return "🥉"
    else:
        return f"#{rank}"


@st.fragment
def kpi_progress_fragment(
    # Data
    targets_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    salesperson_summary_df: pd.DataFrame,
    
    # Overall achievement
    overall_achievement_data: Dict,
    
    # KPI progress data (list of dicts with KPI breakdown)
    kpi_progress_data: List[Dict],
    
    # Filter context
    period_type: str,
    year: int,
    selected_employee_ids: List[int],
    
    # Optional: Complex KPI calculator for per-person calculation
    complex_kpi_calculator = None,
    start_date = None,
    end_date = None,
    
    # Fragment key
    fragment_key: str = "kpi_progress"
):
    """
    KPI Progress Fragment with Hierarchical Card Layout.
    
    NEW v3.3.0: Comprehensive view with:
    - Section 1: Team/Individual Overall Achievement summary
    - Section 2: KPI Breakdown by Type with sorting
    - Section 3: Individual Performance cards (when >1 person selected)
    
    Args:
        targets_df: KPI target assignments
        sales_df: Sales data
        salesperson_summary_df: Per-salesperson summary from aggregate_by_salesperson()
        overall_achievement_data: Dict with overall_achievement, kpi_count, kpi_details
        kpi_progress_data: List of dicts with KPI type breakdown
        period_type: YTD/QTD/MTD/LY/Custom
        year: Selected year
        selected_employee_ids: List of selected employee IDs
        complex_kpi_calculator: ComplexKPICalculator for per-person complex KPIs
        start_date: Period start date
        end_date: Period end date
        fragment_key: Unique key prefix
    """
    from datetime import date as date_type
    
    num_people = len(selected_employee_ids) if selected_employee_ids else 0
    is_single_person = num_people == 1
    
    # =========================================================================
    # SECTION 1: TEAM/INDIVIDUAL OVERALL ACHIEVEMENT
    # =========================================================================
    
    with st.container(border=True):
        # Header
        if is_single_person and not salesperson_summary_df.empty:
            person_name = salesperson_summary_df.iloc[0].get('sales_name', 'Salesperson')
            st.markdown(f"### 🎯 {person_name}'s KPI Achievement")
            st.caption("📐 Overall uses **individual KPI assignment weights**")
        else:
            st.markdown("### 🎯 Team Overall Achievement")
            st.caption("📐 Overall uses **KPI Type default weights** (aggregated across selected employees)")
        
        # Summary cards row
        col1, col2, col3, col4 = st.columns(4)
        
        # Overall Achievement
        overall_pct = overall_achievement_data.get('overall_achievement')
        style = _get_achievement_style(overall_pct)
        
        # Different help text for Team vs Individual
        if is_single_person:
            overall_help = "Individual Overall: Weighted avg using assigned KPI weights. Formula: Σ(KPI_Achievement × assignment_weight) / Σ(assignment_weight)"
        else:
            overall_help = "Team Overall: Weighted avg using KPI Type default weights. Formula: Σ(KPI_Type_Achievement × default_weight) / Σ(default_weight). Actual and targets aggregated across all selected employees."
        
        with col1:
            if overall_pct is not None:
                st.metric(
                    label="Overall Achievement",
                    value=f"{overall_pct:.1f}%",
                    delta=style['status'],
                    delta_color="normal" if overall_pct >= 100 else ("off" if overall_pct >= 80 else "inverse"),
                    help=overall_help
                )
            else:
                st.metric(
                    label="Overall Achievement",
                    value="N/A",
                    delta="No targets",
                    delta_color="off"
                )
        
        # People count or KPI count
        with col2:
            kpi_count = overall_achievement_data.get('kpi_count', 0)
            if is_single_person:
                st.metric(
                    label="Assigned KPIs",
                    value=f"{kpi_count}",
                    delta="types",
                    delta_color="off",
                    help="Number of KPI types assigned"
                )
            else:
                st.metric(
                    label="People",
                    value=f"{num_people}",
                    delta="selected",
                    delta_color="off",
                    help="Number of salespeople selected"
                )
        
        # KPI types or total weight
        with col3:
            total_weight = overall_achievement_data.get('total_weight', 0)
            kpi_count = overall_achievement_data.get('kpi_count', 0)
            
            if is_single_person:
                st.metric(
                    label="Total Weight",
                    value=f"{total_weight:.0f}%",
                    delta="sum of weights",
                    delta_color="off",
                    help="Sum of individual KPI assignment weights for this person (from sales_employee_kpi_assignments)"
                )
            else:
                st.metric(
                    label="KPI Types",
                    value=f"{kpi_count}",
                    delta="tracked",
                    delta_color="off",
                    help="Number of unique KPI types assigned across team"
                )
        
        # Best performer (team mode) or Gap to 100% (single mode)
        with col4:
            if is_single_person:
                # Show gap to target
                if overall_pct is not None:
                    gap = 100 - overall_pct
                    if gap <= 0:
                        st.metric(
                            label="Status",
                            value="On Track! 🎉",
                            delta=f"+{abs(gap):.1f}% above",
                            delta_color="normal"
                        )
                    else:
                        st.metric(
                            label="Gap to Target",
                            value=f"{gap:.1f}%",
                            delta="remaining",
                            delta_color="inverse"
                        )
                else:
                    st.metric(label="Gap", value="N/A", delta_color="off")
            else:
                # Show best performer
                if not salesperson_summary_df.empty and 'overall_achievement' in salesperson_summary_df.columns:
                    valid_df = salesperson_summary_df[
                        salesperson_summary_df['overall_achievement'].notna()
                    ]
                    if not valid_df.empty:
                        best_idx = valid_df['overall_achievement'].idxmax()
                        best_row = valid_df.loc[best_idx]
                        best_name = best_row.get('sales_name', 'Unknown')
                        best_pct = best_row.get('overall_achievement', 0)
                        
                        display_name = best_name[:12] + "..." if len(str(best_name)) > 12 else best_name
                        
                        st.metric(
                            label="Top Performer 🏆",
                            value=f"{best_pct:.1f}%",
                            delta=display_name,
                            delta_color="off",
                            help=f"Best overall achievement: {best_name}"
                        )
                    else:
                        st.metric(label="Top Performer", value="N/A", delta_color="off")
                else:
                    st.metric(label="Top Performer", value="N/A", delta_color="off")
        
        # Overall progress bar
        if overall_pct is not None:
            st.markdown("")
            progress_value = min(overall_pct / 100, 1.0)
            st.progress(progress_value)
            
            if overall_pct >= 100:
                st.success(f"✅ Target achieved! ({overall_pct:.1f}%)")
            elif overall_pct >= 80:
                st.warning(f"🟡 Almost there - {100 - overall_pct:.1f}% to go")
            elif overall_pct >= 50:
                st.info(f"🟠 Making progress - {100 - overall_pct:.1f}% gap to close")
            else:
                st.error(f"🔴 Needs attention - {100 - overall_pct:.1f}% below target")
    
    # =========================================================================
    # SECTION 2: KPI BREAKDOWN BY TYPE
    # =========================================================================
    
    st.markdown("")
    
    with st.container(border=True):
        col_header, col_sort = st.columns([4, 1])
        
        with col_header:
            st.markdown("### 📊 KPI Breakdown by Type")
        
        with col_sort:
            sort_option = st.selectbox(
                "Sort by",
                options=["Achievement %", "KPI Name", "Gap to Target"],
                index=0,
                key=f"{fragment_key}_sort",
                label_visibility="collapsed"
            )
        
        if not kpi_progress_data:
            st.info("No KPI targets assigned for selected salespeople")
        else:
            # Sort data
            kpi_list = list(kpi_progress_data)
            
            if sort_option == "Achievement %":
                kpi_list.sort(key=lambda x: x.get('Achievement %', 0), reverse=True)
            elif sort_option == "KPI Name":
                kpi_list.sort(key=lambda x: x.get('KPI', ''))
            elif sort_option == "Gap to Target":
                kpi_list.sort(key=lambda x: 100 - x.get('Achievement %', 0), reverse=True)
            
            # Display each KPI
            for row in kpi_list:
                achievement = row.get('Achievement %', 0)
                kpi_style = _get_achievement_style(achievement)
                
                col_kpi, col_progress = st.columns([1, 3])
                
                with col_kpi:
                    st.markdown(f"**{row['KPI']}**")
                    
                    if achievement >= 100:
                        st.success(f"✅ {achievement:.1f}%")
                    elif achievement >= 80:
                        st.warning(f"🟡 {achievement:.1f}%")
                    elif achievement >= 50:
                        st.info(f"🟠 {achievement:.1f}%")
                    else:
                        st.error(f"🔴 {achievement:.1f}%")
                
                with col_progress:
                    st.progress(max(0.0, min(achievement / 100, 1.0)))
                    
                    if row.get('is_currency', False):
                        actual_str = f"${row['Actual']:,.0f}"
                        target_str = f"${row['Target (Prorated)']:,.0f}"
                        annual_str = f"${row['Target (Annual)']:,.0f}"
                    else:
                        actual_str = f"{row['Actual']:.1f}"
                        target_str = f"{row['Target (Prorated)']:,.0f}"
                        annual_str = f"{row['Target (Annual)']:,.0f}"
                    
                    st.caption(
                        f"{actual_str} / {target_str} prorated "
                        f"({annual_str} annual) • {row.get('employee_count', 0)} people"
                    )
                
                st.markdown("---")
    
    # =========================================================================
    # SECTION 3: INDIVIDUAL PERFORMANCE (Only when multiple people selected)
    # =========================================================================
    
    if not is_single_person and not salesperson_summary_df.empty and num_people > 1:
        st.markdown("")
        
        with st.container(border=True):
            col_ind_header, col_ind_toggle = st.columns([4, 1])
            
            with col_ind_header:
                st.markdown("### 👥 Individual Performance")
                st.caption("📐 Each person's Overall uses their **individual KPI assignment weights**")
            
            with col_ind_toggle:
                expand_all = st.checkbox(
                    "Expand All",
                    value=False,
                    key=f"{fragment_key}_expand_all"
                )
            
            # Sort by overall achievement
            sorted_df = salesperson_summary_df.copy()
            if 'overall_achievement' in sorted_df.columns:
                sorted_df = sorted_df.sort_values(
                    'overall_achievement', 
                    ascending=False, 
                    na_position='last'
                )
            else:
                sorted_df = sorted_df.sort_values('revenue', ascending=False)
            
            sorted_df = sorted_df.reset_index(drop=True)
            
            # Calculate proration factor for individual KPI display
            today = date_type.today()
            if period_type == 'YTD':
                elapsed_months = today.month if year == today.year else 12
                proration_factor = elapsed_months / 12
            elif period_type == 'QTD':
                proration_factor = 1 / 4
            elif period_type == 'MTD':
                proration_factor = 1 / 12
            else:
                proration_factor = 1.0
            
            kpi_column_map = {
                'revenue': ('revenue', True),
                'gross_profit': ('gross_profit', True),
                'gross_profit_1': ('gp1', True),
            }
            
            # Display each salesperson
            for idx, row in sorted_df.iterrows():
                sales_id = row.get('sales_id')
                sales_name = row.get('sales_name', 'Unknown')
                overall_ach = row.get('overall_achievement')
                
                rank_emoji = _get_rank_emoji(idx + 1)
                person_style = _get_achievement_style(overall_ach)
                
                if overall_ach is not None:
                    expander_title = f"{rank_emoji} {sales_name} — Overall: {overall_ach:.1f}% {person_style['icon']}"
                else:
                    expander_title = f"{rank_emoji} {sales_name} — No KPI targets"
                
                with st.expander(expander_title, expanded=expand_all):
                    # Get this person's KPI assignments
                    person_targets = targets_df[targets_df['employee_id'] == sales_id]
                    
                    if person_targets.empty:
                        st.info("No KPI targets assigned to this person")
                        continue
                    
                    # Summary metrics row
                    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                    
                    with col_s1:
                        revenue = row.get('revenue', 0) or 0
                        rev_ach = row.get('revenue_achievement')
                        if rev_ach is not None and not pd.isna(rev_ach):
                            st.metric("Revenue", f"${revenue:,.0f}", f"{rev_ach:.1f}% ach")
                        else:
                            st.metric("Revenue", f"${revenue:,.0f}")
                    
                    with col_s2:
                        gp = row.get('gross_profit', 0) or 0
                        gp_pct = row.get('gp_percent', 0) or 0
                        gp_ach = row.get('gp_achievement')
                        if gp_ach is not None and not pd.isna(gp_ach):
                            st.metric("Gross Profit", f"${gp:,.0f} ({gp_pct:.1f}%)", f"{gp_ach:.1f}% ach")
                        else:
                            st.metric("Gross Profit", f"${gp:,.0f} ({gp_pct:.1f}%)")
                    
                    with col_s3:
                        gp1 = row.get('gp1', 0) or 0
                        gp1_pct = row.get('gp1_percent', 0) or 0
                        gp1_ach = row.get('gp1_achievement')
                        if gp1_ach is not None and not pd.isna(gp1_ach):
                            st.metric("GP1", f"${gp1:,.0f} ({gp1_pct:.1f}%)", f"{gp1_ach:.1f}% ach")
                        else:
                            st.metric("GP1", f"${gp1:,.0f} ({gp1_pct:.1f}%)")
                    
                    with col_s4:
                        customers = row.get('customers', 0) or 0
                        st.metric("Customers", f"{customers}")
                    
                    # KPI Progress Bars
                    st.markdown("##### 📋 KPI Progress")
                    
                    for _, kpi_row in person_targets.iterrows():
                        # FIXED: Normalize KPI name - replace spaces with underscores to match kpi_column_map keys
                        kpi_name = kpi_row['kpi_name'].lower().replace(' ', '_')
                        annual_target = kpi_row['annual_target_value_numeric']
                        weight = kpi_row['weight_numeric']
                        
                        if annual_target <= 0:
                            continue
                        
                        prorated_target = annual_target * proration_factor
                        
                        # Get actual value
                        if kpi_name in kpi_column_map:
                            col_name, is_currency = kpi_column_map[kpi_name]
                            actual = row.get(col_name, 0) or 0
                        else:
                            actual = 0
                            is_currency = kpi_name == 'new_business_revenue'
                            
                            # Try complex KPI calculator
                            if complex_kpi_calculator is not None and start_date and end_date:
                                try:
                                    result = complex_kpi_calculator.calculate_all(
                                        start_date=start_date,
                                        end_date=end_date,
                                        employee_ids=[sales_id]
                                    )
                                    summary = result.get('summary', {})
                                    
                                    if kpi_name == 'num_new_customers':
                                        actual = summary.get('num_new_customers', 0)
                                    elif kpi_name == 'num_new_products':
                                        actual = summary.get('num_new_products', 0)
                                    elif kpi_name == 'new_business_revenue':
                                        actual = summary.get('new_business_revenue', 0)
                                except Exception:
                                    pass
                        
                        # Calculate achievement
                        if prorated_target > 0:
                            kpi_achievement = (actual / prorated_target) * 100
                        else:
                            kpi_achievement = 0
                        
                        # Display name
                        display_names = {
                            'revenue': 'Revenue',
                            'gross_profit': 'Gross Profit',
                            'gross_profit_1': 'GP1',
                            'num_new_customers': 'New Customers',
                            'num_new_products': 'New Products',
                            'new_business_revenue': 'New Business Revenue',
                        }
                        display_name = display_names.get(kpi_name, kpi_name.replace('_', ' ').title())
                        
                        # Render mini progress
                        col_k1, col_k2, col_k3 = st.columns([2, 3, 1])
                        
                        with col_k1:
                            st.markdown(f"**{display_name}**")
                            if is_currency:
                                st.caption(f"${actual:,.0f} / ${prorated_target:,.0f}")
                            else:
                                st.caption(f"{actual:.1f} / {prorated_target:.1f}")
                        
                        with col_k2:
                            st.progress(max(0.0, min(kpi_achievement / 100, 1.0)))
                        
                        with col_k3:
                            kpi_style = _get_achievement_style(kpi_achievement)
                            st.markdown(f"{kpi_style['icon']} **{kpi_achievement:.1f}%**")


# =============================================================================
# COMBINED FRAGMENT: SALES DETAIL TAB (Tab 2)
# NEW v3.4.0: Filters above sub-tabs - all sub-tabs share same filtered data
# =============================================================================

@st.fragment
def sales_detail_tab_fragment(
    sales_df: pd.DataFrame,
    overview_metrics: Dict,
    filter_values: Dict,
    fragment_key: str = "sales_detail_tab"
):
    """
    Combined fragment for entire Sales Detail tab.
    
    Structure:
    1. Filters (Customer, Brand, Product, OC#, Min Amount) - ABOVE sub-tabs
    2. Sub-tabs (Transaction List, Pivot Analysis)
    
    When filters change, both sub-tabs update.
    Fragment prevents full page rerun.
    """
    st.subheader("📋 Sales Transaction Detail")
    
    if sales_df.empty:
        st.info("No sales data for selected period")
        return
    
    # =================================================================
    # FILTERS - Above sub-tabs (shared by all sub-tabs)
    # =================================================================
    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
    
    with col_f1:
        customer_options = sorted(sales_df['customer'].dropna().unique().tolist())
        customer_filter = render_multiselect_filter(
            label="Customer",
            options=customer_options,
            key=f"{fragment_key}_customer",
            placeholder="Choose an option"
        )
    
    with col_f2:
        brand_options = sorted(sales_df['brand'].dropna().unique().tolist())
        brand_filter = render_multiselect_filter(
            label="Brand",
            options=brand_options,
            key=f"{fragment_key}_brand",
            placeholder="Choose an option"
        )
    
    with col_f3:
        product_options = sorted(sales_df['product_pn'].dropna().unique().tolist())[:100]
        product_filter = render_multiselect_filter(
            label="Product",
            options=product_options,
            key=f"{fragment_key}_product",
            placeholder="Choose an option"
        )
    
    with col_f4:
        oc_po_filter = render_text_search_filter(
            label="OC# / Customer PO",
            key=f"{fragment_key}_oc_po",
            placeholder="Search..."
        )
    
    with col_f5:
        amount_filter = render_number_filter(
            label="Min Amount ($)",
            key=f"{fragment_key}_min_amount",
            default_min=0,
            step=1000
        )
    
    # =================================================================
    # APPLY FILTERS (shared by all sub-tabs)
    # =================================================================
    filtered_df = sales_df.copy()
    
    filtered_df = apply_multiselect_filter(filtered_df, 'customer', customer_filter)
    filtered_df = apply_multiselect_filter(filtered_df, 'brand', brand_filter)
    filtered_df = apply_multiselect_filter(filtered_df, 'product_pn', product_filter)
    filtered_df = apply_text_search_filter(
        filtered_df, 
        columns=['oc_number', 'customer_po_number'],
        search_result=oc_po_filter
    )
    filtered_df = apply_number_filter(filtered_df, 'sales_by_split_usd', amount_filter)
    
    # Show filter summary
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
    
    # =================================================================
    # SUB-TABS - Both use filtered_df
    # =================================================================
    detail_tab1, detail_tab2 = st.tabs(["📄 Sales List", "📊 Pivot Analysis"])
    
    with detail_tab1:
        _render_sales_list_content(filtered_df, sales_df, filter_values, f"{fragment_key}_list")
    
    with detail_tab2:
        _render_pivot_content(filtered_df, f"{fragment_key}_pivot")


def _render_sales_list_content(
    filtered_df: pd.DataFrame,
    original_df: pd.DataFrame,
    filter_values: Dict,
    key_prefix: str
):
    """Render Sales List content (without filters - filters are above)."""
    if filtered_df.empty:
        st.info("No transactions match the current filters")
        return
    
    # Summary metrics cards
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    total_revenue = filtered_df['sales_by_split_usd'].sum()
    total_gp = filtered_df['gross_profit_by_split_usd'].sum()
    total_gp1 = filtered_df['gp1_by_split_usd'].sum()
    gp_percent = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
    gp1_percent = (total_gp1 / total_revenue * 100) if total_revenue > 0 else 0
    total_invoices = filtered_df['inv_number'].nunique()
    total_orders = filtered_df['oc_number'].nunique()
    total_customers = filtered_df['customer_id'].nunique()
    
    with col_s1:
        st.metric("💰 Revenue", f"${total_revenue:,.0f}", 
                  delta=f"{total_invoices:,} invoices", delta_color="off",
                  help="Total revenue (split-adjusted)")
    with col_s2:
        st.metric("📈 Gross Profit", f"${total_gp:,.0f}", 
                  delta=f"↑ {gp_percent:.1f}% margin", delta_color="off",
                  help="Total GP (split-adjusted)")
    with col_s3:
        st.metric("📊 GP1", f"${total_gp1:,.0f}", 
                  delta=f"↑ {gp1_percent:.1f}% margin", delta_color="off",
                  help="GP1 = GP - Broker Commission")
    with col_s4:
        st.metric("📋 Orders", f"{total_orders:,}", delta_color="off",
                  help="Unique order confirmations")
    with col_s5:
        st.metric("👥 Customers", f"{total_customers:,}", delta_color="off",
                  help="Unique customers")
    with col_s6:
        avg_order = total_revenue / total_orders if total_orders > 0 else 0
        st.metric("📦 Avg Order", f"${avg_order:,.0f}", delta_color="off",
                  help="Average revenue per order")
    with col_s7:
        avg_gp_customer = total_gp / total_customers if total_customers > 0 else 0
        st.metric("💵 Avg GP", f"${avg_gp_customer:,.0f}", delta_color="off",
                  help="Average GP per customer")
    
    # Prepare display dataframe
    display_df = filtered_df.copy()
    
    # Calculate original values (before split)
    split_pct = display_df['split_rate_percent'].replace(0, 100) / 100
    display_df['total_revenue_usd'] = display_df['sales_by_split_usd'] / split_pct
    display_df['total_gp_usd'] = display_df['gross_profit_by_split_usd'] / split_pct
    
    # Format Product display
    def format_product_display(row):
        parts = []
        if pd.notna(row.get('pt_code')) and row.get('pt_code'):
            parts.append(str(row['pt_code']))
        if pd.notna(row.get('product_pn')) and row.get('product_pn'):
            parts.append(str(row['product_pn']))
        if pd.notna(row.get('package_size')) and row.get('package_size'):
            parts.append(str(row['package_size']))
        return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))
    
    display_df['product_display'] = display_df.apply(format_product_display, axis=1)
    
    # Format OC/PO display
    def format_oc_po(row):
        oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
        po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
        if oc and po:
            return f"{oc} (PO: {po})"
        return oc or (f"(PO: {po})" if po else '')
    
    display_df['oc_po_display'] = display_df.apply(format_oc_po, axis=1)
    
    # Calculate GP% and GP1%
    display_df['gp_percent'] = display_df.apply(
        lambda r: (r.get('gross_profit_by_split_usd', 0) / r.get('sales_by_split_usd', 1) * 100) 
        if r.get('sales_by_split_usd', 0) > 0 else 0, axis=1
    )
    display_df['gp1_percent'] = display_df.apply(
        lambda r: (r.get('gp1_by_split_usd', 0) / r.get('sales_by_split_usd', 1) * 100) 
        if r.get('sales_by_split_usd', 0) > 0 else 0, axis=1
    )
    
    # Display columns
    display_columns = [
        'inv_date', 'inv_number', 'oc_po_display', 'customer', 'product_display', 'brand',
        'total_revenue_usd', 'total_gp_usd', 'split_rate_percent',
        'sales_by_split_usd', 'gross_profit_by_split_usd', 'gp_percent', 
        'gp1_by_split_usd', 'gp1_percent', 'sales_name'
    ]
    available_cols = [c for c in display_columns if c in display_df.columns]
    
    DISPLAY_LIMIT = 5000
    total_filtered = len(display_df)
    display_detail = display_df[available_cols].head(DISPLAY_LIMIT).copy()
    
    if total_filtered > DISPLAY_LIMIT:
        st.markdown(f"**Showing {DISPLAY_LIMIT:,} of {total_filtered:,} transactions** (from {len(original_df):,} total)")
        st.warning(f"⚠️ Display limited to {DISPLAY_LIMIT:,} rows. Export for full data.")
    else:
        st.markdown(f"**Showing {total_filtered:,} transactions** (of {len(original_df):,} total)")
    
    # Column config
    column_config = {
        'inv_date': st.column_config.DateColumn("Date"),
        'inv_number': st.column_config.TextColumn("Invoice#"),
        'oc_po_display': st.column_config.TextColumn("OC / PO", width="medium"),
        'customer': st.column_config.TextColumn("Customer", width="medium"),
        'product_display': st.column_config.TextColumn("Product", width="large",
            help="PT Code | Name | Package Size"),
        'brand': st.column_config.TextColumn("Brand"),
        'total_revenue_usd': st.column_config.NumberColumn("Total Rev", format="$%.0f",
            help="Before split"),
        'total_gp_usd': st.column_config.NumberColumn("Total GP", format="$%.0f",
            help="Before split"),
        'split_rate_percent': st.column_config.NumberColumn("Split %", format="%.0f%%"),
        'sales_by_split_usd': st.column_config.NumberColumn("Revenue", format="$%.0f"),
        'gross_profit_by_split_usd': st.column_config.NumberColumn("GP", format="$%.0f"),
        'gp_percent': st.column_config.NumberColumn("GP%", format="%.1f%%"),
        'gp1_by_split_usd': st.column_config.NumberColumn("GP1", format="$%.0f"),
        'gp1_percent': st.column_config.NumberColumn("GP1%", format="%.1f%%"),
        'sales_name': st.column_config.TextColumn("Salesperson"),
    }
    
    st.dataframe(
        display_detail,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        height=600
    )
    
    # Export button
    from datetime import datetime as dt
    if st.button("📥 Export Filtered View", key=f"{key_prefix}_export"):
        csv = display_df[available_cols].to_csv(index=False)
        st.download_button(
            label="⬇️ Download CSV",
            data=csv,
            file_name=f"sales_detail_{dt.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key=f"{key_prefix}_download"
        )


def _render_pivot_content(filtered_df: pd.DataFrame, key_prefix: str):
    """Render Pivot Analysis content (without filters - filters are above)."""
    if filtered_df.empty:
        st.info("No data for pivot analysis")
        return
    
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        row_options = ['customer', 'brand', 'sales_name', 'product_pn']
        pivot_rows = st.selectbox("Rows", row_options, key=f"{key_prefix}_rows",
                                  format_func=lambda x: x.replace('_', ' ').title())
    
    with col_p2:
        col_options = ['invoice_month', 'invoice_quarter', 'brand', 'customer']
        pivot_cols = st.selectbox("Columns", col_options, key=f"{key_prefix}_cols",
                                  format_func=lambda x: x.replace('_', ' ').title())
    
    with col_p3:
        value_options = ['sales_by_split_usd', 'gross_profit_by_split_usd', 'gp1_by_split_usd']
        pivot_values = st.selectbox("Values", value_options, index=1, key=f"{key_prefix}_values",
                                   format_func=lambda x: x.replace('_by_split_usd', '').replace('_', ' ').title())
    
    if pivot_rows in filtered_df.columns and pivot_cols in filtered_df.columns:
        pivot_df = filtered_df.pivot_table(
            values=pivot_values,
            index=pivot_rows,
            columns=pivot_cols,
            aggfunc='sum',
            fill_value=0
        )
        
        pivot_df['Total'] = pivot_df.sum(axis=1)
        pivot_df = pivot_df.sort_values('Total', ascending=False)
        
        if pivot_cols == 'invoice_month':
            month_cols = [m for m in MONTH_ORDER if m in pivot_df.columns]
            other_cols = [c for c in pivot_df.columns if c not in MONTH_ORDER and c != 'Total']
            pivot_df = pivot_df[month_cols + other_cols + ['Total']]
        
        st.dataframe(
            pivot_df.style.format("${:,.0f}").background_gradient(cmap='Blues', subset=['Total']),
            use_container_width=True,
            height=500
        )
    else:
        st.warning("Selected columns not available")


# =============================================================================
# COMBINED FRAGMENT: BACKLOG TAB (Tab 3)
# NEW v3.4.0: Filters above sub-tabs - all sub-tabs share same filtered data
# =============================================================================

@st.fragment
def backlog_tab_fragment(
    backlog_df: pd.DataFrame,
    in_period_backlog_analysis: Dict,
    total_backlog_df: pd.DataFrame,
    backlog_by_month_df: pd.DataFrame,
    metrics_calc: Any,
    current_year: int,
    filter_values: Dict,
    fragment_key: str = "backlog_tab"
):
    """
    Combined fragment for entire Backlog tab.
    
    Structure:
    1. Overdue warning (if applicable)
    2. Filters (Customer, Brand, Product, OC#, Status) - ABOVE sub-tabs
    3. Sub-tabs (Backlog List, By ETD, Risk Analysis)
    
    When filters change, all sub-tabs update.
    Fragment prevents full page rerun.
    """
    if backlog_df.empty:
        st.info("📦 No backlog data available")
        return
    
    # Show overdue warning at top
    if in_period_backlog_analysis.get('overdue_warning'):
        st.warning(in_period_backlog_analysis['overdue_warning'])
    
    # =================================================================
    # FILTERS - Above sub-tabs (shared by all sub-tabs)
    # =================================================================
    col_bf1, col_bf2, col_bf3, col_bf4, col_bf5 = st.columns(5)
    
    with col_bf1:
        bl_customer_options = sorted(backlog_df['customer'].dropna().unique().tolist())
        bl_customer_filter = render_multiselect_filter(
            label="Customer",
            options=bl_customer_options,
            key=f"{fragment_key}_customer",
            placeholder="Choose an option"
        )
    
    with col_bf2:
        bl_brand_options = sorted(backlog_df['brand'].dropna().unique().tolist())
        bl_brand_filter = render_multiselect_filter(
            label="Brand",
            options=bl_brand_options,
            key=f"{fragment_key}_brand",
            placeholder="Choose an option"
        )
    
    with col_bf3:
        bl_product_options = sorted(backlog_df['product_pn'].dropna().unique().tolist())[:100]
        bl_product_filter = render_multiselect_filter(
            label="Product",
            options=bl_product_options,
            key=f"{fragment_key}_product",
            placeholder="Choose an option"
        )
    
    with col_bf4:
        bl_oc_po_filter = render_text_search_filter(
            label="OC# / Customer PO",
            key=f"{fragment_key}_oc_po",
            placeholder="Search..."
        )
    
    with col_bf5:
        bl_status_options = backlog_df['pending_type'].dropna().unique().tolist()
        bl_status_filter = render_multiselect_filter(
            label="Status",
            options=bl_status_options,
            key=f"{fragment_key}_status",
            placeholder="Choose an option"
        )
    
    # =================================================================
    # APPLY FILTERS (shared by all sub-tabs)
    # =================================================================
    filtered_backlog = backlog_df.copy()
    
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'customer', bl_customer_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'brand', bl_brand_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'product_pn', bl_product_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'pending_type', bl_status_filter)
    filtered_backlog = apply_text_search_filter(
        filtered_backlog, 
        columns=['oc_number', 'customer_po_number'] if 'customer_po_number' in backlog_df.columns else ['oc_number'],
        search_result=bl_oc_po_filter
    )
    
    # Show filter summary
    active_bl_filters = []
    if bl_customer_filter.is_active:
        mode = "excl" if bl_customer_filter.excluded else "incl"
        active_bl_filters.append(f"Customer: {len(bl_customer_filter.selected)} ({mode})")
    if bl_brand_filter.is_active:
        mode = "excl" if bl_brand_filter.excluded else "incl"
        active_bl_filters.append(f"Brand: {len(bl_brand_filter.selected)} ({mode})")
    if bl_product_filter.is_active:
        mode = "excl" if bl_product_filter.excluded else "incl"
        active_bl_filters.append(f"Product: {len(bl_product_filter.selected)} ({mode})")
    if bl_oc_po_filter.is_active:
        mode = "excl" if bl_oc_po_filter.excluded else "incl"
        active_bl_filters.append(f"OC/PO: '{bl_oc_po_filter.query}' ({mode})")
    if bl_status_filter.is_active:
        mode = "excl" if bl_status_filter.excluded else "incl"
        active_bl_filters.append(f"Status: {len(bl_status_filter.selected)} ({mode})")
    
    if active_bl_filters:
        st.caption(f"🔍 Active filters: {' | '.join(active_bl_filters)}")
    
    # =================================================================
    # SUB-TABS - All use filtered_backlog
    # =================================================================
    backlog_tab1, backlog_tab2, backlog_tab3 = st.tabs(["📋 Backlog List", "📅 By ETD", "⚠️ Risk Analysis"])
    
    with backlog_tab1:
        _render_backlog_list_content(
            filtered_backlog, backlog_df, in_period_backlog_analysis, 
            f"{fragment_key}_list"
        )
    
    with backlog_tab2:
        _render_backlog_by_etd_content(
            filtered_backlog, backlog_by_month_df, metrics_calc, current_year, 
            f"{fragment_key}_etd"
        )
    
    with backlog_tab3:
        _render_risk_analysis_content(filtered_backlog, f"{fragment_key}_risk")


def _render_backlog_list_content(
    filtered_backlog: pd.DataFrame,
    original_backlog: pd.DataFrame,
    in_period_backlog_analysis: Dict,
    key_prefix: str
):
    """Render Backlog List content (without filters - filters are above)."""
    if filtered_backlog.empty:
        st.info("No backlog items match the current filters")
        return
    
    # Summary cards - recalculate based on filtered data
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    total_backlog_value = filtered_backlog['backlog_sales_by_split_usd'].sum()
    total_backlog_gp = filtered_backlog['backlog_gp_by_split_usd'].sum()
    total_backlog_gp_percent = (total_backlog_gp / total_backlog_value * 100) if total_backlog_value > 0 else 0
    total_orders = filtered_backlog['oc_number'].nunique()
    total_customers = filtered_backlog['customer_id'].nunique()
    
    with col_s1:
        st.metric("💰 Total Backlog", f"${total_backlog_value:,.0f}", 
                  f"{total_orders:,} orders", delta_color="off",
                  help="All pending orders from filtered selection")
    with col_s2:
        st.metric("📈 Total GP", f"${total_backlog_gp:,.0f}",
                  f"↑ {total_backlog_gp_percent:.1f}% margin", delta_color="off",
                  help="Total GP from filtered backlog")
    with col_s3:
        in_period_value = in_period_backlog_analysis.get('total_value', 0)
        in_period_count = in_period_backlog_analysis.get('total_count', 0)
        st.metric("📅 In-Period", f"${in_period_value:,.0f}",
                  f"{in_period_count:,} orders", delta_color="off",
                  help="ETD within date range")
    with col_s4:
        in_period_gp = in_period_backlog_analysis.get('total_gp', 0)
        in_period_gp_percent = (in_period_gp / in_period_value * 100) if in_period_value > 0 else 0
        st.metric("📊 In-Period GP", f"${in_period_gp:,.0f}",
                  f"↑ {in_period_gp_percent:.1f}% margin", delta_color="off",
                  help="GP from in-period backlog")
    with col_s5:
        on_track_value = in_period_backlog_analysis.get('on_track_value', 0)
        on_track_count = in_period_backlog_analysis.get('on_track_count', 0)
        st.metric("✅ On Track", f"${on_track_value:,.0f}",
                  f"{on_track_count:,} orders", delta_color="off",
                  help="ETD ≥ today")
    with col_s6:
        overdue_value = in_period_backlog_analysis.get('overdue_value', 0)
        overdue_count = in_period_backlog_analysis.get('overdue_count', 0)
        st.metric("⚠️ Overdue", f"${overdue_value:,.0f}",
                  f"{overdue_count:,} orders",
                  delta_color="inverse" if overdue_count > 0 else "off",
                  help="ETD < today (past due)")
    with col_s7:
        status = in_period_backlog_analysis.get('status', 'unknown')
        overdue_cnt = in_period_backlog_analysis.get('overdue_count', 0)
        in_period_cnt = in_period_backlog_analysis.get('total_count', 0)
        
        if status == 'has_overdue' or overdue_cnt > 0:
            status_display = "HAS OVERDUE ⚠️"
        elif status == 'healthy' or (in_period_cnt > 0 and overdue_cnt == 0):
            status_display = "HEALTHY ✅"
        elif status == 'empty' or in_period_cnt == 0:
            status_display = "NO IN-PERIOD"
        else:
            status_display = "N/A"
        
        st.metric("📊 Status", status_display)
    
    # Prepare display dataframe
    display_backlog = filtered_backlog.copy()
    
    # Format Product display
    def format_product_display(row):
        parts = []
        if pd.notna(row.get('pt_code')) and row.get('pt_code'):
            parts.append(str(row['pt_code']))
        if pd.notna(row.get('product_pn')) and row.get('product_pn'):
            parts.append(str(row['product_pn']))
        if pd.notna(row.get('package_size')) and row.get('package_size'):
            parts.append(str(row['package_size']))
        return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))
    
    display_backlog['product_display'] = display_backlog.apply(format_product_display, axis=1)
    
    # Format OC/PO display
    def format_oc_po(row):
        oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
        po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
        if oc and po:
            return f"{oc} (PO: {po})"
        return oc or (f"(PO: {po})" if po else '')
    
    display_backlog['oc_po_display'] = display_backlog.apply(format_oc_po, axis=1)
    
    # Calculate GP%
    display_backlog['gp_percent'] = display_backlog.apply(
        lambda r: (r.get('backlog_gp_by_split_usd', 0) / r.get('backlog_sales_by_split_usd', 1) * 100)
        if r.get('backlog_sales_by_split_usd', 0) > 0 else 0, axis=1
    )
    
    # Display columns
    display_columns = [
        'oc_po_display', 'oc_date', 'etd', 'customer', 'product_display', 'brand',
        'backlog_sales_by_split_usd', 'backlog_gp_by_split_usd', 'gp_percent',
        'days_until_etd', 'pending_type', 'sales_name'
    ]
    available_cols = [c for c in display_columns if c in display_backlog.columns]
    
    DISPLAY_LIMIT = 5000
    total_filtered = len(display_backlog)
    display_detail = display_backlog[available_cols].head(DISPLAY_LIMIT).copy()
    
    if total_filtered > DISPLAY_LIMIT:
        st.markdown(f"**Showing {DISPLAY_LIMIT:,} of {total_filtered:,} items** (from {len(original_backlog):,} total)")
    else:
        st.markdown(f"**Showing {total_filtered:,} backlog items** (of {len(original_backlog):,} total)")
    
    # Column config
    column_config = {
        'oc_po_display': st.column_config.TextColumn("OC / PO", width="medium"),
        'oc_date': st.column_config.DateColumn("OC Date"),
        'etd': st.column_config.DateColumn("ETD"),
        'customer': st.column_config.TextColumn("Customer", width="medium"),
        'product_display': st.column_config.TextColumn("Product", width="large",
            help="PT Code | Name | Package Size"),
        'brand': st.column_config.TextColumn("Brand"),
        'backlog_sales_by_split_usd': st.column_config.NumberColumn("Amount", format="$%.0f"),
        'backlog_gp_by_split_usd': st.column_config.NumberColumn("GP", format="$%.0f"),
        'gp_percent': st.column_config.NumberColumn("GP%", format="%.1f%%"),
        'days_until_etd': st.column_config.NumberColumn("Days to ETD", format="%.0f"),
        'pending_type': st.column_config.TextColumn("Status"),
        'sales_name': st.column_config.TextColumn("Salesperson"),
    }
    
    st.dataframe(
        display_detail,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        height=600
    )


def _render_backlog_by_etd_content(
    filtered_backlog: pd.DataFrame,
    backlog_by_month_df: pd.DataFrame,
    metrics_calc: Any,
    current_year: int,
    key_prefix: str
):
    """Render Backlog By ETD content using filtered data."""
    if filtered_backlog.empty:
        st.info("No backlog data for ETD analysis")
        return
    
    # Re-aggregate filtered backlog by ETD month
    df = filtered_backlog.copy()
    df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
    df = df[df['etd'].notna()]
    
    if df.empty:
        st.info("No ETD data available")
        return
    
    df['etd_year'] = df['etd'].dt.year.astype(int)
    df['etd_month'] = df['etd'].dt.strftime('%b')
    
    filtered_by_month = df.groupby(['etd_year', 'etd_month']).agg({
        'backlog_sales_by_split_usd': 'sum',
        'backlog_gp_by_split_usd': 'sum',
        'oc_number': 'nunique'
    }).reset_index()
    filtered_by_month.columns = ['etd_year', 'etd_month', 'backlog_revenue', 'backlog_gp', 'order_count']
    
    # View mode selection
    view_mode = st.radio(
        "View Mode",
        options=["📅 Timeline", "📊 Stacked", "📈 Single Year"],
        horizontal=True,
        key=f"{key_prefix}_view_mode"
    )
    
    month_order_list = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    if view_mode == "📅 Timeline":
        st.markdown("##### 📅 Backlog Timeline by ETD Month")
        
        if not filtered_by_month.empty:
            timeline_df = filtered_by_month.pivot_table(
                values='backlog_revenue',
                index='etd_month',
                columns='etd_year',
                aggfunc='sum',
                fill_value=0
            )
            timeline_df = timeline_df.reindex([m for m in month_order_list if m in timeline_df.index])
            
            st.dataframe(
                timeline_df.style.format("${:,.0f}").background_gradient(cmap='Blues'),
                use_container_width=True
            )
    
    elif view_mode == "📊 Stacked":
        st.markdown("##### 📊 Backlog by Year (Stacked)")
        
        yearly = filtered_by_month.groupby('etd_year').agg({
            'backlog_revenue': 'sum',
            'backlog_gp': 'sum',
            'order_count': 'sum'
        }).reset_index()
        
        for _, row in yearly.iterrows():
            year = int(row['etd_year'])
            revenue = row['backlog_revenue']
            gp = row['backlog_gp']
            orders = int(row['order_count'])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(f"{year} Revenue", f"${revenue:,.0f}")
            with col2:
                st.metric(f"{year} GP", f"${gp:,.0f}")
            with col3:
                st.metric(f"{year} Orders", f"{orders:,}")
    
    else:  # Single Year
        available_years = sorted(filtered_by_month['etd_year'].unique(), reverse=True)
        if not available_years:
            st.info("No year data available")
            return
            
        default_idx = 0
        if current_year in available_years:
            default_idx = available_years.index(current_year)
            
        selected_year = st.selectbox(
            "Select Year",
            options=available_years,
            index=default_idx,
            key=f"{key_prefix}_year"
        )
        
        year_data = filtered_by_month[filtered_by_month['etd_year'] == selected_year].copy()
        
        if not year_data.empty:
            st.markdown(f"##### 📈 {selected_year} Backlog by Month")
            
            month_order_map = {m: i for i, m in enumerate(month_order_list)}
            year_data['_month_num'] = year_data['etd_month'].map(month_order_map)
            year_data = year_data.sort_values('_month_num')
            
            st.dataframe(
                year_data[['etd_month', 'backlog_revenue', 'backlog_gp', 'order_count']].rename(columns={
                    'etd_month': 'Month',
                    'backlog_revenue': 'Revenue',
                    'backlog_gp': 'GP',
                    'order_count': 'Orders'
                }).style.format({'Revenue': '${:,.0f}', 'GP': '${:,.0f}'}),
                use_container_width=True,
                hide_index=True
            )


def _render_risk_analysis_content(filtered_backlog: pd.DataFrame, key_prefix: str):
    """Render Risk Analysis content."""
    if filtered_backlog.empty:
        st.info("No backlog data for risk analysis")
        return
    
    st.markdown("#### ⚠️ Backlog Risk Analysis")
    
    backlog_risk = filtered_backlog.copy()
    backlog_risk['days_until_etd'] = pd.to_numeric(backlog_risk['days_until_etd'], errors='coerce')
    
    # Categorize
    overdue = backlog_risk[backlog_risk['days_until_etd'] < 0]
    this_week = backlog_risk[(backlog_risk['days_until_etd'] >= 0) & (backlog_risk['days_until_etd'] <= 7)]
    this_month = backlog_risk[(backlog_risk['days_until_etd'] > 7) & (backlog_risk['days_until_etd'] <= 30)]
    on_track = backlog_risk[backlog_risk['days_until_etd'] > 30]
    
    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    
    with col_r1:
        overdue_value = overdue['backlog_sales_by_split_usd'].sum()
        st.metric("🔴 Overdue", f"${overdue_value:,.0f}",
                  delta=f"{len(overdue)} orders", delta_color="inverse")
    
    with col_r2:
        week_value = this_week['backlog_sales_by_split_usd'].sum()
        st.metric("🟠 This Week", f"${week_value:,.0f}",
                  delta=f"{len(this_week)} orders", delta_color="off")
    
    with col_r3:
        month_value = this_month['backlog_sales_by_split_usd'].sum()
        st.metric("🟡 This Month", f"${month_value:,.0f}",
                  delta=f"{len(this_month)} orders", delta_color="off")
    
    with col_r4:
        track_value = on_track['backlog_sales_by_split_usd'].sum()
        st.metric("🟢 On Track", f"${track_value:,.0f}",
                  delta=f"{len(on_track)} orders", delta_color="normal")
    
    st.divider()
    
    # Show overdue details
    if not overdue.empty:
        st.markdown("##### 🔴 Overdue Orders (ETD Passed)")
        
        overdue_display = overdue.copy()
        
        def format_product_display(row):
            parts = []
            if pd.notna(row.get('pt_code')) and row.get('pt_code'):
                parts.append(str(row['pt_code']))
            if pd.notna(row.get('product_pn')) and row.get('product_pn'):
                parts.append(str(row['product_pn']))
            if pd.notna(row.get('package_size')) and row.get('package_size'):
                parts.append(str(row['package_size']))
            return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))
        
        overdue_display['product_display'] = overdue_display.apply(format_product_display, axis=1)
        
        def format_oc_po(row):
            oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
            po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
            if oc and po:
                return f"{oc} (PO: {po})"
            return oc or (f"(PO: {po})" if po else '')
        
        overdue_display['oc_po_display'] = overdue_display.apply(format_oc_po, axis=1)
        overdue_display['days_overdue'] = overdue_display['days_until_etd'].abs()
        
        display_cols = ['oc_po_display', 'etd', 'customer', 'product_display', 'brand',
                       'backlog_sales_by_split_usd', 'backlog_gp_by_split_usd', 
                       'days_overdue', 'pending_type', 'sales_name']
        available_cols = [c for c in display_cols if c in overdue_display.columns]
        
        display_df = overdue_display[available_cols].sort_values(
            'backlog_sales_by_split_usd', ascending=False
        ).head(50).copy()
        
        column_config = {
            'oc_po_display': st.column_config.TextColumn("OC / PO", width="medium"),
            'etd': st.column_config.DateColumn("ETD"),
            'customer': st.column_config.TextColumn("Customer", width="medium"),
            'product_display': st.column_config.TextColumn("Product", width="large"),
            'brand': st.column_config.TextColumn("Brand"),
            'backlog_sales_by_split_usd': st.column_config.NumberColumn("Amount", format="$%.0f"),
            'backlog_gp_by_split_usd': st.column_config.NumberColumn("GP", format="$%.0f"),
            'days_overdue': st.column_config.NumberColumn("Days Overdue"),
            'pending_type': st.column_config.TextColumn("Status"),
            'sales_name': st.column_config.TextColumn("Salesperson"),
        }
        
        st.dataframe(
            display_df,
            column_config=column_config,
            use_container_width=True,
            hide_index=True,
            height=400
        )


# =============================================================================
# EXPORT ALL FRAGMENTS
# =============================================================================

__all__ = [
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'sales_detail_fragment',
    'pivot_analysis_fragment',
    'backlog_list_fragment',
    'export_report_fragment',
    'backlog_by_etd_fragment',
    'team_ranking_fragment',
    'kpi_progress_fragment',
    # NEW v3.4.0: Combined fragments with filters above sub-tabs
    'sales_detail_tab_fragment',
    'backlog_tab_fragment',
]