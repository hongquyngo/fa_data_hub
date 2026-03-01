# utils/legal_entity_performance/filters.py
"""
Sidebar Filter Components for Legal Entity Performance
Aligned with kpi_center_performance/filters.py

VERSION: 2.2.0
CHANGELOG:
- v2.2.0: @st.fragment for sidebar → widget changes don't trigger full page rerun
           Disabled Year selection when Custom period (meaningless)
           Added analyze_period(filter_values) matching KPC signature
- v2.0.0: Initial version with PERIOD_TYPES synced with KPI center
"""

import logging
import calendar
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import streamlit as st

from .constants import PERIOD_TYPES, MONTH_ORDER, CACHE_KEY_UNIFIED, CACHE_KEY_FILTERS

logger = logging.getLogger(__name__)


# =============================================================================
# PERIOD ANALYSIS (synced with KPI center)
# =============================================================================

def _calculate_period_dates(period_type: str, year: int) -> Dict:
    """
    Calculate date range and metadata for a given period type.
    
    Returns:
        Dict with start_date, end_date, year, display_label, is_current_period
    """
    today = date.today()
    
    if period_type == 'YTD':
        start_date = date(year, 1, 1)
        end_date = min(today, date(year, 12, 31))
        label = f"YTD {year}"
    
    elif period_type == 'QTD':
        current_quarter = (today.month - 1) // 3 + 1
        quarter = current_quarter if year == today.year else 4
        start_date = date(year, (quarter - 1) * 3 + 1, 1)
        quarter_end_month = quarter * 3
        last_day = calendar.monthrange(year, quarter_end_month)[1]
        end_date = min(today, date(year, quarter_end_month, last_day))
        label = f"Q{quarter} {year}"
    
    elif period_type == 'MTD':
        month = today.month if year == today.year else 12
        start_date = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = min(today, date(year, month, last_day))
        label = f"{start_date.strftime('%b')} {year}"
    
    elif period_type == 'LY':
        ly = year - 1
        start_date = date(ly, 1, 1)
        end_date = date(ly, 12, 31)
        label = f"LY {ly}"
        year = ly
    
    else:  # Custom
        start_date = date(year, 1, 1)
        end_date = today
        label = "Custom"
    
    is_current = (year == today.year and end_date >= today)
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'year': year,
        'display_label': label,
        'is_current_period': is_current,
    }


def analyze_period(filter_values: Dict) -> Dict:
    """
    Analyze period to determine comparison type and which sections to show.
    Synced with KPC filters.py analyze_period().
    
    Returns:
        Dict with is_historical, is_current, show_backlog, show_forecast,
        comparison_type, period_status, etc.
    """
    today = date.today()
    start = filter_values['start_date']
    end = filter_values['end_date']
    
    years_in_period = list(range(start.year, end.year + 1))
    is_multi_year = len(years_in_period) > 1
    
    is_historical = end < today
    is_future = start > today
    is_current = not is_historical and not is_future
    days_until_end = (end - today).days
    
    if is_historical:
        period_status = 'historical'
    elif is_future:
        period_status = 'future'
    else:
        period_status = 'current'
    
    show_backlog = end >= date(today.year, today.month, 1)
    
    forecast_message = ""
    if not show_backlog:
        forecast_message = f"📅 Historical period ({end.strftime('%Y-%m-%d')}) - forecast not applicable"
    elif is_future:
        forecast_message = "📅 Future period - showing projected backlog only"
    
    return {
        'is_historical': is_historical,
        'is_current': is_current,
        'is_future': is_future,
        'is_multi_year': is_multi_year,
        'years_in_period': years_in_period,
        'show_backlog': show_backlog,
        'show_forecast': show_backlog,
        'comparison_type': 'multi_year' if is_multi_year else 'yoy',
        'forecast_message': forecast_message,
        'today': today,
        'days_until_end': days_until_end,
        'period_status': period_status,
    }


# =============================================================================
# SIDEBAR FRAGMENT - @st.fragment prevents full page rerun on widget change
# =============================================================================

