# pages/0_🏢_Legal_Entity_Performance.py
"""
Legal Entity Performance Dashboard

4 Tabs: Overview | Sales Detail | Analysis | Backlog | Payment
Data Sources:
  - Sales: unified_sales_by_legal_entity_view (V2)
  - Backlog: backlog_by_legal_entity_view (V2)

VERSION: 2.2.0
CHANGELOG:
- v2.2.0: Replaced backlog_metrics with pipeline_metrics (KPC-style Backlog & Forecast).
           Removed duplicate backlog cards from KPI section.
- v2.1.0: Added Complex KPIs (New Business section) + enhanced Backlog metrics
- v2.0.0: Aligned with KPI Center Performance patterns
"""

import logging
from datetime import date
import time
from contextlib import contextmanager
import pandas as pd
import streamlit as st

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="Legal Entity Performance",
    page_icon="🏢",
    layout="wide"
)

# =============================================================================
# IMPORTS
# =============================================================================
from utils.auth import AuthManager
from utils.db import check_db_connection

from utils.legal_entity_performance import (
    # Core classes
    UnifiedDataLoader,
    DataProcessor,
    LegalEntityMetrics,
    LegalEntityFilters,
    AccessControl,
    
    # Tab fragments
    overview_tab_fragment,
    sales_detail_tab_fragment,
    analysis_tab_fragment,
    backlog_tab_fragment,
    payment_tab_fragment,
    
    # Constants
    DEBUG_TIMING,
    CACHE_KEY_TIMING,
    CACHE_KEY_FILTERS,
)

logger = logging.getLogger(__name__)


# =============================================================================
# TIMING UTILITIES (synced with KPI center)
# =============================================================================

def _init_timing():
    if CACHE_KEY_TIMING not in st.session_state:
        st.session_state[CACHE_KEY_TIMING] = []


def _reset_timing():
    st.session_state[CACHE_KEY_TIMING] = []


@contextmanager
def timer(name: str):
    _init_timing()
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if DEBUG_TIMING:
            print(f"⏱️ [{name}] {elapsed:.3f}s")
        st.session_state[CACHE_KEY_TIMING].append({'name': name, 'time': elapsed})


def _print_timing_summary():
    if not DEBUG_TIMING:
        return
    timing_data = st.session_state.get(CACHE_KEY_TIMING, [])
    if not timing_data:
        return
    total_time = sum(t['time'] for t in timing_data)
    print(f"\n{'='*60}")
    print(f"📊 LEGAL ENTITY TIMING SUMMARY")
    print(f"{'='*60}")
    for item in sorted(timing_data, key=lambda x: x['time'], reverse=True):
        pct = (item['time'] / total_time * 100) if total_time > 0 else 0
        bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
        print(f"{item['name']:<45} {item['time']:>6.3f}s ({pct:>5.1f}%) {bar}")
    print(f"{'-'*60}")
    print(f"{'TOTAL':<45} {total_time:>6.3f}s")
    print(f"{'='*60}\n")


# =============================================================================
# AUTHENTICATION & ACCESS CONTROL
# =============================================================================

def check_access():
    auth = AuthManager()
    
    if not auth.check_session():
        st.warning("⚠️ Please login to access this page")
        st.info("Go to the main page to login")
        st.stop()
    
    db_connected, db_error = check_db_connection()
    if not db_connected:
        st.error(f"❌ Database connection failed: {db_error}")
        st.stop()
    
    user_role = st.session_state.get('user_role', '')
    access = AccessControl(user_role)
    
    if not access.can_access_page():
        st.error(access.get_denied_message())
        st.stop()
    
    return access


# =============================================================================
# FILTER STATE MANAGEMENT
# =============================================================================

def _get_applied_filters():
    return st.session_state.get(CACHE_KEY_FILTERS)


def _set_applied_filters(filter_values):
    st.session_state[CACHE_KEY_FILTERS] = filter_values


# =============================================================================
# MAIN PAGE
# =============================================================================

