# utils/kpi_center_performance/filters.py
"""
Sidebar Filter Components for KPI Center Performance

VERSION: 5.1.0
CHANGELOG:
- v5.1.0: Optimized caching for filters
  - _get_kpi_centers_with_assignments() now uses cached targets_raw_df (no SQL)
  - Added warning message when Custom period is before cached data range
  - Added custom_start_date to filter_values for dynamic loading trigger
  - Simplified _expand_kpi_center_ids_with_children() (deprecated, uses cache)
- v5.0.1: Added get_backlog_period_dates() function
  - Helper to calculate correct ETD filter range for In-Period Backlog
  - YTD: Jan 1 - Dec 31 (full year)
  - QTD: Quarter start - Quarter end
  - MTD: Month start - Month end
- v5.0.0: Replaced multiselect with single-selection tree component
  - Prevents parent-child double counting
  - New "Include sub-centers" toggle
  - Search filter for large trees
  - Uses new kpi_center_selector.py component
- v4.1.0: Added analyze_period() with full period context
- v2.15.0: Auto-uncheck "Only with KPI" when no assignments
- v2.14.0: Added kpi_type parameter to assignment filter
- v2.12.0: Added hierarchy display with tree visualization
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
import pandas as pd
import streamlit as st
from sqlalchemy import text

from .constants import PERIOD_TYPES, MONTH_ORDER
from .access_control import AccessControl

logger = logging.getLogger(__name__)


# =============================================================================
# KPI ASSIGNMENT HELPER
# =============================================================================

def _get_kpi_centers_with_assignments(
    years: List[int],
    kpi_type: str = None  # NEW v2.14.0: Optional KPI Type filter
) -> List[int]:
    """
    Get list of KPI Center IDs that have KPI assignments in given years.
    
    UPDATED v4.1.0: Now uses cached targets_raw_df from UnifiedDataLoader
    instead of executing SQL query every time. Falls back to SQL only if
    cache is not available.
    
    UPDATED v2.14.0: Added kpi_type parameter to filter by KPI Type.
    This fixes the bug where TERRITORY filter shows 0 results when only
    VERTICAL has assignments for the selected year.
    
    UPDATED v2.12.0: Now includes all ancestors (parents) of KPI Centers 
    with direct assignments. Business logic: Parent KPI = sum of children KPIs,
    so if any child has assignment, parent should also be considered as having assignment.
    
    Args:
        years: List of years to check
        kpi_type: Optional KPI Type to filter (e.g., 'TERRITORY', 'VERTICAL')
        
    Returns:
        List of kpi_center_ids with KPI assignments (direct or inherited from children)
    """
    if not years:
        return []
    
    # TRY 1: Use cached data (instant) - NEW v4.1.0
    from .constants import CACHE_KEY_UNIFIED
    
    cache = st.session_state.get(CACHE_KEY_UNIFIED)
    if cache and not cache.get('targets_raw_df', pd.DataFrame()).empty:
        targets_df = cache['targets_raw_df']
        hierarchy_df = cache.get('hierarchy_df', pd.DataFrame())
        
        # Step 1: Filter targets by years
        mask = targets_df['year'].isin(years)
        
        # Step 2: Filter by KPI Type if specified
        if kpi_type and 'kpi_center_type' in targets_df.columns:
            mask = mask & (targets_df['kpi_center_type'] == kpi_type)
        
        direct_ids = set(targets_df[mask]['kpi_center_id'].unique().tolist())
        
        if not direct_ids:
            logger.debug(f"No direct assignments (cached) for years={years}, kpi_type={kpi_type}")
            return []
        
        if hierarchy_df.empty:
            return list(direct_ids)
        
        # Step 3: Add ancestors (parents) using cached hierarchy
        all_ids = direct_ids.copy()
        
        # Build parent lookup from hierarchy
        parent_lookup = {}
        for _, row in hierarchy_df.iterrows():
            kpc_id = row['kpi_center_id']
            parent_id = row.get('parent_center_id')
            if pd.notna(parent_id):
                parent_lookup[kpc_id] = int(parent_id)
        
        # Get ancestors for each direct ID
        for kpc_id in list(direct_ids):  # list() to avoid set modification during iteration
            current = kpc_id
            while current in parent_lookup:
                parent = parent_lookup[current]
                all_ids.add(parent)
                current = parent
        
        logger.debug(
            f"KPI Centers with assignments (cached): {len(all_ids)} "
            f"({len(direct_ids)} direct) for years={years}, kpi_type={kpi_type}"
        )
        return list(all_ids)
    
    # TRY 2: Fallback to SQL query (only if cache not available)
    logger.debug("Cache not available, falling back to SQL query for KPI assignments")
    
    try:
        from utils.db import get_db_engine
        engine = get_db_engine()
        
        # Build query with optional kpi_type filter
        # Query includes:
        # 1. KPI Centers with direct assignments (optionally filtered by kpi_type)
        # 2. All ancestors (parents) of those KPI Centers
        
        if kpi_type:
            # Filter by KPI Type - JOIN with kpi_centers to check type
            query = """
                WITH RECURSIVE 
                -- Step 1: Get KPI Centers with direct assignments for this type
                direct_assignments AS (
                    SELECT DISTINCT kac.kpi_center_id
                    FROM sales_kpi_center_assignments_view kac
                    JOIN kpi_centers kc ON kac.kpi_center_id = kc.id
                    WHERE kac.year IN :years
                      AND kc.type = :kpi_type
                      AND (kc.delete_flag = 0 OR kc.delete_flag IS NULL)
                ),
                
                -- Step 2: Get all ancestors (parents) recursively
                all_with_ancestors AS (
                    -- Base case: direct assignments
                    SELECT kpi_center_id, kpi_center_id AS original_id
                    FROM direct_assignments
                    
                    UNION
                    
                    -- Recursive case: parents of KPI Centers
                    SELECT kc.parent_center_id AS kpi_center_id, awa.original_id
                    FROM kpi_centers kc
                    INNER JOIN all_with_ancestors awa ON kc.id = awa.kpi_center_id
                    WHERE kc.parent_center_id IS NOT NULL
                      AND (kc.delete_flag = 0 OR kc.delete_flag IS NULL)
                )
                
                SELECT DISTINCT kpi_center_id 
                FROM all_with_ancestors
                WHERE kpi_center_id IS NOT NULL
                ORDER BY kpi_center_id
            """
            params = {'years': tuple(years), 'kpi_type': kpi_type}
        else:
            # Original query without kpi_type filter
            query = """
                WITH RECURSIVE 
                -- Step 1: Get KPI Centers with direct assignments
                direct_assignments AS (
                    SELECT DISTINCT kpi_center_id
                    FROM sales_kpi_center_assignments_view 
                    WHERE year IN :years
                ),
                
                -- Step 2: Get all ancestors (parents) recursively
                all_with_ancestors AS (
                    -- Base case: direct assignments
                    SELECT kpi_center_id, kpi_center_id AS original_id
                    FROM direct_assignments
                    
                    UNION
                    
                    -- Recursive case: parents of KPI Centers
                    SELECT kc.parent_center_id AS kpi_center_id, awa.original_id
                    FROM kpi_centers kc
                    INNER JOIN all_with_ancestors awa ON kc.id = awa.kpi_center_id
                    WHERE kc.parent_center_id IS NOT NULL
                      AND (kc.delete_flag = 0 OR kc.delete_flag IS NULL)
                )
                
                SELECT DISTINCT kpi_center_id 
                FROM all_with_ancestors
                WHERE kpi_center_id IS NOT NULL
                ORDER BY kpi_center_id
            """
            params = {'years': tuple(years)}
        
        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            ids = [row[0] for row in result]
            logger.debug(f"KPI Centers with assignments (SQL fallback): {len(ids)} for years {years}, kpi_type={kpi_type}")
            return ids
            
    except Exception as e:
        logger.error(f"Error fetching KPI Centers with assignments: {e}")
        return []


# =============================================================================
# ENTITY BY KPI TYPE HELPER - REMOVED v4.1.0
# =============================================================================
# NOTE: _get_entities_by_kpi_type() removed - use DataProcessor.get_entities_by_kpi_type() instead
# which uses cached DataFrame instead of SQL query


def _get_entities_from_cache(kpi_type: str = None) -> pd.DataFrame:
    """
    Get Legal Entities from cached sales data, optionally filtered by KPI Type.
    
    NEW v4.1.0: Replaces SQL-based _get_entities_by_kpi_type() with cached data lookup.
    
    Args:
        kpi_type: KPI Type to filter by (e.g., 'TERRITORY', 'VERTICAL')
                  If None, returns all entities with sales data
        
    Returns:
        DataFrame with columns: entity_id, entity_name
    """
    import streamlit as st
    from .constants import CACHE_KEY_UNIFIED
    
    try:
        cache = st.session_state.get(CACHE_KEY_UNIFIED)
        if not cache:
            return pd.DataFrame(columns=['entity_id', 'entity_name'])
        
        sales_df = cache.get('sales_raw_df', pd.DataFrame())
        if sales_df.empty or 'legal_entity_id' not in sales_df.columns:
            return pd.DataFrame(columns=['entity_id', 'entity_name'])
        
        df = sales_df
        
        # Filter by KPI Type if specified
        if kpi_type and 'kpi_type' in df.columns:
            df = df[df['kpi_type'] == kpi_type]
        
        if df.empty:
            return pd.DataFrame(columns=['entity_id', 'entity_name'])
        
        # Get unique entities
        entities = df.groupby(['legal_entity_id', 'legal_entity']).size().reset_index(name='_count')
        entities = entities.rename(columns={
            'legal_entity_id': 'entity_id',
            'legal_entity': 'entity_name'
        })[['entity_id', 'entity_name']].drop_duplicates()
        
        return entities.sort_values('entity_name').reset_index(drop=True)
        
    except Exception as e:
        logger.error(f"Error fetching entities from cache: {e}")
        return pd.DataFrame(columns=['entity_id', 'entity_name'])


# =============================================================================
# PARENT-CHILD HIERARCHY HELPER - UPDATED v4.1.0
# =============================================================================

def _expand_kpi_center_ids_with_children(kpi_center_ids: List[int]) -> List[int]:
    """
    Expand KPI Center IDs to include all children (recursive).
    
    DEPRECATED v4.1.0: This function is now a thin wrapper around cached hierarchy.
    Consider using UnifiedDataLoader.expand_kpi_center_ids_with_children() directly.
    
    UPDATED v4.1.0: Now uses cached hierarchy from UnifiedDataLoader when available,
    falling back to SQL query only if cache is not present.
    
    Args:
        kpi_center_ids: List of selected KPI Center IDs (may include parents)
        
    Returns:
        List of KPI Center IDs including all descendants
    """
    if not kpi_center_ids:
        return kpi_center_ids
    
    # Use cached hierarchy from session state (instant)
    from .constants import CACHE_KEY_UNIFIED
    
    cache = st.session_state.get(CACHE_KEY_UNIFIED)
    if cache and not cache.get('hierarchy_df', pd.DataFrame()).empty:
        hierarchy_df = cache['hierarchy_df']
        
        # Build parent-child map
        children_map = {}
        for _, row in hierarchy_df.iterrows():
            parent = row.get('parent_center_id')
            if pd.notna(parent):
                parent = int(parent)
                if parent not in children_map:
                    children_map[parent] = []
                children_map[parent].append(int(row['kpi_center_id']))
        
        # BFS to get all descendants
        expanded = set(kpi_center_ids)
        queue = list(kpi_center_ids)
        while queue:
            current = queue.pop(0)
            children = children_map.get(current, [])
            for child in children:
                if child not in expanded:
                    expanded.add(child)
                    queue.append(child)
        
        return list(expanded)
    
    # Fallback: SQL query (only if cache not available)
    logger.debug("Cache not available, falling back to SQL for hierarchy expansion")
    try:
        from utils.db import get_db_engine
        engine = get_db_engine()
        
        query = """
            WITH RECURSIVE all_centers AS (
                SELECT id AS kpi_center_id
                FROM kpi_centers 
                WHERE id IN :selected_ids
                  AND (delete_flag = 0 OR delete_flag IS NULL)
                
                UNION ALL
                
                SELECT kc.id
                FROM kpi_centers kc
                INNER JOIN all_centers ac ON kc.parent_center_id = ac.kpi_center_id
                WHERE kc.delete_flag = 0 OR kc.delete_flag IS NULL
            )
            SELECT DISTINCT kpi_center_id FROM all_centers
            ORDER BY kpi_center_id
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query), {'selected_ids': tuple(kpi_center_ids)})
            return [row[0] for row in result]
            
    except Exception as e:
        logger.error(f"Error expanding KPI Center IDs with children: {e}")
        return kpi_center_ids


