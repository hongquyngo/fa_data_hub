# utils/period_gap/tab_components.py
"""
Tab Components for Period GAP Analysis
Version 4.0 - Redesigned UI with 4 tabs matching Excel export structure
- Tab 1: GAP Detail (matches GAP_Analysis sheet)
- Tab 2: Product Summary (matches Product_Summary sheet)  
- Tab 3: Period Summary (matches Period_Summary sheet) with charts
- Tab 4: Pivot View (matches Pivot_View sheet)
- Action Items Expander (matches Action_Items sheet)
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, List, Set
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# TAB 1: GAP DETAIL
# =============================================================================

def render_gap_detail_tab(
    gap_df: pd.DataFrame,
    display_filters: Dict[str, Any],
    df_demand_filtered: Optional[pd.DataFrame] = None,
    df_supply_filtered: Optional[pd.DataFrame] = None
):
    """
    Render GAP Detail tab - matches GAP_Analysis Excel sheet
    Shows detailed GAP data per product per period
    """
    from .period_helpers import prepare_gap_detail_display, format_gap_display_df
    from .shortage_analyzer import categorize_products
    from .formatters import format_number
    
    if gap_df.empty:
        st.info("📭 No data available. Please run analysis first.")
        return
    
    # Get categorization for filtering
    categorization = categorize_products(gap_df)
    
    # --- Display Filters Section ---
    st.markdown("##### 🔍 Display Filters")
    
    # Filter row 1: Category filter
    filter_col1, filter_col2 = st.columns([3, 2])
    
    with filter_col1:
        period_filter = st.radio(
            "Show:",
            options=["All", "Net Shortage", "Timing Shortage", "Net Surplus", "Timing Surplus"],
            horizontal=True,
            key="tab1_period_filter"
        )
    
    with filter_col2:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            show_matched = st.checkbox("🔗 Matched", value=True, key="tab1_show_matched")
        with col_b:
            show_demand_only = st.checkbox("📤 Demand Only", value=True, key="tab1_demand_only")
        with col_c:
            show_supply_only = st.checkbox("📥 Supply Only", value=True, key="tab1_supply_only")
    
    # Filter row 2: Options
    opt_col1, opt_col2 = st.columns(2)
    with opt_col1:
        highlight_rows = st.checkbox("🎨 Highlight Rows", value=True, key="tab1_highlight")
    with opt_col2:
        show_past = st.checkbox("🔴 Show Past Periods", value=True, key="tab1_show_past")
    
    # Apply category filter
    filtered_df = gap_df.copy()
    
    if period_filter == "Net Shortage":
        filtered_df = filtered_df[filtered_df['pt_code'].isin(categorization['net_shortage'])]
    elif period_filter == "Timing Shortage":
        filtered_df = filtered_df[filtered_df['pt_code'].isin(categorization['timing_shortage'])]
    elif period_filter == "Net Surplus":
        filtered_df = filtered_df[filtered_df['pt_code'].isin(categorization['net_surplus'])]
    elif period_filter == "Timing Surplus":
        filtered_df = filtered_df[filtered_df['pt_code'].isin(categorization['timing_surplus'])]
    
    # Apply product type filter
    if not (show_matched and show_demand_only and show_supply_only):
        demand_products = set(df_demand_filtered['pt_code'].unique()) if df_demand_filtered is not None and not df_demand_filtered.empty else set()
        supply_products = set(df_supply_filtered['pt_code'].unique()) if df_supply_filtered is not None and not df_supply_filtered.empty else set()
        
        products_to_show = set()
        if show_matched:
            products_to_show.update(demand_products & supply_products)
        if show_demand_only:
            products_to_show.update(demand_products - supply_products)
        if show_supply_only:
            products_to_show.update(supply_products - demand_products)
        
        if products_to_show:
            filtered_df = filtered_df[filtered_df['pt_code'].isin(products_to_show)]
    
    # Filter past periods if needed
    if not show_past:
        from .period_helpers import is_past_period
        period_type = display_filters.get('period_type', 'Weekly')
        filtered_df = filtered_df[~filtered_df['period'].apply(lambda x: is_past_period(str(x), period_type))]
    
    if filtered_df.empty:
        st.warning("⚠️ No data matches the selected filters.")
        return
    
    # Show record count
    st.caption(f"📊 Showing {len(filtered_df):,} records | {filtered_df['pt_code'].nunique()} products | {filtered_df['period'].nunique()} periods")
    
    # Prepare display dataframe with category
    display_df = prepare_gap_detail_display(
        filtered_df,
        display_filters,
        df_demand_filtered,
        df_supply_filtered
    )
    
    # Add category column
    def get_category_icon(pt_code):
        if pt_code in categorization['net_shortage']:
            return "🚨"
        elif pt_code in categorization['net_surplus']:
            return "📈"
        elif pt_code in categorization['balanced']:
            return "✅"
        return "❓"
    
    display_df['category'] = display_df['pt_code'].apply(get_category_icon)
    
    # Format the dataframe
    formatted_df = format_gap_display_df(display_df, display_filters)
    
    # Add Category column at the beginning if not present
    if 'Cat' not in formatted_df.columns and 'category' in display_df.columns:
        # Insert category after period status
        cols = list(formatted_df.columns)
        cat_values = display_df['category'].values
        formatted_df.insert(1, 'Cat', cat_values[:len(formatted_df)])
    
    # Display table with optional highlighting
    if highlight_rows:
        from .period_helpers import highlight_gap_rows_enhanced
        try:
            styled_df = formatted_df.style.apply(highlight_gap_rows_enhanced, axis=1)
            st.dataframe(styled_df, use_container_width=True, height=500)
        except Exception as e:
            logger.warning(f"Highlighting failed: {e}")
            st.dataframe(formatted_df, use_container_width=True, height=500)
    else:
        st.dataframe(formatted_df, use_container_width=True, height=500)


# =============================================================================
# TAB 2: PRODUCT SUMMARY
# =============================================================================

def create_product_summary_df(gap_df: pd.DataFrame, track_backlog: bool = True) -> pd.DataFrame:
    """
    Create product summary dataframe - one row per product
    Matches Product_Summary Excel sheet
    """
    from .shortage_analyzer import categorize_products
    
    if gap_df.empty:
        return pd.DataFrame()
    
    categorization = categorize_products(gap_df)
    
    summary_rows = []
    
    for pt_code in gap_df['pt_code'].unique():
        product_df = gap_df[gap_df['pt_code'] == pt_code].copy()
        
        # Get product info
        brand = product_df['brand'].iloc[0] if 'brand' in product_df.columns else ''
        product_name = product_df['product_name'].iloc[0] if 'product_name' in product_df.columns else ''
        package_size = product_df['package_size'].iloc[0] if 'package_size' in product_df.columns else ''
        uom = product_df['standard_uom'].iloc[0] if 'standard_uom' in product_df.columns else ''
        
        # Calculate totals
        total_demand = product_df['total_demand_qty'].sum()
        total_supply = product_df['supply_in_period'].sum()
        net_position = total_supply - total_demand
        
        # Calculate averages
        avg_fill = product_df['fulfillment_rate_percent'].mean()
        
        # Shortage/Surplus quantities
        shortage_qty = abs(product_df[product_df['gap_quantity'] < 0]['gap_quantity'].sum())
        surplus_qty = product_df[product_df['gap_quantity'] > 0]['gap_quantity'].sum()
        
        # Period counts
        shortage_periods = (product_df['gap_quantity'] < 0).sum()
        surplus_periods = (product_df['gap_quantity'] > 0).sum()
        total_periods = len(product_df)
        
        # Final backlog
        final_backlog = 0
        if track_backlog and 'backlog_to_next' in product_df.columns:
            final_backlog = product_df['backlog_to_next'].iloc[-1] if not product_df.empty else 0
        
        # Determine category
        if pt_code in categorization['net_shortage']:
            category = "🚨 Net Shortage"
            category_sort = 1
        elif pt_code in categorization['net_surplus']:
            category = "📈 Net Surplus"
            category_sort = 3
        else:
            category = "✅ Balanced"
            category_sort = 2
        
        # Timing issue flag
        has_timing_issue = (shortage_periods > 0 and surplus_periods > 0)
        timing_flag = "⚠️" if has_timing_issue else ""
        
        # Recommended action
        if pt_code in categorization['net_shortage']:
            action = "New Order"
        elif pt_code in categorization['timing_shortage'] and pt_code not in categorization['net_shortage']:
            action = "Expedite"
        elif pt_code in categorization['net_surplus']:
            action = "Review Stock"
        else:
            action = "Monitor"
        
        summary_rows.append({
            'category': category,
            'category_sort': category_sort,
            'pt_code': pt_code,
            'brand': brand,
            'product_name': product_name,
            'package_size': package_size,
            'uom': uom,
            'total_demand': total_demand,
            'total_supply': total_supply,
            'net_position': net_position,
            'avg_fill_pct': avg_fill,
            'shortage_qty': shortage_qty,
            'surplus_qty': surplus_qty,
            'shortage_periods': shortage_periods,
            'surplus_periods': surplus_periods,
            'total_periods': total_periods,
            'final_backlog': final_backlog,
            'timing_issue': timing_flag,
            'action': action
        })
    
    summary_df = pd.DataFrame(summary_rows)
    
    # Sort by category then by net position
    if not summary_df.empty:
        summary_df = summary_df.sort_values(['category_sort', 'net_position'], ascending=[True, True])
        summary_df = summary_df.drop(columns=['category_sort'])
    
    return summary_df


def render_product_summary_tab(
    gap_df: pd.DataFrame,
    display_filters: Dict[str, Any]
):
    """
    Render Product Summary tab - matches Product_Summary Excel sheet
    Shows one row per product with totals and categorization
    """
    from .formatters import format_number, format_percentage
    from .shortage_analyzer import categorize_products
    
    if gap_df.empty:
        st.info("📭 No data available.")
        return
    
    # Create summary dataframe
    track_backlog = display_filters.get('track_backlog', True)
    summary_df = create_product_summary_df(gap_df, track_backlog)
    
    if summary_df.empty:
        st.warning("⚠️ Could not create product summary.")
        return
    
    # Get categorization for counts
    categorization = categorize_products(gap_df)
    
    # --- Filters ---
    st.markdown("##### 🔍 Filters")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        category_filter = st.selectbox(
            "Category",
            options=["All", "🚨 Net Shortage", "✅ Balanced", "📈 Net Surplus"],
            key="tab2_category"
        )
    
    with col2:
        sort_by = st.selectbox(
            "Sort by",
            options=["Net Position", "Shortage Qty", "Surplus Qty", "Avg Fill %", "Product"],
            key="tab2_sort"
        )
    
    with col3:
        sort_order = st.radio(
            "Order",
            options=["Ascending", "Descending"],
            horizontal=True,
            key="tab2_order"
        )
    
    # Apply category filter
    filtered_df = summary_df.copy()
    if category_filter != "All":
        filtered_df = filtered_df[filtered_df['category'] == category_filter]
    
    # Apply sorting
    sort_col_map = {
        "Net Position": "net_position",
        "Shortage Qty": "shortage_qty",
        "Surplus Qty": "surplus_qty",
        "Avg Fill %": "avg_fill_pct",
        "Product": "pt_code"
    }
    sort_col = sort_col_map.get(sort_by, "net_position")
    ascending = (sort_order == "Ascending")
    filtered_df = filtered_df.sort_values(sort_col, ascending=ascending)
    
    # Show summary counts
    st.caption(
        f"📊 {len(filtered_df)} products | "
        f"🚨 {len(categorization['net_shortage'])} Net Shortage | "
        f"✅ {len(categorization['balanced'])} Balanced | "
        f"📈 {len(categorization['net_surplus'])} Net Surplus"
    )
    
    if filtered_df.empty:
        st.warning("⚠️ No products match the selected filter.")
        return
    
    # Format for display
    display_df = filtered_df.copy()
    
    # Format numeric columns
    display_df['total_demand'] = display_df['total_demand'].apply(lambda x: format_number(x))
    display_df['total_supply'] = display_df['total_supply'].apply(lambda x: format_number(x))
    display_df['net_position'] = display_df['net_position'].apply(lambda x: format_number(x))
    display_df['avg_fill_pct'] = display_df['avg_fill_pct'].apply(lambda x: format_percentage(x))
    display_df['shortage_qty'] = display_df['shortage_qty'].apply(lambda x: format_number(x))
    display_df['surplus_qty'] = display_df['surplus_qty'].apply(lambda x: format_number(x))
    display_df['final_backlog'] = display_df['final_backlog'].apply(lambda x: format_number(x))
    
    # Rename columns for display
    display_df = display_df.rename(columns={
        'category': 'Cat',
        'pt_code': 'PT Code',
        'brand': 'Brand',
        'product_name': 'Product',
        'package_size': 'Pack Size',
        'uom': 'UOM',
        'total_demand': 'Total Demand',
        'total_supply': 'Total Supply',
        'net_position': 'Net Position',
        'avg_fill_pct': 'Avg Fill %',
        'shortage_qty': 'Shortage Qty',
        'surplus_qty': 'Surplus Qty',
        'shortage_periods': 'Short Periods',
        'surplus_periods': 'Surp Periods',
        'total_periods': 'Total Periods',
        'final_backlog': 'Final Backlog',
        'timing_issue': 'Timing',
        'action': 'Action'
    })
    
    # Remove backlog columns if not tracking
    if not track_backlog:
        cols_to_drop = ['Final Backlog']
        display_df = display_df.drop(columns=[c for c in cols_to_drop if c in display_df.columns])
    
    st.dataframe(display_df, use_container_width=True, height=500)
    
    st.caption("💡 Click on a product row to filter GAP Detail tab (coming soon)")


# =============================================================================
# TAB 3: PERIOD SUMMARY
# =============================================================================

def create_period_summary_df(gap_df: pd.DataFrame, period_type: str = "Weekly") -> pd.DataFrame:
    """
    Create period summary dataframe - one row per period
    Matches Period_Summary Excel sheet
    """
    from .period_helpers import is_past_period, parse_week_period, parse_month_period
    
    if gap_df.empty:
        return pd.DataFrame()
    
    summary_rows = []
    
    for period in gap_df['period'].unique():
        period_df = gap_df[gap_df['period'] == period].copy()
        
        # Check if past period
        is_past = is_past_period(str(period), period_type)
        status = "🔴" if is_past else ""
        
        # Calculate metrics
        products_count = period_df['pt_code'].nunique()
        total_demand = period_df['total_demand_qty'].sum()
        total_supply = period_df['supply_in_period'].sum()
        net_gap = total_supply - total_demand
        avg_fill = period_df['fulfillment_rate_percent'].mean()
        
        # Products with shortage/surplus
        products_shortage = (period_df['gap_quantity'] < 0).sum()
        products_surplus = (period_df['gap_quantity'] > 0).sum()
        
        # Total shortage/surplus quantities
        total_shortage_qty = abs(period_df[period_df['gap_quantity'] < 0]['gap_quantity'].sum())
        total_surplus_qty = period_df[period_df['gap_quantity'] > 0]['gap_quantity'].sum()
        
        # Period health
        if avg_fill >= 95:
            health = "🟢"
        elif avg_fill >= 80:
            health = "🟡"
        else:
            health = "🔴"
        
        # Sort key
        if period_type == "Weekly":
            sort_key = parse_week_period(str(period))
        elif period_type == "Monthly":
            sort_key = parse_month_period(str(period))
        else:
            sort_key = (0, 0)
        
        summary_rows.append({
            'status': status,
            'period': period,
            'sort_key': sort_key,
            'products_count': products_count,
            'total_demand': total_demand,
            'total_supply': total_supply,
            'net_gap': net_gap,
            'avg_fill_pct': avg_fill,
            'products_shortage': products_shortage,
            'products_surplus': products_surplus,
            'total_shortage_qty': total_shortage_qty,
            'total_surplus_qty': total_surplus_qty,
            'health': health
        })
    
    summary_df = pd.DataFrame(summary_rows)
    
    # Sort by period
    if not summary_df.empty:
        summary_df = summary_df.sort_values('sort_key')
        summary_df = summary_df.drop(columns=['sort_key'])
    
    return summary_df


def render_period_summary_tab(
    gap_df: pd.DataFrame,
    display_filters: Dict[str, Any]
):
    """
    Render Period Summary tab - matches Period_Summary Excel sheet
    Shows one row per period with aggregated metrics and charts
    """
    from .formatters import format_number, format_percentage
    from .period_helpers import format_period_with_dates
    
    if gap_df.empty:
        st.info("📭 No data available.")
        return
    
    period_type = display_filters.get('period_type', 'Weekly')
    
    # Create summary dataframe
    summary_df = create_period_summary_df(gap_df, period_type)
    
    if summary_df.empty:
        st.warning("⚠️ Could not create period summary.")
        return
    
    # --- Options ---
    st.markdown("##### ⚙️ Options")
    opt_col1, opt_col2 = st.columns(2)
    
    with opt_col1:
        include_past = st.checkbox("🔴 Include Past Periods", value=True, key="tab3_past")
    with opt_col2:
        show_charts = st.checkbox("📈 Show Charts", value=True, key="tab3_charts")
    
    # Filter past periods if needed
    filtered_df = summary_df.copy()
    if not include_past:
        filtered_df = filtered_df[filtered_df['status'] != "🔴"]
    
    if filtered_df.empty:
        st.warning("⚠️ No periods to display after filtering.")
        return
    
    # Show period range info
    periods_list = filtered_df['period'].tolist()
    st.caption(f"📊 {len(filtered_df)} periods analyzed | {periods_list[0]} → {periods_list[-1]}")
    
    # --- Charts Section ---
    if show_charts and len(filtered_df) > 1:
        st.markdown("##### 📈 Demand vs Supply Trend")
        
        # Prepare chart data
        chart_df = filtered_df[['period', 'total_demand', 'total_supply', 'net_gap']].copy()
        chart_df['period_short'] = chart_df['period'].apply(
            lambda x: str(x).replace('Week ', 'W').replace(' - ', '-')[:15]
        )
        
        # Create bar chart using Streamlit native (performance priority)
        bar_data = pd.DataFrame({
            'Period': chart_df['period_short'],
            'Demand': chart_df['total_demand'],
            'Supply': chart_df['total_supply']
        }).set_index('Period')
        
        st.bar_chart(bar_data, use_container_width=True, height=250)
        
        # GAP trend line chart
        st.markdown("##### 📉 GAP Trend")
        gap_data = pd.DataFrame({
            'Period': chart_df['period_short'],
            'Net GAP': chart_df['net_gap']
        }).set_index('Period')
        
        st.line_chart(gap_data, use_container_width=True, height=200)
    
    # --- Data Table ---
    st.markdown("##### 📋 Period Data")
    
    # Format for display
    display_df = filtered_df.copy()
    
    # Format period with date range
    display_df['period'] = display_df['period'].apply(
        lambda x: format_period_with_dates(str(x), period_type)
    )
    
    # Format numeric columns
    display_df['total_demand'] = display_df['total_demand'].apply(lambda x: format_number(x))
    display_df['total_supply'] = display_df['total_supply'].apply(lambda x: format_number(x))
    display_df['net_gap'] = display_df['net_gap'].apply(lambda x: format_number(x))
    display_df['avg_fill_pct'] = display_df['avg_fill_pct'].apply(lambda x: format_percentage(x))
    display_df['total_shortage_qty'] = display_df['total_shortage_qty'].apply(lambda x: format_number(x))
    display_df['total_surplus_qty'] = display_df['total_surplus_qty'].apply(lambda x: format_number(x))
    
    # Rename columns
    display_df = display_df.rename(columns={
        'status': 'St',
        'period': 'Period',
        'products_count': 'Products',
        'total_demand': 'Total Demand',
        'total_supply': 'Total Supply',
        'net_gap': 'Net GAP',
        'avg_fill_pct': 'Avg Fill %',
        'products_shortage': 'Prod w/Short',
        'products_surplus': 'Prod w/Surp',
        'total_shortage_qty': 'Shortage Qty',
        'total_surplus_qty': 'Surplus Qty',
        'health': 'Health'
    })
    
    st.dataframe(display_df, use_container_width=True, height=350)
    
    # Legend
    st.caption("Health: 🟢 Fill ≥95% | 🟡 Fill 80-95% | 🔴 Fill <80%")
    st.caption("💡 Click on a period row to filter GAP Detail tab (coming soon)")


# =============================================================================
# TAB 4: PIVOT VIEW
# =============================================================================

def render_pivot_view_tab(
    gap_df: pd.DataFrame,
    display_filters: Dict[str, Any]
):
    """
    Render Pivot View tab - matches Pivot_View Excel sheet
    Shows products × periods matrix
    """
    from .helpers import create_period_pivot
    from .formatters import format_number, format_percentage
    from .period_helpers import is_past_period
    from .shortage_analyzer import categorize_products
    
    if gap_df.empty:
        st.info("📭 No data available.")
        return
    
    period_type = display_filters.get('period_type', 'Weekly')
    categorization = categorize_products(gap_df)
    
    # --- Options ---
    st.markdown("##### ⚙️ Options")
    
    opt_col1, opt_col2, opt_col3 = st.columns(3)
    
    with opt_col1:
        value_type = st.radio(
            "Value",
            options=["GAP Qty", "Fill %", "Demand", "Supply"],
            horizontal=True,
            key="tab4_value"
        )
    
    with opt_col2:
        show_totals = st.checkbox("➕ Show Totals Column", value=True, key="tab4_totals")
    
    with opt_col3:
        show_past_ind = st.checkbox("🔴 Past Period Indicator", value=True, key="tab4_past_ind")
    
    # Map value type to column
    value_col_map = {
        "GAP Qty": "gap_quantity",
        "Fill %": "fulfillment_rate_percent",
        "Demand": "total_demand_qty",
        "Supply": "supply_in_period"
    }
    value_col = value_col_map.get(value_type, "gap_quantity")
    
    # Create pivot
    pivot_df = create_period_pivot(
        df=gap_df,
        group_cols=["product_name", "pt_code"],
        period_col="period",
        value_col=value_col,
        agg_func="sum",
        period_type=period_type,
        show_only_nonzero=False,
        fill_value=0
    )
    
    if pivot_df.empty:
        st.warning("⚠️ Could not create pivot view.")
        return
    
    # Add category column
    def get_category_icon(pt_code):
        if pt_code in categorization['net_shortage']:
            return "🚨"
        elif pt_code in categorization['net_surplus']:
            return "📈"
        elif pt_code in categorization['balanced']:
            return "✅"
        return "❓"
    
    pivot_df.insert(2, 'Cat', pivot_df['pt_code'].apply(get_category_icon))
    
    # Add totals column if requested
    if show_totals:
        period_cols = [col for col in pivot_df.columns if col not in ['product_name', 'pt_code', 'Cat']]
        if period_cols:
            pivot_df['Total'] = pivot_df[period_cols].sum(axis=1)
    
    # Add past period indicators to column names
    if show_past_ind:
        renamed_columns = {}
        for col in pivot_df.columns:
            if col not in ['product_name', 'pt_code', 'Cat', 'Total']:
                if is_past_period(str(col), period_type):
                    renamed_columns[col] = f"🔴{col}"
        if renamed_columns:
            pivot_df = pivot_df.rename(columns=renamed_columns)
    
    # Show legend
    st.caption("Category: 🚨 Net Shortage | 📈 Net Surplus | ✅ Balanced | Period: 🔴 Past")
    
    # Format numbers
    numeric_cols = [col for col in pivot_df.columns if col not in ['product_name', 'pt_code', 'Cat']]
    for col in numeric_cols:
        if value_type == "Fill %":
            pivot_df[col] = pivot_df[col].apply(lambda x: format_percentage(x) if pd.notna(x) else "")
        else:
            pivot_df[col] = pivot_df[col].apply(lambda x: format_number(x) if pd.notna(x) else "")
    
    # Rename info columns
    pivot_df = pivot_df.rename(columns={
        'product_name': 'Product',
        'pt_code': 'PT Code'
    })
    
    st.caption(f"📊 {len(pivot_df)} products × {len(numeric_cols)} periods")
    
    st.dataframe(pivot_df, use_container_width=True, height=450)


# =============================================================================
# ACTION ITEMS EXPANDER
# =============================================================================

def create_action_items_df(
    gap_df: pd.DataFrame,
    supply_df: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Create action items dataframe - matches Action_Items Excel sheet
    """
    from .shortage_analyzer import categorize_products
    
    if gap_df.empty:
        return pd.DataFrame()
    
    categorization = categorize_products(gap_df)
    
    action_items = []
    
    # Process Net Shortage products - New Order actions
    for pt_code in categorization['net_shortage']:
        product_df = gap_df[gap_df['pt_code'] == pt_code]
        
        total_demand = product_df['total_demand_qty'].sum()
        total_supply = product_df['supply_in_period'].sum()
        shortage_qty = total_demand - total_supply
        
        # Find first shortage period
        shortage_periods = product_df[product_df['gap_quantity'] < 0]
        first_shortage = shortage_periods['period'].iloc[0] if not shortage_periods.empty else ""
        
        # Priority based on shortage timing
        shortage_period_count = (product_df['gap_quantity'] < 0).sum()
        if shortage_period_count >= 3:
            priority = "🔴"
            priority_sort = 1
        elif shortage_period_count >= 2:
            priority = "🟡"
            priority_sort = 2
        else:
            priority = "🔵"
            priority_sort = 3
        
        action_items.append({
            'priority': priority,
            'priority_sort': priority_sort,
            'action_type': 'New Order',
            'pt_code': pt_code,
            'product_name': product_df['product_name'].iloc[0] if 'product_name' in product_df.columns else '',
            'brand': product_df['brand'].iloc[0] if 'brand' in product_df.columns else '',
            'required_qty': shortage_qty,
            'need_by': first_shortage,
            'periods_affected': shortage_period_count,
            'details': f"Net shortage of {shortage_qty:,.0f} units"
        })
    
    # Process Timing Shortage products (not in net shortage) - Expedite actions
    timing_only = categorization['timing_shortage'] - categorization['net_shortage']
    for pt_code in timing_only:
        product_df = gap_df[gap_df['pt_code'] == pt_code]
        
        shortage_periods = product_df[product_df['gap_quantity'] < 0]
        if shortage_periods.empty:
            continue
        
        first_shortage = shortage_periods['period'].iloc[0]
        shortage_qty = abs(shortage_periods['gap_quantity'].sum())
        
        action_items.append({
            'priority': "🟡",
            'priority_sort': 2,
            'action_type': 'Expedite',
            'pt_code': pt_code,
            'product_name': product_df['product_name'].iloc[0] if 'product_name' in product_df.columns else '',
            'brand': product_df['brand'].iloc[0] if 'brand' in product_df.columns else '',
            'required_qty': shortage_qty,
            'need_by': first_shortage,
            'periods_affected': len(shortage_periods),
            'details': f"Timing mismatch - expedite supply"
        })
    
    # Process Net Surplus products - Review Stock actions
    for pt_code in categorization['net_surplus']:
        product_df = gap_df[gap_df['pt_code'] == pt_code]
        
        total_demand = product_df['total_demand_qty'].sum()
        total_supply = product_df['supply_in_period'].sum()
        surplus_qty = total_supply - total_demand
        surplus_pct = (surplus_qty / total_demand * 100) if total_demand > 0 else 100
        
        # Only include if significant surplus
        if surplus_pct >= 20:
            action_items.append({
                'priority': "🔵",
                'priority_sort': 3,
                'action_type': 'Review Stock',
                'pt_code': pt_code,
                'product_name': product_df['product_name'].iloc[0] if 'product_name' in product_df.columns else '',
                'brand': product_df['brand'].iloc[0] if 'brand' in product_df.columns else '',
                'required_qty': surplus_qty,
                'need_by': "",
                'periods_affected': (product_df['gap_quantity'] > 0).sum(),
                'details': f"+{surplus_pct:.0f}% excess inventory"
            })
    
    action_df = pd.DataFrame(action_items)
    
    # Sort by priority then by required qty
    if not action_df.empty:
        action_df = action_df.sort_values(['priority_sort', 'required_qty'], ascending=[True, False])
        action_df = action_df.drop(columns=['priority_sort'])
    
    return action_df


