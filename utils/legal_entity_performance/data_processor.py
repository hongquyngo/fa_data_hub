# utils/legal_entity_performance/data_processor.py
"""
Data Processor for Legal Entity Performance
Aligned with kpi_center_performance/data_processor.py

VERSION: 2.0.0
- Same "Filter Many" pattern as KPI center
- _prepare_dataframes for pre-conversion
- _get_backlog_period_end for correct ETD boundary
- All Pandas-based, no SQL
"""

import logging
import time
import calendar
from datetime import date
from typing import Dict, Optional
import pandas as pd
import numpy as np
import streamlit as st

from .constants import DEBUG_TIMING, LOOKBACK_YEARS

logger = logging.getLogger(__name__)


class DataProcessor:
    """
    Process cached raw data based on filter values.
    All operations are Pandas-based for instant response.
    
    Usage:
        processor = DataProcessor(unified_cache)
        processed_data = processor.process(filter_values)
    """
    
    def __init__(self, unified_cache: Dict):
        self.sales_raw = unified_cache.get('sales_raw_df', pd.DataFrame())
        self.backlog_raw = unified_cache.get('backlog_raw_df', pd.DataFrame())
        self._lookback_start = unified_cache.get('_lookback_start')
        
        # Pre-convert date columns
        self._prepare_dataframes()
    
    def _prepare_dataframes(self):
        """Pre-convert date columns to datetime for faster filtering."""
        if not self.sales_raw.empty and 'inv_date' in self.sales_raw.columns:
            if not pd.api.types.is_datetime64_any_dtype(self.sales_raw['inv_date']):
                self.sales_raw['inv_date'] = pd.to_datetime(self.sales_raw['inv_date'], errors='coerce')
        
        if not self.backlog_raw.empty and 'etd' in self.backlog_raw.columns:
            if not pd.api.types.is_datetime64_any_dtype(self.backlog_raw['etd']):
                self.backlog_raw['etd'] = pd.to_datetime(self.backlog_raw['etd'], errors='coerce')
        
        if not self.backlog_raw.empty and 'oc_date' in self.backlog_raw.columns:
            if not pd.api.types.is_datetime64_any_dtype(self.backlog_raw['oc_date']):
                self.backlog_raw['oc_date'] = pd.to_datetime(self.backlog_raw['oc_date'], errors='coerce')
    
    def _get_backlog_period_end(
        self,
        period_type: str,
        year: int,
        start_date: date,
        end_date: date
    ) -> date:
        """
        Calculate the correct end date for In-Period Backlog ETD filter.
        
        Synced with KPI center v4.0.1:
        - YTD: Jan 1 → Dec 31 (full year)
        - QTD: Quarter start → Quarter end
        - MTD: Month start → Month end
        - LY:  Jan 1 → Dec 31 of previous year
        - Custom: Use filter dates as-is
        """
        if period_type == 'YTD':
            return date(year, 12, 31)
        elif period_type == 'QTD':
            quarter = (start_date.month - 1) // 3 + 1
            quarter_end_month = quarter * 3
            last_day = calendar.monthrange(year, quarter_end_month)[1]
            return date(year, quarter_end_month, last_day)
        elif period_type == 'MTD':
            last_day = calendar.monthrange(year, start_date.month)[1]
            return date(year, start_date.month, last_day)
        elif period_type == 'LY':
            return date(year, 12, 31)
        else:
            return end_date
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    def process(self, filter_values: Dict) -> Dict:
        """
        Process all data based on filter values.
        
        Args:
            filter_values: Dict containing:
                - start_date, end_date, year, period_type
                - entity_ids: Selected legal entities
                - customer_type: Internal/External/All
                - customer_ids, product_ids, brand_filter
                - show_yoy: Boolean
                
        Returns:
            Dict containing all processed DataFrames
        """
        start_time = time.perf_counter()
        
        if DEBUG_TIMING:
            print(f"\n{'='*60}")
            print(f"🔄 PROCESSING DATA (Legal Entity, Pandas only)")
            print(f"{'='*60}")
        
        result = {}
        
        # Extract filter values
        start_date = filter_values.get('start_date', date.today())
        end_date = filter_values.get('end_date', date.today())
        year = filter_values.get('year', date.today().year)
        period_type = filter_values.get('period_type', 'YTD')
        entity_ids = filter_values.get('entity_ids', [])
        customer_type = filter_values.get('customer_type', 'All')
        show_yoy = filter_values.get('show_yoy', True)
        
        # Calculate backlog period end
        backlog_period_end = self._get_backlog_period_end(
            period_type, year, start_date, end_date
        )
        if DEBUG_TIMING:
            print(f"   📅 [backlog_period] {period_type}: {start_date} → {backlog_period_end} (ETD filter)")
        
        # =====================================================================
        # 1. SALES DATA - Current period
        # =====================================================================
        with_timer = time.perf_counter()
        sales_df = self._filter_sales(self.sales_raw, start_date, end_date, filter_values)
        result['sales_df'] = sales_df
        if DEBUG_TIMING:
            print(f"   📊 [filter_sales] {len(sales_df):,} rows in {time.perf_counter()-with_timer:.3f}s")
        
        # =====================================================================
        # 2. SALES DATA - Previous year (for YoY)
        # =====================================================================
        prev_sales_df = pd.DataFrame()
        if show_yoy:
            with_timer = time.perf_counter()
            prev_filters = self._build_prev_year_filters(filter_values)
            if prev_filters:
                prev_sales_df = self._filter_sales(
                    self.sales_raw,
                    prev_filters['start_date'],
                    prev_filters['end_date'],
                    prev_filters
                )
            result['prev_sales_df'] = prev_sales_df
            if DEBUG_TIMING:
                print(f"   📊 [filter_prev_sales] {len(prev_sales_df):,} rows in {time.perf_counter()-with_timer:.3f}s")
        else:
            result['prev_sales_df'] = pd.DataFrame()
        
        # =====================================================================
        # 3. BACKLOG DATA
        # =====================================================================
        with_timer = time.perf_counter()
        backlog_df = self._filter_backlog(self.backlog_raw, filter_values)
        result['backlog_detail_df'] = backlog_df
        
        # In-period backlog (ETD within period boundary)
        backlog_in_period_df = self._filter_backlog_in_period(
            backlog_df, start_date, backlog_period_end
        )
        result['backlog_in_period_df'] = backlog_in_period_df
        if DEBUG_TIMING:
            print(f"   📊 [filter_backlog] {len(backlog_df):,} total, {len(backlog_in_period_df):,} in-period in {time.perf_counter()-with_timer:.3f}s")
        
        # =====================================================================
        # 4. COMPLEX KPIs (New Customers/Products/Combos/Business Revenue)
        # =====================================================================
        with_timer = time.perf_counter()
        try:
            from .complex_kpi_calculator import ComplexKPICalculator
            
            # Cache calculator instance — only re-init when data or customer_type changes
            calc_cache_key = '_le_complex_kpi_calc'
            calc_hash_key = '_le_complex_kpi_calc_hash'
            calc_hash = f"{len(self.sales_raw)}_{customer_type}"
            
            if (calc_cache_key not in st.session_state or
                    st.session_state.get(calc_hash_key) != calc_hash):
                st.session_state[calc_cache_key] = ComplexKPICalculator(
                    lookback_df=self.sales_raw,
                    exclude_internal=(customer_type == 'External')
                )
                st.session_state[calc_hash_key] = calc_hash
                if DEBUG_TIMING:
                    print(f"   📊 [complex_kpi] Created new calculator (hash={calc_hash})")
            else:
                if DEBUG_TIMING:
                    print(f"   ♻️ [complex_kpi] Reusing cached calculator")
            
            calculator = st.session_state[calc_cache_key]
            complex_kpis = calculator.calculate_all(
                start_date=start_date,
                end_date=end_date,
                entity_ids=entity_ids if entity_ids else None
            )
            result['complex_kpis'] = complex_kpis
            result['new_customers_df'] = complex_kpis.get('new_customers_df', pd.DataFrame())
            result['new_products_df'] = complex_kpis.get('new_products_df', pd.DataFrame())
            result['new_combos_detail_df'] = complex_kpis.get('new_combos_detail_df', pd.DataFrame())
            result['new_business_detail_df'] = complex_kpis.get('new_business_detail_df', pd.DataFrame())
        except Exception as e:
            logger.error(f"Complex KPI calculation failed: {e}")
            result['complex_kpis'] = {
                'num_new_customers': 0, 'num_new_products': 0,
                'num_new_combos': 0, 'new_business_revenue': 0,
            }
            result['new_customers_df'] = pd.DataFrame()
            result['new_products_df'] = pd.DataFrame()
            result['new_combos_detail_df'] = pd.DataFrame()
            result['new_business_detail_df'] = pd.DataFrame()
        if DEBUG_TIMING:
            print(f"   📊 [complex_kpis] in {time.perf_counter()-with_timer:.3f}s")
        
        total_elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"{'='*60}")
            print(f"✅ PROCESSING COMPLETE: {total_elapsed:.3f}s")
            print(f"{'='*60}\n")
        
        return result
    
    # =========================================================================
    # SALES FILTERING
    # =========================================================================
    
    def _filter_sales(self, df: pd.DataFrame, start_date: date,
                      end_date: date, filters: dict) -> pd.DataFrame:
        """Apply all filters to sales DataFrame."""
        if df.empty:
            return df
        
        result = df.copy()
        
        # Date range
        result = result[
            (result['inv_date'] >= pd.Timestamp(start_date)) &
            (result['inv_date'] <= pd.Timestamp(end_date))
        ]
        
        # Legal Entity
        entity_ids = filters.get('entity_ids', [])
        if entity_ids:
            result = result[result['legal_entity_id'].isin(entity_ids)]
        
        # Customer Type
        customer_type = filters.get('customer_type', 'All')
        if customer_type and customer_type != 'All':
            result = result[result['customer_type'] == customer_type]
        
        # Customer IDs
        customer_ids = filters.get('customer_ids', [])
        if customer_ids:
            result = result[result['customer_id'].isin(customer_ids)]
        
        # Product IDs
        product_ids = filters.get('product_ids', [])
        if product_ids:
            result = result[result['product_id'].isin(product_ids)]
        
        # Brand
        brands = filters.get('brand_filter', [])
        if brands:
            result = result[result['brand'].isin(brands)]
        
        # Data source
        data_source = filters.get('data_source', 'All')
        if data_source and data_source != 'All' and 'data_source' in result.columns:
            result = result[result['data_source'] == data_source]
        
        return result
    
    def _build_prev_year_filters(self, filters: dict) -> Optional[dict]:
        """Build filters for previous year comparison."""
        start_date = filters.get('start_date')
        end_date = filters.get('end_date')
        if not start_date or not end_date:
            return None
        
        def _safe_prev_year(d: date) -> date:
            """Shift date back one year, handling Feb 29 → Feb 28."""
            try:
                return d.replace(year=d.year - 1)
            except ValueError:
                # Only Feb 29 in a leap year triggers this
                return d.replace(year=d.year - 1, month=2, day=28)
        
        prev_filters = filters.copy()
        prev_filters['start_date'] = _safe_prev_year(start_date)
        prev_filters['end_date'] = _safe_prev_year(end_date)
        return prev_filters
    
    # =========================================================================
    # BACKLOG FILTERING
    # =========================================================================
    
    def _filter_backlog(self, df: pd.DataFrame, filters: dict) -> pd.DataFrame:
        """Apply filters to backlog DataFrame."""
        if df.empty:
            return df
        
        result = df.copy()
        
        # Legal Entity
        entity_ids = filters.get('entity_ids', [])
        if entity_ids and 'legal_entity_id' in result.columns:
            result = result[result['legal_entity_id'].isin(entity_ids)]
        
        # Customer Type
        customer_type = filters.get('customer_type', 'All')
        if customer_type and customer_type != 'All':
            result = result[result['customer_type'] == customer_type]
        
        # Customer IDs
        customer_ids = filters.get('customer_ids', [])
        if customer_ids:
            result = result[result['customer_id'].isin(customer_ids)]
        
        # Product IDs
        product_ids = filters.get('product_ids', [])
        if product_ids:
            result = result[result['product_id'].isin(product_ids)]
        
        # Brand
        brands = filters.get('brand_filter', [])
        if brands:
            result = result[result['brand'].isin(brands)]
        
        return result
    
    def _filter_backlog_in_period(self, df: pd.DataFrame,
                                  start_date: date, end_date: date) -> pd.DataFrame:
        """Filter backlog for items with ETD within period boundary."""
        if df.empty or 'etd' not in df.columns:
            return df
        
        return df[
            (df['etd'] >= pd.Timestamp(start_date)) &
            (df['etd'] <= pd.Timestamp(end_date))
        ]
    
    # =========================================================================
    # AGGREGATION HELPERS (synced column patterns with KPI center)
    # =========================================================================
    
    def prepare_monthly_summary(self, sales_df: pd.DataFrame = None) -> pd.DataFrame:
        """Aggregate sales by month."""
        df = sales_df if sales_df is not None else self.sales_raw
        if df.empty:
            return pd.DataFrame()
        
        df = df.copy()
        if 'invoice_month' not in df.columns:
            if 'inv_date' not in df.columns:
                return pd.DataFrame()
            df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
            df['invoice_month'] = df['inv_date'].dt.strftime('%b')
        
        monthly = df.groupby('invoice_month').agg(
            revenue=('calculated_invoiced_amount_usd', 'sum'),
            gross_profit=('invoiced_gross_profit_usd', 'sum'),
            gp1=('invoiced_gp1_usd', 'sum'),
            commission=('broker_commission_usd', 'sum'),
            orders=('inv_number', pd.Series.nunique),
            customers=('customer_id', pd.Series.nunique),
        ).reset_index()
        
        monthly.rename(columns={'invoice_month': 'month'}, inplace=True)
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
    
    def aggregate_by_entity(self, sales_df: pd.DataFrame = None) -> pd.DataFrame:
        """Aggregate sales by legal entity."""
        df = sales_df if sales_df is not None else self.sales_raw
        if df.empty:
            return pd.DataFrame()
        
        summary = df.groupby(['legal_entity_id', 'legal_entity']).agg(
            revenue=('calculated_invoiced_amount_usd', 'sum'),
            gross_profit=('invoiced_gross_profit_usd', 'sum'),
            gp1=('invoiced_gp1_usd', 'sum'),
            commission=('broker_commission_usd', 'sum'),
            orders=('inv_number', pd.Series.nunique),
            customers=('customer_id', pd.Series.nunique),
        ).reset_index()
        
        summary['gp_percent'] = (
            summary['gross_profit'] / summary['revenue'] * 100
        ).fillna(0).round(1)
        
        return summary.sort_values('revenue', ascending=False).reset_index(drop=True)
    
    def aggregate_by_customer(self, sales_df: pd.DataFrame,
                               top_n: int = 20) -> pd.DataFrame:
        """Aggregate sales by customer, return top N."""
        if sales_df.empty:
            return pd.DataFrame()
        
        agg = sales_df.groupby(['customer_id', 'customer', 'customer_code', 'customer_type']).agg(
            revenue=('calculated_invoiced_amount_usd', 'sum'),
            gross_profit=('invoiced_gross_profit_usd', 'sum'),
            gp1=('invoiced_gp1_usd', 'sum'),
        ).reset_index()
        
        agg['gp_percent'] = np.where(
            agg['revenue'] > 0, agg['gross_profit'] / agg['revenue'] * 100, 0
        )
        
        return agg.sort_values('revenue', ascending=False).head(top_n)
    
    def aggregate_by_product(self, sales_df: pd.DataFrame,
                              top_n: int = 20) -> pd.DataFrame:
        """Aggregate sales by product, return top N."""
        if sales_df.empty:
            return pd.DataFrame()
        
        agg = sales_df.groupby(['product_id', 'product_pn', 'brand']).agg(
            revenue=('calculated_invoiced_amount_usd', 'sum'),
            gross_profit=('invoiced_gross_profit_usd', 'sum'),
            qty=('invoiced_quantity', 'sum'),
        ).reset_index()
        
        agg['gp_percent'] = np.where(
            agg['revenue'] > 0, agg['gross_profit'] / agg['revenue'] * 100, 0
        )
        
        return agg.sort_values('revenue', ascending=False).head(top_n)
    
    def calculate_yoy_growth(self, current_df: pd.DataFrame,
                              previous_df: pd.DataFrame,
                              column: str) -> Optional[float]:
        """Calculate Year-over-Year growth percentage."""
        if current_df.empty and previous_df.empty:
            return None
        current = current_df[column].sum() if not current_df.empty and column in current_df.columns else 0
        previous = previous_df[column].sum() if not previous_df.empty and column in previous_df.columns else 0
        if previous == 0:
            return None if current == 0 else 100.0
        return ((current - previous) / previous) * 100