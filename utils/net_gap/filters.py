# utils/net_gap/filters.py

"""
Filter Components for GAP Analysis - Enhanced with Quick Add
- Added bulk PT code input via Quick Add modal
- Smart parsing of multiple delimiter formats
- Validation feedback for matched/unmatched codes
- Fixed widget state synchronization with dynamic keys
"""

import streamlit as st
import pandas as pd
import re
from typing import Dict, Any, Optional, List, Tuple, Set
from datetime import datetime, timedelta
import logging

from .constants import SUPPLY_SOURCES, DEMAND_SOURCES
from .state import get_state

logger = logging.getLogger(__name__)


class PTCodeParser:
    """Handles parsing and validation of PT codes from bulk input"""
    
    @staticmethod
    def parse_pt_codes(input_text: str) -> List[str]:
        """
        Parse PT codes from text with multiple delimiter support
        Supports: comma, semicolon, space, newline, tab
        """
        if not input_text or not input_text.strip():
            return []
        
        # Replace common delimiters with a standard one
        normalized = input_text.upper().strip()
        
        # Replace various delimiters with comma
        for delimiter in [';', '\n', '\r', '\t', '|']:
            normalized = normalized.replace(delimiter, ',')
        
        # Split by comma and/or spaces
        codes = re.split(r'[,\s]+', normalized)
        
        # Clean and filter
        cleaned_codes = []
        for code in codes:
            code = code.strip()
            # Filter out empty strings and validate basic format
            if code and len(code) > 0:
                # Remove any quotes or special characters
                code = re.sub(r'["\']', '', code)
                if code:  # Check again after cleaning
                    cleaned_codes.append(code)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_codes = []
        for code in cleaned_codes:
            if code not in seen:
                seen.add(code)
                unique_codes.append(code)
        
        return unique_codes
    
    @staticmethod
    def validate_codes(parsed_codes: List[str], available_products: pd.DataFrame) -> Dict[str, Any]:
        """
        Validate parsed codes against available products
        Returns dict with matched product IDs and unmatched codes
        """
        if available_products.empty:
            return {
                'matched_ids': [],
                'matched_codes': [],
                'unmatched_codes': parsed_codes,
                'match_rate': 0
            }
        
        # Create mapping of PT codes to product IDs (case-insensitive)
        pt_code_map = {}
        for _, row in available_products.iterrows():
            pt_code = str(row.get('pt_code', '')).upper().strip()
            if pt_code:
                pt_code_map[pt_code] = {
                    'id': row['product_id'],
                    'original_code': row.get('pt_code', ''),
                    'name': row.get('product_name', '')
                }
        
        matched_ids = []
        matched_codes = []
        unmatched_codes = []
        
        for code in parsed_codes:
            code_upper = code.upper().strip()
            if code_upper in pt_code_map:
                matched_ids.append(pt_code_map[code_upper]['id'])
                matched_codes.append(pt_code_map[code_upper]['original_code'])
            else:
                unmatched_codes.append(code)
        
        match_rate = (len(matched_codes) / len(parsed_codes) * 100) if parsed_codes else 0
        
        return {
            'matched_ids': matched_ids,
            'matched_codes': matched_codes,
            'unmatched_codes': unmatched_codes,
            'match_rate': match_rate
        }