# =============================================================================
# HIERARCHY DISPLAY HELPER - NEW v2.12.0
# =============================================================================

def _build_hierarchy_display_options(
    kpi_center_df: pd.DataFrame,
    kpi_type_filter: str = None
) -> Tuple[List[str], Dict[str, int], Dict[int, str]]:
    """
    Build display options for KPI Center dropdown with hierarchy visualization.
    
    Creates indented tree-like display names for KPI Centers:
    - Parent nodes: 📁 prefix
    - Children: indented with ├─ or └─
    
    Args:
        kpi_center_df: DataFrame with columns:
            - kpi_center_id
            - kpi_center_name  
            - kpi_type
            - parent_center_id (optional)
            - level (optional)
            - has_children (optional)
        kpi_type_filter: Optional KPI Type to filter by
        
    Returns:
        Tuple of:
        - options: List of display names (sorted by hierarchy)
        - display_to_id: Dict mapping display_name → kpi_center_id
        - id_to_display: Dict mapping kpi_center_id → display_name
        
    Example output:
        options = [
            '📁 ALL',
            '  📁 PTV',
            '    HAN',
            '    DAN',
            '    SGN',
            '  📁 OVERSEA',
            '    📁 SEA',
            '      PTP',
            '      ROSEA',
            '    ROW',
        ]
    """
    if kpi_center_df.empty:
        return [], {}, {}
    
    df = kpi_center_df.copy()
    
    # Filter by KPI Type if specified
    if kpi_type_filter and 'kpi_type' in df.columns:
        df = df[df['kpi_type'] == kpi_type_filter]
    
    if df.empty:
        return [], {}, {}
    
    # Check if hierarchy columns exist
    has_hierarchy = all(col in df.columns for col in ['parent_center_id', 'level', 'has_children'])
    
    if not has_hierarchy:
        # Fallback: flat list (no hierarchy info)
        options = sorted(df['kpi_center_name'].tolist())
        display_to_id = dict(zip(df['kpi_center_name'], df['kpi_center_id']))
        id_to_display = dict(zip(df['kpi_center_id'], df['kpi_center_name']))
        return options, display_to_id, id_to_display
    
    # Build hierarchy tree
    options = []
    display_to_id = {}
    id_to_display = {}
    
    # Create lookup dicts
    id_to_row = {row['kpi_center_id']: row for _, row in df.iterrows()}
    children_map = {}  # parent_id → list of children rows
    
    for _, row in df.iterrows():
        parent_id = row.get('parent_center_id')
        if pd.notna(parent_id):
            parent_id = int(parent_id)
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(row)
    
    # Sort children by name
    for parent_id in children_map:
        children_map[parent_id] = sorted(children_map[parent_id], key=lambda x: x['kpi_center_name'])
    
    def build_tree(node_id: int, indent: str = "", is_last: bool = True, is_root: bool = True):
        """Recursively build tree display."""
        if node_id not in id_to_row:
            return
        
        row = id_to_row[node_id]
        name = row['kpi_center_name']
        has_children = row.get('has_children', False)
        kpi_center_id = row['kpi_center_id']
        
        # Build display name
        if is_root:
            # Root level - no indent
            prefix = "📁 " if has_children else ""
            display_name = f"{prefix}{name}"
        else:
            # Child level - with indent
            branch = "└─ " if is_last else "├─ "
            prefix = "📁 " if has_children else ""
            display_name = f"{indent}{branch}{prefix}{name}"
        
        options.append(display_name)
        display_to_id[display_name] = kpi_center_id
        id_to_display[kpi_center_id] = display_name
        
        # Process children
        if node_id in children_map:
            children = children_map[node_id]
            for i, child_row in enumerate(children):
                child_id = child_row['kpi_center_id']
                is_last_child = (i == len(children) - 1)
                
                # Calculate new indent
                if is_root:
                    new_indent = "  "
                else:
                    extension = "   " if is_last else "│  "
                    new_indent = indent + extension
                
                build_tree(child_id, new_indent, is_last_child, is_root=False)
    
    # Find root nodes (no parent or parent not in current filtered set)
    root_nodes = []
    filtered_ids = set(df['kpi_center_id'].tolist())
    
    for _, row in df.iterrows():
        parent_id = row.get('parent_center_id')
        if pd.isna(parent_id) or int(parent_id) not in filtered_ids:
            root_nodes.append(row)
    
    # Sort root nodes by name
    root_nodes = sorted(root_nodes, key=lambda x: x['kpi_center_name'])
    
    # Build tree for each root
    for i, root_row in enumerate(root_nodes):
        is_last_root = (i == len(root_nodes) - 1)
        build_tree(root_row['kpi_center_id'], "", is_last_root, is_root=True)
    
    return options, display_to_id, id_to_display


