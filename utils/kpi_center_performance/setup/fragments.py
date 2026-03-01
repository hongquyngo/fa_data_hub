# utils/kpi_center_performance/setup/fragments.py
"""
UI Fragments for Setup Tab - KPI Center Performance

v2.12.0: Converted KPI Assignments and Hierarchy CRUD to dialog fashion
v2.10.0: Integrated with permissions.py for granular CRUD control
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from .queries import SetupQueries

# v2.10.0: Permission system
from ..permissions import SetupPermissions, get_permissions


# =============================================================================
# CONSTANTS - Synced with main KPI Center Performance page
# =============================================================================

KPI_TYPES = ['TERRITORY', 'VERTICAL', 'BRAND', 'INTERNAL']

# v2.8.1: Sentinel value for "ALL" selection in multiselect filters
ALL_CENTERS = -1

KPI_TYPE_ICONS = {
    'TERRITORY': '🌍',
    'VERTICAL': '📊',
    'BRAND': '🏷️',
    'INTERNAL': '🏢'
}

KPI_ICONS = {
    'revenue': '💰',
    'gross_profit': '📈',
    'gross_profit_1': '📊',
    'gp1': '📊',
    'num_new_customers': '👥',
    'num_new_products': '📦',
    'new_business_revenue': '💼',
}


# =============================================================================
# HELPER FUNCTIONS - Consistent with main page formatting
# =============================================================================

def format_currency(value: float, decimals: int = 0) -> str:
    """Format value as USD currency - same pattern as main page."""
    if pd.isna(value) or value == 0:
        return "$0"
    if decimals > 0:
        return f"${value:,.{decimals}f}"
    return f"${value:,.0f}"


def format_product_display(product_name: str, pt_code: str = None, package_size: str = None, brand: str = None, include_brand: bool = False) -> str:
    """
    Format product for display.
    
    For DataTable fallback: "code | name (package_size)" - matches SQL view format
    For Form Header (include_brand=True): "code | name | package_size (brand)"
    
    Args:
        product_name: Product name
        pt_code: Product code
        package_size: Package size
        brand: Brand name
        include_brand: If True, append brand at end. Default False to match SQL view.
    """
    parts = []
    if pt_code and str(pt_code).strip() and str(pt_code).strip() != 'None':
        parts.append(str(pt_code).strip())
    if product_name and str(product_name).strip():
        parts.append(str(product_name).strip())
    
    # Package size format depends on include_brand
    pkg = str(package_size).strip() if package_size and str(package_size).strip() and str(package_size).strip() != 'None' else None
    
    if include_brand:
        # Form Header format: "code | name | package_size (brand)"
        if pkg:
            parts.append(pkg)
        result = " | ".join(parts) if parts else "N/A"
        if brand and str(brand).strip() and str(brand).strip() != 'None':
            result = f"{result} ({brand})"
    else:
        # SQL View format: "code | name (package_size)"
        result = " | ".join(parts) if parts else "N/A"
        if pkg:
            result = f"{result} ({pkg})"
    
    return result


def format_customer_display(customer_name: str, company_code: str = None) -> str:
    """
    Format customer for display: "code | english_name".
    """
    parts = []
    if company_code and str(company_code).strip() and str(company_code).strip() != 'None':
        parts.append(str(company_code).strip())
    if customer_name and str(customer_name).strip():
        parts.append(str(customer_name).strip())
    
    return " | ".join(parts) if parts else "N/A"


def format_percentage(value: float, decimals: int = 0) -> str:
    """Format as percentage."""
    if pd.isna(value):
        return "0%"
    return f"{value:.{decimals}f}%"


def get_status_display(status: str) -> tuple:
    """Get status badge with icon and color."""
    status_map = {
        'ok': ('✅ OK', 'green'),
        'incomplete_split': ('⚠️ Under 100%', 'orange'),
        'over_100_split': ('🔴 Over 100%', 'red')
    }
    return status_map.get(status, (status, 'gray'))


def get_period_warning(valid_to) -> tuple:
    """
    Get period status: (icon, text, delta_color for st.metric).
    Returns tuple for use with st.metric delta_color.
    """
    if pd.isna(valid_to):
        return ("🟢", "No End Date", "off")
    
    try:
        valid_to_dt = pd.to_datetime(valid_to)
        days_until = (valid_to_dt - pd.Timestamp.now()).days
        
        if days_until < 0:
            return ("⚫", "EXPIRED", "inverse")
        elif days_until <= 7:
            return ("🔴", f"{days_until}d left", "inverse")
        elif days_until <= 30:
            return ("🟠", f"{days_until}d left", "off")
        else:
            return ("🟢", "Active", "normal")
    except:
        return ("❓", "Unknown", "off")


def is_approved_truthy(val) -> bool:
    """
    Check if is_approved value is truthy.
    
    Handles all possible representations from MySQL BIT(1):
    - bytes: b'\\x01' (True), b'\\x00' (False)
    - bool: True, False
    - int: 1, 0
    - str: '1', 'true', 'True'
    - None/NaN: False
    
    Args:
        val: Value from is_approved column
        
    Returns:
        bool: True if approved, False otherwise
    """
    if pd.isna(val) or val is None:
        return False
    
    # Handle bytes (MySQL BIT type)
    if isinstance(val, bytes):
        return val == b'\x01'
    
    # Handle bool
    if isinstance(val, bool):
        return val
    
    # Handle int/float
    if isinstance(val, (int, float)):
        return val == 1
    
    # Handle string
    if isinstance(val, str):
        return val.lower() in ('1', 'true', 'yes')
    
    # Fallback
    return bool(val)


# =============================================================================
# MAIN SETUP TAB FRAGMENT
# =============================================================================

@st.fragment
def setup_tab_fragment(
    kpi_center_ids: List[int] = None,
    active_filters: Dict = None
):
    """
    Main fragment for Setup tab with 3 sub-tabs.
    
    v2.10.0: Integrated with permissions.py for granular CRUD control
    
    Args:
        kpi_center_ids: List of selected KPI Center IDs from sidebar
        active_filters: Dict of active filters from sidebar
    """
    st.subheader("⚙️ KPI Center Configuration")
    
    # Get user context
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    user_role = st.session_state.get('user_role', 'viewer')
    
    # Initialize permission checker (v2.10.0)
    perms = get_permissions(user_role)
    
    # Check Setup Tab access
    if not perms.can_access_setup_tab:
        st.error(perms.get_denied_message())
        return
    
    # Initialize queries with user context
    setup_queries = SetupQueries(user_id=user_id)
    
    # Permission flags for UI rendering (v2.10.0)
    can_create = perms.can_create
    can_edit = perms.can_edit
    can_delete = perms.can_delete
    can_approve = perms.can_approve
    can_bulk = perms.can_bulk_operations
    can_manage_hierarchy = perms.can_manage_hierarchy
    
    # Show permission indicator (collapsible)
    with st.expander("🔐 Your Permissions", expanded=False):
        perm_cols = st.columns(6)
        perm_cols[0].metric("Create", "✅" if can_create else "❌")
        perm_cols[1].metric("Edit", "✅" if can_edit else "❌")
        perm_cols[2].metric("Delete", "✅" if can_delete else "❌")
        perm_cols[3].metric("Approve", "✅" if can_approve else "❌")
        perm_cols[4].metric("Bulk Ops", "✅" if can_bulk else "❌")
        perm_cols[5].metric("Hierarchy", "✅" if can_manage_hierarchy else "❌")
    
    # Get year from filters
    current_year = active_filters.get('year', date.today().year) if active_filters else date.today().year
    
    # Get issue counts for tab badges
    split_stats = setup_queries.get_split_summary_stats()
    split_critical = split_stats.get('over_100_count', 0)
    
    assignment_issues = setup_queries.get_assignment_issues_summary(current_year)
    assign_critical = assignment_issues.get('no_assignment_count', 0) + assignment_issues.get('weight_issues_count', 0)
    
    # Dynamic tab names with badges
    split_tab_name = f"📋 Split Rules{' 🔴' if split_critical > 0 else ''}"
    assign_tab_name = f"🎯 KPI Assignments{' ⚠️' if assign_critical > 0 else ''}"
    
    # Create 3 sub-tabs (Validation merged into Split Rules & Assignments)
    tab1, tab2, tab3 = st.tabs([
        split_tab_name,
        assign_tab_name, 
        "🌳 Hierarchy"
    ])
    
    with tab1:
        split_rules_section(
            setup_queries=setup_queries,
            kpi_center_ids=kpi_center_ids,
            can_create=can_create,
            can_edit=can_edit,
            can_delete=can_delete,
            can_approve=can_approve,
            can_bulk=can_bulk
        )
    
    with tab2:
        kpi_assignments_section(
            setup_queries=setup_queries,
            kpi_center_ids=kpi_center_ids,
            can_create=can_create,
            can_edit=can_edit,
            can_delete=can_delete,
            current_year=current_year
        )
    
    with tab3:
        hierarchy_section(
            setup_queries=setup_queries,
            can_edit=can_manage_hierarchy  # Only admin can manage hierarchy
        )


# =============================================================================
# SPLIT RULES SECTION (v2.10.1 - Removed @st.fragment, called from parent fragment)
# =============================================================================

def split_rules_section(
    setup_queries: SetupQueries,
    kpi_center_ids: List[int] = None,
    can_create: bool = False,
    can_edit: bool = False,
    can_delete: bool = False,
    can_approve: bool = False,
    can_bulk: bool = False
):
    """
    Split Rules sub-tab with CRUD operations and comprehensive filters.
    
    v2.10.0: Updated with granular permissions (can_create, can_edit, can_delete, can_approve, can_bulk)
    v2.6.0: Added comprehensive filter system with 5 filter groups:
    - Period: Year, Period Type, Date Range
    - Entity: KPI Type, Brand, Customer/Product Search
    - Attributes: Split % Range, Status, Approval
    - Audit: Created By, Approved By, Date Range
    - System: Show Deleted, Reset
    """
    
    # =========================================================================
    # HELPER: Build query params from filter state
    # =========================================================================
    def get_current_filter_params():
        """Build query params from current filter state."""
        params = {}  # No default limit - show all matching data
        
        # Period filters
        period_type = st.session_state.get('split_period_type', 'full_year')
        period_year = st.session_state.get('split_period_year', date.today().year)
        
        if period_type == 'ytd':
            params['period_start'] = date(period_year, 1, 1)
            params['period_end'] = date.today()
        elif period_type == 'full_year':
            params['period_year'] = period_year
        elif period_type == 'custom':
            custom_start = st.session_state.get('split_period_start')
            custom_end = st.session_state.get('split_period_end')
            if custom_start:
                params['period_start'] = custom_start
            if custom_end:
                params['period_end'] = custom_end
        # 'all' = no period filter
        
        # Entity filters
        # v2.8.1: KPI Type is now required (no 'All' option)
        kpi_type = st.session_state.get('split_kpi_type_filter', 'TERRITORY')
        params['kpi_type'] = kpi_type
        
        # v2.8.1: KPI Center filter with ALL sentinel handling
        kpi_center_filter = st.session_state.get('split_kpi_center_filter', [])
        # Filter out ALL sentinel - if ALL selected, don't filter by kpi_center
        actual_centers = [c for c in kpi_center_filter if c != ALL_CENTERS]
        if actual_centers:
            params['kpi_center_ids'] = actual_centers
        # Note: If ALL is selected (or empty), no kpi_center_ids filter = all centers
        
        brand_filter = st.session_state.get('split_brand_filter', [])
        if brand_filter:
            params['brand_ids'] = brand_filter
        
        # v2.8.0: Customer & Product multiselect filters
        customer_filter = st.session_state.get('split_customer_filter', [])
        if customer_filter:
            params['customer_ids'] = customer_filter
        
        product_filter = st.session_state.get('split_product_filter', [])
        if product_filter:
            params['product_ids'] = product_filter
        
        # Rule attribute filters
        status_filter = st.session_state.get('split_status_filter')
        if status_filter and status_filter != 'all':
            params['status_filter'] = status_filter
        
        approval_filter = st.session_state.get('split_approval_filter')
        if approval_filter and approval_filter != 'all':
            params['approval_filter'] = approval_filter
        
        split_min = st.session_state.get('split_pct_min')
        split_max = st.session_state.get('split_pct_max')
        if split_min is not None and split_min > 0:
            params['split_min'] = split_min
        if split_max is not None and split_max < 100:
            params['split_max'] = split_max
        
        # Audit filters
        created_by = st.session_state.get('split_created_by_filter')
        if created_by and created_by > 0:
            params['created_by_user_id'] = created_by
        
        approved_by = st.session_state.get('split_approved_by_filter')
        if approved_by and approved_by > 0:
            params['approved_by_user_id'] = approved_by
        
        created_from = st.session_state.get('split_created_date_from')
        created_to = st.session_state.get('split_created_date_to')
        if created_from:
            params['created_date_from'] = created_from
        if created_to:
            params['created_date_to'] = created_to
        
        # v2.8.0: Modified date filters
        modified_from = st.session_state.get('split_modified_date_from')
        modified_to = st.session_state.get('split_modified_date_to')
        if modified_from:
            params['modified_date_from'] = modified_from
        if modified_to:
            params['modified_date_to'] = modified_to
        
        # System filters
        include_deleted = st.session_state.get('split_show_deleted', False)
        params['include_deleted'] = include_deleted
        
        return params
    
    # =========================================================================
    # COMPREHENSIVE FILTERS (v2.6.0)
    # =========================================================================
    with st.expander("🔍 Filters", expanded=True):
        
        # ---------------------------------------------------------------------
        # ROW 1: Period Filters
        # ---------------------------------------------------------------------
        st.markdown("##### 📅 Validity Period")
        
        p_col1, p_col2, p_col3, p_col4 = st.columns([1, 1, 1, 1])
        
        with p_col1:
            # Get available years
            available_years = setup_queries.get_split_rule_years()
            current_year = date.today().year
            
            period_year = st.selectbox(
                "Year",
                options=available_years,
                index=available_years.index(current_year) if current_year in available_years else 0,
                key="split_period_year"
            )
        
        with p_col2:
            period_type_options = {
                'ytd': f'📊 YTD {period_year}',
                'full_year': f'📅 Full Year {period_year}',
                'custom': '🔧 Custom Range',
                'all': '📋 All Periods'
            }
            period_type = st.selectbox(
                "Period Type",
                options=list(period_type_options.keys()),
                format_func=lambda x: period_type_options[x],
                index=1,  # Default: Full Year
                key="split_period_type"
            )
        
        with p_col3:
            # Custom date range (only enabled when period_type == 'custom')
            default_start = date(period_year, 1, 1)
            period_start = st.date_input(
                "From",
                value=default_start,
                disabled=(period_type != 'custom'),
                key="split_period_start"
            )
        
        with p_col4:
            default_end = date(period_year, 12, 31)
            period_end = st.date_input(
                "To",
                value=default_end,
                disabled=(period_type != 'custom'),
                key="split_period_end"
            )
        
        st.divider()
        
        # ---------------------------------------------------------------------
        # ROW 2: Entity Filters (v2.8.1 - Single KPI Type, Smart ALL selection)
        # ---------------------------------------------------------------------
        st.markdown("##### 🏢 Entity Filters")
        
        e_col1, e_col2, e_col3, e_col4 = st.columns(4)
        
        with e_col1:
            # v2.8.1: Single select KPI Type, default TERRITORY
            kpi_type_filter = st.selectbox(
                "KPI Type",
                options=KPI_TYPES,
                index=0,  # Default: TERRITORY
                format_func=lambda x: f"{KPI_TYPE_ICONS.get(x, '📁')} {x}",
                key="split_kpi_type_filter"
            )
        
        with e_col2:
            # v2.8.1: KPI Center multiselect with ALL option
            # Get centers filtered by selected KPI Type
            centers_df = setup_queries.get_kpi_centers_for_dropdown(kpi_type=kpi_type_filter)
            center_ids = centers_df['kpi_center_id'].tolist() if not centers_df.empty else []
            
            # Build options: ALL sentinel + individual centers
            center_options = [ALL_CENTERS] + center_ids  # ALL_CENTERS defined in constants
            
            def format_center(x):
                if x == ALL_CENTERS:
                    return "🌐 ALL"
                if not centers_df.empty and x in centers_df['kpi_center_id'].values:
                    return centers_df[centers_df['kpi_center_id'] == x]['kpi_center_name'].iloc[0]
                return str(x)
            
            # v2.8.1: Smart ALL selection logic
            # Get current selection
            current_selection = st.session_state.get('split_kpi_center_filter', None)
            prev_selection = st.session_state.get('_prev_kpi_center_filter', None)
            
            # Initialize if first time
            if current_selection is None:
                current_selection = [ALL_CENTERS]
                st.session_state['split_kpi_center_filter'] = current_selection
                prev_selection = []
            
            # Detect what changed and apply mutual exclusion logic
            needs_rerun = False
            if current_selection != prev_selection and prev_selection is not None:
                # Something changed
                newly_added = set(current_selection) - set(prev_selection)
                
                if ALL_CENTERS in newly_added and len(current_selection) > 1:
                    # ALL was just added - clear others, keep only ALL
                    st.session_state['split_kpi_center_filter'] = [ALL_CENTERS]
                    needs_rerun = True
                elif ALL_CENTERS in current_selection and len(newly_added) > 0 and ALL_CENTERS not in newly_added:
                    # Individual center was added while ALL was selected - remove ALL
                    st.session_state['split_kpi_center_filter'] = [x for x in current_selection if x != ALL_CENTERS]
                    needs_rerun = True
            
            # Save current as prev BEFORE widget renders
            st.session_state['_prev_kpi_center_filter'] = list(st.session_state.get('split_kpi_center_filter', [ALL_CENTERS]))
            
            if needs_rerun:
                st.rerun(scope="fragment")
            
            kpi_center_filter = st.multiselect(
                "KPI Center",
                options=center_options,
                format_func=format_center,
                key="split_kpi_center_filter",
                help="Select ALL or specific centers"
            )
        
        with e_col3:
            # Brand filter (multi-select)
            brands_df = setup_queries.get_brands_for_dropdown()
            brand_options = brands_df['brand_id'].tolist() if not brands_df.empty else []
            
            brand_filter = st.multiselect(
                "Brand",
                options=brand_options,
                format_func=lambda x: brands_df[brands_df['brand_id'] == x]['brand_name'].iloc[0] if not brands_df.empty else str(x),
                placeholder="All Brands",
                key="split_brand_filter"
            )
        
        with e_col4:
            # v2.8.0: Customer multiselect
            customers_df = setup_queries.get_customers_for_dropdown()
            customer_options = customers_df['customer_id'].tolist() if not customers_df.empty else []
            
            customer_filter = st.multiselect(
                "Customer",
                options=customer_options,
                format_func=lambda x: f"{customers_df[customers_df['customer_id'] == x]['company_code'].iloc[0]} | {customers_df[customers_df['customer_id'] == x]['customer_name'].iloc[0]}" if not customers_df.empty and x in customers_df['customer_id'].values else str(x),
                placeholder="All Customers",
                key="split_customer_filter",
                help="Filter by customer"
            )
        
        # Row 2b: Product filter (full width for better UX with long product names)
        products_df = setup_queries.get_products_for_dropdown()
        product_options = products_df['product_id'].tolist() if not products_df.empty else []
        
        product_filter = st.multiselect(
            "Product",
            options=product_options,
            format_func=lambda x: f"{products_df[products_df['product_id'] == x]['pt_code'].iloc[0]} | {products_df[products_df['product_id'] == x]['product_name'].iloc[0]}" if not products_df.empty and x in products_df['product_id'].values else str(x),
            placeholder="All Products",
            key="split_product_filter",
            help="Filter by product"
        )
        
        st.divider()
        
        # ---------------------------------------------------------------------
        # ROW 3: Rule Attributes
        # ---------------------------------------------------------------------
        st.markdown("##### 📊 Rule Attributes")
        
        r_col1, r_col2, r_col3, r_col4 = st.columns(4)
        
        with r_col1:
            split_min = st.number_input(
                "Split % Min",
                min_value=0,
                max_value=100,
                value=0,
                step=10,
                key="split_pct_min"
            )
        
        with r_col2:
            split_max = st.number_input(
                "Split % Max",
                min_value=0,
                max_value=100,
                value=100,
                step=10,
                key="split_pct_max"
            )
        
        with r_col3:
            status_options = {
                'all': '📋 All Status',
                'ok': '✅ OK (=100%)',
                'incomplete_split': '⚠️ Under 100%',
                'over_100_split': '🔴 Over 100%'
            }
            status_filter = st.selectbox(
                "Split Status",
                options=list(status_options.keys()),
                format_func=lambda x: status_options[x],
                key="split_status_filter"
            )
        
        with r_col4:
            approval_options = {
                'all': '📋 All',
                'approved': '✅ Approved',
                'pending': '⏳ Pending'
            }
            approval_filter = st.selectbox(
                "Approval Status",
                options=list(approval_options.keys()),
                format_func=lambda x: approval_options[x],
                key="split_approval_filter"
            )
        
        st.divider()
        
        # ---------------------------------------------------------------------
        # ROW 4: Audit Trail Filters (v2.8.0 - Added Modified dates)
        # ---------------------------------------------------------------------
        st.markdown("##### 👤 Audit Trail")
        
        # Get users for dropdown
        users_df = setup_queries.get_users_for_dropdown()
        creator_options = [(0, "All Creators")] + [
            (row['user_id'], f"{row['full_name']} ({row['username']})")
            for _, row in users_df.iterrows()
        ] if not users_df.empty else [(0, "All Creators")]
        
        approver_options = [(0, "All Approvers")] + [
            (row['user_id'], f"{row['full_name']} ({row['username']})")
            for _, row in users_df.iterrows()
        ] if not users_df.empty else [(0, "All Approvers")]
        
        a_col1, a_col2, a_col3, a_col4 = st.columns(4)
        
        with a_col1:
            created_by_filter = st.selectbox(
                "Created By",
                options=[u[0] for u in creator_options],
                format_func=lambda x: next((u[1] for u in creator_options if u[0] == x), "All"),
                key="split_created_by_filter"
            )
        
        with a_col2:
            approved_by_filter = st.selectbox(
                "Approved By",
                options=[u[0] for u in approver_options],
                format_func=lambda x: next((u[1] for u in approver_options if u[0] == x), "All"),
                key="split_approved_by_filter"
            )
        
        with a_col3:
            created_date_from = st.date_input(
                "Created From",
                value=None,
                key="split_created_date_from"
            )
        
        with a_col4:
            created_date_to = st.date_input(
                "Created To",
                value=None,
                key="split_created_date_to"
            )
        
        # v2.8.0: Modified date filters row
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        
        with m_col1:
            modified_date_from = st.date_input(
                "Modified From",
                value=None,
                key="split_modified_date_from"
            )
        
        with m_col2:
            modified_date_to = st.date_input(
                "Modified To",
                value=None,
                key="split_modified_date_to"
            )
        
        # Empty columns for alignment
        with m_col3:
            pass
        with m_col4:
            pass
        
        st.divider()
        
        # ---------------------------------------------------------------------
        # ROW 5: System Filters & Actions (v2.8.0)
        # ---------------------------------------------------------------------
        st.markdown("##### ⚙️ System")
        
        sys_col1, sys_col2, sys_col3 = st.columns([2, 1, 1])
        
        with sys_col1:
            show_deleted = st.checkbox(
                "🗑️ Show deleted rules",
                value=False,
                key="split_show_deleted",
                help="Include soft-deleted rules (delete_flag = 1)"
            )
        
        with sys_col2:
            if st.button("🔄 Reset Filters", use_container_width=True):
                # Reset all filter keys (v2.8.1 - updated list)
                keys_to_reset = [
                    'split_period_year', 'split_period_type', 'split_period_start', 'split_period_end',
                    'split_kpi_type_filter', 'split_kpi_center_filter', '_prev_kpi_center_filter',
                    'split_brand_filter', 'split_customer_filter', 'split_product_filter',
                    'split_pct_min', 'split_pct_max', 'split_status_filter', 'split_approval_filter',
                    'split_created_by_filter', 'split_approved_by_filter', 
                    'split_created_date_from', 'split_created_date_to',
                    'split_modified_date_from', 'split_modified_date_to',
                    'split_show_deleted'
                ]
                for key in keys_to_reset:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun(scope="fragment")
        
        with sys_col3:
            # v2.8.1: Updated filter count calculation
            # KPI Center: count as active only if specific centers selected (not ALL)
            kpi_center_active = len([c for c in kpi_center_filter if c != ALL_CENTERS]) > 0
            
            active_filter_count = sum([
                period_type != 'all',
                kpi_type_filter != 'TERRITORY',  # v2.8.1: Only count if not default
                kpi_center_active,  # v2.8.1: Only count if specific centers selected
                len(brand_filter) > 0,
                len(customer_filter) > 0,
                len(product_filter) > 0,
                split_min > 0,
                split_max < 100,
                status_filter != 'all',
                approval_filter != 'all',
                created_by_filter > 0,
                approved_by_filter > 0,
                created_date_from is not None,
                created_date_to is not None,
                modified_date_from is not None,
                modified_date_to is not None,
                show_deleted
            ])
            st.metric("Active Filters", active_filter_count)
    
    # =========================================================================
    # GET FILTER PARAMS FOR SUMMARY & DATA
    # =========================================================================
    query_params = get_current_filter_params()
    
    # =========================================================================
    # SUMMARY METRICS (sync with filters)
    # =========================================================================
    stats = setup_queries.get_split_summary_stats(
        period_year=query_params.get('period_year'),
        period_start=query_params.get('period_start'),
        period_end=query_params.get('period_end'),
        include_deleted=query_params.get('include_deleted', False)
    )
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="Total Rules",
            value=f"{stats['total_rules']:,}",
            help="Total split rules matching current filters"
        )
    with col2:
        st.metric(
            label="✅ OK",
            value=f"{stats['ok_count']:,}",
            delta=f"{stats['ok_count']/max(stats['total_rules'],1)*100:.0f}%" if stats['total_rules'] > 0 else None,
            delta_color="off",
            help="Rules where total split = 100%"
        )
    with col3:
        st.metric(
            label="⚠️ Under 100%",
            value=f"{stats['incomplete_count']:,}",
            delta_color="off",
            help="Rules where total split < 100%"
        )
    with col4:
        st.metric(
            label="🔴 Over 100%",
            value=f"{stats['over_100_count']:,}",
            delta_color="off",
            help="Rules where total split > 100% - needs fix!"
        )
    with col5:
        st.metric(
            label="⏳ Pending",
            value=f"{stats['pending_count']:,}",
            help="Rules awaiting approval"
        )
    
    st.divider()
    
    # =========================================================================
    # TOOLBAR (v2.10.0: Uses can_create permission for Add button)
    # =========================================================================
    if can_create:
        # Store context for dialog to access
        st.session_state['_split_dialog_can_approve'] = can_approve
        
        if st.button("➕ Add Split Rule", type="primary"):
            _add_split_rule_dialog()
    elif not can_edit:
        # Show read-only notice for users without any write permission
        st.info("👁️ View-only mode. You don't have permission to create or edit split rules.")
    
    # =========================================================================
    # v2.9.0: Edit form removed - now using dialog (_edit_split_rule_dialog)
    # Dialog is called directly from Edit button in _render_split_data_table
    # =========================================================================
    
    # =========================================================================
    # GET DATA WITH FILTERS
    # =========================================================================
    split_df = setup_queries.get_kpi_split_data(**query_params)
    
    if split_df.empty:
        st.info("No split rules found matching the filters")
        return
    
    # =========================================================================
    # RESULTS SUMMARY
    # =========================================================================
    period_desc = ""
    if period_type == 'ytd':
        period_desc = f"YTD {period_year} (Jan 1 - Today)"
    elif period_type == 'full_year':
        period_desc = f"Full Year {period_year}"
    elif period_type == 'custom':
        period_desc = f"{period_start} to {period_end}"
    else:
        period_desc = "All Periods"
    
    st.caption(f"📊 Showing **{len(split_df):,}** rules | Period: {period_desc}")
    
    # =========================================================================
    # v2.10.0: Call nested fragment with granular permissions
    # v2.11.0: Added can_create for Copy to New Period feature
    # =========================================================================
    _render_split_data_table(
        split_df=split_df,
        setup_queries=setup_queries,
        can_create=can_create,
        can_edit=can_edit,
        can_delete=can_delete,
        can_approve=can_approve,
        can_bulk=can_bulk
    )


# =============================================================================
# SPLIT DATA TABLE HELPER (v2.10.1 - Removed @st.fragment to fix nested fragment bug)
# =============================================================================

def _render_split_data_table(
    split_df: pd.DataFrame,
    setup_queries: SetupQueries,
    can_create: bool = False,
    can_edit: bool = False,
    can_delete: bool = False,
    can_approve: bool = False,
    can_bulk: bool = False
):
    """
    v2.11.0: Added can_create for Copy to New Period feature.
    v2.10.1: Removed @st.fragment decorator to fix nested fragment AssertionError.
             Row selection rerun now handled by parent fragment (split_rules_section).
    v2.10.0: Updated with granular permissions (can_edit, can_delete, can_approve, can_bulk)
    v2.8.2: Nested fragment for data table and action bar.
    
    Synced with Salesperson Performance pattern.
    """
    if split_df.empty:
        st.info("No split rules found matching the filters")
        return
    
    display_df = split_df.copy()
    
    # Format columns
    display_df['ID'] = display_df['kpi_center_split_id'].apply(lambda x: f"#{x}")
    
    display_df['Type'] = display_df['kpi_type'].apply(
        lambda x: f"{KPI_TYPE_ICONS.get(x, '📁')} {x}" if pd.notna(x) else ''
    )
    
    if 'customer_display' in display_df.columns:
        display_df['Customer'] = display_df['customer_display']
    else:
        display_df['Customer'] = display_df.apply(
            lambda r: format_customer_display(r.get('customer_name', ''), r.get('company_code', '')), 
            axis=1
        )
    
    if 'product_display' in display_df.columns:
        display_df['Product'] = display_df['product_display']
    else:
        display_df['Product'] = display_df.apply(
            lambda r: format_product_display(r['product_name'], r.get('pt_code'), r.get('package_size'), r.get('brand')), 
            axis=1
        )
    
    display_df['Split'] = display_df['split_percentage'].apply(lambda x: f"{x:.0f}%")
    
    display_df['Status'] = display_df['kpi_split_status'].apply(
        lambda x: get_status_display(x)[0]
    )
    
    # v2.7.3: Compute boolean column once for consistent BIT(1) handling
    display_df['_is_approved_bool'] = display_df['is_approved'].apply(is_approved_truthy)
    
    display_df['Approved'] = display_df.apply(
        lambda r: f"✅ {r.get('approved_by_name', '').strip()}" if r['_is_approved_bool'] else '⏳ Pending',
        axis=1
    )
    
    display_df['Created By'] = display_df['created_by_name'].fillna('').apply(lambda x: x.strip() if x else '-')
    
    # Get show_deleted from session state (safe reference)
    show_deleted_flag = st.session_state.get('split_show_deleted', False)
    
    # Add deleted indicator if showing deleted
    if show_deleted_flag and 'delete_flag' in display_df.columns:
        display_df['Deleted'] = display_df['delete_flag'].apply(lambda x: '🗑️' if x else '')
    
    # Build column list
    columns_to_show = [
        'ID', 'kpi_center_name', 'Type', 'Customer', 'Product', 'brand',
        'Split', 'effective_period', 'Status', 'Approved', 'Created By'
    ]
    if show_deleted_flag and 'delete_flag' in display_df.columns:
        columns_to_show.append('Deleted')
    
    # =========================================================================
    # INITIALIZE SELECTION STATE & CALCULATE TOTALS
    # =========================================================================
    if 'split_selected_ids' not in st.session_state:
        st.session_state['split_selected_ids'] = set()
    
    # Get current selection
    selected_ids = st.session_state.get('split_selected_ids', set())
    valid_selected = selected_ids & set(display_df['kpi_center_split_id'].tolist())
    selected_count = len(valid_selected)
    
    # v2.7.3: Calculate totals using pre-computed boolean column
    total_pending = (~display_df['_is_approved_bool']).sum()
    total_approved = display_df['_is_approved_bool'].sum()
    
    # Get IDs by approval status for quick selection
    pending_ids = set(display_df[~display_df['_is_approved_bool']]['kpi_center_split_id'].tolist())
    approved_ids = set(display_df[display_df['_is_approved_bool']]['kpi_center_split_id'].tolist())
    
    # Get approver info
    approver_user_id = st.session_state.get('user_id')  # users.id
    
    # =========================================================================
    # INSIGHTS + QUICK SELECTION (ABOVE DATA TABLE) - v2.7.2
    # =========================================================================
    if can_edit and not split_df.empty:
        ins_col1, ins_col2, ins_col3, ins_col4 = st.columns([2, 1, 1, 1])
        
        with ins_col1:
            # Insights display
            st.markdown(f"📋 **{total_pending:,}** pending · ✅ **{total_approved:,}** approved")
        
        with ins_col2:
            if st.button("☑️ Select All Pending", use_container_width=True,
                        disabled=total_pending == 0,
                        help=f"Select all {total_pending} pending rules"):
                st.session_state['split_selected_ids'] = pending_ids
                st.rerun(scope="fragment")
        
        with ins_col3:
            if st.button("☑️ Select All Approved", use_container_width=True,
                        disabled=total_approved == 0,
                        help=f"Select all {total_approved} approved rules"):
                st.session_state['split_selected_ids'] = approved_ids
                st.rerun(scope="fragment")
        
        with ins_col4:
            if st.button("✖️ Clear", use_container_width=True,
                        disabled=selected_count == 0,
                        help="Clear selection"):
                st.session_state['split_selected_ids'] = set()
                st.rerun(scope="fragment")
    
    # =========================================================================
    # DATA TABLE WITH MULTI-SELECTION
    # =========================================================================
    
    # Add Select column
    display_df['Select'] = display_df['kpi_center_split_id'].isin(
        st.session_state.get('split_selected_ids', set())
    )
    
    # Move Select to front
    columns_with_select = ['Select'] + columns_to_show
    
    # Use data_editor for selection
    edited_df = st.data_editor(
        display_df[columns_with_select],
        hide_index=True,
        column_config={
            'Select': st.column_config.CheckboxColumn(
                '✓',
                width='small',
                help="Select for bulk actions"
            ),
            'ID': st.column_config.TextColumn('ID', width='small', disabled=True),
            'kpi_center_name': st.column_config.TextColumn('KPI Center', width='medium', disabled=True),
            'Type': st.column_config.TextColumn('Type', width='small', disabled=True),
            'Customer': st.column_config.TextColumn('Customer', width='large', disabled=True),
            'Product': st.column_config.TextColumn('Product', width='large', disabled=True),
            'brand': st.column_config.TextColumn('Brand', width='small', disabled=True),
            'Split': st.column_config.TextColumn('Split %', width='small', disabled=True),
            'effective_period': st.column_config.TextColumn('Period', width='medium', disabled=True),
            'Status': st.column_config.TextColumn('Status', width='small', disabled=True),
            'Approved': st.column_config.TextColumn('Approved', width='medium', disabled=True),
            'Created By': st.column_config.TextColumn('Created By', width='medium', disabled=True),
            'Deleted': st.column_config.TextColumn('🗑️', width='small', disabled=True),
        },
        use_container_width=True,
        key="split_data_editor_v2"
    )
    
    # Update selection state from editor
    if edited_df is not None and 'Select' in edited_df.columns:
        new_selected = set(display_df[edited_df['Select'] == True]['kpi_center_split_id'].tolist())
        if new_selected != st.session_state.get('split_selected_ids', set()):
            st.session_state['split_selected_ids'] = new_selected
            st.rerun(scope="fragment")
    
    # =========================================================================
    # BULK ACTIONS (BELOW DATA TABLE) - v2.10.0: Granular permission checks
    # =========================================================================
    if not split_df.empty and valid_selected:
        selected_df = display_df[display_df['kpi_center_split_id'].isin(valid_selected)]
        # v2.7.3: Use pre-computed boolean column for consistent BIT(1) handling
        selected_pending = (~selected_df['_is_approved_bool']).sum()
        selected_approved = selected_df['_is_approved_bool'].sum()
        
        with st.container(border=True):
            # Selection summary
            st.caption(f"📌 **{selected_count}** rules selected: {selected_pending} pending, {selected_approved} approved")
            
            # =================================================================
            # APPROVAL ACTIONS (Requires can_approve)
            # =================================================================
            if can_approve:
                appr_col1, appr_col2, appr_col3 = st.columns([1, 1, 2])
                
                with appr_col1:
                    if selected_pending > 0:
                        with st.popover(f"✅ Approve {selected_pending}", use_container_width=True):
                            st.warning(f"Approve **{selected_pending}** pending rules?")
                            if st.button("✅ Yes, Approve All", type="primary", 
                                        key="split_dt_bulk_approve", use_container_width=True):
                                pending_to_approve = selected_df[~selected_df['_is_approved_bool']]['kpi_center_split_id'].tolist()
                                result = setup_queries.approve_split_rules(
                                    rule_ids=pending_to_approve,
                                    approved_by=approver_user_id
                                )
                                if result['success']:
                                    st.session_state['split_selected_ids'] = set()
                                    st.toast(f"✅ Approved {result['count']} rules", icon="✅")
                                    st.rerun(scope="fragment")
                                else:
                                    st.error(result['message'])
                    else:
                        st.button("✅ Approve", disabled=True, use_container_width=True,
                                 help="No pending rules selected", key="split_dt_bulk_approve_dis")
                
                with appr_col2:
                    if selected_approved > 0:
                        with st.popover(f"⏳ Disapprove", use_container_width=True):
                            st.warning(f"Reset **{selected_approved}** rules to Pending?")
                            if st.button("⏳ Yes, Reset to Pending", type="primary",
                                        key="split_dt_bulk_disapprove", use_container_width=True):
                                approved_to_reset = selected_df[selected_df['_is_approved_bool']]['kpi_center_split_id'].tolist()
                                result = setup_queries.bulk_disapprove_split_rules(
                                    rule_ids=approved_to_reset,
                                    modified_by=approver_user_id
                                )
                                if result['success']:
                                    st.session_state['split_selected_ids'] = set()
                                    st.toast(f"⏳ Reset {result['count']} rules to Pending", icon="⏳")
                                    st.rerun(scope="fragment")
                                else:
                                    st.error(result['message'])
                    else:
                        st.button("⏳ Disapprove", disabled=True, use_container_width=True,
                                 help="No approved rules selected", key="split_dt_bulk_disapprove_dis")
            
            # =================================================================
            # BULK UPDATE ACTIONS (v2.10.0: Requires can_bulk AND can_edit)
            # =================================================================
            if can_bulk and can_edit:
                st.divider()
                st.caption("📝 Bulk Update Actions")
            
            upd_col1, upd_col2, upd_col3 = st.columns([1, 1, 2])
            
            # Bulk Update Period (v2.8.2: With validation preview)
            with upd_col1:
                with st.popover(f"📅 Update Period ({selected_count})", use_container_width=True):
                    st.markdown(f"**Set validity period for {selected_count} rules**")
                    
                    bulk_valid_from = st.date_input(
                        "Valid From",
                        value=date.today(),
                        key="split_bulk_valid_from"
                    )
                    bulk_valid_to = st.date_input(
                        "Valid To",
                        value=date(date.today().year, 12, 31),
                        key="split_bulk_valid_to"
                    )
                    
                    st.caption(f"📌 Will update: {bulk_valid_from} → {bulk_valid_to}")
                    
                    # v2.8.2: Validation preview with overlap check
                    selected_rule_ids = list(valid_selected)
                    period_impact = setup_queries.validate_bulk_period_impact(
                        rule_ids=selected_rule_ids,
                        valid_from=bulk_valid_from,
                        valid_to=bulk_valid_to
                    )
                    
                    # Show validation results
                    if period_impact['period_errors']:
                        for err in period_impact['period_errors']:
                            st.error(f"❌ {err}")
                    
                    if period_impact.get('period_warnings'):
                        for warn in period_impact['period_warnings']:
                            st.warning(f"⚠️ {warn}")
                    
                    if period_impact['overlap_count'] > 0:
                        st.error(f"❌ {period_impact['overlap_count']} rules will have overlapping periods")
                        with st.expander("🔍 View overlap details"):
                            for ow in period_impact['overlap_warnings'][:5]:
                                st.caption(
                                    f"• #{ow['rule_id']}: {ow['kpi_center_name']} - "
                                    f"{ow['overlap_count']} overlap(s)"
                                )
                            if period_impact['overlap_count'] > 5:
                                st.caption(f"... and {period_impact['overlap_count'] - 5} more")
                    
                    # Block if any errors or overlaps
                    can_proceed_period = period_impact['can_proceed']
                    
                    if can_proceed_period:
                        if not period_impact['period_errors'] and not period_impact['overlap_count']:
                            st.success("✅ No conflicts detected")
                        
                        if st.button("📅 Apply Period", type="primary", 
                                    key="split_bulk_update_period", use_container_width=True):
                            result = setup_queries.bulk_update_split_period(
                                rule_ids=selected_rule_ids,
                                valid_from=bulk_valid_from,
                                valid_to=bulk_valid_to,
                                modified_by=approver_user_id
                            )
                            if result['success']:
                                st.session_state['split_selected_ids'] = set()
                                st.toast(f"📅 Updated period for {result['count']} rules", icon="📅")
                                st.rerun(scope="fragment")
                            else:
                                st.error(result['message'])
                    else:
                        st.button("📅 Apply Period", type="primary", disabled=True,
                                 key="split_bulk_update_period_dis", use_container_width=True)
                        st.error("❌ Fix errors above before proceeding")
            
            # Bulk Update Split % (v2.8.1: With validation preview)
            with upd_col2:
                with st.popover(f"📊 Update Split % ({selected_count})", use_container_width=True):
                    st.markdown(f"**Set split % for {selected_count} rules**")
                    st.warning("⚠️ This sets the SAME percentage for ALL selected rules!")
                    
                    bulk_split_pct = st.number_input(
                        "Split %",
                        min_value=0.0,
                        max_value=100.0,
                        value=100.0,
                        step=5.0,
                        key="split_bulk_split_pct"
                    )
                    
                    # v2.8.1: Impact preview
                    selected_rule_ids = list(valid_selected)
                    split_impact = setup_queries.validate_bulk_split_impact(
                        rule_ids=selected_rule_ids,
                        new_split_percentage=float(bulk_split_pct)
                    )
                    
                    # Show impact summary
                    imp_col1, imp_col2, imp_col3 = st.columns(3)
                    with imp_col1:
                        st.metric("✅ OK", split_impact['will_be_ok'], help="Will have total = 100%")
                    with imp_col2:
                        st.metric("⚠️ Under", split_impact['will_be_under'], help="Will have total < 100%")
                    with imp_col3:
                        delta_color = "inverse" if split_impact['will_be_over'] > 0 else "off"
                        st.metric(
                            "🔴 Over", 
                            split_impact['will_be_over'], 
                            help="Will have total > 100%",
                            delta="BLOCKED" if split_impact['will_be_over'] > 0 else None,
                            delta_color=delta_color
                        )
                    
                    # Show detailed issues if any over 100%
                    if split_impact['will_be_over'] > 0:
                        over_rules = [d for d in split_impact['details'] if d['status'] == 'over']
                        with st.expander(f"🔴 View {len(over_rules)} over-allocated combos"):
                            for r in over_rules[:5]:
                                st.caption(f"• {r['kpi_type']}: {r['customer_name'][:20]}... | {r['product_name'][:20]}... → {r['new_total']:.0f}%")
                            if len(over_rules) > 5:
                                st.caption(f"... and {len(over_rules) - 5} more")
                        
                        st.error(f"❌ Cannot proceed: {split_impact['will_be_over']} combo(s) would exceed 100%")
                    
                    # Block if any over 100%
                    can_bulk_update = split_impact['can_proceed']
                    
                    if can_bulk_update:
                        if st.button("📊 Update Split %", type="primary",
                                    key="split_bulk_update_split", use_container_width=True):
                            result = setup_queries.bulk_update_split_percentage(
                                rule_ids=selected_rule_ids,
                                split_percentage=bulk_split_pct,
                                modified_by=approver_user_id
                            )
                            if result['success']:
                                st.session_state['split_selected_ids'] = set()
                                st.toast(f"📊 Updated split % for {result['count']} rules", icon="📊")
                                st.rerun(scope="fragment")
                            else:
                                st.error(result['message'])
                    else:
                        st.button("📊 Update Split %", type="primary", disabled=True,
                                 key="split_bulk_update_split_dis", use_container_width=True)
            
            # =================================================================
            # EDIT/DELETE ACTIONS (v2.10.0: Granular permission checks)
            # =================================================================
            if can_edit or can_delete:
                st.divider()
            
            if selected_count == 1:
                # Single selection: Edit + Delete + Copy
                selected_rule_id = list(valid_selected)[0]
                selected_row = selected_df.iloc[0]
                
                st.caption(f"📌 Rule **#{selected_rule_id}** | {selected_row['kpi_center_name']} | {selected_row['Customer']}")
                
                edit_col1, edit_col2, edit_col3, edit_col4 = st.columns([1, 1, 1, 1])
                
                with edit_col1:
                    # v2.10.0: Check can_edit permission
                    if can_edit:
                        # v2.9.0: Open dialog instead of inline form
                        if st.button("✏️ Edit", use_container_width=True, type="secondary", key="split_dt_edit"):
                            st.session_state['_edit_split_rule_id'] = selected_rule_id
                            _edit_split_rule_dialog()
                    else:
                        st.button("✏️ Edit", disabled=True, use_container_width=True, 
                                 help="You don't have edit permission", key="split_dt_edit_disabled")
                
                with edit_col2:
                    # v2.10.0: Check can_delete permission
                    if can_delete:
                        with st.popover("🗑️ Delete", use_container_width=True):
                            st.warning(f"Delete rule **#{selected_rule_id}**?")
                            if st.button("🗑️ Yes, Delete", type="primary", 
                                        key="split_dt_confirm_delete", use_container_width=True):
                                result = setup_queries.delete_split_rule(selected_rule_id)
                                if result['success']:
                                    st.session_state['split_selected_ids'] = set()
                                    st.toast("Rule deleted", icon="🗑️")
                                    st.rerun(scope="fragment")
                                else:
                                    st.error(result['message'])
                    else:
                        st.button("🗑️ Delete", disabled=True, use_container_width=True,
                                 help="You don't have delete permission", key="split_dt_delete_disabled")
                
                with edit_col3:
                    # v2.11.0: Copy to New Period (requires can_create)
                    if can_create:
                        if st.button("📋 Copy to New Period", use_container_width=True, key="split_dt_copy"):
                            st.session_state['_copy_to_period_rule_ids'] = [selected_rule_id]
                            st.session_state['_copy_dialog_can_approve'] = can_approve
                            _copy_to_period_dialog()
                    else:
                        st.button("📋 Copy", disabled=True, use_container_width=True,
                                 help="You don't have create permission", key="split_dt_copy_disabled")
            else:
                # Multi selection: Bulk Delete + Copy (requires can_bulk)
                if can_bulk:
                    bulk_col1, bulk_col2, bulk_col3 = st.columns([1, 1, 2])
                    
                    with bulk_col1:
                        if can_delete:
                            with st.popover(f"🗑️ Delete {selected_count} Rules", use_container_width=True):
                                st.error(f"⚠️ Delete **{selected_count}** rules?")
                                st.caption("This action cannot be undone easily.")
                                
                                if st.button("🗑️ Yes, Delete All", type="primary",
                                            key="split_bulk_delete", use_container_width=True):
                                    result = setup_queries.delete_split_rules_bulk(list(valid_selected))
                                    if result['success']:
                                        st.session_state['split_selected_ids'] = set()
                                        st.toast(f"🗑️ Deleted {result['count']} rules", icon="🗑️")
                                        st.rerun(scope="fragment")
                                    else:
                                        st.error(result['message'])
                        else:
                            st.button(f"🗑️ Delete {selected_count}", disabled=True, use_container_width=True,
                                     help="You don't have delete permission", key="split_bulk_delete_disabled")
                    
                    with bulk_col2:
                        # v2.11.0: Bulk Copy to New Period (requires can_create)
                        if can_create:
                            if st.button(f"📋 Copy {selected_count} to New Period", use_container_width=True, 
                                        key="split_bulk_copy"):
                                st.session_state['_copy_to_period_rule_ids'] = list(valid_selected)
                                st.session_state['_copy_dialog_can_approve'] = can_approve
                                _copy_to_period_dialog()
                        else:
                            st.button(f"📋 Copy {selected_count}", disabled=True, use_container_width=True,
                                     help="You don't have create permission", key="split_bulk_copy_disabled")


# =============================================================================
# HELPER: CURRENT SPLIT STRUCTURE (v2.9.0 - Synced with Salesperson)
# =============================================================================

def _render_current_split_structure(
    setup_queries: SetupQueries,
    customer_id: int,
    product_id: int,
    kpi_type: str = None,
    exclude_rule_id: int = None,
    expanded: bool = True
):
    """
    Render current split structure insights for a customer/product combo.
    
    v2.9.0: NEW - Synced with Salesperson Performance module.
    v2.9.1: FIX - Use same query as validation for consistency.
    
    Shows:
    - Summary metrics: Other Allocations, Other Rules, Approved %, Pending %
    - Allocation Breakdown: Table of all KPI Centers with their splits
    
    Args:
        setup_queries: SetupQueries instance
        customer_id: Customer ID
        product_id: Product ID
        kpi_type: Optional KPI type filter (TERRITORY, VERTICAL, etc.)
        exclude_rule_id: Rule ID to exclude (for edit mode)
        expanded: Whether expander starts expanded
    """
    if not customer_id or not product_id:
        return
    
    # v2.9.1: Use same query as validation for consistency
    # get_split_by_customer_product is used by validate_split_percentage
    structure_df = setup_queries.get_split_by_customer_product(
        customer_id=customer_id,
        product_id=product_id,
        kpi_type=kpi_type,
        exclude_rule_id=exclude_rule_id
    )
    
    # Calculate summary from structure_df
    if structure_df.empty:
        total_split = 0.0
        rule_count = 0
        approved_split = 0.0
        pending_split = 0.0
    else:
        total_split = float(structure_df['split_percentage'].sum())
        rule_count = len(structure_df)
        # Handle BIT(1) is_approved column
        structure_df['_is_approved_bool'] = structure_df['is_approved'].apply(is_approved_truthy)
        approved_split = float(structure_df[structure_df['_is_approved_bool']]['split_percentage'].sum())
        pending_split = float(structure_df[~structure_df['_is_approved_bool']]['split_percentage'].sum())
    
    type_label = f" ({kpi_type})" if kpi_type else ""
    
    with st.expander(f"📊 Current Split Structure{type_label}", expanded=expanded):
        # Summary metrics row
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        
        with m_col1:
            st.metric(
                "Other Allocations",
                f"{total_split:.0f}%",
                help="Total split % from other rules"
            )
        
        with m_col2:
            st.metric(
                "Other Rules",
                f"{rule_count}",
                help="Number of other active rules"
            )
        
        with m_col3:
            st.metric(
                "Approved",
                f"{approved_split:.0f}%",
                help="Total from approved rules"
            )
        
        with m_col4:
            st.metric(
                "Pending",
                f"{pending_split:.0f}%",
                help="Total from pending rules"
            )
        
        # Allocation Breakdown
        if not structure_df.empty:
            st.markdown("##### 📋 Allocation Breakdown")
            
            for _, row in structure_df.iterrows():
                # Progress bar style display
                pct = float(row['split_percentage'])
                kpc_name = row.get('kpi_center_name', 'Unknown')
                kpc_type = row.get('kpi_type', '')
                
                # Build period display
                valid_from = row.get('effective_from') or row.get('valid_from')
                valid_to = row.get('effective_to') or row.get('valid_to')
                if pd.notna(valid_from) and pd.notna(valid_to):
                    period = f"{pd.to_datetime(valid_from).strftime('%Y-%m-%d')} → {pd.to_datetime(valid_to).strftime('%Y-%m-%d')}"
                elif pd.notna(valid_from):
                    period = f"{pd.to_datetime(valid_from).strftime('%Y-%m-%d')} → No End"
                else:
                    period = "No dates"
                
                is_approved = is_approved_truthy(row.get('is_approved'))
                
                # Status icon
                approval_icon = "✅" if is_approved else "⏳"
                type_icon = KPI_TYPE_ICONS.get(kpc_type, '📁')
                
                col_name, col_bar, col_period, col_status = st.columns([2, 2, 2, 1])
                
                with col_name:
                    st.markdown(f"{type_icon} **{kpc_name}**")
                
                with col_bar:
                    st.progress(min(pct / 100, 1.0), text=f"{pct:.0f}%")
                
                with col_period:
                    st.caption(f"📅 {period}")
                
                with col_status:
                    st.markdown(approval_icon)
        else:
            st.info("No other allocations for this combo")


# =============================================================================
# ADD SPLIT RULE DIALOG (v2.9.0 - With Current Structure Insights)
# =============================================================================

@st.dialog("➕ Add Split Rule", width="large")
def _add_split_rule_dialog():
    """
    Dialog for adding a new split rule.
    
    v2.9.0: Enhanced with Current Split Structure insights.
    v2.8.2: NEW - Converted from inline form to dialog for cleaner UX.
    """
    # Get context from session state
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    can_approve = st.session_state.get('_split_dialog_can_approve', False)
    
    # Initialize queries
    setup_queries = SetupQueries(user_id=user_id)
    
    # Form layout
    col1, col2 = st.columns(2)
    
    with col1:
        # Customer selection
        customers_df = setup_queries.get_customers_for_dropdown()
        
        if not customers_df.empty:
            customer_id = st.selectbox(
                "Customer *",
                options=customers_df['customer_id'].tolist(),
                format_func=lambda x: f"{customers_df[customers_df['customer_id'] == x]['customer_name'].iloc[0]} ({customers_df[customers_df['customer_id'] == x]['company_code'].iloc[0]})",
                key="dialog_customer_id"
            )
        else:
            customer_id = None
            st.caption("No customers found")
        
        # KPI Center selection
        centers_df = setup_queries.get_kpi_centers_for_dropdown()
        if not centers_df.empty:
            kpi_center_id = st.selectbox(
                "KPI Center *",
                options=centers_df['kpi_center_id'].tolist(),
                format_func=lambda x: f"{KPI_TYPE_ICONS.get(centers_df[centers_df['kpi_center_id'] == x]['kpi_type'].iloc[0], '📁')} {centers_df[centers_df['kpi_center_id'] == x]['kpi_center_name'].iloc[0]}",
                key="dialog_kpi_center_id"
            )
        else:
            kpi_center_id = None
    
    with col2:
        # Product selection
        products_df = setup_queries.get_products_for_dropdown()
        
        if not products_df.empty:
            def format_product_option(row):
                name = row['product_name'] or ''
                code = row['pt_code'] or ''
                pkg = row.get('package_size', '') or ''
                detail = " | ".join(filter(None, [code, pkg]))
                return f"{name} ({detail})" if detail else name
            
            product_id = st.selectbox(
                "Product *",
                options=products_df['product_id'].tolist(),
                format_func=lambda x: format_product_option(products_df[products_df['product_id'] == x].iloc[0]),
                key="dialog_product_id"
            )
        else:
            product_id = None
            st.caption("No products found")
        
        # Split percentage
        split_pct = st.number_input(
            "Split % *",
            min_value=0.0,
            max_value=100.0,
            value=100.0,
            step=5.0,
            key="dialog_split_pct"
        )
    
    # Period inputs
    col3, col4 = st.columns(2)
    with col3:
        valid_from = st.date_input("Valid From *", value=date.today(), key="dialog_valid_from")
    
    with col4:
        valid_to = st.date_input("Valid To *", value=date(date.today().year, 12, 31), key="dialog_valid_to")
    
    # =========================================================================
    # v2.9.0: CURRENT SPLIT STRUCTURE INSIGHTS
    # =========================================================================
    if customer_id and product_id and kpi_center_id and not centers_df.empty:
        selected_type = centers_df[centers_df['kpi_center_id'] == kpi_center_id]['kpi_type'].iloc[0]
        
        st.divider()
        _render_current_split_structure(
            setup_queries=setup_queries,
            customer_id=customer_id,
            product_id=product_id,
            kpi_type=selected_type,
            exclude_rule_id=None,
            expanded=False  # Start collapsed in Add mode
        )
    
    # =========================================================================
    # VALIDATION SECTION
    # =========================================================================
    st.divider()
    st.markdown("##### 🔍 Validation")
    
    validation_errors = []
    validation_warnings = []
    can_save = True
    
    # 1. Period Validation
    period_validation = setup_queries.validate_period(valid_from, valid_to)
    
    if not period_validation['is_valid']:
        for err in period_validation['errors']:
            validation_errors.append(f"📅 {err}")
        can_save = False
    
    for warn in period_validation.get('warnings', []):
        validation_warnings.append(f"📅 {warn}")
    
    # 2. Period Overlap Check
    if customer_id and product_id and kpi_center_id and valid_from and valid_to:
        overlap_check = setup_queries.check_period_overlap(
            customer_id=customer_id,
            product_id=product_id,
            kpi_center_id=kpi_center_id,
            valid_from=valid_from,
            valid_to=valid_to,
            exclude_rule_id=None
        )
        
        if overlap_check['has_overlap']:
            validation_errors.append(
                f"📅 Period overlaps with {overlap_check['overlap_count']} existing rule(s) for this KPI Center"
            )
            can_save = False
            
            with st.expander(f"🔍 View {overlap_check['overlap_count']} overlapping rules", expanded=False):
                for r in overlap_check['overlapping_rules']:
                    st.caption(f"• Rule #{r['rule_id']}: {r['split_percentage']:.0f}% ({r['period_display']})")
    
    # 3. Split Percentage Validation
    if customer_id and product_id and kpi_center_id and not centers_df.empty:
        selected_type = centers_df[centers_df['kpi_center_id'] == kpi_center_id]['kpi_type'].iloc[0]
        
        split_validation = setup_queries.validate_split_percentage(
            customer_id=customer_id,
            product_id=product_id,
            kpi_type=selected_type,
            new_percentage=split_pct,
            exclude_rule_id=None
        )
        
        # Display metrics
        val_col1, val_col2, val_col3 = st.columns(3)
        
        with val_col1:
            st.metric(
                "Current Total",
                f"{split_validation['current_total']:.0f}%",
                help=f"Total for {selected_type} type"
            )
        
        with val_col2:
            delta_color = "inverse" if split_validation['new_total'] > 100 else "off"
            st.metric(
                "After Save",
                f"{split_validation['new_total']:.0f}%",
                delta=f"+{split_pct:.0f}%",
                delta_color=delta_color
            )
        
        with val_col3:
            if split_validation['new_total'] == 100:
                st.success("✅ Perfect!")
            elif split_validation['new_total'] > 100:
                over_pct = split_validation['new_total'] - 100
                st.error(f"🔴 Over by {over_pct:.0f}%")
                validation_errors.append(
                    f"📊 Total split ({split_validation['new_total']:.0f}%) exceeds 100% for {selected_type}"
                )
                can_save = False
            else:
                st.warning(f"⚠️ {split_validation['remaining']:.0f}% remaining")
                validation_warnings.append(
                    f"📊 Under-allocated: {split_validation['remaining']:.0f}% remaining for {selected_type}"
                )
    
    # Display validation summary
    if validation_errors:
        for err in validation_errors:
            st.error(err)
    
    if validation_warnings and not validation_errors:
        for warn in validation_warnings:
            st.warning(warn)
    
    if not validation_errors and not validation_warnings:
        st.success("✅ All validations passed")
    
    # Approve checkbox (only for admins)
    st.divider()
    
    approve_on_create = False
    if can_approve:
        approve_on_create = st.checkbox(
            "✅ Approve this rule",
            value=True,
            key="dialog_approve_on_create",
            help="Automatically approve this rule upon creation"
        )
    
    # Button (Cancel removed - use dialog X button to close)
    if st.button("💾 Save", type="primary", use_container_width=True, disabled=not can_save):
        if not all([customer_id, product_id, kpi_center_id]):
            st.error("Please fill all required fields")
        else:
            result = setup_queries.create_split_rule(
                customer_id=customer_id,
                product_id=product_id,
                kpi_center_id=kpi_center_id,
                split_percentage=split_pct,
                valid_from=valid_from,
                valid_to=valid_to,
                is_approved=approve_on_create,
                approved_by=user_id if approve_on_create else None
            )
            
            if result['success']:
                st.toast("✅ Created successfully!", icon="✅")
                st.rerun()  # Close dialog and refresh
            else:
                st.error(result['message'])


# =============================================================================
# EDIT SPLIT RULE DIALOG (v2.9.0 - Modal with Current Structure Insights)
# =============================================================================

@st.dialog("✏️ Edit Split Rule", width="large")
def _edit_split_rule_dialog():
    """
    Dialog for editing an existing split rule.
    
    v2.9.0: NEW - Synced with Salesperson Performance module.
    
    Features:
    - Header with Rule ID, Customer, Product info
    - Current Split Structure insights (collapsible)
    - Form: KPI Center, Split %, Valid From, Valid To
    - Validation section with metrics
    - Approve checkbox (admin only)
    - Update button (use X to close/cancel)
    """
    # Get context from session state
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    can_approve = st.session_state.get('_split_dialog_can_approve', False)
    rule_id = st.session_state.get('_edit_split_rule_id')
    
    if not rule_id:
        st.error("No rule selected for editing. Please close this dialog and select a rule first.")
        return
    
    # Initialize queries
    setup_queries = SetupQueries(user_id=user_id)
    
    # Get existing rule data
    df = setup_queries.get_kpi_split_data(limit=5000)
    df = df[df['kpi_center_split_id'] == rule_id]
    
    if df.empty:
        st.error(f"Rule #{rule_id} not found. Please close this dialog and try again.")
        return
    
    existing = df.iloc[0]
    
    # =========================================================================
    # HEADER: Rule Info
    # =========================================================================
    st.caption(f"Rule ID: #{rule_id}")
    
    header_col1, header_col2 = st.columns(2)
    with header_col1:
        customer_display = format_customer_display(
            existing['customer_name'], 
            existing.get('company_code')
        )
        st.markdown(f"**Customer:** {customer_display}")
    
    with header_col2:
        product_display = format_product_display(
            existing['product_name'],
            existing.get('pt_code'),
            existing.get('package_size'),
            existing.get('brand'),
            include_brand=True
        )
        st.markdown(f"**Product:** {product_display}")
    
    # Get KPI Center type for structure display
    centers_df = setup_queries.get_kpi_centers_for_dropdown()
    current_kpi_center_id = existing['kpi_center_id']
    selected_type = None
    if not centers_df.empty and current_kpi_center_id in centers_df['kpi_center_id'].values:
        selected_type = centers_df[centers_df['kpi_center_id'] == current_kpi_center_id]['kpi_type'].iloc[0]
    
    # =========================================================================
    # CURRENT SPLIT STRUCTURE INSIGHTS
    # =========================================================================
    _render_current_split_structure(
        setup_queries=setup_queries,
        customer_id=int(existing['customer_id']),
        product_id=int(existing['product_id']),
        kpi_type=selected_type,
        exclude_rule_id=rule_id,
        expanded=True  # Start expanded in Edit mode
    )
    
    st.divider()
    
    # =========================================================================
    # FORM FIELDS
    # =========================================================================
    form_col1, form_col2 = st.columns(2)
    
    with form_col1:
        # KPI Center selection
        if not centers_df.empty:
            default_idx = 0
            if current_kpi_center_id in centers_df['kpi_center_id'].values:
                idx_list = centers_df['kpi_center_id'].tolist()
                default_idx = idx_list.index(current_kpi_center_id)
            
            kpi_center_id = st.selectbox(
                "KPI Center *",
                options=centers_df['kpi_center_id'].tolist(),
                index=default_idx,
                format_func=lambda x: f"{KPI_TYPE_ICONS.get(centers_df[centers_df['kpi_center_id'] == x]['kpi_type'].iloc[0], '📁')} {centers_df[centers_df['kpi_center_id'] == x]['kpi_center_name'].iloc[0]}",
                key="edit_dialog_kpi_center_id"
            )
        else:
            kpi_center_id = current_kpi_center_id
            st.warning("No KPI Centers available")
    
    with form_col2:
        # Split percentage
        default_split = float(existing['split_percentage']) if pd.notna(existing['split_percentage']) else 100.0
        split_pct = st.number_input(
            "Split % *",
            min_value=0.0,
            max_value=100.0,
            value=default_split,
            step=5.0,
            key="edit_dialog_split_pct"
        )
    
    # Period inputs
    period_col1, period_col2 = st.columns(2)
    
    with period_col1:
        default_from = pd.to_datetime(existing['effective_from']).date() if pd.notna(existing.get('effective_from')) else date.today()
        valid_from = st.date_input(
            "Valid From *",
            value=default_from,
            key="edit_dialog_valid_from"
        )
    
    with period_col2:
        default_to = pd.to_datetime(existing['effective_to']).date() if pd.notna(existing.get('effective_to')) else date(date.today().year, 12, 31)
        valid_to = st.date_input(
            "Valid To *",
            value=default_to,
            key="edit_dialog_valid_to"
        )
    
    # =========================================================================
    # VALIDATION SECTION
    # =========================================================================
    st.divider()
    st.markdown("##### 🔍 Validation")
    
    validation_errors = []
    validation_warnings = []
    can_save = True
    
    # 1. Period Validation
    period_validation = setup_queries.validate_period(valid_from, valid_to)
    
    if not period_validation['is_valid']:
        for err in period_validation['errors']:
            validation_errors.append(f"📅 {err}")
        can_save = False
    
    for warn in period_validation.get('warnings', []):
        validation_warnings.append(f"📅 {warn}")
    
    # 2. Period Overlap Check (for same KPI Center)
    customer_id = int(existing['customer_id'])
    product_id = int(existing['product_id'])
    
    if kpi_center_id and valid_from and valid_to:
        overlap_check = setup_queries.check_period_overlap(
            customer_id=customer_id,
            product_id=product_id,
            kpi_center_id=kpi_center_id,
            valid_from=valid_from,
            valid_to=valid_to,
            exclude_rule_id=rule_id
        )
        
        if overlap_check['has_overlap']:
            validation_errors.append(
                f"📅 Period overlaps with {overlap_check['overlap_count']} existing rule(s) for this KPI Center"
            )
            can_save = False
            
            with st.expander(f"🔍 View {overlap_check['overlap_count']} overlapping rules", expanded=False):
                for r in overlap_check['overlapping_rules']:
                    st.caption(f"• Rule #{r['rule_id']}: {r['split_percentage']:.0f}% ({r['period_display']})")
    
    # 3. Split Percentage Validation
    if kpi_center_id and not centers_df.empty:
        new_selected_type = centers_df[centers_df['kpi_center_id'] == kpi_center_id]['kpi_type'].iloc[0]
        
        split_validation = setup_queries.validate_split_percentage(
            customer_id=customer_id,
            product_id=product_id,
            kpi_type=new_selected_type,
            new_percentage=split_pct,
            exclude_rule_id=rule_id
        )
        
        # Display metrics
        val_col1, val_col2, val_col3 = st.columns(3)
        
        with val_col1:
            st.metric(
                "Current Total",
                f"{split_validation['current_total']:.0f}%",
                help=f"Total for {new_selected_type} type (excluding this rule)"
            )
        
        with val_col2:
            delta_color = "inverse" if split_validation['new_total'] > 100 else "off"
            st.metric(
                "After Save",
                f"{split_validation['new_total']:.0f}%",
                delta=f"+{split_pct:.0f}%",
                delta_color=delta_color
            )
        
        with val_col3:
            if split_validation['new_total'] == 100:
                st.success("✅ Perfect!")
            elif split_validation['new_total'] > 100:
                over_pct = split_validation['new_total'] - 100
                st.error(f"🔴 Over by {over_pct:.0f}%")
                validation_errors.append(
                    f"📊 Total split ({split_validation['new_total']:.0f}%) exceeds 100% for {new_selected_type}"
                )
                can_save = False
            else:
                st.warning(f"⚠️ {split_validation['remaining']:.0f}% remaining")
                validation_warnings.append(
                    f"📊 Under-allocated: {split_validation['remaining']:.0f}% remaining for {new_selected_type}"
                )
    
    # Display validation summary
    if validation_errors:
        for err in validation_errors:
            st.error(err)
    
    if validation_warnings and not validation_errors:
        for warn in validation_warnings:
            st.warning(warn)
    
    if not validation_errors and not validation_warnings:
        st.success("✅ All validations passed")
    
    # =========================================================================
    # APPROVE CHECKBOX (Admin only)
    # =========================================================================
    st.divider()
    
    current_approved = is_approved_truthy(existing.get('is_approved'))
    approve_rule = current_approved
    
    if can_approve:
        approve_rule = st.checkbox(
            "✅ Approve this rule",
            value=current_approved,
            key="edit_dialog_approve",
            help="Mark this rule as approved"
        )
    else:
        # Show current status for non-admins
        if current_approved:
            st.info("✅ This rule is approved")
        else:
            st.warning("⏳ This rule is pending approval")
    
    # =========================================================================
    # BUTTON (Cancel removed - use dialog X button to close)
    # =========================================================================
    st.divider()
    
    if st.button("💾 Update", type="primary", use_container_width=True, disabled=not can_save):
        # Update the rule
        result = setup_queries.update_split_rule(
            rule_id=rule_id,
            split_percentage=split_pct,
            valid_from=valid_from,
            valid_to=valid_to,
            kpi_center_id=kpi_center_id
        )
        
        if result['success']:
            # Handle approval change if admin
            if can_approve:
                if approve_rule and not current_approved:
                    # Approve
                    setup_queries.approve_split_rules([rule_id], approved_by=user_id)
                elif not approve_rule and current_approved:
                    # Disapprove
                    setup_queries.bulk_disapprove_split_rules([rule_id], modified_by=user_id)
            
            st.toast("✅ Updated successfully!", icon="✅")
            st.session_state.pop('_edit_split_rule_id', None)
            st.session_state['split_selected_ids'] = set()  # Clear selection
            st.rerun()  # Close dialog and refresh
        else:
            st.error(result['message'])


# =============================================================================
# COPY TO NEW PERIOD DIALOG (v2.11.0)
# =============================================================================

@st.dialog("📋 Copy to New Period", width="large")
def _copy_to_period_dialog():
    """
    Dialog for copying selected split rules to a new validity period.
    
    v2.11.0: NEW - Bulk copy split rules to new period.
    
    Features:
    - Preview selected rules
    - Set new validity period
    - Option to copy approval status
    - Validation: period overlap, split % exceeds 100%
    """
    # Get context from session state
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    selected_ids = st.session_state.get('_copy_to_period_rule_ids', [])
    can_approve = st.session_state.get('_copy_dialog_can_approve', False)
    
    if not selected_ids:
        st.error("No rules selected for copying. Please close this dialog and select rules first.")
        return
    
    # Initialize queries
    setup_queries = SetupQueries(user_id=user_id)
    
    # Get selected rules info for preview
    rules_df = setup_queries.get_kpi_split_data(limit=5000)
    selected_rules = rules_df[rules_df['kpi_center_split_id'].isin(selected_ids)]
    
    if selected_rules.empty:
        st.error("Selected rules not found. Please close this dialog and try again.")
        return
    
    # ==========================================================================
    # HEADER: Selection Summary
    # ==========================================================================
    st.markdown(f"### 📋 Copy {len(selected_ids)} Rule(s) to New Period")
    
    # Show summary
    summary_col1, summary_col2, summary_col3 = st.columns(3)
    with summary_col1:
        unique_customers = selected_rules['customer_id'].nunique()
        st.metric("Customers", unique_customers)
    with summary_col2:
        unique_products = selected_rules['product_id'].nunique()
        st.metric("Products", unique_products)
    with summary_col3:
        unique_centers = selected_rules['kpi_center_id'].nunique()
        st.metric("KPI Centers", unique_centers)
    
    # ==========================================================================
    # PREVIEW: Selected Rules (collapsible)
    # ==========================================================================
    with st.expander(f"📄 Preview Selected Rules ({len(selected_ids)})", expanded=False):
        preview_df = selected_rules[[
            'kpi_center_split_id', 'kpi_center_name', 'customer_name', 
            'product_name', 'split_percentage', 'effective_period'
        ]].copy()
        preview_df.columns = ['ID', 'KPI Center', 'Customer', 'Product', 'Split %', 'Current Period']
        st.dataframe(preview_df, hide_index=True, use_container_width=True)
    
    st.divider()
    
    # ==========================================================================
    # NEW PERIOD INPUTS
    # ==========================================================================
    st.markdown("##### 📅 New Validity Period")
    
    # Default: next year
    current_year = date.today().year
    default_from = date(current_year + 1, 1, 1)
    default_to = date(current_year + 1, 12, 31)
    
    period_col1, period_col2 = st.columns(2)
    
    with period_col1:
        new_valid_from = st.date_input(
            "Valid From *",
            value=default_from,
            key="copy_dialog_valid_from"
        )
    
    with period_col2:
        new_valid_to = st.date_input(
            "Valid To *",
            value=default_to,
            key="copy_dialog_valid_to"
        )
    
    # Quick period presets
    st.caption("Quick presets:")
    preset_col1, preset_col2, preset_col3, preset_col4 = st.columns(4)
    
    with preset_col1:
        if st.button(f"📅 {current_year + 1}", use_container_width=True, 
                     help=f"Full year {current_year + 1}"):
            st.session_state['copy_dialog_valid_from'] = date(current_year + 1, 1, 1)
            st.session_state['copy_dialog_valid_to'] = date(current_year + 1, 12, 31)
            st.rerun()
    
    with preset_col2:
        if st.button(f"📅 H1 {current_year + 1}", use_container_width=True,
                     help=f"First half of {current_year + 1}"):
            st.session_state['copy_dialog_valid_from'] = date(current_year + 1, 1, 1)
            st.session_state['copy_dialog_valid_to'] = date(current_year + 1, 6, 30)
            st.rerun()
    
    with preset_col3:
        if st.button(f"📅 H2 {current_year + 1}", use_container_width=True,
                     help=f"Second half of {current_year + 1}"):
            st.session_state['copy_dialog_valid_from'] = date(current_year + 1, 7, 1)
            st.session_state['copy_dialog_valid_to'] = date(current_year + 1, 12, 31)
            st.rerun()
    
    with preset_col4:
        if st.button(f"📅 {current_year + 2}", use_container_width=True,
                     help=f"Full year {current_year + 2}"):
            st.session_state['copy_dialog_valid_from'] = date(current_year + 2, 1, 1)
            st.session_state['copy_dialog_valid_to'] = date(current_year + 2, 12, 31)
            st.rerun()
    
    # ==========================================================================
    # OPTIONS
    # ==========================================================================
    st.divider()
    st.markdown("##### ⚙️ Options")
    
    copy_approval = st.checkbox(
        "Copy approval status",
        value=False,
        help="If checked, approved rules will be copied as approved. Otherwise, all copies will be pending.",
        disabled=not can_approve,
        key="copy_dialog_copy_approval"
    )
    
    if not can_approve:
        st.caption("ℹ️ You don't have approval permission. All copies will be set to pending.")
    
    # ==========================================================================
    # VALIDATION
    # ==========================================================================
    st.divider()
    st.markdown("##### 🔍 Validation")
    
    # Run validation
    validation = setup_queries.validate_copy_to_period(
        rule_ids=list(selected_ids),
        new_valid_from=new_valid_from,
        new_valid_to=new_valid_to
    )
    
    can_proceed = validation['can_proceed']
    
    # Show validation results
    if validation['period_errors']:
        for err in validation['period_errors']:
            st.error(f"📅 {err}")
        can_proceed = False
    
    if validation['period_warnings']:
        for warn in validation['period_warnings']:
            st.warning(f"📅 {warn}")
    
    # Overlap check
    if validation['overlap_count'] > 0:
        st.error(f"🔴 {validation['overlap_count']} rule(s) would overlap with existing rules")
        
        with st.expander(f"View {validation['overlap_count']} overlapping rules", expanded=True):
            for detail in validation['overlap_details'][:10]:
                st.caption(
                    f"• #{detail['rule_id']} | {detail['kpi_center_name']} | "
                    f"{detail['customer_name'][:25]}... | {detail['product_name'][:25]}..."
                )
            if validation['overlap_count'] > 10:
                st.caption(f"... and {validation['overlap_count'] - 10} more")
        
        can_proceed = False
    
    # Split % warnings (not blocking, just warning)
    if validation.get('split_warnings'):
        st.warning(f"⚠️ {len(validation['split_warnings'])} rule(s) may exceed 100% split after copy")
        
        with st.expander(f"View {len(validation['split_warnings'])} split warnings", expanded=False):
            for detail in validation['split_warnings'][:10]:
                st.caption(
                    f"• #{detail['rule_id']} | {detail['kpi_type']} | "
                    f"{detail['customer_name'][:20]}... → {detail['new_total']:.0f}%"
                )
            if len(validation['split_warnings']) > 10:
                st.caption(f"... and {len(validation['split_warnings']) - 10} more")
    
    # Success message if all good
    if can_proceed and not validation.get('split_warnings'):
        st.success("✅ All validations passed")
    elif can_proceed and validation.get('split_warnings'):
        st.info("✅ Can proceed (with split % warnings)")
    
    # ==========================================================================
    # BUTTON (Cancel removed - use dialog X button to close)
    # ==========================================================================
    st.divider()
    
    if st.button(
        f"📋 Copy {len(selected_ids)} Rules",
        type="primary",
        use_container_width=True,
        disabled=not can_proceed
    ):
        # Execute copy
        result = setup_queries.copy_split_rules_to_period(
            rule_ids=list(selected_ids),
            new_valid_from=new_valid_from,
            new_valid_to=new_valid_to,
            copy_approval_status=copy_approval,
            created_by=user_id
        )
        
        if result['success']:
            st.toast(f"✅ {result['message']}", icon="✅")
            # Clear selection and close dialog
            st.session_state.pop('_copy_to_period_rule_ids', None)
            st.session_state['split_selected_ids'] = set()
            st.rerun()
        else:
            st.error(f"❌ {result['message']}")


def _render_split_form(setup_queries: SetupQueries, can_approve: bool, 
                       mode: str = 'add', rule_id: int = None):
    """
    Render Add/Edit split rule form.
    
    ⚠️ DEPRECATED in v2.9.0:
    - Add mode: Use _add_split_rule_dialog() instead
    - Edit mode: Use _edit_split_rule_dialog() instead
    
    This function is kept for backward compatibility but should not be used.
    """
    
    existing = None
    if mode == 'edit' and rule_id:
        df = setup_queries.get_kpi_split_data(limit=5000)
        df = df[df['kpi_center_split_id'] == rule_id]
        if not df.empty:
            existing = df.iloc[0]
        else:
            st.error("Rule not found")
            st.session_state['edit_split_id'] = None
            return
    
    title = "✏️ Edit Split Rule" if mode == 'edit' else "➕ Add Split Rule"
    
    with st.container(border=True):
        st.markdown(f"### {title}")
        
        if mode == 'edit' and existing is not None:
            st.caption(f"Rule ID: {rule_id}")
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.markdown(f"**Customer:** {format_customer_display(existing['customer_name'], existing.get('company_code'))}")
            with col_info2:
                st.markdown(f"**Product:** {format_product_display(existing['product_name'], existing.get('pt_code'), existing.get('package_size'), existing.get('brand'), include_brand=True)}")
        
        with st.form(f"{mode}_split_form", clear_on_submit=False):
            col1, col2 = st.columns(2)
            
            with col1:
                if mode == 'add':
                    # Customer selection
                    customers_df = setup_queries.get_customers_for_dropdown()
                    
                    if not customers_df.empty:
                        customer_id = st.selectbox(
                            "Customer *",
                            options=customers_df['customer_id'].tolist(),
                            format_func=lambda x: f"{customers_df[customers_df['customer_id'] == x]['customer_name'].iloc[0]} ({customers_df[customers_df['customer_id'] == x]['company_code'].iloc[0]})",
                            key=f"{mode}_customer_id"
                        )
                    else:
                        customer_id = None
                        st.caption("No customers found")
                else:
                    customer_id = existing['customer_id']
                
                # KPI Center selection
                centers_df = setup_queries.get_kpi_centers_for_dropdown()
                if not centers_df.empty:
                    default_idx = 0
                    if existing is not None and 'kpi_center_id' in existing:
                        matches = centers_df[centers_df['kpi_center_id'] == existing['kpi_center_id']]
                        if not matches.empty:
                            default_idx = centers_df.index.tolist().index(matches.index[0])
                    
                    kpi_center_id = st.selectbox(
                        "KPI Center *",
                        options=centers_df['kpi_center_id'].tolist(),
                        index=default_idx,
                        format_func=lambda x: f"{KPI_TYPE_ICONS.get(centers_df[centers_df['kpi_center_id'] == x]['kpi_type'].iloc[0], '📁')} {centers_df[centers_df['kpi_center_id'] == x]['kpi_center_name'].iloc[0]}",
                        key=f"{mode}_kpi_center_id"
                    )
                else:
                    kpi_center_id = None
            
            with col2:
                if mode == 'add':
                    # Product selection
                    products_df = setup_queries.get_products_for_dropdown()
                    
                    if not products_df.empty:
                        # Format: "name (code | package_size)" - consistent with customer dropdown
                        def format_product_option(row):
                            name = row['product_name'] or ''
                            code = row['pt_code'] or ''
                            pkg = row.get('package_size', '') or ''
                            detail = " | ".join(filter(None, [code, pkg]))
                            return f"{name} ({detail})" if detail else name
                        
                        product_id = st.selectbox(
                            "Product *",
                            options=products_df['product_id'].tolist(),
                            format_func=lambda x: format_product_option(products_df[products_df['product_id'] == x].iloc[0]),
                            key=f"{mode}_product_id"
                        )
                    else:
                        product_id = None
                        st.caption("No products found")
                else:
                    product_id = existing['product_id']
                
                # Split percentage
                default_split = float(existing['split_percentage']) if existing is not None else 100.0
                split_pct = st.number_input(
                    "Split % *",
                    min_value=0.0,
                    max_value=100.0,
                    value=default_split,
                    step=5.0,
                    key=f"{mode}_split_pct"
                )
            
            # Period inputs (moved up for validation)
            col3, col4 = st.columns(2)
            with col3:
                default_from = pd.to_datetime(existing['effective_from']).date() if existing is not None and pd.notna(existing.get('effective_from')) else date.today()
                valid_from = st.date_input("Valid From *", value=default_from, key=f"{mode}_valid_from")
            
            with col4:
                default_to = pd.to_datetime(existing['effective_to']).date() if existing is not None and pd.notna(existing.get('effective_to')) else date(date.today().year, 12, 31)
                valid_to = st.date_input("Valid To *", value=default_to, key=f"{mode}_valid_to")
            
            # =====================================================================
            # ENHANCED VALIDATION SECTION (v2.8.0)
            # =====================================================================
            st.divider()
            st.markdown("##### 🔍 Validation")
            
            validation_errors = []
            validation_warnings = []
            can_save = True
            
            # -----------------------------------------------------------------
            # 1. Period Validation
            # -----------------------------------------------------------------
            period_validation = setup_queries.validate_period(valid_from, valid_to)
            
            if not period_validation['is_valid']:
                for err in period_validation['errors']:
                    validation_errors.append(f"📅 {err}")
                can_save = False
            
            for warn in period_validation.get('warnings', []):
                validation_warnings.append(f"📅 {warn}")
            
            # -----------------------------------------------------------------
            # 2. Period Overlap Check (for same KPI Center) - BLOCK
            # -----------------------------------------------------------------
            if customer_id and product_id and kpi_center_id and valid_from and valid_to:
                overlap_check = setup_queries.check_period_overlap(
                    customer_id=customer_id,
                    product_id=product_id,
                    kpi_center_id=kpi_center_id,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    exclude_rule_id=rule_id if mode == 'edit' else None
                )
                
                if overlap_check['has_overlap']:
                    validation_errors.append(
                        f"📅 Period overlaps with {overlap_check['overlap_count']} existing rule(s) for this KPI Center"
                    )
                    can_save = False
                    
                    with st.expander(f"🔍 View {overlap_check['overlap_count']} overlapping rules", expanded=False):
                        for r in overlap_check['overlapping_rules']:
                            st.caption(f"• Rule #{r['rule_id']}: {r['split_percentage']:.0f}% ({r['period_display']})")
            
            # -----------------------------------------------------------------
            # 3. Split Percentage Validation (per kpi_type) - BLOCK if >100%
            # -----------------------------------------------------------------
            if customer_id and product_id and kpi_center_id and not centers_df.empty:
                selected_type = centers_df[centers_df['kpi_center_id'] == kpi_center_id]['kpi_type'].iloc[0]
                
                split_validation = setup_queries.validate_split_percentage(
                    customer_id=customer_id,
                    product_id=product_id,
                    kpi_type=selected_type,
                    new_percentage=split_pct,
                    exclude_rule_id=rule_id if mode == 'edit' else None
                )
                
                # Display metrics
                val_col1, val_col2, val_col3 = st.columns(3)
                
                with val_col1:
                    st.metric(
                        "Current Total",
                        f"{split_validation['current_total']:.0f}%",
                        help=f"Total for {selected_type} type"
                    )
                
                with val_col2:
                    delta_color = "inverse" if split_validation['new_total'] > 100 else "off"
                    st.metric(
                        "After Save",
                        f"{split_validation['new_total']:.0f}%",
                        delta=f"+{split_pct:.0f}%",
                        delta_color=delta_color
                    )
                
                with val_col3:
                    if split_validation['new_total'] == 100:
                        st.success("✅ Perfect!")
                    elif split_validation['new_total'] > 100:
                        over_pct = split_validation['new_total'] - 100
                        st.error(f"🔴 Over by {over_pct:.0f}%")
                        
                        # BLOCK save - business rule
                        validation_errors.append(
                            f"📊 Total split ({split_validation['new_total']:.0f}%) exceeds 100% for {selected_type}"
                        )
                        can_save = False
                    else:
                        st.warning(f"⚠️ {split_validation['remaining']:.0f}% remaining")
                        validation_warnings.append(
                            f"📊 Under-allocated: {split_validation['remaining']:.0f}% remaining for {selected_type}"
                        )
            
            # -----------------------------------------------------------------
            # Display validation summary
            # -----------------------------------------------------------------
            if validation_errors:
                for err in validation_errors:
                    st.error(err)
            
            if validation_warnings and not validation_errors:
                for warn in validation_warnings:
                    st.warning(warn)
            
            if not validation_errors and not validation_warnings:
                st.success("✅ All validations passed")
            
            # Form buttons
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                submitted = st.form_submit_button(
                    "💾 Save" if mode == 'add' else "💾 Update",
                    type="primary",
                    use_container_width=True,
                    disabled=not can_save
                )
            
            with col_cancel:
                cancelled = st.form_submit_button("❌ Cancel", use_container_width=True)
            
            if submitted:
                # Double-check before saving
                if not can_save:
                    st.error("Cannot save - please fix validation errors above")
                elif mode == 'add' and not all([customer_id, product_id, kpi_center_id]):
                    st.error("Please fill all required fields")
                else:
                    if mode == 'add':
                        result = setup_queries.create_split_rule(
                            customer_id=customer_id,
                            product_id=product_id,
                            kpi_center_id=kpi_center_id,
                            split_percentage=split_pct,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            is_approved=can_approve
                        )
                    else:
                        result = setup_queries.update_split_rule(
                            rule_id=rule_id,
                            split_percentage=split_pct,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            kpi_center_id=kpi_center_id
                        )
                    
                    if result['success']:
                        st.success(f"{'Created' if mode == 'add' else 'Updated'} successfully!")
                        st.session_state['show_add_split_form'] = False
                        st.session_state['edit_split_id'] = None
                        st.rerun(scope="fragment")
                    else:
                        st.error(result['message'])
            
            if cancelled:
                st.session_state['show_add_split_form'] = False
                st.session_state['edit_split_id'] = None
                st.rerun(scope="fragment")


# =============================================================================
# ADD ASSIGNMENT DIALOG (v2.12.0 - Dialog fashion)
# =============================================================================

@st.dialog("➕ Add KPI Assignment", width="large")
def _add_assignment_dialog():
    """
    Dialog for adding a new KPI assignment.
    
    v2.12.0: NEW - Converted from inline form to dialog for cleaner UX.
    """
    # Get context from session state
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    selected_year = st.session_state.get('_assignment_dialog_year', date.today().year)
    default_center_id = st.session_state.get('_assignment_dialog_center_id')
    
    # Initialize queries
    setup_queries = SetupQueries(user_id=user_id)
    
    # Form layout
    col1, col2 = st.columns(2)
    
    with col1:
        # KPI Center
        centers_df = setup_queries.get_kpi_centers_for_dropdown()
        
        default_idx = 0
        if default_center_id and not centers_df.empty:
            matches = centers_df[centers_df['kpi_center_id'] == default_center_id]
            if not matches.empty:
                default_idx = centers_df.index.tolist().index(matches.index[0])
        
        kpi_center_id = st.selectbox(
            "KPI Center *",
            options=centers_df['kpi_center_id'].tolist(),
            index=default_idx,
            format_func=lambda x: f"{KPI_TYPE_ICONS.get(centers_df[centers_df['kpi_center_id'] == x]['kpi_type'].iloc[0], '📁')} {centers_df[centers_df['kpi_center_id'] == x]['kpi_center_name'].iloc[0]}",
            key="dialog_assign_center"
        )
        
        # KPI Type
        kpi_types_df = setup_queries.get_kpi_types()
        
        kpi_type_id = st.selectbox(
            "KPI Type *",
            options=kpi_types_df['kpi_type_id'].tolist(),
            format_func=lambda x: f"{KPI_ICONS.get(kpi_types_df[kpi_types_df['kpi_type_id'] == x]['kpi_name'].iloc[0].lower().replace(' ', '_'), '📋')} {kpi_types_df[kpi_types_df['kpi_type_id'] == x]['kpi_name'].iloc[0]}",
            key="dialog_assign_type"
        )
    
    with col2:
        # Get UOM for selected KPI
        selected_kpi = kpi_types_df[kpi_types_df['kpi_type_id'] == kpi_type_id].iloc[0]
        selected_uom = selected_kpi['unit_of_measure']
        
        # Annual target
        annual_target = st.number_input(
            f"Annual Target ({selected_uom}) *",
            min_value=0,
            value=0,
            step=10000 if selected_uom == 'USD' else 1,
            key="dialog_assign_target"
        )
        
        if selected_uom == 'USD' and annual_target > 0:
            st.caption(f"= {format_currency(annual_target / 12)}/month • {format_currency(annual_target / 4)}/quarter")
        
        # Weight
        weight = st.number_input(
            "Weight % *",
            min_value=0,
            max_value=100,
            value=0,
            step=5,
            key="dialog_assign_weight"
        )
    
    # Validation
    st.divider()
    st.markdown("##### 🔍 Validation")
    
    validation = setup_queries.validate_assignment_weight(
        kpi_center_id=kpi_center_id,
        year=selected_year,
        new_weight=weight,
        exclude_assignment_id=None
    )
    
    val_col1, val_col2, val_col3 = st.columns(3)
    
    with val_col1:
        st.metric("Current Weight Sum", f"{validation['current_total']}%")
    
    with val_col2:
        delta_color = "inverse" if validation['new_total'] > 100 else "off"
        st.metric(
            "After Save",
            f"{validation['new_total']}%",
            delta=f"+{weight}%",
            delta_color=delta_color
        )
    
    with val_col3:
        if validation['new_total'] == 100:
            st.success("✅ Perfect!")
        elif validation['new_total'] > 100:
            st.error(f"🔴 Over by {validation['new_total'] - 100}%")
        else:
            st.warning(f"⚠️ {100 - validation['new_total']}% remaining")
    
    # Notes
    notes = st.text_input(
        "Notes (optional)",
        value="",
        key="dialog_assign_notes"
    )
    
    # Validation errors
    can_save = True
    if annual_target <= 0:
        st.error("Annual target must be > 0")
        can_save = False
    if weight <= 0:
        st.error("Weight must be > 0")
        can_save = False
    
    # Save button
    st.divider()
    if st.button("💾 Save", type="primary", use_container_width=True, disabled=not can_save):
        result = setup_queries.create_assignment(
            kpi_center_id=kpi_center_id,
            kpi_type_id=kpi_type_id,
            year=selected_year,
            annual_target_value=annual_target,
            weight=weight,
            notes=notes if notes else None
        )
        
        if result['success']:
            st.toast("✅ Created successfully!", icon="✅")
            st.rerun()  # Close dialog and refresh
        else:
            st.error(result['message'])


# =============================================================================
# EDIT ASSIGNMENT DIALOG (v2.12.0 - Dialog fashion)
# =============================================================================

@st.dialog("✏️ Edit KPI Assignment", width="large")
def _edit_assignment_dialog():
    """
    Dialog for editing an existing KPI assignment.
    
    v2.12.0: NEW - Converted from inline form to dialog for cleaner UX.
    """
    # Get context from session state
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    assignment_id = st.session_state.get('_edit_assignment_id')
    selected_year = st.session_state.get('_assignment_dialog_year', date.today().year)
    
    if not assignment_id:
        st.error("No assignment selected for editing. Please close this dialog and try again.")
        return
    
    # Initialize queries
    setup_queries = SetupQueries(user_id=user_id)
    
    # Get existing assignment data
    df = setup_queries.get_kpi_assignments()
    df = df[df['assignment_id'] == assignment_id]
    
    if df.empty:
        st.error(f"Assignment #{assignment_id} not found. Please close this dialog and try again.")
        return
    
    existing = df.iloc[0]
    
    # Header info
    st.markdown(f"**Assignment #{assignment_id}**")
    st.caption(f"📍 {existing['kpi_center_name']} • {existing['kpi_name']} • Year {existing['year']}")
    
    st.divider()
    
    # Form layout - KPI Center and Type are read-only in edit mode
    col1, col2 = st.columns(2)
    
    with col1:
        # KPI Center (read-only)
        center_display = f"{KPI_TYPE_ICONS.get(existing['kpi_center_type'], '📁')} {existing['kpi_center_name']}"
        st.text_input("KPI Center", value=center_display, disabled=True)
        
        # KPI Type (read-only)
        kpi_display = f"{KPI_ICONS.get(existing['kpi_name'].lower().replace(' ', '_'), '📋')} {existing['kpi_name']}"
        st.text_input("KPI Type", value=kpi_display, disabled=True)
    
    with col2:
        # Get UOM
        selected_uom = existing['unit_of_measure']
        
        # Annual target
        default_target = int(existing['annual_target_value_numeric'])
        annual_target = st.number_input(
            f"Annual Target ({selected_uom}) *",
            min_value=0,
            value=default_target,
            step=10000 if selected_uom == 'USD' else 1,
            key="dialog_edit_assign_target"
        )
        
        if selected_uom == 'USD' and annual_target > 0:
            st.caption(f"= {format_currency(annual_target / 12)}/month • {format_currency(annual_target / 4)}/quarter")
        
        # Weight
        default_weight = int(existing['weight_numeric'])
        weight = st.number_input(
            "Weight % *",
            min_value=0,
            max_value=100,
            value=default_weight,
            step=5,
            key="dialog_edit_assign_weight"
        )
    
    # Validation
    st.divider()
    st.markdown("##### 🔍 Validation")
    
    validation = setup_queries.validate_assignment_weight(
        kpi_center_id=existing['kpi_center_id'],
        year=existing['year'],
        new_weight=weight,
        exclude_assignment_id=assignment_id
    )
    
    val_col1, val_col2, val_col3 = st.columns(3)
    
    with val_col1:
        st.metric("Current Weight Sum", f"{validation['current_total']}%")
    
    with val_col2:
        delta_color = "inverse" if validation['new_total'] > 100 else "off"
        st.metric(
            "After Save",
            f"{validation['new_total']}%",
            delta=f"+{weight}%",
            delta_color=delta_color
        )
    
    with val_col3:
        if validation['new_total'] == 100:
            st.success("✅ Perfect!")
        elif validation['new_total'] > 100:
            st.error(f"🔴 Over by {validation['new_total'] - 100}%")
        else:
            st.warning(f"⚠️ {100 - validation['new_total']}% remaining")
    
    # Notes
    notes = st.text_input(
        "Notes (optional)",
        value=existing['notes'] if pd.notna(existing.get('notes')) else "",
        key="dialog_edit_assign_notes"
    )
    
    # Validation errors
    can_save = True
    if annual_target <= 0:
        st.error("Annual target must be > 0")
        can_save = False
    if weight <= 0:
        st.error("Weight must be > 0")
        can_save = False
    
    # Save button
    st.divider()
    if st.button("💾 Update", type="primary", use_container_width=True, disabled=not can_save):
        result = setup_queries.update_assignment(
            assignment_id=assignment_id,
            annual_target_value=annual_target,
            weight=weight,
            notes=notes if notes else None
        )
        
        if result['success']:
            st.toast("✅ Updated successfully!", icon="✅")
            st.rerun()  # Close dialog and refresh
        else:
            st.error(result['message'])


# =============================================================================
# DELETE ASSIGNMENT DIALOG (v2.12.0 - Confirmation dialog)
# =============================================================================

@st.dialog("🗑️ Delete KPI Assignment")
def _delete_assignment_dialog():
    """
    Confirmation dialog for deleting a KPI assignment.
    
    v2.12.0: NEW - Separate confirmation dialog for better UX.
    """
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    assignment_id = st.session_state.get('_delete_assignment_id')
    
    if not assignment_id:
        st.error("No assignment selected for deletion.")
        return
    
    setup_queries = SetupQueries(user_id=user_id)
    
    # Get assignment info
    df = setup_queries.get_kpi_assignments()
    df = df[df['assignment_id'] == assignment_id]
    
    if df.empty:
        st.error(f"Assignment #{assignment_id} not found.")
        return
    
    existing = df.iloc[0]
    
    st.warning(f"⚠️ Are you sure you want to delete this assignment?")
    
    st.markdown(f"""
    **Assignment #{assignment_id}**
    - KPI Center: {existing['kpi_center_name']}
    - KPI Type: {existing['kpi_name']}
    - Target: {format_currency(existing['annual_target_value_numeric']) if existing['unit_of_measure'] == 'USD' else f"{existing['annual_target_value_numeric']:,.0f}"}
    - Weight: {existing['weight_numeric']:.0f}%
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🗑️ Yes, Delete", type="primary", use_container_width=True):
            result = setup_queries.delete_assignment(assignment_id)
            if result['success']:
                st.toast("🗑️ Deleted successfully!", icon="🗑️")
                st.rerun()
            else:
                st.error(result['message'])
    
    with col2:
        if st.button("❌ Cancel", use_container_width=True):
            st.rerun()


