# utils/period_gap/gap_display.py
"""
Display Functions for Period GAP Analysis
Handles all visualization and presentation logic
Version 3.0 - Refactored with mutually exclusive categories + timing flags
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def show_gap_summary(
    gap_df: pd.DataFrame, 
    display_options: Dict[str, Any],
    df_demand_filtered: Optional[pd.DataFrame] = None,
    df_supply_filtered: Optional[pd.DataFrame] = None
):
    """
    Show GAP analysis summary with mutually exclusive categories + timing flags
    
    Args:
        gap_df: GAP analysis results
        display_options: Display configuration options
        df_demand_filtered: Filtered demand data (for additional context)
        df_supply_filtered: Filtered supply data (for additional context)
    """
    from .formatters import format_number, format_currency
    from .period_helpers import is_past_period
    from .shortage_analyzer import categorize_products, get_shortage_summary
    
    st.markdown("### 📊 GAP Analysis Summary")
    
    if gap_df.empty:
        st.warning("No GAP data available for summary.")
        return
    
    # Verify required columns exist
    required_columns = ['pt_code', 'gap_quantity', 'period', 'total_demand_qty', 
                       'total_available', 'supply_in_period', 'fulfillment_rate_percent']
    missing_columns = [col for col in required_columns if col not in gap_df.columns]
    
    if missing_columns:
        st.error(f"Missing required columns in GAP data: {missing_columns}")
        return
    
    # Categorize products using new unified function
    categorization = categorize_products(gap_df)
    
    net_shortage_products = categorization['net_shortage']
    net_surplus_products = categorization['net_surplus']
    balanced_products = categorization['balanced']
    timing_shortage_products = categorization['timing_shortage']
    timing_surplus_products = categorization['timing_surplus']
    
    # Calculate essential metrics
    total_products = gap_df['pt_code'].nunique()
    total_periods = gap_df['period'].nunique()
    
    # Metrics for different categories (mutually exclusive main categories)
    products_with_net_shortage = len(net_shortage_products)
    products_with_net_surplus = len(net_surplus_products)
    products_balanced = len(balanced_products)
    
    # Timing flags (cross-cutting)
    products_with_timing_shortage = len(timing_shortage_products)
    products_with_timing_surplus = len(timing_surplus_products)
    
    # Calculate shortage and surplus quantities
    net_shortage_qty = gap_df[gap_df['pt_code'].isin(net_shortage_products)]['gap_quantity'].clip(upper=0).abs().sum()
    net_surplus_qty = gap_df[gap_df['pt_code'].isin(net_surplus_products)]['gap_quantity'].clip(lower=0).sum()
    timing_shortage_qty = gap_df[gap_df['pt_code'].isin(timing_shortage_products) & (gap_df['gap_quantity'] < 0)]['gap_quantity'].abs().sum()
    timing_surplus_qty = gap_df[gap_df['pt_code'].isin(timing_surplus_products) & (gap_df['gap_quantity'] > 0)]['gap_quantity'].sum()
    
    # Calculate backlog metrics if tracking
    track_backlog = display_options.get('track_backlog', True)
    if track_backlog and 'backlog_to_next' in gap_df.columns:
        final_backlog_by_product = gap_df.groupby('pt_code')['backlog_to_next'].last()
        total_backlog = final_backlog_by_product.sum()
        products_with_backlog = (final_backlog_by_product > 0).sum()
    else:
        total_backlog = 0
        products_with_backlog = 0
    
    # Determine overall status with improved categorization
    if products_with_net_shortage > 0:
        status_color = "#dc3545"
        status_bg_color = "#f8d7da"
        status_icon = "🚨"
        status_text = "Net Shortage Detected"
        status_detail = f"{products_with_net_shortage} products need new orders | {products_with_timing_shortage} products have timing shortages"
    elif products_with_timing_shortage > 0:
        status_color = "#ffc107"
        status_bg_color = "#fff3cd"
        status_icon = "⚠️"
        status_text = "Timing Shortages Detected"
        status_detail = f"{products_with_timing_shortage} products have shortage periods (expedite/reschedule needed)"
    elif products_with_backlog > 0:
        status_color = "#fd7e14"
        status_bg_color = "#fff3cd"
        status_icon = "⚠️"
        status_text = "Backlog Detected"
        status_detail = f"{products_with_backlog} products have unfulfilled demand carried forward"
    elif products_with_net_surplus > 0:
        status_color = "#17a2b8"
        status_bg_color = "#d1ecf1"
        status_icon = "📈"
        status_text = "Net Surplus Detected"
        status_detail = f"{products_with_net_surplus} products have excess inventory to review"
    elif products_with_timing_surplus > 0:
        status_color = "#6c757d"
        status_bg_color = "#e2e3e5"
        status_icon = "⏰"
        status_text = "Timing Surplus Detected"
        status_detail = f"{products_with_timing_surplus} products have surplus periods that could be optimized"
    else:
        status_color = "#28a745"
        status_bg_color = "#d4edda"
        status_icon = "✅"
        status_text = "Supply Meets Demand"
        status_detail = "All products have balanced supply with proper timing"
    
    # Main status card
    st.markdown(f"""
    <div style="background-color: {status_bg_color}; padding: 20px; border-radius: 10px; border-left: 5px solid {status_color};">
        <h2 style="margin: 0; color: {status_color};">{status_icon} {status_text}</h2>
        <p style="margin: 10px 0 0 0; font-size: 18px; color: #333;">
            {status_detail}
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("")
    
    # Show tracking mode info
    if track_backlog:
        st.info("📊 **Backlog Tracking: ON** - Unfulfilled demand accumulates to next periods")
    else:
        st.info("📊 **Backlog Tracking: OFF** - Each period calculated independently")
    
    # Show categorization breakdown - Main categories + Timing flags
    st.markdown("#### 🎯 Product Categorization")
    
    # Main categories (mutually exclusive)
    st.caption("**Main Categories (Mutually Exclusive):**")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "🚨 Net Shortage",
            f"{products_with_net_shortage}",
            delta=f"{format_number(net_shortage_qty)} units" if net_shortage_qty > 0 else "None",
            delta_color="inverse" if products_with_net_shortage > 0 else "off",
            help="Products where total supply < total demand - Need new orders"
        )
    
    with col2:
        st.metric(
            "✅ Balanced",
            f"{products_balanced}",
            delta=f"{(products_balanced/total_products*100):.0f}%" if total_products > 0 else "0%",
            delta_color="normal" if products_balanced > 0 else "off",
            help="Products with exact balance (total supply = total demand)"
        )
    
    with col3:
        st.metric(
            "📈 Net Surplus",
            f"{products_with_net_surplus}",
            delta=f"+{format_number(net_surplus_qty)} units" if net_surplus_qty > 0 else "None",
            delta_color="normal" if products_with_net_surplus > 0 else "off",
            help="Products where total supply > total demand - Review excess stock"
        )
    
    # Timing flags (cross-cutting)
    st.caption("**Timing Flags (Cross-cutting):**")
    col4, col5 = st.columns(2)
    
    with col4:
        st.metric(
            "⚠️ Timing Shortage",
            f"{products_with_timing_shortage}",
            delta=f"{format_number(timing_shortage_qty)} units in periods" if timing_shortage_qty > 0 else "None",
            delta_color="inverse" if products_with_timing_shortage > 0 else "off",
            help="Products with shortage periods - Need expedite/reschedule"
        )
    
    with col5:
        st.metric(
            "⏰ Timing Surplus",
            f"{products_with_timing_surplus}",
            delta=f"+{format_number(timing_surplus_qty)} units in periods" if timing_surplus_qty > 0 else "None",
            delta_color="normal" if products_with_timing_surplus > 0 else "off",
            help="Products with surplus periods - Optimize schedule"
        )
    
    # Expandable action items
    with st.expander("📋 View Action Items", expanded=(products_with_net_shortage > 0 or products_with_timing_shortage > 0)):
        
        if products_with_net_shortage > 0 or products_with_timing_shortage > 0 or products_with_net_surplus > 0:
            
            action_col1, action_col2, action_col3 = st.columns(3)
            
            with action_col1:
                st.markdown("##### 📦 Products Needing Orders")
                if products_with_net_shortage > 0:
                    # Get top products with net shortage
                    net_shortage_df = gap_df[gap_df['pt_code'].isin(net_shortage_products)]
                    product_shortage = net_shortage_df.groupby('pt_code').agg({
                        'gap_quantity': lambda x: x[x < 0].sum() if any(x < 0) else 0,
                        'total_demand_qty': 'sum',
                        'supply_in_period': 'sum'
                    })
                    product_shortage['net_shortage'] = product_shortage['total_demand_qty'] - product_shortage['supply_in_period']
                    product_shortage = product_shortage[product_shortage['net_shortage'] > 0]
                    product_shortage = product_shortage.sort_values('net_shortage', ascending=False).head(5)
                    
                    for pt_code, row in product_shortage.iterrows():
                        st.caption(f"• **{pt_code}**: Order {format_number(row['net_shortage'])} units")
                else:
                    st.caption("✅ No new orders needed")
            
            with action_col2:
                st.markdown("##### ⏱️ Products Needing Expedite")
                if products_with_timing_shortage > 0:
                    # Get top products with timing shortages
                    timing_shortage_df = gap_df[gap_df['pt_code'].isin(timing_shortage_products)]
                    product_timing = timing_shortage_df.groupby('pt_code').agg({
                        'gap_quantity': lambda x: x[x < 0].sum() if any(x < 0) else 0,
                        'period': lambda x: x[timing_shortage_df.loc[x.index, 'gap_quantity'] < 0].iloc[0] if any(timing_shortage_df.loc[x.index, 'gap_quantity'] < 0) else None
                    })
                    product_timing['gap_quantity'] = product_timing['gap_quantity'].abs()
                    product_timing = product_timing[product_timing['gap_quantity'] > 0]
                    product_timing = product_timing.sort_values('gap_quantity', ascending=False).head(5)
                    
                    for pt_code, row in product_timing.iterrows():
                        period_str = row['period'] if pd.notna(row['period']) else "Unknown"
                        st.caption(f"• **{pt_code}**: Expedite for {period_str}")
                else:
                    st.caption("✅ No expedite needed")
            
            with action_col3:
                st.markdown("##### 📈 Products with Excess")
                if products_with_net_surplus > 0:
                    # Get top products with net surplus
                    net_surplus_df = gap_df[gap_df['pt_code'].isin(net_surplus_products)]
                    product_surplus = net_surplus_df.groupby('pt_code').agg({
                        'total_demand_qty': 'sum',
                        'supply_in_period': 'sum'
                    })
                    product_surplus['net_surplus'] = product_surplus['supply_in_period'] - product_surplus['total_demand_qty']
                    product_surplus = product_surplus[product_surplus['net_surplus'] > 0]
                    product_surplus = product_surplus.sort_values('net_surplus', ascending=False).head(5)
                    
                    for pt_code, row in product_surplus.iterrows():
                        st.caption(f"• **{pt_code}**: +{format_number(row['net_surplus'])} excess")
                else:
                    st.caption("✅ No excess inventory")
        
        else:
            st.success("✅ No action items - All products are properly balanced")
        
        # Summary statistics
        st.markdown("##### 📊 Supply vs Demand Balance")
        
        if track_backlog and 'effective_demand' in gap_df.columns:
            total_demand = gap_df.groupby(['pt_code', 'period'])['effective_demand'].first().sum()
            display_demand_label = "Total Effective Demand"
        else:
            total_demand = gap_df['total_demand_qty'].sum()
            display_demand_label = "Total Demand"
        
        total_supply = gap_df['supply_in_period'].sum()
        net_position = total_supply - total_demand
        
        balance_col1, balance_col2, balance_col3 = st.columns([2, 1, 2])
        
        with balance_col1:
            st.metric(display_demand_label, format_number(total_demand))
        
        with balance_col2:
            if net_position >= 0:
                st.markdown("<h2 style='text-align: center; color: green;'>→</h2>", unsafe_allow_html=True)
            else:
                st.markdown("<h2 style='text-align: center; color: red;'>→</h2>", unsafe_allow_html=True)
        
        with balance_col3:
            st.metric(
                "Total Supply", 
                format_number(total_supply),
                delta=format_number(net_position),
                delta_color="normal" if net_position >= 0 else "inverse"
            )
        
        if total_demand > 0:
            supply_rate = min(total_supply / total_demand * 100, 100)
            st.progress(supply_rate / 100)
            st.caption(f"Supply covers {supply_rate:.1f}% of total {display_demand_label.lower()}")