# =============================================================================
# MULTISELECT FILTER WITH EXCLUDED OPTION
# =============================================================================

@dataclass
class FilterResult:
    """
    Result from a multiselect filter with excluded option.
    """
    selected: List[Any]
    excluded: bool
    is_active: bool
    
    def __repr__(self) -> str:
        mode = "EXCLUDE" if self.excluded else "INCLUDE"
        if not self.is_active:
            return "FilterResult(inactive)"
        return f"FilterResult({mode} {len(self.selected)} items)"


def render_multiselect_with_exclude(
    label: str,
    options: List[Any],
    default: List[Any] = None,
    key: str = None,
    help_text: str = None,
    ctx = None
) -> FilterResult:
    """
    Render a multiselect with an Exclude checkbox.
    
    Args:
        label: Label for the multiselect
        options: List of options
        default: Default selected values
        key: Unique key prefix for widgets
        help_text: Help text for multiselect
        ctx: Streamlit context (st or st.sidebar)
        
    Returns:
        FilterResult with selected items, exclude flag, and is_active flag
    """
    if ctx is None:
        ctx = st
    
    if default is None:
        default = []
    
    # Layout: Label with Exclude checkbox on right
    col1, col2 = ctx.columns([4, 1])
    
    with col1:
        ctx.markdown(f"**{label}**")
    
    with col2:
        excluded = ctx.checkbox(
            "Excl",
            value=False,
            key=f"{key}_exclude"
        )
    
    # Multiselect
    selected = ctx.multiselect(
        label=label,
        options=options,
        default=default,
        key=f"{key}_select",
        help=help_text,
        label_visibility="collapsed"
    )
    
    # Determine if filter is active
    is_active = len(selected) > 0 and selected != ['All']
    
    return FilterResult(
        selected=selected,
        excluded=excluded,
        is_active=is_active
    )


def apply_multiselect_filter(
    df: pd.DataFrame,
    column: str,
    filter_result: FilterResult
) -> pd.DataFrame:
    """
    Apply multiselect filter to DataFrame.
    
    Args:
        df: DataFrame to filter
        column: Column name to filter on
        filter_result: FilterResult from render_multiselect_with_exclude
        
    Returns:
        Filtered DataFrame
    """
    if df.empty or not filter_result.is_active:
        return df
    
    if column not in df.columns:
        return df
    
    if filter_result.excluded:
        # EXCLUDE mode: keep rows NOT in selected
        return df[~df[column].isin(filter_result.selected)]
    else:
        # INCLUDE mode: keep rows IN selected
        return df[df[column].isin(filter_result.selected)]


# =============================================================================
# TEXT SEARCH FILTER - NEW v2.13.0 (SYNCED with Salesperson)
# =============================================================================

@dataclass
class TextSearchResult:
    """Result from text search filter."""
    query: str
    excluded: bool
    is_active: bool


def render_text_search_filter(
    label: str,
    key: str,
    placeholder: str = "Search...",
    help_text: str = None,
    ctx = None
) -> TextSearchResult:
    """
    Render a text search filter with Excl option.
    
    Args:
        label: Filter label
        key: Unique widget key
        placeholder: Placeholder text
        help_text: Optional help tooltip
        ctx: Optional Streamlit context
        
    Returns:
        TextSearchResult with query, excluded flag, and is_active flag
    """
    if ctx is None:
        ctx = st
    
    # Header row
    col_label, col_excl = ctx.columns([4, 1])
    
    with col_label:
        ctx.markdown(f"**{label}**")
    
    with col_excl:
        excluded = ctx.checkbox(
            "Excl",
            value=False,
            key=f"{key}_excl"
        )
    
    # Text input
    query = ctx.text_input(
        label=label,
        placeholder=placeholder,
        key=f"{key}_input",
        help=help_text,
        label_visibility="collapsed"
    )
    
    return TextSearchResult(
        query=query.strip(),
        excluded=excluded,
        is_active=bool(query.strip())
    )