# =============================================================================
# KPI ASSIGNMENTS SECTION (v2.12.0 - Updated with dialogs)
# =============================================================================

def kpi_assignments_section(
    setup_queries: SetupQueries,
    kpi_center_ids: List[int] = None,
    can_create: bool = False,
    can_edit: bool = False,
    can_delete: bool = False,
    current_year: int = None
):
    """
    KPI Assignments sub-tab - styled like KPI & Targets tab.
    
    v2.12.0: Updated with dialog fashion for CRUD operations.
    v2.10.1: Removed @st.fragment decorator to fix nested fragment bug.
    v2.10.0: Updated with granular permissions (can_create, can_edit, can_delete)
    """
    
    current_year = current_year or date.today().year
    
    # -------------------------------------------------------------------------
    # FILTER BAR
    # -------------------------------------------------------------------------
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        available_years = setup_queries.get_available_years()
        if current_year not in available_years:
            available_years.append(current_year)
        available_years.sort(reverse=True)
        
        selected_year = st.selectbox(
            "Year",
            options=available_years,
            index=available_years.index(current_year) if current_year in available_years else 0,
            key="assign_year_filter"
        )
    
    with col2:
        centers_df = setup_queries.get_kpi_centers_for_dropdown()
        center_options = [(-1, "All KPI Centers")] + [
            (row['kpi_center_id'], f"{KPI_TYPE_ICONS.get(row['kpi_type'], '📁')} {row['kpi_center_name']}") 
            for _, row in centers_df.iterrows()
        ]
        selected_center_id = st.selectbox(
            "KPI Center",
            options=[c[0] for c in center_options],
            format_func=lambda x: next((c[1] for c in center_options if c[0] == x), ""),
            key="assign_center_filter"
        )
    
    with col3:
        # v2.12.0: Use dialog for Add Assignment
        if can_create:
            st.write("")  # Spacer
            if st.button("➕ Add Assignment", type="primary", use_container_width=True):
                st.session_state['_assignment_dialog_year'] = selected_year
                st.session_state['_assignment_dialog_center_id'] = None
                _add_assignment_dialog()
    
    # -------------------------------------------------------------------------
    # ISSUES SECTION (Enhanced v2.4.0 - Leaf/Parent distinction with rollup)
    # -------------------------------------------------------------------------
    issues = setup_queries.get_assignment_issues_summary_v2(selected_year)
    
    # Count actual issues (exclude parent_with_rollup as they're INFO not issues)
    critical_count = issues['leaf_missing_count'] + issues['parent_no_coverage_count']
    warning_count = issues['weight_issues_count']
    info_count = issues['parent_with_rollup_count']
    
    has_issues = critical_count > 0 or warning_count > 0
    has_info = info_count > 0
    
    if has_issues or has_info:
        # Determine expander title based on severity
        if critical_count > 0:
            expander_title = f"🔴 {critical_count} Issues Found"
            if info_count > 0:
                expander_title += f" • 📁 {info_count} Parents with Rollup"
        elif warning_count > 0:
            expander_title = f"⚠️ {warning_count} Weight Issues"
            if info_count > 0:
                expander_title += f" • 📁 {info_count} Parents with Rollup"
        else:
            expander_title = f"📁 {info_count} Parent Centers (Rollup from Children)"
        
        with st.expander(expander_title, expanded=(critical_count > 0)):
            
            # =================================================================
            # CRITICAL: Leaf centers without direct assignment
            # =================================================================
            if issues['leaf_missing_count'] > 0:
                st.markdown("##### 🔴 Missing Assignments (Leaf Centers)")
                st.caption(f"{issues['leaf_missing_count']} leaf KPI Centers need direct {selected_year} assignments")
                
                with st.container(border=True):
                    for center in issues['leaf_missing_details']:
                        col_info, col_action = st.columns([4, 1])
                        with col_info:
                            center_type = center.get('type', 'UNKNOWN')
                            icon = KPI_TYPE_ICONS.get(center_type, '📁')
                            st.markdown(f"🎯 {icon} **{center['name']}**")
                            st.caption(f"{center_type} • Leaf (no children)")
                        with col_action:
                            if can_edit and st.button(
                                "➕ Add", 
                                key=f"add_assign_leaf_{center['id']}", 
                                use_container_width=True
                            ):
                                st.session_state['_assignment_dialog_year'] = selected_year
                                st.session_state['_assignment_dialog_center_id'] = center['id']
                                _add_assignment_dialog()
                
                st.divider()
            
            # =================================================================
            # WARNING: Parent centers with no coverage anywhere
            # =================================================================
            if issues['parent_no_coverage_count'] > 0:
                st.markdown("##### ⚠️ No Coverage (Parent Centers)")
                st.caption(f"{issues['parent_no_coverage_count']} parent centers have no assignments in entire subtree")
                
                with st.container(border=True):
                    for center in issues['parent_no_coverage_details']:
                        col_info, col_action = st.columns([4, 1])
                        with col_info:
                            center_type = center.get('type', 'UNKNOWN')
                            icon = KPI_TYPE_ICONS.get(center_type, '📁')
                            children_count = center.get('children_count', 0)
                            st.markdown(f"📁 {icon} **{center['name']}**")
                            st.caption(f"{center_type} • Parent ({children_count} children) • ⚠️ No assignments in subtree")
                        with col_action:
                            if can_edit and st.button(
                                "➕ Add", 
                                key=f"add_assign_parent_{center['id']}", 
                                use_container_width=True
                            ):
                                st.session_state['_assignment_dialog_year'] = selected_year
                                st.session_state['_assignment_dialog_center_id'] = center['id']
                                _add_assignment_dialog()
                
                st.divider()
            
            # =================================================================
            # INFO: Parent centers with rollup from children (NOT an issue)
            # =================================================================
            if issues['parent_with_rollup_count'] > 0:
                st.markdown("##### 📁 Parent Centers (Rollup from Children)")
                st.caption(f"{issues['parent_with_rollup_count']} parent centers auto-aggregate targets from children")
                
                with st.container(border=True):
                    for center in issues['parent_with_rollup_details']:
                        center_type = center.get('type', 'UNKNOWN')
                        icon = KPI_TYPE_ICONS.get(center_type, '📁')
                        desc_count = center.get('descendants_with_assignments', 0)
                        desc_names = center.get('descendant_names', '')
                        
                        # Header row
                        col_info, col_action = st.columns([4, 1])
                        with col_info:
                            st.markdown(f"📁 {icon} **{center['name']}**")
                            st.caption(f"{center_type} • Rollup from {desc_count} children")
                        with col_action:
                            if can_edit and st.button(
                                "➕ Override", 
                                key=f"add_assign_override_{center['id']}", 
                                use_container_width=True,
                                help="Add direct assignment to override rollup"
                            ):
                                st.session_state['_assignment_dialog_year'] = selected_year
                                st.session_state['_assignment_dialog_center_id'] = center['id']
                                _add_assignment_dialog()
                        
                        # Show rollup targets
                        rollup_data = setup_queries.get_rollup_targets_for_center(center['id'], selected_year)
                        if rollup_data['has_rollup'] and rollup_data['targets']:
                            # Format targets as compact summary
                            target_parts = []
                            for t in rollup_data['targets']:
                                if t['is_currency']:
                                    target_parts.append(f"{t['kpi_name']}: ${t['annual_target']:,.0f}")
                                else:
                                    target_parts.append(f"{t['kpi_name']}: {t['annual_target']:,.0f}")
                            
                            st.markdown(f"<div style='margin-left: 24px; color: #666; font-size: 0.85em;'>📊 {' | '.join(target_parts)}</div>", unsafe_allow_html=True)
                            
                            # Show source centers (truncated)
                            sources = rollup_data['source_centers']
                            if sources:
                                sources_str = ', '.join(sources[:3])
                                if len(sources) > 3:
                                    sources_str += f" +{len(sources) - 3} more"
                                st.markdown(f"<div style='margin-left: 24px; color: #888; font-size: 0.8em;'>↳ From: {sources_str}</div>", unsafe_allow_html=True)
                        
                        st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #eee;'>", unsafe_allow_html=True)
                
                st.info("ℹ️ Parent centers auto-aggregate KPI targets from their children. Add a direct assignment to override the rollup calculation.", icon="💡")
            
            # =================================================================
            # WARNING: Weight not 100%
            # =================================================================
            if issues['weight_issues_count'] > 0:
                if critical_count > 0 or info_count > 0:
                    st.divider()
                
                st.markdown("##### ⚠️ Weight Sum ≠ 100%")
                st.caption(f"{issues['weight_issues_count']} KPI Centers have weights not summing to 100%")
                
                with st.container(border=True):
                    for center in issues['weight_issues_details']:
                        col_info, col_weight, col_action = st.columns([3, 1, 1])
                        with col_info:
                            st.markdown(f"**{center['kpi_center_name']}**")
                        with col_weight:
                            weight = center['total_weight']
                            if weight < 100:
                                st.warning(f"{weight:.0f}%")
                            else:
                                st.error(f"{weight:.0f}%")
                        with col_action:
                            gap = 100 - weight
                            if gap > 0:
                                st.caption(f"+{gap:.0f}% needed")
                            else:
                                st.caption(f"{abs(gap):.0f}% over")
    
    else:
        st.success(f"✅ All {selected_year} assignments are healthy!")
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # KPI TYPE SUMMARY - Like Overview tab metrics
    # -------------------------------------------------------------------------
    summary_df = setup_queries.get_assignment_summary_by_type(selected_year)
    
    if not summary_df.empty:
        st.markdown(f"#### 📊 {selected_year} Targets Overview")
        
        num_cols = min(len(summary_df), 4)
        cols = st.columns(num_cols)
        
        for idx, (_, row) in enumerate(summary_df.iterrows()):
            with cols[idx % num_cols]:
                kpi_lower = row['kpi_name'].lower().replace(' ', '_')
                icon = KPI_ICONS.get(kpi_lower, '📋')
                
                if row['unit_of_measure'] == 'USD':
                    value = format_currency(row['total_target'])
                else:
                    value = f"{row['total_target']:,.0f}"
                
                st.metric(
                    label=f"{icon} {row['kpi_name']}",
                    value=value,
                    delta=f"{row['center_count']} centers",
                    delta_color="off",
                    help=f"Total {selected_year} target for {row['kpi_name']}"
                )
        
        st.divider()
    
    # -------------------------------------------------------------------------
    # ASSIGNMENTS BY KPI CENTER - Card layout like Progress tab
    # -------------------------------------------------------------------------
    query_params = {'year': selected_year}
    if selected_center_id > 0:
        query_params['kpi_center_ids'] = [selected_center_id]
    elif kpi_center_ids:
        query_params['kpi_center_ids'] = kpi_center_ids
    
    assignments_df = setup_queries.get_kpi_assignments(**query_params)
    weight_summary_df = setup_queries.get_assignment_weight_summary(selected_year)
    
    if assignments_df.empty:
        st.info(f"No KPI assignments found for {selected_year}")
        return
    
    # Group by KPI Center
    for center_id in assignments_df['kpi_center_id'].unique():
        center_data = assignments_df[assignments_df['kpi_center_id'] == center_id]
        center_name = center_data.iloc[0]['kpi_center_name']
        center_type = center_data.iloc[0]['kpi_center_type']
        
        # Get weight sum
        weight_row = weight_summary_df[weight_summary_df['kpi_center_id'] == center_id]
        total_weight = int(weight_row['total_weight'].iloc[0]) if not weight_row.empty else 0
        kpi_count = len(center_data)
        
        # Determine weight status
        if total_weight == 100:
            weight_badge = "✅"
            weight_color = "normal"
        elif total_weight < 100:
            weight_badge = "⚠️"
            weight_color = "off"
        else:
            weight_badge = "🔴"
            weight_color = "inverse"
        
        icon = KPI_TYPE_ICONS.get(center_type, '📁')
        
        # Card container - like Progress tab
        with st.container(border=True):
            # Header
            header_col1, header_col2 = st.columns([4, 1])
            
            with header_col1:
                st.markdown(f"### {icon} {center_name}")
                st.caption(f"{center_type} • {kpi_count} KPI{'s' if kpi_count > 1 else ''}")
            
            with header_col2:
                st.metric(
                    label="Weight Sum",
                    value=f"{total_weight}%",
                    delta=weight_badge,
                    delta_color=weight_color,
                    help="Total weight should equal 100%"
                )
            
            # KPI rows
            for _, kpi in center_data.iterrows():
                _render_kpi_assignment_row(kpi, can_edit, can_delete, setup_queries, selected_year)
            
            # Add KPI button
            if can_edit:
                if st.button(
                    f"➕ Add KPI to {center_name}", 
                    key=f"add_kpi_btn_{center_id}",
                    use_container_width=True
                ):
                    st.session_state['_assignment_dialog_year'] = selected_year
                    st.session_state['_assignment_dialog_center_id'] = center_id
                    _add_assignment_dialog()


