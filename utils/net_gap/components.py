# utils/net_gap/components.py - VERSION 4.5

"""
UI Components for GAP Analysis - VERSION 4.5
Synchronized with new status classification logic:
- net_gap < 0 → SHORTAGE (with severity levels)
- net_gap = 0 → BALANCED
- net_gap > 0 → SURPLUS (with severity levels)
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
import logging

from .constants import STATUS_ICONS, FIELD_TOOLTIPS, UI_CONFIG, STATUS_CONFIG, GAP_CATEGORIES
from .formatters import GAPFormatter

logger = logging.getLogger(__name__)


# =============================================================================
# STATUS ICONS MAPPING - v4.5 (Option A - Net GAP sign primary)
# =============================================================================
STATUS_ICONS_V45 = {
    # Shortage statuses (net_gap < 0)
    'CRITICAL_SHORTAGE': '🚨',
    'SEVERE_SHORTAGE': '🔴',
    'HIGH_SHORTAGE': '🟠',
    'MODERATE_SHORTAGE': '🟡',
    'LIGHT_SHORTAGE': '⚠️',
    
    # Balanced (net_gap = 0)
    'BALANCED': '✅',
    
    # Surplus statuses (net_gap > 0)
    'LIGHT_SURPLUS': '🔵',
    'MODERATE_SURPLUS': '🟣',
    'HIGH_SURPLUS': '🟠',
    'SEVERE_SURPLUS': '🔴',
    
    # Inactive
    'NO_DEMAND': '⚪',
    'NO_ACTIVITY': '⚪'
}


# =============================================================================
# FORMULA GUIDE - Complete version
# =============================================================================
def render_formula_guide():
    """Render expandable formula explanation guide - Complete version"""
    
    with st.expander("📊 **GAP Calculation Guide** - Click to understand the formulas", expanded=False):
        
        # ===== ROW 1: Core Formulas + Status Logic =====
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("""
            ### Core Formulas
            
            **Safety Gap** = Total Supply - Safety Stock
            - Can be negative when supply is below safety requirement
            - Shows how much buffer you have (or lack)
            
            **Available Supply** = max(0, Safety Gap)
            - When safety enabled: **capped at 0** (never negative)
            - When safety disabled: equals Total Supply
            
            **Net GAP** = Available Supply - Total Demand
            - Primary metric for shortage/surplus
            
            **True GAP** = Total Supply - Total Demand
            - Always ignores safety stock
            - Shows actual supply vs demand difference
            
            **Coverage Ratio** = (Available Supply ÷ Demand) × 100%
            - 100% means surplus, <100% means shortage
            """)
        
        with col2:
            st.markdown("""
            ### v4.5 Status Logic
            
            **Primary rule: Net GAP sign determines group**
            """)
            
            status_logic = pd.DataFrame([
                {'Net GAP': '< 0', 'Group': '🔴 SHORTAGE (always!)'},
                {'Net GAP': '= 0', 'Group': '✅ BALANCED'},
                {'Net GAP': '> 0', 'Group': '📦 SURPLUS (always!)'}
            ])
            st.dataframe(status_logic, use_container_width=True, hide_index=True)
            
            st.markdown("""
            **Secondary: Coverage determines severity**
            
            Within SHORTAGE group:
            - Coverage < 25% → 🚨 Critical
            - Coverage < 50% → 🔴 Severe
            - Coverage < 75% → 🟠 High
            - Coverage < 90% → 🟡 Moderate
            - Coverage < 100% → ⚠️ Light
            """)
        
        st.markdown("---")
        
        # ===== ROW 2: Financial Calculations + Shortage Causes =====
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("""
            ### Financial Calculations
            
            **At Risk Value** = |Shortage Qty| × Selling Price
            - Revenue that could be lost due to shortage
            - Only calculated when Net GAP < 0
            
            **GAP Value** = Net GAP × Unit Cost
            - Inventory value of the gap
            
            **Safety Stock Impact** = Net GAP - True GAP
            - Shows how safety stock affects the gap
            - Negative means safety stock creates shortage
            """)
        
        with col2:
            st.markdown("### Shortage Causes")
            
            causes_data = pd.DataFrame([
                {'Icon': '✅', 'Cause': 'OK - No shortage'},
                {'Icon': '🔒', 'Cause': 'Safety stock requirement'},
                {'Icon': '🚨', 'Cause': 'Real shortage'}
            ])
            st.dataframe(causes_data, use_container_width=True, hide_index=True)
            
            st.markdown("""
            **How to interpret:**
            - **OK**: Net GAP ≥ 0, no action needed
            - **Safety Requirement**: True GAP ≥ 0 but Net GAP < 0  
              (shortage caused by safety stock reservation)
            - **Real Shortage**: True GAP < 0  
              (actual supply cannot meet demand)
            """)
        
        st.markdown("---")
        
        # ===== ROW 3: Example Scenarios =====
        st.markdown("### Example Scenarios")
        
        example_data = pd.DataFrame([
            {
                'Scenario': '✅ Healthy',
                'Supply': 100,
                'Safety': 20,
                'Demand': 50,
                'Safety Gap': '+80',
                'Available': 80,
                'Net GAP': '+30',
                'True GAP': '+50',
                'Cause': '✅ OK'
            },
            {
                'Scenario': '⚠️ Tight',
                'Supply': 100,
                'Safety': 20,
                'Demand': 90,
                'Safety Gap': '+80',
                'Available': 80,
                'Net GAP': '-10',
                'True GAP': '+10',
                'Cause': '🔒 Safety Requirement'
            },
            {
                'Scenario': '🔴 Real Shortage',
                'Supply': 50,
                'Safety': 20,
                'Demand': 80,
                'Safety Gap': '+30',
                'Available': 30,
                'Net GAP': '-50',
                'True GAP': '-30',
                'Cause': '🚨 Real Shortage'
            },
            {
                'Scenario': '⚠️ Under Safety',
                'Supply': 3,
                'Safety': 25,
                'Demand': 3,
                'Safety Gap': '-22',
                'Available': 0,
                'Net GAP': '-3',
                'True GAP': '0',
                'Cause': '🔒 Supply < Safety Req.'
            }
        ])
        
        st.dataframe(
            example_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                'Scenario': st.column_config.TextColumn('Scenario', width='medium'),
                'Supply': st.column_config.NumberColumn('Supply', format='%d'),
                'Safety': st.column_config.NumberColumn('Safety', format='%d'),
                'Demand': st.column_config.NumberColumn('Demand', format='%d'),
                'Safety Gap': st.column_config.TextColumn('Safety Gap', width='small'),
                'Available': st.column_config.NumberColumn('Available', format='%d'),
                'Net GAP': st.column_config.TextColumn('Net GAP', width='small'),
                'True GAP': st.column_config.TextColumn('True GAP', width='small'),
                'Cause': st.column_config.TextColumn('Cause', width='medium')
            }
        )
        
        st.info("""
        💡 **Key Insight**: The "Under Safety" scenario shows why Safety Gap column is important.
        Even when True GAP = 0 (supply equals demand), the item shows as shortage because 
        supply (3) is below safety requirement (25), leaving no Available Supply for demand.
        """)


# =============================================================================
# KPI CARDS
# =============================================================================
def render_kpi_cards(metrics: Dict[str, Any], include_safety: bool = False):
    """Render KPI metric cards"""
    
    # Row 1: Core metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "📦 Total Products",
            f"{metrics['total_products']:,}",
            help="Total number of products analyzed"
        )
    
    with col2:
        shortage_pct = (metrics['shortage_items'] / max(metrics['total_products'], 1)) * 100
        st.metric(
            "⚠️ Shortage Items",
            f"{metrics['shortage_items']:,}",
            f"{shortage_pct:.1f}% of total",
            delta_color="inverse"
        )
    
    with col3:
        st.metric(
            "🚨 Critical Items",
            f"{metrics['critical_items']:,}",
            "Immediate action" if metrics['critical_items'] > 0 else "All good",
            delta_color="inverse" if metrics['critical_items'] > 0 else "normal"
        )
    
    with col4:
        coverage = metrics['overall_coverage']
        st.metric(
            "📊 Coverage Rate",
            f"{coverage:.1f}%",
            "Target: 95%" if coverage < 95 else "On target",
            delta_color="normal" if coverage >= 95 else "inverse"
        )
    
    # Row 2: Supply/Demand metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "📉 Total Shortage",
            f"{metrics['total_shortage']:,.0f}",
            "units"
        )
    
    with col2:
        st.metric(
            "📈 Total Surplus",
            f"{metrics['total_surplus']:,.0f}",
            "units"
        )
    
    with col3:
        st.metric(
            "💰 At Risk Value",
            f"${metrics['at_risk_value_usd']:,.0f}",
            help="Revenue at risk from shortages"
        )
    
    with col4:
        st.metric(
            "👥 Affected Customers",
            f"{metrics.get('affected_customers', 0):,}",
            help="Unique customers affected by shortages"
        )
    
    # Row 3: Safety metrics (if applicable)
    if include_safety and 'below_safety_count' in metrics:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "🔒 Below Safety",
                f"{metrics.get('below_safety_count', 0):,}",
                help="Items below safety stock level"
            )
        
        with col2:
            st.metric(
                "📦 At Reorder",
                f"{metrics.get('at_reorder_count', 0):,}",
                help="Items at or below reorder point"
            )
        
        with col3:
            st.metric(
                "💵 Safety Value",
                f"${metrics.get('safety_stock_value', 0):,.0f}",
                help="Total value of safety stock"
            )
        
        with col4:
            expired_count = metrics.get('has_expired_count', 0)
            expiry_risk = metrics.get('expiry_risk_count', 0)
            
            if expired_count > 0:
                st.metric(
                    "⌛ Expired",
                    f"{expired_count:,}",
                    f"+{expiry_risk} at risk",
                    delta_color="inverse"
                )
            else:
                st.metric(
                    "✅ Expiry Status",
                    "Clear",
                    f"{expiry_risk} watch" if expiry_risk > 0 else "All good"
                )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def _format_safety_gap(value: float, formatter: GAPFormatter) -> str:
    """Format safety gap with visual indicator"""
    if pd.isna(value):
        return "N/A"
    
    if value < 0:
        return f"🔴 {formatter.format_number(value, show_sign=True)}"
    elif value == 0:
        return f"🟡 0"
    else:
        return f"🟢 {formatter.format_number(value, show_sign=True)}"


def _get_status_display(status: str) -> str:
    """Get formatted status display with icon"""
    icon = STATUS_ICONS_V45.get(status, '❓')
    label = status.replace('_', ' ').title()
    return f"{icon} {label}"


# =============================================================================
# DETAILED DISPLAY - v4.5
# =============================================================================
def prepare_detailed_display(
    df: pd.DataFrame,
    formatter: GAPFormatter,
    include_safety: bool = False,
    include_expired: bool = False
) -> pd.DataFrame:
    """Prepare display dataframe with columns matching v4.5 logic"""
    
    if df.empty:
        return df
    
    display_df = pd.DataFrame()
    
    # Product identification
    if 'pt_code' in df.columns:
        display_df['PT Code'] = df['pt_code']
    if 'product_name' in df.columns:
        display_df['Product Name'] = df['product_name']
    if 'brand' in df.columns:
        display_df['Brand'] = df['brand']
    if 'standard_uom' in df.columns:
        display_df['UOM'] = df['standard_uom']
    
    # Supply columns
    if 'total_supply' in df.columns:
        display_df['Total Supply'] = df['total_supply'].apply(
            lambda x: formatter.format_number(x, field_name='total_supply')
        )
    
    # Supply breakdown
    if 'supply_inventory' in df.columns:
        display_df['Inventory'] = df['supply_inventory'].apply(
            lambda x: formatter.format_number(x, field_name='supply_inventory')
        )
    if 'supply_can_pending' in df.columns:
        display_df['CAN Pending'] = df['supply_can_pending'].apply(
            lambda x: formatter.format_number(x, field_name='supply_can_pending')
        )
    if 'supply_warehouse_transfer' in df.columns:
        display_df['Transfer'] = df['supply_warehouse_transfer'].apply(
            lambda x: formatter.format_number(x, field_name='supply_warehouse_transfer')
        )
    if 'supply_purchase_order' in df.columns:
        display_df['PO'] = df['supply_purchase_order'].apply(
            lambda x: formatter.format_number(x, field_name='supply_purchase_order')
        )
    
    # Demand columns
    if 'total_demand' in df.columns:
        display_df['Total Demand'] = df['total_demand'].apply(formatter.format_number)
    
    if 'demand_oc_pending' in df.columns:
        display_df['OC Pending'] = df['demand_oc_pending'].apply(formatter.format_number)
    if 'demand_forecast' in df.columns:
        display_df['Forecast'] = df['demand_forecast'].apply(formatter.format_number)
    
    # Safety Stock columns (when enabled)
    if include_safety:
        if 'safety_stock_qty' in df.columns:
            display_df['Safety Stock'] = df['safety_stock_qty'].apply(
                lambda x: formatter.format_number(x, field_name='safety_stock_qty')
            )
        
        if 'safety_gap' in df.columns:
            display_df['Safety Gap'] = df['safety_gap'].apply(
                lambda x: _format_safety_gap(x, formatter)
            )
        
        if 'available_supply' in df.columns:
            display_df['Available'] = df['available_supply'].apply(
                lambda x: formatter.format_number(x, field_name='available_supply')
            )
    
    # GAP Analysis
    if 'net_gap' in df.columns:
        display_df['Net GAP'] = df['net_gap'].apply(
            lambda x: formatter.format_number(x, show_sign=True)
        )
    
    if 'true_gap' in df.columns:
        display_df['True GAP'] = df['true_gap'].apply(
            lambda x: formatter.format_number(x, show_sign=True)
        )
    elif 'total_supply' in df.columns and 'total_demand' in df.columns:
        true_gap = df['total_supply'] - df['total_demand']
        display_df['True GAP'] = true_gap.apply(
            lambda x: formatter.format_number(x, show_sign=True)
        )
    
    # Shortage Cause
    if 'shortage_cause' in df.columns:
        display_df['Shortage Cause'] = df['shortage_cause']
    
    # Coverage metrics
    if 'coverage_ratio' in df.columns:
        display_df['Coverage %'] = df['coverage_ratio'].apply(formatter.format_coverage)
    
    if 'gap_percentage' in df.columns:
        display_df['GAP %'] = df['gap_percentage'].apply(
            lambda x: formatter.format_percentage(x, show_sign=True)
        )
    
    # Additional Safety columns
    if include_safety:
        if 'reorder_point' in df.columns:
            display_df['Reorder Point'] = df['reorder_point'].apply(
                lambda x: formatter.format_number(x, field_name='reorder_point')
            )
        
        if 'below_reorder' in df.columns:
            display_df['Below Reorder'] = df['below_reorder'].apply(
                lambda x: '⚠️ Yes' if x else '✅ No'
            )
        
        if 'safety_coverage' in df.columns:
            display_df['Safety Coverage'] = df['safety_coverage'].apply(
                lambda x: f"{x:.1f}x" if pd.notna(x) and x < 999 else "N/A"
            )
    
    # Financial columns
    if 'avg_unit_cost_usd' in df.columns:
        display_df['Unit Cost'] = df['avg_unit_cost_usd'].apply(
            lambda x: formatter.format_currency(x, decimals=2)
        )
    
    if 'avg_selling_price_usd' in df.columns:
        display_df['Sell Price'] = df['avg_selling_price_usd'].apply(
            lambda x: formatter.format_currency(x, decimals=2)
        )
    
    if 'at_risk_value_usd' in df.columns:
        display_df['At Risk Value'] = df['at_risk_value_usd'].apply(
            lambda x: formatter.format_currency(x, abbreviate=True)
        )
    
    if 'gap_value_usd' in df.columns:
        display_df['GAP Value'] = df['gap_value_usd'].apply(
            lambda x: formatter.format_currency(x, abbreviate=True)
        )
    
    # Status columns - v4.5 with new icons
    if 'gap_status' in df.columns:
        display_df['Status'] = df['gap_status'].apply(_get_status_display)
    
    if 'priority' in df.columns:
        priority_map = {1: 'P1-Critical', 2: 'P2-High', 3: 'P3-Medium', 4: 'P4-Low', 99: 'P99-OK'}
        display_df['Priority'] = df['priority'].map(priority_map).fillna('Unknown')
    
    if 'suggested_action' in df.columns:
        display_df['Action'] = df['suggested_action']
    
    # Customer impact
    if 'customer_count' in df.columns:
        display_df['Customers'] = df['customer_count'].apply(
            lambda x: f"{int(x):,}" if pd.notna(x) and x > 0 else "-"
        )
    
    # Expired inventory columns
    if include_expired:
        if 'expired_quantity' in df.columns:
            display_df['⚠️ Expired Qty'] = df['expired_quantity'].apply(
                lambda x: formatter.format_number(x) if x > 0 else '-'
            )
        
        if 'expired_batches_info' in df.columns:
            display_df['📋 Expired Batches'] = df['expired_batches_info'].apply(
                lambda x: x if x else '-'
            )
    
    return display_df


# =============================================================================
# DATA TABLE
# =============================================================================
def render_data_table(
    df: pd.DataFrame,
    items_per_page: int = 25,
    current_page: int = 1,
    formatter: Optional[GAPFormatter] = None,
    include_safety: bool = False,
    include_expired: bool = False
):
    """Enhanced data table with v4.5 status display"""
    
    if formatter is None:
        formatter = GAPFormatter()
    
    if df.empty:
        st.info("No data matches current filters")
        return None
    
    display_df = prepare_detailed_display(
        df, 
        formatter, 
        include_safety=include_safety,
        include_expired=include_expired
    )
    
    # Default visible columns
    default_visible = [
        'PT Code', 'Product Name', 'Brand',
        'Total Supply', 'Total Demand', 
        'Net GAP', 'Coverage %',
        'Status', 'Priority'
    ]
    
    # Add safety-related columns if enabled
    if include_safety:
        idx = default_visible.index('Total Demand') + 1
        safety_cols = ['Safety Stock', 'Safety Gap', 'Available', 'True GAP', 'Shortage Cause']
        for i, col in enumerate(safety_cols):
            if col in display_df.columns:
                default_visible.insert(idx + i, col)
    
    # Configure columns
    column_config = {}
    
    if 'Net GAP' in display_df.columns:
        column_config['Net GAP'] = st.column_config.TextColumn(
            'Net GAP',
            help='Available Supply - Demand. Negative = Shortage (always!)',
            width='small'
        )
    
    if 'True GAP' in display_df.columns:
        column_config['True GAP'] = st.column_config.TextColumn(
            'True GAP',
            help='Total Supply - Demand (ignores safety stock)',
            width='small'
        )
    
    if 'Safety Gap' in display_df.columns:
        column_config['Safety Gap'] = st.column_config.TextColumn(
            'Safety Gap',
            help='Supply - Safety Stock. Negative = supply below safety!',
            width='small'
        )
    
    if 'Shortage Cause' in display_df.columns:
        column_config['Shortage Cause'] = st.column_config.TextColumn(
            'Shortage Cause',
            help='Why shortage exists: Real or Safety-induced',
            width='medium'
        )
    
    if 'Status' in display_df.columns:
        column_config['Status'] = st.column_config.TextColumn(
            'Status',
            help='v4.5: Based on Net GAP sign (negative=Shortage, positive=Surplus)',
            width='medium'
        )
    
    help_texts = {
        'Coverage %': 'Available Supply as percentage of Demand',
        'Available': 'Supply after safety reservation = max(0, Supply - Safety)',
        'Safety Stock': 'Minimum buffer required',
        'At Risk Value': 'Revenue at risk due to shortage'
    }
    
    for col, help_text in help_texts.items():
        if col in display_df.columns:
            column_config[col] = st.column_config.Column(col, help=help_text)
    
    # Pagination
    total_items = len(display_df)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    page = min(current_page, total_pages)
    
    start_idx = (page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    
    # Display info
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        st.caption(f"Showing {start_idx+1}-{end_idx} of {total_items} items")
    with col2:
        st.caption("🔵 Net GAP | 🟣 True GAP | 🟠 Safety Gap")
    with col3:
        st.caption("v4.5: Net GAP < 0 = Always Shortage")
    
    # Display table
    st.dataframe(
        display_df.iloc[start_idx:end_idx],
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        height=min(600, (end_idx - start_idx) * 35 + 50),
        key=f"gap_table_{page}"
    )
    
    return {
        'page': page,
        'total_pages': total_pages,
        'total_items': total_items,
        'columns': len(display_df.columns)
    }


# =============================================================================
# PAGINATION
# =============================================================================
def render_pagination(current_page: int, total_pages: int, key_prefix: str = "page"):
    """Render pagination controls"""
    
    if total_pages <= 1:
        return current_page
    
    col1, col2, col3, col4, col5 = st.columns([1, 1, 3, 1, 1])
    
    new_page = current_page
    
    with col1:
        if st.button("⏮", disabled=(current_page == 1), key=f"{key_prefix}_first"):
            new_page = 1
    
    with col2:
        if st.button("◀", disabled=(current_page == 1), key=f"{key_prefix}_prev"):
            new_page = current_page - 1
    
    with col3:
        st.markdown(
            f"<div style='text-align: center; padding: 8px;'>"
            f"Page <b>{current_page}</b> of <b>{total_pages}</b>"
            f"</div>",
            unsafe_allow_html=True
        )
    
    with col4:
        if st.button("▶", disabled=(current_page == total_pages), key=f"{key_prefix}_next"):
            new_page = current_page + 1
    
    with col5:
        if st.button("⏭", disabled=(current_page == total_pages), key=f"{key_prefix}_last"):
            new_page = total_pages
    
    return new_page


# =============================================================================
# STATUS SUMMARY
# =============================================================================
def render_status_summary(gap_df: pd.DataFrame):
    """Render detailed status summary"""
    
    if gap_df.empty:
        return
    
    counts = {}
    for category, config in GAP_CATEGORIES.items():
        mask = gap_df['gap_status'].isin(config['statuses'])
        count = len(gap_df[mask])
        if count > 0:
            counts[category] = {
                'count': count,
                'pct': (count / len(gap_df)) * 100,
                'icon': config['icon'],
                'label': config['label']
            }
    
    cols = st.columns(len(counts))
    for idx, (category, data) in enumerate(counts.items()):
        with cols[idx]:
            st.metric(
                f"{data['icon']} {data['label']}",
                f"{data['count']:,}",
                f"{data['pct']:.1f}%"
            )


# =============================================================================
# QUICK FILTER
# =============================================================================
def render_quick_filter():
    """Render quick filter for results - v4.5"""
    filter_options = {
        'all': '📊 All Items',
        'shortage': '🔴 Shortage Only',
        'optimal': '✅ Balanced Only',
        'surplus': '📦 Surplus Only',
        'inactive': '⚪ No Demand',
        'critical': '🚨 Critical Only'
    }
    
    selected = st.radio(
        "Quick Filter",
        options=list(filter_options.keys()),
        format_func=lambda x: filter_options[x],
        horizontal=True,
        label_visibility="collapsed",
        key="quick_filter",
        help="Filter by status category (v4.5 logic)"
    )
    
    return selected


def apply_quick_filter(df: pd.DataFrame, filter_type: str) -> pd.DataFrame:
    """Apply quick filter to dataframe"""
    
    if filter_type == 'all' or df.empty:
        return df
    
    if filter_type == 'critical':
        return df[df['priority'] == 1]
    
    category_map = {
        'shortage': 'SHORTAGE',
        'optimal': 'OPTIMAL',
        'surplus': 'SURPLUS',
        'inactive': 'INACTIVE'
    }
    
    category = category_map.get(filter_type)
    if category and category in GAP_CATEGORIES:
        statuses = GAP_CATEGORIES[category]['statuses']
        return df[df['gap_status'].isin(statuses)]
    
    return df


# =============================================================================
# EXPIRED INVENTORY
# =============================================================================
def render_expired_inventory_summary(gap_df: pd.DataFrame):
    """Render expired inventory summary alert"""
    
    if gap_df.empty or 'expired_quantity' not in gap_df.columns:
        return
    
    total_expired = gap_df['expired_quantity'].sum()
    
    if total_expired > 0:
        expired_items = len(gap_df[gap_df['expired_quantity'] > 0])
        
        st.warning(
            f"⚠️ **Expired Inventory Alert**: {expired_items} products "
            f"with total {total_expired:,.0f} units expired"
        )
        
        top_expired = gap_df[gap_df['expired_quantity'] > 0].nlargest(5, 'expired_quantity')
        
        if not top_expired.empty:
            with st.expander("📋 Top 5 Expired Products", expanded=False):
                for _, row in top_expired.iterrows():
                    st.markdown(
                        f"**{row.get('pt_code', 'N/A')}** - {row.get('product_name', 'N/A')}: "
                        f"{row['expired_quantity']:,.0f} units"
                    )