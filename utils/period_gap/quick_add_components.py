# utils/period_gap/quick_add_components.py
"""
Quick Add Components for Period GAP Analysis
Provides bulk PT code import functionality via dialog
"""

import streamlit as st
from typing import List, Dict, Any
import logging
from .pt_code_parser import PTCodeParser

logger = logging.getLogger(__name__)


@st.dialog("📋 Quick Add PT Codes", width="large")
def show_quick_add_dialog_for_products(
    product_options: List[str],
    current_selection: List[str],
    exclude_mode: bool
):
    """
    Dialog for bulk PT code input
    Product options are in format: "PT_CODE | Product Name | Package (Brand)"
    
    Args:
        product_options: List of formatted product display strings
        current_selection: Currently selected product display strings
        exclude_mode: Whether exclude mode is active
    """
    
    st.markdown("### 📦 Bulk Import PT Codes")
    st.caption("Paste PT codes separated by commas, semicolons, spaces, or on new lines")
    
    # Initialize dialog state
    if 'pgap_quick_add_text' not in st.session_state:
        st.session_state.pgap_quick_add_text = ""
    if 'pgap_quick_add_results' not in st.session_state:
        st.session_state.pgap_quick_add_results = None
    
    # Text input area
    input_text = st.text_area(
        "PT Codes",
        value=st.session_state.pgap_quick_add_text,
        height=150,
        placeholder="Example:\nP001000001\nP001001271, P001001286\nP001001288; P001001290",
        key="pgap_pt_code_input",
        help="Enter PT codes in any format - separated by commas, semicolons, spaces, or new lines"
    )
    
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("🔍 Parse & Validate", type="primary", use_container_width=True):
            if input_text.strip():
                parser = PTCodeParser()
                parsed_codes = parser.parse_pt_codes(input_text)
                
                if parsed_codes:
                    validation = parser.validate_codes_against_display_list(
                        parsed_codes, 
                        product_options
                    )
                    st.session_state.pgap_quick_add_results = validation
                    st.session_state.pgap_quick_add_text = input_text
                    st.rerun()
                else:
                    st.warning("⚠️ No valid PT codes found in input")
            else:
                st.warning("⚠️ Please enter PT codes to parse")
    
    with col2:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.pgap_quick_add_text = ""
            st.session_state.pgap_quick_add_results = None
            st.rerun()
    
    # Display results
    if st.session_state.pgap_quick_add_results:
        results = st.session_state.pgap_quick_add_results
        
        st.divider()
        
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("✅ Matched", len(results['matched_codes']))
        with col2:
            st.metric("⚠️ Not Found", len(results['unmatched_codes']))
        with col3:
            match_rate = results['match_rate']
            st.metric("📊 Match Rate", f"{match_rate:.0f}%")
        
        # Show matched codes
        if results['matched_codes']:
            with st.expander(f"✅ Matched PT Codes ({len(results['matched_codes'])})", expanded=True):
                matched_display = results['matched_codes']
                n_cols = 3
                cols = st.columns(n_cols)
                for i, code in enumerate(matched_display[:30]):
                    with cols[i % n_cols]:
                        st.caption(f"• {code}")
                if len(matched_display) > 30:
                    st.caption(f"... and {len(matched_display) - 30} more")
        
        # Show unmatched codes
        if results['unmatched_codes']:
            with st.expander(f"⚠️ Not Found ({len(results['unmatched_codes'])})", expanded=False):
                st.warning("These PT codes were not found in the available products:")
                unmatched_text = ", ".join(results['unmatched_codes'][:20])
                if len(results['unmatched_codes']) > 20:
                    unmatched_text += f" ... and {len(results['unmatched_codes']) - 20} more"
                st.code(unmatched_text)
        
        # Action buttons
        st.divider()
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("✅ Add to Selection", type="primary", use_container_width=True,
                        disabled=not results['matched_options']):
                # Store matched options to be added (ensure it's a list)
                matched_options = results.get('matched_options', [])
                if matched_options:  # Only set if not empty
                    st.session_state.pgap_quick_add_confirmed = matched_options
                st.session_state.pgap_show_quick_add = False
                st.session_state.pgap_quick_add_text = ""
                st.session_state.pgap_quick_add_results = None
                st.rerun()
        
        with col2:
            if st.button("❌ Cancel", use_container_width=True):
                st.session_state.pgap_quick_add_cancelled = True
                st.session_state.pgap_show_quick_add = False
                st.session_state.pgap_quick_add_text = ""
                st.session_state.pgap_quick_add_results = None
                st.rerun()
        
        with col3:
            # Show help text
            if results['matched_options']:
                action_text = "exclude from" if exclude_mode else "add to"
                st.caption(f"💡 Will {action_text} selection: {len(results['matched_options'])} products")
    
    else:
        # Show example and help
        st.info("""
        **How to use:**
        1. Paste PT codes in the text area above
        2. Click "Parse & Validate" to check which codes are valid
        3. Review matched and unmatched codes
        4. Click "Add to Selection" to add matched products
        """)
        
        with st.expander("📝 Supported Formats", expanded=False):
            st.markdown("""
            **Delimiters:** Comma, semicolon, space, newline, tab, pipe
            
            **Examples:**
            ```
            P001000001, P001001271, P001001286
            P001000001; P001001271; P001001286
            P001000001 P001001271 P001001286
            P001000001
            P001001271
            P001001286
            ```
            """)


