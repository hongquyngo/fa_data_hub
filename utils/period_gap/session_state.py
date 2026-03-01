# utils/period_gap/session_state.py
"""
Complete Session State Management for Period GAP Analysis
Version 2.2 - Added Quick Add PT code support
"""

import streamlit as st
from typing import Any, Dict, List
from datetime import datetime

def initialize_session_state():
    """Initialize all required session state variables for Period GAP"""
    
    defaults = {
        # Data loading status
        'period_gap_data_loaded': False,
        'period_gap_load_time': None,
        
        # Analysis status
        'period_gap_analysis_ran': False,
        'period_gap_analysis_data': None,
        'period_gap_result': None,
        
        # Cross-page data sharing (CRITICAL)
        'gap_analysis_result': None,
        'demand_filtered': None,
        'supply_filtered': None,
        'last_gap_analysis': None,
        'last_analysis_time': None,
        
        # Filter cache (removed customers)
        'period_gap_filter_entities': [],
        'period_gap_filter_products': [],
        'period_gap_filter_brands': [],
        
        # Filter data initialization
        'pgap_filter_data': None,
        'pgap_temp_demand': None,
        'pgap_temp_supply': None,
        
        # Calculation options cache
        'period_gap_period_type': 'Weekly',
        'period_gap_track_backlog': True,
        'period_gap_exclude_missing_dates': True,
        
        # Display options cache
        'period_gap_show_matched': True,
        'period_gap_show_demand_only': True,
        'period_gap_show_supply_only': True,
        'period_gap_period_filter': 'All',
        'period_gap_enable_row_highlighting': False,
        
        # GAP calculation cache
        'pgap_gap_df': None,
        'pgap_result_cache_key': None,
        
        # Exclude filter states
        'pgap_exclude_entity': False,
        'pgap_exclude_product': False,
        'pgap_exclude_brand': False,
        'pgap_selected_entities_excluded': [],
        'pgap_selected_products_excluded': [],
        'pgap_selected_brands_excluded': [],
        
        # Quick Add PT code states
        'pgap_quick_add_text': '',
        'pgap_quick_add_results': None,
        # Note: pgap_quick_add_confirmed is NOT initialized here
        # It's only set when user confirms Quick Add selection
        'pgap_quick_add_cancelled': False,
        'pgap_show_quick_add': False,
        'pgap_product_widget_counter': 0
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def get_session_value(key: str, default: Any = None) -> Any:
    """
    Safely get value from session state
    
    Args:
        key: Session state key
        default: Default value if key not found
    
    Returns:
        Value from session state or default
    """
    return st.session_state.get(key, default)


def set_session_value(key: str, value: Any):
    """
    Safely set value in session state
    
    Args:
        key: Session state key
        value: Value to set
    """
    st.session_state[key] = value


def save_filter_state(filter_config: Dict[str, Any]):
    """
    Save filter configuration including exclude states
    
    Args:
        filter_config: Dictionary containing filter settings and exclude flags
    """
    if 'entity' in filter_config:
        st.session_state['pgap_selected_entities'] = filter_config['entity']
        st.session_state['pgap_exclude_entity'] = filter_config.get('exclude_entity', False)
    
    if 'product' in filter_config:
        st.session_state['pgap_selected_products'] = filter_config['product']
        st.session_state['pgap_exclude_product'] = filter_config.get('exclude_product', False)
    
    if 'brand' in filter_config:
        st.session_state['pgap_selected_brands'] = filter_config['brand']
        st.session_state['pgap_exclude_brand'] = filter_config.get('exclude_brand', False)
    
    if 'start_date' in filter_config:
        st.session_state['pgap_start_date'] = filter_config['start_date']
    if 'end_date' in filter_config:
        st.session_state['pgap_end_date'] = filter_config['end_date']


def get_filter_state() -> Dict[str, Any]:
    """
    Get current filter configuration including exclude states
    
    Returns:
        Dictionary with current filter settings
    """
    return {
        'entity': get_session_value('pgap_selected_entities', []),
        'exclude_entity': get_session_value('pgap_exclude_entity', False),
        'product': get_session_value('pgap_selected_products', []),
        'exclude_product': get_session_value('pgap_exclude_product', False),
        'brand': get_session_value('pgap_selected_brands', []),
        'exclude_brand': get_session_value('pgap_exclude_brand', False),
        'start_date': get_session_value('pgap_start_date'),
        'end_date': get_session_value('pgap_end_date')
    }


def clear_period_gap_cache():
    """Clear Period GAP analysis cache but preserve filter data"""
    cache_keys = [
        'period_gap_data_loaded',
        'period_gap_load_time',
        'period_gap_analysis_ran',
        'period_gap_analysis_data',
        'period_gap_result',
        'pgap_gap_df',
        'pgap_result_cache_key'
    ]
    
    for key in cache_keys:
        if key in st.session_state:
            del st.session_state[key]


def save_period_gap_state(data: dict):
    """
    Save Period GAP analysis state for display and cross-page access
    
    Args:
        data: Dictionary with analysis results
    """
    st.session_state['period_gap_analysis_data'] = data
    st.session_state['period_gap_analysis_ran'] = True
    st.session_state['period_gap_load_time'] = datetime.now()
    
    if 'demand' in data:
        st.session_state['demand_filtered'] = data['demand']
    if 'supply' in data:
        st.session_state['supply_filtered'] = data['supply']
    
    if 'filters' in data:
        save_filter_state(data['filters'])


def get_period_gap_state() -> dict:
    """
    Get Period GAP analysis state
    
    Returns:
        Dictionary with cached analysis data or empty dict
    """
    if st.session_state.get('period_gap_analysis_ran', False):
        return st.session_state.get('period_gap_analysis_data', {})
    return {}


def update_filter_cache(entities: list, products: list, brands: list):
    """
    Update filter options cache for dropdowns
    
    Args:
        entities: List of entities
        products: List of products
        brands: List of brands
    """
    st.session_state['period_gap_filter_entities'] = entities or []
    st.session_state['period_gap_filter_products'] = products or []
    st.session_state['period_gap_filter_brands'] = brands or []


def get_filter_cache() -> dict:
    """
    Get cached filter options
    
    Returns:
        Dictionary with filter options
    """
    return {
        'entities': st.session_state.get('period_gap_filter_entities', []),
        'products': st.session_state.get('period_gap_filter_products', []),
        'brands': st.session_state.get('period_gap_filter_brands', [])
    }


def is_gap_analysis_available() -> bool:
    """
    Check if GAP analysis results are available for other pages
    
    Returns:
        True if GAP analysis has been run and results are available
    """
    return (
        st.session_state.get('gap_analysis_result') is not None and
        st.session_state.get('demand_filtered') is not None and
        st.session_state.get('supply_filtered') is not None
    )


def get_gap_analysis_for_allocation() -> dict:
    """
    Get GAP analysis data formatted for Allocation Plan page
    
    Returns:
        Dictionary with gap_df, demand_df, supply_df or None values
    """
    if is_gap_analysis_available():
        return {
            'gap_df': st.session_state.get('gap_analysis_result'),
            'demand_df': st.session_state.get('demand_filtered'),
            'supply_df': st.session_state.get('supply_filtered'),
            'period_type': st.session_state.get('period_gap_period_type', 'Weekly'),
            'analysis_time': st.session_state.get('last_analysis_time'),
            'filters': get_filter_state()
        }
    return {
        'gap_df': None,
        'demand_df': None,
        'supply_df': None,
        'period_type': 'Weekly',
        'analysis_time': None,
        'filters': {}
    }


def get_gap_analysis_for_po_suggestions() -> dict:
    """
    Get GAP analysis data formatted for PO Suggestions page
    
    Returns:
        Dictionary with shortage products and analysis metadata
    """
    gap_df = st.session_state.get('gap_analysis_result')
    
    if gap_df is not None and not gap_df.empty:
        shortage_df = gap_df[gap_df['gap_quantity'] < 0].copy()
        
        if not shortage_df.empty:
            shortage_summary = shortage_df.groupby(['pt_code', 'product_name']).agg({
                'gap_quantity': lambda x: x.abs().sum(),
                'period': 'count'
            }).reset_index()
            shortage_summary.columns = ['pt_code', 'product_name', 'shortage_quantity', 'affected_periods']
            
            return {
                'shortage_products': shortage_summary,
                'period_type': st.session_state.get('period_gap_period_type', 'Weekly'),
                'analysis_time': st.session_state.get('last_analysis_time'),
                'filters': get_filter_state()
            }
    
    return {
        'shortage_products': None,
        'period_type': 'Weekly',
        'analysis_time': None,
        'filters': {}
    }


def clear_all_gap_data():
    """Clear all GAP analysis related data (for logout or reset)"""
    gap_keys = [k for k in st.session_state.keys() if any(
        pattern in k.lower() for pattern in ['gap', 'pgap', 'period_gap']
    )]
    
    for key in gap_keys:
        del st.session_state[key]
    
    cross_page_keys = [
        'gap_analysis_result',
        'demand_filtered',
        'supply_filtered',
        'last_gap_analysis',
        'last_analysis_time'
    ]
    
    for key in cross_page_keys:
        if key in st.session_state:
            del st.session_state[key]


def get_filter_summary() -> str:
    """
    Get a text summary of active filters
    
    Returns:
        String description of active filters
    """
    filter_state = get_filter_state()
    summary_parts = []
    
    if filter_state['entity']:
        mode = "excluding" if filter_state['exclude_entity'] else "including"
        count = len(filter_state['entity'])
        summary_parts.append(f"{mode} {count} entities")
    
    if filter_state['product']:
        mode = "excluding" if filter_state['exclude_product'] else "including"
        count = len(filter_state['product'])
        summary_parts.append(f"{mode} {count} products")
    
    if filter_state['brand']:
        mode = "excluding" if filter_state['exclude_brand'] else "including"
        count = len(filter_state['brand'])
        summary_parts.append(f"{mode} {count} brands")
    
    if summary_parts:
        return "Filters: " + ", ".join(summary_parts)
    else:
        return "No active filters"


def is_filter_active() -> bool:
    """
    Check if any filter is active
    
    Returns:
        True if any filter has selections
    """
    filter_state = get_filter_state()
    return any([
        filter_state['entity'],
        filter_state['product'],
        filter_state['brand']
    ])


def clear_quick_add_state():
    """Clear all Quick Add related session state"""
    quick_add_keys = [
        'pgap_quick_add_text',
        'pgap_quick_add_results',
        'pgap_quick_add_confirmed',
        'pgap_quick_add_cancelled',
        'pgap_show_quick_add'
    ]
    
    for key in quick_add_keys:
        if key in st.session_state:
            del st.session_state[key]


def increment_product_widget_counter():
    """Increment product widget counter to force re-render"""
    if 'pgap_product_widget_counter' not in st.session_state:
        st.session_state['pgap_product_widget_counter'] = 0
    st.session_state['pgap_product_widget_counter'] += 1


def get_product_widget_key() -> str:
    """Get current product widget key based on counter"""
    counter = st.session_state.get('pgap_product_widget_counter', 0)
    return f"pgap_products_multi_{counter}"