@st.fragment
def _sidebar_filter_fragment(
    entity_df: pd.DataFrame,
    available_years: list,
):
    """
    Fragment for sidebar filters.
    
    Widget changes only rerun this fragment (not full page).
    "Apply Filters" button commits values and triggers full page rerun.
    
    NOTE: Must be called inside `with st.sidebar:` context manager.
    """
    current_year = date.today().year
    today = date.today()
    
    st.header("🏢 Legal Entity Performance")
    
    # =============================================================
    # PERIOD SELECTION
    # =============================================================
    st.subheader("📅 Period")
    
    period_type = st.selectbox(
        "Period Type",
        options=PERIOD_TYPES,
        index=0,
        key='le_period_type'
    )
    
    is_custom = (period_type == 'Custom')
    
    # Year selection - disabled when Custom (date inputs override year)
    year = st.selectbox(
        "Year",
        options=available_years if available_years else [current_year],
        index=0,
        key='le_year',
        disabled=is_custom,
        help="Disabled for Custom period — use date inputs below" if is_custom else None,
    )
    
    # Calculate date range from period_type + year
    period_info = _calculate_period_dates(period_type, year)
    start_date = period_info['start_date']
    end_date = period_info['end_date']
    effective_year = period_info['year']
    
    # Override for specific period types
    if period_type == 'QTD' and year != current_year:
        quarter = st.selectbox(
            "Quarter", options=[1, 2, 3, 4], index=3,
            key='le_quarter'
        )
        start_date = date(year, (quarter - 1) * 3 + 1, 1)
        qem = quarter * 3
        end_date = date(year, qem, calendar.monthrange(year, qem)[1])
    
    elif period_type == 'MTD' and year != current_year:
        month = st.selectbox(
            "Month", options=list(range(1, 13)),
            format_func=lambda m: date(2000, m, 1).strftime('%B'),
            index=11, key='le_month'
        )
        start_date = date(year, month, 1)
        end_date = date(year, month, calendar.monthrange(year, month)[1])
    
    elif is_custom:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "From", value=date(current_year, 1, 1), key='le_custom_start'
            )
        with col2:
            end_date = st.date_input(
                "To", value=today, key='le_custom_end'
            )
        # For Custom, effective_year comes from start_date
        effective_year = start_date.year
    
    st.caption(f"📅 {start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}")
    
    # Dynamic loading warning for Custom
    custom_start_date = None
    if is_custom:
        custom_start_date = start_date
        cache = st.session_state.get(CACHE_KEY_UNIFIED)
        if cache:
            cached_start = cache.get('_lookback_start')
            if cached_start and start_date < cached_start:
                st.warning(
                    f"⚠️ Custom period before cached range "
                    f"({start_date} < {cached_start}). "
                    f"Data will be reloaded."
                )
    
    # =============================================================
    # ENTITY SELECTION
    # =============================================================
    st.subheader("🏢 Legal Entity")
    
    entity_options = []
    entity_id_map = {}
    if not entity_df.empty:
        for _, row in entity_df.iterrows():
            name = str(row.get('legal_entity', 'Unknown'))
            eid = row.get('legal_entity_id')
            entity_options.append(name)
            entity_id_map[name] = eid
    
    selected_entities = st.multiselect(
        "Select Entities",
        options=entity_options,
        default=[],
        placeholder="All entities",
        key='le_entity_filter'
    )
    entity_ids = [entity_id_map[n] for n in selected_entities if n in entity_id_map]
    
    # =============================================================
    # CUSTOMER TYPE
    # =============================================================
    st.subheader("👤 Filters")
    
    customer_type = st.selectbox(
        "Customer Type",
        options=['All', 'External', 'Internal'],
        index=0,
        key='le_customer_type'
    )
    
    # =============================================================
    # OPTIONS
    # =============================================================
    show_yoy = st.checkbox("📊 Show YoY comparison", value=True, key='le_show_yoy')
    
    # =============================================================
    # APPLY BUTTON
    # =============================================================
    submitted = st.button(
        "🔄 Apply Filters", type="primary",
        use_container_width=True, key='le_apply_btn'
    )
    
    # Build filter values dict
    filter_values = {
        'period_type': period_type,
        'year': effective_year,
        'start_date': start_date,
        'end_date': end_date,
        'entity_ids': entity_ids,
        'customer_type': customer_type,
        'customer_ids': [],
        'product_ids': [],
        'brand_filter': [],
        'show_yoy': show_yoy,
        'submitted': submitted,
        'custom_start_date': custom_start_date,
    }
    
    # Auto-apply on first load (no applied filters exist yet)
    if CACHE_KEY_FILTERS not in st.session_state:
        st.session_state[CACHE_KEY_FILTERS] = filter_values
    
    # Apply on button click → store + full page rerun
    if submitted:
        st.session_state[CACHE_KEY_FILTERS] = filter_values
        st.rerun(scope="app")