def show_gap_detail_table(
    gap_df: pd.DataFrame,
    display_filters: Dict[str, Any],
    df_demand_filtered: Optional[pd.DataFrame] = None,
    df_supply_filtered: Optional[pd.DataFrame] = None
):
    """Show detailed GAP analysis table with enhanced categorization"""
    from .period_helpers import prepare_gap_detail_display, format_gap_display_df
    from .shortage_analyzer import categorize_products
    
    st.markdown("### 📋 GAP Details by Product & Period")
    
    if gap_df.empty:
        st.info("No data matches the selected filters.")
        return
    
    # Add categorization info
    categorization = categorize_products(gap_df)
    
    # Show filter status with enhanced info
    filter_status = display_filters.get('period_filter', 'All')
    if filter_status == "Net Shortage":
        st.info(f"🚨 Showing {len(categorization['net_shortage'])} products with net shortage (need new orders)")
    elif filter_status == "Timing Shortage":
        st.info(f"⚠️ Showing {len(categorization['timing_shortage'])} products with timing shortages (expedite/reschedule)")
    elif filter_status == "Net Surplus":
        st.info(f"📈 Showing {len(categorization['net_surplus'])} products with net surplus (excess inventory)")
    elif filter_status == "Timing Surplus":
        st.info(f"⏰ Showing {len(categorization['timing_surplus'])} products with timing surplus (optimize schedule)")
    else:
        st.caption(f"Showing {len(gap_df):,} records")
    
    # Prepare display dataframe
    display_df = prepare_gap_detail_display(
        gap_df, 
        display_filters, 
        df_demand_filtered, 
        df_supply_filtered
    )
    
    # Add category column
    def get_product_category(pt_code):
        if pt_code in categorization['net_shortage']:
            return "🚨 Net Shortage"
        elif pt_code in categorization['net_surplus']:
            return "📈 Net Surplus"
        elif pt_code in categorization['balanced']:
            return "✅ Balanced"
        else:
            return "❓ Unknown"
    
    display_df['category'] = display_df['pt_code'].apply(get_product_category)
    
    # Format the dataframe
    formatted_df = format_gap_display_df(display_df, display_filters)
    
    # Apply row highlighting if enabled
    if display_filters.get("enable_row_highlighting", False):
        from .period_helpers import highlight_gap_rows_enhanced
        styled_df = formatted_df.style.apply(highlight_gap_rows_enhanced, axis=1)
        st.dataframe(styled_df, use_container_width=True, height=600)
    else:
        st.dataframe(formatted_df, use_container_width=True, height=600)