def _render_kpi_assignment_row(kpi: pd.Series, can_edit: bool, can_delete: bool, setup_queries: SetupQueries, selected_year: int):
    """
    Render a single KPI assignment row - Updated with dialog triggers.
    
    v2.12.0: Updated to use dialogs instead of session state forms.
    """
    
    kpi_lower = kpi['kpi_name'].lower().replace(' ', '_')
    icon = KPI_ICONS.get(kpi_lower, '📋')
    
    col1, col2, col3, col4, col5 = st.columns([2, 3, 1, 2, 1])
    
    with col1:
        st.markdown(f"**{icon} {kpi['kpi_name']}**")
        # Show assignment ID for reference
        st.caption(f"ID: {kpi['assignment_id']}")
    
    with col2:
        if kpi['unit_of_measure'] == 'USD':
            annual = format_currency(kpi['annual_target_value_numeric'])
            monthly = format_currency(kpi['monthly_target_value'])
        else:
            annual = f"{kpi['annual_target_value_numeric']:,.0f}"
            monthly = f"{kpi['monthly_target_value']:,.1f}"
        
        st.caption(f"Annual: {annual} • Monthly: {monthly}")
    
    with col3:
        st.markdown(f"**{kpi['weight_numeric']:.0f}%** weight")
    
    with col4:
        # Show creator and modifier info
        created_by = kpi.get('created_by_name', '').strip() if pd.notna(kpi.get('created_by_name')) else '-'
        modified_by = kpi.get('modified_by_name', '').strip() if pd.notna(kpi.get('modified_by_name')) else None
        
        if modified_by and modified_by != created_by:
            st.caption(f"👤 {created_by} • ✏️ {modified_by}")
        else:
            st.caption(f"👤 {created_by}")
    
    with col5:
        if can_edit or can_delete:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if can_edit and st.button("✏️", key=f"edit_assign_{kpi['assignment_id']}", help="Edit"):
                    st.session_state['_edit_assignment_id'] = kpi['assignment_id']
                    st.session_state['_assignment_dialog_year'] = selected_year
                    _edit_assignment_dialog()
            with btn_col2:
                if can_delete and st.button("🗑️", key=f"del_assign_{kpi['assignment_id']}", help="Delete"):
                    st.session_state['_delete_assignment_id'] = kpi['assignment_id']
                    _delete_assignment_dialog()