@st.dialog("Quick Add PT Codes", width="large")
def show_quick_add_dialog(products_df: pd.DataFrame, current_selection: List[int], exclude_mode: bool):
    """
    Dialog for bulk PT code input
    Returns selected product IDs to add to current selection
    """
    
    st.markdown("### Bulk Import PT Codes")
    st.caption("Paste PT codes separated by commas, semicolons, spaces, or on new lines")
    
    # Initialize session state for dialog
    if 'quick_add_text' not in st.session_state:
        st.session_state.quick_add_text = ""
    if 'quick_add_results' not in st.session_state:
        st.session_state.quick_add_results = None
    
    # Text input area
    input_text = st.text_area(
        "PT Codes",
        value=st.session_state.quick_add_text,
        height=150,
        placeholder="Example:\nP001000001\nP001001271, P001001286\nP001001288; P001001290",
        key="pt_code_input"
    )
    
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("📋 Parse & Validate", type="primary", use_container_width=True):
            if input_text.strip():
                # Parse codes
                parser = PTCodeParser()
                parsed_codes = parser.parse_pt_codes(input_text)
                
                if parsed_codes:
                    # Validate against available products
                    validation = parser.validate_codes(parsed_codes, products_df)
                    st.session_state.quick_add_results = validation
                    st.session_state.quick_add_text = input_text
                    st.rerun()  # FIX: Rerun to show results immediately
                else:
                    st.warning("No valid PT codes found in input")
            else:
                st.warning("Please enter PT codes to parse")
    
    with col2:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.quick_add_text = ""
            st.session_state.quick_add_results = None
            st.rerun()
    
    # Display results
    if st.session_state.quick_add_results:
        results = st.session_state.quick_add_results
        
        st.divider()
        
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("✅ Matched", len(results['matched_codes']))
        with col2:
            st.metric("⚠️ Not Found", len(results['unmatched_codes']))
        with col3:
            st.metric("📊 Match Rate", f"{results['match_rate']:.0f}%")
        
        # Show matched codes
        if results['matched_codes']:
            with st.expander(f"✅ Matched PT Codes ({len(results['matched_codes'])})", expanded=True):
                # Display in columns for better readability
                matched_display = results['matched_codes']
                n_cols = 3
                cols = st.columns(n_cols)
                for i, code in enumerate(matched_display[:30]):  # Show first 30
                    with cols[i % n_cols]:
                        st.caption(f"• {code}")
                if len(matched_display) > 30:
                    st.caption(f"... and {len(matched_display) - 30} more")
        
        # Show unmatched codes
        if results['unmatched_codes']:
            with st.expander(f"⚠️ Not Found ({len(results['unmatched_codes'])})", expanded=True):
                st.warning("These PT codes were not found in the available products:")
                unmatched_text = ", ".join(results['unmatched_codes'][:20])
                if len(results['unmatched_codes']) > 20:
                    unmatched_text += f"... and {len(results['unmatched_codes']) - 20} more"
                st.text(unmatched_text)
        
        # Action buttons
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            if results['matched_ids']:
                action_text = "Add to Excluded" if exclude_mode else "Add to Selected"
                if st.button(f"✅ {action_text} ({len(results['matched_ids'])} products)", 
                            type="primary", use_container_width=True):
                    # Return the matched IDs to be added
                    st.session_state.quick_add_confirmed = results['matched_ids']
                    st.session_state.quick_add_text = ""
                    st.session_state.quick_add_results = None
                    
                    # Increment widget counter to force re-render (FIX FOR BUG)
                    if 'product_widget_counter' not in st.session_state:
                        st.session_state.product_widget_counter = 0
                    st.session_state.product_widget_counter += 1
                    
                    # Clear show flag to close dialog
                    if 'show_quick_add' in st.session_state:
                        del st.session_state.show_quick_add
                    st.rerun()
        
        with col2:
            if st.button("❌ Cancel", use_container_width=True):
                st.session_state.quick_add_text = ""
                st.session_state.quick_add_results = None
                st.session_state.quick_add_cancelled = True
                # Clear show flag to close dialog
                if 'show_quick_add' in st.session_state:
                    del st.session_state.show_quick_add
                st.rerun()


