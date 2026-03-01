# utils/legal_entity_performance/queries.py
"""
SQL Queries for Legal Entity Performance
Aligned with kpi_center_performance/queries.py

Data sources:
  - Sales: unified_sales_by_legal_entity_view (V2)
  - Backlog: backlog_by_legal_entity_view (V2)

VERSION: 2.0.0
- Uses sqlalchemy engine + text() (synced with KPI center)
- Lazy engine loading pattern
"""

import logging
import time
from datetime import date
from typing import List, Optional
import pandas as pd
from sqlalchemy import text

from utils.db import get_db_engine
from .constants import DEBUG_QUERY_TIMING

logger = logging.getLogger(__name__)


class LegalEntityQueries:
    """
    SQL query helpers for Legal Entity Performance.
    
    Usage:
        queries = LegalEntityQueries()
        sales_df = queries.load_sales_raw(lookback_start)
        backlog_df = queries.load_backlog_raw()
    """
    
    def __init__(self):
        self._engine = None
    
    @property
    def engine(self):
        """Lazy load database engine."""
        if self._engine is None:
            self._engine = get_db_engine()
        return self._engine
    
    # =========================================================================
    # SALES RAW DATA
    # =========================================================================
    
    def load_sales_raw(self, lookback_start: date) -> pd.DataFrame:
        """
        Load all sales data from lookback_start.
        Single query replaces all date-range queries.
        
        Args:
            lookback_start: Earliest date to load
        """
        start_time = time.perf_counter()
        
        query = """
            SELECT *
            FROM unified_sales_by_legal_entity_view
            WHERE inv_date >= :lookback_start
            ORDER BY inv_date DESC
        """
        
        try:
            df = pd.read_sql(text(query), self.engine, params={'lookback_start': lookback_start})
            # Normalize column names if needed
            if 'entity_id' in df.columns and 'legal_entity_id' not in df.columns:
                df = df.rename(columns={'entity_id': 'legal_entity_id'})
            elapsed = time.perf_counter() - start_time
            if DEBUG_QUERY_TIMING:
                print(f"   📊 SQL [sales_raw]: {elapsed:.3f}s → {len(df):,} rows")
            return df
        except Exception as e:
            logger.error(f"Error loading sales_raw: {e}")
            return pd.DataFrame()
    
    # =========================================================================
    # AR OUTSTANDING (all unpaid/partial invoices, NO date filter)
    # =========================================================================
    
    def load_ar_outstanding(self) -> pd.DataFrame:
        """
        Load ALL invoices with outstanding balance — not filtered by date.
        
        This gives a complete picture of Accounts Receivable regardless of 
        which period the user selects in sidebar filters.
        
        Includes:
        - Unpaid invoices (payment_status = 'Unpaid')
        - Partially paid invoices (payment_ratio < 1)
        
        Excludes:
        - Fully paid invoices
        - HISTORY rows (payment_status IS NULL)
        """
        start_time = time.perf_counter()
        
        query = """
            SELECT *
            FROM unified_sales_by_legal_entity_view
            WHERE payment_status IS NOT NULL
              AND payment_status != 'Fully Paid'
        """
        
        try:
            df = pd.read_sql(text(query), self.engine)
            # Normalize column names
            if 'entity_id' in df.columns and 'legal_entity_id' not in df.columns:
                df = df.rename(columns={'entity_id': 'legal_entity_id'})
            elapsed = time.perf_counter() - start_time
            if DEBUG_QUERY_TIMING:
                print(f"   📊 SQL [ar_outstanding]: {elapsed:.3f}s → {len(df):,} rows")
            return df
        except Exception as e:
            logger.error(f"Error loading ar_outstanding: {e}")
            return pd.DataFrame()
    
    # =========================================================================
    # BACKLOG RAW DATA
    # =========================================================================
    
    def load_backlog_raw(self) -> pd.DataFrame:
        """
        Load all pending backlog orders.
        Loads ALL pending orders; filtering done later by DataProcessor.
        """
        start_time = time.perf_counter()
        
        query = """
            SELECT *
            FROM backlog_by_legal_entity_view
        """
        
        try:
            df = pd.read_sql(text(query), self.engine)
            # Normalize column name: entity_id → legal_entity_id
            if 'entity_id' in df.columns and 'legal_entity_id' not in df.columns:
                df = df.rename(columns={'entity_id': 'legal_entity_id'})
            elapsed = time.perf_counter() - start_time
            if DEBUG_QUERY_TIMING:
                print(f"   📊 SQL [backlog_raw]: {elapsed:.3f}s → {len(df):,} rows")
            return df
        except Exception as e:
            logger.error(f"Error loading backlog_raw: {e}")
            return pd.DataFrame()