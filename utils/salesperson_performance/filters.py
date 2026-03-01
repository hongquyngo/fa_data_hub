# utils/salesperson_performance/filters.py
"""
Sidebar Filter Components for Salesperson Performance

Renders filter UI elements:
- Period selector (YTD/QTD/MTD/LY/Custom) with radio buttons
- Year selector
- Salesperson selector (role-based) with KPI filter option
- Entity selector
- Internal revenue filter
- YoY comparison toggle
- Metric view selector

CHANGELOG:
- v2.3.0: REFACTOR - Hybrid form approach for responsive period selection
          - Period type radio moved OUTSIDE form → UI updates immediately
          - Date inputs + other filters remain INSIDE form → apply on submit
          - Trade-off: Period change causes quick UI rerun (~0.1s) but no data reload
          - Fixes UX issue where Custom date picker wasn't visible until Apply clicked
          - Disabled date_input for non-Custom shows correct calculated dates
- v2.4.0: UPDATED - Non-blocking empty selection handling
          - Empty employee_ids no longer blocks page with st.stop()
          - validate_filters() now sets 'is_empty_selection' flag instead
          - Added get_empty_selection_reason() helper for informative messages
          - Page renders with $0 values, all tabs accessible including Setup
- v2.6.0: FIXED Excl checkbox layout wrapping on narrow columns
          - Changed column ratio from [4, 1] to [3, 1] with gap="small"
          - Gives Excl checkbox more horizontal space to prevent label wrapping
          - Applied to: render_multiselect_filter, render_text_search_filter, render_number_filter
- v2.5.0: NEW - Dynamic sidebar for Setup tab (Phase 3 & 4)
          - Added render_setup_sidebar() for Setup-specific sidebar content
          - Added get_most_recent_kpi_year() for smart year default
          - Added get_setup_quick_stats() for sidebar stats display
          - Setup tab now independent with its own filter system
- v2.2.0: FIX - KPI assignment checkbox and LY date display
          - Bug 1: "Only with KPI assignment" always used current_year instead of 
            period-specific year (e.g., LY should check 2025 KPIs, not 2026)
          - Bug 2: Date inputs didn't update when selecting LY/YTD/QTD/MTD
          - Fix: Calculate selected_year based on period_type before KPI filtering
- v2.1.0: ADDED Last Year (LY) period type
          - Quick selection for full previous year (Jan 1 - Dec 31)
          - Automatically sets year to last year
          - Useful for YoY comparison analysis
- v2.0.0: REFACTORED - All filters inside st.form to prevent rerun on every change
          - ALL widgets (period type, dates, KPI checkbox, etc.) inside form
          - Date inputs ALWAYS enabled, but only used when "Custom" is selected
          - YTD/QTD/MTD: Dates auto-calculated, inputs ignored (tooltip explains this)
          - Detailed tooltips showing exact date ranges for each period type
          - Consistent English language throughout
          - Page only reruns when "Apply Filters" is clicked
- v1.4.0: Added "Only with KPI assignment" checkbox
          - Filters salesperson dropdown to only show those with KPI targets
          - Default: checked (hide managers without KPI)
          - Supports cross-year periods (checks both years)
- v1.3.0: Added Period Type radio buttons (YTD/QTD/MTD/Custom)
          - Only Custom shows date pickers
          - YTD/QTD/MTD auto-calculate dates for current year
          - KPI targets prorate based on period_type
- v1.2.0: Added MultiSelectFilter with Excluded option
          - render_multiselect_filter(): Reusable filter component
          - apply_multiselect_filter(): Apply filter logic to DataFrame
          - FilterResult dataclass for clean return values
- v1.1.0: Added exclude_internal_revenue checkbox to filter out internal company revenue

VERSION: 2.6.0
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import streamlit as st
from sqlalchemy import text

from .constants import PERIOD_TYPES, MONTH_ORDER
from .access_control import AccessControl

logger = logging.getLogger(__name__)


# =============================================================================
# KPI ASSIGNMENT HELPER
# =============================================================================

def _get_employees_with_kpi_assignments(years: List[int]) -> List[int]:
    """
    Get list of employee IDs that have KPI assignments in given years.
    
    Standalone helper function to avoid circular imports with queries.py.
    
    Args:
        years: List of years to check (e.g., [2025] or [2024, 2025])
        
    Returns:
        List of employee_ids with KPI assignments
    """
    if not years:
        return []
    
    try:
        from utils.db import get_db_engine
        engine = get_db_engine()
        
        query = """
            SELECT DISTINCT employee_id 
            FROM sales_employee_kpi_assignments_view 
            WHERE year IN :years
            ORDER BY employee_id
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query), {'years': tuple(years)})
            return [row[0] for row in result]
            
    except Exception as e:
        logger.error(f"Error fetching employees with KPI: {e}")
        return []


# =============================================================================
# MULTISELECT FILTER WITH EXCLUDED OPTION
# =============================================================================