def apply_text_search_filter(
    df: pd.DataFrame,
    columns: List[str],
    search_result: TextSearchResult,
    case_sensitive: bool = False
) -> pd.DataFrame:
    """
    Apply text search filter to DataFrame (searches across multiple columns).
    
    Args:
        df: DataFrame to filter
        columns: List of column names to search in
        search_result: TextSearchResult from render_text_search_filter
        case_sensitive: Whether search is case-sensitive
        
    Returns:
        Filtered DataFrame
    """
    if df.empty or not search_result.is_active:
        return df
    
    query = search_result.query
    if not case_sensitive:
        query = query.lower()
    
    # Build combined mask across all columns
    combined_mask = pd.Series([False] * len(df), index=df.index)
    
    for column in columns:
        if column in df.columns:
            col_values = df[column].astype(str)
            if not case_sensitive:
                col_values = col_values.str.lower()
            
            mask = col_values.str.contains(query, na=False, regex=False)
            combined_mask = combined_mask | mask
    
    if search_result.excluded:
        return df[~combined_mask]
    else:
        return df[combined_mask]


# =============================================================================
# NUMBER RANGE FILTER
# =============================================================================

@dataclass
class NumberRangeResult:
    """Result from a number range filter."""
    min_value: Optional[float]
    max_value: Optional[float]
    excluded: bool
    is_active: bool


def render_number_filter_with_exclude(
    label: str,
    default_min: float = 0,
    step: float = 1000,
    key: str = None,
    help_text: str = None,
    ctx = None
) -> NumberRangeResult:
    """
    Render a number input with Exclude checkbox.
    """
    if ctx is None:
        ctx = st
    
    # Layout
    col1, col2 = ctx.columns([4, 1])
    
    with col1:
        ctx.markdown(f"**{label}**")
    
    with col2:
        excluded = ctx.checkbox(
            "Excl",
            value=False,
            key=f"{key}_exclude"
        )
    
    # Number input
    min_value = ctx.number_input(
        label=label,
        value=default_min,
        step=step,
        key=f"{key}_input",
        help=help_text,
        label_visibility="collapsed"
    )
    
    return NumberRangeResult(
        min_value=min_value if min_value > 0 else None,
        max_value=None,
        excluded=excluded,
        is_active=min_value > 0
    )


def apply_number_filter(
    df: pd.DataFrame,
    column: str,
    filter_result: NumberRangeResult
) -> pd.DataFrame:
    """
    Apply number filter to DataFrame.
    """
    if df.empty or not filter_result.is_active:
        return df
    
    if column not in df.columns:
        return df
    
    if filter_result.min_value is not None:
        if filter_result.excluded:
            # Exclude: keep rows BELOW min
            return df[df[column] < filter_result.min_value]
        else:
            # Include: keep rows AT OR ABOVE min
            return df[df[column] >= filter_result.min_value]
    
    return df


# =============================================================================
# SMART CACHING SESSION STATE
# NOTE: _get_cached_year_range() and _set_cached_year_range() REMOVED in v4.0.0
#       - Replaced by CACHE_KEY_UNIFIED in UnifiedDataLoader
# =============================================================================


def _get_applied_filters() -> Optional[Dict]:
    """Get last applied filters from session state."""
    return st.session_state.get('_kpc_applied_filters')


def _set_applied_filters(filters: Dict):
    """Store applied filters in session state."""
    st.session_state['_kpc_applied_filters'] = filters.copy()


