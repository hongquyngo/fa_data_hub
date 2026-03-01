# pages/1_👤_Salesperson_Performance.py
"""
👤 Salesperson Performance Dashboard (Tabbed Version)

5 Tabs:
1. Overview - KPI summary, charts, trends
2. Sales Detail - Transaction list, pivot analysis
3. Backlog - Backlog detail, ETD analysis, risk
4. KPI & Targets - KPI assignments, progress, ranking
5. Setup - Sales split

"""

import streamlit as st
from datetime import datetime, date
import logging
import pandas as pd
import time
from contextlib import contextmanager
from functools import wraps

from utils.salesperson_performance.setup import setup_tab_fragment

# =============================================================================
# DEBUG TIMING UTILITIES
# =============================================================================

# Set to True to enable timing output
DEBUG_TIMING = True

_timing_log = []

@contextmanager
def timer(label: str, print_immediately: bool = True):
    """Context manager for timing code blocks."""
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    msg = f"⏱️ [{label}] {elapsed:.3f}s"
    _timing_log.append((label, elapsed))
    if DEBUG_TIMING and print_immediately:
        print(msg)

def timing_decorator(label: str = None):
    """Decorator for timing functions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_label = label or func.__name__
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            msg = f"⏱️ [{func_label}] {elapsed:.3f}s"
            _timing_log.append((func_label, elapsed))
            if DEBUG_TIMING:
                print(msg)
            return result
        return wrapper
    return decorator

def print_timing_summary():
    """Print summary of all timing measurements."""
    if not DEBUG_TIMING or not _timing_log:
        return
    print("\n" + "="*60)
    print("📊 TIMING SUMMARY")
    print("="*60)
    total = sum(t[1] for t in _timing_log)
    for label, elapsed in sorted(_timing_log, key=lambda x: -x[1]):
        pct = (elapsed / total * 100) if total > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"{label:40} {elapsed:7.3f}s ({pct:5.1f}%) {bar}")
    print("-"*60)
    print(f"{'TOTAL':40} {total:7.3f}s")
    print("="*60 + "\n")

def reset_timing():
    """Reset timing log for new page load."""
    global _timing_log
    _timing_log = []

# Shared utilities
from utils.auth import AuthManager
from utils.db import check_db_connection

# Page-specific module
from utils.salesperson_performance import (
    AccessControl,
    SalespersonQueries,
    SalespersonMetrics,
    SalespersonFilters,
    SalespersonCharts,
    MONTH_ORDER
)

# NEW v3.0.0: Pandas-based Complex KPI Calculator
from utils.salesperson_performance.complex_kpi_calculator import (
    ComplexKPICalculator,
    calculate_lookback_start,
)

# NEW v3.2.0: Dynamic KPI type weights from database
from utils.salesperson_performance.queries import get_kpi_type_weights_cached

from utils.salesperson_performance.fragments import (
    monthly_trend_fragment,
    yoy_comparison_fragment,
    sales_detail_fragment,
    pivot_analysis_fragment,
    backlog_list_fragment,
    export_report_fragment,
    backlog_by_etd_fragment,
    team_ranking_fragment,
    kpi_progress_fragment,
    # NEW v3.4.0: Combined fragments with filters above sub-tabs
    sales_detail_tab_fragment,
    backlog_tab_fragment,
)
from utils.salesperson_performance.filters import (
    analyze_period,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean dataframe to avoid Arrow serialization errors.
    Fixes mixed type columns (especially year columns from SQL DATE_FORMAT).
    """
    if df.empty:
        return df
    
    df_clean = df.copy()
    
    # Columns that should be numeric but might be strings from SQL DATE_FORMAT
    year_columns = ['etd_year', 'oc_year', 'invoice_year', 'year']
    numeric_columns = ['days_until_etd', 'days_since_order', 'split_rate_percent', 'split_percentage']
    
    for col in year_columns:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0).astype(int)
    
    for col in numeric_columns:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    
    # Fix object columns with mixed types (but preserve dates)
    for col in df_clean.columns:
        if df_clean[col].dtype == 'object':
            # Skip date-like columns
            if any(x in col.lower() for x in ['date', '_at', 'etd', 'due']):
                continue
            
            # Check if this column has truly mixed types
            unique_types = set(type(x).__name__ for x in df_clean[col].dropna().head(100))
            if len(unique_types) > 1 and 'str' in unique_types:
                try:
                    df_clean[col] = df_clean[col].astype(str).replace('nan', '').replace('None', '')
                except:
                    pass
    
    return df_clean