# =============================================================================
# ADD KPI CENTER DIALOG (v2.12.0 - Dialog fashion)
# =============================================================================

@st.dialog("➕ Add KPI Center", width="large")
def _add_center_dialog():
    """
    Dialog for adding a new KPI Center.
    
    v2.12.0: NEW - Converted from inline form to dialog for cleaner UX.
    """
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    setup_queries = SetupQueries(user_id=user_id)
    
    # Form layout
    col1, col2 = st.columns(2)
    
    with col1:
        name = st.text_input(
            "Name *",
            value="",
            key="dialog_center_name"
        )
    
    with col2:
        kpi_type = st.selectbox(
            "Type *",
            options=KPI_TYPES,
            format_func=lambda x: f"{KPI_TYPE_ICONS.get(x, '📁')} {x}",
            key="dialog_center_type"
        )
    
    description = st.text_input(
        "Description",
        value="",
        key="dialog_center_desc"
    )
    
    # Parent selection (filtered by selected type)
    centers_df = setup_queries.get_kpi_centers_for_dropdown(kpi_type=kpi_type)
    
    parent_options = [(0, "No Parent (Root)")] + [
        (row['kpi_center_id'], f"└ {row['kpi_center_name']}")
        for _, row in centers_df.iterrows()
    ]
    
    parent_id = st.selectbox(
        "Parent Center",
        options=[p[0] for p in parent_options],
        format_func=lambda x: next((p[1] for p in parent_options if p[0] == x), ""),
        key="dialog_center_parent"
    )
    
    # Validation
    can_save = True
    if not name or not name.strip():
        st.warning("Name is required")
        can_save = False
    
    # Save button
    st.divider()
    if st.button("💾 Save", type="primary", use_container_width=True, disabled=not can_save):
        result = setup_queries.create_kpi_center(
            name=name.strip(),
            kpi_type=kpi_type,
            description=description.strip() if description else None,
            parent_center_id=parent_id if parent_id > 0 else None
        )
        
        if result['success']:
            st.toast("✅ Created successfully!", icon="✅")
            st.rerun()  # Close dialog and refresh
        else:
            st.error(result['message'])