@dataclass
class FilterResult:
    """
    Result from a multiselect filter with excluded option.
    
    Attributes:
        selected: List of selected values (empty if "All" or nothing selected)
        excluded: True if "Excl" checkbox is ticked
        is_active: True if filter should be applied (has selections and not "All")
    """
    selected: List[Any]
    excluded: bool
    is_active: bool
    
    def __repr__(self) -> str:
        mode = "EXCLUDE" if self.excluded else "INCLUDE"
        return f"FilterResult({len(self.selected)} items, {mode}, active={self.is_active})"


def render_multiselect_filter(
    label: str,
    options: List[Any],
    key: str,
    default_excluded: bool = False,
    placeholder: str = "Select...",
    help_text: str = None,
    max_selections: int = None,
    container = None
) -> FilterResult:
    """
    Render a multiselect filter with an "Excl" (Excluded) checkbox.
    
    Layout:
    ```
    Label                    ☐ Excl
    [Multiselect dropdown with tags    ]
    ```
    
    Args:
        label: Filter label (e.g., "Customer", "Brand")
        options: List of options to choose from
        key: Unique key for Streamlit widgets
        default_excluded: Default state of Excl checkbox (False = include mode)
        placeholder: Placeholder text for empty multiselect
        help_text: Optional help tooltip
        max_selections: Optional limit on number of selections
        container: Optional Streamlit container (default: st)
        
    Returns:
        FilterResult with selected values, excluded flag, and is_active flag
        
    Example:
        >>> result = render_multiselect_filter(
        ...     label="Brand",
        ...     options=["3M", "Henkel", "Momentive"],
        ...     key="brand_filter"
        ... )
        >>> if result.is_active:
        ...     if result.excluded:
        ...         df = df[~df['brand'].isin(result.selected)]
        ...     else:
        ...         df = df[df['brand'].isin(result.selected)]
    """
    ctx = container if container else st
    
    # FIXED v2.6.0: Give more space to Excl checkbox to prevent wrapping
    # Previous layout [4, 1] caused "Excl" to wrap on narrow screens
    # New layout [3, 1]: Label takes 3 parts, Excl takes 1 part = more space for checkbox
    col_label, col_excl = ctx.columns([3, 1], gap="small")
    
    with col_label:
        ctx.markdown(f"**{label}**")
    
    with col_excl:
        excluded = ctx.checkbox(
            "Excl",
            value=default_excluded,
            key=f"{key}_excl",
            help="Tick to EXCLUDE selected items instead of filtering to them",
            label_visibility="visible"
        )
    
    # Multiselect
    selected = ctx.multiselect(
        label=label,
        options=options,
        default=[],
        key=f"{key}_select",
        placeholder=placeholder,
        help=help_text,
        max_selections=max_selections,
        label_visibility="collapsed"
    )
    
    # Determine if filter is active
    is_active = len(selected) > 0
    
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
    Apply multiselect filter to a DataFrame.
    
    Args:
        df: DataFrame to filter
        column: Column name to filter on
        filter_result: FilterResult from render_multiselect_filter
        
    Returns:
        Filtered DataFrame
        
    Example:
        >>> brand_filter = render_multiselect_filter("Brand", brands, "brand")
        >>> df = apply_multiselect_filter(df, 'brand', brand_filter)
    """
    if df.empty or not filter_result.is_active:
        return df
    
    if column not in df.columns:
        logger.warning(f"Column '{column}' not found in DataFrame")
        return df
    
    if filter_result.excluded:
        # Exclude mode: remove rows with selected values
        return df[~df[column].isin(filter_result.selected)]
    else:
        # Include mode: keep only rows with selected values
        return df[df[column].isin(filter_result.selected)]


def apply_all_filters(
    df: pd.DataFrame,
    filter_results: Dict[str, FilterResult]
) -> pd.DataFrame:
    """
    Apply multiple filters to a DataFrame.
    
    Args:
        df: DataFrame to filter
        filter_results: Dict from render_filter_row
        
    Returns:
        Filtered DataFrame
    """
    for column, result in filter_results.items():
        df = apply_multiselect_filter(df, column, result)
    return df


def get_active_filter_summary(filter_results: Dict[str, FilterResult]) -> str:
    """
    Get human-readable summary of active filters.
    
    Args:
        filter_results: Dict of filter results
        
    Returns:
        Summary string like "Brand: 3M, Henkel (excl) | Customer: VINFAST"
    """
    parts = []
    
    for column, result in filter_results.items():
        if result.is_active:
            label = column.replace('_', ' ').title()
            values = ', '.join(str(v) for v in result.selected[:3])
            if len(result.selected) > 3:
                values += f" +{len(result.selected) - 3} more"
            
            mode = " (excl)" if result.excluded else ""
            parts.append(f"{label}: {values}{mode}")
    
    return " | ".join(parts) if parts else "No filters applied"


# =============================================================================
# TEXT SEARCH FILTER
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
    container = None
) -> TextSearchResult:
    """
    Render a text search filter with Excl option.
    
    Args:
        label: Filter label
        key: Unique widget key
        placeholder: Placeholder text
        help_text: Optional help tooltip
        container: Optional Streamlit container
        
    Returns:
        TextSearchResult with query, excluded flag, and is_active flag
    """
    ctx = container if container else st
    
    # FIXED v2.6.0: Match layout with render_multiselect_filter [3, 1] for more Excl space
    col_label, col_excl = ctx.columns([3, 1], gap="small")
    
    with col_label:
        ctx.markdown(f"**{label}**")
    
    with col_excl:
        excluded = ctx.checkbox(
            "Excl",
            value=False,
            key=f"{key}_excl",
            help="Tick to EXCLUDE items matching search",
            label_visibility="visible"
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
    """Result from number range filter."""
    min_value: Optional[float]
    max_value: Optional[float]
    excluded: bool
    is_active: bool


def render_number_filter(
    label: str,
    key: str,
    default_min: float = 0,
    step: float = 1000,
    help_text: str = None,
    container = None
) -> NumberRangeResult:
    """
    Render a minimum number filter with Excl option.
    
    Args:
        label: Filter label (e.g., "Min Amount ($)")
        key: Unique widget key
        default_min: Default minimum value
        step: Step increment
        help_text: Optional help tooltip
        container: Optional Streamlit container
        
    Returns:
        NumberRangeResult
    """
    ctx = container if container else st
    
    # FIXED v2.6.0: Match layout with other filter functions [3, 1] for more Excl space
    col_label, col_excl = ctx.columns([3, 1], gap="small")
    
    with col_label:
        ctx.markdown(f"**{label}**")
    
    with col_excl:
        excluded = ctx.checkbox(
            "Excl",
            value=False,
            key=f"{key}_excl",
            help="Tick to EXCLUDE items matching this condition",
            label_visibility="visible"
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
    
    Args:
        df: DataFrame to filter
        column: Column name to filter on
        filter_result: NumberRangeResult
        
    Returns:
        Filtered DataFrame
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
# SALESPERSON FILTERS CLASS (Original - kept for backward compatibility)
# =============================================================================

class SalespersonFilters:
    """
    Sidebar filter components with role-based access control.
    
    Usage:
        access = AccessControl(user_role, employee_id)
        filters = SalespersonFilters(access)
        
        filter_values = filters.render_all_filters(
            salesperson_options_df,
            entity_options_df,
            available_years
        )
    """
    
    def __init__(self, access_control: AccessControl):
        """
        Initialize with access control.
        
        Args:
            access_control: AccessControl instance
        """
        self.access = access_control
    
    # =========================================================================
    # MAIN RENDER METHOD
    # =========================================================================
    
    def render_all_filters(
        self,
        salesperson_df: pd.DataFrame,
        entity_df: pd.DataFrame,
        available_years: List[int]
    ) -> Dict:
        """
        Render all sidebar filters and return selected values.
        
        Args:
            salesperson_df: Salesperson options (employee_id, sales_name)
            entity_df: Entity options (entity_id, entity_name)
            available_years: List of available years
            
        Returns:
            Dict with all filter values:
            {
                'period_type': str,
                'year': int,
                'start_date': date,
                'end_date': date,
                'employee_ids': List[int],
                'entity_ids': List[int],
                'compare_yoy': bool,
                'exclude_internal_revenue': bool,
                'metric_view': str
            }
        """
        st.sidebar.header("🎛️ Filters")
        
        # Period and Year
        period_type, year = self._render_period_year_selector(available_years)
        
        # Date range based on period
        start_date, end_date = self._render_date_range(period_type, year)
        
        st.sidebar.divider()
        
        # Salesperson filter (respects access control)
        employee_ids = self._render_salesperson_filter(salesperson_df)
        
        # Entity filter
        entity_ids = self._render_entity_filter(entity_df)
        
        st.sidebar.divider()
        
        # Display access info
        self._render_access_info()
        
        return {
            'period_type': period_type,
            'year': year,
            'start_date': start_date,
            'end_date': end_date,
            'employee_ids': employee_ids,
            'entity_ids': entity_ids,
            'compare_yoy': True,  # Always enabled
            'exclude_internal_revenue': True,  # Default exclude
        }
    
    def render_filter_form(
        self,
        salesperson_df: pd.DataFrame,
        entity_df: pd.DataFrame,
        default_start_date: date = None,
        default_end_date: date = None
    ) -> Tuple[Dict, bool]:
        """
        Render ALL filters inside a form - only applies when user clicks Apply.
        This prevents page reruns on every filter change.
        
        REFACTORED v2.0.0:
        - ALL filters inside st.form (no widgets outside that cause rerun)
        - YTD/QTD/MTD: Auto-calculate for current year, date inputs disabled
        - Custom: Date inputs enabled for any date range selection
        - Consistent English language throughout
        
        Args:
            salesperson_df: Salesperson options
            entity_df: Entity options  
            default_start_date: Default start date (from DB - Jan 1 of latest sales year)
            default_end_date: Default end date (from DB - max backlog ETD or today)
        
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
        
        # Pre-calculate date ranges for current year
        current_quarter = (today.month - 1) // 3 + 1
        quarter_start_month = (current_quarter - 1) * 3 + 1
        
        ytd_start = date(current_year, 1, 1)
        ytd_end = today
        
        qtd_start = date(current_year, quarter_start_month, 1)
        qtd_end = today
        
        mtd_start = date(current_year, today.month, 1)
        mtd_end = today
        
        # NEW v2.1.0: Last Year (LY) - full previous year
        last_year = current_year - 1
        ly_start = date(last_year, 1, 1)
        ly_end = date(last_year, 12, 31)
        
        with st.sidebar:
            st.header("🎛️ Filters")
            
            # =================================================================
            # HYBRID APPROACH v2.3.0:
            # - Period type OUTSIDE form → UI updates immediately when changed
            # - Date inputs + other filters INSIDE form → only apply on submit
            # 
            # Trade-off: Period change causes quick UI rerun (~0.1s) but no data reload
            # =================================================================
            
            # =============================================================
            # PERIOD TYPE - OUTSIDE FORM (immediate UI response)
            # =============================================================
            st.markdown("**📅 Date Range**")
            st.caption("Applies to Sales data. Backlog shows full pipeline.")
            
            # Build detailed tooltip with exact date ranges
            period_help = (
                f"**YTD** (Year to Date): {ytd_start.strftime('%b %d')} → {ytd_end.strftime('%b %d, %Y')}\n\n"
                f"**QTD** (Q{current_quarter} to Date): {qtd_start.strftime('%b %d')} → {qtd_end.strftime('%b %d, %Y')}\n\n"
                f"**MTD** ({today.strftime('%B')} to Date): {mtd_start.strftime('%b %d')} → {mtd_end.strftime('%b %d, %Y')}\n\n"
                f"**LY** (Last Year): {ly_start.strftime('%b %d')} → {ly_end.strftime('%b %d, %Y')}\n\n"
                f"**Custom**: Select any date range using Start/End inputs"
            )
            
            # Period type radio - OUTSIDE FORM for immediate UI update
            period_type = st.radio(
                "Period",
                options=['YTD', 'QTD', 'MTD', 'LY', 'Custom'],
                index=0,  # Default to YTD
                horizontal=True,
                key="sidebar_period_type",  # Changed key to avoid conflict
                help=period_help
            )
            
            # =============================================================
            # Determine year and dates based on period_type
            # =============================================================
            if period_type == 'YTD':
                selected_year = current_year
                display_start = ytd_start
                display_end = ytd_end
            elif period_type == 'QTD':
                selected_year = current_year
                display_start = qtd_start
                display_end = qtd_end
            elif period_type == 'MTD':
                selected_year = current_year
                display_start = mtd_start
                display_end = mtd_end
            elif period_type == 'LY':
                selected_year = last_year
                display_start = ly_start
                display_end = ly_end
            else:  # Custom
                selected_year = default_start_date.year
                display_start = default_start_date
                display_end = default_end_date
            
            # =================================================================
            # FORM: Date inputs + all other filters
            # =================================================================
            with st.form("sidebar_filter_form", border=False):
                
                # Date range display/input based on period type
                col_start, col_end = st.columns(2)
                
                if period_type == 'Custom':
                    # Custom mode: Editable date inputs
                    with col_start:
                        start_date_input = st.date_input(
                            "Start",
                            value=default_start_date,
                            key="form_start_date",
                            help="Select start date for custom period."
                        )
                    
                    with col_end:
                        end_date_input = st.date_input(
                            "End",
                            value=default_end_date,
                            key="form_end_date",
                            help="Select end date for custom period."
                        )
                else:
                    # Non-Custom: Show calculated dates (read-only)
                    start_date_input = display_start
                    end_date_input = display_end
                    
                    with col_start:
                        st.date_input(
                            "Start",
                            value=display_start,
                            key="form_start_date",
                            disabled=True,
                            help=f"Auto-calculated for {period_type}"
                        )
                    
                    with col_end:
                        st.date_input(
                            "End",
                            value=display_end,
                            key="form_end_date",
                            disabled=True,
                            help=f"Auto-calculated for {period_type}"
                        )
                
                st.divider()
                
                # =============================================================
                # KPI FILTER CHECKBOX
                # =============================================================
                only_with_kpi = st.checkbox(
                    "Only with KPI assignment",
                    value=True,
                    key="form_only_with_kpi",
                    help=(
                        f"Show only salespeople who have KPI targets assigned for {selected_year}. "
                        "Uncheck to include all salespeople (including managers without individual KPI)."
                    )
                )
                
                # FIX v2.2.0: Use selected_year based on period_type, not hardcoded current_year
                kpi_check_years = [selected_year]
                kpi_employee_ids = []
                filtered_salesperson_df = salesperson_df.copy()
                
                if only_with_kpi and not salesperson_df.empty:
                    kpi_employee_ids = _get_employees_with_kpi_assignments(kpi_check_years)
                    if kpi_employee_ids:
                        filtered_salesperson_df = salesperson_df[
                            salesperson_df['employee_id'].isin(kpi_employee_ids)
                        ]
                        excluded_count = len(salesperson_df) - len(filtered_salesperson_df)
                        if excluded_count > 0:
                            st.caption(f"📋 {len(filtered_salesperson_df)} with KPI ({excluded_count} hidden)")
                
                # =============================================================
                # SALESPERSON FILTER
                # =============================================================
                st.markdown("**👤 Salesperson**")
                
                if filtered_salesperson_df.empty:
                    employee_ids = []
                    st.warning("No salespeople available")
                else:
                    all_salespeople = filtered_salesperson_df['sales_name'].tolist()
                    id_map = dict(zip(
                        filtered_salesperson_df['sales_name'],
                        filtered_salesperson_df['employee_id']
                    ))
                    
                    access_level = self.access.get_access_level()
                    
                    if access_level == 'full':
                        options = ['All'] + all_salespeople
                        default = ['All']
                    elif access_level == 'team':
                        team_ids = self.access.get_accessible_employee_ids()
                        if only_with_kpi and kpi_employee_ids:
                            team_ids = [tid for tid in team_ids if tid in kpi_employee_ids]
                        team_names = filtered_salesperson_df[
                            filtered_salesperson_df['employee_id'].isin(team_ids)
                        ]['sales_name'].tolist()
                        options = ['All Team'] + team_names
                        default = ['All Team']
                    else:  # self access
                        my_id = self.access.employee_id
                        my_row = filtered_salesperson_df[
                            filtered_salesperson_df['employee_id'] == my_id
                        ]
                        if not my_row.empty:
                            options = [my_row.iloc[0]['sales_name']]
                            default = options
                        else:
                            options = all_salespeople[:1] if all_salespeople else []
                            default = options
                    
                    selected_names = st.multiselect(
                        "Select salespeople",
                        options=options,
                        default=default,
                        key="form_salesperson",
                        label_visibility="collapsed"
                    )
                    
                    # Convert to IDs
                    if 'All' in selected_names:
                        employee_ids = list(id_map.values())
                    elif 'All Team' in selected_names:
                        team_ids = self.access.get_accessible_employee_ids()
                        if only_with_kpi and kpi_employee_ids:
                            employee_ids = [tid for tid in team_ids if tid in kpi_employee_ids]
                        else:
                            employee_ids = team_ids
                    else:
                        employee_ids = [id_map[name] for name in selected_names if name in id_map]
                
                st.divider()
                
                # =============================================================
                # ENTITY FILTER
                # =============================================================
                st.markdown("**🏢 Legal Entity**")
                
                if entity_df.empty:
                    entity_ids = []
                else:
                    entity_options = ['All'] + entity_df['entity_name'].tolist()
                    entity_id_map = dict(zip(
                        entity_df['entity_name'],
                        entity_df['entity_id']
                    ))
                    
                    selected_entities = st.multiselect(
                        "Select entities",
                        options=entity_options,
                        default=['All'],
                        key="form_entity",
                        label_visibility="collapsed"
                    )
                    
                    if 'All' in selected_entities or not selected_entities:
                        entity_ids = []  # No filter
                    else:
                        entity_ids = [
                            entity_id_map[name]
                            for name in selected_entities
                            if name in entity_id_map
                        ]
                
                st.divider()
                
                # =============================================================
                # EXCLUDE INTERNAL REVENUE
                # =============================================================
                exclude_internal = st.checkbox(
                    "Exclude internal revenue",
                    value=True,
                    key="form_exclude_internal",
                    help=(
                        "Exclude revenue from internal company transactions. "
                        "Gross Profit is kept intact for accurate GP% calculation."
                    )
                )
                
                st.divider()
                
                # =============================================================
                # SUBMIT BUTTON
                # =============================================================
                submitted = st.form_submit_button(
                    "🔍 Apply Filters",
                    use_container_width=True,
                    type="primary"
                )
            
            # Show access info outside form (static, no interaction needed)
            self._render_access_info()
        
        # =================================================================
        # DETERMINE ACTUAL DATES BASED ON PERIOD TYPE
        # =================================================================
        if period_type == 'YTD':
            start_date = ytd_start
            end_date = ytd_end
            year = current_year
        elif period_type == 'QTD':
            start_date = qtd_start
            end_date = qtd_end
            year = current_year
        elif period_type == 'MTD':
            start_date = mtd_start
            end_date = mtd_end
            year = current_year
        elif period_type == 'LY':
            # NEW v2.1.0: Last Year - full previous year
            start_date = ly_start
            end_date = ly_end
            year = last_year
        else:  # Custom
            start_date = start_date_input
            end_date = end_date_input
            # Validation
            if start_date > end_date:
                end_date = start_date
            # Use start_date's year for KPI matching
            year = start_date.year
        
        # Build filter values dict
        # UPDATED v2.4.0: Added _only_with_kpi_checked for empty state messaging
        filter_values = {
            'period_type': period_type,
            'year': year,
            'start_date': start_date,
            'end_date': end_date,
            'employee_ids': employee_ids,
            'entity_ids': entity_ids,
            'compare_yoy': True,
            'exclude_internal_revenue': exclude_internal,
            'only_with_kpi': only_with_kpi,
            '_only_with_kpi_checked': only_with_kpi,  # For empty state reason detection
            '_kpi_employee_count': len(kpi_employee_ids) if only_with_kpi else None,
            '_total_salesperson_count': len(salesperson_df) if not salesperson_df.empty else 0,
        }
        
        return filter_values, submitted
    
    def _infer_period_type(self, start_date: date, end_date: date, year: int) -> str:
        """Infer period type from date range."""
        today = date.today()
        
        # Check if YTD
        if start_date == date(year, 1, 1):
            if end_date >= today or end_date == date(year, 12, 31):
                return 'YTD'
        
        # Check if QTD
        quarter_starts = [date(year, 1, 1), date(year, 4, 1), date(year, 7, 1), date(year, 10, 1)]
        if start_date in quarter_starts:
            return 'QTD'
        
        # Check if MTD
        if start_date.day == 1 and start_date.month == end_date.month:
            return 'MTD'
        
        return 'Custom'
    
    # =========================================================================
    # PERIOD & DATE SELECTORS
    # =========================================================================
    
    def _render_period_year_selector(
        self,
        available_years: List[int]
    ) -> Tuple[str, int]:
        """Render period type and year selectors."""
        col1, col2 = st.sidebar.columns(2)
        
        with col1:
            period_type = st.selectbox(
                "📅 Period",
                options=PERIOD_TYPES,
                index=0,
                key="filter_period"
            )
        
        with col2:
            current_year = datetime.now().year
            if not available_years:
                available_years = [current_year, current_year - 1]
            
            year = st.selectbox(
                "📆 Year",
                options=sorted(available_years, reverse=True),
                index=0,
                key="filter_year"
            )
        
        return period_type, int(year)
    
    def _render_date_range(
        self,
        period_type: str,
        year: int
    ) -> Tuple[date, date]:
        """Calculate and optionally render custom date range."""
        start_date, end_date = self._calculate_period_dates(period_type, year)
        
        if period_type == 'Custom':
            col1, col2 = st.sidebar.columns(2)
            with col1:
                start_date = st.date_input(
                    "Start Date",
                    value=start_date,
                    key="filter_start_date"
                )
            with col2:
                end_date = st.date_input(
                    "End Date",
                    value=end_date,
                    key="filter_end_date"
                )
        else:
            # Show calculated range as info
            st.sidebar.caption(
                f"📅 {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
            )
        
        return start_date, end_date
    
    @staticmethod
    def _calculate_period_dates(period_type: str, year: int) -> Tuple[date, date]:
        """Calculate start and end dates for period type."""
        today = date.today()
        year = int(year)
        
        if period_type == 'YTD':
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        elif period_type == 'QTD':
            current_quarter = (today.month - 1) // 3 + 1
            quarter_start_month = (current_quarter - 1) * 3 + 1
            start = date(year, quarter_start_month, 1)
            end = min(today, date(year, 12, 31))
        
        elif period_type == 'MTD':
            start = date(year, today.month, 1)
            end = today
        
        elif period_type == 'LY':
            # Last Year - full previous year
            last_year = today.year - 1
            start = date(last_year, 1, 1)
            end = date(last_year, 12, 31)
        
        else:  # Custom
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        return start, end
    
    # =========================================================================
    # SALESPERSON FILTER
    # =========================================================================
    
    def _render_salesperson_filter(
        self,
        salesperson_df: pd.DataFrame
    ) -> List[int]:
        """Render salesperson filter based on access level."""
        if salesperson_df.empty:
            st.sidebar.warning("No salespeople available")
            return []
        
        access_level = self.access.get_access_level()
        
        # Build options based on access level
        all_salespeople = salesperson_df['sales_name'].tolist()
        id_map = dict(zip(
            salesperson_df['sales_name'],
            salesperson_df['employee_id']
        ))
        
        if access_level == 'full':
            options = ['All'] + all_salespeople
            default = ['All']
            label = "👤 Salesperson"
        
        elif access_level == 'team':
            # Filter to team members only
            team_ids = self.access.get_accessible_employee_ids()
            team_names = salesperson_df[
                salesperson_df['employee_id'].isin(team_ids)
            ]['sales_name'].tolist()
            
            options = ['All Team'] + team_names
            default = ['All Team']
            label = "👥 Team Member"
        
        else:
            # Self only
            my_id = self.access.employee_id
            my_row = salesperson_df[salesperson_df['employee_id'] == my_id]
            
            if not my_row.empty:
                my_name = my_row.iloc[0]['sales_name']
                return [my_id]  # No selection needed
            else:
                return []
        
        # Render multiselect
        selected = st.sidebar.multiselect(
            label,
            options=options,
            default=default,
            key="filter_salesperson"
        )
        
        # Convert to IDs
        if 'All' in selected:
            return list(id_map.values())
        elif 'All Team' in selected:
            return self.access.get_accessible_employee_ids()
        else:
            return [id_map[name] for name in selected if name in id_map]
    
    # =========================================================================
    # ENTITY FILTER
    # =========================================================================
    
    def _render_entity_filter(
        self,
        entity_df: pd.DataFrame
    ) -> List[int]:
        """Render entity (legal entity) filter."""
        if entity_df.empty:
            return []
        
        options = ['All Entities'] + entity_df['entity_name'].tolist()
        id_map = dict(zip(
            entity_df['entity_name'],
            entity_df['entity_id']
        ))
        
        selected = st.sidebar.multiselect(
            "🏢 Legal Entity",
            options=options,
            default=['All Entities'],
            key="filter_entity"
        )
        
        if 'All Entities' in selected or not selected:
            return []  # No filter - return empty list to indicate "all"
        
        return [id_map[name] for name in selected if name in id_map]
    
    # =========================================================================
    # ACCESS INFO
    # =========================================================================
    
    def _render_access_info(self):
        """Display access level info in sidebar."""
        access_level = self.access.get_access_level()
        team_size = self.access.get_team_size()
        
        # Icon and label based on access level
        if access_level == 'full':
            icon = "🔓"
            label = "Full Access"
        elif access_level == 'team':
            icon = "👥"
            label = f"Team Access ({team_size} members)"
        else:
            icon = "👤"
            label = "Personal View"
        
        st.sidebar.caption(f"{icon} {label}")
    

    # =========================================================================
    # FILTER STATE HELPERS
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
        
        # Salespeople count
        emp_count = len(filters.get('employee_ids', []))
        if emp_count == 1:
            parts.append("1 salesperson")
        elif emp_count > 1:
            parts.append(f"{emp_count} salespeople")
        
        # Internal revenue status (NEW)
        if filters.get('exclude_internal_revenue', True):
            parts.append("excl. internal")
        
        return " • ".join(parts)
    
    @staticmethod
    def validate_filters(filters: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate filter values.
        
        UPDATED v2.4.0: Empty employee_ids no longer blocks page.
        Instead, sets 'is_empty_selection' flag and allows graceful empty state.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check date range
        if filters['start_date'] > filters['end_date']:
            return False, "Start date must be before end date"
        
        # Check year range (reasonable bounds)
        if filters['year'] < 2010 or filters['year'] > 2100:
            return False, "Invalid year selected"
        
        # UPDATED v2.4.0: Empty employee selection is now allowed
        # Set flag instead of returning error - page will show empty state
        if not filters.get('employee_ids'):
            filters['is_empty_selection'] = True
        else:
            filters['is_empty_selection'] = False
        
        return True, None
    
    @staticmethod
    def get_empty_selection_reason(filters: Dict) -> Dict:
        """
        Get detailed reason for empty selection to display helpful message.
        
        NEW v2.4.0: Provides context for why no salespeople are available.
        
        Returns:
            Dict with reason info:
            {
                'reason': str,
                'details': List[str],
                'suggestions': List[str]
            }
        """
        reasons = {
            'reason': 'No salespeople match current filters',
            'details': [],
            'suggestions': []
        }
        
        # Check if KPI filter is the cause
        if filters.get('_only_with_kpi_checked', False):
            year = filters.get('year', date.today().year)
            reasons['details'].append(
                f'"Only with KPI assignment" is checked for year {year}'
            )
            reasons['suggestions'].append(
                'Uncheck "Only with KPI assignment" to see all salespeople'
            )
            reasons['suggestions'].append(
                f'Go to Setup tab → KPI Assignments to create {year} targets'
            )
        
        return reasons


# =============================================================================
# STANDALONE FILTER FUNCTIONS
# =============================================================================

def analyze_period(filter_values: Dict) -> Dict:
    """
    Analyze period to determine comparison type and which sections to show.
    
    Args:
        filter_values: Dict containing start_date, end_date, year
        
    Returns:
        Dict with:
        - is_historical: True if end_date < today
        - is_multi_year: True if period spans more than 1 year
        - years_in_period: List of years covered [2023, 2024, 2025]
        - show_backlog: True if backlog section should be shown
        - comparison_type: 'yoy' or 'multi_year'
    """
    today = date.today()
    start = filter_values['start_date']
    end = filter_values['end_date']
    
    # Get list of years in period
    years_in_period = list(range(start.year, end.year + 1))
    is_multi_year = len(years_in_period) > 1
    
    # Historical = end date is in the past
    is_historical = end < today
    
    # Only show backlog for current/future periods
    # Allow if end_date is within current month or future
    show_backlog = end >= date(today.year, today.month, 1)
    
    return {
        'is_historical': is_historical,
        'is_multi_year': is_multi_year,
        'years_in_period': years_in_period,
        'show_backlog': show_backlog,
        'comparison_type': 'multi_year' if is_multi_year else 'yoy',
    }


# =============================================================================
# SETUP TAB SIDEBAR (NEW v2.4.0 - Phase 3)
# =============================================================================

def render_setup_sidebar(access_level: str, accessible_count: int, editable_count: int):
    """
    Render Setup-specific sidebar content when Setup tab is active.
    
    NEW v2.4.0: Dynamic sidebar for Setup tab showing:
    - Access level badge
    - Scope information
    - Quick stats
    - Info message about inline filters
    
    Args:
        access_level: 'full', 'team', or 'self'
        accessible_count: Number of salespeople user can view
        editable_count: Number of salespeople user can edit
    """
    with st.sidebar:
        st.header("⚙️ Setup Mode")
        
        # Access level badge
        if access_level == 'full':
            st.success("🔓 **Full Access** (Admin)")
        elif access_level == 'team':
            st.info(f"👥 **Team Access** ({accessible_count} members)")
        else:
            st.warning("👤 **Personal View** (Read-only)")
        
        st.divider()
        
        # Scope information
        st.markdown("**📊 Your Scope:**")
        st.markdown(f"- **View**: {accessible_count if accessible_count else 'All'} salespeople")
        st.markdown(f"- **Edit**: {editable_count if editable_count else 'All'} salespeople")
        
        st.divider()
        
        # Info message
        st.info(
            """
            ℹ️ **Setup tab has its own filter system.**
            
            Use the inline filters within each sub-tab for data filtering.
            
            Sidebar filters (Period, KPI assignment, etc.) apply to other tabs only.
            """
        )
        
        st.divider()
        
        # Quick stats placeholder - will be populated by setup tab
        if 'setup_quick_stats' in st.session_state:
            stats = st.session_state['setup_quick_stats']
            st.markdown("**📈 Quick Stats:**")
            
            if 'split_rules_count' in stats:
                st.markdown(f"- Split Rules: {stats['split_rules_count']}")
            if 'kpi_current_year_count' in stats:
                year = stats.get('kpi_year', date.today().year)
                count = stats['kpi_current_year_count']
                if count == 0:
                    st.markdown(f"- KPI {year}: **0** ⚠️")
                else:
                    st.markdown(f"- KPI {year}: {count}")
            if 'active_salespeople_count' in stats:
                st.markdown(f"- Active Salespeople: {stats['active_salespeople_count']}")


def get_most_recent_kpi_year() -> int:
    """
    Get the most recent year that has KPI assignment data.
    
    NEW v2.4.0 (Phase 4): Used to set default year in Setup tab.
    Falls back to current year if no data found.
    
    Returns:
        Year with most recent KPI data, or current year if none
    """
    try:
        from utils.db import get_db_engine
        engine = get_db_engine()
        
        query = """
            SELECT MAX(year) as max_year
            FROM sales_employee_kpi_assignments
            WHERE delete_flag = 0
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query))
            row = result.fetchone()
            
            if row and row[0]:
                return int(row[0])
            else:
                return date.today().year
                
    except Exception as e:
        logger.error(f"Error fetching most recent KPI year: {e}")
        return date.today().year


def get_setup_quick_stats(year: int = None) -> Dict:
    """
    Get quick statistics for Setup sidebar display.
    
    NEW v2.4.0 (Phase 3): Provides overview stats for Setup tab.
    
    Args:
        year: Year to check KPI assignments (default: current year)
        
    Returns:
        Dict with counts for display
    """
    if year is None:
        year = date.today().year
    
    stats = {
        'kpi_year': year,
        'split_rules_count': 0,
        'kpi_current_year_count': 0,
        'active_salespeople_count': 0,
    }
    
    try:
        from utils.db import get_db_engine
        engine = get_db_engine()
        
        with engine.connect() as conn:
            # Count split rules
            result = conn.execute(text("""
                SELECT COUNT(*) FROM sales_split_by_customer_product
                WHERE (delete_flag = 0 OR delete_flag IS NULL)
            """))
            stats['split_rules_count'] = result.fetchone()[0] or 0
            
            # Count KPI assignments for specified year
            result = conn.execute(text("""
                SELECT COUNT(*) FROM sales_employee_kpi_assignments
                WHERE year = :year AND (delete_flag = 0 OR delete_flag IS NULL)
            """), {'year': year})
            stats['kpi_current_year_count'] = result.fetchone()[0] or 0
            
            # Count active salespeople with sales data
            result = conn.execute(text("""
                SELECT COUNT(DISTINCT sales_id) 
                FROM unified_sales_by_salesperson_view
                WHERE sales_id IS NOT NULL
            """))
            stats['active_salespeople_count'] = result.fetchone()[0] or 0
            
    except Exception as e:
        logger.error(f"Error fetching setup quick stats: {e}")
    
    return stats