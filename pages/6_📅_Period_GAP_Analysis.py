# pages/2_📅_Period_GAP_Analysis.py
"""
Period-based Supply-Demand GAP Analysis - Version 4.0
Redesigned UI with tabs matching Excel export structure:
- Tab 1: GAP Detail (matches GAP_Analysis sheet)
- Tab 2: Product Summary (matches Product_Summary sheet)
- Tab 3: Period Summary (matches Period_Summary sheet) with charts
- Tab 4: Pivot View (matches Pivot_View sheet)
- Action Items Expander (matches Action_Items sheet)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import Dict, Any, Optional, List, Tuple
import sys
from pathlib import Path

# Configure page
st.set_page_config(
    page_title="Period GAP Analysis - SCM",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Import authentication
from utils.auth import AuthManager

# Constants
VERSION = "4.0"  # Redesigned UI with tabs
MAX_EXPORT_ROWS = 50000
DEFAULT_PERIOD_TYPE = "Weekly"
DEFAULT_TRACK_BACKLOG = True
DEFAULT_OC_DATE_FIELD = "ETA"


def initialize_components():
    """Initialize all Period GAP analysis components"""
    from utils.period_gap.data_loader import PeriodGAPDataLoader
    from utils.period_gap.display_components import DisplayComponents
    from utils.period_gap.session_state import initialize_session_state
    
    initialize_session_state()
    data_loader = PeriodGAPDataLoader()
    display_components = DisplayComponents()
    
    return data_loader, display_components


def handle_error(e: Exception) -> None:
    """Handle errors with appropriate user messages"""
    error_type = type(e).__name__
    error_msg = str(e).lower()
    
    logger.error(f"Error in Period GAP analysis: {e}", exc_info=True)
    
    if "connection" in error_msg or "connect" in error_msg:
        st.error("🔌 Database connection issue. Please refresh the page.")
    elif "permission" in error_msg or "denied" in error_msg:
        st.error("🔒 Access denied. Please check your permissions.")
    elif "timeout" in error_msg:
        st.error("⏱️ Request timed out. Try using more specific filters.")
    else:
        st.error(f"❌ An error occurred: {error_type}")
    
    with st.expander("Error Details", expanded=False):
        st.code(str(e))


@st.cache_data(ttl=300)
def initialize_filter_data(_data_loader) -> Dict[str, Any]:
    """Pre-load data to populate filter dropdowns"""
    try:
        demand_df = _data_loader.get_demand_data(
            sources=["OC", "Forecast"],
            include_converted=False,
            oc_date_field="ETA"
        )
        supply_df = _data_loader.get_supply_data(
            sources=["Inventory", "Pending CAN", "Pending PO", "Pending WH Transfer"],
            exclude_expired=False
        )
        
        entities = set()
        products = {}
        brands = set()
        
        min_date = datetime.today().date()
        max_date = datetime.today().date()
        
        # Process demand data
        if not demand_df.empty:
            entities.update(demand_df['legal_entity'].dropna().unique())
            brands.update(demand_df['brand'].dropna().unique())
            
            if 'pt_code' in demand_df.columns:
                for _, row in demand_df.drop_duplicates(subset=['pt_code']).iterrows():
                    pt_code = str(row['pt_code'])
                    if pd.notna(row['pt_code']) and pt_code != 'nan':
                        product_name = str(row.get('product_name', ''))[:30] if pd.notna(row.get('product_name')) else ''
                        package_size = str(row.get('package_size', '')) if pd.notna(row.get('package_size')) else ''
                        brand = str(row.get('brand', '')) if pd.notna(row.get('brand')) else ''
                        
                        if package_size == 'nan': package_size = ''
                        if brand == 'nan': brand = ''
                        
                        products[pt_code] = (product_name, package_size, brand)
            
            for date_col in ['etd', 'eta']:
                if date_col in demand_df.columns:
                    dates = pd.to_datetime(demand_df[date_col], errors='coerce').dropna()
                    if len(dates) > 0:
                        min_date = min(min_date, dates.min().date())
                        max_date = max(max_date, dates.max().date())
        
        # Process supply data
        if not supply_df.empty:
            entities.update(supply_df['legal_entity'].dropna().unique())
            brands.update(supply_df['brand'].dropna().unique())
            
            if 'pt_code' in supply_df.columns:
                for _, row in supply_df.drop_duplicates(subset=['pt_code']).iterrows():
                    pt_code = str(row['pt_code'])
                    if pd.notna(row['pt_code']) and pt_code != 'nan' and pt_code not in products:
                        product_name = str(row.get('product_name', ''))[:30] if pd.notna(row.get('product_name')) else ''
                        package_size = str(row.get('package_size', '')) if pd.notna(row.get('package_size')) else ''
                        brand = str(row.get('brand', '')) if pd.notna(row.get('brand')) else ''
                        
                        if package_size == 'nan': package_size = ''
                        if brand == 'nan': brand = ''
                        
                        products[pt_code] = (product_name, package_size, brand)
            
            if 'date_ref' in supply_df.columns:
                supply_dates = pd.to_datetime(supply_df['date_ref'], errors='coerce').dropna()
                if len(supply_dates) > 0:
                    min_date = min(min_date, supply_dates.min().date())
                    max_date = max(max_date, supply_dates.max().date())
        
        # Create formatted product options
        product_options = []
        for pt_code, (name, package, brand) in sorted(products.items()):
            parts = [pt_code]
            if name: parts.append(name)
            if package: parts.append(package)
            if brand: parts.append(brand)
            product_options.append(" | ".join(parts))
        
        return {
            'entities': sorted(list(entities)),
            'products': sorted(list(products.keys())),
            'product_options': product_options,
            'brands': sorted(list(brands)),
            'min_date': min_date,
            'max_date': max_date,
            'demand_df': demand_df,
            'supply_df': supply_df
        }
        
    except Exception as e:
        logger.error(f"Error initializing filter data: {e}")
        today = datetime.today().date()
        return {
            'entities': [], 'products': [], 'product_options': [], 'brands': [],
            'min_date': today, 'max_date': today,
            'demand_df': pd.DataFrame(), 'supply_df': pd.DataFrame()
        }


def render_source_selection() -> Dict[str, Any]:
    """Render demand and supply source selection"""
    st.markdown("### 📊 Data Sources")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### 📤 Demand")
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            demand_oc = st.checkbox("OC", value=True, key="pgap_demand_oc")
        with d_col2:
            demand_forecast = st.checkbox("Forecast", value=False, key="pgap_demand_forecast")
        
        selected_demand = []
        if demand_oc: selected_demand.append("OC")
        if demand_forecast: selected_demand.append("Forecast")
        
        oc_date_field = DEFAULT_OC_DATE_FIELD
        if demand_oc:
            oc_date_field = st.radio(
                "OC Timing:",
                options=["ETA", "ETD"],
                horizontal=True,
                key="pgap_oc_date_field"
            )
        
        include_converted = False
        if demand_forecast:
            include_converted = st.checkbox(
                "Include Converted Forecasts",
                value=False,
                key="pgap_include_converted"
            )
    
    with col2:
        st.markdown("##### 📥 Supply")
        s_col1, s_col2 = st.columns(2)
        with s_col1:
            supply_inv = st.checkbox("Inventory", value=True, key="pgap_supply_inv")
            supply_can = st.checkbox("Pending CAN", value=True, key="pgap_supply_can")
        with s_col2:
            supply_po = st.checkbox("Pending PO", value=True, key="pgap_supply_po")
            supply_wht = st.checkbox("Pending WH Transfer", value=True, key="pgap_supply_wht")
        
        exclude_expired = st.checkbox("Exclude Expired", value=True, key="pgap_exclude_expired")
        
        selected_supply = []
        if supply_inv: selected_supply.append("Inventory")
        if supply_can: selected_supply.append("Pending CAN")
        if supply_po: selected_supply.append("Pending PO")
        if supply_wht: selected_supply.append("Pending WH Transfer")
    
    return {
        "demand": selected_demand,
        "supply": selected_supply,
        "include_converted": include_converted,
        "exclude_expired": exclude_expired,
        "oc_date_field": oc_date_field
    }


def render_filters(filter_data: Dict[str, Any]) -> Dict[str, Any]:
    """Render filters section"""
    with st.expander("🔍 Filters", expanded=True):
        filters = {}
        
        # Main filters row - adjusted column widths
        # Entity: [multiselect] [excl] | Product: [multiselect] [excl] [quick_add] | Brand: [multiselect] [excl]
        col1, col1_ex, col2, col2_ex, col2_qa, col3, col3_ex = st.columns([2.5, 0.3, 3.2, 0.3, 0.5, 2, 0.3])
        
        # Entity filter
        with col1:
            filters['entity'] = st.multiselect(
                "Legal Entity",
                filter_data.get('entities', []),
                key="pgap_entity_filter",
                placeholder="All entities"
            )
        with col1_ex:
            filters['exclude_entity'] = st.checkbox("🚫", key="pgap_exclude_entity")
        
        # Product filter with Quick Add
        product_options = filter_data.get('product_options', [])
        session_key = 'pgap_product_selection'
        
        # Handle Quick Add confirmation
        if 'pgap_quick_add_confirmed' in st.session_state:
            new_products = st.session_state.pgap_quick_add_confirmed
            if new_products and isinstance(new_products, list):
                current = st.session_state.get(session_key, [])
                merged = list(set(current + new_products))
                st.session_state[session_key] = [p for p in merged if p in product_options]
            del st.session_state.pgap_quick_add_confirmed
            if 'pgap_product_widget_counter' not in st.session_state:
                st.session_state['pgap_product_widget_counter'] = 0
            st.session_state['pgap_product_widget_counter'] += 1
        
        default_selection = st.session_state.get(session_key, [])
        default_selection = [p for p in default_selection if p in product_options]
        
        if st.session_state.get('pgap_quick_add_cancelled'):
            del st.session_state.pgap_quick_add_cancelled
        
        with col2:
            widget_counter = st.session_state.get('pgap_product_widget_counter', 0)
            widget_key = f"pgap_product_filter_{widget_counter}"
            
            selected_products = st.multiselect(
                "Product",
                product_options,
                default=default_selection,
                key=widget_key,
                placeholder="All products"
            )
            st.session_state[session_key] = selected_products
        
        with col2_ex:
            filters['exclude_product'] = st.checkbox("🚫", key="pgap_exclude_product")
        
        with col2_qa:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📋", key="pgap_quick_add_btn", help="Quick Add PT codes"):
                st.session_state.pgap_show_quick_add = True
        
        # Show Quick Add dialog if triggered
        if st.session_state.get('pgap_show_quick_add'):
            from utils.period_gap.quick_add_components import show_quick_add_dialog_for_products
            show_quick_add_dialog_for_products(product_options, selected_products, False)
        
        filters['product'] = []
        for sel in selected_products:
            pt_code = sel.split(' | ')[0].strip() if '|' in sel else sel.strip()
            filters['product'].append(pt_code)
        
        # Brand filter
        with col3:
            filters['brand'] = st.multiselect(
                "Brand",
                filter_data.get('brands', []),
                key="pgap_brand_filter",
                placeholder="All brands"
            )
        with col3_ex:
            filters['exclude_brand'] = st.checkbox("🚫", key="pgap_exclude_brand")
        
        # Date range
        date_col1, date_col2 = st.columns(2)
        min_date = filter_data.get('min_date', datetime.today().date())
        max_date = filter_data.get('max_date', datetime.today().date())
        
        with date_col1:
            filters['start_date'] = st.date_input(
                "From Date",
                value=min_date,
                min_value=min_date - timedelta(days=365),
                max_value=max_date + timedelta(days=365),
                key="pgap_start_date"
            )
        with date_col2:
            filters['end_date'] = st.date_input(
                "To Date",
                value=max_date,
                min_value=min_date - timedelta(days=365),
                max_value=max_date + timedelta(days=365),
                key="pgap_end_date"
            )
    
    return filters


def render_calculation_options() -> Dict[str, Any]:
    """Render calculation options"""
    st.markdown("### ⚙️ Calculation")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        period_type = st.selectbox(
            "Group By",
            ["Daily", "Weekly", "Monthly"],
            index=1,
            key="pgap_period_select"
        )
    
    with col2:
        exclude_missing = st.checkbox(
            "📅 Exclude missing dates",
            value=True,
            key="pgap_exclude_missing"
        )
    
    with col3:
        track_backlog = st.checkbox(
            "📊 Track Backlog",
            value=DEFAULT_TRACK_BACKLOG,
            key="pgap_track_backlog"
        )
    
    return {
        "period_type": period_type,
        "exclude_missing_dates": exclude_missing,
        "track_backlog": track_backlog
    }


def apply_filters_to_data(
    df_demand: pd.DataFrame,
    df_supply: pd.DataFrame,
    filters: Dict[str, Any],
    oc_date_field: str = "ETA"
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Apply filters to demand and supply dataframes"""
    
    filtered_demand = df_demand.copy()
    filtered_supply = df_supply.copy()
    
    # Clean pt_code
    for df in [filtered_demand, filtered_supply]:
        if 'pt_code' in df.columns:
            df['pt_code'] = df['pt_code'].astype(str).str.strip()
    
    # Apply filters to demand
    if filters.get('entity'):
        if filters.get('exclude_entity', False):
            filtered_demand = filtered_demand[~filtered_demand['legal_entity'].isin(filters['entity'])]
        else:
            filtered_demand = filtered_demand[filtered_demand['legal_entity'].isin(filters['entity'])]
    
    if filters.get('product'):
        clean_products = [str(p).strip() for p in filters['product']]
        if filters.get('exclude_product', False):
            filtered_demand = filtered_demand[~filtered_demand['pt_code'].isin(clean_products)]
        else:
            filtered_demand = filtered_demand[filtered_demand['pt_code'].isin(clean_products)]
    
    if filters.get('brand'):
        clean_brands = [str(b).strip().lower() for b in filters['brand']]
        filtered_demand['_brand_clean'] = filtered_demand['brand'].astype(str).str.strip().str.lower()
        if filters.get('exclude_brand', False):
            filtered_demand = filtered_demand[~filtered_demand['_brand_clean'].isin(clean_brands)]
        else:
            filtered_demand = filtered_demand[filtered_demand['_brand_clean'].isin(clean_brands)]
        filtered_demand = filtered_demand.drop(columns=['_brand_clean'])
    
    # Apply date filter to demand
    if 'demand_date' in filtered_demand.columns and filters.get('start_date') and filters.get('end_date'):
        start_date = pd.to_datetime(filters['start_date'])
        end_date = pd.to_datetime(filters['end_date'])
        filtered_demand['demand_date'] = pd.to_datetime(filtered_demand['demand_date'], errors='coerce')
        date_mask = (
            filtered_demand['demand_date'].isna() |
            ((filtered_demand['demand_date'] >= start_date) & (filtered_demand['demand_date'] <= end_date))
        )
        filtered_demand = filtered_demand[date_mask]
    
    # Apply same filters to supply
    if filters.get('entity'):
        if filters.get('exclude_entity', False):
            filtered_supply = filtered_supply[~filtered_supply['legal_entity'].isin(filters['entity'])]
        else:
            filtered_supply = filtered_supply[filtered_supply['legal_entity'].isin(filters['entity'])]
    
    if filters.get('product'):
        clean_products = [str(p).strip() for p in filters['product']]
        if filters.get('exclude_product', False):
            filtered_supply = filtered_supply[~filtered_supply['pt_code'].isin(clean_products)]
        else:
            filtered_supply = filtered_supply[filtered_supply['pt_code'].isin(clean_products)]
    
    if filters.get('brand'):
        clean_brands = [str(b).strip().lower() for b in filters['brand']]
        filtered_supply['_brand_clean'] = filtered_supply['brand'].astype(str).str.strip().str.lower()
        if filters.get('exclude_brand', False):
            filtered_supply = filtered_supply[~filtered_supply['_brand_clean'].isin(clean_brands)]
        else:
            filtered_supply = filtered_supply[filtered_supply['_brand_clean'].isin(clean_brands)]
        filtered_supply = filtered_supply.drop(columns=['_brand_clean'])
    
    # Apply date filter to supply
    if 'date_ref' in filtered_supply.columns and filters.get('start_date') and filters.get('end_date'):
        start_date = pd.to_datetime(filters['start_date'])
        end_date = pd.to_datetime(filters['end_date'])
        filtered_supply['date_ref'] = pd.to_datetime(filtered_supply['date_ref'], errors='coerce')
        date_mask = (
            filtered_supply['date_ref'].isna() |
            ((filtered_supply['date_ref'] >= start_date) & (filtered_supply['date_ref'] <= end_date))
        )
        filtered_supply = filtered_supply[date_mask]
    
    return filtered_demand, filtered_supply