def render_action_items_expander(
    gap_df: pd.DataFrame,
    supply_df: Optional[pd.DataFrame] = None
):
    """
    Render Action Items as collapsible expander
    Matches Action_Items Excel sheet
    """
    from .formatters import format_number
    
    if gap_df.empty:
        return
    
    # Create action items
    action_df = create_action_items_df(gap_df, supply_df)
    
    if action_df.empty:
        with st.expander("🎯 Action Items (0 items)", expanded=False):
            st.success("✅ No action items - all products are properly balanced!")
        return
    
    # Count by action type
    action_counts = action_df['action_type'].value_counts().to_dict()
    total_items = len(action_df)
    
    with st.expander(f"🎯 Action Items ({total_items} items)", expanded=False):
        # Filter by action type
        filter_options = ["All"] + list(action_counts.keys())
        filter_labels = ["All"] + [f"{k} ({v})" for k, v in action_counts.items()]
        
        action_filter = st.radio(
            "Filter:",
            options=filter_options,
            format_func=lambda x: filter_labels[filter_options.index(x)],
            horizontal=True,
            key="action_filter"
        )
        
        # Apply filter
        filtered_df = action_df.copy()
        if action_filter != "All":
            filtered_df = filtered_df[filtered_df['action_type'] == action_filter]
        
        if filtered_df.empty:
            st.info("No items match the selected filter.")
            return
        
        # Format for display
        display_df = filtered_df.copy()
        display_df['required_qty'] = display_df['required_qty'].apply(lambda x: format_number(abs(x)))
        
        # Rename columns
        display_df = display_df.rename(columns={
            'priority': 'Pri',
            'action_type': 'Action',
            'pt_code': 'PT Code',
            'product_name': 'Product',
            'brand': 'Brand',
            'required_qty': 'Qty',
            'need_by': 'Need By',
            'periods_affected': 'Periods',
            'details': 'Details'
        })
        
        st.dataframe(display_df, use_container_width=True, height=300)
        
        # Legend
        st.caption("Priority: 🔴 High (Immediate) | 🟡 Medium (This week) | 🔵 Low (Plan)")