# =============================================================================
# EDIT KPI CENTER DIALOG (v2.12.0 - Dialog fashion)
# =============================================================================

@st.dialog("✏️ Edit KPI Center", width="large")
def _edit_center_dialog():
    """
    Dialog for editing an existing KPI Center.
    
    v2.12.0: NEW - Converted from inline form to dialog for cleaner UX.
    """
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    center_id = st.session_state.get('_edit_center_id')
    
    if not center_id:
        st.error("No center selected for editing. Please close this dialog and try again.")
        return
    
    setup_queries = SetupQueries(user_id=user_id)
    
    # Get existing center data
    existing = setup_queries.get_kpi_center_detail(center_id)
    
    if not existing:
        st.error(f"Center #{center_id} not found. Please close this dialog and try again.")
        return
    
    # Header info
    st.markdown(f"**KPI Center #{center_id}**")
    st.caption(f"📍 {existing['kpi_type']} • {existing.get('description', 'No description')}")
    
    st.divider()
    
    # Form layout
    col1, col2 = st.columns(2)
    
    with col1:
        name = st.text_input(
            "Name *",
            value=existing['kpi_center_name'],
            key="dialog_edit_center_name"
        )
    
    with col2:
        # Type is read-only in edit mode
        kpi_type = existing['kpi_type']
        st.text_input("Type", value=f"{KPI_TYPE_ICONS.get(kpi_type, '📁')} {kpi_type}", disabled=True)
    
    description = st.text_input(
        "Description",
        value=existing.get('description', '') or '',
        key="dialog_edit_center_desc"
    )
    
    # Parent selection (filtered by same type, exclude self and descendants)
    centers_df = setup_queries.get_kpi_centers_for_dropdown(
        kpi_type=kpi_type,
        exclude_ids=[center_id]
    )
    
    parent_options = [(0, "No Parent (Root)")] + [
        (row['kpi_center_id'], f"└ {row['kpi_center_name']}")
        for _, row in centers_df.iterrows()
    ]
    
    current_parent = existing.get('parent_center_id', 0) or 0
    default_idx = next((i for i, p in enumerate(parent_options) if p[0] == current_parent), 0)
    
    parent_id = st.selectbox(
        "Parent Center",
        options=[p[0] for p in parent_options],
        index=default_idx,
        format_func=lambda x: next((p[1] for p in parent_options if p[0] == x), ""),
        key="dialog_edit_center_parent"
    )
    
    # Validation
    can_save = True
    if not name or not name.strip():
        st.warning("Name is required")
        can_save = False
    
    # Save button
    st.divider()
    if st.button("💾 Update", type="primary", use_container_width=True, disabled=not can_save):
        result = setup_queries.update_kpi_center(
            kpi_center_id=center_id,
            name=name.strip(),
            description=description.strip() if description else None,
            parent_center_id=parent_id if parent_id > 0 else None
        )
        
        if result['success']:
            st.toast("✅ Updated successfully!", icon="✅")
            st.rerun()  # Close dialog and refresh
        else:
            st.error(result['message'])


