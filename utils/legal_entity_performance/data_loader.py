# utils/legal_entity_performance/data_loader.py
"""
Unified Data Loader for Legal Entity Performance
Aligned with kpi_center_performance/data_loader.py

VERSION: 2.0.0
- Same "Load Once, Filter Many" pattern as KPI center
- TTL-based cache invalidation
- Progress bar during loading
- Dynamic loading for Custom periods
- sqlalchemy engine (lazy loaded)

Principles:
1. Load all raw data in one go (3 SQL queries: sales + backlog + AR outstanding)
2. Cache in session_state for duration of session
3. Only reload when cache expired or custom period extends range
4. All filtering done via DataProcessor (Pandas-based)
"""

import logging
import time
from datetime import date, datetime
from typing import Dict, Optional
import pandas as pd
import streamlit as st

from .constants import (
    LOOKBACK_YEARS,
    MIN_DATA_YEAR,
    MAX_FUTURE_YEARS,
    CACHE_TTL_SECONDS,
    CACHE_KEY_UNIFIED,
    DEBUG_TIMING,
)
from .queries import LegalEntityQueries

logger = logging.getLogger(__name__)


class UnifiedDataLoader:
    """
    Load and cache all raw data needed for Legal Entity Performance.
    
    Implements "Load Once, Filter Many" pattern:
    - 3 SQL queries load ALL data (sales + backlog + AR outstanding)
    - Data cached in session_state with TTL
    - Subsequent filter changes use cached data (instant)
    
    Usage:
        loader = UnifiedDataLoader(access_control)
        unified_cache = loader.get_unified_data()
        filter_options = loader.extract_filter_options(unified_cache)
    """
    
    def __init__(self, access_control):
        self.access = access_control
        self.queries = LegalEntityQueries()
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    def get_unified_data(
        self,
        force_reload: bool = False,
        custom_start_date: date = None
    ) -> Dict:
        """
        Get unified raw data (cached or fresh).
        
        Args:
            force_reload: If True, bypass cache and reload from DB
            custom_start_date: Optional custom start date for extended lookback
            
        Returns:
            Dict containing:
            - sales_raw_df: N years of sales data
            - backlog_raw_df: All pending orders
            - ar_outstanding_df: All unpaid/partial invoices (no date filter)
            - _metadata: Loading info
        """
        if not self.access.can_access_page():
            return self._empty_cache()
        
        # Check if we can use cached data
        needs_reload, reload_reason = self._needs_reload(custom_start_date)
        
        if not force_reload and not needs_reload:
            if DEBUG_TIMING:
                print(f"♻️ Using cached unified data (Legal Entity)")
            return st.session_state[CACHE_KEY_UNIFIED]
        
        if DEBUG_TIMING and reload_reason:
            print(f"🔄 Reload reason: {reload_reason}")
        
        return self._load_all_raw_data(custom_start_date=custom_start_date)
    
    def _needs_reload(self, custom_start_date: date = None) -> tuple:
        """
        Check if data needs to be reloaded.
        Returns tuple (needs_reload: bool, reason: str)
        """
        cache = st.session_state.get(CACHE_KEY_UNIFIED)
        
        if cache is None:
            return True, "No cached data"
        
        if cache.get('sales_raw_df') is None:
            return True, "Missing sales_raw_df"
        
        if cache.get('ar_outstanding_df') is None:
            return True, "Missing ar_outstanding_df"
        
        # Check TTL
        loaded_at = cache.get('_loaded_at')
        if loaded_at:
            elapsed = (datetime.now() - loaded_at).total_seconds()
            if elapsed > CACHE_TTL_SECONDS:
                return True, f"TTL expired ({elapsed:.0f}s)"
        
        # Check if custom_start_date requires extended data range
        if custom_start_date:
            cached_start = cache.get('_lookback_start')
            if cached_start and custom_start_date < cached_start:
                return True, f"Custom period before cached range ({custom_start_date} < {cached_start})"
        
        return False, None
    
    def _empty_cache(self) -> Dict:
        return {
            'sales_raw_df': pd.DataFrame(),
            'backlog_raw_df': pd.DataFrame(),
            'ar_outstanding_df': pd.DataFrame(),
            '_loaded_at': None,
            '_lookback_start': None,
            '_lookback_end': None,
        }
    
    # =========================================================================
    # DATA LOADING
    # =========================================================================
    
    def _load_all_raw_data(self, custom_start_date: date = None) -> Dict:
        """
        Load all raw data from database.
        Executes 3 SQL queries: sales + backlog + AR outstanding.
        """
        today = date.today()
        
        # Determine lookback_start
        default_lookback_start = date(max(today.year - LOOKBACK_YEARS, MIN_DATA_YEAR), 1, 1)
        
        if custom_start_date and custom_start_date < default_lookback_start:
            lookback_start = date(max(custom_start_date.year, MIN_DATA_YEAR), 1, 1)
            if DEBUG_TIMING:
                print(f"📅 Using EXTENDED lookback: {lookback_start} (custom) vs {default_lookback_start} (default)")
        else:
            lookback_start = default_lookback_start
        
        lookback_end = date(today.year + MAX_FUTURE_YEARS, 12, 31)
        
        if DEBUG_TIMING:
            print(f"\n{'='*60}")
            print(f"📦 LOADING UNIFIED RAW DATA (Legal Entity)")
            print(f"   Period: {lookback_start} → {lookback_end}")
            print(f"   Lookback: {LOOKBACK_YEARS} years")
            print(f"{'='*60}")
        
        data = {}
        total_start = time.perf_counter()
        
        # Progress bar
        progress_bar = st.progress(0, text="🔄 Loading legal entity data...")
        
        try:
            # 1. SALES RAW DATA
            progress_bar.progress(10, text="📊 Loading sales data...")
            data['sales_raw_df'] = self.queries.load_sales_raw(lookback_start)
            
            # 2. BACKLOG RAW DATA
            progress_bar.progress(45, text="📦 Loading backlog data...")
            data['backlog_raw_df'] = self.queries.load_backlog_raw()
            
            # 3. AR OUTSTANDING (all unpaid/partial, no date filter)
            progress_bar.progress(75, text="💰 Loading AR outstanding...")
            data['ar_outstanding_df'] = self.queries.load_ar_outstanding()
            
            progress_bar.progress(100, text="✅ Data loaded successfully!")
            
        finally:
            import time as _time
            _time.sleep(0.3)
            progress_bar.empty()
        
        # Metadata
        data['_loaded_at'] = datetime.now()
        data['_lookback_start'] = lookback_start
        data['_lookback_end'] = lookback_end
        data['_lookback_years'] = LOOKBACK_YEARS
        
        total_elapsed = time.perf_counter() - total_start
        if DEBUG_TIMING:
            print(f"{'='*60}")
            print(f"✅ UNIFIED DATA LOADED (Legal Entity): {total_elapsed:.3f}s total")
            print(f"   Sales: {len(data['sales_raw_df']):,} rows")
            print(f"   Backlog: {len(data['backlog_raw_df']):,} rows")
            print(f"   AR Outstanding: {len(data['ar_outstanding_df']):,} rows")
            print(f"{'='*60}\n")
        
        # Store in session state
        st.session_state[CACHE_KEY_UNIFIED] = data
        
        logger.info(
            f"Unified data loaded (LE): sales={len(data['sales_raw_df'])}, "
            f"backlog={len(data['backlog_raw_df'])}, "
            f"ar_outstanding={len(data['ar_outstanding_df'])}"
        )
        
        return data
    
    # =========================================================================
    # FILTER OPTIONS EXTRACTION
    # =========================================================================
    
    def extract_filter_options(self, unified_cache: Dict) -> Dict:
        """Extract filter options from cached data."""
        sales_df = unified_cache.get('sales_raw_df', pd.DataFrame())
        backlog_df = unified_cache.get('backlog_raw_df', pd.DataFrame())
        
        return {
            'entities': self._extract_entities(sales_df, backlog_df),
            'years': self._extract_years(sales_df),
            'brands': self._extract_values(sales_df, 'brand'),
            'customer_types': self._extract_values(sales_df, 'customer_type'),
        }
    
    def _extract_entities(self, sales_df: pd.DataFrame,
                          backlog_df: pd.DataFrame) -> pd.DataFrame:
        """Extract unique legal entities from data."""
        frames = []
        
        if not sales_df.empty and 'legal_entity_id' in sales_df.columns:
            frames.append(
                sales_df[['legal_entity_id', 'legal_entity']]
                .dropna(subset=['legal_entity_id'])
                .drop_duplicates()
            )
        
        if not backlog_df.empty and 'legal_entity_id' in backlog_df.columns:
            frames.append(
                backlog_df[['legal_entity_id', 'legal_entity']]
                .dropna(subset=['legal_entity_id'])
                .drop_duplicates()
            )
        
        if not frames:
            return pd.DataFrame(columns=['legal_entity_id', 'legal_entity'])
        
        combined = pd.concat(frames).drop_duplicates(subset=['legal_entity_id'])
        return combined.sort_values('legal_entity').reset_index(drop=True)
    
    def _extract_years(self, sales_df: pd.DataFrame) -> list:
        if sales_df.empty or 'invoice_year' not in sales_df.columns:
            return [date.today().year]
        years = sorted(sales_df['invoice_year'].dropna().unique().tolist(), reverse=True)
        return [int(y) for y in years] if years else [date.today().year]
    
    def _extract_values(self, df: pd.DataFrame, col: str) -> list:
        if df.empty or col not in df.columns:
            return []
        return sorted(df[col].dropna().unique().tolist())
    
    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================
    
    def get_cached_data_range(self) -> Optional[Dict]:
        """Get the date range of currently cached data."""
        cache = st.session_state.get(CACHE_KEY_UNIFIED)
        if not cache:
            return None
        return {
            'lookback_start': cache.get('_lookback_start'),
            'lookback_end': cache.get('_lookback_end'),
            'loaded_at': cache.get('_loaded_at'),
        }
    
    def is_date_in_cached_range(self, check_date: date) -> bool:
        """Check if a date is within the cached data range."""
        cache_range = self.get_cached_data_range()
        if not cache_range:
            return False
        start = cache_range.get('lookback_start')
        end = cache_range.get('lookback_end')
        if not start or not end:
            return False
        return start <= check_date <= end
    
    def clear_cache(self):
        """Clear the unified data cache."""
        if CACHE_KEY_UNIFIED in st.session_state:
            del st.session_state[CACHE_KEY_UNIFIED]
        logger.info("Legal Entity unified data cache cleared")