def render_multiselect_with_quick_add(
    label: str,
    options: List[str],
    key_prefix: str,
    placeholder: str = None,
    help_text: str = None,
    col_ratio: List[int] = [4.5, 1, 0.5],
    enable_quick_add: bool = True
) -> tuple[List[str], bool]:
    """
    Render a multiselect with Quick Add button and exclude checkbox
    
    Args:
        label: Label for the multiselect
        options: List of formatted product options (PT_CODE | Name | Package)
        key_prefix: Prefix for widget keys
        placeholder: Placeholder text
        help_text: Help text for multiselect
        col_ratio: Column width ratio [multiselect, quick_add_btn, checkbox]
        enable_quick_add: Enable Quick Add button
    
    Returns:
        Tuple of (selected_values, exclude_flag)
    """
    
    # Check for confirmed Quick Add
    if 'pgap_quick_add_confirmed' in st.session_state:
        new_options = st.session_state.pgap_quick_add_confirmed
        
        # Get current selection from widget or session
        widget_key = f"{key_prefix}_select"
        if widget_key in st.session_state:
            current_selection = st.session_state[widget_key]
        else:
            current_selection = []
        
        # Merge: add new options to existing selection (remove duplicates)
        merged_selection = list(set(current_selection + new_options))
        
        # Filter to only valid options
        valid_selected = [opt for opt in merged_selection if opt in options]
        
        # Update session state
        st.session_state[widget_key] = valid_selected
        
        # Clear the confirmation flag
        del st.session_state.pgap_quick_add_confirmed
        
        # Increment widget counter to force re-render
        from .session_state import increment_product_widget_counter
        increment_product_widget_counter()
        
        logger.info(f"Quick Add: Added {len(new_options)} products, total now: {len(valid_selected)}")
    
    # Get current widget key
    from .session_state import get_product_widget_key
    widget_key = get_product_widget_key()
    
    # Layout
    if enable_quick_add:
        col_main, col_quick, col_excl = st.columns(col_ratio)
    else:
        col_main, col_excl = st.columns([5, 1])
        col_quick = None
    
    with col_main:
        if placeholder is None:
            placeholder = f"All {label.lower()}"
        
        # Get default value from session state if exists
        default_value = st.session_state.get(widget_key, [])
        
        selected = st.multiselect(
            label,
            options=options,
            default=default_value,
            key=widget_key,
            placeholder=placeholder if options else f"No {label.lower()} available",
            help=help_text or "Select products or use Quick Add for bulk import"
        )
    
    # Quick Add button
    if enable_quick_add and col_quick:
        with col_quick:
            if st.button("📋 Quick Add", key=f"{key_prefix}_quick_add_btn", 
                        use_container_width=True, help="Bulk import PT codes"):
                st.session_state.pgap_show_quick_add = True
    
    # Exclude checkbox
    with col_excl:
        exclude = st.checkbox(
            "Excl",
            value=False,
            key=f"{key_prefix}_exclude",
            help=f"Exclude selected {label.lower()}"
        )
    
    # Show Quick Add dialog if triggered
    if st.session_state.get('pgap_show_quick_add'):
        show_quick_add_dialog_for_products(options, selected, exclude)
    
    # Clear cancelled flag if set
    if st.session_state.get('pgap_quick_add_cancelled'):
        del st.session_state.pgap_quick_add_cancelled
    
    # Display selection info
    if selected:
        st.caption(f"💡 {len(selected)} products {'excluded' if exclude else 'selected'}")
    
    return selected, exclude