# =============================================================================
# MAIN FILTER CLASS
# =============================================================================

class LegalEntityFilters:
    """Render and manage sidebar filters."""
    
    def __init__(self, access_control=None):
        self.access = access_control
    
    def render_sidebar_filters(
        self,
        entity_df: pd.DataFrame,
        available_years: list,
    ) -> Dict:
        """
        Render sidebar filters as a fragment.
        
        Widget changes only rerun the fragment (not the full page).
        "Apply Filters" triggers full page rerun via st.rerun(scope="app").
        
        Returns:
            Applied filter values from session state (or None if not yet applied).
        """
        with st.sidebar:
            _sidebar_filter_fragment(entity_df, available_years)
        return st.session_state.get(CACHE_KEY_FILTERS)
    
    @staticmethod
    def validate_filters(filter_values: dict) -> Tuple[bool, Optional[str]]:
        """Validate filter selections."""
        if not filter_values:
            return False, "No filters applied"
        start = filter_values.get('start_date')
        end = filter_values.get('end_date')
        if start and end and start > end:
            return False, "Start date must be before end date"
        return True, None
    
    @staticmethod
    def get_filter_summary(filters: dict) -> str:
        """Generate human-readable filter summary."""
        pt = filters.get('period_type', 'YTD')
        year = filters.get('year', '')
        
        if pt == 'Custom':
            label = (
                f"{filters['start_date'].strftime('%d %b %Y')} → "
                f"{filters['end_date'].strftime('%d %b %Y')}"
            )
        elif pt == 'LY':
            label = f"LY {year}"
        elif pt == 'QTD':
            q = (filters['start_date'].month - 1) // 3 + 1
            label = f"Q{q} {year}"
        elif pt == 'MTD':
            label = f"{filters['start_date'].strftime('%B')} {year}"
        else:
            label = f"YTD {year}"
        
        parts = [label]
        
        entity_ids = filters.get('entity_ids', [])
        parts.append(f"{len(entity_ids)} entity(ies)" if entity_ids else "All entities")
        
        ct = filters.get('customer_type', 'All')
        if ct != 'All':
            parts.append(ct)
        
        return " | ".join(parts)


# =============================================================================
# STANDALONE FUNCTIONS (backward compat)
# =============================================================================

def get_backlog_period_dates(filter_values: Dict) -> tuple:
    """
    Get correct date range for In-Period Backlog calculation.
    Synced with KPC filters.py get_backlog_period_dates().
    """
    period_type = filter_values.get('period_type', 'YTD')
    year = filter_values.get('year', date.today().year)
    start_date = filter_values.get('start_date', date(year, 1, 1))
    end_date = filter_values.get('end_date', date(year, 12, 31))
    
    backlog_start = start_date
    
    if period_type == 'YTD':
        backlog_end = date(year, 12, 31)
    elif period_type == 'QTD':
        quarter = (start_date.month - 1) // 3 + 1
        quarter_end_month = quarter * 3
        last_day = calendar.monthrange(year, quarter_end_month)[1]
        backlog_end = date(year, quarter_end_month, last_day)
    elif period_type == 'MTD':
        last_day = calendar.monthrange(year, start_date.month)[1]
        backlog_end = date(year, start_date.month, last_day)
    elif period_type == 'LY':
        backlog_end = date(year, 12, 31)
    else:  # Custom
        backlog_end = end_date
    
    return (backlog_start, backlog_end)