# =============================================================================
# HIERARCHY SECTION (v2.12.0 - Updated with dialogs)
# =============================================================================

def hierarchy_section(
    setup_queries: SetupQueries,
    can_edit: bool = False
):
    """
    Hierarchy sub-tab with tree view.
    
    v2.12.0: Updated with dialog fashion for CRUD operations.
    v2.10.1: Removed @st.fragment decorator to fix nested fragment bug.
    """
    
    # Toolbar
    col1, col2 = st.columns([1, 5])
    
    with col1:
        if can_edit:
            if st.button("➕ Add Center", type="primary"):
                _add_center_dialog()
    
    with col2:
        expand_all = st.checkbox("Expand All", value=True, key="hier_expand_all")
    
    st.divider()
    
    # Get hierarchy
    hierarchy_df = setup_queries.get_kpi_center_hierarchy(include_stats=True)
    
    if hierarchy_df.empty:
        st.info("No KPI Centers found")
        return
    
    # Group by KPI Type
    for kpi_type in hierarchy_df['kpi_type'].dropna().unique():
        type_df = hierarchy_df[hierarchy_df['kpi_type'] == kpi_type].copy()
        icon = KPI_TYPE_ICONS.get(kpi_type, '📁')
        
        with st.expander(f"{icon} {kpi_type} ({len(type_df)} centers)", expanded=expand_all):
            # Build tree structure: render parents first, then their children
            _render_hierarchy_tree(type_df, can_edit, setup_queries, parent_id=None, level=0)


