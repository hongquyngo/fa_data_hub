# utils/net_gap/state.py

"""
Simplified state management for GAP Analysis - Fixed Reset with Widget Counter
"""

import streamlit as st
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class GAPState:
    """Simple state manager with complete reset functionality"""
    
    # State keys
    KEY_FILTERS = 'gap_filters'
    KEY_RESULT = 'gap_result'
    KEY_PAGE = 'current_page'
    KEY_DIALOG_PAGE = 'dialog_page'
    KEY_PRODUCT_SELECTION = 'product_selection_state'
    KEY_WIDGET_COUNTER = 'product_widget_counter'  # Added key for widget counter
    
    def __init__(self):
        self._init_defaults()
    
    def _init_defaults(self):
        """Initialize default values"""
        if self.KEY_FILTERS not in st.session_state:
            st.session_state[self.KEY_FILTERS] = self.get_default_filters()
        if self.KEY_RESULT not in st.session_state:
            st.session_state[self.KEY_RESULT] = None
        if self.KEY_PAGE not in st.session_state:
            st.session_state[self.KEY_PAGE] = 1
        if self.KEY_DIALOG_PAGE not in st.session_state:
            st.session_state[self.KEY_DIALOG_PAGE] = 1
        if self.KEY_WIDGET_COUNTER not in st.session_state:
            st.session_state[self.KEY_WIDGET_COUNTER] = 0
    
    @staticmethod
    def get_default_filters() -> Dict[str, Any]:
        """Get default filter configuration"""
        return {
            'entity': None,
            'exclude_entity': False,
            'products': [],
            'exclude_products': False,
            'brands': [],
            'exclude_brands': False,
            'exclude_expired': True,
            'group_by': 'product',
            'supply_sources': ['INVENTORY', 'CAN_PENDING', 'WAREHOUSE_TRANSFER', 'PURCHASE_ORDER'],
            'demand_sources': ['OC_PENDING'],
            'include_safety': True
        }
    
    # Filters
    def get_filters(self) -> Dict[str, Any]:
        """Get current filters"""
        return st.session_state.get(self.KEY_FILTERS, self.get_default_filters())
    
    def set_filters(self, filters: Dict[str, Any]):
        """Set filters and check if changed"""
        current = self.get_filters()
        
        # Check if filters actually changed (simple comparison)
        changed = False
        for key in ['entity', 'products', 'brands', 'supply_sources', 'demand_sources', 
                   'include_safety', 'group_by', 'exclude_expired']:
            if filters.get(key) != current.get(key):
                changed = True
                break
        
        st.session_state[self.KEY_FILTERS] = filters
        
        # Clear result if filters changed
        if changed:
            st.session_state[self.KEY_RESULT] = None
            st.session_state[self.KEY_PAGE] = 1
            logger.info("Filters changed, cleared result")
    
    def reset_filters(self):
        """Reset to default filters and clear ALL related state"""
        # Reset main filters
        st.session_state[self.KEY_FILTERS] = self.get_default_filters()
        st.session_state[self.KEY_RESULT] = None
        st.session_state[self.KEY_PAGE] = 1
        
        # Reset widget counter to force re-render
        st.session_state[self.KEY_WIDGET_COUNTER] = 0
        
        # Clear product selection state
        if self.KEY_PRODUCT_SELECTION in st.session_state:
            del st.session_state[self.KEY_PRODUCT_SELECTION]
        
        # Clear any Quick Add related state
        quick_add_keys = [
            'quick_add_text',
            'quick_add_results', 
            'quick_add_confirmed',
            'quick_add_cancelled',
            'show_quick_add'
        ]
        for key in quick_add_keys:
            if key in st.session_state:
                del st.session_state[key]
        
        # Clear dialog states
        dialog_keys = [
            'show_customer_dialog',
            self.KEY_DIALOG_PAGE
        ]
        for key in dialog_keys:
            if key in st.session_state:
                del st.session_state[key]
        
        # Clear multiselect widget keys (all variations)
        widget_keys_to_clear = []
        for key in st.session_state.keys():
            if key.startswith('products_multi'):
                widget_keys_to_clear.append(key)
        for key in widget_keys_to_clear:
            del st.session_state[key]
        
        logger.info("All filters and states reset to defaults")
    
    # GAP Result
    def get_result(self):
        """Get calculation result"""
        return st.session_state.get(self.KEY_RESULT)
    
    def set_result(self, result):
        """Store calculation result"""
        st.session_state[self.KEY_RESULT] = result
        logger.info(f"Stored result: {len(result.gap_df)} items")
    
    def has_result(self) -> bool:
        """Check if result exists"""
        return st.session_state.get(self.KEY_RESULT) is not None
    
    def should_recalculate(self) -> bool:
        """Check if recalculation needed"""
        return st.session_state.get(self.KEY_RESULT) is None
    
    # Pagination
    def get_page(self) -> int:
        """Get current page"""
        return st.session_state.get(self.KEY_PAGE, 1)
    
    def set_page(self, page: int, max_page: int):
        """Set page with validation"""
        page = max(1, min(page, max_page))
        st.session_state[self.KEY_PAGE] = page
    
    def get_dialog_page(self) -> int:
        """Get dialog page"""
        return st.session_state.get(self.KEY_DIALOG_PAGE, 1)
    
    def set_dialog_page(self, page: int, max_page: int):
        """Set dialog page"""
        page = max(1, min(page, max_page))
        st.session_state[self.KEY_DIALOG_PAGE] = page
    
    # Utility
    def clear_all(self):
        """Clear ALL state completely"""
        # List of all possible state keys to clear
        all_keys = [
            self.KEY_FILTERS,
            self.KEY_RESULT,
            self.KEY_PAGE,
            self.KEY_DIALOG_PAGE,
            self.KEY_PRODUCT_SELECTION,
            self.KEY_WIDGET_COUNTER,
            'quick_add_text',
            'quick_add_results',
            'quick_add_confirmed',
            'quick_add_cancelled',
            'show_quick_add',
            'show_customer_dialog',
            'quick_filter',
            'items_per_page',
            'search'
        ]
        
        # Clear widget keys (all variations)
        widget_keys_to_clear = []
        for key in st.session_state.keys():
            if key.startswith('products_multi'):
                widget_keys_to_clear.append(key)
        
        # Clear everything
        for key in all_keys:
            if key in st.session_state:
                del st.session_state[key]
        
        for key in widget_keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        # Re-initialize defaults
        self._init_defaults()
        logger.info("All state completely cleared")
    
    def increment_widget_counter(self):
        """Increment widget counter to force re-render"""
        if self.KEY_WIDGET_COUNTER not in st.session_state:
            st.session_state[self.KEY_WIDGET_COUNTER] = 0
        st.session_state[self.KEY_WIDGET_COUNTER] += 1
        logger.info(f"Widget counter incremented to {st.session_state[self.KEY_WIDGET_COUNTER]}")


# Singleton instance
_state = None

def get_state() -> GAPState:
    """Get or create state manager"""
    global _state
    if _state is None:
        _state = GAPState()
    return _state