# =============================================================================
# OVERVIEW SECTION
# =============================================================================

def render_overview_section(
    gap_df: pd.DataFrame,
    display_options: Dict[str, Any]
):
    """
    Render Overview section - always visible above tabs
    Compact summary with key metrics
    """
    from .formatters import format_number
    from .shortage_analyzer import categorize_products
    
    if gap_df.empty:
        st.info("📭 No analysis data. Please run the GAP analysis.")
        return
    
    # Get categorization
    categorization = categorize_products(gap_df)
    
    # Calculate metrics
    total_products = gap_df['pt_code'].nunique()
    total_periods = gap_df['period'].nunique()
    
    net_shortage_count = len(categorization['net_shortage'])
    balanced_count = len(categorization['balanced'])
    net_surplus_count = len(categorization['net_surplus'])
    
    total_demand = gap_df['total_demand_qty'].sum()
    total_supply = gap_df['supply_in_period'].sum()
    supply_coverage = min(100, (total_supply / total_demand * 100)) if total_demand > 0 else 100
    
    # Determine status
    if net_shortage_count > 0:
        status_color = "#dc3545"
        status_bg = "#f8d7da"
        status_icon = "🚨"
        status_text = "Net Shortage Detected"
        status_detail = f"{net_shortage_count} products need new orders"
    elif len(categorization['timing_shortage']) > 0:
        status_color = "#ffc107"
        status_bg = "#fff3cd"
        status_icon = "⚠️"
        status_text = "Timing Shortages Detected"
        status_detail = f"{len(categorization['timing_shortage'])} products need expediting"
    elif net_surplus_count > 0:
        status_color = "#17a2b8"
        status_bg = "#d1ecf1"
        status_icon = "📈"
        status_text = "Net Surplus Detected"
        status_detail = f"{net_surplus_count} products have excess inventory"
    else:
        status_color = "#28a745"
        status_bg = "#d4edda"
        status_icon = "✅"
        status_text = "Supply Meets Demand"
        status_detail = "All products are properly balanced"
    
    # Status card
    st.markdown(f"""
    <div style="background-color: {status_bg}; padding: 12px 16px; border-radius: 8px; 
                border-left: 4px solid {status_color}; margin-bottom: 12px;">
        <span style="font-size: 1.3em; font-weight: 600; color: {status_color};">
            {status_icon} {status_text}
        </span>
        <span style="margin-left: 16px; color: #555;">{status_detail}</span>
    </div>
    """, unsafe_allow_html=True)
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("🚨 Net Shortage", net_shortage_count, help="Products where total supply < total demand")
    with col2:
        st.metric("✅ Balanced", balanced_count, help="Products with exact supply-demand balance")
    with col3:
        st.metric("📈 Net Surplus", net_surplus_count, help="Products where total supply > total demand")
    with col4:
        st.metric("📅 Periods", total_periods, help="Number of periods analyzed")
    
    # Supply coverage bar
    st.caption(f"Supply Coverage: {supply_coverage:.1f}% | Demand: {format_number(total_demand)} | Supply: {format_number(total_supply)}")
    st.progress(supply_coverage / 100)
