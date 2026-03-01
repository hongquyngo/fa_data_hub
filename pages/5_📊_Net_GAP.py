# pages/1_📊_Net_GAP.py

"""
Net GAP Analysis Page - Enhanced with Expired Inventory Tracking v4.2
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import logging
from typing import Dict, Any
import os
from pathlib import Path

# Configure page
st.set_page_config(
    page_title="Net GAP Analysis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import utilities
project_root = os.environ.get('PROJECT_ROOT', Path(__file__).parent.parent)
if str(project_root) not in os.sys.path:
    os.sys.path.insert(0, str(project_root))

from utils.auth import AuthManager
from utils.net_gap.state import get_state
from utils.net_gap.data_loader import GAPDataLoader
from utils.net_gap.calculator import GAPCalculator
from utils.net_gap.filters import GAPFilters
from utils.net_gap.charts import GAPCharts
from utils.net_gap.formatters import GAPFormatter
from utils.net_gap.components import (
    render_kpi_cards, 
    render_data_table, 
    render_status_summary,
    render_quick_filter,
    apply_quick_filter,
    render_pagination,
    render_formula_guide,
    render_expired_inventory_summary
)
from utils.net_gap.export import export_to_excel
from utils.net_gap.customer_dialog import show_customer_dialog
from utils.net_gap.constants import UI_CONFIG

VERSION = "4.2"


def initialize_system():
    """Initialize all components"""
    state = get_state()
    data_loader = GAPDataLoader()
    calculator = GAPCalculator()
    formatter = GAPFormatter()
    filters = GAPFilters(data_loader)
    charts = GAPCharts(formatter)
    
    return state, data_loader, calculator, formatter, filters, charts


def calculate_gap(
    data_loader: GAPDataLoader,
    calculator: GAPCalculator,
    filter_values: Dict[str, Any]
):
    """Load data and calculate GAP with expired inventory tracking"""
    
    with st.spinner("📊 Calculating GAP analysis..."):
        # Load supply data
        supply_df = data_loader.load_supply_data(
            entity_name=filter_values.get('entity'),
            exclude_entity=filter_values.get('exclude_entity', False),
            product_ids=filter_values.get('products_tuple'),
            brands=filter_values.get('brands_tuple'),
            exclude_products=filter_values.get('exclude_products', False),
            exclude_brands=filter_values.get('exclude_brands', False),
            exclude_expired=filter_values.get('exclude_expired', True)
        )
        
        # Load expired inventory details if including expired
        expired_inventory_df = None
        if not filter_values.get('exclude_expired', True):
            expired_inventory_df = data_loader.load_expired_inventory_details(
                entity_name=filter_values.get('entity'),
                exclude_entity=filter_values.get('exclude_entity', False),
                product_ids=filter_values.get('products_tuple'),
                brands=filter_values.get('brands_tuple'),
                exclude_products=filter_values.get('exclude_products', False),
                exclude_brands=filter_values.get('exclude_brands', False)
            )
            logger.info(f"Loaded expired inventory for {len(expired_inventory_df)} products")
        
        # Load demand data
        demand_df = data_loader.load_demand_data(
            entity_name=filter_values.get('entity'),
            exclude_entity=filter_values.get('exclude_entity', False),
            product_ids=filter_values.get('products_tuple'),
            brands=filter_values.get('brands_tuple'),
            exclude_products=filter_values.get('exclude_products', False),
            exclude_brands=filter_values.get('exclude_brands', False)
        )
        
        # Load safety stock if needed
        safety_stock_df = None
        if filter_values.get('include_safety', False):
            safety_stock_df = data_loader.load_safety_stock_data(
                entity_name=filter_values.get('entity'),
                exclude_entity=filter_values.get('exclude_entity', False),
                product_ids=filter_values.get('products_tuple')
            )
        
        # Validate data
        if supply_df.empty and demand_df.empty:
            st.warning("No data available for selected filters")
            return None
        
        # Calculate GAP with expired inventory
        result = calculator.calculate_net_gap(
            supply_df=supply_df,
            demand_df=demand_df,
            safety_stock_df=safety_stock_df,
            expired_inventory_df=expired_inventory_df,
            group_by=filter_values.get('group_by', 'product'),
            selected_supply_sources=filter_values.get('supply_sources'),
            selected_demand_sources=filter_values.get('demand_sources'),
            include_safety_stock=filter_values.get('include_safety', False)
        )
        
        logger.info(f"GAP calculated: {result.get_summary()}")
        return result


def main():
    """Main application"""
    
    # Authentication check
    auth_manager = AuthManager()
    if not auth_manager.check_session():
        st.warning("⚠️ Please login to access this page")
        st.stop()
    
    # Initialize
    state, data_loader, calculator, formatter, filters, charts = initialize_system()
    
    # Page header
    st.title("📊 Net GAP Analysis")
    st.markdown("Supply-Demand Analysis with Safety Stock & Expired Inventory Tracking")
    
    # Sidebar
    with st.sidebar:
        st.markdown(f"👤 **User:** {auth_manager.get_user_display_name()}")
        if st.button("🚪 Logout", use_container_width=True):
            auth_manager.logout()
            st.rerun()
        
        st.divider()
        st.caption(f"Version {VERSION}")
    
    # Check if customer dialog should be shown
    if st.session_state.get('show_customer_dialog'):
        result = state.get_result()
        if result and result.customer_impact:
            show_customer_dialog()
    
    # Filters section
    with st.expander("🔧 **Configuration**", expanded=True):
        filter_values = filters.render_filters()
    
    # Action buttons
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("🔄 Reset", use_container_width=True):
            state.reset_filters()
            st.rerun()
    
    with col2:
        calculate_clicked = st.button(
            "📊 Calculate GAP",
            type="primary",
            use_container_width=True
        )
    
    with col3:
        if state.has_result():
            st.success("✅ Results ready")
        else:
            st.info("👆 Click Calculate to start")
    
    # Calculate if needed
    if calculate_clicked:
        try:
            result = calculate_gap(data_loader, calculator, filter_values)
            if result:
                state.set_filters(filter_values)
                state.set_result(result)
                st.rerun()
        except Exception as e:
            logger.error(f"Calculation failed: {e}", exc_info=True)
            st.error(f"❌ Calculation failed: {str(e)}")
            st.stop()
    
    # Display results
    result = state.get_result()
    
    if not result:
        st.info("Configure filters and click 'Calculate GAP' to begin")
        st.stop()
    
    # Check if expired inventory is included
    include_expired = not filter_values.get('exclude_expired', True)
    
    # KPI Cards
    st.subheader("📈 Key Metrics")
    render_kpi_cards(
        result.metrics,
        include_safety=filter_values.get('include_safety', False)
    )
    
    # Expired inventory summary
    if include_expired:
        render_expired_inventory_summary(result.gap_df)
    
    # Customer impact button (if available)
    if result.customer_impact and result.customer_impact.affected_count > 0:
        if st.button(
            f"👥 View {result.customer_impact.affected_count} Affected Customers",
            type="secondary"
        ):
            st.session_state['show_customer_dialog'] = True
            st.rerun()
    
    st.divider()
    
    # Visual Analysis - More compact layout
    st.subheader("📊 Visual Analysis")
    
    # Use tabs for better organization and space saving
    tab1, tab2, tab3 = st.tabs(["Overview", "Top Items", "Formula Guide"])
    
    with tab1:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            # Status distribution
            fig_status = charts.create_status_donut(result.gap_df)
            st.plotly_chart(fig_status, use_container_width=True)
        
        with col2:
            # Value at risk
            fig_value = charts.create_value_analysis(result.gap_df)
            st.plotly_chart(fig_value, use_container_width=True)
    
    with tab2:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("#### 📉 Top Shortages")
            fig_shortage = charts.create_top_items_bar(result.gap_df, 'shortage', top_n=10)
            st.plotly_chart(fig_shortage, use_container_width=True)
        
        with col2:
            st.markdown("#### 📈 Top Surplus")
            fig_surplus = charts.create_top_items_bar(result.gap_df, 'surplus', top_n=10)
            st.plotly_chart(fig_surplus, use_container_width=True)
    
    with tab3:
        # Formula guide section
        render_formula_guide()
    
    st.divider()
    
    # Detailed Table
    st.subheader("📋 Detailed Analysis")
    
    # Status summary
    render_status_summary(result.gap_df)
    
    # Quick filter
    quick_filter = render_quick_filter()
    filtered_df = apply_quick_filter(result.gap_df, quick_filter)
    
    if quick_filter != 'all':
        st.info(f"Showing {len(filtered_df)} of {len(result.gap_df)} items ({quick_filter})")
    
    # Table controls
    col1, col2, col3 = st.columns([2, 2, 3])
    
    with col1:
        items_per_page = st.selectbox(
            "Items per page",
            UI_CONFIG['items_per_page_options'],
            index=1,
            key="items_per_page"
        )
    
    with col2:
        # Search
        search = st.text_input("Search", placeholder="Filter in all columns...", key="search")
        if search:
            mask = filtered_df.astype(str).apply(
                lambda x: x.str.contains(search, case=False, na=False)
            ).any(axis=1)
            filtered_df = filtered_df[mask]
    
    with col3:
        # Export button
        if st.button("📥 Export Excel", type="primary", use_container_width=True):
            try:
                excel_data = export_to_excel(
                    result, 
                    filter_values,
                    include_cost_breakdown=True
                )
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                st.download_button(
                    label="📥 Download",
                    data=excel_data,
                    file_name=f"gap_analysis_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                logger.error(f"Export failed: {e}")
                st.error("Export failed")
    
    # Display enhanced table with expired inventory columns
    page_info = render_data_table(
        filtered_df,
        items_per_page=items_per_page,
        current_page=state.get_page(),
        formatter=formatter,
        include_safety=filter_values.get('include_safety', False),
        include_expired=include_expired
    )
    
    # Handle pagination
    if page_info:
        new_page = render_pagination(
            page_info['page'],
            page_info['total_pages'],
            key_prefix="main"
        )
        
        if new_page != page_info['page']:
            state.set_page(new_page, page_info['total_pages'])
            st.rerun()
    
    # Footer
    st.divider()
    st.caption(
        f"Last calculated: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
        f"Net GAP Analysis v{VERSION}"
    )


if __name__ == "__main__":
    main()