def _render_hierarchy_tree(df: pd.DataFrame, can_edit: bool, setup_queries: SetupQueries, 
                           parent_id: int = None, level: int = 0):
    """
    Recursively render hierarchy tree with proper parent-child grouping.
    
    Args:
        df: DataFrame containing all centers for this KPI type
        can_edit: Whether user can edit
        setup_queries: Query handler
        parent_id: Current parent ID (None for root level)
        level: Current indentation level
    """
    # Get nodes at this level (matching parent_id)
    if parent_id is None:
        # Root level: get nodes with no parent or parent_center_id is NULL
        current_level = df[df['parent_center_id'].isna() | (df['parent_center_id'] == 0)]
    else:
        current_level = df[df['parent_center_id'] == parent_id]
    
    # Sort by name
    current_level = current_level.sort_values('kpi_center_name')
    
    for _, row in current_level.iterrows():
        # Render this node
        _render_hierarchy_node(row, can_edit, setup_queries, level)
        
        # Recursively render children
        children = df[df['parent_center_id'] == row['kpi_center_id']]
        if not children.empty:
            _render_hierarchy_tree(df, can_edit, setup_queries, 
                                  parent_id=row['kpi_center_id'], level=level + 1)


def _render_hierarchy_node(row: pd.Series, can_edit: bool, setup_queries: SetupQueries, level: int = 0):
    """
    Render a single hierarchy node with proper indentation.
    
    v2.12.0: Updated to use dialog instead of session state form.
    """
    
    # Visual indent using CSS margin
    indent_px = level * 24
    has_children = row['children_count'] > 0
    
    # Icons based on level and children
    if level == 0:
        node_icon = "📁" if has_children else "📄"
    else:
        node_icon = "┗━ 📁" if has_children else "┗━ 📄"
    
    # Container with indent
    with st.container():
        col1, col2, col3 = st.columns([4, 2, 1])
        
        with col1:
            # Apply indentation
            name_display = row['kpi_center_name']
            if has_children:
                name_display = f"**{name_display}** ({row['children_count']} children)"
            
            if level > 0:
                st.markdown(
                    f"<div style='margin-left: {indent_px}px;'>{node_icon} {name_display}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(f"{node_icon} {name_display}")
        
        with col2:
            stats_parts = []
            if row.get('assignment_count', 0) > 0:
                stats_parts.append(f"{int(row['assignment_count'])} KPIs")
            if row.get('split_count', 0) > 0:
                stats_parts.append(f"{int(row['split_count'])} splits")
            
            if stats_parts:
                st.caption(" | ".join(stats_parts))
            else:
                st.caption("No data")
        
        with col3:
            if can_edit:
                if st.button("✏️", key=f"edit_hier_{row['kpi_center_id']}", help="Edit"):
                    st.session_state['_edit_center_id'] = row['kpi_center_id']
                    _edit_center_dialog()