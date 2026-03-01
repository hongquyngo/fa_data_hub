# utils/salesperson_performance/sidebar_options_extractor.py
"""
Sidebar Options Extractor - Extract sidebar options from cached lookback data

Instead of making 3 separate SQL queries for sidebar options (7.3s total),
extract the same information from the already-loaded lookback_sales_data (~0.01s).

Performance Improvement:
- Before: 3 SQL queries = 7.33s
  - salesperson_options: 3.18s
  - entity_options: 2.31s  
  - default_date_range: 1.83s
- After: Pandas extraction = ~0.01s
- Savings: 7.32s (99.9%)

CHANGELOG:
- v1.0.0: Initial implementation
          - extract_salesperson_options(): Get salespeople with invoice counts
          - extract_entity_options(): Get legal entities with invoice counts
          - extract_date_range(): Get min/max years for date range
          - extract_all(): Convenience method for all options

VERSION: 1.0.0
"""

import logging
from datetime import date
from typing import List, Optional, Tuple, Dict, Any
import pandas as pd
import time

logger = logging.getLogger(__name__)

# Debug timing flag
DEBUG_TIMING = True


class SidebarOptionsExtractor:
    """
    Extract sidebar options from cached lookback sales data.
    
    This eliminates the need for separate SQL queries for:
    - Salesperson dropdown options
    - Entity dropdown options
    - Default date range (min/max years)
    
    Usage:
        # After loading lookback data
        lookback_df = queries.get_lookback_sales_data(end_date)
        
        # Extract sidebar options
        extractor = SidebarOptionsExtractor(lookback_df)
        
        # Get options (filtered by access control)
        salesperson_options = extractor.extract_salesperson_options(accessible_ids)
        entity_options = extractor.extract_entity_options()
        start_date, end_date = extractor.extract_date_range()
    """
    
    def __init__(self, lookback_df: pd.DataFrame):
        """
        Initialize with lookback sales data.
        
        Args:
            lookback_df: Sales data from get_lookback_sales_data()
                        Must contain: sales_id, sales_name, sales_email, inv_number,
                                     legal_entity_id, legal_entity, invoice_year
        """
        self._df = lookback_df.copy() if not lookback_df.empty else pd.DataFrame()
        
        # Validate required columns
        required_cols = ['sales_id', 'sales_name', 'inv_number', 'invoice_year']
        if not self._df.empty:
            missing = [c for c in required_cols if c not in self._df.columns]
            if missing:
                logger.warning(f"SidebarOptionsExtractor: Missing columns {missing}")
        
        logger.info(f"SidebarOptionsExtractor initialized: {len(self._df):,} rows")
    
    # =========================================================================
    # SALESPERSON OPTIONS
    # =========================================================================
    
    def extract_salesperson_options(
        self,
        accessible_employee_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Extract salesperson options from cached data.
        
        Equivalent to queries.get_salesperson_options() but uses cached data.
        
        Args:
            accessible_employee_ids: List of employee IDs user has access to.
                                    If None, returns all salespeople.
        
        Returns:
            DataFrame with columns: employee_id, sales_name, email, invoice_count
            Sorted by sales_name
        """
        start_time = time.perf_counter()
        
        if self._df.empty:
            return pd.DataFrame(columns=['employee_id', 'sales_name', 'email', 'invoice_count'])
        
        df = self._df.copy()
        
        # Filter by accessible IDs if provided
        if accessible_employee_ids:
            df = df[df['sales_id'].isin(accessible_employee_ids)]
        
        # Filter valid salespeople
        df = df[df['sales_id'].notna() & df['sales_name'].notna()]
        
        if df.empty:
            return pd.DataFrame(columns=['employee_id', 'sales_name', 'email', 'invoice_count'])
        
        # Aggregate by salesperson
        result = df.groupby(['sales_id', 'sales_name']).agg(
            email=('sales_email', 'first'),
            invoice_count=('inv_number', 'nunique')
        ).reset_index()
        
        # Rename columns to match original query
        result = result.rename(columns={'sales_id': 'employee_id'})
        
        # Filter to those with invoices
        result = result[result['invoice_count'] > 0]
        
        # Sort by name
        result = result.sort_values('sales_name').reset_index(drop=True)
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [extract_salesperson_options] {len(result)} rows in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # ENTITY OPTIONS
    # =========================================================================
    
    def extract_entity_options(self) -> pd.DataFrame:
        """
        Extract legal entity options from cached data.
        
        Equivalent to queries.get_entity_options() but uses cached data.
        
        Returns:
            DataFrame with columns: entity_id, entity_name, invoice_count
            Sorted by entity_name
        """
        start_time = time.perf_counter()
        
        if self._df.empty:
            return pd.DataFrame(columns=['entity_id', 'entity_name', 'invoice_count'])
        
        df = self._df.copy()
        
        # Filter valid entities
        df = df[df['legal_entity_id'].notna() & df['legal_entity'].notna()]
        
        if df.empty:
            return pd.DataFrame(columns=['entity_id', 'entity_name', 'invoice_count'])
        
        # Aggregate by entity
        result = df.groupby(['legal_entity_id', 'legal_entity']).agg(
            invoice_count=('inv_number', 'nunique')
        ).reset_index()
        
        # Rename columns to match original query
        result = result.rename(columns={
            'legal_entity_id': 'entity_id',
            'legal_entity': 'entity_name'
        })
        
        # Filter to those with invoices
        result = result[result['invoice_count'] > 0]
        
        # Sort by name
        result = result.sort_values('entity_name').reset_index(drop=True)
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [extract_entity_options] {len(result)} rows in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # DATE RANGE
    # =========================================================================
    
    def extract_date_range(self) -> Tuple[date, date]:
        """
        Extract default date range from cached data.
        
        Equivalent to queries.get_default_date_range() but uses cached data.
        
        Returns:
            Tuple of (start_date, end_date):
            - start_date: January 1st of max year in data
            - end_date: Today
        """
        start_time = time.perf_counter()
        
        today = date.today()
        
        if self._df.empty:
            return date(today.year, 1, 1), today
        
        # Get max year from data
        max_year = self._df['invoice_year'].max()
        
        if pd.isna(max_year):
            start_date = date(today.year, 1, 1)
        else:
            start_date = date(int(max_year), 1, 1)
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [extract_date_range] {start_date} to {today} in {elapsed:.3f}s")
        
        return start_date, today
    
    # =========================================================================
    # AVAILABLE YEARS
    # =========================================================================
    
    def extract_available_years(self) -> List[int]:
        """
        Extract list of available years from cached data.
        
        Equivalent to queries.get_available_years() but uses cached data.
        
        Returns:
            List of years (descending order)
        """
        start_time = time.perf_counter()
        
        if self._df.empty:
            current_year = date.today().year
            return [current_year, current_year - 1]
        
        # Get unique years
        years = self._df['invoice_year'].dropna().unique()
        years = sorted([int(y) for y in years], reverse=True)
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [extract_available_years] {len(years)} years in {elapsed:.3f}s")
        
        return years
    
    # =========================================================================
    # CONVENIENCE METHOD
    # =========================================================================
    
    def extract_all(
        self,
        accessible_employee_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Extract all sidebar options at once.
        
        Args:
            accessible_employee_ids: List of employee IDs user has access to
            
        Returns:
            Dict with:
            - salesperson_options: DataFrame
            - entity_options: DataFrame
            - date_range: Tuple[date, date]
            - available_years: List[int]
        """
        start_time = time.perf_counter()
        
        result = {
            'salesperson_options': self.extract_salesperson_options(accessible_employee_ids),
            'entity_options': self.extract_entity_options(),
            'date_range': self.extract_date_range(),
            'available_years': self.extract_available_years(),
        }
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [extract_all] Total: {elapsed:.3f}s")
        
        return result


# =============================================================================
# HELPER FUNCTION
# =============================================================================

def extract_sidebar_options_from_lookback(
    lookback_df: pd.DataFrame,
    accessible_employee_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Convenience function to extract all sidebar options from lookback data.
    
    Args:
        lookback_df: Sales data from get_lookback_sales_data()
        accessible_employee_ids: List of employee IDs user has access to
        
    Returns:
        Dict with salesperson_options, entity_options, date_range, available_years
    """
    extractor = SidebarOptionsExtractor(lookback_df)
    return extractor.extract_all(accessible_employee_ids)