def main():
    _reset_timing()
    
    # Auth
    access = check_access()
    
    # Header
    st.title("🏢 Legal Entity Performance")
    st.caption(
        f"Logged in as: {st.session_state.get('user_fullname', 'User')} "
        f"({st.session_state.get('user_role', '')})"
    )
    
    # =========================================================================
    # STEP 1: LOAD UNIFIED RAW DATA (cached)
    # =========================================================================
    with timer("Load unified raw data"):
        loader = UnifiedDataLoader(access)
        unified_cache = loader.get_unified_data()
    
    if unified_cache.get('sales_raw_df') is None or unified_cache['sales_raw_df'].empty:
        st.error("Failed to load data. Please try refreshing the page.")
        _print_timing_summary()
        st.stop()
    
    # =========================================================================
    # STEP 2: EXTRACT FILTER OPTIONS
    # =========================================================================
    with timer("Extract filter options"):
        filter_options = loader.extract_filter_options(unified_cache)
    
    # =========================================================================
    # STEP 3: RENDER SIDEBAR FILTERS (fragment - no full rerun on widget change)
    # =========================================================================
    filters_mgr = LegalEntityFilters(access)
    
    with timer("Render sidebar filters"):
        filters_mgr.render_sidebar_filters(
            entity_df=filter_options['entities'],
            available_years=filter_options['years'],
        )
    
    # =========================================================================
    # STEP 4: GET APPLIED FILTERS (from session state, managed by fragment)
    # =========================================================================
    active_filters = _get_applied_filters()
    if active_filters is None:
        st.info("⏳ Loading filters...")
        st.stop()
    
    is_valid, error_msg = filters_mgr.validate_filters(active_filters)
    if not is_valid:
        st.error(f"⚠️ Filter error: {error_msg}")
        st.stop()
    
    # =========================================================================
    # STEP 4.1: DYNAMIC RELOAD IF CUSTOM PERIOD REQUIRES EXTENDED DATA
    # =========================================================================
    custom_start_date = active_filters.get('custom_start_date')
    if custom_start_date:
        if not loader.is_date_in_cached_range(custom_start_date):
            with timer("Load unified raw data (extended range)"):
                unified_cache = loader.get_unified_data(custom_start_date=custom_start_date)
    
    # =========================================================================
    # STEP 5: PROCESS DATA (Pandas filtering + Complex KPIs)
    # =========================================================================
    with timer("Process data"):
        processor = DataProcessor(unified_cache)
        data = processor.process(active_filters)
    
    sales_df = data.get('sales_df', pd.DataFrame())
    prev_sales_df = data.get('prev_sales_df', pd.DataFrame())
    backlog_df = data.get('backlog_detail_df', pd.DataFrame())
    backlog_in_period_df = data.get('backlog_in_period_df', pd.DataFrame())
    
    # Complex KPIs (calculated inside processor.process() v2.1.0)
    complex_kpis = data.get('complex_kpis', {})
    new_customers_df = data.get('new_customers_df', pd.DataFrame())
    new_products_df = data.get('new_products_df', pd.DataFrame())
    new_combos_detail_df = data.get('new_combos_detail_df', pd.DataFrame())
    new_business_detail_df = data.get('new_business_detail_df', pd.DataFrame())
    
    # =========================================================================
    # STEP 6: CHECK DATA
    # =========================================================================
    if sales_df.empty and backlog_df.empty:
        st.warning("No data found for the selected filters. Try adjusting your selection.")
        _print_timing_summary()
        st.stop()
    
    # =========================================================================
    # STEP 7: CALCULATE METRICS
    # =========================================================================
    with timer("Calculate overview metrics"):
        metrics_calc = LegalEntityMetrics(sales_df)
        overview_metrics = metrics_calc.calculate_overview_metrics()
    
    # YoY metrics
    yoy_metrics = None
    if active_filters.get('show_yoy', True) and not prev_sales_df.empty:
        with timer("Calculate YoY metrics"):
            yoy_metrics = metrics_calc.calculate_yoy_metrics(sales_df, prev_sales_df)
    
    # Pipeline & Forecast metrics (Synced with KPC pattern)
    pipeline_metrics = {}
    with timer("Calculate pipeline metrics"):
        pipeline_metrics = LegalEntityMetrics.calculate_pipeline_metrics(
            sales_df=sales_df,
            backlog_df=backlog_df,
            backlog_in_period_df=backlog_in_period_df,
        )
    
    # Summaries
    with timer("Prepare summaries"):
        monthly_df = processor.prepare_monthly_summary(sales_df)
        entity_summary_df = processor.aggregate_by_entity(sales_df)
    
    # Filter summary
    filter_summary = filters_mgr.get_filter_summary(active_filters)
    st.caption(f"📊 {filter_summary}")
    
    if DEBUG_TIMING:
        print(f"\n🖼️ RENDERING UI...")
    
    # =========================================================================
    # TABS
    # =========================================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview", "📋 Sales Detail", "📈 Analysis", "📦 Backlog", "💰 Payment",
    ])
    
    # =========================================================================
    # TAB 1: OVERVIEW
    # =========================================================================
    with tab1:
        overview_tab_fragment(
            # Data
            sales_df=sales_df,
            overview_metrics=overview_metrics,
            yoy_metrics=yoy_metrics,
            monthly_df=monthly_df,
            entity_summary_df=entity_summary_df,
            active_filters=active_filters,
            prev_sales_df=prev_sales_df,
            unified_cache=unified_cache,
            # Complex KPIs
            complex_kpis=complex_kpis,
            new_customers_df=new_customers_df,
            new_products_df=new_products_df,
            new_combos_detail_df=new_combos_detail_df,
            new_business_detail_df=new_business_detail_df,
            # Pipeline (Backlog & Forecast)
            pipeline_metrics=pipeline_metrics,
            # AR Outstanding (all unpaid/partial, no date filter)
            ar_outstanding_df=unified_cache.get('ar_outstanding_df', pd.DataFrame()),
        )
    
    # =========================================================================
    # TAB 2: SALES DETAIL
    # =========================================================================
    with tab2:
        sales_detail_tab_fragment(
            sales_df=sales_df,
            filter_values=active_filters,
            key_prefix="le_sales"
        )
    
    # =========================================================================
    # TAB 3: ANALYSIS
    # =========================================================================
    with tab3:
        analysis_tab_fragment(
            sales_df=sales_df,
            prev_sales_df=prev_sales_df,
            filter_values=active_filters,
            processor=processor,
        )
    
    # =========================================================================
    # TAB 4: BACKLOG
    # =========================================================================
    with tab4:
        backlog_tab_fragment(
            backlog_df=backlog_df,
            filter_values=active_filters,
            key_prefix="le_backlog"
        )
    
    # =========================================================================
    # TAB 5: PAYMENT & COLLECTION
    # =========================================================================
    with tab5:
        payment_tab_fragment(
            sales_df=sales_df,
            filter_values=active_filters,
            key_prefix="le_payment",
            ar_outstanding_df=unified_cache.get('ar_outstanding_df', pd.DataFrame()),
        )
    
    # =========================================================================
    # TIMING SUMMARY
    # =========================================================================
    if DEBUG_TIMING:
        print(f"✅ PAGE RENDER COMPLETE")
    _print_timing_summary()


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    main()
else:
    main()