def export_to_excel(
    gap_df: pd.DataFrame,
    filter_values: Dict[str, Any],
    display_filters: Dict[str, Any],
    calc_options: Dict[str, Any],
    df_demand_filtered: pd.DataFrame,
    df_supply_filtered: pd.DataFrame
) -> bytes:
    """Export GAP analysis to Excel with all sheets"""
    from utils.period_gap.helpers import export_gap_with_metadata
    
    return export_gap_with_metadata(
        gap_df=gap_df,
        filter_values=filter_values,
        display_filters=display_filters,
        calc_options=calc_options,
        df_demand_filtered=df_demand_filtered,
        df_supply_filtered=df_supply_filtered
    )


def main():
    """Main application logic"""
    # Auth check
    auth_manager = AuthManager()
    if not auth_manager.check_session():
        st.warning("⚠️ Please login to access this page")
        st.stop()
    
    # Initialize
    data_loader, display_components = initialize_components()
    
    from utils.period_gap.gap_calculator import calculate_gap_with_carry_forward
    from utils.period_gap.tab_components import (
        render_overview_section,
        render_gap_detail_tab,
        render_product_summary_tab,
        render_period_summary_tab,
        render_pivot_view_tab,
        render_action_items_expander
    )
    from utils.period_gap.session_state import (
        save_period_gap_state,
        get_period_gap_state,
        update_filter_cache
    )
    from utils.period_gap.helpers import save_to_session_state
    
    # Header
    st.title("📅 Period-Based GAP Analysis")
    st.caption(f"v{VERSION} | User: {auth_manager.get_user_display_name()}")
    
    # Sidebar - User info
    with st.sidebar:
        st.markdown(f"👤 **{auth_manager.get_user_display_name()}**")
        if st.button("🚪 Logout", use_container_width=True):
            auth_manager.logout()
            st.rerun()
    
    st.markdown("---")
    
    try:
        # Load filter data
        with st.spinner("Initializing..."):
            filter_data = initialize_filter_data(data_loader)
            update_filter_cache(
                entities=filter_data['entities'],
                products=filter_data['products'],
                brands=filter_data['brands']
            )
        
        # Source Selection
        selected_sources = render_source_selection()
        
        if not selected_sources['demand'] or not selected_sources['supply']:
            st.warning("⚠️ Please select at least one demand and one supply source.")
            st.stop()
        
        # Filters
        filters = render_filters(filter_data)
        
        # Calculation Options
        calc_options = render_calculation_options()
        
        # Run Analysis button
        st.markdown("---")
        run_analysis = st.button("🚀 Run Analysis", type="primary", use_container_width=True)
        
        if run_analysis:
            # Clear Quick Add dialog state to prevent it from popping up
            if 'pgap_show_quick_add' in st.session_state:
                del st.session_state['pgap_show_quick_add']
            
            with st.spinner("Loading data and calculating GAP..."):
                # Load fresh data with selected sources
                df_demand = data_loader.get_demand_data(
                    sources=selected_sources['demand'],
                    include_converted=selected_sources.get('include_converted', False),
                    oc_date_field=selected_sources.get('oc_date_field', 'ETA')
                )
                
                df_supply = data_loader.get_supply_data(
                    sources=selected_sources['supply'],
                    exclude_expired=selected_sources.get('exclude_expired', True)
                )
                
                # Apply filters
                df_demand_filtered, df_supply_filtered = apply_filters_to_data(
                    df_demand,
                    df_supply,
                    filters,
                    selected_sources.get('oc_date_field', 'ETA')
                )
                
                # Calculate GAP
                gap_df = calculate_gap_with_carry_forward(
                    df_demand_filtered,
                    df_supply_filtered,
                    calc_options['period_type'],
                    calc_options['track_backlog']
                )
                
                # Save to session state
                st.session_state['pgap_gap_df'] = gap_df
                st.session_state['pgap_demand_filtered'] = df_demand_filtered
                st.session_state['pgap_supply_filtered'] = df_supply_filtered
                st.session_state['pgap_calc_options'] = calc_options
                st.session_state['pgap_filters'] = filters
                st.session_state['pgap_sources'] = selected_sources
                st.session_state['pgap_analysis_complete'] = True
                
                save_to_session_state('gap_analysis_result', gap_df)
                save_to_session_state('demand_filtered', df_demand_filtered)
                save_to_session_state('supply_filtered', df_supply_filtered)
                save_to_session_state('last_analysis_time', datetime.now().strftime('%Y-%m-%d %H:%M'))
        
        # Display results if analysis has been run
        if st.session_state.get('pgap_analysis_complete'):
            gap_df = st.session_state.get('pgap_gap_df', pd.DataFrame())
            df_demand_filtered = st.session_state.get('pgap_demand_filtered', pd.DataFrame())
            df_supply_filtered = st.session_state.get('pgap_supply_filtered', pd.DataFrame())
            stored_calc_options = st.session_state.get('pgap_calc_options', calc_options)
            stored_sources = st.session_state.get('pgap_sources', selected_sources)
            
            if gap_df.empty:
                st.warning("No data available for the selected filters and sources.")
                st.stop()
            
            # Show OC date field info
            if 'OC' in stored_sources.get("demand", []):
                st.info(f"📊 OC Analysis using: **{stored_sources.get('oc_date_field', 'ETA')}**")
            
            st.markdown("---")
            
            # === OVERVIEW SECTION ===
            display_options = {
                'period_type': stored_calc_options['period_type'],
                'track_backlog': stored_calc_options['track_backlog']
            }
            
            render_overview_section(gap_df, display_options)
            
            st.markdown("---")
            
            # === TABS SECTION ===
            tab1, tab2, tab3, tab4 = st.tabs([
                "📋 GAP Detail",
                "📦 Product Summary",
                "📅 Period Summary",
                "🔄 Pivot View"
            ])
            
            with tab1:
                render_gap_detail_tab(
                    gap_df,
                    display_options,
                    df_demand_filtered,
                    df_supply_filtered
                )
            
            with tab2:
                render_product_summary_tab(gap_df, display_options)
            
            with tab3:
                render_period_summary_tab(gap_df, display_options)
            
            with tab4:
                render_pivot_view_tab(gap_df, display_options)
            
            st.markdown("---")
            
            # === ACTION ITEMS EXPANDER ===
            render_action_items_expander(gap_df, df_supply_filtered)
            
            st.markdown("---")
            
            # === EXPORT SECTION ===
            st.markdown("### 📤 Export")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                excel_data = export_to_excel(
                    gap_df,
                    filters,
                    display_options,
                    stored_calc_options,
                    df_demand_filtered,
                    df_supply_filtered
                )
                st.download_button(
                    "📊 Export Full Report",
                    data=excel_data,
                    file_name=f"gap_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col2:
                st.caption("Export includes: Export_Info, GAP_Analysis, Product_Summary, Period_Summary, Pivot_View, Action_Items")
    
    except Exception as e:
        handle_error(e)
    
    # Footer
    st.markdown("---")
    st.caption(f"Period GAP Analysis v{VERSION} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()