def clear_data_cache():
    """
    Clear all cached data - called by Refresh button.
    
    UPDATED v4.0.0: Uses new unified cache keys from constants.py
    """
    from .constants import CACHE_KEY_UNIFIED, CACHE_KEY_PROCESSED, CACHE_KEY_FILTERS, CACHE_KEY_TIMING
    
    keys_to_clear = [
        # New v4.0.0 cache keys
        CACHE_KEY_UNIFIED,
        CACHE_KEY_PROCESSED,
        CACHE_KEY_FILTERS,
        CACHE_KEY_TIMING,
        # Legacy keys (for backward compatibility during transition)
        '_kpc_cached_start_year',
        '_kpc_cached_end_year',
        '_kpc_raw_cached_data',
        '_kpc_applied_filters'
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    
    # Also clear st.cache_data
    st.cache_data.clear()
    logger.info("Data cache cleared (v4.0.0 unified + legacy keys)")


# =============================================================================
# MAIN FILTER CLASS
# =============================================================================

class KPICenterFilters:
    """
    Filter UI components for KPI Center Performance page.
    
    SYNCED with Salesperson filters v2.2.0:
    - Period definitions shown in tooltip (?) next to Period label
    - Same date range logic and UI layout
    - Same period type behavior (YTD/QTD/MTD for current_year)
    - Identical tooltip text for Start/End inputs
    - Same caption note about Sales data vs Backlog
    
    UPDATED v2.12.0:
    - KPI Center dropdown now shows hierarchy with indent/prefix
    - Parent KPI Centers visible with 📁 prefix
    - Children indented with tree-like structure
    
    UPDATED v2.11.0:
    - ALL filters now in single @st.fragment (no full page rerun)
    - Entity filters by KPI Type (dynamic)
    - Date pickers: disabled for YTD/QTD/MTD, enabled for Custom
    - No more st.form - fragment handles all updates
    
    Usage:
        filters = KPICenterFilters(access)
        filter_values, submitted = filters.render_filter_form(
            kpi_center_df, entity_df, default_start, default_end
        )
    """
    
    def __init__(self, access: AccessControl):
        """Initialize with access control."""
        self.access = access
    
    def render_filter_form(
            self,
            kpi_center_df: pd.DataFrame,
            entity_df: pd.DataFrame = None,
            default_start_date: date = None,
            default_end_date: date = None,
            kpi_types_with_assignment: set = None,
        ) -> Tuple[Dict, bool]:
            """
            Render ALL filters inside a single @st.fragment.
            No full page rerun when filters change - only fragment reruns.
            
            v2.12.0 IMPROVEMENTS:
            - KPI Center dropdown now shows hierarchy with tree-like display
            - Parent KPI Centers visible with 📁 prefix
            
            v2.11.0 IMPROVEMENTS:
            - Entity dropdown now filters by KPI Type
            - Date pickers: DISABLED for YTD/QTD/MTD, ENABLED for Custom
            - All filters in fragment for instant feedback
            - Submit button sets flag to trigger main page data reload
            
            Args:
                kpi_center_df: KPI Center options (with hierarchy columns if available)
                entity_df: Entity options (fallback if _get_entities_from_cache fails)
                default_start_date: Default start date (from DB - Jan 1 of latest sales year)
                default_end_date: Default end date (from DB - max backlog ETD or today)
                kpi_types_with_assignment: Set of KPI Types that have KPI assignments
            
            Returns:
                Tuple of (filter_values dict, submitted boolean)
            """
            # Default dates if not provided
            today = date.today()
            current_year = today.year
            
            if default_start_date is None:
                default_start_date = date(current_year, 1, 1)
            if default_end_date is None:
                default_end_date = today
            
            # Pre-calculate date ranges for CURRENT YEAR
            current_quarter = (today.month - 1) // 3 + 1
            quarter_start_month = (current_quarter - 1) * 3 + 1
            
            ytd_start = date(current_year, 1, 1)
            ytd_end = today
            
            qtd_start = date(current_year, quarter_start_month, 1)
            qtd_end = today
            
            mtd_start = date(current_year, today.month, 1)
            mtd_end = today
            
            # Last Year (LY) - Full previous year
            ly_start = date(current_year - 1, 1, 1)
            ly_end = date(current_year - 1, 12, 31)
            
            with st.sidebar:
                st.header("🎯 KPI Center Filters")
                
                # Show access info at top
                self._render_access_info()
                
                st.divider()
                
                # =================================================================
                # ALL FILTERS WRAPPED IN SINGLE FRAGMENT - v2.11.0
                # Changes here only rerun fragment, not whole page
                # =================================================================
                
                @st.fragment
                def all_filters_fragment():
                    """
                    Single fragment containing ALL filter controls.
                    Values are passed to outer scope via session_state.
                    """
                    
                    # =========================================================
                    # 1. KPI TYPE FILTER
                    # =========================================================
                    kpi_type_filter_local = 'TERRITORY'
                    available_types = []
                    
                    if not kpi_center_df.empty and 'kpi_type' in kpi_center_df.columns:
                        all_types = set(kpi_center_df['kpi_type'].dropna().unique().tolist())
                        
                        if kpi_types_with_assignment:
                            available_types = sorted(all_types & kpi_types_with_assignment)
                        else:
                            available_types = sorted(all_types)
                        
                        if available_types:
                            # Initialize session state
                            if 'frag_kpi_type' not in st.session_state:
                                st.session_state.frag_kpi_type = (
                                    'TERRITORY' if 'TERRITORY' in available_types 
                                    else available_types[0]
                                )
                            
                            # Ensure current value is still valid
                            if st.session_state.frag_kpi_type not in available_types:
                                st.session_state.frag_kpi_type = available_types[0]
                            
                            selected_type = st.selectbox(
                                "KPI Type",
                                options=available_types,
                                key="frag_kpi_type",
                                help="Select KPI Type. KPI Center and Entity options update instantly."
                            )
                            
                            kpi_type_filter_local = selected_type
                    
                    # =========================================================
                    # 2. ONLY WITH KPI CHECKBOX - UPDATED v2.15.0
                    # =========================================================
                    
                    # v2.15.0: Check assignments BEFORE rendering checkbox
                    # This avoids the "cannot modify after widget instantiated" error
                    kpi_check_years_local = [current_year]
                    kpi_center_ids_with_kpi = []
                    
                    # Pre-check if there are any assignments for this type/year
                    # Only query if checkbox would be checked (default or session state)
                    should_check_assignments = st.session_state.get('frag_only_with_kpi', True)
                    
                    if should_check_assignments:
                        kpi_center_ids_with_kpi = _get_kpi_centers_with_assignments(
                            kpi_check_years_local, 
                            kpi_type=kpi_type_filter_local
                        )
                        
                        # NEW v2.15.0 (Option C): Auto-uncheck if no assignments found
                        # Must do this BEFORE checkbox is rendered
                        if not kpi_center_ids_with_kpi:
                            st.session_state.frag_only_with_kpi = False
                            st.warning(
                                f"⚠️ No KPI assignments for **{kpi_type_filter_local}** in {current_year}. "
                                f"Filter unchecked to show all KPI Centers."
                            )
                    
                    # Initialize checkbox default if not set
                    if 'frag_only_with_kpi' not in st.session_state:
                        st.session_state.frag_only_with_kpi = True
                    
                    # Now render the checkbox (session_state already set correctly)
                    only_with_kpi_local = st.checkbox(
                        "Only with KPI assignment",
                        key="frag_only_with_kpi",
                        help="Show only KPI Centers with KPI targets assigned for the selected year and type."
                    )
                    
                    # If user just checked the box, we need to query again
                    if only_with_kpi_local and not kpi_center_ids_with_kpi:
                        kpi_center_ids_with_kpi = _get_kpi_centers_with_assignments(
                            kpi_check_years_local, 
                            kpi_type=kpi_type_filter_local
                        )
                    
                    # =========================================================
                    # 3. KPI CENTER FILTER - UPDATED v5.0.0 (Single Selection)
                    # =========================================================
                    # NEW v5.0.0: Single selection with tree hierarchy
                    # Prevents parent-child double counting
                    
                    from .kpi_center_selector import render_kpi_center_selector
                    
                    filtered_kc_df = kpi_center_df.copy()
                    kpi_center_ids_local = []
                    include_children_local = True
                    
                    if not kpi_center_df.empty:
                        # Filter by KPI Type
                        if 'kpi_type' in kpi_center_df.columns and kpi_type_filter_local:
                            filtered_kc_df = filtered_kc_df[filtered_kc_df['kpi_type'] == kpi_type_filter_local]
                        
                        # Build allowed IDs set for "Only with KPI" filter
                        allowed_ids_set = None
                        if only_with_kpi_local and kpi_center_ids_with_kpi:
                            allowed_ids_set = set(kpi_center_ids_with_kpi)
                            
                            # Show info about filtered count
                            total_in_type = len(kpi_center_df[kpi_center_df['kpi_type'] == kpi_type_filter_local]) if 'kpi_type' in kpi_center_df.columns else len(kpi_center_df)
                            filtered_count = len([x for x in filtered_kc_df['kpi_center_id'] if x in allowed_ids_set])
                            hidden_count = total_in_type - filtered_count
                            
                            if hidden_count > 0:
                                st.caption(f"📋 {filtered_count} with KPI in {current_year} ({hidden_count} hidden)")
                    
                    if filtered_kc_df.empty:
                        st.warning(f"No KPI Centers for type '{kpi_type_filter_local}'")
                    else:
                        # Track previous KPI Type to detect changes and reset selection
                        prev_kpi_type = st.session_state.get('_prev_kpi_type', None)
                        
                        if prev_kpi_type != kpi_type_filter_local:
                            # KPI Type changed → reset selection
                            st.session_state._prev_kpi_type = kpi_type_filter_local
                            # Reset selector state
                            if 'kpc_sel_select' in st.session_state:
                                del st.session_state['kpc_sel_select']
                            if 'kpc_sel_include_children' in st.session_state:
                                del st.session_state['kpc_sel_include_children']
                            # Also reset Entity when KPI Type changes
                            st.session_state.frag_entity = ['All']
                        
                        # Render tree selector component
                        selection = render_kpi_center_selector(
                            hierarchy_df=filtered_kc_df,
                            kpi_type_filter=None,  # Already filtered above
                            allowed_ids=allowed_ids_set,
                            key_prefix="kpc_sel",
                            show_search=(len(filtered_kc_df) > 10)
                        )
                        
                        # Get selected IDs
                        kpi_center_ids_local = selection.expanded_ids
                        include_children_local = selection.include_children
                    
                    st.divider()
                    
                    # =========================================================
                    # 4. ENTITY FILTER (filtered by KPI Type) - UPDATED v4.1.0
                    # =========================================================
                    st.markdown("**🏢 Legal Entity**")
                    
                    entity_ids_local = []
                    
                    # Get entities for selected KPI Type from cached data
                    # UPDATED v4.1.0: Use cached sales_raw instead of SQL query
                    filtered_entity_df = _get_entities_from_cache(kpi_type_filter_local)
                    
                    # Fallback to provided entity_df if cache lookup fails
                    if filtered_entity_df.empty and entity_df is not None:
                        filtered_entity_df = entity_df.copy()
                    
                    if not filtered_entity_df.empty:
                        entity_count = len(filtered_entity_df)
                        st.caption(f"📋 {entity_count} entities with {kpi_type_filter_local} data")
                        
                        entity_options = ['All'] + filtered_entity_df['entity_name'].tolist()
                        entity_id_map = dict(zip(
                            filtered_entity_df['entity_name'],
                            filtered_entity_df['entity_id']
                        ))
                        
                        # Initialize entity selection
                        if 'frag_entity' not in st.session_state:
                            st.session_state.frag_entity = ['All']
                        
                        # Validate current selection against available options
                        current_selection = st.session_state.frag_entity
                        valid_selection = [e for e in current_selection if e in entity_options]
                        if not valid_selection:
                            valid_selection = ['All']
                        if valid_selection != current_selection:
                            st.session_state.frag_entity = valid_selection
                        
                        selected_entities = st.multiselect(
                            "Select entities",
                            options=entity_options,
                            key="frag_entity",
                            label_visibility="collapsed"
                        )
                        
                        if 'All' in selected_entities or not selected_entities:
                            entity_ids_local = []  # No filter
                        else:
                            entity_ids_local = [
                                entity_id_map[name]
                                for name in selected_entities
                                if name in entity_id_map
                            ]
                    else:
                        st.info("No entities found for selected KPI Type")
                    
                    st.divider()
                    
                    # =========================================================
                    # 5. DATE RANGE SECTION - IMPROVED v2.11.0
                    # =========================================================
                    st.markdown("**📅 Date Range**")
                    st.caption("Applies to Sales data. Backlog shows full pipeline.")
                    
                    # Period type radio
                    if 'frag_period_type' not in st.session_state:
                        st.session_state.frag_period_type = 'YTD'
                    
                    period_type_local = st.radio(
                        "Period",
                        options=['YTD', 'QTD', 'MTD', 'LY', 'Custom'],
                        key="frag_period_type",
                        horizontal=True,
                        help=(
                            f"**YTD** (Year to Date): Jan 01 → {ytd_end.strftime('%b %d, %Y')}\n\n"
                            f"**QTD** (Q{current_quarter} to Date): {qtd_start.strftime('%b %d')} → {qtd_end.strftime('%b %d, %Y')}\n\n"
                            f"**MTD** ({today.strftime('%B')} to Date): {mtd_start.strftime('%b %d')} → {mtd_end.strftime('%b %d, %Y')}\n\n"
                            f"**LY** (Last Year): {ly_start.strftime('%b %d, %Y')} → {ly_end.strftime('%b %d, %Y')}\n\n"
                            f"**Custom**: Select any date range using Start/End inputs below"
                        )
                    )
                    
                    # Determine if date pickers should be disabled
                    is_custom = (period_type_local == 'Custom')
                    
                    # Calculate display dates based on period type
                    if period_type_local == 'YTD':
                        display_start = ytd_start
                        display_end = ytd_end
                    elif period_type_local == 'QTD':
                        display_start = qtd_start
                        display_end = qtd_end
                    elif period_type_local == 'MTD':
                        display_start = mtd_start
                        display_end = mtd_end
                    elif period_type_local == 'LY':
                        display_start = ly_start
                        display_end = ly_end
                    else:  # Custom
                        # Use stored custom dates or defaults
                        display_start = st.session_state.get('frag_custom_start', default_start_date)
                        display_end = st.session_state.get('frag_custom_end', default_end_date)
                    
                    # Date inputs
                    col_start, col_end = st.columns(2)
                    
                    with col_start:
                        if is_custom:
                            # ENABLED - user can edit
                            # v5.1.0: Allow selection from MIN_DATA_YEAR
                            from .constants import MIN_DATA_YEAR
                            start_date_input = st.date_input(
                                "Start",
                                value=display_start,
                                min_value=date(MIN_DATA_YEAR, 1, 1),
                                key="frag_start_date",
                                help=f"Start date for Custom period (data available from {MIN_DATA_YEAR})"
                            )
                            # Store custom date
                            st.session_state.frag_custom_start = start_date_input
                        else:
                            # DISABLED - just show calculated date
                            st.date_input(
                                "Start",
                                value=display_start,
                                key="frag_start_date_display",
                                disabled=True,
                                help=f"Auto-calculated for {period_type_local}"
                            )
                            start_date_input = display_start
                    
                    with col_end:
                        if is_custom:
                            # ENABLED - user can edit
                            # v5.1.0: Allow selection from MIN_DATA_YEAR
                            from .constants import MIN_DATA_YEAR
                            end_date_input = st.date_input(
                                "End",
                                value=display_end,
                                min_value=date(MIN_DATA_YEAR, 1, 1),
                                key="frag_end_date",
                                help=f"End date for Custom period (data available from {MIN_DATA_YEAR})"
                            )
                            # Store custom date
                            st.session_state.frag_custom_end = end_date_input
                        else:
                            # DISABLED - just show calculated date
                            st.date_input(
                                "End",
                                value=display_end,
                                key="frag_end_date_display",
                                disabled=True,
                                help=f"Auto-calculated for {period_type_local}"
                            )
                            end_date_input = display_end
                    
                    # Final date values
                    if period_type_local == 'YTD':
                        final_start = ytd_start
                        final_end = ytd_end
                    elif period_type_local == 'QTD':
                        final_start = qtd_start
                        final_end = qtd_end
                    elif period_type_local == 'MTD':
                        final_start = mtd_start
                        final_end = mtd_end
                    elif period_type_local == 'LY':
                        final_start = ly_start
                        final_end = ly_end
                    else:  # Custom
                        final_start = start_date_input
                        final_end = end_date_input
                        # Validate
                        if final_start > final_end:
                            final_end = final_start
                            st.warning("⚠️ End date adjusted to match Start date")
                        
                        # NEW v4.1.0: Check if Custom period requires extended data loading
                        from .constants import CACHE_KEY_UNIFIED, LOOKBACK_YEARS, MIN_DATA_YEAR
                        cache = st.session_state.get(CACHE_KEY_UNIFIED)
                        
                        # Check if selected date is before MIN_DATA_YEAR (no data available)
                        if final_start.year < MIN_DATA_YEAR:
                            st.warning(
                                f"⚠️ No data available before **{MIN_DATA_YEAR}**. "
                                f"Results will start from {MIN_DATA_YEAR}-01-01."
                            )
                        elif cache:
                            cached_start = cache.get('_lookback_start')
                            if cached_start and final_start < cached_start:
                                st.info(
                                    f"📅 Selected date ({final_start.strftime('%Y-%m-%d')}) is before "
                                    f"default data range ({cached_start.strftime('%Y-%m-%d')}). "
                                    f"Click **Apply** to load extended data."
                                )
                        else:
                            # No cache yet - calculate default start
                            default_start = date(max(today.year - LOOKBACK_YEARS, MIN_DATA_YEAR), 1, 1)
                            if final_start < default_start:
                                st.info(
                                    f"📅 Selected date ({final_start.strftime('%Y-%m-%d')}) is before "
                                    f"default data range ({default_start.strftime('%Y-%m-%d')}). "
                                    f"Click **Apply** to load extended data."
                                )
                    
                    st.divider()
                    
                    # =========================================================
                    # 6. EXCLUDE INTERNAL REVENUE
                    # =========================================================
                    if 'frag_exclude_internal' not in st.session_state:
                        st.session_state.frag_exclude_internal = True
                    
                    exclude_internal_local = st.checkbox(
                        "Exclude internal revenue",
                        key="frag_exclude_internal",
                        help=(
                            "Exclude revenue from internal company transactions. "
                            "Gross Profit is kept intact for accurate GP% calculation."
                        )
                    )
                    
                    st.divider()
                    
                    # =========================================================
                    # 7. APPLY BUTTON
                    # =========================================================
                    if st.button(
                        "🔍 Apply Filters",
                        use_container_width=True,
                        type="primary",
                        key="frag_apply_btn"
                    ):
                        # Set flag to trigger main page data reload
                        st.session_state._filters_submitted = True
                        st.rerun()
                    
                    # =========================================================
                    # PASS VALUES TO OUTER SCOPE VIA SESSION STATE
                    # =========================================================
                    st.session_state._frag_kpi_type_filter = kpi_type_filter_local
                    st.session_state._frag_only_with_kpi = only_with_kpi_local
                    st.session_state._frag_kpi_center_ids = kpi_center_ids_local
                    st.session_state._frag_kpi_check_years = kpi_check_years_local
                    st.session_state._frag_entity_ids = entity_ids_local
                    st.session_state._frag_period_type = period_type_local
                    st.session_state._frag_start_date = final_start
                    st.session_state._frag_end_date = final_end
                    st.session_state._frag_exclude_internal = exclude_internal_local
                
                # Execute the fragment
                all_filters_fragment()
                
                # Read values from session_state
                kpi_type_filter = st.session_state.get('_frag_kpi_type_filter', 'TERRITORY')
                only_with_kpi = st.session_state.get('_frag_only_with_kpi', True)
                kpi_center_ids = st.session_state.get('_frag_kpi_center_ids', [])
                kpi_check_years = st.session_state.get('_frag_kpi_check_years', [current_year])
                entity_ids = st.session_state.get('_frag_entity_ids', [])
                period_type = st.session_state.get('_frag_period_type', 'YTD')
                start_date = st.session_state.get('_frag_start_date', ytd_start)
                end_date = st.session_state.get('_frag_end_date', ytd_end)
                exclude_internal = st.session_state.get('_frag_exclude_internal', True)
                
                # Check if submitted
                submitted = st.session_state.pop('_filters_submitted', False)
            
            # =================================================================
            # DETERMINE YEAR FROM DATES
            # =================================================================
            if period_type in ['YTD', 'QTD', 'MTD']:
                year = current_year
            elif period_type == 'LY':
                year = current_year - 1
            else:
                year = start_date.year
            
            # =================================================================
            # RECALCULATE kpi_check_years based on actual period
            # =================================================================
            if period_type in ['YTD', 'QTD', 'MTD']:
                kpi_check_years = [current_year]
            elif period_type == 'LY':
                kpi_check_years = [current_year - 1]
            else:
                # Custom: include all years in range
                kpi_check_years = list(range(start_date.year, end_date.year + 1))
            
            # =================================================================
            # KPI CENTER IDs - UPDATED v5.0.0
            # =================================================================
            # NEW v5.0.0: Component already handles expansion via "Include sub-centers" toggle
            # kpi_center_ids now contains expanded IDs if toggle is on
            # No need to call _expand_kpi_center_ids_with_children() again
            
            # Get include_children flag from session state (set by component)
            include_children = st.session_state.get('kpc_sel_include_children', True)
            
            # For backward compatibility:
            # - kpi_center_ids_selected: The single selected ID (for UI display)
            # - kpi_center_ids_expanded: All IDs to query (selected + children if toggled)
            # - kpi_center_ids: Same as expanded (for backward compat)
            
            if kpi_center_ids:
                # Extract single selected ID from expanded list (it's the first one that's a parent)
                # For now, use first ID as "selected" - component ensures single selection
                kpi_center_ids_selected = [kpi_center_ids[0]] if kpi_center_ids else []
            else:
                kpi_center_ids_selected = []
            
            kpi_center_ids_expanded = kpi_center_ids.copy()
            
            logger.debug(f"KPI Centers: selected={len(kpi_center_ids_selected)}, expanded={len(kpi_center_ids_expanded)}, include_children={include_children}")
            
            # Build filter values dict
            filter_values = {
                'period_type': period_type,
                'year': year,
                'start_date': start_date,
                'end_date': end_date,
                'kpi_center_ids': kpi_center_ids_expanded,
                'kpi_center_ids_selected': kpi_center_ids_selected,
                'kpi_center_ids_expanded': kpi_center_ids_expanded,
                'kpi_type_filter': kpi_type_filter,
                'entity_ids': entity_ids,
                'exclude_internal_revenue': exclude_internal,
                'show_yoy': True,
                'only_with_kpi': only_with_kpi,
                'kpi_check_years': kpi_check_years,
                'include_children': include_children,  # NEW v5.0.0
                # NEW v4.1.0: Custom start date for dynamic loading
                # Used by UnifiedDataLoader to determine if extended data range is needed
                'custom_start_date': start_date if period_type == 'Custom' else None,
            }
            
            return filter_values, submitted

    # =========================================================================
    # LEGACY METHOD - DEPRECATED v4.1.0
    # =========================================================================
    
    def render_sidebar_filters(
        self,
        kpi_center_df: pd.DataFrame,
        entity_df: pd.DataFrame = None,
        available_years: List[int] = None,
        kpi_types_with_assignment: set = None,
    ) -> Dict:
        """
        DEPRECATED v4.1.0: Use render_filter_form() directly instead.
        
        This wrapper exists for backward compatibility only.
        Will be removed in a future version.
        
        Legacy method - redirects to render_filter_form.
        """
        import warnings
        warnings.warn(
            "render_sidebar_filters() is deprecated. Use render_filter_form() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        filter_values, _ = self.render_filter_form(
            kpi_center_df=kpi_center_df,
            entity_df=entity_df,
            kpi_types_with_assignment=kpi_types_with_assignment,
        )
        filter_values['submitted'] = True
        return filter_values
    
    # =========================================================================
    # ACCESS INFO
    # =========================================================================
    
    def _render_access_info(self):
        """Display access level info in sidebar."""
        if self.access.can_access_page():
            st.caption("🔓 Full Access - All KPI Centers")
        else:
            st.error("🚫 Access Denied")
    
    # =========================================================================
    # FILTER SUMMARY
    # =========================================================================
    
    @staticmethod
    def get_filter_summary(filters: Dict) -> str:
        """Get human-readable summary of current filters."""
        parts = []
        
        # Period
        parts.append(f"{filters['period_type']} {filters['year']}")
        
        # Date range
        parts.append(
            f"({filters['start_date'].strftime('%b %d')} - "
            f"{filters['end_date'].strftime('%b %d')})"
        )
        
        # KPI Centers count
        kc_selected = len(filters.get('kpi_center_ids_selected', []))
        kc_expanded = len(filters.get('kpi_center_ids_expanded', filters.get('kpi_center_ids', [])))
        
        if kc_expanded > kc_selected:
            parts.append(f"{kc_selected} KPI Centers (+{kc_expanded - kc_selected} children)")
        elif kc_selected == 1:
            parts.append("1 KPI Center")
        elif kc_selected > 1:
            parts.append(f"{kc_selected} KPI Centers")
        
        # Internal revenue status
        if filters.get('exclude_internal_revenue', True):
            parts.append("excl. internal")
        
        return " • ".join(parts)
    
    @staticmethod
    def validate_filters(filters: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate filter values.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check date range
        if filters['start_date'] > filters['end_date']:
            return False, "Start date must be before end date"
        
        # Check KPI Center selection
        if not filters.get('kpi_center_ids'):
            return False, "Please select at least one KPI Center"
        
        # Check year range
        if filters['year'] < 2010 or filters['year'] > 2100:
            return False, "Invalid year selected"
        
        return True, None


# =============================================================================
# STANDALONE FUNCTIONS
# =============================================================================

# =============================================================================
# BACKWARD COMPATIBILITY ALIASES
# =============================================================================

# Alias for old function name used in __init__.py
render_multiselect_filter = render_multiselect_with_exclude
render_number_filter = render_number_filter_with_exclude
apply_filter_to_dataframe = apply_multiselect_filter


def analyze_period(filter_values: Dict) -> Dict:
    """
    Analyze period to determine comparison type and which sections to show.
    
    UPDATED v4.1.0: Consolidated with KPICenterMetrics.analyze_period_context().
    Now includes all fields from both functions.
    
    Returns:
        Dictionary with:
        - is_historical: End date is in the past
        - is_current: Period includes today
        - is_future: Start date is in the future
        - is_multi_year: Period spans multiple years
        - years_in_period: List of years in period
        - show_backlog: Whether to show backlog/forecast section
        - show_forecast: Whether to show forecast (same as show_backlog)
        - comparison_type: 'multi_year' or 'yoy'
        - forecast_message: Message when forecast not shown
        - today: Current date
        - days_until_end: Days from today until end_date
        - period_status: 'historical', 'current', or 'future'
    """
    today = date.today()
    start = filter_values['start_date']
    end = filter_values['end_date']
    
    # Get list of years in period
    years_in_period = list(range(start.year, end.year + 1))
    is_multi_year = len(years_in_period) > 1
    
    # Period classification (from analyze_period_context)
    is_historical = end < today
    is_future = start > today
    is_current = not is_historical and not is_future
    days_until_end = (end - today).days
    
    # Period status
    if is_historical:
        period_status = 'historical'
    elif is_future:
        period_status = 'future'
    else:
        period_status = 'current'
    
    # Only show backlog for current/future periods
    show_backlog = end >= date(today.year, today.month, 1)
    
    # Forecast message
    forecast_message = ""
    if not show_backlog:
        forecast_message = f"📅 Historical period ({end.strftime('%Y-%m-%d')}) - forecast not applicable"
    elif is_future:
        forecast_message = "📅 Future period - showing projected backlog only"
    
    return {
        # Original fields
        'is_historical': is_historical,
        'is_multi_year': is_multi_year,
        'years_in_period': years_in_period,
        'show_backlog': show_backlog,
        'show_forecast': show_backlog,
        'comparison_type': 'multi_year' if is_multi_year else 'yoy',
        'forecast_message': forecast_message,
        # Added from analyze_period_context
        'is_current': is_current,
        'is_future': is_future,
        'today': today,
        'days_until_end': days_until_end,
        'period_status': period_status,
    }


def get_backlog_period_dates(filter_values: Dict) -> tuple:
    """
    Get correct date range for In-Period Backlog calculation.
    
    NEW v5.0.1: Backlog ETD should be filtered by PERIOD BOUNDARY, not current date range.
    
    Logic:
    - Backlog = pending orders (not yet invoiced)
    - ETD = Expected delivery date (future)
    - "In-Period" = orders expected to be delivered within the KPI period
    
    Period boundaries:
    - YTD: Jan 1 → Dec 31 of selected year
    - QTD: Quarter start → Quarter end
    - MTD: Month start → Month end
    - LY: Jan 1 → Dec 31 of previous year
    - Custom: Use filter dates as-is
    
    Args:
        filter_values: Dict with period_type, year, start_date, end_date
        
    Returns:
        Tuple of (backlog_start_date, backlog_end_date)
    
    Example:
        Filter: YTD 2026, Jan 1 - Jan 27
        → Backlog Period: Jan 1, 2026 - Dec 31, 2026
        
        Filter: QTD Q1 2026, Jan 1 - Jan 27
        → Backlog Period: Jan 1, 2026 - Mar 31, 2026
    """
    import calendar
    
    period_type = filter_values.get('period_type', 'YTD')
    year = filter_values.get('year', date.today().year)
    start_date = filter_values.get('start_date', date(year, 1, 1))
    end_date = filter_values.get('end_date', date(year, 12, 31))
    
    # Start date is always the period start
    backlog_start = start_date
    
    if period_type == 'YTD':
        # Full year
        backlog_end = date(year, 12, 31)
        
    elif period_type == 'QTD':
        # End of quarter
        quarter = (start_date.month - 1) // 3 + 1
        quarter_end_month = quarter * 3
        last_day = calendar.monthrange(year, quarter_end_month)[1]
        backlog_end = date(year, quarter_end_month, last_day)
        
    elif period_type == 'MTD':
        # End of month
        last_day = calendar.monthrange(year, start_date.month)[1]
        backlog_end = date(year, start_date.month, last_day)
        
    elif period_type == 'LY':
        # Full previous year
        backlog_end = date(year, 12, 31)
        
    else:  # Custom or unknown
        # Use filter dates as-is
        backlog_end = end_date
    
    return (backlog_start, backlog_end)