def _prepare_backlog_by_month_from_detail(backlog_detail_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate backlog_detail to backlog_by_month format.
    
    ADDED v2.5.0: Fix for Backlog by ETD not filtering by selected salesperson.
    
    The original backlog_by_month query aggregates across ALL accessible employees
    and has no sales_id column, so it cannot be filtered client-side.
    
    This function aggregates from backlog_detail which:
    - Has sales_id column
    - Is properly filtered by filter_data_client_side()
    - Respects selected salesperson filter
    
    Args:
        backlog_detail_df: Filtered backlog detail data
        
    Returns:
        DataFrame with columns: etd_year, etd_month, backlog_revenue, backlog_gp, order_count
    """
    if backlog_detail_df.empty:
        return pd.DataFrame(columns=['etd_year', 'etd_month', 'backlog_revenue', 'backlog_gp', 'order_count'])
    
    df = backlog_detail_df.copy()
    
    # Convert ETD to datetime
    df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
    
    # Filter out null ETDs
    df = df[df['etd'].notna()]
    
    if df.empty:
        return pd.DataFrame(columns=['etd_year', 'etd_month', 'backlog_revenue', 'backlog_gp', 'order_count'])
    
    # Extract year and month
    df['etd_year'] = df['etd'].dt.year.astype(int)
    df['etd_month'] = df['etd'].dt.strftime('%b')  # Jan, Feb, etc.
    
    # Aggregate by year and month
    result = df.groupby(['etd_year', 'etd_month']).agg({
        'backlog_sales_by_split_usd': 'sum',
        'backlog_gp_by_split_usd': 'sum',
        'oc_number': 'nunique'
    }).reset_index()
    
    result.columns = ['etd_year', 'etd_month', 'backlog_revenue', 'backlog_gp', 'order_count']
    
    # Sort by year and month order
    month_order = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                   'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
    result['_month_num'] = result['etd_month'].map(month_order)
    result = result.sort_values(['etd_year', '_month_num'])
    result = result.drop('_month_num', axis=1).reset_index(drop=True)
    
    logger.debug(f"Prepared backlog_by_month from detail: {len(result)} rows")
    
    return result

# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Salesperson Performance",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# AUTHENTICATION CHECK
# =============================================================================

auth = AuthManager()

if not auth.check_session():
    st.warning("⚠️ Please login to access this page")
    st.info("Go to the main page to login")
    st.stop()

# =============================================================================
# DATABASE CONNECTION CHECK
# =============================================================================

db_connected, db_error = check_db_connection()

if not db_connected:
    st.error(f"❌ Database connection failed: {db_error}")
    st.info("Please check your network connection or VPN")
    st.stop()

# =============================================================================
# INITIALIZE COMPONENTS
# =============================================================================

# OPTIMIZATION v2.6.0: Cache AccessControl accessible_ids in session_state
user_role = st.session_state.get('user_role', 'viewer')
employee_id = st.session_state.get('employee_id')
access_cache_key = f"_access_control_{user_role}_{employee_id}"

access = AccessControl(user_role=user_role, employee_id=employee_id)

# Cache or reuse accessible IDs
if access_cache_key not in st.session_state:
    _ac_ids = access.get_accessible_employee_ids()
    st.session_state[access_cache_key] = {
        'level': access.get_access_level(),
        'ids': _ac_ids
    }
    if DEBUG_TIMING:
        print(f"   ✅ AccessControl IDs cached: {access.get_access_level()}, {len(_ac_ids) if _ac_ids else 'all'} employees")
else:
    # Inject cached IDs to avoid DB query
    access._accessible_ids = st.session_state[access_cache_key]['ids']
    if DEBUG_TIMING:
        _ac_level = st.session_state[access_cache_key]['level']
        _ac_ids = st.session_state[access_cache_key]['ids']
        print(f"   ♻️ Using cached AccessControl: {_ac_level}, {len(_ac_ids) if _ac_ids else 'all'} employees")

queries = SalespersonQueries(access)
filters_ui = SalespersonFilters(access)

# =============================================================================
# SIDEBAR FILTERS (Form-based - only applies on click)
# OPTIMIZED v3.1.0: Extract options from lookback data instead of SQL queries
# =============================================================================

# Import sidebar options extractor
from utils.salesperson_performance.sidebar_options_extractor import SidebarOptionsExtractor

def _get_cached_sidebar_options():
    """
    Get sidebar options with session_state caching.
    
    OPTIMIZED v3.1.0: Extract from lookback_sales_data instead of 3 SQL queries
    - Before: 3 SQL queries = 7.33s
    - After: 1 SQL query + Pandas extraction = ~2.8s + ~0.01s
    - Savings: 4.5s on first load (subsequent loads still use cache)
    """
    cache_key = f"sidebar_options_{st.session_state.get('employee_id', 0)}"
    
    if cache_key not in st.session_state:
        # Load lookback data for sidebar options extraction
        # This is the same data we'll use for Complex KPIs later
        with timer("Sidebar: load_lookback_for_options"):
            lookback_df = queries.get_lookback_sales_data(
                end_date=date.today(),
                lookback_years=5
            )
        
        # Store lookback data for reuse in data loading phase
        st.session_state['_sidebar_lookback_df'] = lookback_df
        
        # Extract sidebar options from loaded data (instant - ~0.01s)
        with timer("Sidebar: extract_options_from_lookback"):
            extractor = SidebarOptionsExtractor(lookback_df)
            accessible_ids = access.get_accessible_employee_ids()
            
            salesperson_opts = extractor.extract_salesperson_options(accessible_ids)
            entity_opts = extractor.extract_entity_options()
            default_start, default_end = extractor.extract_date_range()
        
        st.session_state[cache_key] = {
            'salesperson': salesperson_opts,
            'entity': entity_opts,
            'default_start': default_start,
            'default_end': default_end,
            'cached_at': datetime.now()
        }
        if DEBUG_TIMING:
            print(f"   ✅ Sidebar options extracted from lookback data for employee_id={st.session_state.get('employee_id')}")
    else:
        if DEBUG_TIMING:
            cached_at = st.session_state[cache_key].get('cached_at', 'unknown')
            print(f"   ♻️ Using cached sidebar options (cached at: {cached_at})")
    
    return st.session_state[cache_key]

sidebar_cache = _get_cached_sidebar_options()
salesperson_options = sidebar_cache['salesperson']
entity_options = sidebar_cache['entity']
default_start = sidebar_cache['default_start']
default_end = sidebar_cache['default_end']

# Use form-based filters to prevent rerun on every change
filter_values, filters_submitted = filters_ui.render_filter_form(
    salesperson_df=salesperson_options,
    entity_df=entity_options,
    default_start_date=default_start,
    default_end_date=default_end
)

is_valid, error_msg = filters_ui.validate_filters(filter_values)
if not is_valid:
    st.error(f"⚠️ {error_msg}")
    st.stop()

# =============================================================================
# EMPTY SELECTION HANDLING (NEW v2.4.0 - Non-blocking)
# =============================================================================

is_empty_selection = filter_values.get('is_empty_selection', False)

if is_empty_selection:
    # Log for debugging
    logger.info(f"Empty selection detected: only_with_kpi={filter_values.get('_only_with_kpi_checked')}, year={filter_values.get('year')}")

# =============================================================================
# LOAD ALL DATA WITH SMART CACHING (Client-Side Filtering)
# =============================================================================

def load_data_for_year_range(start_year: int, end_year: int, exclude_internal: bool = True) -> dict:
    """
    Load data for specified year range based on user's access control.
    
    REFACTORED v2.1.0:
    - Accepts start_year and end_year parameters instead of hardcoded 3 years
    - Supports smart caching: only reload when year range expands
    
    UPDATED v1.8.0: Added exclude_internal parameter for Complex KPIs
    
    OPTIMIZED v2.0:
    - Full access (admin/GM/MD): Load all data
    - Team access (sales_manager): Load only team members' data
    - Self access (sales): Load only own data
    
    This significantly reduces load time for non-admin users.
    """
    print(f"\n{'='*60}")
    print(f"🚀 STARTING DATA LOAD: {start_year}-{end_year}")
    print(f"{'='*60}")
    load_start_time = time.perf_counter()
    
    # OPTIMIZATION v2.6.0: Cache AccessControl accessible_ids in session_state
    # This avoids expensive recursive CTE query on every page load
    user_role = st.session_state.get('user_role', 'viewer')
    employee_id = st.session_state.get('employee_id')
    access_cache_key = f"_access_control_{user_role}_{employee_id}"
    
    if access_cache_key in st.session_state:
        access_level = st.session_state[access_cache_key]['level']
        accessible_ids = st.session_state[access_cache_key]['ids']
        if DEBUG_TIMING:
            print(f"   ♻️ Using cached AccessControl ({access_level}, {len(accessible_ids) if accessible_ids else 'all'} employees)")
    else:
        with timer("AccessControl.init"):
            access_control = AccessControl(user_role, employee_id)
        
        with timer("AccessControl.get_accessible_ids"):
            access_level = access_control.get_access_level()
            accessible_ids = access_control.get_accessible_employee_ids()
        
        st.session_state[access_cache_key] = {
            'level': access_level,
            'ids': accessible_ids
        }
    
    # Create AccessControl with cached IDs (no DB query needed)
    access_control = AccessControl(user_role, employee_id)
    access_control._accessible_ids = accessible_ids  # Inject cached IDs
    
    # For full access, pass None to load all (more efficient than huge IN clause)
    # For restricted access, pass the specific IDs
    if access_level == 'full':
        filter_employee_ids = None  # Load all
        load_msg = "all salespeople"
    else:
        filter_employee_ids = accessible_ids if accessible_ids else None
        if access_level == 'team':
            load_msg = f"team ({len(accessible_ids)} members)"
        else:
            load_msg = "your data only"
    
    q = SalespersonQueries(access_control)
    
    # Use provided year range
    start_date = date(start_year, 1, 1)
    end_date = date(end_year, 12, 31)
    
    # Progress bar with status
    progress_bar = st.progress(0, text=f"🔄 Loading {load_msg} ({start_year}-{end_year})...")
    
    data = {}
    
    try:
        # =====================================================================
        # PHASE 1: Sequential - Sales data & KPI targets (needed first)
        # =====================================================================
        progress_bar.progress(10, text=f"📊 Loading sales data ({load_msg})...")
        with timer("DB: get_sales_data"):
            data['sales'] = q.get_sales_data(
                start_date=start_date,
                end_date=end_date,
                employee_ids=filter_employee_ids,
                entity_ids=None
            )
        print(f"   → Sales rows: {len(data['sales']):,}")
        
        progress_bar.progress(20, text="🎯 Loading KPI targets...")
        with timer("DB: get_kpi_targets (all years)"):
            targets_list = []
            for yr in range(start_year, end_year + 1):
                t = q.get_kpi_targets(year=yr, employee_ids=filter_employee_ids)
                if not t.empty:
                    targets_list.append(t)
            data['targets'] = pd.concat(targets_list, ignore_index=True) if targets_list else pd.DataFrame()
        print(f"   → Targets rows: {len(data['targets']):,}")
        
        # =====================================================================
        # PHASE 1.5: KPI Type Weights (for Overall Achievement calculation)
        # NEW v3.2.0: Dynamic loading from database
        # =====================================================================
        with timer("DB: get_kpi_type_weights"):
            data['kpi_type_weights'] = get_kpi_type_weights_cached()
        print(f"   → KPI type weights: {len(data['kpi_type_weights'])} types")
        
        # =====================================================================
        # PHASE 2: Complex KPIs - Using Pandas Calculator (v3.0.0)
        # Single SQL query + in-memory processing
        # Performance: 14.76s → ~3.0s (80% faster)
        # OPTIMIZED v3.1.0: Reuse lookback_df from sidebar options if available
        # =====================================================================
        progress_bar.progress(30, text="🆕 Loading lookback data for Complex KPIs...")
        
        # Check if lookback data was already loaded for sidebar options
        if '_sidebar_lookback_df' in st.session_state and st.session_state['_sidebar_lookback_df'] is not None:
            lookback_df = st.session_state['_sidebar_lookback_df']
            if DEBUG_TIMING:
                print(f"   ♻️ Reusing lookback data from sidebar ({len(lookback_df):,} rows)")
            # Clear the temporary storage to free memory
            # (we'll store it in data['_lookback_df'] instead)
            del st.session_state['_sidebar_lookback_df']
        else:
            # Load lookback data (5 years) - single query, NO employee filter
            # Complex KPIs need GLOBAL first dates (first to COMPANY, not to salesperson)
            with timer("DB: get_lookback_sales_data"):
                lookback_df = q.get_lookback_sales_data(end_date, lookback_years=5)
            print(f"   → Lookback data rows: {len(lookback_df):,}")
        
        # Store raw lookback data for later recalculation if exclude_internal changes
        data['_lookback_df'] = lookback_df
        
        # Create calculator and compute all Complex KPIs
        progress_bar.progress(40, text="📊 Calculating Complex KPIs (Pandas)...")
        with timer("Pandas: ComplexKPICalculator"):
            complex_kpi_calc = ComplexKPICalculator(lookback_df, exclude_internal=exclude_internal)
            complex_kpis_result = complex_kpi_calc.calculate_all(
                start_date=start_date,
                end_date=end_date,
                employee_ids=filter_employee_ids
            )
        
        # Unpack results (maintain same data structure as before)
        data['new_customers'] = complex_kpis_result['new_customers']
        data['new_products'] = complex_kpis_result['new_products']
        data['new_combos_detail'] = complex_kpis_result['new_combos_detail']  # NEW v1.1.0
        data['new_business'] = complex_kpis_result['new_business']
        data['new_business_detail'] = complex_kpis_result['new_business_detail']
        
        # Store calculator for instant recalculation on filter changes
        data['_complex_kpi_calculator'] = complex_kpi_calc
        
        print(f"   → New customers: {len(data['new_customers']):,} rows")
        print(f"   → New products: {len(data['new_products']):,} rows")
        print(f"   → New combos detail: {len(data['new_combos_detail']):,} rows")  # NEW v1.1.0
        print(f"   → New business: {len(data['new_business']):,} rows")
        print(f"   → New business detail: {len(data['new_business_detail']):,} rows")
        
        # =====================================================================
        # PHASE 3: Backlog data - FILTERED by access control
        # =====================================================================
        progress_bar.progress(60, text="📦 Loading backlog data...")
        
        with timer("DB: get_backlog_data (total)"):
            data['total_backlog'] = q.get_backlog_data(
                employee_ids=filter_employee_ids,
                entity_ids=None
            )
        print(f"   → Total backlog rows: {len(data['total_backlog']):,}")
        
        with timer("DB: get_backlog_in_period"):
            data['in_period_backlog'] = q.get_backlog_in_period(
                start_date=start_date,
                end_date=end_date,
                employee_ids=filter_employee_ids,
                entity_ids=None
            )
        print(f"   → In-period backlog rows: {len(data['in_period_backlog']):,}")
        
        with timer("DB: get_backlog_by_month"):
            data['backlog_by_month'] = q.get_backlog_by_month(
                employee_ids=filter_employee_ids,
                entity_ids=None
            )
        print(f"   → Backlog by month rows: {len(data['backlog_by_month']):,}")
        
        # Backlog detail - FILTERED by access control
        # UPDATED v2.2.0: Removed limit to get ALL backlog records for accurate totals
        progress_bar.progress(80, text="📋 Loading backlog details...")
        with timer("DB: get_backlog_detail"):
            data['backlog_detail'] = q.get_backlog_detail(
                employee_ids=filter_employee_ids,
                entity_ids=None
            )
        print(f"   → Backlog detail rows: {len(data['backlog_detail']):,}")
        
        # =====================================================================
        # PHASE 4: Sequential - Sales split data
        # =====================================================================
        progress_bar.progress(90, text="👥 Loading sales split data...")
        with timer("DB: get_sales_split_data"):
            data['sales_split'] = q.get_sales_split_data(employee_ids=filter_employee_ids)
        print(f"   → Sales split rows: {len(data['sales_split']):,}")
        
        # Step 7: Clean all dataframes
        with timer("Clean dataframes"):
            for key in data:
                if isinstance(data[key], pd.DataFrame) and not data[key].empty:
                    data[key] = _clean_dataframe_for_display(data[key])
        
        # Store metadata
        data['_loaded_at'] = datetime.now()
        data['_access_level'] = access_level
        data['_accessible_ids'] = accessible_ids
        data['_year_range'] = (start_year, end_year)
        
        # Complete
        progress_bar.progress(100, text="✅ Data loaded successfully!")
        
        # Print load summary
        total_load_time = time.perf_counter() - load_start_time
        print(f"\n{'='*60}")
        print(f"✅ DATA LOAD COMPLETE: {total_load_time:.2f}s total")
        print(f"{'='*60}\n")
        
    except Exception as e:
        progress_bar.empty()
        st.error(f"❌ Error loading data: {str(e)}")
        logger.exception("Error loading data")
        st.stop()
    
    finally:
        # Clear progress bar after short delay
        time.sleep(0.3)
        progress_bar.empty()
    
    return data


def filter_data_client_side(raw_data: dict, filter_values: dict) -> dict:
    """
    Filter cached data client-side based on ALL filters.
    This is instant - no DB query needed.
    
    UPDATED v1.1.0: Added exclude_internal_revenue handling
    - Uses customer_type column from unified_sales_by_salesperson_view
    - When True: Sets revenue to 0 for Internal customers, keeps GP intact
    - Purpose: Evaluate sales performance with real (external) customers only
    
    UPDATED v1.8.0: Extended exclude_internal_revenue to backlog data
    - Backlog detail still shows internal orders (for display)
    - Backlog aggregates (total_backlog, in_period_backlog) zero internal revenue
    
    UPDATED v2.4.0: Handle empty employee_ids (is_empty_selection)
    - When employee_ids is empty list [], return empty DataFrames
    - Allows page to render with $0 values instead of blocking
    """
    filter_start = time.perf_counter()
    if DEBUG_TIMING:
        print(f"\n🔍 CLIENT-SIDE FILTERING...")
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    employee_ids = filter_values['employee_ids']
    entity_ids = filter_values['entity_ids']
    year = filter_values['year']
    exclude_internal_revenue = filter_values.get('exclude_internal_revenue', True)  # NEW
    is_empty_selection = filter_values.get('is_empty_selection', False)  # NEW v2.4.0
    
    filtered = {}
    
    # NEW v2.4.0: If empty selection, return empty DataFrames for data tables
    # This allows page to render with $0 values instead of blocking
    if is_empty_selection:
        if DEBUG_TIMING:
            print(f"   ⚠️ Empty selection - returning empty DataFrames")
        for key, df in raw_data.items():
            if key.startswith('_'):
                continue
            if isinstance(df, pd.DataFrame):
                # Return empty DataFrame with same structure
                filtered[key] = df.head(0)
            else:
                filtered[key] = df
        return filtered
    
    # FIXED v2.11.0: Backlog data should NOT be filtered by date range
    # Backlog represents ALL pending orders - date range only applies to Sales data
    # In-Period backlog is calculated separately using ETD field in metrics.py
    backlog_keys = {'total_backlog', 'in_period_backlog', 'backlog_by_month', 'backlog_detail'}
    
    for key, df in raw_data.items():
        # Skip metadata
        if key.startswith('_'):
            continue
            
        if not isinstance(df, pd.DataFrame) or df.empty:
            filtered[key] = df
            continue
        
        df_filtered = df.copy()
        
        # FIXED v2.11.0: Skip date filtering for backlog data
        # Backlog is future orders - should not be filtered by invoice/OC date range
        if key not in backlog_keys:
            # Filter by date range - only for sales and complex KPI data
            date_cols = [
                'inv_date',              # sales data
                'first_invoice_date',    # new_customers
                'first_sale_date',       # new_products
                'first_combo_date',      # new_business_detail
            ]
            for date_col in date_cols:
                if date_col in df_filtered.columns:
                    df_filtered[date_col] = pd.to_datetime(df_filtered[date_col], errors='coerce')
                    df_filtered = df_filtered[
                        (df_filtered[date_col] >= pd.Timestamp(start_date)) & 
                        (df_filtered[date_col] <= pd.Timestamp(end_date))
                    ]
                    break
        
        # Filter by employee_ids (salesperson)
        if employee_ids:
            emp_ids_set = set(employee_ids)
            if 'sales_id' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['sales_id'].isin(emp_ids_set)]
            elif 'employee_id' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['employee_id'].isin(emp_ids_set)]
        
        # Filter by entity_ids
        if entity_ids:
            entity_ids_set = set(entity_ids)
            if 'entity_id' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['entity_id'].isin(entity_ids_set)]
            elif 'legal_entity_id' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['legal_entity_id'].isin(entity_ids_set)]
        
        # Special handling for targets - filter by year
        if key == 'targets' and 'year' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['year'] == year]
        
        # =====================================================================
        # NEW: Exclude Internal Revenue (but keep GP)
        # Uses customer_type column from unified_sales_by_salesperson_view
        # customer_type = 'Internal' for internal companies
        # =====================================================================
        if exclude_internal_revenue and key == 'sales':
            if 'customer_type' in df_filtered.columns and 'sales_by_split_usd' in df_filtered.columns:
                # Create mask for internal customers
                is_internal = df_filtered['customer_type'].str.lower() == 'internal'
                
                # Log for debugging
                internal_count = is_internal.sum()
                if internal_count > 0:
                    internal_revenue = df_filtered.loc[is_internal, 'sales_by_split_usd'].sum()
                    logger.info(
                        f"Excluding internal revenue: {internal_count} rows, "
                        f"${internal_revenue:,.0f} revenue zeroed (GP kept intact)"
                    )
                
                # Zero out ONLY revenue for internal customers
                # GP columns (gross_profit_by_split_usd, gp1_by_split_usd) are kept intact
                # This allows evaluation of sales performance with real customers
                df_filtered.loc[is_internal, 'sales_by_split_usd'] = 0
        
        # =====================================================================
        # NEW v1.8.0: Exclude Internal Revenue from Backlog (for Pipeline & Forecast)
        # Backlog detail shows all orders (including internal) for display
        # But aggregates (total_backlog, in_period_backlog) exclude internal revenue
        # =====================================================================
        if exclude_internal_revenue and key == 'backlog_detail':
            if 'customer_type' in df_filtered.columns and 'backlog_sales_by_split_usd' in df_filtered.columns:
                # Create mask for internal customers
                is_internal = df_filtered['customer_type'].str.lower() == 'internal'
                
                # Log for debugging
                internal_count = is_internal.sum()
                if internal_count > 0:
                    internal_backlog = df_filtered.loc[is_internal, 'backlog_sales_by_split_usd'].sum()
                    logger.info(
                        f"Excluding internal backlog revenue: {internal_count} rows, "
                        f"${internal_backlog:,.0f} backlog revenue zeroed (GP kept intact)"
                    )
                
                # Zero out ONLY revenue for internal customers
                # GP columns (backlog_gp_by_split_usd) are kept intact
                df_filtered.loc[is_internal, 'backlog_sales_by_split_usd'] = 0
        
        filtered[key] = df_filtered
    
    # =========================================================================
    # NEW v3.0.0: Recalculate Complex KPIs with Pandas when filters change
    # This is instant (<0.3s) since data is already in memory
    # =========================================================================
    if '_complex_kpi_calculator' in raw_data and raw_data['_complex_kpi_calculator'] is not None:
        calc = raw_data['_complex_kpi_calculator']
        
        with timer("Pandas: Recalculate Complex KPIs"):
            # Recalculate with current filters (employee_ids)
            complex_kpis_result = calc.calculate_all(
                start_date=start_date,
                end_date=end_date,
                employee_ids=employee_ids if employee_ids else None
            )
        
        # Update filtered data with recalculated Complex KPIs
        filtered['new_customers'] = complex_kpis_result['new_customers']
        filtered['new_products'] = complex_kpis_result['new_products']
        filtered['new_combos_detail'] = complex_kpis_result['new_combos_detail']  # NEW v1.1.0
        filtered['new_business'] = complex_kpis_result['new_business']
        filtered['new_business_detail'] = complex_kpis_result['new_business_detail']
    
    # Print timing
    filter_elapsed = time.perf_counter() - filter_start
    if DEBUG_TIMING:
        print(f"⏱️ [Client-side filter] {filter_elapsed:.3f}s")
        for key, df in filtered.items():
            if isinstance(df, pd.DataFrame):
                print(f"   → {key}: {len(df):,} rows")
    
    return filtered

# =============================================================================
# SMART CACHING LOGIC - Only reload when year range expands
# =============================================================================

def _get_applied_filters():
    """Get currently applied filters from session state."""
    return st.session_state.get('_applied_filters')


def _set_applied_filters(filters: dict):
    """Store applied filters in session state."""
    st.session_state['_applied_filters'] = filters.copy()


def _get_cached_year_range():
    """Get the year range of currently cached data."""
    return (
        st.session_state.get('_cached_start_year'),
        st.session_state.get('_cached_end_year')
    )


def _set_cached_year_range(start_year: int, end_year: int):
    """Store the year range of cached data."""
    st.session_state['_cached_start_year'] = start_year
    st.session_state['_cached_end_year'] = end_year


def _needs_data_reload(filter_values: dict) -> bool:
    """
    Check if we need to reload data from database.
    
    Returns True if:
    - No cached data exists
    - Requested year range expands beyond cached range
    
    UPDATED v1.8.0: exclude_internal is handled separately for Complex KPIs only
    """
    if 'raw_cached_data' not in st.session_state or st.session_state.raw_cached_data is None:
        return True
    
    cached_start, cached_end = _get_cached_year_range()
    if cached_start is None or cached_end is None:
        return True
    
    required_start = filter_values['start_date'].year
    required_end = filter_values['end_date'].year
    
    # Need reload if requested range expands beyond cached range
    return required_start < cached_start or required_end > cached_end


def _needs_complex_kpi_reload(filter_values: dict) -> bool:
    """
    Check if we need to recreate Complex KPI calculator.
    
    UPDATED v3.0.0: Uses Pandas calculator instead of SQL queries.
    Only need to recreate when exclude_internal changes.
    
    Returns True if:
    - No cached calculator exists
    - exclude_internal value changed (need to rebuild with different filter)
    """
    # Check if calculator exists
    if 'raw_cached_data' not in st.session_state or st.session_state.raw_cached_data is None:
        return True
    
    raw_data = st.session_state.raw_cached_data
    if '_complex_kpi_calculator' not in raw_data or raw_data['_complex_kpi_calculator'] is None:
        return True
    
    # Check if exclude_internal changed
    cached_exclude_internal = st.session_state.get('_cached_exclude_internal')
    current_exclude_internal = filter_values.get('exclude_internal_revenue', True)
    
    if cached_exclude_internal is None:
        return True
    
    return cached_exclude_internal != current_exclude_internal


def _reload_complex_kpis(filter_values: dict):
    """
    Recreate Complex KPI calculator when exclude_internal changes.
    
    UPDATED v3.0.0: Uses Pandas calculator instead of SQL queries.
    Much faster - only rebuilds the calculator with new exclude_internal setting.
    """
    if 'raw_cached_data' not in st.session_state or st.session_state.raw_cached_data is None:
        logger.warning("No raw_cached_data for Complex KPI reload")
        return
    
    raw_data = st.session_state.raw_cached_data
    
    # Check if we have lookback data
    if '_lookback_df' not in raw_data or raw_data['_lookback_df'] is None:
        logger.warning("No lookback data for Complex KPI recalculation")
        return
    
    lookback_df = raw_data['_lookback_df']
    exclude_internal = filter_values.get('exclude_internal_revenue', True)
    
    logger.info(f"Recreating ComplexKPICalculator with exclude_internal={exclude_internal}")
    
    # Recreate calculator with new exclude_internal setting
    with timer("Pandas: Recreate ComplexKPICalculator"):
        calc = ComplexKPICalculator(lookback_df, exclude_internal=exclude_internal)
    
    # Store updated calculator
    raw_data['_complex_kpi_calculator'] = calc
    
    # Recalculate for current filters
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    employee_ids = filter_values.get('employee_ids')
    
    result = calc.calculate_all(start_date, end_date, employee_ids)
    
    # Update cached data
    raw_data['new_customers'] = result['new_customers']
    raw_data['new_products'] = result['new_products']
    raw_data['new_business'] = result['new_business']
    raw_data['new_business_detail'] = result['new_business_detail']
    
    # Update cache flag
    st.session_state['_cached_exclude_internal'] = exclude_internal
    
    logger.info(f"Complex KPIs recalculated: {result['summary']}")


def get_or_load_data(filter_values: dict) -> dict:
    """
    Smart data loading with session-based caching.
    Only reloads if requested year range expands beyond cached range.
    
    UPDATED v1.8.0: Also handles Complex KPIs reload when exclude_internal changes
    
    Args:
        filter_values: Current filter values
        
    Returns:
        Raw data dict (not yet filtered by current filters)
    """
    required_start = filter_values['start_date'].year
    required_end = filter_values['end_date'].year
    exclude_internal = filter_values.get('exclude_internal_revenue', True)
    
    cached_start, cached_end = _get_cached_year_range()
    
    # Check if we need to expand the cached range
    if _needs_data_reload(filter_values):
        # Calculate expanded range
        if cached_start is not None and cached_end is not None:
            # Expand existing range
            new_start = min(required_start, cached_start)
            new_end = max(required_end, cached_end)
        else:
            # First load - use default 3 years from current year
            current_year = date.today().year
            new_start = min(required_start, current_year - 2)
            new_end = max(required_end, current_year)
        
        # Load data for expanded range (with exclude_internal for Complex KPIs)
        data = load_data_for_year_range(new_start, new_end, exclude_internal)
        
        # Cache data and year range
        st.session_state.raw_cached_data = data
        _set_cached_year_range(new_start, new_end)
        
        # Store current exclude_internal value
        st.session_state['_cached_exclude_internal'] = exclude_internal
        
        return data
    
    # Check if Complex KPIs need reload due to exclude_internal change
    if _needs_complex_kpi_reload(filter_values):
        _reload_complex_kpis(filter_values)
    
    return st.session_state.raw_cached_data


# Initialize applied filters on first load
if _get_applied_filters() is None:
    _set_applied_filters(filter_values)
    filters_submitted = True  # Force initial load

# Update applied filters when form is submitted
if filters_submitted:
    _set_applied_filters(filter_values)
    logger.info(f"Filters applied: {filter_values['period_type']} {filter_values['year']}")
    
    # OPTIMIZATION v2.6.0: Clear computed caches when filters change
    # This ensures fresh calculations for new filter values
    # UPDATED v2.6.1: Removed new_business_detail_ - now cached in raw_cached_data
    cache_prefixes = (
        'complex_kpi_',        # Main page complex KPI cache
        '_complex_kpi_',       # queries.py internal cache
        'prev_year_data_',     # YoY comparison cache
        'yoy_frag_prev_',      # Fragment YoY cache
    )
    keys_to_clear = [k for k in st.session_state.keys() 
                    if k.startswith(cache_prefixes)]
    for key in keys_to_clear:
        del st.session_state[key]
    if DEBUG_TIMING and keys_to_clear:
        print(f"   🗑️ Cleared {len(keys_to_clear)} computed caches due to filter change")

# Always use applied filters (not current form values)
# This ensures data stays consistent even if form values change without submit
active_filters = _get_applied_filters()

# Add Refresh button in sidebar
with st.sidebar:
    st.divider()
    col_r1, col_r2 = st.columns([1, 1])
    with col_r1:
        if st.button("🔄 Refresh", use_container_width=True, help="Reload data from database"):
            # Clear all cached data
            st.session_state.raw_cached_data = None
            if '_cached_start_year' in st.session_state:
                del st.session_state['_cached_start_year']
            if '_cached_end_year' in st.session_state:
                del st.session_state['_cached_end_year']
            if '_cached_exclude_internal' in st.session_state:
                del st.session_state['_cached_exclude_internal']
            
            # OPTIMIZATION v2.6.0: Also clear sidebar cache and computed caches
            employee_id = st.session_state.get('employee_id', 0)
            user_role = st.session_state.get('user_role', 'viewer')
            sidebar_cache_key = f"sidebar_options_{employee_id}"
            access_cache_key = f"_access_control_{user_role}_{employee_id}"
            
            if sidebar_cache_key in st.session_state:
                del st.session_state[sidebar_cache_key]
            if access_cache_key in st.session_state:
                del st.session_state[access_cache_key]
            
            # Clear all computed caches
            # UPDATED v2.6.1: Removed new_business_detail_ - now in raw_cached_data
            cache_prefixes = ('complex_kpi_', '_complex_kpi_', 'prev_year_data_', 
                            'yoy_frag_prev_')
            for key in list(st.session_state.keys()):
                if key.startswith(cache_prefixes):
                    del st.session_state[key]
            
            st.rerun()
    with col_r2:
        cached_start, cached_end = _get_cached_year_range()
        if cached_start and cached_end:
            st.caption(f"📦 {cached_start}-{cached_end}")
    
    # =========================================================================
    # SETUP QUICK STATS (NEW v2.4.0 - Phase 3)
    # Shows Setup tab stats if available (populated when Setup tab renders)
    # =========================================================================
    if 'setup_quick_stats' in st.session_state:
        with st.expander("⚙️ Setup Quick Stats", expanded=False):
            stats = st.session_state['setup_quick_stats']
            
            # KPI Year with warning if 0
            kpi_year = stats.get('kpi_year', date.today().year)
            kpi_count = stats.get('kpi_current_year_count', 0)
            
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.metric("📋 Split Rules", stats.get('split_rules_count', 0))
            with col_s2:
                if kpi_count == 0:
                    st.metric(f"🎯 KPI {kpi_year}", "0 ⚠️", help="No KPI assignments for this year")
                else:
                    st.metric(f"🎯 KPI {kpi_year}", kpi_count)
            
            # Show issues if any
            split_critical = stats.get('split_critical', 0)
            assign_critical = stats.get('assign_critical', 0)
            
            if split_critical > 0 or assign_critical > 0:
                st.warning(f"Issues: {split_critical} split, {assign_critical} KPI")
            
            st.caption("Go to **⚙️ Setup** tab to manage")
    
    # Show hint when empty selection due to KPI filter
    if is_empty_selection and filter_values.get('_only_with_kpi_checked'):
        st.warning(
            f"💡 **Tip**: No KPI for {filter_values.get('year', date.today().year)}. "
            f"Go to **⚙️ Setup** tab to create targets."
        )
    
# Load data with smart caching
raw_data = get_or_load_data(active_filters)

# =============================================================================
# APPLY CLIENT-SIDE FILTERING (Instant - no DB query)
# =============================================================================

data = filter_data_client_side(
    raw_data=raw_data,
    filter_values=active_filters
)

# =============================================================================
# EMPTY DATA HANDLING (UPDATED v2.4.0 - Non-blocking)
# =============================================================================

# Check if we have empty data (could be due to empty employee selection or just no matching data)
has_empty_data = data['sales'].empty and data['total_backlog'].empty

# Prepare empty state info for display
empty_state_info = None
if has_empty_data or active_filters.get('is_empty_selection', False):
    empty_state_info = {
        'has_empty_data': has_empty_data,
        'is_empty_selection': active_filters.get('is_empty_selection', False),
        'year': active_filters.get('year'),
        'only_with_kpi': active_filters.get('_only_with_kpi_checked', False),
        'kpi_employee_count': active_filters.get('_kpi_employee_count', 0),
        'total_salesperson_count': active_filters.get('_total_salesperson_count', 0),
    }

# =============================================================================
# CALCULATE METRICS
# =============================================================================

if DEBUG_TIMING:
    print(f"\n📈 CALCULATING METRICS...")

with timer("Metrics: SalespersonMetrics init"):
    metrics_calc = SalespersonMetrics(data['sales'], data['targets'])

with timer("Metrics: calculate_overview_metrics"):
    overview_metrics = metrics_calc.calculate_overview_metrics(
        period_type=active_filters['period_type'],
        year=active_filters['year']
    )

# Complex KPIs are now calculated by ComplexKPICalculator (v3.0.0)
# Data is already available in cached data from Pandas processing
fresh_new_business_df = data.get('new_business', pd.DataFrame())
fresh_new_business_detail_df = data.get('new_business_detail', pd.DataFrame())
if DEBUG_TIMING:
    print(f"   ♻️ Using cached new_business data ({len(fresh_new_business_df)} rows)")
    print(f"   ♻️ Using cached new_business_detail ({len(fresh_new_business_detail_df)} rows)")

# NEW v1.1.0: Get new_combos_detail for New Combos metric
fresh_new_combos_detail_df = data.get('new_combos_detail', pd.DataFrame())
if DEBUG_TIMING:
    print(f"   ♻️ Using cached new_combos_detail ({len(fresh_new_combos_detail_df)} rows)")

with timer("Metrics: calculate_complex_kpis"):
    complex_kpis = metrics_calc.calculate_complex_kpis(
        new_customers_df=data['new_customers'],
        new_products_df=data['new_products'],
        new_business_df=fresh_new_business_df,  # Use fresh data instead of cached
        new_combos_detail_df=fresh_new_combos_detail_df  # NEW v1.1.0
    )

with timer("Metrics: calculate_backlog_metrics"):
    backlog_metrics = metrics_calc.calculate_backlog_metrics(
        total_backlog_df=data['total_backlog'],
        in_period_backlog_df=data['in_period_backlog'],
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date']
    )

# NEW v2.5.0: Calculate Pipeline & Forecast with KPI-filtered logic
# This ensures each metric (Revenue/GP/GP1) only includes data from
# employees who have that specific KPI target assigned
with timer("Metrics: calculate_pipeline_forecast_metrics"):
    pipeline_forecast_metrics = metrics_calc.calculate_pipeline_forecast_metrics(
        total_backlog_df=data['total_backlog'],
        in_period_backlog_df=data['in_period_backlog'],
        backlog_detail_df=data['backlog_detail'],  # Needed for employee filtering
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date']
    )

# Analyze in-period backlog for overdue detection
# FIXED v2.11.0: Pass period_type and year for correct full period end date calculation
with timer("Metrics: analyze_in_period_backlog"):
    in_period_backlog_analysis = metrics_calc.analyze_in_period_backlog(
        backlog_detail_df=data['backlog_detail'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date'],
        period_type=active_filters['period_type'],
        year=active_filters['year']
    )

# Get period context for display logic
period_context = backlog_metrics.get('period_context', {})

# =============================================================================
# ANALYZE PERIOD TYPE
# =============================================================================

period_info = analyze_period(active_filters)

# YoY comparison (only for single-year periods)
yoy_metrics = None
if active_filters['compare_yoy'] and not period_info['is_multi_year']:
    # OPTIMIZATION v2.6.0: Cache previous year data
    yoy_cache_key = f"prev_year_data_{active_filters['start_date']}_{active_filters['end_date']}_{tuple(active_filters['employee_ids'] or [])}"
    
    if yoy_cache_key not in st.session_state:
        with timer("DB: get_previous_year_data"):
            previous_sales_df = queries.get_previous_year_data(
                start_date=active_filters['start_date'],
                end_date=active_filters['end_date'],
                employee_ids=active_filters['employee_ids'],
                entity_ids=active_filters['entity_ids'] if active_filters['entity_ids'] else None
            )
        st.session_state[yoy_cache_key] = previous_sales_df
    else:
        previous_sales_df = st.session_state[yoy_cache_key]
        if DEBUG_TIMING:
            print(f"   ♻️ Using cached previous_year_data ({len(previous_sales_df)} rows)")
    
    if not previous_sales_df.empty:
        prev_metrics_calc = SalespersonMetrics(previous_sales_df, None)
        prev_overview = prev_metrics_calc.calculate_overview_metrics(
            period_type=active_filters['period_type'],
            year=active_filters['year'] - 1
        )
        yoy_metrics = metrics_calc.calculate_yoy_comparison(overview_metrics, prev_overview)

# Overall KPI Achievement (weighted average)
with timer("Metrics: calculate_overall_kpi_achievement"):
    overall_achievement = metrics_calc.calculate_overall_kpi_achievement(
        overview_metrics=overview_metrics,
        complex_kpis=complex_kpis,
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        kpi_type_weights=data.get('kpi_type_weights'),
        new_customers_df=data['new_customers'],
        new_products_df=data['new_products'],
        new_business_df=data.get('new_business', pd.DataFrame())
    )

# Print timing summary before rendering
if DEBUG_TIMING:
    print_timing_summary()
    reset_timing()
    print(f"\n🖼️ RENDERING UI...")

# =============================================================================
# PAGE HEADER
# =============================================================================

st.title("👤 Salesperson Performance")
filter_summary = filters_ui.get_filter_summary(active_filters)
st.caption(f"📊 {filter_summary}")

# =============================================================================
# EMPTY STATE BANNER (NEW v2.4.0)
# =============================================================================

if empty_state_info:
    with st.container():
        if empty_state_info.get('is_empty_selection'):
            # Empty due to filter settings (e.g., "Only with KPI" checked but no KPIs)
            year = empty_state_info.get('year', date.today().year)
            total_sp = empty_state_info.get('total_salesperson_count', 0)
            
            st.info(
                f"""
                ℹ️ **No salespeople match current filters**
                
                • "Only with KPI assignment" is checked for year **{year}**
                • **0** salespeople have KPI assignments for {year} ({total_sp} total salespeople)
                
                **Options:**
                - Uncheck "Only with KPI assignment" in sidebar to see all salespeople
                - Go to **⚙️ Setup** tab → **KPI Assignments** to create {year} targets
                
                *Data below shows $0 values. Setup tab is fully accessible.*
                """
            )
        elif empty_state_info.get('has_empty_data'):
            # Empty due to no data for selected filters
            st.warning(
                """
                📭 **No data found for the selected filters**
                
                Try adjusting your filter criteria or date range.
                """
            )

# =============================================================================
# TABS
# =============================================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview",
    "📋 Sales Detail",
    "📦 Backlog",
    "🎯 KPI & Targets",
    "⚙️ Setup"
])

# =============================================================================
# TAB 1: OVERVIEW
# =============================================================================

with tab1:
    # KPI Cards - Performance & New Business sections
    SalespersonCharts.render_kpi_cards(
        metrics=overview_metrics,
        yoy_metrics=yoy_metrics,
        complex_kpis=complex_kpis,
        backlog_metrics=None,  # Backlog shown in separate Backlog & Forecast section below
        overall_achievement=overall_achievement,
        show_complex=True,
        show_backlog=False,  # Backlog & Forecast section is rendered separately
        # NEW v1.2.0: Pass detail dataframes for popup buttons
        new_customers_df=data['new_customers'],
        new_products_df=data['new_products'],
        new_business_df=fresh_new_business_df,
        # NEW v1.5.0: Pass combo detail for New Business popup
        new_business_detail_df=fresh_new_business_detail_df,
        # NEW v1.3.0: Pass new combos detail for New Combos popup
        new_combos_detail_df=fresh_new_combos_detail_df
    )
    
    st.divider()
    
    # Forecast section - only show for current/future periods
    if period_context.get('show_forecast', True):
        col_bf_header, col_bf_help = st.columns([6, 1])
        with col_bf_header:
            st.subheader("📦 Backlog & Forecast")
        with col_bf_help:
            with st.popover("ℹ️ Help"):
                st.markdown("""
**📦 Backlog & Forecast**

| Metric | Formula | Description |
|--------|---------|-------------|
| **Total Backlog** | `Σ backlog_by_split_usd` | All outstanding orders (all employees) |
| **In-Period (KPI)** | `Σ backlog WHERE ETD in period` | Backlog expected to ship in period. **Only from employees with this KPI assigned.** |
| **Target** | `Σ prorated_target` | Sum of prorated annual targets |
| **Forecast (KPI)** | `Invoiced + In-Period` | Projected total. **Only from employees with this KPI assigned.** |
| **GAP/Surplus** | `Forecast - Target` | Positive = ahead of target, Negative = behind |

---

**⚠️ Important: Data Filtered by KPI Assignment**

Each tab shows data ONLY from employees who have that specific KPI target:
- **Revenue tab**: Employees with Revenue KPI
- **GP tab**: Employees with Gross Profit KPI  
- **GP1 tab**: Employees with GP1 KPI

This ensures accurate achievement calculation.

---

**📐 Target Calculation:**
```
Target = Σ (Annual_Target × Proration_Factor)
```

Proration by Period Type:
- **YTD**: elapsed_months / 12
- **QTD**: 1/4
- **MTD**: 1/12

---

**📊 GP1 Backlog Estimation:**
```
Backlog GP1 = Backlog GP × (GP1/GP ratio from invoiced data)
```
                """)
        
        # Show overdue warning if applicable
        if in_period_backlog_analysis.get('overdue_warning'):
            st.warning(in_period_backlog_analysis['overdue_warning'])
        
        # Convert pipeline_forecast_metrics to legacy format for chart methods
        chart_backlog_metrics = SalespersonCharts.convert_pipeline_to_backlog_metrics(
            pipeline_forecast_metrics
        )
        
        # Extract metrics for cards
        revenue_metrics = pipeline_forecast_metrics.get('revenue', {})
        gp_metrics = pipeline_forecast_metrics.get('gross_profit', {})
        gp1_metrics = pipeline_forecast_metrics.get('gp1', {})
        summary_metrics = pipeline_forecast_metrics.get('summary', {})
        
        # Show GP1/GP ratio if available
        gp1_gp_ratio = summary_metrics.get('gp1_gp_ratio', 1.0)
        if gp1_gp_ratio != 1.0:
            st.caption(f"📊 GP1 backlog estimated using GP1/GP ratio: {gp1_gp_ratio:.2%}")
        
        # Tabs for different metrics
        bf_tab1, bf_tab2, bf_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        # =================================================================
        # TAB: REVENUE
        # =================================================================
        with bf_tab1:
            # Metrics cards row
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            
            with col_m1:
                # FIXED v2.2.0: Use summary_metrics for orders count to match total_backlog_revenue
                st.metric(
                    label="Total Backlog",
                    value=f"${summary_metrics.get('total_backlog_revenue', 0):,.0f}",
                    delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
                    delta_color="off",
                    help="All outstanding revenue from pending orders (all employees)"
                )
            
            with col_m2:
                in_period = revenue_metrics.get('in_period_backlog', 0)
                target = revenue_metrics.get('target')
                pct = (in_period / target * 100) if target and target > 0 else None
                emp_count = revenue_metrics.get('employee_count', 0)
                st.metric(
                    label="In-Period (KPI)",
                    value=f"${in_period:,.0f}",
                    delta=f"{pct:.0f}% of target" if pct else None,
                    delta_color="off",
                    help=f"Backlog with ETD in period. Only from {emp_count} employees with Revenue KPI assigned."
                )
            
            with col_m3:
                target = revenue_metrics.get('target')
                emp_count = revenue_metrics.get('employee_count', 0)
                if target and target > 0:
                    st.metric(
                        label="Target",
                        value=f"${target:,.0f}",
                        delta=f"{emp_count} people",
                        delta_color="off",
                        help=f"Sum of prorated Revenue targets from {emp_count} employees with Revenue KPI"
                    )
                else:
                    st.metric(label="Target", value="N/A", delta="No KPI assigned", delta_color="off")
            
            with col_m4:
                forecast = revenue_metrics.get('forecast')
                achievement = revenue_metrics.get('forecast_achievement')
                emp_count = revenue_metrics.get('employee_count', 0)
                if forecast is not None:
                    delta_color = "normal" if achievement and achievement >= 100 else "inverse"
                    st.metric(
                        label="Forecast (KPI)",
                        value=f"${forecast:,.0f}",
                        delta=f"{achievement:.0f}% of target" if achievement else None,
                        delta_color=delta_color if achievement else "off",
                        help=f"Invoiced + In-Period Backlog. Only from {emp_count} employees with Revenue KPI."
                    )
                else:
                    st.metric(label="Forecast (KPI)", value="N/A", delta_color="off")
            
            with col_m5:
                gap = revenue_metrics.get('gap')
                gap_pct = revenue_metrics.get('gap_percent')
                if gap is not None:
                    label = "Surplus ✅" if gap >= 0 else "GAP ⚠️"
                    delta_color = "normal" if gap >= 0 else "inverse"
                    st.metric(
                        label=label,
                        value=f"${gap:+,.0f}",
                        delta=f"{gap_pct:+.1f}%" if gap_pct else None,
                        delta_color=delta_color,
                        help="Forecast - Target. Positive = ahead, Negative = behind."
                    )
                else:
                    st.metric(label="GAP", value="N/A", delta_color="off")
            
            # Charts row
            col_bf1, col_bf2 = st.columns(2)
            with col_bf1:
                forecast_chart = SalespersonCharts.build_forecast_waterfall_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metric='revenue',
                    title="Revenue Forecast vs Target"
                )
                st.altair_chart(forecast_chart, use_container_width=True)
            with col_bf2:
                gap_chart = SalespersonCharts.build_gap_analysis_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metrics_to_show=['revenue'],
                    title="Revenue: Target vs Forecast"
                )
                st.altair_chart(gap_chart, use_container_width=True)
        
        # =================================================================
        # TAB: GROSS PROFIT
        # =================================================================
        with bf_tab2:
            # Metrics cards row
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            
            with col_m1:
                # FIXED v2.2.0: Use summary_metrics for orders count to match total_backlog_gp
                st.metric(
                    label="Total Backlog",
                    value=f"${summary_metrics.get('total_backlog_gp', 0):,.0f}",
                    delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
                    delta_color="off",
                    help="All outstanding GP from pending orders (all employees)"
                )
            
            with col_m2:
                in_period = gp_metrics.get('in_period_backlog', 0)
                target = gp_metrics.get('target')
                pct = (in_period / target * 100) if target and target > 0 else None
                emp_count = gp_metrics.get('employee_count', 0)
                st.metric(
                    label="In-Period (KPI)",
                    value=f"${in_period:,.0f}",
                    delta=f"{pct:.0f}% of target" if pct else None,
                    delta_color="off",
                    help=f"Backlog with ETD in period. Only from {emp_count} employees with GP KPI assigned."
                )
            
            with col_m3:
                target = gp_metrics.get('target')
                emp_count = gp_metrics.get('employee_count', 0)
                if target and target > 0:
                    st.metric(
                        label="Target",
                        value=f"${target:,.0f}",
                        delta=f"{emp_count} people",
                        delta_color="off",
                        help=f"Sum of prorated GP targets from {emp_count} employees with GP KPI"
                    )
                else:
                    st.metric(label="Target", value="N/A", delta="No KPI assigned", delta_color="off")
            
            with col_m4:
                forecast = gp_metrics.get('forecast')
                achievement = gp_metrics.get('forecast_achievement')
                emp_count = gp_metrics.get('employee_count', 0)
                if forecast is not None:
                    delta_color = "normal" if achievement and achievement >= 100 else "inverse"
                    st.metric(
                        label="Forecast (KPI)",
                        value=f"${forecast:,.0f}",
                        delta=f"{achievement:.0f}% of target" if achievement else None,
                        delta_color=delta_color if achievement else "off",
                        help=f"Invoiced + In-Period Backlog. Only from {emp_count} employees with GP KPI."
                    )
                else:
                    st.metric(label="Forecast (KPI)", value="N/A", delta_color="off")
            
            with col_m5:
                gap = gp_metrics.get('gap')
                gap_pct = gp_metrics.get('gap_percent')
                if gap is not None:
                    label = "Surplus ✅" if gap >= 0 else "GAP ⚠️"
                    delta_color = "normal" if gap >= 0 else "inverse"
                    st.metric(
                        label=label,
                        value=f"${gap:+,.0f}",
                        delta=f"{gap_pct:+.1f}%" if gap_pct else None,
                        delta_color=delta_color,
                        help="Forecast - Target. Positive = ahead, Negative = behind."
                    )
                else:
                    st.metric(label="GAP", value="N/A", delta_color="off")
            
            # Charts row
            col_bf1, col_bf2 = st.columns(2)
            with col_bf1:
                forecast_chart = SalespersonCharts.build_forecast_waterfall_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metric='gp',
                    title="GP Forecast vs Target"
                )
                st.altair_chart(forecast_chart, use_container_width=True)
            with col_bf2:
                gap_chart = SalespersonCharts.build_gap_analysis_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metrics_to_show=['gp'],
                    title="GP: Target vs Forecast"
                )
                st.altair_chart(gap_chart, use_container_width=True)
        
        # =================================================================
        # TAB: GP1
        # =================================================================
        with bf_tab3:
            # Metrics cards row
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            
            with col_m1:
                # FIXED v2.2.0: Use summary_metrics for orders count to match total_backlog_gp1
                st.metric(
                    label="Total Backlog",
                    value=f"${summary_metrics.get('total_backlog_gp1', 0):,.0f}",
                    delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
                    delta_color="off",
                    help=f"Estimated GP1 backlog (GP × {gp1_gp_ratio:.2%}). All employees."
                )
            
            with col_m2:
                in_period = gp1_metrics.get('in_period_backlog', 0)
                target = gp1_metrics.get('target')
                pct = (in_period / target * 100) if target and target > 0 else None
                emp_count = gp1_metrics.get('employee_count', 0)
                st.metric(
                    label="In-Period (KPI)",
                    value=f"${in_period:,.0f}",
                    delta=f"{pct:.0f}% of target" if pct else None,
                    delta_color="off",
                    help=f"Estimated GP1 backlog with ETD in period. Only from {emp_count} employees with GP1 KPI assigned."
                )
            
            with col_m3:
                target = gp1_metrics.get('target')
                emp_count = gp1_metrics.get('employee_count', 0)
                if target and target > 0:
                    st.metric(
                        label="Target",
                        value=f"${target:,.0f}",
                        delta=f"{emp_count} people",
                        delta_color="off",
                        help=f"Sum of prorated GP1 targets from {emp_count} employees with GP1 KPI"
                    )
                else:
                    st.metric(label="Target", value="N/A", delta="No KPI assigned", delta_color="off")
            
            with col_m4:
                forecast = gp1_metrics.get('forecast')
                achievement = gp1_metrics.get('forecast_achievement')
                emp_count = gp1_metrics.get('employee_count', 0)
                if forecast is not None:
                    delta_color = "normal" if achievement and achievement >= 100 else "inverse"
                    st.metric(
                        label="Forecast (KPI)",
                        value=f"${forecast:,.0f}",
                        delta=f"{achievement:.0f}% of target" if achievement else None,
                        delta_color=delta_color if achievement else "off",
                        help=f"Invoiced + In-Period Backlog (estimated). Only from {emp_count} employees with GP1 KPI."
                    )
                else:
                    st.metric(label="Forecast (KPI)", value="N/A", delta_color="off")
            
            with col_m5:
                gap = gp1_metrics.get('gap')
                gap_pct = gp1_metrics.get('gap_percent')
                if gap is not None:
                    label = "Surplus ✅" if gap >= 0 else "GAP ⚠️"
                    delta_color = "normal" if gap >= 0 else "inverse"
                    st.metric(
                        label=label,
                        value=f"${gap:+,.0f}",
                        delta=f"{gap_pct:+.1f}%" if gap_pct else None,
                        delta_color=delta_color,
                        help="Forecast - Target. Positive = ahead, Negative = behind."
                    )
                else:
                    st.metric(label="GAP", value="N/A", delta_color="off")
            
            # Charts row
            col_bf1, col_bf2 = st.columns(2)
            with col_bf1:
                forecast_chart = SalespersonCharts.build_forecast_waterfall_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metric='gp1',
                    title="GP1 Forecast vs Target"
                )
                st.altair_chart(forecast_chart, use_container_width=True)
            with col_bf2:
                gap_chart = SalespersonCharts.build_gap_analysis_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metrics_to_show=['gp1'],
                    title="GP1: Target vs Forecast"
                )
                st.altair_chart(gap_chart, use_container_width=True)
        
        st.divider()
    else:
        # Historical period - show info message with detailed explanation
        st.info(f"""
        📅 **Forecast not available for historical periods**
        
        End date ({active_filters['end_date'].strftime('%Y-%m-%d')}) is in the past.
        Forecast is only meaningful when end date >= today.
        
        💡 **Tip:** To view Forecast, adjust End Date to today or a future date.
        """)
        st.divider()

    # ==========================================================================
    # MONTHLY TREND + CUMULATIVE - FRAGMENT
    # Only reruns when filters in this section change (not entire page)
    # ==========================================================================
    monthly_trend_fragment(
        sales_df=data['sales'],
        targets_df=data['targets'],
        fragment_key="trend"
    )
    
    # ==========================================================================
    # YEAR COMPARISON SECTION
    # Single-year: YoY Comparison (current vs previous year)
    # Multi-year: Multi-Year Comparison (all years in period)
    # ==========================================================================
    
    st.divider()
    
    # ==========================================================================
    # YEAR-OVER-YEAR COMPARISON - FRAGMENT
    # Only reruns when filters in this section change (not entire page)
    # ==========================================================================
    yoy_comparison_fragment(
        sales_df=data['sales'],
        queries=queries,
        filter_values=active_filters,
        fragment_key="yoy"
    )
    
    st.divider()
    
    # Top customers/brands with metric tabs and help
    col_tc_header, col_tc_help = st.columns([6, 1])
    with col_tc_header:
        st.subheader("🏆 Top Customers & Brands Analysis")
    with col_tc_help:
        with st.popover("ℹ️ Help"):
            st.markdown("""
            **🏆 Pareto Analysis (80/20 Rule)**
            
            Shows customers/brands contributing to **80%** of the selected metric.
            
            **Chart Elements:**
            | Element | Description |
            |---------|-------------|
            | Bars | Individual contribution |
            | Line | Cumulative % |
            | 80% line | Pareto threshold |
            
            **Calculation:**
            1. Sort by metric (descending)
            2. Calculate cumulative sum
            3. Show items until 80% reached
            
            **Metrics Available:**
            - **Revenue**: Total sales by customer/brand
            - **Gross Profit**: GP contribution
            - **GP1**: GP1 contribution
            
            **Use Cases:**
            - Identify key accounts
            - Focus sales efforts
            - Risk assessment (concentration)
            """)
    
    ranking_tab1, ranking_tab2, ranking_tab3 = st.tabs(["💰 By Revenue", "📈 By Gross Profit", "📊 By GP1"])
    
    with ranking_tab1:
        col3, col4 = st.columns(2)
        with col3:
            top_customers = metrics_calc.prepare_top_customers_by_metric('revenue', top_percent=0.8)
            if not top_customers.empty:
                chart = SalespersonCharts.build_top_customers_chart(
                    top_df=top_customers, 
                    metric='revenue',
                    title="Top Customers by Revenue"
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No customer data available")
        with col4:
            top_brands = metrics_calc.prepare_top_brands_by_metric('revenue', top_percent=0.8)
            if not top_brands.empty:
                chart = SalespersonCharts.build_top_brands_chart(
                    top_df=top_brands,
                    metric='revenue',
                    title="Top Brands by Revenue"
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No brand data available")
    
    with ranking_tab2:
        col3, col4 = st.columns(2)
        with col3:
            top_customers = metrics_calc.prepare_top_customers_by_metric('gross_profit', top_percent=0.8)
            if not top_customers.empty:
                chart = SalespersonCharts.build_top_customers_chart(
                    top_df=top_customers,
                    metric='gross_profit',
                    title="Top Customers by Gross Profit"
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No customer data available")
        with col4:
            top_brands = metrics_calc.prepare_top_brands_by_metric('gross_profit', top_percent=0.8)
            if not top_brands.empty:
                chart = SalespersonCharts.build_top_brands_chart(
                    top_df=top_brands,
                    metric='gross_profit',
                    title="Top Brands by Gross Profit"
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No brand data available")
    
    with ranking_tab3:
        col3, col4 = st.columns(2)
        with col3:
            top_customers = metrics_calc.prepare_top_customers_by_metric('gp1', top_percent=0.8)
            if not top_customers.empty:
                chart = SalespersonCharts.build_top_customers_chart(
                    top_df=top_customers,
                    metric='gp1',
                    title="Top Customers by GP1"
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No customer data available")
        with col4:
            top_brands = metrics_calc.prepare_top_brands_by_metric('gp1', top_percent=0.8)
            if not top_brands.empty:
                chart = SalespersonCharts.build_top_brands_chart(
                    top_df=top_brands,
                    metric='gp1',
                    title="Top Brands by GP1"
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No brand data available")
    
    st.divider()
    
    # Summary table
    st.subheader("📋 Performance by Salesperson")
    # FIXED v3.2.0: Pass raw dataframes for per-salesperson complex KPI calculation
    salesperson_summary = metrics_calc.aggregate_by_salesperson(
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        new_customers_df=data['new_customers'],
        new_products_df=data['new_products'],
        new_business_df=data.get('new_business', pd.DataFrame())
    )
    
    if not salesperson_summary.empty:
        display_cols = ['sales_name', 'revenue', 'gross_profit', 'gp1', 'gp_percent', 'customers', 'invoices']
        # UPDATED v3.2.0: Use overall_achievement (weighted avg of all KPIs) instead of revenue_achievement
        if 'overall_achievement' in salesperson_summary.columns:
            display_cols.append('overall_achievement')
        
        display_df = salesperson_summary[[c for c in display_cols if c in salesperson_summary.columns]].copy()
        display_df.columns = ['Salesperson', 'Revenue', 'Gross Profit', 'GP1', 'GP %', 'Customers', 'Invoices'] + \
                            (['Achievement %'] if 'overall_achievement' in display_cols else [])
        
        st.dataframe(
            display_df.style.format({
                'Revenue': '${:,.0f}',
                'Gross Profit': '${:,.0f}',
                'GP1': '${:,.0f}',
                'GP %': '{:.1f}%',
                'Achievement %': '{:.1f}%'
            } if 'Achievement %' in display_df.columns else {
                'Revenue': '${:,.0f}',
                'Gross Profit': '${:,.0f}',
                'GP1': '${:,.0f}',
                'GP %': '{:.1f}%',
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No salesperson data available for the selected filters")
    
    # ==========================================================================
    # EXPORT REPORT - FRAGMENT (NEW v2.4.0)
    # Runs independently - no page reload when generating
    # ==========================================================================
    st.divider()
    # FIXED v2.5.1: Use prepared_backlog_by_month for consistent filtering
    prepared_backlog_by_month = _prepare_backlog_by_month_from_detail(data['backlog_detail'])
    
    export_report_fragment(
        overview_metrics=overview_metrics,
        complex_kpis=complex_kpis,
        pipeline_forecast_metrics=pipeline_forecast_metrics,
        yoy_metrics=yoy_metrics,
        in_period_backlog_analysis=in_period_backlog_analysis,
        filter_values=active_filters,
        sales_df=data['sales'],
        total_backlog_df=data['total_backlog'],
        backlog_detail_df=data['backlog_detail'],
        backlog_by_month_df=prepared_backlog_by_month,
        targets_df=data['targets'],
        # NEW v3.2.0: Pass raw dataframes for per-salesperson achievement
        new_customers_df=data['new_customers'],
        new_products_df=data['new_products'],
        new_business_df=data.get('new_business', pd.DataFrame()),
        metrics_calc=metrics_calc,
        # NEW v2.5.0: Add kpi_type_weights for synced Overall Achievement
        kpi_type_weights=data.get('kpi_type_weights', {}),
        fragment_key="export"
    )

# =============================================================================
# TAB 2: SALES DETAIL
# UPDATED v3.4.0: Combined fragment with filters ABOVE sub-tabs
# =============================================================================

with tab2:
    # Combined fragment: filters above + sub-tabs below
    # When filter changes, all sub-tabs update (no full page rerun)
    sales_detail_tab_fragment(
        sales_df=data['sales'],
        overview_metrics=overview_metrics,
        filter_values=active_filters,
        fragment_key="sales_detail_tab"
    )

# =============================================================================
# TAB 3: BACKLOG
# UPDATED v3.4.0: Combined fragment with filters ABOVE sub-tabs
# =============================================================================

with tab3:
    col_bl_header, col_bl_help = st.columns([6, 1])
    with col_bl_header:
        st.subheader("📦 Backlog Analysis")
    with col_bl_help:
        with st.popover("ℹ️ Help"):
            st.markdown("""
**📦 Backlog Analysis**

Backlog is a snapshot of ALL pending orders **at current time**.

| Metric | Description |
|--------|-------------|
| **Total Backlog** | All pending orders (not yet invoiced) |
| **Total GP** | Total gross profit from pending orders |
| **In-Period** | Orders with ETD within selected date range |
| **In-Period GP** | Gross profit from in-period orders |
| **On Track** | In-period orders with ETD ≥ today |
| **Overdue** | In-period orders with ETD < today (past due) |

---

**⚠️ Important Notes:**
- Backlog is NOT historical data - always shows current status
- Date range only filters In-Period calculation
- This section shows ALL selected employees (not KPI-filtered)
- Different from Overview's In-Period (KPI) which only includes employees with KPI assigned

---

**📊 Comparison with Overview:**

| Section | In-Period Scope |
|---------|-----------------|
| **Overview** → In-Period (KPI) | Only employees with KPI assigned |
| **Backlog Tab** → In-Period | All selected employees |
            """)
    
    # Combined fragment: filters above + sub-tabs below
    # When filter changes, all sub-tabs update (no full page rerun)
    # FIXED v2.5.1: Use backlog_detail (which respects salesperson filter)
    prepared_backlog_by_month = _prepare_backlog_by_month_from_detail(data['backlog_detail'])
    
    backlog_tab_fragment(
        backlog_df=data['backlog_detail'],
        in_period_backlog_analysis=in_period_backlog_analysis,
        total_backlog_df=data['total_backlog'],
        backlog_by_month_df=prepared_backlog_by_month,
        metrics_calc=metrics_calc,
        current_year=active_filters['year'],
        filter_values=active_filters,
        fragment_key="backlog_tab"
    )

# =============================================================================
# TAB 4: KPI & TARGETS
# =============================================================================

with tab4:
    st.subheader("🎯 KPI & Targets")
    
    targets_df = data['targets']
    
    if targets_df.empty:
        st.info("No KPI assignments found for selected salespeople")
    else:
        # Sub-tabs
        kpi_tab1, kpi_tab2, kpi_tab3 = st.tabs(["📊 My KPIs", "📈 Progress", "🏆 Ranking"])
        
        with kpi_tab1:
            # =================================================================
            # MY KPIs - Professional Layout (Updated v3.5.0)
            # =================================================================
            
            # KPI Icons mapping
            kpi_icons = {
                'revenue': '💰',
                'gross_profit': '📈',
                'gross_profit_1': '📊',
                'gp1': '📊',
                'num_new_customers': '👥',
                'new_customers': '👥',
                'num_new_products': '📦',
                'new_products': '📦',
                'new_business_revenue': '🚀',
                'num_new_projects': '🎯',
                'num_new_combos': '🔗',
                'purchase_value': '🛒',
            }
            
            # Header row with title and help button
            col_header, col_help = st.columns([4, 1])
            with col_header:
                st.markdown("### 📊 KPI Assignments")
            with col_help:
                with st.popover("ℹ️ How it works"):
                    st.markdown("""
                    **KPI Assignments** hiển thị các mục tiêu KPI được gán cho mỗi salesperson.
                    
                    **Columns:**
                    - **KPI**: Loại KPI (Revenue, GP, New Customers, etc.)
                    - **Annual Target**: Mục tiêu cả năm
                    - **Monthly**: Mục tiêu hàng tháng (= Annual / 12)
                    - **Quarterly**: Mục tiêu hàng quý (= Annual / 4)
                    - **Unit**: Đơn vị (USD, customer, product, etc.)
                    - **Weight %**: Trọng số của KPI trong Overall Achievement
                    
                    **Lưu ý:**
                    - Weight % dùng để tính Overall Achievement cá nhân
                    - Tổng Weight không nhất thiết = 100%
                    """)
            
            st.markdown("")
            
            # Get unique salespeople
            unique_salespeople = targets_df[['employee_id', 'employee_name']].drop_duplicates()
            num_salespeople = len(unique_salespeople)
            
            # If multiple salespeople, show summary card first
            if num_salespeople > 1:
                with st.container(border=True):
                    st.markdown(f"##### 📋 ALL (Rollup from {num_salespeople} salespeople)")
                    
                    # Aggregate targets by KPI type
                    all_kpis_agg = targets_df.groupby('kpi_name').agg({
                        'annual_target_value_numeric': 'sum',
                        'monthly_target_value': lambda x: x.astype(str).iloc[0] if len(x) > 0 else '',
                        'quarterly_target_value': lambda x: x.astype(str).iloc[0] if len(x) > 0 else '',
                        'unit_of_measure': 'first'
                    }).reset_index()
                    
                    # Recalculate monthly/quarterly from annual
                    all_kpis_agg['monthly_calc'] = all_kpis_agg['annual_target_value_numeric'] / 12
                    all_kpis_agg['quarterly_calc'] = all_kpis_agg['annual_target_value_numeric'] / 4
                    
                    # Build display data
                    display_rows = []
                    for _, kpi_row in all_kpis_agg.iterrows():
                        kpi_name = kpi_row['kpi_name']
                        kpi_lower = kpi_name.lower().replace(' ', '_')
                        icon = kpi_icons.get(kpi_lower, '📌')
                        unit = kpi_row['unit_of_measure'] or ''
                        annual = kpi_row['annual_target_value_numeric']
                        monthly = kpi_row['monthly_calc']
                        quarterly = kpi_row['quarterly_calc']
                        
                        # Format based on unit
                        if 'USD' in str(unit).upper() or 'usd' in str(unit).lower():
                            annual_fmt = f"${annual:,.0f}"
                            monthly_fmt = f"${monthly:,.0f}"
                            quarterly_fmt = f"${quarterly:,.0f}"
                        else:
                            annual_fmt = f"{annual:,.1f}" if annual % 1 != 0 else f"{annual:,.0f}"
                            monthly_fmt = f"{monthly:,.1f}"
                            quarterly_fmt = f"{quarterly:,.1f}"
                        
                        display_rows.append({
                            'KPI': f"{icon} {kpi_name.replace('_', ' ').title()}",
                            'Annual Target': annual_fmt,
                            'Monthly': monthly_fmt,
                            'Quarterly': quarterly_fmt,
                            'Unit': unit
                        })
                    
                    if display_rows:
                        df_display = pd.DataFrame(display_rows)
                        st.dataframe(
                            df_display,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                'KPI': st.column_config.TextColumn('KPI', width='medium'),
                                'Annual Target': st.column_config.TextColumn('Annual Target', width='small'),
                                'Monthly': st.column_config.TextColumn('Monthly', width='small'),
                                'Quarterly': st.column_config.TextColumn('Quarterly', width='small'),
                                'Unit': st.column_config.TextColumn('Unit', width='small'),
                            }
                        )
                    
                    # Show aggregated from note
                    names = unique_salespeople['employee_name'].tolist()
                    names_str = ', '.join(names[:5])
                    if len(names) > 5:
                        names_str += f" +{len(names)-5} more"
                    st.caption(f"📊 Aggregated from: {names_str}")
                
                st.markdown("")
            
            # Individual salesperson sections
            for idx, (_, sales_row) in enumerate(unique_salespeople.iterrows()):
                sales_id = sales_row['employee_id']
                sales_name = sales_row['employee_name']
                sales_targets = targets_df[targets_df['employee_id'] == sales_id]
                
                # Calculate total weight for this person
                total_weight = sales_targets['weight_numeric'].sum()
                
                with st.expander(f"👤 {sales_name}", expanded=(num_salespeople == 1 or idx == 0)):
                    # Build formatted display data
                    display_rows = []
                    for _, kpi_row in sales_targets.iterrows():
                        kpi_name = kpi_row['kpi_name']
                        kpi_lower = kpi_name.lower().replace(' ', '_')
                        icon = kpi_icons.get(kpi_lower, '📌')
                        unit = kpi_row['unit_of_measure'] or ''
                        weight = kpi_row['weight_numeric']
                        
                        # Get values
                        annual = kpi_row['annual_target_value']
                        monthly = kpi_row['monthly_target_value']
                        quarterly = kpi_row['quarterly_target_value']
                        
                        # Format weight with color indicator
                        if pd.notna(weight):
                            weight_fmt = f"{weight:.0f}%"
                        else:
                            weight_fmt = "-"
                        
                        display_rows.append({
                            'KPI': f"{icon} {kpi_name.replace('_', ' ').title()}",
                            'Annual Target': annual if pd.notna(annual) else '-',
                            'Monthly': monthly if pd.notna(monthly) else '-',
                            'Quarterly': quarterly if pd.notna(quarterly) else '-',
                            'Unit': unit,
                            'Weight %': weight_fmt
                        })
                    
                    if display_rows:
                        df_display = pd.DataFrame(display_rows)
                        st.dataframe(
                            df_display,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                'KPI': st.column_config.TextColumn('KPI', width='medium'),
                                'Annual Target': st.column_config.TextColumn('Annual Target', width='small'),
                                'Monthly': st.column_config.TextColumn('Monthly', width='small'),
                                'Quarterly': st.column_config.TextColumn('Quarterly', width='small'),
                                'Unit': st.column_config.TextColumn('Unit', width='small'),
                                'Weight %': st.column_config.TextColumn('Weight %', width='small'),
                            }
                        )
                        
                        # Show total weight
                        st.caption(f"📐 Total Weight: **{total_weight:.0f}%** (sum of all KPI weights for Overall Achievement calculation)")
        
        with kpi_tab2:
            # =================================================================
            # KPI Progress - Using new Hierarchical Card Layout (v3.3.0)
            # =================================================================
            
            # Prepare KPI progress data (same logic as before, but passed to fragment)
            kpi_column_map = {
                'revenue': 'sales_by_split_usd',
                'gross_profit': 'gross_profit_by_split_usd',
                'gross_profit_1': 'gp1_by_split_usd',
            }
            complex_kpi_names = ['num_new_customers', 'num_new_products', 'new_business_revenue']
            kpi_display_names = {
                'revenue': 'Revenue',
                'gross_profit': 'Gross Profit',
                'gross_profit_1': 'GP1',
                'num_new_customers': 'New Customers',
                'num_new_products': 'New Products',
                'new_business_revenue': 'New Business Revenue',
                'num_new_projects': 'New Projects',
            }
            currency_kpis = ['revenue', 'gross_profit', 'gross_profit_1', 'new_business_revenue']
            
            # Build KPI progress data
            kpi_progress = []
            sales_df = data['sales']
            
            for kpi_name in targets_df['kpi_name'].str.lower().unique():
                employees_with_target = targets_df[
                    targets_df['kpi_name'].str.lower() == kpi_name
                ]['employee_id'].unique().tolist()
                
                kpi_target = targets_df[
                    targets_df['kpi_name'].str.lower() == kpi_name
                ]['annual_target_value_numeric'].sum()
                
                if kpi_target <= 0:
                    continue
                
                if kpi_name in kpi_column_map:
                    col_name = kpi_column_map[kpi_name]
                    if not sales_df.empty and col_name in sales_df.columns:
                        filtered_sales = sales_df[sales_df['sales_id'].isin(employees_with_target)]
                        actual = filtered_sales[col_name].sum() if not filtered_sales.empty else 0
                    else:
                        actual = 0
                elif kpi_name in complex_kpi_names:
                    cache_key = f"complex_kpi_{kpi_name}_{active_filters['start_date']}_{active_filters['end_date']}_{tuple(sorted(employees_with_target))}"
                    if cache_key not in st.session_state:
                        calc = st.session_state.get('raw_cached_data', {}).get('_complex_kpi_calculator')
                        if calc is not None:
                            result = calc.calculate_all(
                                start_date=active_filters['start_date'],
                                end_date=active_filters['end_date'],
                                employee_ids=employees_with_target
                            )
                            summary = result.get('summary', {})
                            if kpi_name == 'num_new_customers':
                                actual = summary.get('num_new_customers', 0)
                            elif kpi_name == 'num_new_products':
                                actual = summary.get('num_new_products', 0)
                            elif kpi_name == 'new_business_revenue':
                                actual = summary.get('new_business_revenue', 0)
                            else:
                                actual = 0
                        else:
                            actual = 0
                        st.session_state[cache_key] = actual
                    else:
                        actual = st.session_state[cache_key]
                else:
                    actual = 0
                
                display_name = kpi_display_names.get(kpi_name, kpi_name.replace('_', ' ').title())
                prorated_target = metrics_calc._get_prorated_target(kpi_name, active_filters['period_type'], active_filters['year'])
                if prorated_target is None:
                    prorated_target = kpi_target
                
                achievement = (actual / prorated_target * 100) if prorated_target and prorated_target > 0 else 0
                
                kpi_progress.append({
                    'kpi_name': kpi_name,
                    'KPI': display_name,
                    'Actual': actual,
                    'Target (Annual)': kpi_target,
                    'Target (Prorated)': prorated_target,
                    'Achievement %': achievement,
                    'is_currency': kpi_name in currency_kpis,
                    'employee_count': len(employees_with_target)
                })
            
            # Get salesperson summary for individual performance section
            salesperson_summary = metrics_calc.aggregate_by_salesperson(
                period_type=active_filters['period_type'],
                year=active_filters['year'],
                new_customers_df=data['new_customers'],
                new_products_df=data['new_products'],
                new_business_df=data.get('new_business', pd.DataFrame())
            )
            
            # Get overall achievement data
            overall_achievement_data = metrics_calc.calculate_overall_kpi_achievement(
                overview_metrics=overview_metrics,
                complex_kpis=complex_kpis,
                period_type=active_filters['period_type'],
                year=active_filters['year'],
                kpi_type_weights=data.get('kpi_type_weights'),
                new_customers_df=data['new_customers'],
                new_products_df=data['new_products'],
                new_business_df=data.get('new_business', pd.DataFrame())
            )
            
            # Get complex KPI calculator for per-person calculation
            complex_kpi_calc = st.session_state.get('raw_cached_data', {}).get('_complex_kpi_calculator')
            
            # Render the new hierarchical KPI progress fragment
            kpi_progress_fragment(
                targets_df=targets_df,
                sales_df=data['sales'],
                salesperson_summary_df=salesperson_summary,
                overall_achievement_data=overall_achievement_data,
                kpi_progress_data=kpi_progress,
                period_type=active_filters['period_type'],
                year=active_filters['year'],
                selected_employee_ids=active_filters['employee_ids'],
                complex_kpi_calculator=complex_kpi_calc,
                start_date=active_filters['start_date'],
                end_date=active_filters['end_date'],
                fragment_key="kpi_progress"
            )
        
        with kpi_tab3:
            # Use fragment to prevent page rerun on dropdown change
            # FIXED v3.2.0: Pass raw dataframes for per-salesperson complex KPI calculation
            salesperson_summary = metrics_calc.aggregate_by_salesperson(
                period_type=active_filters['period_type'],
                year=active_filters['year'],
                new_customers_df=data['new_customers'],
                new_products_df=data['new_products'],
                new_business_df=data.get('new_business', pd.DataFrame())
            )
            team_ranking_fragment(
                salesperson_summary_df=salesperson_summary,
                fragment_key="team_ranking"
            )

# =============================================================================
# TAB 5: SETUP
# =============================================================================

with tab5:
    setup_tab_fragment(
        sales_split_df=data['sales_split'],
        sales_df=data['sales'],
        active_filters=active_filters,
        fragment_key="setup"
    )


# =============================================================================
# FOOTER
# =============================================================================

# Print final timing summary for UI rendering
if DEBUG_TIMING:
    print_timing_summary()
    print(f"✅ PAGE RENDER COMPLETE\n{'='*60}\n")

st.divider()
st.caption(
    f"Generated by Prostech BI Dashboard | "
    f"User: {st.session_state.get('user_fullname', 'Unknown')} | "
    f"Access: {access.get_access_level().title()}"
)