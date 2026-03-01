# utils/kpi_center_performance/data_processor.py
"""
Data Processor for KPI Center Performance

VERSION: 4.0.1
CHANGELOG:
- v4.0.1: BUGFIX - In-Period Backlog date range
  - Fixed: Use period boundary for backlog ETD filter (not filter date range)
  - YTD: ETD in Jan 1 - Dec 31 (full year)
  - QTD: ETD in quarter start - quarter end
  - MTD: ETD in month start - month end
  - Root cause: Backlog ETD was filtered by filter dates (Jan 1-27) instead of period boundary
- v4.0.0: Initial unified data loading architecture

Process cached raw data based on filter values.
All operations are Pandas-based (instant, no SQL).

This module implements the "Filter Many" part of
"Load Once, Filter Many" pattern.
"""

import logging
import time
import calendar
from datetime import date, datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from .complex_kpi_calculator import ComplexKPICalculator
from .backlog_calculator import BacklogCalculator
from .constants import DEBUG_TIMING, LOOKBACK_YEARS

logger = logging.getLogger(__name__)


class DataProcessor:
    """
    Process cached raw data based on filter values.
    
    All operations are Pandas-based for instant response.
    No SQL queries are executed in this class.
    
    Usage:
        processor = DataProcessor(unified_cache)
        processed_data = processor.process(filter_values)
    """
    
    def __init__(self, unified_cache: Dict):
        """
        Initialize with unified cache.
        
        Args:
            unified_cache: Dict from UnifiedDataLoader.get_unified_data()
        """
        self.sales_raw = unified_cache.get('sales_raw_df', pd.DataFrame())
        self.backlog_raw = unified_cache.get('backlog_raw_df', pd.DataFrame())
        self.targets_raw = unified_cache.get('targets_raw_df', pd.DataFrame())
        self.hierarchy = unified_cache.get('hierarchy_df', pd.DataFrame())
        self._lookback_start = unified_cache.get('_lookback_start')
        
        # Pre-convert date columns for faster filtering
        self._prepare_dataframes()
        
        # Cache for complex KPI calculator (reuse across filter changes)
        self._complex_kpi_calculator = None
    
    def _prepare_dataframes(self):
        """Pre-convert date columns to datetime for faster filtering."""
        if not self.sales_raw.empty and 'inv_date' in self.sales_raw.columns:
            if not pd.api.types.is_datetime64_any_dtype(self.sales_raw['inv_date']):
                self.sales_raw['inv_date'] = pd.to_datetime(self.sales_raw['inv_date'], errors='coerce')
        
        if not self.backlog_raw.empty and 'etd' in self.backlog_raw.columns:
            if not pd.api.types.is_datetime64_any_dtype(self.backlog_raw['etd']):
                self.backlog_raw['etd'] = pd.to_datetime(self.backlog_raw['etd'], errors='coerce')
    
    def _get_backlog_period_end(
        self,
        period_type: str,
        year: int,
        start_date: date,
        end_date: date
    ) -> date:
        """
        Calculate the correct end date for In-Period Backlog ETD filter.
        
        NEW v4.0.1: Backlog ETD should be filtered by PERIOD BOUNDARY, not filter date range.
        
        Logic:
        - Backlog = pending orders (not yet invoiced)
        - ETD = Expected delivery date (should be in future)
        - "In-Period" = orders expected to be delivered within the KPI period
        
        Period boundaries:
        - YTD: Jan 1 → Dec 31 of selected year
        - QTD: Quarter start → Quarter end
        - MTD: Month start → Month end
        - LY: Jan 1 → Dec 31 of previous year
        - Custom: Use filter dates as-is
        
        Args:
            period_type: 'YTD', 'QTD', 'MTD', 'LY', or 'Custom'
            year: Selected year
            start_date: Filter start date
            end_date: Filter end date
            
        Returns:
            Correct end date for backlog ETD filter
            
        Example:
            Filter: YTD 2026, Jan 1 - Jan 27
            → Returns: Dec 31, 2026 (full year)
        """
        if period_type == 'YTD':
            # Full year
            return date(year, 12, 31)
        
        elif period_type == 'QTD':
            # End of quarter containing start_date
            quarter = (start_date.month - 1) // 3 + 1
            quarter_end_month = quarter * 3
            last_day = calendar.monthrange(year, quarter_end_month)[1]
            return date(year, quarter_end_month, last_day)
        
        elif period_type == 'MTD':
            # End of month containing start_date
            last_day = calendar.monthrange(year, start_date.month)[1]
            return date(year, start_date.month, last_day)
        
        elif period_type == 'LY':
            # Full year (previous year is already in 'year' variable)
            return date(year, 12, 31)
        
        else:  # Custom or unknown
            # Use filter end_date as-is
            return end_date
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    def process(self, filter_values: Dict) -> Dict:
        """
        Process all data based on filter values.
        
        This is the main entry point that returns all processed DataFrames
        needed for the dashboard.
        
        Args:
            filter_values: Dict containing:
                - start_date, end_date: Date range
                - year: Selected year
                - kpi_center_ids: Selected KPI Centers
                - kpi_center_ids_expanded: KPI Centers + children
                - entity_ids: Selected entities
                - kpi_type_filter: Selected KPI type
                - exclude_internal_revenue: Boolean
                
        Returns:
            Dict containing all processed DataFrames:
            - sales_df: Filtered sales data
            - targets_df: Filtered targets
            - prev_sales_df: Previous year sales
            - backlog_summary_df, backlog_in_period_df, etc.
            - new_customers_df, new_products_df, etc.
        """
        start_time = time.perf_counter()
        
        if DEBUG_TIMING:
            print(f"\n{'='*60}")
            print(f"🔄 PROCESSING DATA (Pandas only)")
            print(f"{'='*60}")
        
        result = {}
        
        # Extract filter values with defaults
        start_date = filter_values.get('start_date', date.today())
        end_date = filter_values.get('end_date', date.today())
        year = filter_values.get('year', date.today().year)
        period_type = filter_values.get('period_type', 'YTD')  # NEW v4.0.1
        
        # Use expanded IDs (includes children) if available
        kpi_center_ids = filter_values.get(
            'kpi_center_ids_expanded',
            filter_values.get('kpi_center_ids', [])
        )
        entity_ids = filter_values.get('entity_ids', [])
        kpi_type = filter_values.get('kpi_type_filter')
        exclude_internal = filter_values.get('exclude_internal_revenue', True)
        
        # FIXED v4.0.1: Calculate backlog period end based on period_type
        # Backlog ETD should be filtered by full period boundary, not current date range
        backlog_period_end = self._get_backlog_period_end(period_type, year, start_date, end_date)
        if DEBUG_TIMING:
            print(f"   📅 [backlog_period] {period_type}: {start_date} → {backlog_period_end} (ETD filter)")
        
        # =====================================================================
        # 1. FILTER SALES DATA
        # =====================================================================
        t = time.perf_counter()
        result['sales_df'] = self._filter_sales(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids,
            kpi_type=kpi_type,
            exclude_internal=exclude_internal
        )
        if DEBUG_TIMING:
            print(f"   📊 [filter_sales] {time.perf_counter()-t:.3f}s → {len(result['sales_df']):,} rows")
        
        # =====================================================================
        # 2. FILTER TARGETS
        # =====================================================================
        t = time.perf_counter()
        result['targets_df'] = self._filter_targets(
            year=year,
            kpi_center_ids=kpi_center_ids,
            kpi_type=kpi_type
        )
        if DEBUG_TIMING:
            print(f"   📊 [filter_targets] {time.perf_counter()-t:.3f}s → {len(result['targets_df']):,} rows")
        
        # =====================================================================
        # 3. PREVIOUS YEAR DATA (extract from sales_raw)
        # =====================================================================
        t = time.perf_counter()
        result['prev_sales_df'] = self._extract_previous_year(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids,
            kpi_type=kpi_type,
            exclude_internal=exclude_internal
        )
        if DEBUG_TIMING:
            print(f"   📊 [prev_year_sales] {time.perf_counter()-t:.3f}s → {len(result['prev_sales_df']):,} rows")
        
        # =====================================================================
        # 4. PROCESS BACKLOG
        # =====================================================================
        t = time.perf_counter()
        # FIXED v4.0.1: Use backlog_period_end for ETD filter (not end_date)
        backlog_results = self._process_backlog(
            start_date=start_date,
            end_date=backlog_period_end,  # Use period boundary, not filter end_date
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids,
            kpi_type=kpi_type,
            exclude_internal=exclude_internal
        )
        result.update(backlog_results)
        if DEBUG_TIMING:
            print(f"   📊 [process_backlog] {time.perf_counter()-t:.3f}s → {len(result.get('backlog_detail_df', [])):,} detail rows")
        
        # =====================================================================
        # 5. CALCULATE COMPLEX KPIs
        # =====================================================================
        t = time.perf_counter()
        complex_results = self._calculate_complex_kpis(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids,
            exclude_internal=exclude_internal
        )
        result.update(complex_results)
        if DEBUG_TIMING:
            nc = len(result.get('new_customers_df', []))
            np_count = len(result.get('new_products_df', []))
            nb = len(result.get('new_business_detail_df', []))
            print(f"   📊 [complex_kpis] {time.perf_counter()-t:.3f}s → customers:{nc}, products:{np_count}, business:{nb}")
        
        # =====================================================================
        # 6. ADD METADATA
        # =====================================================================
        result['_processed_at'] = datetime.now()
        result['_filter_values'] = filter_values.copy()
        
        total_elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"{'='*60}")
            print(f"✅ DATA PROCESSED: {total_elapsed:.3f}s total")
            print(f"{'='*60}\n")
        
        return result
    
    # =========================================================================
    # FILTER METHODS
    # =========================================================================
    
    def _filter_sales(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int],
        entity_ids: List[int],
        kpi_type: str,
        exclude_internal: bool
    ) -> pd.DataFrame:
        """
        Filter sales_raw_df by all criteria.
        
        Args:
            start_date: Period start date
            end_date: Period end date
            kpi_center_ids: List of KPI Center IDs (already expanded with children)
            entity_ids: List of entity IDs
            kpi_type: KPI type filter (e.g., 'TERRITORY')
            exclude_internal: If True, set internal revenue to 0
            
        Returns:
            Filtered sales DataFrame
        """
        if self.sales_raw.empty:
            return pd.DataFrame()
        
        df = self.sales_raw.copy()
        
        # Date filter
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        df = df[(df['inv_date'] >= start_ts) & (df['inv_date'] <= end_ts)]
        
        # KPI Center filter
        if kpi_center_ids:
            df = df[df['kpi_center_id'].isin(kpi_center_ids)]
        
        # Entity filter
        if entity_ids:
            df = df[df['legal_entity_id'].isin(entity_ids)]
        
        # KPI Type filter
        if kpi_type:
            df = df[df['kpi_type'] == kpi_type]
        
        # Exclude internal revenue (set to 0, keep GP/GP1)
        if exclude_internal and 'customer_type' in df.columns:
            internal_mask = df['customer_type'].str.lower() == 'internal'
            if internal_mask.any():
                df = df.copy()  # Avoid SettingWithCopyWarning
                df.loc[internal_mask, 'sales_by_kpi_center_usd'] = 0
        
        return df
    
    def _filter_targets(
        self,
        year: int,
        kpi_center_ids: List[int],
        kpi_type: str
    ) -> pd.DataFrame:
        """
        Filter targets_raw_df by year, KPI Centers, and type.
        
        Args:
            year: Target year
            kpi_center_ids: List of KPI Center IDs
            kpi_type: KPI type filter
            
        Returns:
            Filtered targets DataFrame
        """
        if self.targets_raw.empty:
            return pd.DataFrame()
        
        df = self.targets_raw.copy()
        
        # Year filter
        df = df[df['year'] == year]
        
        # KPI Center filter
        if kpi_center_ids:
            df = df[df['kpi_center_id'].isin(kpi_center_ids)]
        
        # KPI Type filter (targets use kpi_center_type column)
        if kpi_type:
            df = df[df['kpi_center_type'] == kpi_type]
        
        return df
    
    def _extract_previous_year(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int],
        entity_ids: List[int],
        kpi_type: str,
        exclude_internal: bool
    ) -> pd.DataFrame:
        """
        Extract previous year data from sales_raw.
        
        This replaces the separate SQL query for previous year data.
        Simply filters sales_raw for the same period in previous year.
        
        Args:
            start_date: Current period start
            end_date: Current period end
            kpi_center_ids: KPI Center filter
            entity_ids: Entity filter
            kpi_type: KPI type filter
            exclude_internal: Exclude internal revenue
            
        Returns:
            Previous year sales DataFrame
        """
        # Calculate previous year dates
        try:
            prev_start = date(start_date.year - 1, start_date.month, start_date.day)
        except ValueError:  # Feb 29 handling
            prev_start = date(start_date.year - 1, start_date.month, 28)
        
        try:
            prev_end = date(end_date.year - 1, end_date.month, end_date.day)
        except ValueError:  # Feb 29 handling
            prev_end = date(end_date.year - 1, end_date.month, 28)
        
        # Reuse _filter_sales with previous year dates
        return self._filter_sales(
            start_date=prev_start,
            end_date=prev_end,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids,
            kpi_type=kpi_type,
            exclude_internal=exclude_internal
        )
    
    def _process_backlog(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int],
        entity_ids: List[int],
        kpi_type: str,
        exclude_internal: bool
    ) -> Dict:
        """
        Process backlog data using BacklogCalculator.
        
        First filters backlog_raw_df, then uses BacklogCalculator
        for aggregations and risk analysis.
        
        Args:
            start_date: Period start (for in-period calculation)
            end_date: Period end (for in-period calculation)
            kpi_center_ids: KPI Center filter
            entity_ids: Entity filter
            kpi_type: KPI type filter
            exclude_internal: Exclude internal revenue
            
        Returns:
            Dict with backlog DataFrames:
            - backlog_summary_df
            - backlog_in_period_df
            - backlog_by_month_df
            - backlog_detail_df
            - backlog_risk
        """
        empty_result = {
            'backlog_summary_df': pd.DataFrame(),
            'backlog_in_period_df': pd.DataFrame(),
            'backlog_by_month_df': pd.DataFrame(),
            'backlog_detail_df': pd.DataFrame(),
            'backlog_risk': {},
        }
        
        if self.backlog_raw.empty:
            return empty_result
        
        # Filter backlog_raw
        df = self.backlog_raw.copy()
        
        # KPI Center filter
        if kpi_center_ids:
            df = df[df['kpi_center_id'].isin(kpi_center_ids)]
        
        # Entity filter
        if entity_ids:
            df = df[df['legal_entity_id'].isin(entity_ids)]
        
        # KPI Type filter
        if kpi_type:
            df = df[df['kpi_type'] == kpi_type]
        
        if df.empty:
            return empty_result
        
        # Use BacklogCalculator for aggregations
        calculator = BacklogCalculator(df, exclude_internal=exclude_internal)
        results = calculator.calculate_all(start_date, end_date)
        
        return results
    
    def _calculate_complex_kpis(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int],
        entity_ids: List[int],
        exclude_internal: bool
    ) -> Dict:
        """
        Calculate complex KPIs using ComplexKPICalculator.
        
        Complex KPIs include:
        - New Customers (first sale in period)
        - New Products (first sale in period)
        - New Business (new customer+product combos)
        
        Args:
            start_date: Period start
            end_date: Period end
            kpi_center_ids: KPI Center filter
            entity_ids: Entity filter
            exclude_internal: Exclude internal customers
            
        Returns:
            Dict with complex KPI DataFrames
        """
        empty_result = {
            'new_customers_df': pd.DataFrame(),
            'new_customers_detail_df': pd.DataFrame(),
            'new_products_df': pd.DataFrame(),
            'new_products_detail_df': pd.DataFrame(),
            'new_business_df': pd.DataFrame(),
            'new_business_detail_df': pd.DataFrame(),
            '_complex_kpi_calculator': None,
        }
        
        if self.sales_raw.empty:
            return empty_result
        
        # Create or reuse calculator
        # Note: Calculator is initialized with ALL sales_raw data
        # because it needs lookback history to determine "new"
        # FIX v4.1.0: Track exclude_internal to invalidate cache when it changes
        cache_key = f"exclude_internal_{exclude_internal}"
        if (self._complex_kpi_calculator is None or 
            getattr(self, '_complex_kpi_cache_key', None) != cache_key):
            self._complex_kpi_calculator = ComplexKPICalculator(
                self.sales_raw,
                exclude_internal=exclude_internal
            )
            self._complex_kpi_cache_key = cache_key
        
        calculator = self._complex_kpi_calculator
        
        # Calculate all complex KPIs
        results = calculator.calculate_all(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        # Map to expected keys
        # DEBUG v4.6.1: Track what's being returned
        print(f"   🔍 [DEBUG data_processor] num_new_customers = {results.get('num_new_customers', 'NOT_FOUND')}")
        print(f"   🔍 [DEBUG data_processor] num_new_products = {results.get('num_new_products', 'NOT_FOUND')}")
        print(f"   🔍 [DEBUG data_processor] num_new_combos = {results.get('num_new_combos', 'NOT_FOUND')}")
        
        return {
            'new_customers_df': results.get('new_customers', pd.DataFrame()),
            'new_customers_detail_df': results.get('new_customers_detail', pd.DataFrame()),
            'new_products_df': results.get('new_products', pd.DataFrame()),
            'new_products_detail_df': results.get('new_products_detail', pd.DataFrame()),
            'new_business_df': results.get('new_business', pd.DataFrame()),
            'new_business_detail_df': results.get('new_business_detail', pd.DataFrame()),
            'new_combos_detail_df': results.get('new_combos_detail', pd.DataFrame()),  # NEW v5.3.2: Deduplicated
            '_complex_kpi_calculator': calculator,
            # v4.5.0: Propagate *_by_center to avoid duplicate calculation in main page
            'new_customers_by_center_df': results.get('new_customers_by_center', pd.DataFrame()),
            'new_products_by_center_df': results.get('new_products_by_center', pd.DataFrame()),
            'new_business_by_center_df': results.get('new_business_by_center', pd.DataFrame()),
            # NEW v4.7.0: New combos by center
            'new_combos_by_center_df': results.get('new_combos_by_center', pd.DataFrame()),
            # v4.6.1: Propagate pre-calculated weighted counts (single source of truth)
            'num_new_customers': results.get('num_new_customers', 0),
            'num_new_products': results.get('num_new_products', 0),
            'num_new_combos': results.get('num_new_combos', 0),  # NEW v4.7.0
            'new_business_revenue': results.get('new_business_revenue', 0),
        }
    
    # =========================================================================
    # ADDITIONAL PROCESSING METHODS
    # =========================================================================
    
    def get_entities_by_kpi_type(self, kpi_type: str = None) -> pd.DataFrame:
        """
        Get entities that have sales for a specific KPI type.
        
        Args:
            kpi_type: KPI type to filter by
            
        Returns:
            DataFrame with entity_id, entity_name
        """
        if self.sales_raw.empty:
            return pd.DataFrame(columns=['entity_id', 'entity_name'])
        
        df = self.sales_raw
        
        if kpi_type:
            df = df[df['kpi_type'] == kpi_type]
        
        if df.empty:
            return pd.DataFrame(columns=['entity_id', 'entity_name'])
        
        entities = df.groupby(['legal_entity_id', 'legal_entity']).size().reset_index(name='_count')
        entities = entities.rename(columns={
            'legal_entity_id': 'entity_id',
            'legal_entity': 'entity_name'
        })[['entity_id', 'entity_name']].drop_duplicates()
        
        return entities.sort_values('entity_name').reset_index(drop=True)
    
    def prepare_monthly_summary(self, sales_df: pd.DataFrame = None) -> pd.DataFrame:
        """
        Prepare monthly summary from sales data.
        
        Args:
            sales_df: Filtered sales DataFrame (if None, uses full sales_raw)
            
        Returns:
            Monthly summary DataFrame with columns:
            - month, revenue, gross_profit, gp1, orders, customers, gp_percent
        """
        df = sales_df if sales_df is not None else self.sales_raw
        
        if df.empty:
            return pd.DataFrame()
        
        # Ensure invoice_month exists
        if 'invoice_month' not in df.columns:
            if 'inv_date' not in df.columns:
                return pd.DataFrame()
            df = df.copy()
            df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
            df['invoice_month'] = df['inv_date'].dt.strftime('%b')
        
        # Aggregate by month
        monthly = df.groupby('invoice_month').agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum',
            'oc_number': pd.Series.nunique,
            'customer_id': pd.Series.nunique
        }).reset_index()
        
        monthly.columns = ['month', 'revenue', 'gross_profit', 'gp1', 'orders', 'customers']
        
        # Add GP%
        monthly['gp_percent'] = (
            monthly['gross_profit'] / monthly['revenue'] * 100
        ).fillna(0).round(1)
        
        # Sort by month order
        month_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        monthly['month_order'] = monthly['month'].map(
            {m: i for i, m in enumerate(month_order)}
        )
        monthly = monthly.sort_values('month_order').drop(columns=['month_order'])
        
        return monthly.reset_index(drop=True)
    
    def aggregate_by_kpi_center(self, sales_df: pd.DataFrame = None) -> pd.DataFrame:
        """
        Aggregate sales data by KPI Center.
        
        Args:
            sales_df: Filtered sales DataFrame
            
        Returns:
            Summary DataFrame with columns:
            - kpi_center_id, kpi_center, kpi_type
            - revenue, gross_profit, gp1, orders, customers
            - gp_percent
        """
        df = sales_df if sales_df is not None else self.sales_raw
        
        if df.empty:
            return pd.DataFrame()
        
        summary = df.groupby(['kpi_center_id', 'kpi_center', 'kpi_type']).agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum',
            'oc_number': pd.Series.nunique,
            'customer_id': pd.Series.nunique
        }).reset_index()
        
        summary.columns = [
            'kpi_center_id', 'kpi_center', 'kpi_type',
            'revenue', 'gross_profit', 'gp1', 'orders', 'customers'
        ]
        
        # Add GP%
        summary['gp_percent'] = (
            summary['gross_profit'] / summary['revenue'] * 100
        ).fillna(0).round(1)
        
        return summary.sort_values('revenue', ascending=False).reset_index(drop=True)
    
    def calculate_yoy_growth(
        self,
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        column: str
    ) -> Optional[float]:
        """
        Calculate Year-over-Year growth percentage.
        
        Args:
            current_df: Current period DataFrame
            previous_df: Previous year DataFrame
            column: Column to compare
            
        Returns:
            YoY growth percentage or None
        """
        if current_df.empty and previous_df.empty:
            return None
        
        current = current_df[column].sum() if not current_df.empty and column in current_df.columns else 0
        previous = previous_df[column].sum() if not previous_df.empty and column in previous_df.columns else 0
        
        if previous == 0:
            return None if current == 0 else 100.0
        
        return ((current - previous) / previous) * 100