class GAPFilters:
    """Filter management with enhanced Quick Add functionality"""
    
    def __init__(self, data_loader):
        self.data_loader = data_loader
        self.state = get_state()
        self._safety_available = data_loader.check_safety_stock_availability()
    
    def render_filters(self) -> Dict[str, Any]:
        """Render all filters with improved layout and Quick Add support"""
        
        # Initialize widget counter if not exists (FIX FOR BUG)
        if 'product_widget_counter' not in st.session_state:
            st.session_state.product_widget_counter = 0
        
        with st.container():
            # Apply compact CSS with tooltip support
            self._apply_compact_css()
            
            # Get current filters from state
            current = self.state.get_filters()
            filters = {}
            
            # Date Range Display (non-editable, informational)
            self._render_date_range_info()
            
            # Scope Section - 2 Row Layout
            st.markdown("#### 🔍 Scope")
            
            # Row 1: Entity | Brand
            col_entity, col_brand = st.columns([6, 4])
            
            with col_entity:
                entity_data = self._render_entity_selector(current)
                filters['entity'] = entity_data['selected']
                filters['exclude_entity'] = entity_data['exclude']
            
            with col_brand:
                brand_data = self._render_brand_selector(filters.get('entity'), current)
                filters['brands'] = brand_data['selected']
                filters['exclude_brands'] = brand_data['exclude']
            
            # Row 2: Products with Quick Add | Exclude Expired Inventory
            col_product, col_expired = st.columns([8, 2])
            
            with col_product:
                product_data = self._render_product_selector_with_quick_add(
                    filters.get('entity'), current
                )
                filters['products'] = product_data['selected']
                filters['exclude_products'] = product_data['exclude']
            
            with col_expired:
                st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                filters['exclude_expired'] = st.checkbox(
                    "🚫 No Expired",
                    value=current.get('exclude_expired', True),
                    key="exclude_expired",
                    help="Exclude expired inventory from supply"
                )
            
            # Data Sources Section
            st.markdown("#### 📊 Data Sources")
            col_supply, col_demand, col_safety = st.columns([4, 3, 3])
            
            with col_supply:
                filters['supply_sources'] = self._render_supply_sources(current)
            
            with col_demand:
                filters['demand_sources'] = self._render_demand_sources(current)
            
            with col_safety:
                filters['include_safety'] = self._render_safety_toggle(current)
            
            # Analysis Options
            col_group, col_info = st.columns([3, 7])
            
            with col_group:
                filters['group_by'] = st.radio(
                    "Group by",
                    options=['product', 'brand'],
                    format_func=lambda x: f"📊 By {x.title()}",
                    index=0 if current.get('group_by') == 'product' else 1,
                    horizontal=True,
                    key="group_by"
                )
            
            with col_info:
                active_filters = self._count_active_filters(filters)
                if active_filters > 0:
                    st.info(f"✔ {active_filters} filters active")
        
        # Convert lists to tuples for caching
        filters['products_tuple'] = tuple(filters.get('products', []))
        filters['brands_tuple'] = tuple(filters.get('brands', []))
        
        return filters
    
    def _apply_compact_css(self):
        """Apply CSS for compact layout with tooltip support"""
        st.markdown("""
            <style>
            /* Compact multiselect */
            .stMultiSelect > div {
                max-height: 38px;
            }
            /* Reduce column gaps */
            [data-testid="column"] {
                padding: 0 0.5rem;
            }
            /* Align elements */
            .stCheckbox {
                margin-top: 28px;
            }
            /* Quick Add button styling */
            .quick-add-btn {
                background: #0066cc;
                color: white;
                border: none;
                padding: 4px 12px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }
            .quick-add-btn:hover {
                background: #0052a3;
            }
            </style>
        """, unsafe_allow_html=True)
    
    def _render_date_range_info(self):
        """Display data date range information"""
        try:
            today = datetime.now().date()
            min_date = today - timedelta(days=90)
            max_date = today + timedelta(days=90)
            
            st.info(
                f"📅 Data Range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')} "
                f"(All available data will be included)"
            )
        except Exception as e:
            logger.warning(f"Could not display date range: {e}")
    
    def _render_entity_selector(self, current: Dict) -> Dict[str, Any]:
        """Render entity selector with improved format"""
        try:
            entities_df = self.data_loader.get_entities_formatted()
            
            if entities_df.empty:
                st.warning("No entities")
                return {'selected': None, 'exclude': False}
            
            entity_count = len(entities_df)
            
            # Sub-columns
            sub1, sub2 = st.columns([5, 1])
            
            with sub1:
                options = [f"All ({entity_count} available)"]
                entity_map = {}
                
                for _, row in entities_df.iterrows():
                    code = row.get('company_code', 'N/A')
                    name = row['english_name']
                    display_name = name[:40] + "..." if len(name) > 40 else name
                    display = f"{code} | {display_name}"
                    
                    options.append(display)
                    entity_map[display] = row['english_name']
                
                current_entity = current.get('entity')
                default_idx = 0
                if current_entity:
                    for idx, (display, name) in enumerate(entity_map.items(), 1):
                        if name == current_entity:
                            default_idx = idx
                            break
                
                selected_display = st.selectbox(
                    "Entity",
                    options=options,
                    index=default_idx,
                    key="entity_select",
                    help="Select entity or leave as 'All'"
                )
            
            with sub2:
                st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                exclude = st.checkbox(
                    "Excl",
                    value=current.get('exclude_entity', False),
                    key="entity_excl",
                    help="Exclude this entity"
                )
            
            if selected_display.startswith("All"):
                return {'selected': None, 'exclude': False}
            else:
                entity = entity_map.get(selected_display)
                if entity and exclude:
                    st.caption("🚫 Excluded")
                elif entity:
                    st.caption("✔ Only")
                return {'selected': entity, 'exclude': exclude}
                
        except Exception as e:
            logger.error(f"Error loading entities: {e}")
            st.error("Failed to load entities")
            return {'selected': None, 'exclude': False}
    
    def _render_product_selector_with_quick_add(self, entity: Optional[str], current: Dict) -> Dict[str, Any]:
        """Enhanced product selector with Quick Add functionality - FIXED WITH DYNAMIC KEY"""
        try:
            products_df = self.data_loader.get_products(entity)
            
            if products_df.empty:
                return {'selected': [], 'exclude': False}
            
            # Format display
            def format_product_display(row):
                pt_code = row.get('pt_code', 'N/A')
                name = row.get('product_name', 'N/A')
                package = row.get('package_size', '')
                brand = row.get('brand', '')
                
                name_display = name[:25] + "..." if len(name) > 25 else name
                display = f"{pt_code} | {name_display}"
                if package:
                    display += f" | {package}"
                if brand:
                    display += f" ({brand})"
                
                return display
            
            products_df['display'] = products_df.apply(format_product_display, axis=1)
            
            # Create mapping
            product_map = {}
            for _, row in products_df.iterrows():
                product_map[row['product_id']] = {
                    'display': row['display'],
                    'pt_code': row.get('pt_code', '')
                }
            
            # Get selection from session state if exists, otherwise from current filters
            session_key = 'product_selection_state'
            
            # Check if Quick Add was confirmed (do this BEFORE getting current selection)
            if 'quick_add_confirmed' in st.session_state:
                new_ids = st.session_state.quick_add_confirmed
                # Get current selection
                if session_key in st.session_state:
                    current_selection = st.session_state[session_key]
                else:
                    current_selection = current.get('products', [])
                
                # Merge: add new IDs to existing selection (remove duplicates)
                merged_selection = list(set(current_selection + new_ids))
                # Filter to only valid product IDs
                valid_selected = [p for p in merged_selection if p in product_map]
                # Save to session state
                st.session_state[session_key] = valid_selected
                
                # Clear the flag
                del st.session_state.quick_add_confirmed
                logger.info(f"Quick Add: Added {len(new_ids)} products, total now: {len(valid_selected)}")
            elif session_key in st.session_state:
                valid_selected = st.session_state[session_key]
            else:
                current_products = current.get('products', [])
                valid_selected = [p for p in current_products if p in product_map]
            
            # Layout with Quick Add button
            st.markdown("**Products**")
            sub1, sub2, sub3 = st.columns([4.5, 1, 0.5])
            
            with sub1:
                # FIX: Use dynamic key based on counter to force re-render when needed
                widget_key = f"products_multi_{st.session_state.product_widget_counter}"
                
                selected = st.multiselect(
                    "Products",
                    options=list(product_map.keys()),
                    default=valid_selected,
                    format_func=lambda x: product_map[x]['display'],
                    placeholder=f"All ({len(products_df)} available)",
                    key=widget_key,  # Dynamic key
                    label_visibility="collapsed",
                    help="Select products or use Quick Add for bulk import"
                )
                
                # Update session state whenever selection changes
                st.session_state[session_key] = selected
            
            with sub2:
                if st.button("📋 Quick Add", key="quick_add_btn", use_container_width=True,
                            help="Bulk import PT codes"):
                    st.session_state.show_quick_add = True
            
            with sub3:
                exclude = st.checkbox(
                    "Excl",
                    value=current.get('exclude_products', False),
                    key="products_excl",
                    help="Exclude selected"
                )
            
            # Show Quick Add dialog if triggered
            if st.session_state.get('show_quick_add'):
                show_quick_add_dialog(products_df, selected, exclude)
                # Don't delete flag here - let dialog buttons handle it
                # This prevents dialog from staying open after rerun
            
            # Clear cancelled flag if set
            if st.session_state.get('quick_add_cancelled'):
                del st.session_state.quick_add_cancelled
            
            # Display selection info
            if selected:
                st.caption(f"{len(selected)} products {'excluded' if exclude else 'selected'}")
            
            return {'selected': selected, 'exclude': exclude}
            
        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return {'selected': [], 'exclude': False}
    
    def _render_brand_selector(self, entity: Optional[str], current: Dict) -> Dict[str, Any]:
        """Render brand multiselect"""
        try:
            brands = self.data_loader.get_brands(entity)
            
            if not brands:
                return {'selected': [], 'exclude': False}
            
            current_brands = current.get('brands', [])
            valid_selected = [b for b in current_brands if b in brands]
            
            sub1, sub2 = st.columns([4, 2])
            
            with sub1:
                selected = st.multiselect(
                    "Brands",
                    options=brands,
                    default=valid_selected,
                    placeholder=f"All ({len(brands)})",
                    key="brands_multi",
                    help="Select brands or leave empty for all"
                )
            
            with sub2:
                st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                exclude = st.checkbox(
                    "Excl",
                    value=current.get('exclude_brands', False),
                    key="brands_excl",
                    help="Exclude selected brands"
                )
            
            return {'selected': selected, 'exclude': exclude}
            
        except Exception as e:
            logger.error(f"Error loading brands: {e}")
            return {'selected': [], 'exclude': False}
    
    def _render_supply_sources(self, current: Dict) -> List[str]:
        """Render supply source checkboxes"""
        st.markdown("**Supply Sources**")
        
        selected = []
        default_selected = current.get('supply_sources', list(SUPPLY_SOURCES.keys()))
        
        cols = st.columns(2)
        sources = list(SUPPLY_SOURCES.items())
        
        for idx, (key, config) in enumerate(sources):
            col_idx = idx % 2
            with cols[col_idx]:
                if st.checkbox(
                    f"{config['icon']} {config['name']}",
                    value=key in default_selected,
                    key=f"supply_{key}",
                    help=f"Lead: {config['lead_days']} days"
                ):
                    selected.append(key)
        
        return selected if selected else ['INVENTORY']
    
    def _render_demand_sources(self, current: Dict) -> List[str]:
        """Render demand source checkboxes"""
        st.markdown("**Demand Sources**")
        
        selected = []
        default_selected = current.get('demand_sources', ['OC_PENDING'])
        
        for key, config in DEMAND_SOURCES.items():
            if st.checkbox(
                f"{config['icon']} {config['name']}",
                value=key in default_selected,
                key=f"demand_{key}"
            ):
                selected.append(key)
        
        return selected if selected else ['OC_PENDING']
    
    def _render_safety_toggle(self, current: Dict) -> bool:
        """Render safety stock toggle"""
        st.markdown("**Safety Stock**")
        
        if self._safety_available:
            return st.toggle(
                "Include Safety",
                value=current.get('include_safety', True),
                key="safety_toggle"
            )
        else:
            st.caption("⚠️ Not configured")
            return False
    
    def _count_active_filters(self, filters: Dict) -> int:
        """Count non-default filters"""
        count = 0
        defaults = self.state.get_default_filters()
        
        if filters.get('entity') != defaults['entity']:
            count += 1
        if filters.get('products', []) != defaults['products']:
            count += 1
        if filters.get('brands', []) != defaults['brands']:
            count += 1
        if filters.get('exclude_expired') != defaults['exclude_expired']:
            count += 1
        if set(filters.get('supply_sources', [])) != set(defaults['supply_sources']):
            count += 1
        if set(filters.get('demand_sources', [])) != set(defaults['demand_sources']):
            count += 1
        
        return count