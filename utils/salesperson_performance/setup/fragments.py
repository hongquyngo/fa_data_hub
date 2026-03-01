# utils/salesperson_performance/setup/fragments.py
"""
UI Fragments for Setup Tab - Salesperson Performance

3 Sub-tabs:
1. Split Rules - CRUD for sales_split_by_customer_product
2. KPI Assignments - CRUD for sales_employee_kpi_assignments
3. Salespeople - List/manage salespeople

v2.2.1: FIX - Edit Split Rule dialog shows wrong salesperson:
        - Streamlit persists selectbox values by key in session_state
        - Opening Edit for rule A then rule B would show rule A's salesperson
        - Fix: detect rule_id change and clear stale form widget keys
        - Affects: sale_person_id, split_pct, valid_from, valid_to, is_approved
v2.0.3: FIX - Add KPI Assignment dialog batch queue:
        - "Add to Queue" now uses callback pattern (on_click)
        - Callback runs BEFORE re-render → batch queue updates immediately
        - No full page rerun, dialog stays open smoothly
        - Removed _kpi_reopen_dialog flag (no longer needed)
v2.0.2: (Deprecated) Used reopen flag pattern with full page rerun
v2.0.1: FIX - KPI Type selector moved outside form for immediate UI update
v2.0.0: KPI Assignments refactored with Modal/Dialog pattern
        - Batch Add support
        - Improved notifications with row highlighting
        - Delete confirmation dialog
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from .queries import SalespersonSetupQueries


# =============================================================================
# CONSTANTS
# =============================================================================

KPI_ICONS = {
    'revenue': '💰',
    'gross_profit': '📈',
    'gross_profit_1': '📊',
    'gp1': '📊',
    'num_new_customers': '👥',
    'num_new_products': '📦',
    'new_business_revenue': '💼',
    'num_new_projects': '🎯',
}

STATUS_ICONS = {
    'ACTIVE': '🟢',
    'INACTIVE': '🟡',
    'TERMINATED': '🔴',
    'ON_LEAVE': '🟠',
}


# =============================================================================
# NOTIFICATION SYSTEM (v1.8.0 - NEW)
# =============================================================================

def _set_notification(
    notification_key: str,
    ntype: str, 
    message: str, 
    details: str = None,
    affected_ids: List[int] = None
):
    """
    Set notification to display after rerun.
    
    Args:
        notification_key: Session state key for this notification area
        ntype: 'success', 'error', 'warning', 'info'
        message: Main notification message
        details: Optional additional details
        affected_ids: List of IDs that were affected (for row highlighting)
    """
    st.session_state[notification_key] = {
        'type': ntype,
        'message': message,
        'details': details,
        'affected_ids': set(affected_ids) if affected_ids else set(),
        'timestamp': datetime.now()
    }


def _show_notification(notification_key: str, auto_clear: bool = True) -> set:
    """
    Display persistent notification banner.
    
    Args:
        notification_key: Session state key for this notification area
        auto_clear: If True, clear notification after display
        
    Returns:
        Set of affected IDs for row highlighting
    """
    notif = st.session_state.get(notification_key)
    affected_ids = set()
    
    if notif:
        ntype = notif.get('type', 'info')
        message = notif.get('message', '')
        details = notif.get('details', '')
        affected_ids = notif.get('affected_ids', set())
        timestamp = notif.get('timestamp')
        
        # Format timestamp
        time_str = timestamp.strftime('%H:%M:%S') if timestamp else ''
        
        # Display notification with appropriate style
        if ntype == 'success':
            st.success(f"✅ **{message}**")
            if details:
                st.caption(f"ℹ️ {details} • {time_str}")
        elif ntype == 'error':
            st.error(f"❌ **{message}**")
            if details:
                st.caption(f"⚠️ {details}")
        elif ntype == 'warning':
            st.warning(f"⚠️ **{message}**")
            if details:
                st.caption(details)
        else:
            st.info(f"ℹ️ **{message}**")
            if details:
                st.caption(details)
        
        # Clear after display
        if auto_clear:
            del st.session_state[notification_key]
    
    return affected_ids


# =============================================================================
# DATA CACHING SYSTEM (v1.9.0 - NEW)
# =============================================================================
# Version-based caching to ensure data refresh after CRUD operations.
# Each data type (split, kpi) has its own version counter.
# When CRUD succeeds, version is bumped, causing cache miss on next render.

def _get_data_version(data_type: str) -> int:
    """
    Get current data version for cache invalidation.
    
    Args:
        data_type: 'split' or 'kpi'
        
    Returns:
        Current version number (starts at 0)
    """
    return st.session_state.get(f'_setup_{data_type}_version', 0)


def _bump_data_version(data_type: str):
    """
    Increment version to invalidate cache after CRUD operation.
    
    Call this after successful create/update/delete operations.
    Next render will fetch fresh data from database.
    
    Args:
        data_type: 'split' or 'kpi'
    """
    key = f'_setup_{data_type}_version'
    current = st.session_state.get(key, 0)
    st.session_state[key] = current + 1
    
    # Also clear any cached data for this type
    keys_to_clear = [k for k in st.session_state.keys() 
                     if k.startswith(f'_setup_{data_type}_cache')]
    for k in keys_to_clear:
        del st.session_state[k]


def _get_cached_split_data(
    setup_queries: SalespersonSetupQueries,
    query_params: Dict,
    force_refresh: bool = False
) -> pd.DataFrame:
    """
    Get split data with version-based caching.
    
    Cache is automatically invalidated when:
    - Version changes (after CRUD operations)
    - Query params change (filters changed)
    - force_refresh=True
    
    Args:
        setup_queries: Query handler instance
        query_params: Dict of filter parameters
        force_refresh: Force fresh fetch even if cached
        
    Returns:
        DataFrame with split rules data
    """
    version = _get_data_version('split')
    
    # Create deterministic hash of params for cache key
    # Sort to ensure consistent ordering
    params_items = []
    for k, v in sorted(query_params.items()):
        if isinstance(v, (list, tuple)):
            params_items.append((k, tuple(sorted(v)) if v else ()))
        elif isinstance(v, date):
            params_items.append((k, v.isoformat()))
        else:
            params_items.append((k, v))
    params_hash = hash(tuple(params_items))
    
    cache_key = f'_setup_split_cache_v{version}'
    params_key = f'_setup_split_params_v{version}'
    
    cached_params_hash = st.session_state.get(params_key)
    
    need_refresh = (
        force_refresh or
        cache_key not in st.session_state or
        cached_params_hash != params_hash
    )
    
    if need_refresh:
        # Fetch fresh data from database
        split_df = setup_queries.get_sales_split_data(**query_params)
        st.session_state[cache_key] = split_df
        st.session_state[params_key] = params_hash
    
    return st.session_state[cache_key]


def _get_cached_kpi_data(
    setup_queries: SalespersonSetupQueries,
    year: int,
    employee_ids: List[int] = None,
    force_refresh: bool = False
) -> pd.DataFrame:
    """
    Get KPI assignments data with version-based caching.
    
    Args:
        setup_queries: Query handler instance
        year: Year to filter
        employee_ids: Optional list of employee IDs to filter
        force_refresh: Force fresh fetch
        
    Returns:
        DataFrame with KPI assignments
    """
    version = _get_data_version('kpi')
    
    # Create cache key including params
    emp_hash = hash(tuple(sorted(employee_ids))) if employee_ids else 0
    cache_key = f'_setup_kpi_cache_v{version}_y{year}_e{emp_hash}'
    
    if force_refresh or cache_key not in st.session_state:
        query_params = {'year': year}
        if employee_ids:
            query_params['employee_ids'] = employee_ids
        
        kpi_df = setup_queries.get_kpi_assignments(**query_params)
        st.session_state[cache_key] = kpi_df
    
    return st.session_state[cache_key]


def _clear_all_setup_cache():
    """
    Clear all setup-related cache.
    
    Use when major changes happen that affect multiple data types.
    """
    keys_to_clear = [k for k in list(st.session_state.keys()) 
                     if k.startswith('_setup_') and 'cache' in k]
    for k in keys_to_clear:
        del st.session_state[k]
    
    # Reset versions
    st.session_state['_setup_split_version'] = 0
    st.session_state['_setup_kpi_version'] = 0


# =============================================================================
# AUTHORIZATION HELPERS (v1.2.0)
# =============================================================================

def can_modify_record(
    record_owner_id: int,
    access_level: str,
    accessible_employee_ids: List[int] = None
) -> bool:
    """
    Check if current user can modify a specific record.
    
    Authorization rules (Option C: Hybrid):
    - admin (full): Can modify ALL records
    - sales_manager (team): Can modify records owned by team members
    - sales (self): Can only modify own records
    
    Args:
        record_owner_id: Employee ID who owns the record (sale_person_id)
        access_level: 'full', 'team', or 'self'
        accessible_employee_ids: List of employee IDs user can access
        
    Returns:
        True if user can modify this record
    """
    if access_level == 'full':
        return True  # Admin can modify all
    
    if accessible_employee_ids is None:
        return True  # Full access (shouldn't happen but safety check)
    
    return record_owner_id in accessible_employee_ids


def get_editable_employee_ids(
    access_level: str,
    accessible_employee_ids: List[int] = None,
    user_employee_id: int = None
) -> List[int]:
    """
    Get list of employee IDs that user can CREATE/EDIT records FOR.
    
    This determines which salespeople appear in dropdown when creating new rules.
    
    Args:
        access_level: 'full', 'team', or 'self'
        accessible_employee_ids: List of employee IDs user can access
        user_employee_id: Current user's employee ID
        
    Returns:
        List of employee IDs user can create/edit records for
    """
    if access_level == 'full':
        return None  # None means all (no filter)
    
    if access_level == 'team':
        return accessible_employee_ids  # Can create for team members
    
    # 'self' access - can only create for themselves
    return [user_employee_id] if user_employee_id else []


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _render_authorization_info(current_role: str):
    """
    Render authorization matrix info in popover.
    
    v1.4.2: Shows role-based permissions with current user highlighted.
    """
    st.markdown("#### 🔐 Authorization Matrix")
    st.caption("Your current role is highlighted")
    
    # Define authorization matrix
    auth_matrix = {
        'admin': {
            'label': '👑 Admin',
            'scope': 'All Records',
            'view': '✅', 'create': '✅', 'edit': '✅', 'delete': '✅', 'approve': '✅',
            'notes': 'Full access to all records and approval'
        },
        'sales_manager': {
            'label': '👔 Sales Manager',
            'scope': 'Team Members',
            'view': '✅', 'create': '✅', 'edit': '✅', 'delete': '✅', 'approve': '✅',
            'notes': 'CRUD + Approve for team members only'
        },
        'gm': {
            'label': '🏢 GM',
            'scope': 'All Records',
            'view': '✅', 'create': '✅', 'edit': '✅', 'delete': '✅', 'approve': '❌',
            'notes': 'Full CRUD but cannot approve'
        },
        'md': {
            'label': '🏢 MD',
            'scope': 'All Records',
            'view': '✅', 'create': '✅', 'edit': '✅', 'delete': '✅', 'approve': '❌',
            'notes': 'Full CRUD but cannot approve'
        },
        'director': {
            'label': '🏢 Director',
            'scope': 'All Records',
            'view': '✅', 'create': '✅', 'edit': '✅', 'delete': '✅', 'approve': '❌',
            'notes': 'Full CRUD but cannot approve'
        },
        'sales': {
            'label': '💼 Sales',
            'scope': 'Own Records',
            'view': '✅', 'create': '✅*', 'edit': '✅*', 'delete': '✅', 'approve': '❌',
            'notes': '* Created/edited records are Pending approval'
        },
        'viewer': {
            'label': '👁️ Viewer',
            'scope': 'View Only',
            'view': '✅', 'create': '❌', 'edit': '❌', 'delete': '❌', 'approve': '❌',
            'notes': 'Read-only access'
        },
    }
    
    # Show current user's permissions first
    current_role_lower = current_role.lower()
    if current_role_lower in auth_matrix:
        info = auth_matrix[current_role_lower]
        st.success(f"**Your Role: {info['label']}**")
        st.markdown(f"**Scope:** {info['scope']}")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("View", info['view'])
        col2.metric("Create", info['create'])
        col3.metric("Edit", info['edit'])
        col4.metric("Delete", info['delete'])
        col5.metric("Approve", info['approve'])
        
        if info.get('notes'):
            st.caption(f"📝 {info['notes']}")
    else:
        st.warning(f"Unknown role: {current_role}")
    
    st.divider()
    
    # Show full matrix
    with st.expander("📋 View All Roles", expanded=False):
        # Build table data
        table_data = []
        for role_key, info in auth_matrix.items():
            is_current = (role_key == current_role_lower)
            row = {
                'Role': f"**{info['label']}**" if is_current else info['label'],
                'Scope': info['scope'],
                'View': info['view'],
                'Create': info['create'],
                'Edit': info['edit'],
                'Delete': info['delete'],
                'Approve': info['approve'],
            }
            table_data.append(row)
        
        st.dataframe(
            table_data,
            hide_index=True,
            use_container_width=True,
            column_config={
                'Role': st.column_config.TextColumn('Role', width='medium'),
                'Scope': st.column_config.TextColumn('Scope', width='medium'),
                'View': st.column_config.TextColumn('View', width='small'),
                'Create': st.column_config.TextColumn('Create', width='small'),
                'Edit': st.column_config.TextColumn('Edit', width='small'),
                'Delete': st.column_config.TextColumn('Delete', width='small'),
                'Approve': st.column_config.TextColumn('Approve', width='small'),
            }
        )
        
        st.caption("""
        **Legend:**
        - ✅ = Allowed
        - ✅* = Allowed but record stays Pending
        - ❌ = Not allowed
        """)


def format_currency(value: float, decimals: int = 0) -> str:
    """Format value as USD currency."""
    if pd.isna(value) or value == 0:
        return "$0"
    if decimals > 0:
        return f"${value:,.{decimals}f}"
    return f"${value:,.0f}"


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
    """Get period status: (icon, text, delta_color for st.metric)."""
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


# =============================================================================
# MAIN SETUP TAB FRAGMENT
# =============================================================================

@st.fragment
def setup_tab_fragment(
    sales_split_df: pd.DataFrame = None,  # DEPRECATED v1.9.0 - data fetched internally
    sales_df: pd.DataFrame = None,         # DEPRECATED v1.9.0 - not used
    active_filters: Dict = None,           # DEPRECATED v1.9.0 - uses own filters
    fragment_key: str = "setup"
):
    """
    Main fragment for Setup tab with 3 sub-tabs.
    
    v1.9.0: MAJOR REFACTOR - Self-contained data management
            - Data is now fetched INTERNALLY within each sub-tab
            - Uses version-based caching for CRUD refresh
            - No longer depends on main page's cached data
            - Parameters kept for backward compatibility but IGNORED
    
    v1.2.0: Setup tab now uses AccessControl for employee filtering instead of
            main page's active_filters. This prevents "Only with KPI assignment"
            filter from affecting Setup tab.
    
    Args:
        sales_split_df: DEPRECATED - data fetched internally with caching
        sales_df: DEPRECATED - not used
        active_filters: DEPRECATED - Setup tab has its own filter system
        fragment_key: Unique key for fragment
    """
    # Initialize queries with user context
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    setup_queries = SalespersonSetupQueries(user_id=user_id)
    
    # Get user role for permission check
    user_role = st.session_state.get('user_role', 'viewer')
    user_role_lower = str(user_role).lower() if user_role else ''
    
    # =========================================================================
    # HEADER WITH AUTHORIZATION INFO (v1.4.2)
    # =========================================================================
    header_col1, header_col2 = st.columns([6, 1])
    
    with header_col1:
        st.subheader("⚙️ Salesperson Configuration")
    
    with header_col2:
        # Authorization info popover
        with st.popover("🔐 Permissions", use_container_width=True):
            _render_authorization_info(user_role_lower)
    
    # =========================================================================
    # v1.3.0 (Phase 4): Get default year from MOST RECENT KPI data
    # Instead of using active_filters year, default to year with actual KPI data
    # =========================================================================
    def _get_most_recent_kpi_year() -> int:
        """Get year with most recent KPI assignments, or current year if none."""
        try:
            result = setup_queries.execute_query("""
                SELECT MAX(year) as max_year
                FROM sales_employee_kpi_assignments
                WHERE delete_flag = 0 OR delete_flag IS NULL
            """)
            if result and len(result) > 0 and result[0].get('max_year'):
                return int(result[0]['max_year'])
        except Exception:
            pass
        return date.today().year
    
    # Use session state to cache default year for Setup tab
    if 'setup_default_year' not in st.session_state:
        st.session_state['setup_default_year'] = _get_most_recent_kpi_year()
    
    # Setup tab uses its own year (independent from sidebar filters)
    current_year = st.session_state.get('setup_default_year', date.today().year)
    
    # =========================================================================
    # v1.2.0: Get accessible employees from AccessControl (NOT from active_filters)
    # This prevents "Only with KPI assignment" from affecting Setup tab
    # =========================================================================
    from utils.salesperson_performance import AccessControl
    
    # Get user info from session state
    user_role = st.session_state.get('user_role', 'viewer')
    employee_id = st.session_state.get('employee_id')
    
    access = AccessControl(user_role=user_role, employee_id=employee_id)
    access_level = access.get_access_level()
    
    if access_level == 'full':
        # Admin/GM/MD can see all salespeople
        accessible_employee_ids = None  # None means no filter (all)
    else:
        # Team or Self access - restricted to accessible employees
        accessible_employee_ids = access.get_accessible_employee_ids()
    
    # =========================================================================
    # v1.2.0: Determine EDITABLE scope (who can user CREATE/EDIT records for)
    # - admin (full): All salespeople
    # - sales_manager (team): Team members only
    # - sales (self): View only (no edit permission)
    # =========================================================================
    editable_employee_ids = get_editable_employee_ids(
        access_level=access_level,
        accessible_employee_ids=accessible_employee_ids,
        user_employee_id=employee_id
    )
    
    # =========================================================================
    # v1.3.0 (Phase 3): Store quick stats for sidebar display
    # =========================================================================
    accessible_count = len(accessible_employee_ids) if accessible_employee_ids else None
    editable_count = len(editable_employee_ids) if editable_employee_ids else None
    
    # Store for sidebar to access
    st.session_state['setup_access_info'] = {
        'access_level': access_level,
        'accessible_count': accessible_count,
        'editable_count': editable_count,
    }
    
    # Determine base edit permission by role
    # v1.4.1: sales role can now CRUD their own records (but cannot approve)
    can_edit_base = user_role_lower in ['admin', 'gm', 'md', 'director', 'sales_manager', 'sales']
    
    # v1.4.0: Approve permission
    # - admin: can approve ALL records
    # - sales_manager: can approve for team members only (checked per-record)
    # - sales: CANNOT approve (their records stay pending)
    can_approve = user_role_lower in ['admin', 'sales_manager']
    
    # Get issue counts for tab badges (using accessible scope)
    split_stats = setup_queries.get_split_summary_stats(
        employee_ids=accessible_employee_ids
    )
    split_critical = split_stats.get('over_100_count', 0)
    
    # FIX v1.3.1: Pass accessible_employee_ids to filter by team scope
    assignment_issues = setup_queries.get_assignment_issues_summary(
        current_year,
        employee_ids=accessible_employee_ids
    )
    assign_critical = assignment_issues.get('no_assignment_count', 0) + assignment_issues.get('weight_issues_count', 0)
    
    # =========================================================================
    # v1.3.0 (Phase 3): Store quick stats in session_state for sidebar
    # =========================================================================
    st.session_state['setup_quick_stats'] = {
        'split_rules_count': split_stats.get('total_rules', 0),
        'kpi_year': current_year,
        'kpi_current_year_count': assignment_issues.get('total_assignments', 0),
        'split_critical': split_critical,
        'assign_critical': assign_critical,
    }
    
    # Dynamic tab names with badges
    split_tab_name = f"📋 Split Rules{' 🔴' if split_critical > 0 else ''}"
    assign_tab_name = f"🎯 KPI Assignments{' ⚠️' if assign_critical > 0 else ''}"
    
    # Create 3 sub-tabs
    tab1, tab2, tab3 = st.tabs([
        split_tab_name,
        assign_tab_name, 
        "👥 Salespeople"
    ])
    
    with tab1:
        split_rules_section(
            setup_queries=setup_queries,
            accessible_employee_ids=accessible_employee_ids,
            editable_employee_ids=editable_employee_ids,  # v1.2.0: For record-level auth
            can_edit_base=can_edit_base,  # v1.2.0: Renamed
            can_approve=can_approve,
            access_level=access_level,
            user_employee_id=employee_id  # v1.2.0: For ownership check
        )
    
    with tab2:
        kpi_assignments_section(
            setup_queries=setup_queries,
            employee_ids=accessible_employee_ids,
            editable_employee_ids=editable_employee_ids,  # v1.2.0
            can_edit_base=can_edit_base,  # v1.2.0
            current_year=current_year,
            access_level=access_level,  # v1.2.0
            user_employee_id=employee_id  # v1.2.0
        )
    
    with tab3:
        # FIX v1.3.1: Pass accessible_employee_ids to filter salespeople list
        salespeople_section(
            setup_queries=setup_queries,
            employee_ids=accessible_employee_ids,  # NEW: Filter by team scope
            can_edit=can_edit_base and access_level == 'full'  # Only admin can edit salespeople
        )


# =============================================================================
# SPLIT RULES SECTION (v1.1.0 - Added Audit Trail Filters)
# =============================================================================

@st.fragment
def split_rules_section(
    setup_queries: SalespersonSetupQueries,
    accessible_employee_ids: List[int] = None,
    editable_employee_ids: List[int] = None,  # v1.2.0: Who can user CREATE/EDIT for
    can_edit_base: bool = False,  # v1.2.0: Base permission (role allows editing)
    can_approve: bool = False,
    access_level: str = 'self',
    user_employee_id: int = None  # v1.2.0: For ownership check
):
    """
    Split Rules sub-tab with CRUD operations and comprehensive filters.
    
    v1.9.0: REFACTOR - Self-contained data fetching with version-based cache
            - Data fetched internally using _get_cached_split_data()
            - Cache invalidated automatically after CRUD via _bump_data_version()
            - Fragment rerun now correctly shows fresh data
    
    v1.1.0: Added Audit Trail filter group (Created By, Approved By, Date Ranges)
    v1.2.0: Hybrid authorization (Option C):
            - admin (full): CRUD all records
            - sales_manager (team): CRUD for team members only
            - sales (self): CRUD only own records
    
    Args:
        setup_queries: Query handler
        accessible_employee_ids: List of employee IDs user can VIEW (None = all)
        editable_employee_ids: List of employee IDs user can CREATE/EDIT FOR (None = all)
        can_edit_base: Whether user's role allows editing at all
        can_approve: Whether user can approve rules
        access_level: 'full', 'team', or 'self'
        user_employee_id: Current user's employee ID
    """
    
    # Helper to check if user can modify a specific record
    def can_modify_this_record(record_owner_id: int) -> bool:
        """Check if current user can edit/delete this specific record."""
        if not can_edit_base:
            return False
        return can_modify_record(record_owner_id, access_level, editable_employee_ids)
    
    # =========================================================================
    # HELPER: Build query params from filter state
    # =========================================================================
    def get_current_filter_params():
        """
        Build query params from current filter state.
        
        v1.2.0: Changed to use Setup tab's own salesperson filter instead of
                main page's employee_ids. Applies accessible_employee_ids constraint.
        """
        params = {}
        
        # Period filters
        period_type = st.session_state.get('sp_split_period_type', 'full_year')
        period_year = st.session_state.get('sp_split_period_year', date.today().year)
        
        if period_type == 'ytd':
            params['period_start'] = date(period_year, 1, 1)
            params['period_end'] = date.today()
        elif period_type == 'full_year':
            params['period_year'] = period_year
        elif period_type == 'custom':
            custom_start = st.session_state.get('sp_split_period_start')
            custom_end = st.session_state.get('sp_split_period_end')
            if custom_start:
                params['period_start'] = custom_start
            if custom_end:
                params['period_end'] = custom_end
        
        # =====================================================================
        # v1.2.0: Salesperson filter - Setup tab's own filter
        # Note: selectbox returns single value (-1 = All, or specific employee_id)
        # =====================================================================
        sp_filter = st.session_state.get('sp_split_salesperson_filter', -1)
        
        if sp_filter and sp_filter != -1:
            # User selected a specific salesperson
            # Apply accessible constraint if not full access
            if accessible_employee_ids is not None:
                # Verify selected person is in accessible scope
                if sp_filter in accessible_employee_ids:
                    params['employee_ids'] = [sp_filter]
                else:
                    # Fallback to all accessible (shouldn't happen with proper UI)
                    params['employee_ids'] = accessible_employee_ids
            else:
                params['employee_ids'] = [sp_filter]
        elif accessible_employee_ids is not None:
            # "All" selected but user has restricted access
            params['employee_ids'] = accessible_employee_ids
        # else: Full access, "All" selected = show all (no filter)
        
        # Entity filters - Brand
        brand_filter = st.session_state.get('sp_split_brand_filter', [])
        if brand_filter:
            params['brand_ids'] = brand_filter
        
        # v1.5.2: Entity filters - Customer (multiselect)
        customer_filter = st.session_state.get('sp_split_customer_filter', [])
        if customer_filter:
            params['customer_ids'] = customer_filter
        
        # v1.5.2: Entity filters - Product (multiselect)
        product_filter = st.session_state.get('sp_split_product_filter', [])
        if product_filter:
            params['product_ids'] = product_filter
        
        # Rule attribute filters
        status_filter = st.session_state.get('sp_split_status_filter')
        if status_filter and status_filter != 'all':
            params['status_filter'] = status_filter
        
        approval_filter = st.session_state.get('sp_split_approval_filter')
        if approval_filter and approval_filter != 'all':
            params['approval_filter'] = approval_filter
        
        split_min = st.session_state.get('sp_split_pct_min')
        split_max = st.session_state.get('sp_split_pct_max')
        if split_min is not None and split_min > 0:
            params['split_min'] = split_min
        if split_max is not None and split_max < 100:
            params['split_max'] = split_max
        
        # Audit trail filters (v1.1.0 - NEW, v1.4.2 - FIXED)
        created_by = st.session_state.get('sp_split_created_by_filter')
        if created_by and created_by > 0:
            params['created_by_employee_id'] = created_by
        
        approved_by = st.session_state.get('sp_split_approved_by_filter')
        if approved_by and approved_by > 0:
            params['approved_by_employee_id'] = approved_by
        
        created_from = st.session_state.get('sp_split_created_date_from')
        if created_from:
            params['created_date_from'] = created_from
        
        created_to = st.session_state.get('sp_split_created_date_to')
        if created_to:
            params['created_date_to'] = created_to
        
        modified_from = st.session_state.get('sp_split_modified_date_from')
        if modified_from:
            params['modified_date_from'] = modified_from
        
        modified_to = st.session_state.get('sp_split_modified_date_to')
        if modified_to:
            params['modified_date_to'] = modified_to
        
        # System filters
        include_deleted = st.session_state.get('sp_split_show_deleted', False)
        params['include_deleted'] = include_deleted
        
        return params
    
    # =========================================================================
    # FILTERS (v1.1.0 - 5 Filter Groups like KPI Center)
    # =========================================================================
    with st.expander("🔍 Filters", expanded=True):
        
        # ROW 1: Period Filters
        st.markdown("##### 📅 Validity Period")
        
        p_col1, p_col2, p_col3, p_col4 = st.columns([1, 1, 1, 1])
        
        with p_col1:
            available_years = setup_queries.get_split_rule_years()
            current_year = date.today().year
            
            period_year = st.selectbox(
                "Year",
                options=available_years,
                index=available_years.index(current_year) if current_year in available_years else 0,
                key="sp_split_period_year"
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
                index=1,
                key="sp_split_period_type"
            )
        
        with p_col3:
            default_start = date(period_year, 1, 1)
            period_start = st.date_input(
                "From",
                value=default_start,
                disabled=(period_type != 'custom'),
                key="sp_split_period_start"
            )
        
        with p_col4:
            default_end = date(period_year, 12, 31)
            period_end = st.date_input(
                "To",
                value=default_end,
                disabled=(period_type != 'custom'),
                key="sp_split_period_end"
            )
        
        st.divider()
        
        # ROW 2: Entity Filters
        st.markdown("##### 🏢 Entity Filters")
        
        e_col1, e_col2, e_col3, e_col4 = st.columns(4)
        
        # v1.2.0: Salesperson filter - Setup tab's own filter
        with e_col1:
            # Get salespeople within accessible scope
            salespeople_df = setup_queries.get_salespeople_for_dropdown(include_inactive=True)
            
            # Filter to accessible scope if restricted
            if accessible_employee_ids is not None:
                salespeople_df = salespeople_df[
                    salespeople_df['employee_id'].isin(accessible_employee_ids)
                ]
            
            if not salespeople_df.empty:
                sp_options = [(-1, "👥 All Salespeople")] + [
                    (row['employee_id'], f"👤 {row['employee_name']}") 
                    for _, row in salespeople_df.iterrows()
                ]
                
                # Determine label based on access level
                if access_level == 'full':
                    filter_label = "Salesperson"
                elif access_level == 'team':
                    filter_label = f"Team Member ({len(salespeople_df)})"
                else:
                    filter_label = "Your Data"
                
                st.selectbox(
                    filter_label,
                    options=[s[0] for s in sp_options],
                    format_func=lambda x: next((s[1] for s in sp_options if s[0] == x), "All"),
                    key="sp_split_salesperson_filter",
                    help="Filter rules by salesperson (within your access scope)"
                )
            else:
                st.info("No salespeople available")
        
        with e_col2:
            brands_df = setup_queries.get_brands_for_dropdown()
            brand_options = brands_df['brand_id'].tolist() if not brands_df.empty else []
            
            brand_filter = st.multiselect(
                "Brand",
                options=brand_options,
                format_func=lambda x: brands_df[brands_df['brand_id'] == x]['brand_name'].iloc[0] if not brands_df.empty else str(x),
                placeholder="All Brands",
                key="sp_split_brand_filter"
            )
        
        # v1.5.2: Customer multiselect (only customers with split rules)
        with e_col3:
            customers_df = setup_queries.get_customers_with_splits(
                employee_ids=accessible_employee_ids
            )
            
            if not customers_df.empty:
                customer_options = customers_df['customer_id'].tolist()
                st.multiselect(
                    "Customer",
                    options=customer_options,
                    format_func=lambda x: customers_df[customers_df['customer_id'] == x]['display_name'].iloc[0] if x in customer_options else str(x),
                    placeholder="All Customers",
                    key="sp_split_customer_filter",
                    help=f"{len(customer_options)} customers with split rules"
                )
            else:
                st.multiselect("Customer", options=[], placeholder="No customers", disabled=True)
        
        # v1.5.2: Product multiselect (only products with split rules)
        with e_col4:
            products_df = setup_queries.get_products_with_splits(
                employee_ids=accessible_employee_ids
            )
            
            if not products_df.empty:
                product_options = products_df['product_id'].tolist()
                st.multiselect(
                    "Product",
                    options=product_options,
                    format_func=lambda x: products_df[products_df['product_id'] == x]['display_name'].iloc[0] if x in product_options else str(x),
                    placeholder="All Products",
                    key="sp_split_product_filter",
                    help=f"{len(product_options)} products with split rules"
                )
            else:
                st.multiselect("Product", options=[], placeholder="No products", disabled=True)
        
        st.divider()
        
        # ROW 3: Rule Attributes
        st.markdown("##### 📊 Rule Attributes")
        
        r_col1, r_col2, r_col3, r_col4 = st.columns(4)
        
        with r_col1:
            split_min = st.number_input(
                "Split % Min",
                min_value=0,
                max_value=100,
                value=0,
                step=10,
                key="sp_split_pct_min"
            )
        
        with r_col2:
            split_max = st.number_input(
                "Split % Max",
                min_value=0,
                max_value=100,
                value=100,
                step=10,
                key="sp_split_pct_max"
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
                key="sp_split_status_filter"
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
                key="sp_split_approval_filter"
            )
        
        st.divider()
        
        # ROW 4: Audit Trail Filters (v1.1.0 - NEW)
        st.markdown("##### 👤 Audit Trail")
        
        a_col1, a_col2, a_col3, a_col4 = st.columns(4)
        
        with a_col1:
            # Created By dropdown (v1.4.2: Fixed - uses employees via keycloak_id)
            creators_df = setup_queries.get_creators_for_dropdown()
            creator_options = [(-1, "All Creators")] + [
                (row['employee_id'], row['employee_name']) 
                for _, row in creators_df.iterrows()
            ] if not creators_df.empty else [(-1, "All Creators")]
            
            created_by_filter = st.selectbox(
                "Created By",
                options=[c[0] for c in creator_options],
                format_func=lambda x: next((c[1] for c in creator_options if c[0] == x), "All Creators"),
                key="sp_split_created_by_filter"
            )
        
        with a_col2:
            # Approved By dropdown
            approvers_df = setup_queries.get_approvers_for_dropdown()
            approver_options = [(-1, "All Approvers")] + [
                (row['employee_id'], row['employee_name']) 
                for _, row in approvers_df.iterrows()
            ] if not approvers_df.empty else [(-1, "All Approvers")]
            
            approved_by_filter = st.selectbox(
                "Approved By",
                options=[a[0] for a in approver_options],
                format_func=lambda x: next((a[1] for a in approver_options if a[0] == x), "All Approvers"),
                key="sp_split_approved_by_filter"
            )
        
        with a_col3:
            # Created Date Range
            created_date_from = st.date_input(
                "Created From",
                value=None,
                key="sp_split_created_date_from"
            )
        
        with a_col4:
            created_date_to = st.date_input(
                "Created To",
                value=None,
                key="sp_split_created_date_to"
            )
        
        # Modified date row
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        
        with m_col1:
            modified_date_from = st.date_input(
                "Modified From",
                value=None,
                key="sp_split_modified_date_from"
            )
        
        with m_col2:
            modified_date_to = st.date_input(
                "Modified To",
                value=None,
                key="sp_split_modified_date_to"
            )
        
        st.divider()
        
        # ROW 5: System Filters
        st.markdown("##### ⚙️ System")
        
        sys_col1, sys_col2, sys_col3 = st.columns([2, 1, 1])
        
        with sys_col1:
            # NOTE: View has built-in WHERE delete_flag=0, so this checkbox
            # cannot actually show deleted records. Kept disabled for UI consistency.
            show_deleted = st.checkbox(
                "🗑️ Show deleted rules",
                value=False,
                key="sp_split_show_deleted",
                help="⚠️ Not available: View filters out deleted records",
                disabled=True  # Cannot show deleted with current view
            )
        
        with sys_col2:
            if st.button("🔄 Reset Filters", use_container_width=True):
                keys_to_reset = [
                    'sp_split_period_year', 'sp_split_period_type', 'sp_split_period_start', 'sp_split_period_end',
                    'sp_split_salesperson_filter',
                    'sp_split_brand_filter', 'sp_split_customer_filter', 'sp_split_product_filter',  # v1.5.2: Updated
                    'sp_split_pct_min', 'sp_split_pct_max', 'sp_split_status_filter', 'sp_split_approval_filter',
                    'sp_split_created_by_filter', 'sp_split_approved_by_filter',
                    'sp_split_created_date_from', 'sp_split_created_date_to',
                    'sp_split_modified_date_from', 'sp_split_modified_date_to',
                    'sp_split_show_deleted'
                ]
                for key in keys_to_reset:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun(scope="fragment")
        
        with sys_col3:
            # Count active filters
            sp_filter_val = st.session_state.get('sp_split_salesperson_filter', -1)
            customer_filter_val = st.session_state.get('sp_split_customer_filter', [])
            product_filter_val = st.session_state.get('sp_split_product_filter', [])
            active_filter_count = sum([
                period_type != 'all',
                sp_filter_val != -1 if sp_filter_val else False,
                len(brand_filter) > 0,
                len(customer_filter_val) > 0,  # v1.5.2: Updated
                len(product_filter_val) > 0,   # v1.5.2: Updated
                split_min > 0,
                split_max < 100,
                status_filter != 'all',
                approval_filter != 'all',
                created_by_filter > 0 if created_by_filter else False,
                approved_by_filter > 0 if approved_by_filter else False,
                created_date_from is not None,
                created_date_to is not None,
                modified_date_from is not None if 'modified_date_from' in dir() else False,
                modified_date_to is not None if 'modified_date_to' in dir() else False,
                show_deleted
            ])
            st.metric("Active Filters", active_filter_count)
    
    # =========================================================================
    # GET FILTER PARAMS
    # =========================================================================
    query_params = get_current_filter_params()
    
    # =========================================================================
    # SUMMARY METRICS (v1.2.0: Now synced with data table via employee_ids)
    # =========================================================================
    stats = setup_queries.get_split_summary_stats(
        period_year=query_params.get('period_year'),
        period_start=query_params.get('period_start'),
        period_end=query_params.get('period_end'),
        include_deleted=query_params.get('include_deleted', False),
        employee_ids=query_params.get('employee_ids')  # v1.2.0: Sync with data table
    )
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
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
    with col6:
        st.metric(
            label="⏰ Expiring",
            value=f"{stats['expiring_soon_count']:,}",
            help="Rules expiring within 30 days"
        )
    
    st.divider()
    
    # =========================================================================
    # TOOLBAR (v1.7.0: Using dialogs instead of inline forms)
    # =========================================================================
    # Get user_id from session state for dialog context
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    
    # Store context for dialogs to access
    st.session_state['_split_dialog_context'] = {
        'user_id': user_id,
        'can_approve': can_approve,
        'editable_employee_ids': editable_employee_ids,
        'access_level': access_level
    }
    
    if can_edit_base:
        if st.button("➕ Add Split Rule", type="primary"):
            _add_split_rule_dialog()
    
    # =========================================================================
    # RESULTS SUMMARY - Build period description
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
    
    # =========================================================================
    # v1.9.0: Pass query_params to nested fragment for internal data fetching
    # This ensures CRUD operations trigger fresh data fetch on fragment rerun
    # =========================================================================
    _render_split_data_table(
        setup_queries=setup_queries,
        query_params=query_params,
        period_desc=period_desc,
        can_edit_base=can_edit_base,
        can_approve=can_approve,
        editable_employee_ids=editable_employee_ids,
        access_level=access_level
    )


@st.fragment
def _render_split_data_table(
    setup_queries: SalespersonSetupQueries,
    query_params: Dict,
    period_desc: str,
    can_edit_base: bool,
    can_approve: bool,
    editable_employee_ids: List[int],
    access_level: str
):
    """
    v1.9.0: REFACTORED - Now fetches data internally for proper CRUD refresh.
    v1.5.2: Nested fragment for data table and action bar.
    v1.8.0: Added notification banner and row highlighting.
    This allows row selection to only rerun this section, not the entire filters.
    
    Data is now fetched INSIDE this fragment using version-based caching.
    When CRUD operations call _bump_data_version() and st.rerun(scope="fragment"),
    this fragment will re-fetch fresh data from the database.
    """
    # =========================================================================
    # v1.8.0: Show notification banner (persists after action)
    # =========================================================================
    NOTIF_KEY = '_split_rules_notification'
    highlighted_ids = _show_notification(NOTIF_KEY)
    
    # =========================================================================
    # v1.9.0: Fetch data INSIDE fragment for proper CRUD refresh
    # =========================================================================
    split_df = _get_cached_split_data(setup_queries, query_params)
    
    # Show count
    st.caption(f"📊 Showing **{len(split_df):,}** rules | Period: {period_desc}")
    
    if split_df.empty:
        st.info("No split rules found matching the filters")
        return
    
    # Helper to check if user can modify a specific record
    def can_modify_this_record(record_owner_id: int) -> bool:
        if not can_edit_base:
            return False
        return can_modify_record(record_owner_id, access_level, editable_employee_ids)
    
    # Prepare display dataframe
    display_df = split_df.copy()
    
    display_df['ID'] = display_df['split_id'].apply(lambda x: f"#{x}")
    display_df['Salesperson'] = display_df['salesperson_name']
    display_df['Customer'] = display_df['customer_display']
    display_df['Product'] = display_df['product_display']
    display_df['Split'] = display_df['split_percentage'].apply(lambda x: f"{x:.0f}%")
    display_df['Status'] = display_df['split_status'].apply(lambda x: get_status_display(x)[0])
    display_df['Approved'] = display_df.apply(
        lambda r: f"✅ {r.get('approved_by_name', '').strip() if pd.notna(r.get('approved_by_name')) else ''}" if r.get('is_approved') else '⏳ Pending',
        axis=1
    )
    display_df['Created By'] = display_df['created_by_name'].fillna('')
    
    show_deleted_flag = st.session_state.get('sp_split_show_deleted', False)
    
    if show_deleted_flag and 'delete_flag' in display_df.columns:
        display_df['Deleted'] = display_df['delete_flag'].apply(lambda x: '🗑️' if x else '')
    
    # Get user's employee_id for approver tracking
    approver_employee_id = st.session_state.get('employee_id')
    
    # Count pending and approved
    pending_mask = display_df['is_approved'] != 1
    approved_mask = display_df['is_approved'] == 1
    pending_count = pending_mask.sum()
    approved_count = approved_mask.sum()
    
    # Initialize selection state
    if 'sp_split_selected_ids' not in st.session_state:
        st.session_state['sp_split_selected_ids'] = set()
    
    selected_ids = st.session_state.get('sp_split_selected_ids', set())
    valid_selected = set(display_df['split_id'].tolist()) & selected_ids if selected_ids else set()
    selected_count = len(valid_selected)
    
    # =========================================================================
    # UNIFIED ACTION BAR
    # =========================================================================
    with st.container(border=True):
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns([2, 1, 1, 1])
        
        with row1_col1:
            st.markdown(f"**📋 {pending_count}** pending · **✅ {approved_count}** approved")
        
        with row1_col2:
            if st.button("☑️ Select All Pending", use_container_width=True, 
                        help="Select all pending rules", key="sp_dt_select_pending"):
                pending_ids = display_df[pending_mask]['split_id'].tolist()
                st.session_state['sp_split_selected_ids'] = set(pending_ids)
                st.rerun(scope="fragment")
        
        with row1_col3:
            if st.button("☑️ Select All Approved", use_container_width=True,
                        help="Select all approved rules", key="sp_dt_select_approved"):
                approved_ids = display_df[approved_mask]['split_id'].tolist()
                st.session_state['sp_split_selected_ids'] = set(approved_ids)
                st.rerun(scope="fragment")
        
        with row1_col4:
            if st.button("✖️ Clear", use_container_width=True, 
                        disabled=selected_count == 0, key="sp_dt_clear"):
                st.session_state['sp_split_selected_ids'] = set()
                st.rerun(scope="fragment")
        
        # ROW 2: Action buttons (only show when items selected)
        if valid_selected:
            selected_df = display_df[display_df['split_id'].isin(valid_selected)]
            selected_pending = (selected_df['is_approved'] != 1).sum()
            selected_approved = (selected_df['is_approved'] == 1).sum()
            
            st.divider()
            
            # Single selection: Show Edit/Delete + Approve/Disapprove
            if selected_count == 1:
                selected_rule_id = list(valid_selected)[0]
                selected_row = selected_df.iloc[0]
                record_owner_id = selected_row['sale_person_id']
                is_rule_approved = selected_row.get('is_approved', 0) == 1
                
                can_modify = can_modify_this_record(record_owner_id)
                
                st.caption(f"📌 Selected: **#{selected_rule_id}** | {selected_row['salesperson_name']} | {selected_row['customer_display']}")
                
                if can_approve:
                    act_col1, act_col2, act_col3, act_col4 = st.columns(4)
                else:
                    act_col1, act_col2 = st.columns(2)
                    act_col3 = act_col4 = None
                
                with act_col1:
                    if can_modify:
                        if st.button("✏️ Edit", use_container_width=True, type="secondary", key="sp_dt_edit"):
                            # v1.7.0: Call dialog directly instead of setting session state
                            _edit_split_rule_dialog(rule_id=selected_rule_id)
                    else:
                        st.button("✏️ Edit", use_container_width=True, disabled=True,
                                 help="You can only edit records for your team members", key="sp_dt_edit_dis")
                
                with act_col2:
                    if can_modify:
                        with st.popover("🗑️ Delete", use_container_width=True):
                            st.warning(f"Delete rule **#{selected_rule_id}**?")
                            if st.button("🗑️ Yes, Delete", type="primary", 
                                        key="sp_dt_confirm_delete", use_container_width=True):
                                with st.spinner("Deleting..."):
                                    result = setup_queries.delete_split_rule(selected_rule_id)
                                if result['success']:
                                    _set_notification(
                                        NOTIF_KEY, 'success',
                                        f"Rule #{selected_rule_id} deleted",
                                        f"Removed from database"
                                    )
                                    st.session_state['sp_split_selected_ids'] = set()
                                    _bump_data_version('split')  # v1.9.0: Invalidate cache
                                    st.rerun(scope="fragment")
                                else:
                                    _set_notification(
                                        NOTIF_KEY, 'error',
                                        f"Failed to delete rule #{selected_rule_id}",
                                        result['message']
                                    )
                                    st.rerun(scope="fragment")
                    else:
                        st.button("🗑️ Delete", use_container_width=True, disabled=True,
                                 help="You can only delete records for your team members", key="sp_dt_del_dis")
                
                if can_approve:
                    with act_col3:
                        if not is_rule_approved:
                            if st.button("✅ Approve", use_container_width=True, type="primary", key="sp_dt_approve"):
                                with st.spinner("Approving..."):
                                    result = setup_queries.bulk_approve_split_rules(
                                        rule_ids=[selected_rule_id],
                                        approver_employee_id=approver_employee_id
                                    )
                                if result['success']:
                                    _set_notification(
                                        NOTIF_KEY, 'success',
                                        f"Rule #{selected_rule_id} approved",
                                        f"Approved by you",
                                        affected_ids=[selected_rule_id]
                                    )
                                    st.session_state['sp_split_selected_ids'] = set()
                                    _bump_data_version('split')  # v1.9.0: Invalidate cache
                                    st.rerun(scope="fragment")
                                else:
                                    _set_notification(
                                        NOTIF_KEY, 'error',
                                        f"Failed to approve rule #{selected_rule_id}",
                                        result['message']
                                    )
                                    st.rerun(scope="fragment")
                        else:
                            st.button("✅ Approve", use_container_width=True, disabled=True,
                                     help="Already approved", key="sp_dt_approve_dis")
                    
                    with act_col4:
                        if is_rule_approved:
                            if st.button("⏳ Disapprove", use_container_width=True, key="sp_dt_disapprove"):
                                with st.spinner("Processing..."):
                                    result = setup_queries.bulk_disapprove_split_rules(
                                        rule_ids=[selected_rule_id]
                                    )
                                if result['success']:
                                    _set_notification(
                                        NOTIF_KEY, 'success',
                                        f"Rule #{selected_rule_id} reset to Pending",
                                        f"Requires re-approval",
                                        affected_ids=[selected_rule_id]
                                    )
                                    st.session_state['sp_split_selected_ids'] = set()
                                    _bump_data_version('split')  # v1.9.0: Invalidate cache
                                    st.rerun(scope="fragment")
                                else:
                                    _set_notification(
                                        NOTIF_KEY, 'error',
                                        f"Failed to reset rule #{selected_rule_id}",
                                        result['message']
                                    )
                                    st.rerun(scope="fragment")
                        else:
                            st.button("⏳ Disapprove", use_container_width=True, disabled=True,
                                     help="Not approved yet", key="sp_dt_disapprove_dis")
                
                # v2.2.0: Copy to New Period button for single rule
                if can_modify:
                    st.divider()
                    copy_col1, copy_col2, copy_col3 = st.columns([1, 1, 2])
                    with copy_col1:
                        if st.button("📋 Copy to New Period", use_container_width=True, key="sp_dt_copy_period"):
                            _copy_to_period_dialog(rule_id=selected_rule_id)
            
            # Multi selection: Show bulk actions only
            else:
                st.caption(f"📌 **{selected_count}** rules selected: {selected_pending} pending, {selected_approved} approved")
                
                # ROW 1: Approval actions (if user can approve)
                if can_approve:
                    bulk_col1, bulk_col2, bulk_col3 = st.columns([1, 1, 2])
                    
                    with bulk_col1:
                        if selected_pending > 0:
                            with st.popover(f"✅ Approve {selected_pending}", use_container_width=True):
                                st.warning(f"Approve **{selected_pending}** pending rules?")
                                if st.button("✅ Yes, Approve All", type="primary", 
                                            key="sp_dt_bulk_approve", use_container_width=True):
                                    pending_to_approve = selected_df[selected_df['is_approved'] != 1]['split_id'].tolist()
                                    with st.spinner(f"Approving {len(pending_to_approve)} rules..."):
                                        result = setup_queries.bulk_approve_split_rules(
                                            rule_ids=pending_to_approve,
                                            approver_employee_id=approver_employee_id
                                        )
                                    if result['success']:
                                        _set_notification(
                                            NOTIF_KEY, 'success',
                                            f"Approved {result['count']} rules",
                                            f"All selected pending rules are now approved",
                                            affected_ids=pending_to_approve
                                        )
                                        st.session_state['sp_split_selected_ids'] = set()
                                        _bump_data_version('split')  # v1.9.0: Invalidate cache
                                        st.rerun(scope="fragment")
                                    else:
                                        _set_notification(
                                            NOTIF_KEY, 'error',
                                            f"Failed to approve rules",
                                            result['message']
                                        )
                                        st.rerun(scope="fragment")
                        else:
                            st.button("✅ Approve", disabled=True, use_container_width=True,
                                     help="No pending rules selected", key="sp_dt_bulk_approve_dis")
                    
                    with bulk_col2:
                        if selected_approved > 0:
                            with st.popover(f"⏳ Disapprove {selected_approved}", use_container_width=True):
                                st.warning(f"Reset **{selected_approved}** rules to Pending?")
                                if st.button("⏳ Yes, Reset to Pending", type="primary",
                                            key="sp_dt_bulk_disapprove", use_container_width=True):
                                    approved_to_reset = selected_df[selected_df['is_approved'] == 1]['split_id'].tolist()
                                    with st.spinner(f"Resetting {len(approved_to_reset)} rules..."):
                                        result = setup_queries.bulk_disapprove_split_rules(
                                            rule_ids=approved_to_reset
                                        )
                                    if result['success']:
                                        _set_notification(
                                            NOTIF_KEY, 'success',
                                            f"Reset {result['count']} rules to Pending",
                                            f"These rules now require re-approval",
                                            affected_ids=approved_to_reset
                                        )
                                        st.session_state['sp_split_selected_ids'] = set()
                                        _bump_data_version('split')  # v1.9.0: Invalidate cache
                                        st.rerun(scope="fragment")
                                    else:
                                        _set_notification(
                                            NOTIF_KEY, 'error',
                                            f"Failed to reset rules",
                                            result['message']
                                        )
                                        st.rerun(scope="fragment")
                        else:
                            st.button("⏳ Disapprove", disabled=True, use_container_width=True,
                                     help="No approved rules selected", key="sp_dt_bulk_disapprove_dis")
                
                # ROW 2: Bulk Update actions (v1.6.0 - Enhanced with validation)
                # Only show if user has edit permission
                if can_edit_base:
                    st.divider()
                    st.caption("📝 Bulk Update Actions")
                    
                    upd_col1, upd_col2, upd_col3 = st.columns([1, 1, 2])
                    
                    # Bulk Update Period (v1.6.0: With validation preview)
                    with upd_col1:
                        with st.popover(f"📅 Update Period ({selected_count})", use_container_width=True):
                            st.markdown(f"**Set validity period for {selected_count} rules**")
                            
                            bulk_valid_from = st.date_input(
                                "Valid From",
                                value=date.today(),
                                key="sp_bulk_valid_from"
                            )
                            bulk_valid_to = st.date_input(
                                "Valid To",
                                value=date(date.today().year, 12, 31),
                                key="sp_bulk_valid_to"
                            )
                            
                            st.caption(f"📌 Will update: {bulk_valid_from} → {bulk_valid_to}")
                            
                            # v1.6.0: Validation preview
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
                                st.error(f"❌ {period_impact['overlap_count']} rules will have overlapping periods - Not allowed")
                                with st.expander("View overlap details"):
                                    for ow in period_impact['overlap_warnings'][:5]:  # Show max 5
                                        st.caption(f"• #{ow['rule_id']}: {ow['salesperson_name']} - {ow['overlap_count']} overlaps")
                                    if period_impact['overlap_count'] > 5:
                                        st.caption(f"... and {period_impact['overlap_count'] - 5} more")
                            
                            # v1.6.2: Block if any overlaps OR period errors (pre-validation)
                            can_proceed_period = period_impact['can_proceed'] and period_impact['overlap_count'] == 0
                            
                            if can_proceed_period:
                                if st.button("📅 Apply Period", type="primary", 
                                            key="sp_dt_bulk_period", use_container_width=True):
                                    with st.spinner(f"Updating {len(selected_rule_ids)} rules..."):
                                        result = setup_queries.bulk_update_split_period(
                                            rule_ids=selected_rule_ids,
                                            valid_from=bulk_valid_from,
                                            valid_to=bulk_valid_to
                                        )
                                    if result['success']:
                                        _set_notification(
                                            NOTIF_KEY, 'success',
                                            f"Updated period for {result['count']} rules",
                                            f"New period: {bulk_valid_from} → {bulk_valid_to}",
                                            affected_ids=selected_rule_ids
                                        )
                                        st.session_state['sp_split_selected_ids'] = set()
                                        _bump_data_version('split')  # v1.9.0: Invalidate cache
                                        st.rerun(scope="fragment")
                                    else:
                                        _set_notification(
                                            NOTIF_KEY, 'error',
                                            f"Failed to update period",
                                            result['message']
                                        )
                                        st.rerun(scope="fragment")
                            else:
                                st.button("📅 Apply Period", type="primary", disabled=True,
                                         key="sp_dt_bulk_period_dis", use_container_width=True)
                                st.error("❌ Fix errors above before proceeding")
                    
                    # Bulk Update Split % (v1.6.0: With validation preview)
                    with upd_col2:
                        with st.popover(f"📊 Update Split % ({selected_count})", use_container_width=True):
                            st.markdown(f"**Set split % for {selected_count} rules**")
                            
                            bulk_split_pct = st.number_input(
                                "Split Percentage",
                                min_value=0,
                                max_value=100,
                                value=100,
                                step=5,
                                key="sp_bulk_split_pct"
                            )
                            
                            st.caption(f"📌 Will set: **{bulk_split_pct}%** for all selected rules")
                            
                            # v1.6.0: Validation preview with impact analysis
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
                                st.metric("🔴 Over", split_impact['will_be_over'], 
                                         help="Will have total > 100%",
                                         delta="BLOCKED" if split_impact['will_be_over'] > 0 and access_level != 'full' else None,
                                         delta_color=delta_color)
                            
                            # Show detailed issues
                            if split_impact['will_be_over'] > 0:
                                over_rules = [d for d in split_impact['details'] if d['status'] == 'over']
                                with st.expander(f"🔴 View {len(over_rules)} over-allocated rules"):
                                    for r in over_rules[:5]:
                                        st.caption(f"• #{r['rule_id']}: {r['customer_name'][:20]}... → {r['new_total']:.0f}%")
                                    if len(over_rules) > 5:
                                        st.caption(f"... and {len(over_rules) - 5} more")
                            
                            # v1.6.0: Block if any over 100% - ALL users (business rule)
                            can_bulk_update = split_impact['can_proceed']
                            
                            if split_impact['will_be_over'] > 0:
                                st.error(f"❌ Cannot proceed: {split_impact['will_be_over']} rules would exceed 100%")
                            
                            if can_bulk_update:
                                if st.button("📊 Apply Split %", type="primary",
                                            key="sp_dt_bulk_split", use_container_width=True):
                                    with st.spinner(f"Updating {len(selected_rule_ids)} rules..."):
                                        result = setup_queries.bulk_update_split_percentage(
                                            rule_ids=selected_rule_ids,
                                            split_percentage=bulk_split_pct
                                        )
                                    if result['success']:
                                        _set_notification(
                                            NOTIF_KEY, 'success',
                                            f"Updated split % for {result['count']} rules",
                                            f"New split: {bulk_split_pct}%",
                                            affected_ids=selected_rule_ids
                                        )
                                        st.session_state['sp_split_selected_ids'] = set()
                                        _bump_data_version('split')  # v1.9.0: Invalidate cache
                                        st.rerun(scope="fragment")
                                    else:
                                        _set_notification(
                                            NOTIF_KEY, 'error',
                                            f"Failed to update split %",
                                            result['message']
                                        )
                                        st.rerun(scope="fragment")
                            else:
                                st.button("📊 Apply Split %", type="primary", disabled=True,
                                         key="sp_dt_bulk_split_dis", use_container_width=True)
                    
                    # v2.2.0: Bulk Copy to New Period
                    with upd_col3:
                        if st.button(
                            f"📋 Copy to New Period ({selected_count})",
                            use_container_width=True,
                            key="sp_dt_bulk_copy_period"
                        ):
                            _bulk_copy_to_period_dialog(list(valid_selected))
                
                if not can_approve and not can_edit_base:
                    st.info("💡 Select a single rule to view details")
    
    # =========================================================================
    # DATA TABLE WITH CHECKBOXES
    # =========================================================================
    display_df['Select'] = display_df['split_id'].apply(
        lambda x: x in st.session_state.get('sp_split_selected_ids', set())
    )
    
    columns_to_show = [
        'Select', 'ID', 'Salesperson', 'Customer', 'Product', 'brand',
        'Split', 'effective_period', 'Status', 'Approved', 'Created By'
    ]
    if show_deleted_flag and 'delete_flag' in display_df.columns:
        columns_to_show.append('Deleted')
    
    edited_df = st.data_editor(
        display_df[columns_to_show],
        hide_index=True,
        column_config={
            'Select': st.column_config.CheckboxColumn(
                '☑️',
                width='small',
                help="Select for actions"
            ),
            'ID': st.column_config.TextColumn('ID', width='small', disabled=True),
            'Salesperson': st.column_config.TextColumn('Salesperson', width='medium', disabled=True),
            'Customer': st.column_config.TextColumn('Customer', width='large', disabled=True),
            'Product': st.column_config.TextColumn('Product', width='large', disabled=True),
            'brand': st.column_config.TextColumn('Brand', width='small', disabled=True),
            'Split': st.column_config.TextColumn('Split %', width='small', disabled=True),
            'effective_period': st.column_config.TextColumn('Period', width='medium', disabled=True),
            'Status': st.column_config.TextColumn('Status', width='small', disabled=True),
            'Approved': st.column_config.TextColumn('Approved', width='medium', disabled=True),
            'Created By': st.column_config.TextColumn('Created By', width='medium', disabled=True),
        },
        use_container_width=True,
        key="sp_split_data_editor_v2"
    )
    
    if edited_df is not None and 'Select' in edited_df.columns:
        new_selected = set(display_df[edited_df['Select'] == True]['split_id'].tolist())
        if new_selected != st.session_state.get('sp_split_selected_ids', set()):
            st.session_state['sp_split_selected_ids'] = new_selected
            st.rerun(scope="fragment")


# =============================================================================
# COMBO INSIGHTS SECTION (v1.7.0 - For Edit Dialog)
# =============================================================================

def _render_combo_insights(
    setup_queries: SalespersonSetupQueries,
    customer_id: int,
    product_id: int,
    current_rule_id: int = None,
    current_salesperson_id: int = None
):
    """
    Render insights section showing current split structure.
    
    v1.7.0: New function for Edit dialog.
    v1.7.1: Removed Sales History tab (table not available).
    """
    with st.expander("📊 **Current Split Structure**", expanded=True):
        
        # Get current split structure (excluding the rule being edited)
        split_structure = setup_queries.get_combo_split_structure(
            customer_id=customer_id,
            product_id=product_id,
            exclude_rule_id=current_rule_id,
            include_expired=False
        )
        
        # Get combo summary
        combo_summary = setup_queries.get_combo_summary(
            customer_id=customer_id,
            product_id=product_id,
            exclude_rule_id=current_rule_id
        )
        
        # Summary metrics row
        sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
        
        with sum_col1:
            total_split = combo_summary['total_split']
            st.metric(
                "Other Allocations",
                f"{total_split:.0f}%",
                help="Total split % from other rules (excluding this one)"
            )
        
        with sum_col2:
            st.metric(
                "Other Rules",
                combo_summary['rule_count'],
                help="Number of other active rules for this combo"
            )
        
        with sum_col3:
            st.metric(
                "Approved",
                f"{combo_summary['approved_split']:.0f}%",
                help="Split % from approved rules"
            )
        
        with sum_col4:
            st.metric(
                "Pending",
                f"{combo_summary['pending_split']:.0f}%",
                help="Split % from pending rules"
            )
        
        # Allocation breakdown
        if not split_structure.empty:
            st.markdown("##### 👥 Allocation Breakdown")
            
            # Create visual display for each salesperson
            for _, row in split_structure.iterrows():
                is_same_person = (row['salesperson_id'] == current_salesperson_id)
                
                # Status indicators
                period_icon = {
                    'ok': '🟢',
                    'warning': '🟠',
                    'critical': '🔴',
                    'expired': '⚫',
                    'no_end': '🔵'
                }.get(row['period_status'], '❓')
                
                approval_badge = "✅" if row['is_approved'] else "⏳"
                
                # Highlight if same salesperson
                same_person_note = " *(same salesperson)*" if is_same_person else ""
                
                cols = st.columns([3, 2, 2, 1])
                
                with cols[0]:
                    st.markdown(f"**{row['salesperson_name']}**{same_person_note}")
                    st.caption(f"{row['salesperson_email']}")
                
                with cols[1]:
                    # Visual progress bar
                    pct = row['split_percentage']
                    bar_width = min(pct, 100)
                    bar_color = "#4CAF50" if pct <= 100 else "#f44336"
                    st.markdown(f"""
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div style="flex: 1; background: #e0e0e0; border-radius: 4px; height: 8px;">
                                <div style="width: {bar_width}%; background: {bar_color}; height: 100%; border-radius: 4px;"></div>
                            </div>
                            <span style="font-weight: bold; min-width: 45px;">{pct:.0f}%</span>
                        </div>
                    """, unsafe_allow_html=True)
                
                with cols[2]:
                    st.caption(f"{period_icon} {row['period_display']}")
                
                with cols[3]:
                    st.markdown(f"{approval_badge}")
                
                st.divider()
            
            # Warning if same salesperson has overlapping allocation
            same_person_rules = split_structure[
                split_structure['salesperson_id'] == current_salesperson_id
            ]
            if not same_person_rules.empty:
                st.warning(
                    f"⚠️ **{same_person_rules.iloc[0]['salesperson_name']}** already has "
                    f"**{same_person_rules['split_percentage'].sum():.0f}%** allocation for this combo. "
                    f"Check for period overlaps!"
                )
        else:
            st.info("✨ No other allocations for this customer/product combo")


# =============================================================================
# SPLIT RULE DIALOGS (v1.7.0 - Replaced inline forms with dialogs)
# =============================================================================

@st.dialog("➕ Add Split Rule", width="large")
def _add_split_rule_dialog():
    """
    Dialog for adding new split rule.
    
    v1.7.0: New - replaces inline form for better UX.
    Reads context from st.session_state['_split_dialog_context'].
    """
    ctx = st.session_state.get('_split_dialog_context', {})
    user_id = ctx.get('user_id')
    can_approve = ctx.get('can_approve', False)
    editable_employee_ids = ctx.get('editable_employee_ids')
    access_level = ctx.get('access_level', 'self')
    
    setup_queries = SalespersonSetupQueries(user_id=user_id)
    
    _render_split_form_content(
        setup_queries=setup_queries,
        can_approve=can_approve,
        mode='add',
        rule_id=None,
        editable_employee_ids=editable_employee_ids,
        access_level=access_level
    )


@st.dialog("✏️ Edit Split Rule", width="large")
def _edit_split_rule_dialog(rule_id: int):
    """
    Dialog for editing existing split rule.
    
    v1.7.0: New - replaces inline form for better UX.
    
    Args:
        rule_id: ID of rule to edit
    """
    ctx = st.session_state.get('_split_dialog_context', {})
    user_id = ctx.get('user_id')
    can_approve = ctx.get('can_approve', False)
    editable_employee_ids = ctx.get('editable_employee_ids')
    access_level = ctx.get('access_level', 'self')
    
    setup_queries = SalespersonSetupQueries(user_id=user_id)
    
    _render_split_form_content(
        setup_queries=setup_queries,
        can_approve=can_approve,
        mode='edit',
        rule_id=rule_id,
        editable_employee_ids=editable_employee_ids,
        access_level=access_level
    )


# =============================================================================
# COPY TO NEW PERIOD DIALOGS (v2.2.0 - NEW)
# =============================================================================

@st.dialog("📋 Copy Rule to New Period", width="large")
def _copy_to_period_dialog(rule_id: int):
    """
    Dialog for copying a single split rule to a new period.
    
    v2.2.0: NEW - Single rule copy to new period.
    
    Args:
        rule_id: ID of rule to copy
    """
    ctx = st.session_state.get('_split_dialog_context', {})
    user_id = ctx.get('user_id')
    can_approve = ctx.get('can_approve', False)
    access_level = ctx.get('access_level', 'self')
    
    setup_queries = SalespersonSetupQueries(user_id=user_id)
    
    # Get rule details
    rule = setup_queries.get_rule_details(rule_id)
    
    if rule is None:
        st.error(f"Rule #{rule_id} not found")
        return
    
    # Header info
    st.markdown("""
    ℹ️ Create a **NEW** rule with same details but different period.  
    Original rule will **NOT** be modified.
    """)
    
    st.divider()
    
    # Original Rule Info
    st.markdown("##### 📌 Original Rule")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"**👤 Salesperson:** {rule['salesperson_name']}")
            st.markdown(f"**🏢 Customer:** {rule['customer_display']}")
        
        with col2:
            st.markdown(f"**📦 Product:** {rule['product_display']}")
            st.markdown(f"**📊 Split:** {rule['split_percentage']:.0f}%")
        
        # Period and approval
        original_period = f"{rule['valid_from']} → {rule['valid_to'] or 'No End'}"
        approval_status = "✅ Approved" if rule.get('is_approved') else "⏳ Pending"
        if rule.get('approved_by_name'):
            approval_status += f" (by {rule['approved_by_name']})"
        
        st.caption(f"📅 Period: {original_period} | {approval_status}")
    
    st.divider()
    
    # New Period Section
    st.markdown("##### 📅 New Period")
    
    col_from, col_to = st.columns(2)
    
    with col_from:
        new_valid_from = st.date_input(
            "Valid From *",
            value=date(date.today().year + 1, 1, 1),
            key="copy_single_valid_from"
        )
    
    with col_to:
        new_valid_to = st.date_input(
            "Valid To",
            value=date(date.today().year + 1, 12, 31),
            key="copy_single_valid_to"
        )
    
    st.divider()
    
    # Options Section - Only for admin/sales_manager
    user_role = st.session_state.get('user_role', 'viewer')
    user_role_lower = str(user_role).lower() if user_role else ''
    can_choose_approval = user_role_lower in ['admin', 'sales_manager']
    
    copy_approval = False
    if can_choose_approval and rule.get('is_approved'):
        st.markdown("##### ⚙️ Options")
        copy_approval = st.checkbox(
            "Copy approval status (new rule will be Approved)",
            value=False,
            key="copy_single_approval",
            help="If unchecked, new rule will be Pending"
        )
        if not copy_approval:
            st.caption("ℹ️ New rule will be created as **Pending** (requires approval)")
    else:
        st.caption("ℹ️ New rule will be created as **Pending** (requires approval)")
    
    st.divider()
    
    # Validation Section
    st.markdown("##### 🔍 Validation")
    
    validation = setup_queries.validate_copy_to_period(
        source_rule_ids=[rule_id],
        new_valid_from=new_valid_from,
        new_valid_to=new_valid_to
    )
    
    if validation['details']:
        detail = validation['details'][0]
        
        if detail['status'] == 'valid':
            st.success("✅ Ready to create")
        elif detail['status'] == 'warning':
            st.warning(f"⚠️ Warnings: {detail['message']}")
            st.caption("You can still proceed, but please review the warnings above.")
        else:
            st.error(f"❌ Error: {detail['message']}")
    
    st.divider()
    
    # Action Buttons
    col_cancel, col_create = st.columns(2)
    
    with col_cancel:
        if st.button("❌ Cancel", use_container_width=True):
            st.rerun()
    
    with col_create:
        can_proceed = validation['error_count'] == 0
        
        if st.button(
            "📋 Create New Rule",
            type="primary",
            use_container_width=True,
            disabled=not can_proceed
        ):
            approver_id = st.session_state.get('employee_id') if copy_approval else None
            
            with st.spinner("Creating new rule..."):
                result = setup_queries.copy_rule_to_new_period(
                    source_rule_id=rule_id,
                    new_valid_from=new_valid_from,
                    new_valid_to=new_valid_to,
                    copy_approval=copy_approval,
                    approver_employee_id=approver_id
                )
            
            if result['success']:
                _set_notification(
                    '_split_rules_notification', 'success',
                    f"Created new rule #{result['id']}",
                    f"Copied from #{rule_id} | Period: {new_valid_from} → {new_valid_to}",
                    affected_ids=[result['id']]
                )
                _bump_data_version('split')
                st.rerun()
            else:
                st.error(f"❌ {result['message']}")


@st.dialog("📋 Copy Rules to New Period", width="large")
def _bulk_copy_to_period_dialog(rule_ids: List[int]):
    """
    Dialog for bulk copying multiple split rules to a new period.
    
    v2.2.0: NEW - Bulk copy to new period.
    
    Args:
        rule_ids: List of rule IDs to copy
    """
    ctx = st.session_state.get('_split_dialog_context', {})
    user_id = ctx.get('user_id')
    can_approve = ctx.get('can_approve', False)
    access_level = ctx.get('access_level', 'self')
    
    setup_queries = SalespersonSetupQueries(user_id=user_id)
    
    rule_count = len(rule_ids)
    
    # Header
    st.markdown(f"""
    ℹ️ Create **{rule_count} NEW** rules with same details but different period.  
    Original rules will **NOT** be modified.
    """)
    
    st.divider()
    
    # New Period Section
    st.markdown("##### 📅 New Period")
    
    col_from, col_to = st.columns(2)
    
    with col_from:
        new_valid_from = st.date_input(
            "Valid From *",
            value=date(date.today().year + 1, 1, 1),
            key="copy_bulk_valid_from"
        )
    
    with col_to:
        new_valid_to = st.date_input(
            "Valid To",
            value=date(date.today().year + 1, 12, 31),
            key="copy_bulk_valid_to"
        )
    
    st.divider()
    
    # Options Section - Only for admin/sales_manager
    user_role = st.session_state.get('user_role', 'viewer')
    user_role_lower = str(user_role).lower() if user_role else ''
    can_choose_approval = user_role_lower in ['admin', 'sales_manager']
    
    copy_approval = False
    if can_choose_approval:
        st.markdown("##### ⚙️ Options")
        copy_approval = st.checkbox(
            "Copy approval status from original rules",
            value=False,
            key="copy_bulk_approval",
            help="If unchecked, all new rules will be Pending"
        )
        if not copy_approval:
            st.caption("ℹ️ All new rules will be created as **Pending**")
    else:
        st.caption("ℹ️ All new rules will be created as **Pending** (requires approval)")
    
    st.divider()
    
    # Validation Section
    st.markdown("##### 🔍 Preview & Validation")
    
    validation = setup_queries.validate_copy_to_period(
        source_rule_ids=rule_ids,
        new_valid_from=new_valid_from,
        new_valid_to=new_valid_to
    )
    
    # Summary metrics
    sum_col1, sum_col2, sum_col3 = st.columns(3)
    
    with sum_col1:
        st.metric("✅ Ready", validation['valid_count'])
    with sum_col2:
        st.metric("⚠️ Warnings", validation['warning_count'])
    with sum_col3:
        st.metric("❌ Errors", validation['error_count'])
    
    # Details table
    if validation['details']:
        with st.expander(f"📋 View Details ({len(validation['details'])} rules)", expanded=False):
            for detail in validation['details']:
                rule_info = detail.get('rule_info', {})
                status_icon = "✅" if detail['status'] == 'valid' else ("⚠️" if detail['status'] == 'warning' else "❌")
                
                cols = st.columns([1, 2, 2, 3])
                with cols[0]:
                    st.markdown(f"{status_icon} #{detail['rule_id']}")
                with cols[1]:
                    st.caption(rule_info.get('salesperson_name', 'N/A'))
                with cols[2]:
                    customer_short = rule_info.get('customer_display', 'N/A')[:25] + "..." if len(rule_info.get('customer_display', '')) > 25 else rule_info.get('customer_display', 'N/A')
                    st.caption(customer_short)
                with cols[3]:
                    st.caption(detail['message'][:50] + "..." if len(detail['message']) > 50 else detail['message'])
    
    # Warning details
    warning_details = [d for d in validation['details'] if d['status'] == 'warning']
    if warning_details:
        with st.expander(f"⚠️ Warnings ({len(warning_details)})", expanded=True):
            for wd in warning_details[:5]:
                rule_info = wd.get('rule_info', {})
                st.caption(f"• **#{wd['rule_id']}** ({rule_info.get('salesperson_name', 'N/A')}): {wd['message']}")
            if len(warning_details) > 5:
                st.caption(f"... and {len(warning_details) - 5} more")
    
    st.divider()
    
    # Include warnings checkbox
    include_warnings = True
    if validation['warning_count'] > 0:
        include_warnings = st.checkbox(
            f"Include {validation['warning_count']} rules with warnings",
            value=True,
            key="copy_bulk_include_warnings"
        )
    
    # Calculate how many will be created
    if include_warnings:
        to_create_count = validation['valid_count'] + validation['warning_count']
    else:
        to_create_count = validation['valid_count']
    
    st.divider()
    
    # Action Buttons
    col_cancel, col_create = st.columns(2)
    
    with col_cancel:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state['sp_split_selected_ids'] = set()
            st.rerun()
    
    with col_create:
        can_proceed = to_create_count > 0
        
        button_text = f"📋 Create {to_create_count} Rules"
        if validation['warning_count'] > 0 and not include_warnings:
            button_text = f"📋 Create {to_create_count} Rules (skip {validation['warning_count']} warnings)"
        
        if st.button(
            button_text,
            type="primary",
            use_container_width=True,
            disabled=not can_proceed
        ):
            approver_id = st.session_state.get('employee_id') if copy_approval else None
            
            progress_bar = st.progress(0, text="Creating rules...")
            
            with st.spinner(f"Creating {to_create_count} rules..."):
                result = setup_queries.bulk_copy_rules_to_new_period(
                    source_rule_ids=rule_ids,
                    new_valid_from=new_valid_from,
                    new_valid_to=new_valid_to,
                    copy_approval=copy_approval,
                    approver_employee_id=approver_id,
                    include_warnings=include_warnings
                )
            
            progress_bar.empty()
            
            if result['success']:
                _set_notification(
                    '_split_rules_notification', 'success',
                    f"Created {result['success_count']} new rule(s)",
                    f"Period: {new_valid_from} → {new_valid_to}" + 
                    (f" | Skipped: {result['skipped_count']}" if result['skipped_count'] > 0 else ""),
                    affected_ids=result['created_ids']
                )
                _bump_data_version('split')
                st.session_state['sp_split_selected_ids'] = set()
                st.rerun()
            else:
                st.error(f"❌ {result['message']}")
                if result['error_details']:
                    for err in result['error_details'][:3]:
                        st.caption(f"• #{err['rule_id']}: {err['reason']}")


def _render_split_form_content(
    setup_queries: SalespersonSetupQueries, 
    can_approve: bool, 
    mode: str = 'add', 
    rule_id: int = None,
    editable_employee_ids: List[int] = None,
    access_level: str = 'self'
):
    """
    Render split rule form content (used inside dialogs).
    
    v1.7.0: Refactored from _render_split_form to be used inside @st.dialog.
            Added insights section for Edit mode.
    """
    existing = None
    if mode == 'edit' and rule_id:
        df = setup_queries.get_sales_split_data(limit=5000)
        df = df[df['split_id'] == rule_id]
        if not df.empty:
            existing = df.iloc[0]
        else:
            st.error("Rule not found")
            if st.button("Close", use_container_width=True):
                st.rerun(scope="fragment")
            return
    
    # =========================================================================
    # v2.2.1 FIX: Clear stale widget values when editing a different rule.
    # Streamlit persists selectbox/input values in session_state by key.
    # When user opens Edit dialog for rule A, then later for rule B,
    # the old values from rule A remain → wrong salesperson shown.
    # Solution: detect rule_id change and delete stale keys so widgets
    # re-initialize with correct defaults from `existing`.
    # =========================================================================
    if mode == 'edit' and existing is not None:
        last_edit_id = st.session_state.get('_split_form_last_edit_rule_id')
        if last_edit_id != rule_id:
            for suffix in ['sale_person_id', 'split_pct', 'valid_from', 'valid_to', 'is_approved']:
                form_key = f"sp_{mode}_{suffix}"
                if form_key in st.session_state:
                    del st.session_state[form_key]
            st.session_state['_split_form_last_edit_rule_id'] = rule_id
    
    if mode == 'edit' and existing is not None:
        st.caption(f"Rule ID: **#{rule_id}**")
        col_info1, col_info2 = st.columns(2)
        with col_info1:
            st.markdown(f"**Customer:** {existing['customer_display']}")
        with col_info2:
            st.markdown(f"**Product:** {existing['product_display']}")
        
        # =====================================================================
        # v1.7.0: INSIGHTS SECTION - Current Split Structure & Sales History
        # =====================================================================
        _render_combo_insights(
            setup_queries=setup_queries,
            customer_id=existing['customer_id'],
            product_id=existing['product_id'],
            current_rule_id=rule_id,
            current_salesperson_id=existing['sale_person_id']
        )
    
    with st.form(f"sp_{mode}_split_form_dialog", clear_on_submit=False):
            if mode == 'add':
                # v1.7.2: Customer and Product in full-width rows for better readability
                # Customer dropdown - full width
                customers_df = setup_queries.get_customers_for_dropdown(limit=99999)
                
                if not customers_df.empty:
                    customer_id = st.selectbox(
                        "Customer *",
                        options=customers_df['customer_id'].tolist(),
                        format_func=lambda x: customers_df[customers_df['customer_id'] == x]['display_name'].iloc[0],
                        key=f"sp_{mode}_customer_id"
                    )
                else:
                    customer_id = None
                    st.caption("No customers found")
                
                # Product dropdown - full width
                products_df = setup_queries.get_products_for_dropdown(limit=99999)
                
                if not products_df.empty:
                    product_id = st.selectbox(
                        "Product *",
                        options=products_df['product_id'].tolist(),
                        format_func=lambda x: products_df[products_df['product_id'] == x]['display_name'].iloc[0],
                        key=f"sp_{mode}_product_id"
                    )
                else:
                    product_id = None
                    st.caption("No products found")
            else:
                customer_id = existing['customer_id']
                product_id = existing['product_id']
            
            # Salesperson and Split % in 2 columns
            col1, col2 = st.columns(2)
            
            with col1:
                # Salesperson selection (v1.2.0: Filter by editable scope)
                salespeople_df = setup_queries.get_salespeople_for_dropdown()
                
                # v1.2.0: Filter to only show editable employees
                if editable_employee_ids is not None and not salespeople_df.empty:
                    salespeople_df = salespeople_df[
                        salespeople_df['employee_id'].isin(editable_employee_ids)
                    ].reset_index(drop=True)
                
                if not salespeople_df.empty:
                    default_idx = 0
                    if existing is not None and 'sale_person_id' in existing:
                        matches = salespeople_df[salespeople_df['employee_id'] == existing['sale_person_id']]
                        if not matches.empty:
                            default_idx = salespeople_df.index.tolist().index(matches.index[0])
                    
                    # v1.2.0: Add label hint based on access level
                    sp_label = "Salesperson *"
                    if access_level == 'self':
                        sp_label = "Salesperson * (your account)"
                    elif access_level == 'team':
                        sp_label = "Salesperson * (team members)"
                    
                    sale_person_id = st.selectbox(
                        sp_label,
                        options=salespeople_df['employee_id'].tolist(),
                        index=default_idx,
                        format_func=lambda x: f"👤 {salespeople_df[salespeople_df['employee_id'] == x]['employee_name'].iloc[0]}",
                        key=f"sp_{mode}_sale_person_id"
                    )
                else:
                    sale_person_id = None
            
            with col2:
                # Split percentage
                default_split = float(existing['split_percentage']) if existing is not None else 100.0
                split_pct = st.number_input(
                    "Split % *",
                    min_value=0.0,
                    max_value=100.0,
                    value=default_split,
                    step=5.0,
                    key=f"sp_{mode}_split_pct"
                )
            
            # Period inputs (moved up for better UX)
            col3, col4 = st.columns(2)
            with col3:
                default_from = pd.to_datetime(existing['effective_from']).date() if existing is not None and pd.notna(existing.get('effective_from')) else date.today()
                valid_from = st.date_input("Valid From *", value=default_from, key=f"sp_{mode}_valid_from")
            
            with col4:
                default_to = pd.to_datetime(existing['effective_to']).date() if existing is not None and pd.notna(existing.get('effective_to')) else date(date.today().year, 12, 31)
                valid_to = st.date_input("Valid To *", value=default_to, key=f"sp_{mode}_valid_to")
            
            # =====================================================================
            # v1.6.0: ENHANCED VALIDATION SECTION
            # =====================================================================
            st.divider()
            st.markdown("##### 🔍 Validation")
            
            validation_errors = []
            validation_warnings = []
            can_save = True
            
            # 1. Period Validation
            if valid_from and valid_to:
                period_validation = setup_queries.validate_period(valid_from, valid_to)
                
                if not period_validation['is_valid']:
                    for err in period_validation['errors']:
                        validation_errors.append(f"📅 {err}")
                        can_save = False
                
                for warn in period_validation.get('warnings', []):
                    validation_warnings.append(f"📅 {warn}")
            
            # 2. Period Overlap Check (for same salesperson)
            # v1.6.2: BLOCK overlap (pre-validation business rule)
            if customer_id and product_id and sale_person_id and valid_from:
                overlap_check = setup_queries.check_period_overlap(
                    customer_id=customer_id,
                    product_id=product_id,
                    sale_person_id=sale_person_id,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    exclude_rule_id=rule_id if mode == 'edit' else None
                )
                
                if overlap_check['has_overlap']:
                    # v1.6.2: BLOCK - not allowed to create overlapping rules
                    validation_errors.append(f"📅 Period overlaps with {overlap_check['overlap_count']} existing rule(s) for this salesperson")
                    can_save = False
                    
                    with st.expander(f"🔍 View {overlap_check['overlap_count']} overlapping rules"):
                        for r in overlap_check['overlapping_rules']:
                            st.caption(f"• Rule #{r['rule_id']}: {r['split_percentage']:.0f}% ({r['period_display']})")
            
            # 3. Split Percentage Validation (with period awareness)
            if customer_id and product_id:
                split_validation = setup_queries.validate_split_percentage(
                    customer_id=customer_id,
                    product_id=product_id,
                    new_percentage=split_pct,
                    exclude_rule_id=rule_id if mode == 'edit' else None,
                    valid_from=valid_from,
                    valid_to=valid_to
                )
                
                val_col1, val_col2, val_col3 = st.columns(3)
                with val_col1:
                    st.metric("Current Total", f"{split_validation['current_total']:.0f}%",
                             help=f"{split_validation['existing_count']} existing rule(s)")
                with val_col2:
                    delta_color = "off"
                    if split_validation['new_total'] > 100:
                        delta_color = "inverse"
                    st.metric("After Save", f"{split_validation['new_total']:.0f}%",
                             delta=f"+{split_pct:.0f}%", delta_color=delta_color)
                with val_col3:
                    if split_validation['new_total'] == 100:
                        st.success("✅ Perfect!")
                    elif split_validation['new_total'] > 100:
                        over_pct = split_validation['over_amount']
                        st.error(f"🔴 Over by {over_pct:.0f}%")
                        
                        # v1.6.0: Block save for over 100% - ALL users (business rule)
                        validation_errors.append(f"📊 Total split ({split_validation['new_total']:.0f}%) exceeds 100% - Not allowed")
                        can_save = False
                    else:
                        st.warning(f"⚠️ {split_validation['remaining']:.0f}% remaining")
                        validation_warnings.append(f"📊 Under-allocated: {split_validation['remaining']:.0f}% remaining")
            
            # Display validation summary
            if validation_errors:
                for err in validation_errors:
                    st.error(err)
            
            if validation_warnings and not validation_errors:
                for warn in validation_warnings:
                    st.warning(warn)
            
            # Approval checkbox (only for edit mode and users with approve permission)
            is_approved_value = False
            if mode == 'edit' and can_approve:
                st.divider()
                current_approval = bool(existing.get('is_approved', 0)) if existing is not None else False
                is_approved_value = st.checkbox(
                    "✅ Approve this rule",
                    value=current_approval,
                    key=f"sp_{mode}_is_approved",
                    help="Check to approve this split rule. Only admins/managers can approve."
                )
                if is_approved_value and not current_approval:
                    st.success("Rule will be marked as Approved after save")
                elif not is_approved_value and current_approval:
                    st.warning("Rule will be marked as Pending after save")
            elif mode == 'edit' and not can_approve:
                # v1.4.1: Sales role - show warning that edit resets approval
                current_approval = bool(existing.get('is_approved', 0)) if existing is not None else False
                st.divider()
                if current_approval:
                    st.warning("⚠️ This rule is currently **Approved**. After saving your changes, it will need to be re-approved by your manager.")
                else:
                    st.info("⏳ Status: **Pending approval** - Your manager will review after you save.")
            
            # Form submit button only
            submitted = st.form_submit_button(
                "💾 Save" if mode == 'add' else "💾 Update",
                type="primary",
                use_container_width=True
            )
            
            if submitted:
                # v1.6.0: Check validation before proceeding
                if not can_save:
                    st.error("❌ Cannot save - Please fix validation errors above")
                elif mode == 'add' and not all([customer_id, product_id, sale_person_id]):
                    st.error("Please fill all required fields")
                else:
                    if mode == 'add':
                        result = setup_queries.create_split_rule(
                            customer_id=customer_id,
                            product_id=product_id,
                            sale_person_id=sale_person_id,
                            split_percentage=split_pct,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            is_approved=can_approve
                        )
                    else:
                        # Build update params
                        update_kwargs = {
                            'rule_id': rule_id,
                            'split_percentage': split_pct,
                            'valid_from': valid_from,
                            'valid_to': valid_to,
                            'sale_person_id': sale_person_id
                        }
                        
                        # v1.4.1: Handle approval status on update
                        # - If user can approve: use checkbox value
                        # - If user cannot approve (sales): reset to pending (needs re-approval)
                        if can_approve:
                            update_kwargs['is_approved'] = is_approved_value
                        else:
                            # Sales role edits reset approval status to pending
                            update_kwargs['is_approved'] = False
                        
                        result = setup_queries.update_split_rule(**update_kwargs)
                    
                    if result['success']:
                        # v1.8.0: Set notification for display after rerun
                        _set_notification(
                            '_split_rules_notification', 'success',
                            f"Rule {'created' if mode == 'add' else 'updated'} successfully",
                            f"Rule #{result.get('id', rule_id)} • Split: {split_pct}%",
                            affected_ids=[result.get('id', rule_id)]
                        )
                        # v1.9.0: Invalidate cache before rerun
                        _bump_data_version('split')
                        # v1.7.0: Dialog closes automatically on rerun
                        st.rerun(scope="fragment")
                    else:
                        st.error(f"❌ {result['message']}")


# =============================================================================
# KPI ASSIGNMENT DIALOGS (v2.0.0 - NEW Modal Pattern with Batch Add)
# =============================================================================

def _add_to_queue_callback():
    """
    Callback for Add to Queue button.
    
    v2.0.3: NEW - Callback runs BEFORE dialog re-renders, so batch queue
            updates immediately without full page rerun.
    """
    # Get context from session state
    ctx = st.session_state.get('_kpi_dialog_context', {})
    year = ctx.get('year', date.today().year)
    
    # Get values from widget session state keys
    employee_id = st.session_state.get('kpi_batch_employee')
    kpi_type_id = st.session_state.get('kpi_batch_type')
    annual_target = st.session_state.get('kpi_batch_target', 0)
    weight = st.session_state.get('kpi_batch_weight', 0)
    notes = st.session_state.get('kpi_batch_notes', '')
    
    # Skip if invalid values (validation will show error in UI)
    if annual_target <= 0 or weight <= 0:
        return
    
    # Check if already exists in DB (set by dialog before callback)
    if st.session_state.get('_kpi_batch_already_exists_in_db', False):
        st.session_state['_kpi_batch_error'] = "Assignment already exists for this employee/KPI/year in database"
        return
    
    # Get KPI type info from cached context
    kpi_info = st.session_state.get('_kpi_batch_current_kpi_info', {})
    employee_name = st.session_state.get('_kpi_batch_current_employee_name', 'Unknown')
    
    # Check for duplicates in batch
    batch_items = st.session_state.get('_kpi_batch_items', [])
    is_duplicate = any(
        item['employee_id'] == employee_id and 
        item['kpi_type_id'] == kpi_type_id and 
        item['year'] == year
        for item in batch_items
    )
    
    if is_duplicate:
        st.session_state['_kpi_batch_error'] = "This employee/KPI/year combination is already in the queue"
        return
    
    # Create new item
    new_item = {
        'employee_id': employee_id,
        'employee_name': employee_name,
        'kpi_type_id': kpi_type_id,
        'kpi_name': kpi_info.get('kpi_name', 'Unknown'),
        'uom': kpi_info.get('uom', 'USD'),
        'year': year,
        'annual_target': annual_target,
        'weight': weight,
        'notes': notes if notes else None
    }
    
    # Add to batch
    if '_kpi_batch_items' not in st.session_state:
        st.session_state['_kpi_batch_items'] = []
    st.session_state['_kpi_batch_items'].append(new_item)
    
    # Reset input values for next entry
    default_weight = kpi_info.get('default_weight', 0)
    st.session_state['kpi_batch_target'] = 0
    st.session_state['kpi_batch_weight'] = default_weight
    st.session_state['kpi_batch_notes'] = ""
    
    # Set success message to show
    st.session_state['_kpi_batch_success'] = f"Added **{kpi_info.get('kpi_name', 'KPI')}** for **{employee_name}**"
    
    # Clear any previous error
    st.session_state.pop('_kpi_batch_error', None)


@st.dialog("➕ Add KPI Assignments", width="large")
def _add_kpi_assignment_dialog():
    """
    Dialog for adding KPI assignments with BATCH ADD support.
    
    v2.1.0: UX IMPROVEMENT - Separated sections with confirmation:
            - "Add New Assignment" section with "Add to Queue" only
            - "Pending Assignments" section with "Clear All" and "Save All"
            - Added confirmation popover for "Save All Assignments"
            - Removed "Add & Save" button to prevent accidental saves
            - Visual separation between sections with borders
    v2.0.3: FIX - Add to Queue now uses callback pattern:
            - Callback runs BEFORE re-render → batch queue updates immediately
            - No full page rerun, dialog stays open smoothly
    v2.0.2: (Deprecated) Used reopen flag pattern with full page rerun
    v2.0.1: FIX - KPI Type change now updates fields immediately
    v2.0.0: NEW - Modal pattern with batch add capability.
    """
    ctx = st.session_state.get('_kpi_dialog_context', {})
    user_id = ctx.get('user_id')
    editable_employee_ids = ctx.get('editable_employee_ids')
    access_level = ctx.get('access_level', 'self')
    year = ctx.get('year', date.today().year)
    pre_selected_employee_id = ctx.get('pre_selected_employee_id')
    employee_ids_scope = ctx.get('employee_ids_scope')
    
    setup_queries = SalespersonSetupQueries(user_id=user_id)
    
    # Initialize batch list
    if '_kpi_batch_items' not in st.session_state:
        st.session_state['_kpi_batch_items'] = []
    
    batch_items = st.session_state['_kpi_batch_items']
    
    # =========================================================================
    # ADD NEW ASSIGNMENT SECTION - v2.1.0: At TOP for better UX flow
    # =========================================================================
    with st.container(border=True):
        st.markdown("### ➕ Add New Assignment")
        st.caption("Fill in the details below and click 'Add to Queue'")
        
        # Get dropdown data
        salespeople_df = setup_queries.get_salespeople_for_dropdown()
        
        # Filter by accessible scope first
        if employee_ids_scope is not None and not salespeople_df.empty:
            salespeople_df = salespeople_df[
                salespeople_df['employee_id'].isin(employee_ids_scope)
            ]
        
        # Then filter by editable scope
        if editable_employee_ids is not None and not salespeople_df.empty:
            salespeople_df = salespeople_df[
                salespeople_df['employee_id'].isin(editable_employee_ids)
            ].reset_index(drop=True)
        
        kpi_types_df = setup_queries.get_kpi_types()
        
        if salespeople_df.empty:
            st.warning("No salespeople available for assignment")
            return
        
        if kpi_types_df.empty:
            st.warning("No KPI types defined in the system")
            return
        
        # ROW 1: Salesperson and KPI Type
        selector_col1, selector_col2 = st.columns(2)
        
        with selector_col1:
            sp_label = "Salesperson *"
            if access_level == 'self':
                sp_label = "Salesperson * (your account)"
            elif access_level == 'team':
                sp_label = "Salesperson * (team members)"
            
            # Pre-select employee if provided
            default_idx = 0
            if pre_selected_employee_id and not salespeople_df.empty:
                matches = salespeople_df[salespeople_df['employee_id'] == pre_selected_employee_id]
                if not matches.empty:
                    default_idx = salespeople_df.index.tolist().index(matches.index[0])
            
            employee_id = st.selectbox(
                sp_label,
                options=salespeople_df['employee_id'].tolist(),
                index=default_idx,
                format_func=lambda x: f"👤 {salespeople_df[salespeople_df['employee_id'] == x]['employee_name'].iloc[0]}",
                key="kpi_batch_employee"
            )
        
        with selector_col2:
            kpi_type_id = st.selectbox(
                "KPI Type *",
                options=kpi_types_df['kpi_type_id'].tolist(),
                format_func=lambda x: f"{KPI_ICONS.get(kpi_types_df[kpi_types_df['kpi_type_id'] == x]['kpi_name'].iloc[0].lower().replace(' ', '_'), '📋')} {kpi_types_df[kpi_types_df['kpi_type_id'] == x]['kpi_name'].iloc[0]}",
                key="kpi_batch_type"
            )
        
        # Get UOM and defaults for selected KPI type
        selected_kpi = kpi_types_df[kpi_types_df['kpi_type_id'] == kpi_type_id].iloc[0]
        selected_uom = selected_kpi['unit_of_measure']
        selected_kpi_name = selected_kpi['kpi_name']
        default_weight = int(selected_kpi.get('default_weight', 0) or 0)
        
        # v2.0.3: Store info in session state for callback to access
        employee_name = salespeople_df[
            salespeople_df['employee_id'] == employee_id
        ]['employee_name'].iloc[0] if employee_id else 'Unknown'
        st.session_state['_kpi_batch_current_employee_name'] = employee_name
        st.session_state['_kpi_batch_current_kpi_info'] = {
            'kpi_name': selected_kpi_name,
            'uom': selected_uom,
            'default_weight': default_weight
        }
        
        # Determine step and label based on UOM
        is_currency = selected_uom == 'USD'
        target_step = 10000 if is_currency else 1
        target_label = f"Annual Target ({selected_uom}) *"
        
        # ROW 2: Target and Weight
        input_col1, input_col2 = st.columns(2)
        
        with input_col1:
            annual_target = st.number_input(
                target_label,
                min_value=0,
                value=0,
                step=target_step,
                key="kpi_batch_target"
            )
            
            # v2.1.0: Show breakdown with year/quarter/month - all with proper formatting
            if annual_target > 0:
                if is_currency:
                    # Currency format with commas
                    year_display = format_currency(annual_target)
                    quarter_display = format_currency(annual_target / 4)
                    month_display = format_currency(annual_target / 12)
                    st.caption(f"💡 {year_display}/year • {quarter_display}/quarter • {month_display}/month")
                else:
                    # Count format with commas
                    year_display = f"{annual_target:,.0f}"
                    quarter_display = f"{annual_target / 4:,.1f}"
                    month_display = f"{annual_target / 12:,.1f}"
                    st.caption(f"💡 {year_display}/year • {quarter_display}/quarter • {month_display}/month")
        
        with input_col2:
            weight = st.number_input(
                "Weight % *",
                min_value=0,
                max_value=100,
                value=default_weight,
                step=5,
                key="kpi_batch_weight"
            )
        
        # Validation preview
        if employee_id:
            validation = setup_queries.validate_assignment_weight(
                employee_id=employee_id,
                year=year,
                new_weight=weight
            )
            
            batch_weight_for_emp = sum(
                item['weight'] for item in batch_items 
                if item['employee_id'] == employee_id and item['year'] == year
            )
            total_with_batch = validation['current_total'] + batch_weight_for_emp + weight
            
            val_col1, val_col2 = st.columns(2)
            with val_col1:
                st.metric("Current DB Weight", f"{validation['current_total']}%")
            with val_col2:
                if total_with_batch == 100:
                    st.success(f"✅ Total after save: {total_with_batch}%")
                elif total_with_batch > 100:
                    st.error(f"🔴 Total after save: {total_with_batch}% (over limit!)")
                else:
                    st.warning(f"⚠️ Total after save: {total_with_batch}% ({100 - total_with_batch}% remaining)")
        
        # Notes
        notes = st.text_input("Notes (optional)", key="kpi_batch_notes")
        
        # Check for duplicates
        is_duplicate_in_batch = any(
            item['employee_id'] == employee_id and 
            item['kpi_type_id'] == kpi_type_id and 
            item['year'] == year
            for item in batch_items
        )
        
        # Check if already exists in DB
        existing_check = setup_queries.get_kpi_assignments(
            year=year, 
            employee_ids=[employee_id]
        )
        existing_for_kpi = existing_check[existing_check['kpi_type_id'] == kpi_type_id] if not existing_check.empty else pd.DataFrame()
        already_exists_in_db = not existing_for_kpi.empty
        
        # Store DB exists info for callback
        st.session_state['_kpi_batch_already_exists_in_db'] = already_exists_in_db
        
        # Show validation errors before buttons
        validation_error = None
        if annual_target <= 0:
            validation_error = "Annual target must be greater than 0"
        elif weight <= 0:
            validation_error = "Weight must be greater than 0"
        elif is_duplicate_in_batch:
            validation_error = "This employee/KPI/year combination is already in the queue"
        elif already_exists_in_db:
            validation_error = "Assignment already exists for this employee/KPI/year in database"
        
        if validation_error:
            st.error(f"❌ {validation_error}")
        
        # Show success/error messages from callback
        if '_kpi_batch_success' in st.session_state:
            st.success(f"✅ {st.session_state['_kpi_batch_success']}")
            del st.session_state['_kpi_batch_success']
        
        if '_kpi_batch_error' in st.session_state:
            st.error(f"❌ {st.session_state['_kpi_batch_error']}")
            del st.session_state['_kpi_batch_error']
        
        st.divider()
        
        # v2.1.0: Only "Add to Queue" button - no "Add & Save"
        st.button(
            "➕ Add to Queue",
            type="primary",
            use_container_width=True,
            disabled=(validation_error is not None),
            on_click=_add_to_queue_callback,
            key="kpi_add_to_queue_btn"
        )
    
    # =========================================================================
    # PENDING ASSIGNMENTS SECTION - v2.1.0: At BOTTOM after form
    # =========================================================================
    if batch_items:
        st.divider()
        
        with st.container(border=True):
            st.markdown("### 📋 Pending Assignments")
            st.caption(f"{len(batch_items)} assignment(s) ready to save")
            
            st.divider()
            
            # Display batch items in a compact format
            for idx, item in enumerate(batch_items):
                cols = st.columns([3, 2, 2, 1, 1])
                
                with cols[0]:
                    st.markdown(f"**👤 {item['employee_name']}**")
                with cols[1]:
                    icon = KPI_ICONS.get(item['kpi_name'].lower().replace(' ', '_'), '📋')
                    st.markdown(f"{icon} {item['kpi_name']}")
                with cols[2]:
                    if item.get('uom') == 'USD':
                        target_display = format_currency(item['annual_target'])
                    else:
                        target_display = f"{item['annual_target']:,.0f}"
                    st.caption(f"Target: {target_display} • Weight: {item['weight']}%")
                with cols[3]:
                    st.caption(f"Year: {item['year']}")
                with cols[4]:
                    if st.button("🗑️", key=f"kpi_batch_remove_{idx}", help="Remove from queue"):
                        st.session_state['_kpi_batch_items'].pop(idx)
                        st.rerun()
                
                if idx < len(batch_items) - 1:
                    st.divider()
            
            st.divider()
            
            # Batch actions - v2.1.0: Save All with confirmation popover
            action_col1, action_col2 = st.columns([1, 1])
            
            with action_col1:
                if st.button("🗑️ Clear All", use_container_width=True, type="secondary", key="kpi_clear_all_bottom"):
                    st.session_state['_kpi_batch_items'] = []
                    st.rerun()
            
            with action_col2:
                # v2.1.0: Use popover for confirmation
                with st.popover("💾 Save All Assignments", use_container_width=True):
                    st.warning(f"⚠️ **Confirm Save**")
                    st.caption(f"About to create **{len(batch_items)} assignment(s)** in database")
                    
                    # Show summary by employee
                    emp_summary = {}
                    for item in batch_items:
                        emp_id = item['employee_id']
                        if emp_id not in emp_summary:
                            emp_summary[emp_id] = {
                                'name': item['employee_name'],
                                'count': 0,
                                'total_weight': 0
                            }
                        emp_summary[emp_id]['count'] += 1
                        emp_summary[emp_id]['total_weight'] += item['weight']
                    
                    st.markdown("**Summary by Employee:**")
                    for emp_id, info in emp_summary.items():
                        weight_status = "✅" if info['total_weight'] == 100 else "⚠️"
                        st.caption(f"{weight_status} {info['name']}: {info['count']} KPI{'s' if info['count'] > 1 else ''} ({info['total_weight']:.0f}% weight)")
                    
                    st.divider()
                    
                    if st.button("✅ Confirm & Save All", type="primary", use_container_width=True, key="kpi_confirm_save_all"):
                        success_count = 0
                        error_count = 0
                        error_messages = []
                        created_ids = []
                        
                        progress_bar = st.progress(0, text="Saving assignments...")
                        
                        for i, item in enumerate(batch_items):
                            progress_bar.progress((i + 1) / len(batch_items), text=f"Saving {i+1}/{len(batch_items)}...")
                            
                            result = setup_queries.create_assignment(
                                employee_id=item['employee_id'],
                                kpi_type_id=item['kpi_type_id'],
                                year=item['year'],
                                annual_target_value=item['annual_target'],
                                weight=item['weight'],
                                notes=item.get('notes')
                            )
                            if result['success']:
                                success_count += 1
                                created_ids.append(result['id'])
                            else:
                                error_count += 1
                                error_messages.append(f"{item['employee_name']}/{item['kpi_name']}: {result['message']}")
                        
                        progress_bar.empty()
                        
                        # Clear batch
                        st.session_state['_kpi_batch_items'] = []
                        
                        if success_count > 0:
                            _set_notification(
                                '_kpi_assignments_notification', 'success',
                                f"Created {success_count} KPI assignment(s)",
                                f"Assignment IDs: {', '.join(map(str, created_ids[:5]))}{'...' if len(created_ids) > 5 else ''}",
                                affected_ids=created_ids
                            )
                            _bump_data_version('kpi')
                        
                        if error_count > 0:
                            st.error(f"❌ Failed to create {error_count} assignment(s)")
                            for msg in error_messages[:3]:
                                st.caption(f"• {msg}")
                        else:
                            st.rerun()


@st.dialog("✏️ Edit KPI Assignment", width="large")
def _edit_kpi_assignment_dialog(assignment_id: int):
    """
    Dialog for editing existing KPI assignment.
    
    v2.0.0: NEW - Modal pattern for edit.
    """
    ctx = st.session_state.get('_kpi_dialog_context', {})
    user_id = ctx.get('user_id')
    year = ctx.get('year', date.today().year)
    
    setup_queries = SalespersonSetupQueries(user_id=user_id)
    
    # Get existing assignment
    assignments_df = setup_queries.get_kpi_assignments()
    existing_df = assignments_df[assignments_df['assignment_id'] == assignment_id]
    
    if existing_df.empty:
        st.error("Assignment not found")
        return
    
    existing = existing_df.iloc[0]
    
    # Header info
    st.markdown(f"**Assignment ID:** #{assignment_id}")
    
    info_col1, info_col2 = st.columns(2)
    with info_col1:
        st.markdown(f"**👤 Salesperson:** {existing['employee_name']}")
    with info_col2:
        icon = KPI_ICONS.get(existing['kpi_name'].lower().replace(' ', '_'), '📋')
        st.markdown(f"**{icon} KPI:** {existing['kpi_name']}")
    
    st.divider()
    
    # Current weight summary for this employee
    weight_summary = setup_queries.get_assignment_weight_summary(existing['year'])
    emp_weight = weight_summary[weight_summary['employee_id'] == existing['employee_id']]
    current_total_weight = int(emp_weight['total_weight'].iloc[0]) if not emp_weight.empty else 0
    
    # Edit form
    with st.form("kpi_edit_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            # Annual target
            selected_uom = existing['unit_of_measure']
            annual_target = st.number_input(
                f"Annual Target ({selected_uom}) *",
                min_value=0,
                value=int(existing['annual_target_value_numeric']),
                step=10000 if selected_uom == 'USD' else 1,
                key="kpi_edit_target"
            )
            
            # v2.1.0: Show breakdown with year/quarter/month - consistent with add dialog
            if annual_target > 0:
                if selected_uom == 'USD':
                    # Currency format with commas
                    year_display = format_currency(annual_target)
                    quarter_display = format_currency(annual_target / 4)
                    month_display = format_currency(annual_target / 12)
                    st.caption(f"💡 {year_display}/year • {quarter_display}/quarter • {month_display}/month")
                else:
                    # Count format with commas
                    year_display = f"{annual_target:,.0f}"
                    quarter_display = f"{annual_target / 4:,.1f}"
                    month_display = f"{annual_target / 12:,.1f}"
                    st.caption(f"💡 {year_display}/year • {quarter_display}/quarter • {month_display}/month")
        
        with col2:
            # Weight
            weight = st.number_input(
                "Weight % *",
                min_value=0,
                max_value=100,
                value=int(existing['weight_numeric']),
                step=5,
                key="kpi_edit_weight"
            )
        
        # Weight validation
        old_weight = int(existing['weight_numeric'])
        weight_diff = weight - old_weight
        new_total = current_total_weight + weight_diff
        
        val_col1, val_col2 = st.columns(2)
        with val_col1:
            st.metric("Current Total Weight", f"{current_total_weight}%")
        with val_col2:
            if new_total == 100:
                st.success(f"✅ After save: {new_total}%")
            elif new_total > 100:
                st.error(f"🔴 After save: {new_total}% (over limit!)")
            else:
                st.warning(f"⚠️ After save: {new_total}% ({100 - new_total}% remaining)")
        
        # Notes
        notes = st.text_input(
            "Notes (optional)",
            value=existing['notes'] if pd.notna(existing.get('notes')) else "",
            key="kpi_edit_notes"
        )
        
        st.divider()
        
        # Form buttons
        col_save, col_cancel = st.columns(2)
        
        with col_save:
            submitted = st.form_submit_button("💾 Update", type="primary", use_container_width=True)
        
        with col_cancel:
            cancelled = st.form_submit_button("❌ Cancel", use_container_width=True)
        
        if submitted:
            if annual_target <= 0:
                st.error("Annual target must be greater than 0")
            elif weight <= 0:
                st.error("Weight must be greater than 0")
            else:
                result = setup_queries.update_assignment(
                    assignment_id=assignment_id,
                    annual_target_value=annual_target,
                    weight=weight,
                    notes=notes if notes else None
                )
                
                if result['success']:
                    _set_notification(
                        '_kpi_assignments_notification', 'success',
                        f"KPI assignment updated",
                        f"#{assignment_id} • Target: {format_currency(annual_target) if selected_uom == 'USD' else annual_target} • Weight: {weight}%",
                        affected_ids=[assignment_id]
                    )
                    _bump_data_version('kpi')
                    st.rerun()
                else:
                    st.error(f"❌ {result['message']}")
        
        if cancelled:
            st.rerun()


@st.dialog("🗑️ Delete KPI Assignment", width="small")
def _delete_kpi_assignment_dialog(assignment_id: int, assignment_info: dict):
    """
    Confirmation dialog for deleting KPI assignment.
    
    v2.0.0: NEW - Confirmation modal before delete.
    """
    ctx = st.session_state.get('_kpi_dialog_context', {})
    user_id = ctx.get('user_id')
    
    setup_queries = SalespersonSetupQueries(user_id=user_id)
    
    st.warning("⚠️ **Are you sure you want to delete this assignment?**")
    
    st.markdown(f"""
    - **Assignment ID:** #{assignment_id}
    - **Salesperson:** {assignment_info.get('employee_name', 'N/A')}
    - **KPI:** {assignment_info.get('kpi_name', 'N/A')}
    - **Target:** {assignment_info.get('target_display', 'N/A')}
    - **Weight:** {assignment_info.get('weight', 0)}%
    """)
    
    st.caption("This action cannot be undone.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🗑️ Yes, Delete", type="primary", use_container_width=True):
            result = setup_queries.delete_assignment(assignment_id)
            
            if result['success']:
                _set_notification(
                    '_kpi_assignments_notification', 'success',
                    f"KPI assignment deleted",
                    f"Assignment #{assignment_id} removed",
                    affected_ids=[assignment_id]
                )
                _bump_data_version('kpi')
                st.rerun()
            else:
                st.error(f"❌ {result['message']}")
    
    with col2:
        if st.button("❌ Cancel", use_container_width=True):
            st.rerun()


# =============================================================================
# KPI ASSIGNMENTS SECTION (v2.0.0 - Refactored with Modal Pattern)
# =============================================================================

@st.fragment
def kpi_assignments_section(
    setup_queries: SalespersonSetupQueries,
    employee_ids: List[int] = None,
    editable_employee_ids: List[int] = None,  # v1.2.0
    can_edit_base: bool = False,  # v1.2.0: Renamed from can_edit
    current_year: int = None,
    access_level: str = 'self',  # v1.2.0
    user_employee_id: int = None  # v1.2.0
):
    """
    KPI Assignments sub-tab.
    
    v2.0.0: MAJOR REFACTOR - Modal/Dialog pattern with Batch Add
            - Uses dialogs instead of inline forms (like Split Rules)
            - Batch add support for creating multiple assignments at once
            - Improved notifications with row highlighting
    v1.9.0: REFACTOR - Self-contained data fetching with version-based cache
            - Data fetched internally using _get_cached_kpi_data()
            - Cache invalidated automatically after CRUD via _bump_data_version()
    v1.1.0: Added KPI Summary by Type section (synced with KPI Center Performance)
    v1.2.0: Hybrid authorization - record-level permissions
    v1.8.0: Added notification banner
    """
    # =========================================================================
    # v1.8.0: Show notification banner (persists after action)
    # =========================================================================
    KPI_NOTIF_KEY = '_kpi_assignments_notification'
    highlighted_ids = _show_notification(KPI_NOTIF_KEY)
    
    # Helper to check if user can modify a specific record
    def can_modify_this_record(record_owner_id: int) -> bool:
        """Check if current user can edit/delete this specific record."""
        if not can_edit_base:
            return False
        return can_modify_record(record_owner_id, access_level, editable_employee_ids)
    
    current_year = current_year or date.today().year
    
    # =========================================================================
    # v2.0.0: Store dialog context for modal functions
    # =========================================================================
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    st.session_state['_kpi_dialog_context'] = {
        'user_id': user_id,
        'editable_employee_ids': editable_employee_ids,
        'access_level': access_level,
        'year': current_year,
        'employee_ids_scope': employee_ids,
        'pre_selected_employee_id': None  # Will be set when clicking Add from employee card
    }
    
    # v2.0.3: Removed _kpi_reopen_dialog flag - no longer needed
    # Add to Queue now works without closing dialog
    
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
            key="sp_assign_year_filter"
        )
        
        # Update context with selected year
        st.session_state['_kpi_dialog_context']['year'] = selected_year
    
    with col2:
        salespeople_df = setup_queries.get_salespeople_for_dropdown(include_inactive=True)
        
        # FIX v1.5.3: Filter by accessible employee scope (was missing)
        if employee_ids is not None:
            salespeople_df = salespeople_df[
                salespeople_df['employee_id'].isin(employee_ids)
            ]
        
        salesperson_options = [(-1, "All Salespeople")] + [
            (row['employee_id'], f"👤 {row['employee_name']}") 
            for _, row in salespeople_df.iterrows()
        ]
        selected_employee_id = st.selectbox(
            "Salesperson",
            options=[s[0] for s in salesperson_options],
            format_func=lambda x: next((s[1] for s in salesperson_options if s[0] == x), ""),
            key="sp_assign_employee_filter"
        )
    
    with col3:
        # v2.0.0: Use dialog instead of inline form
        if can_edit_base:
            st.write("")
            if st.button("➕ Add Assignment", type="primary", use_container_width=True):
                # Clear any pre-selection and batch items
                st.session_state['_kpi_dialog_context']['pre_selected_employee_id'] = None
                if '_kpi_batch_items' in st.session_state:
                    st.session_state['_kpi_batch_items'] = []
                _add_kpi_assignment_dialog()
    
    # -------------------------------------------------------------------------
    # KPI SUMMARY BY TYPE (v1.1.0 - NEW - Synced with KPI Center Performance)
    # FIX v1.5.3: Filter by employee_ids for team scope
    # -------------------------------------------------------------------------
    summary_df = setup_queries.get_assignment_summary_by_type(selected_year, employee_ids=employee_ids)
    
    if not summary_df.empty:
        st.markdown(f"##### 📊 {selected_year} Targets Overview")
        
        # Create summary cards
        num_kpis = len(summary_df)
        cols = st.columns(min(num_kpis, 4))
        
        for idx, (_, row) in enumerate(summary_df.iterrows()):
            col_idx = idx % 4
            kpi_lower = row['kpi_name'].lower().replace(' ', '_')
            icon = KPI_ICONS.get(kpi_lower, '📋')
            
            with cols[col_idx]:
                # Format target based on UOM
                if row['unit_of_measure'] == 'USD':
                    target_display = format_currency(row['total_target'])
                else:
                    target_display = f"{row['total_target']:,.0f}"
                
                st.metric(
                    label=f"{icon} {row['kpi_name']}",
                    value=target_display,
                    delta=f"{row['employee_count']} salespeople",
                    delta_color="off",
                    help=f"Total {row['kpi_name']} target for {selected_year}"
                )
        
        st.divider()
    
    # -------------------------------------------------------------------------
    # ISSUES SECTION
    # FIX v1.5.3: Pass employee_ids to filter by team scope (was missing)
    # v2.0.0: Use dialog for adding assignments
    # -------------------------------------------------------------------------
    issues = setup_queries.get_assignment_issues_summary(selected_year, employee_ids=employee_ids)
    
    critical_count = issues['no_assignment_count']
    warning_count = issues['weight_issues_count']
    
    has_issues = critical_count > 0 or warning_count > 0
    
    if has_issues:
        if critical_count > 0:
            expander_title = f"🔴 {critical_count} Missing Assignments"
        else:
            expander_title = f"⚠️ {warning_count} Weight Issues"
        
        with st.expander(expander_title, expanded=(critical_count > 0)):
            
            # Missing assignments
            if issues['no_assignment_count'] > 0:
                st.markdown("##### 🔴 Salespeople Without Assignments")
                st.caption(f"{issues['no_assignment_count']} active salespeople need {selected_year} KPI assignments")
                
                with st.container(border=True):
                    for emp in issues['no_assignment_details']:
                        col_info, col_action = st.columns([4, 1])
                        with col_info:
                            st.markdown(f"👤 **{emp['name']}**")
                            st.caption(emp.get('email', ''))
                        with col_action:
                            # v2.0.0: Use dialog instead of inline form
                            if can_edit_base and can_modify_this_record(emp['id']):
                                if st.button(
                                    "➕ Add", 
                                    key=f"sp_add_assign_{emp['id']}", 
                                    use_container_width=True
                                ):
                                    # Pre-select this employee in dialog
                                    st.session_state['_kpi_dialog_context']['pre_selected_employee_id'] = emp['id']
                                    if '_kpi_batch_items' in st.session_state:
                                        st.session_state['_kpi_batch_items'] = []
                                    _add_kpi_assignment_dialog()
                
                st.divider()
            
            # Weight issues
            if issues['weight_issues_count'] > 0:
                st.markdown("##### ⚠️ Weight Sum ≠ 100%")
                st.caption(f"{issues['weight_issues_count']} salespeople have weights not summing to 100%")
                
                with st.container(border=True):
                    for emp in issues['weight_issues_details']:
                        col_info, col_weight, col_action = st.columns([3, 1, 1])
                        with col_info:
                            st.markdown(f"**{emp['employee_name']}**")
                        with col_weight:
                            weight = emp['total_weight']
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
    # v2.0.0: Inline forms removed - Now using Modal Dialogs
    # See: _add_kpi_assignment_dialog(), _edit_kpi_assignment_dialog()
    # -------------------------------------------------------------------------
    
    # -------------------------------------------------------------------------
    # GET DATA (v1.9.0: Using version-based cache)
    # -------------------------------------------------------------------------
    filter_employee_ids = None
    if selected_employee_id > 0:
        filter_employee_ids = [selected_employee_id]
    elif employee_ids:
        filter_employee_ids = employee_ids
    
    assignments_df = _get_cached_kpi_data(
        setup_queries, 
        year=selected_year, 
        employee_ids=filter_employee_ids
    )
    weight_summary_df = setup_queries.get_assignment_weight_summary(selected_year)
    
    if assignments_df.empty:
        st.info(f"No KPI assignments found for {selected_year}")
        return
    
    # -------------------------------------------------------------------------
    # ASSIGNMENTS BY SALESPERSON - Card layout
    # -------------------------------------------------------------------------
    for emp_id in assignments_df['employee_id'].unique():
        emp_data = assignments_df[assignments_df['employee_id'] == emp_id]
        emp_name = emp_data.iloc[0]['employee_name']
        emp_email = emp_data.iloc[0]['employee_email']
        emp_status = emp_data.iloc[0]['employee_status']
        
        # Get weight sum
        weight_row = weight_summary_df[weight_summary_df['employee_id'] == emp_id]
        total_weight = int(weight_row['total_weight'].iloc[0]) if not weight_row.empty else 0
        kpi_count = len(emp_data)
        
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
        
        status_icon = STATUS_ICONS.get(emp_status, '❓')
        
        # v1.2.0: Check if user can modify records for this employee
        can_modify_for_emp = can_modify_this_record(emp_id)
        
        # Card container
        with st.container(border=True):
            # Header
            header_col1, header_col2 = st.columns([4, 1])
            
            with header_col1:
                st.markdown(f"### {status_icon} {emp_name}")
                st.caption(f"{emp_email} • {kpi_count} KPI{'s' if kpi_count > 1 else ''}")
            
            with header_col2:
                st.metric(
                    label="Weight Sum",
                    value=f"{total_weight}%",
                    delta=weight_badge,
                    delta_color=weight_color,
                    help="Total weight should equal 100%"
                )
            
            # KPI rows (v2.0.0: Pass highlighted_ids for row highlighting)
            for _, kpi in emp_data.iterrows():
                is_highlighted = kpi['assignment_id'] in highlighted_ids
                _render_kpi_assignment_row(kpi, can_modify_for_emp, setup_queries, is_highlighted)
            
            # Add KPI button (v2.0.0: Use dialog instead of inline form)
            if can_edit_base and can_modify_for_emp:
                if st.button(
                    f"➕ Add KPI to {emp_name}", 
                    key=f"sp_add_kpi_btn_{emp_id}",
                    use_container_width=True
                ):
                    # Pre-select this employee in dialog
                    st.session_state['_kpi_dialog_context']['pre_selected_employee_id'] = emp_id
                    if '_kpi_batch_items' in st.session_state:
                        st.session_state['_kpi_batch_items'] = []
                    _add_kpi_assignment_dialog()


def _render_kpi_assignment_row(
    kpi: pd.Series, 
    can_edit: bool, 
    setup_queries: SalespersonSetupQueries,
    is_highlighted: bool = False
):
    """
    Render a single KPI assignment row.
    
    v2.0.0: Added dialog support and row highlighting.
    
    Args:
        kpi: Series with KPI assignment data
        can_edit: Whether user can edit this assignment
        setup_queries: Query handler
        is_highlighted: Whether this row was recently modified (for visual highlight)
    """
    kpi_lower = kpi['kpi_name'].lower().replace(' ', '_')
    icon = KPI_ICONS.get(kpi_lower, '📋')
    
    # v2.0.0: Add visual highlight for recently modified rows
    if is_highlighted:
        st.markdown("""
            <style>
            .highlighted-row {
                background-color: #d4edda;
                border-left: 4px solid #28a745;
                padding-left: 8px;
                margin: 4px 0;
                border-radius: 4px;
            }
            </style>
        """, unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
    
    with col1:
        if is_highlighted:
            st.markdown(f"**{icon} {kpi['kpi_name']}** ✨")
        else:
            st.markdown(f"**{icon} {kpi['kpi_name']}**")
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
        if can_edit:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                # v2.0.0: Use edit dialog
                if st.button("✏️", key=f"sp_edit_assign_{kpi['assignment_id']}", help="Edit"):
                    _edit_kpi_assignment_dialog(kpi['assignment_id'])
            
            with btn_col2:
                # v2.0.0: Use delete confirmation dialog
                if st.button("🗑️", key=f"sp_del_assign_{kpi['assignment_id']}", help="Delete"):
                    # Prepare info for confirmation dialog
                    if kpi['unit_of_measure'] == 'USD':
                        target_display = format_currency(kpi['annual_target_value_numeric'])
                    else:
                        target_display = f"{kpi['annual_target_value_numeric']:,.0f}"
                    
                    assignment_info = {
                        'employee_name': kpi['employee_name'],
                        'kpi_name': kpi['kpi_name'],
                        'target_display': target_display,
                        'weight': int(kpi['weight_numeric'])
                    }
                    _delete_kpi_assignment_dialog(kpi['assignment_id'], assignment_info)


# =============================================================================
# v2.0.0: _render_assignment_form() has been REMOVED
# Functionality replaced by:
# - _add_kpi_assignment_dialog() - Modal for adding (with batch support)
# - _edit_kpi_assignment_dialog() - Modal for editing
# - _delete_kpi_assignment_dialog() - Confirmation modal for delete
# =============================================================================


# =============================================================================
# SALESPEOPLE SECTION
# =============================================================================

@st.fragment  
def salespeople_section(
    setup_queries: SalespersonSetupQueries,
    employee_ids: List[int] = None,  # FIX v1.3.1: Filter by team scope
    can_edit: bool = False
):
    """
    Salespeople sub-tab with list view.
    
    FIX v1.3.1: Added employee_ids parameter to filter by team scope.
    Non-admin users should only see their team members.
    """
    
    # Toolbar
    col1, col2 = st.columns([1, 5])
    
    with col1:
        status_options = {
            'ACTIVE': '🟢 Active',
            'all': '📋 All Status',
            'INACTIVE': '🟡 Inactive',
            'TERMINATED': '🔴 Terminated',
            'ON_LEAVE': '🟠 On Leave'
        }
        status_filter = st.selectbox(
            "Status",
            options=list(status_options.keys()),
            format_func=lambda x: status_options[x],
            key="sp_salespeople_status"
        )
    
    with col2:
        search = st.text_input("🔍 Search", placeholder="Name or email...", key="sp_salespeople_search")
    
    st.divider()
    
    # Get salespeople
    include_inactive = (status_filter == 'all')
    status_param = status_filter if status_filter != 'all' else None
    
    salespeople_df = setup_queries.get_salespeople(
        status_filter=status_param,
        include_inactive=include_inactive
    )
    
    # FIX v1.3.1: Filter by employee_ids (team scope)
    if not salespeople_df.empty and employee_ids is not None:
        salespeople_df = salespeople_df[salespeople_df['employee_id'].isin(employee_ids)]
    
    # Client-side search
    if not salespeople_df.empty and search:
        search_lower = search.lower()
        mask = (
            salespeople_df['employee_name'].fillna('').str.lower().str.contains(search_lower, regex=False) |
            salespeople_df['email'].fillna('').str.lower().str.contains(search_lower, regex=False)
        )
        salespeople_df = salespeople_df[mask]
    
    if salespeople_df.empty:
        st.info("No salespeople found")
        return
    
    st.caption(f"📊 Showing **{len(salespeople_df)}** salespeople")
    
    # Render cards
    for _, row in salespeople_df.iterrows():
        status_icon = STATUS_ICONS.get(row['status'], '❓')
        
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 1])
            
            with col1:
                st.markdown(f"### {status_icon} {row['employee_name']}")
                st.caption(row['email'] or '')
                
                # Position info
                info_parts = []
                if row.get('title_name') and pd.notna(row['title_name']):
                    info_parts.append(row['title_name'])
                if row.get('department_name') and pd.notna(row['department_name']):
                    info_parts.append(row['department_name'])
                if info_parts:
                    st.caption(" • ".join(info_parts))
            
            with col2:
                # Stats
                st.metric(
                    label="Active Splits",
                    value=row['active_split_count'],
                    help="Number of active split rules"
                )
            
            with col3:
                st.metric(
                    label=f"{date.today().year} KPIs",
                    value=row['current_year_kpi_count'],
                    help=f"Number of KPI assignments for {date.today().year}"
                )
            
            # Manager info
            if row.get('manager_name') and pd.notna(row['manager_name']):
                st.caption(f"👔 Manager: {row['manager_name']}")