def show_gap_pivot_view(gap_df: pd.DataFrame, display_options: Dict[str, Any]):
    """Show GAP pivot view with past period indicators and enhanced category info"""
    from .helpers import create_period_pivot
    from .formatters import format_number
    from .period_helpers import is_past_period
    from .shortage_analyzer import categorize_products
    
    st.markdown("### 📊 Pivot View - GAP by Period")
    
    if gap_df.empty:
        st.info("No data to display in pivot view.")
        return
    
    # Get categorization
    categorization = categorize_products(gap_df)
    
    # Create pivot
    pivot_df = create_period_pivot(
        df=gap_df,
        group_cols=["product_name", "pt_code"],
        period_col="period",
        value_col="gap_quantity",
        agg_func="sum",
        period_type=display_options["period_type"],
        show_only_nonzero=False,
        fill_value=0
    )
    
    if pivot_df.empty:
        st.info("No data to display after pivoting.")
        return
    
    # Add category column with icons
    def get_category_icon(pt_code):
        if pt_code in categorization['net_shortage']:
            return "🚨"
        elif pt_code in categorization['net_surplus']:
            return "📈"
        elif pt_code in categorization['balanced']:
            return "✅"
        else:
            return "❓"
    
    pivot_df.insert(2, 'Category', pivot_df['pt_code'].apply(get_category_icon))
    
    # Add past period indicators to column names
    renamed_columns = {}
    for col in pivot_df.columns:
        if col not in ["product_name", "pt_code", "Category"]:
            if is_past_period(str(col), display_options["period_type"]):
                renamed_columns[col] = f"🔴 {col}"
    
    if renamed_columns:
        pivot_df = pivot_df.rename(columns=renamed_columns)
    
    # Show enhanced legend
    st.info("**Category:** 🚨 = Net Shortage | 📈 = Net Surplus | ✅ = Balanced | **Period:** 🔴 = Past")
    
    # Format numbers
    for col in pivot_df.columns[3:]:  # Skip product_name, pt_code, and Category columns
        pivot_df[col] = pivot_df[col].apply(lambda x: format_number(x))
    
    st.dataframe(pivot_df, use_container_width=True, height=400)