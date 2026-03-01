# utils/kpi_center_performance/complex_kpi_calculator.py
"""
Complex KPI Calculator - Pandas-based calculations for KPI Center Performance

"""

import pandas as pd
import numpy as np
from datetime import date
from typing import List, Optional, Dict, Any, Tuple
import time
import logging

from .constants import DEBUG_TIMING

logger = logging.getLogger(__name__)


class ComplexKPICalculator:
    """
    Calculate Complex KPIs using Pandas instead of SQL CTEs.
    
    The key optimization is pre-calculating "first dates" on initialization,
    so that subsequent calls to calculate_* methods are instant.
    
    Attributes:
        _df: The lookback sales data
        _first_customer_dates: Series mapping customer_id -> first invoice date
        _first_product_dates: Series mapping product_key -> first invoice date
        _first_combo_dates: Series mapping combo_key -> first invoice date
    """
    
    def __init__(self, lookback_df: pd.DataFrame, exclude_internal: bool = True):
        """
        Initialize with lookback data and pre-calculate first dates.
        
        Args:
            lookback_df: Sales data from get_lookback_sales_data()
            exclude_internal: If True, exclude Internal customers from calculations
        """
        start_time = time.perf_counter()
        
        self._df = lookback_df.copy()
        self._exclude_internal = exclude_internal
        
        # Filter internal customers if requested
        if exclude_internal and 'customer_type' in self._df.columns:
            before_count = len(self._df)
            self._df = self._df[
                self._df['customer_type'].str.lower() != 'internal'
            ]
            if DEBUG_TIMING:
                print(f"   📊 [preprocess] Filtered internal: {before_count:,} → {len(self._df):,} rows")
        
        # Create unified product key (use product_id if available, else legacy_code)
        self._df['product_key'] = self._df.apply(
            lambda r: str(int(r['product_id'])) if pd.notna(r['product_id']) 
                      else (r['legacy_code'] if pd.notna(r['legacy_code']) else None),
            axis=1
        )
        
        # Create combo key (customer + product)
        self._df['combo_key'] = (
            self._df['customer_id'].astype(str) + '_' + 
            self._df['product_key'].fillna('')
        )
        
        # Pre-calculate first dates (ONCE - reused for all calculations)
        self._precalculate_first_dates()
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [preprocess] Completed in {elapsed:.3f}s → {len(self._df):,} rows")
        
        logger.info(f"ComplexKPICalculator initialized: {len(self._df):,} rows, exclude_internal={exclude_internal}")
    
    def _precalculate_first_dates(self):
        """Pre-calculate first occurrence dates for customers, products, and combos."""
        start_time = time.perf_counter()
        
        if self._df.empty:
            self._first_customer_dates = pd.Series(dtype='datetime64[ns]')
            self._first_product_dates = pd.Series(dtype='datetime64[ns]')
            self._first_combo_dates = pd.Series(dtype='datetime64[ns]')
            return
        
        # Ensure inv_date is datetime
        if not pd.api.types.is_datetime64_any_dtype(self._df['inv_date']):
            self._df['inv_date'] = pd.to_datetime(self._df['inv_date'])
        
        # First date per customer (across ALL KPI Centers - global first)
        self._first_customer_dates = self._df.groupby('customer_id')['inv_date'].min()
        
        # First date per product (across ALL KPI Centers - global first)
        self._first_product_dates = self._df.groupby('product_key')['inv_date'].min()
        
        # First date per combo (customer + product) - for New Business
        self._first_combo_dates = self._df.groupby('combo_key')['inv_date'].min()
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [precalculate] First dates: customers={len(self._first_customer_dates):,}, "
                  f"products={len(self._first_product_dates):,}, combos={len(self._first_combo_dates):,} "
                  f"in {elapsed:.3f}s")
    
    # =========================================================================
    # NEW CUSTOMERS
    # =========================================================================
    
    def calculate_new_customers(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: Optional[List[int]] = None,
        entity_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Calculate new customers - customers whose FIRST invoice falls in period.
        
        Returns DataFrame with columns:
        - kpi_center_id, kpi_center (renamed from kpi_center_name)
        - customer_id, customer, customer_code
        - first_sale_date (renamed from first_invoice_date for charts.py compatibility)
        - split_rate_percent (for weighted counting)
        """
        start_time = time.perf_counter()
        
        if self._df.empty:
            return pd.DataFrame()
        
        # Convert dates
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        
        # Find customers whose first date is in period
        mask = (self._first_customer_dates >= start_dt) & (self._first_customer_dates <= end_dt)
        new_customer_ids = self._first_customer_dates[mask].index.tolist()
        
        if not new_customer_ids:
            if DEBUG_TIMING:
                print(f"   📊 [new_customers] 0 rows in {time.perf_counter() - start_time:.3f}s")
            return pd.DataFrame()
        
        # Get the first invoice details for each new customer
        result = self._df[
            (self._df['customer_id'].isin(new_customer_ids)) &
            (self._df['inv_date'] == self._df['customer_id'].map(self._first_customer_dates))
        ].copy()
        
        # Apply filters
        if kpi_center_ids:
            result = result[result['kpi_center_id'].isin(kpi_center_ids)]
        if entity_ids:
            result = result[result['legal_entity_id'].isin(entity_ids)]
        
        # Deduplicate - keep one row per customer per KPI Center
        result = result.drop_duplicates(subset=['kpi_center_id', 'customer_id'])
        
        # Add first_sale_date column (renamed from first_invoice_date for compatibility)
        result['first_sale_date'] = result['customer_id'].map(self._first_customer_dates)
        
        # Rename columns to match expected schema from original SQL queries
        if 'kpi_center_name' in result.columns:
            result = result.rename(columns={'kpi_center_name': 'kpi_center'})
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [new_customers] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    def calculate_new_customers_by_kpi_center(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: Optional[List[int]] = None,
        entity_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Calculate weighted new customer count per KPI Center.
        
        Returns DataFrame with columns:
        - kpi_center_id
        - weighted_count (sum of split_rate_percent / 100)
        """
        new_customers_df = self.calculate_new_customers(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        
        if new_customers_df.empty:
            return pd.DataFrame(columns=['kpi_center_id', 'weighted_count'])
        
        # Group by KPI Center and sum split_rate_percent
        result = new_customers_df.groupby('kpi_center_id').agg(
            weighted_count=('split_rate_percent', lambda x: x.sum() / 100)
        ).reset_index()
        
        return result
    
    # =========================================================================
    # NEW PRODUCTS
    # =========================================================================
    
    def calculate_new_products(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: Optional[List[int]] = None,
        entity_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Calculate new products - products whose FIRST invoice falls in period.
        
        Returns DataFrame with columns:
        - kpi_center_id, kpi_center (renamed from kpi_center_name)
        - product_id, product_pn, brand, legacy_code
        - first_sale_date (renamed from first_invoice_date for charts.py compatibility)
        - split_rate_percent (for weighted counting)
        """
        start_time = time.perf_counter()
        
        if self._df.empty:
            return pd.DataFrame()
        
        # Convert dates
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        
        # Find products whose first date is in period
        mask = (self._first_product_dates >= start_dt) & (self._first_product_dates <= end_dt)
        new_product_keys = self._first_product_dates[mask].index.tolist()
        
        if not new_product_keys:
            if DEBUG_TIMING:
                print(f"   📊 [new_products] 0 rows in {time.perf_counter() - start_time:.3f}s")
            return pd.DataFrame()
        
        # Get the first invoice details for each new product
        result = self._df[
            (self._df['product_key'].isin(new_product_keys)) &
            (self._df['inv_date'] == self._df['product_key'].map(self._first_product_dates))
        ].copy()
        
        # Apply filters
        if kpi_center_ids:
            result = result[result['kpi_center_id'].isin(kpi_center_ids)]
        if entity_ids:
            result = result[result['legal_entity_id'].isin(entity_ids)]
        
        # Deduplicate - keep one row per product per KPI Center
        result = result.drop_duplicates(subset=['kpi_center_id', 'product_key'])
        
        # Add first_sale_date column (renamed from first_invoice_date for compatibility)
        result['first_sale_date'] = result['product_key'].map(self._first_product_dates)
        
        # Rename columns to match expected schema from original SQL queries
        if 'kpi_center_name' in result.columns:
            result = result.rename(columns={'kpi_center_name': 'kpi_center'})
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [new_products] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    def calculate_new_products_by_kpi_center(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: Optional[List[int]] = None,
        entity_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Calculate weighted new product count per KPI Center.
        
        Returns DataFrame with columns:
        - kpi_center_id
        - weighted_count (sum of split_rate_percent / 100)
        """
        new_products_df = self.calculate_new_products(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        
        if new_products_df.empty:
            return pd.DataFrame(columns=['kpi_center_id', 'weighted_count'])
        
        # Group by KPI Center and sum split_rate_percent
        result = new_products_df.groupby('kpi_center_id').agg(
            weighted_count=('split_rate_percent', lambda x: x.sum() / 100)
        ).reset_index()
        
        return result
    
    # =========================================================================
    # NEW BUSINESS REVENUE
    # =========================================================================
    
    def calculate_new_business(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: Optional[List[int]] = None,
        entity_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Calculate new business - revenue from new customer-product combinations.
        
        A combo is "new" if its FIRST invoice falls in the period.
        
        Returns DataFrame with columns:
        - kpi_center_id, kpi_center (renamed from kpi_center_name)
        - customer_id, customer
        - product_id, product_pn
        - sales_by_kpi_center_usd, gross_profit_by_kpi_center_usd
        - first_combo_date
        """
        start_time = time.perf_counter()
        
        if self._df.empty:
            return pd.DataFrame()
        
        # Convert dates
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        
        # Find combos whose first date is in period
        mask = (self._first_combo_dates >= start_dt) & (self._first_combo_dates <= end_dt)
        new_combo_keys = self._first_combo_dates[mask].index.tolist()
        
        if not new_combo_keys:
            if DEBUG_TIMING:
                print(f"   📊 [new_business] 0 rows in {time.perf_counter() - start_time:.3f}s")
            return pd.DataFrame()
        
        # Get ALL invoices in period for these new combos (not just first invoice)
        result = self._df[
            (self._df['combo_key'].isin(new_combo_keys)) &
            (self._df['inv_date'] >= start_dt) &
            (self._df['inv_date'] <= end_dt)
        ].copy()
        
        # Apply filters
        if kpi_center_ids:
            result = result[result['kpi_center_id'].isin(kpi_center_ids)]
        if entity_ids:
            result = result[result['legal_entity_id'].isin(entity_ids)]
        
        # Add first_combo_date column (for compatibility with original schema)
        result['first_combo_date'] = result['combo_key'].map(self._first_combo_dates)
        
        # Rename columns to match expected schema from original SQL queries
        if 'kpi_center_name' in result.columns:
            result = result.rename(columns={'kpi_center_name': 'kpi_center'})
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [new_business_detail] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    def calculate_new_business_revenue(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: Optional[List[int]] = None,
        entity_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Calculate total new business revenue.
        
        Returns DataFrame with columns:
        - new_business_revenue (total)
        """
        start_time = time.perf_counter()
        
        new_business_df = self.calculate_new_business(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        
        if new_business_df.empty:
            result = pd.DataFrame({'new_business_revenue': [0]})
        else:
            # Sum revenue (use the split amount column)
            revenue_col = 'sales_by_kpi_center_usd' if 'sales_by_kpi_center_usd' in new_business_df.columns else 'sales_by_split_usd'
            total_revenue = new_business_df[revenue_col].sum() if revenue_col in new_business_df.columns else 0
            result = pd.DataFrame({'new_business_revenue': [total_revenue]})
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [new_business_revenue] ${result['new_business_revenue'].iloc[0]:,.0f} in {elapsed:.3f}s")
        
        return result
    
    def calculate_new_business_by_kpi_center(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: Optional[List[int]] = None,
        entity_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Calculate new business revenue per KPI Center.
        
        Returns DataFrame with columns:
        - kpi_center_id
        - new_business_revenue
        """
        new_business_df = self.calculate_new_business(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        
        if new_business_df.empty:
            return pd.DataFrame(columns=['kpi_center_id', 'new_business_revenue'])
        
        # Sum revenue per KPI Center
        revenue_col = 'sales_by_kpi_center_usd' if 'sales_by_kpi_center_usd' in new_business_df.columns else 'sales_by_split_usd'
        result = new_business_df.groupby('kpi_center_id').agg(
            new_business_revenue=(revenue_col, 'sum')
        ).reset_index()
        
        return result
    
    # =========================================================================
    # COMBINED CALCULATION
    # =========================================================================
    
    def calculate_all(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: Optional[List[int]] = None,
        entity_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Calculate all complex KPIs at once.
        
        Returns dict with:
        - new_customers: DataFrame of new customers
        - new_customers_detail: Same as new_customers (for detail view)
        - new_products: DataFrame of new products
        - new_products_detail: Same as new_products (for detail view)
        - new_business: DataFrame with total new business revenue
        - new_business_detail: DataFrame of new business line items
        - by_kpi_center: Dict with per-center aggregations
        """
        start_time = time.perf_counter()
        
        new_customers_df = self.calculate_new_customers(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        new_products_df = self.calculate_new_products(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        new_business_df = self.calculate_new_business_revenue(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        new_business_detail_df = self.calculate_new_business(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        
        # Per KPI Center aggregations
        new_customers_by_center = self.calculate_new_customers_by_kpi_center(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        new_products_by_center = self.calculate_new_products_by_kpi_center(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        new_business_by_center = self.calculate_new_business_by_kpi_center(
            start_date, end_date, kpi_center_ids, entity_ids
        )
        
        # Calculate weighted counts
        num_new_customers = new_customers_df['split_rate_percent'].sum() / 100 if not new_customers_df.empty and 'split_rate_percent' in new_customers_df.columns else 0
        num_new_products = new_products_df['split_rate_percent'].sum() / 100 if not new_products_df.empty and 'split_rate_percent' in new_products_df.columns else 0
        
        # NEW v4.7.0: Calculate num_new_combos (distinct customer-product pairs)
        if not new_business_detail_df.empty and 'combo_key' in new_business_detail_df.columns:
            num_new_combos = new_business_detail_df['combo_key'].nunique()
        elif not new_business_detail_df.empty and 'customer_id' in new_business_detail_df.columns and 'product_key' in new_business_detail_df.columns:
            num_new_combos = new_business_detail_df.groupby(['customer_id', 'product_key']).ngroups
        else:
            num_new_combos = 0
        
        # NEW v5.3.2: Create new_combos_detail_df with UNIQUE combos (deduplicated)
        # This is for display purposes - each combo should appear only once
        if not new_business_detail_df.empty and 'combo_key' in new_business_detail_df.columns:
            # Group by combo_key and aggregate
            agg_dict = {}
            
            # Revenue columns - sum
            for col in ['sales_by_kpi_center_usd', 'gross_profit_by_kpi_center_usd', 'gp1_by_kpi_center_usd']:
                if col in new_business_detail_df.columns:
                    agg_dict[col] = 'sum'
            
            # First occurrence columns - first
            for col in ['customer_id', 'customer', 'customer_code', 'product_id', 'product_pn', 
                        'pt_code', 'brand', 'kpi_center_id', 'kpi_center', 'first_combo_date',
                        'legal_entity_id', 'legal_entity']:
                if col in new_business_detail_df.columns:
                    agg_dict[col] = 'first'
            
            if agg_dict:
                new_combos_detail_df = new_business_detail_df.groupby('combo_key', as_index=False).agg(agg_dict)
                # Add combo_key back as column if needed
                if 'combo_key' not in new_combos_detail_df.columns:
                    new_combos_detail_df = new_business_detail_df.groupby('combo_key').agg(agg_dict).reset_index()
            else:
                # Fallback: just dedupe on combo_key, keep first row
                new_combos_detail_df = new_business_detail_df.drop_duplicates(subset=['combo_key'], keep='first').copy()
        else:
            new_combos_detail_df = pd.DataFrame()
        
        if DEBUG_TIMING:
            print(f"   📊 [new_combos_detail] Created {len(new_combos_detail_df):,} unique combos from {len(new_business_detail_df):,} rows")
        
        # NEW v4.7.0: Calculate new_combos_by_center
        if not new_business_detail_df.empty and 'kpi_center_id' in new_business_detail_df.columns:
            new_combos_by_center = new_business_detail_df.groupby('kpi_center_id').agg(
                combo_count=('combo_key', 'nunique') if 'combo_key' in new_business_detail_df.columns 
                           else ('customer_id', 'count')
            ).reset_index()
        else:
            new_combos_by_center = pd.DataFrame(columns=['kpi_center_id', 'combo_count'])
        
        # DEBUG v4.6.1: Track weighted counts
        print(f"   🔍 [DEBUG complex_kpi_calculator] num_new_customers = {num_new_customers:.2f}")
        print(f"   🔍 [DEBUG complex_kpi_calculator] num_new_products = {num_new_products:.2f}")
        print(f"   🔍 [DEBUG complex_kpi_calculator] num_new_combos = {num_new_combos}")
        if not new_customers_df.empty and 'split_rate_percent' in new_customers_df.columns:
            null_count = new_customers_df['split_rate_percent'].isna().sum()
            print(f"   🔍 [DEBUG] new_customers_df: {len(new_customers_df)} rows, {null_count} NULL split_rate")
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [calculate_all] Total: {elapsed:.3f}s")
            print(f"      → New Customers: {num_new_customers:.0f}")
            print(f"      → New Products: {num_new_products:.0f}")
            print(f"      → New Combos: {num_new_combos:,}")
            print(f"      → New Business Revenue: ${new_business_df['new_business_revenue'].iloc[0]:,.0f}" if not new_business_df.empty else "      → New Business Revenue: $0")
        
        return {
            'new_customers': new_customers_df,
            'new_customers_detail': new_customers_df,  # Alias for compatibility
            'new_products': new_products_df,
            'new_products_detail': new_products_df,  # Alias for compatibility
            'new_business': new_business_df,
            'new_business_detail': new_business_detail_df,
            'new_combos_detail': new_combos_detail_df,  # NEW v5.3.2: Deduplicated combos for display
            'new_customers_by_center': new_customers_by_center,
            'new_products_by_center': new_products_by_center,
            'new_business_by_center': new_business_by_center,
            # NEW v4.7.0: New combos by center
            'new_combos_by_center': new_combos_by_center,
            # Summary counts
            'num_new_customers': num_new_customers,
            'num_new_products': num_new_products,
            'num_new_combos': num_new_combos,  # NEW v4.7.0
            'new_business_revenue': new_business_df['new_business_revenue'].iloc[0] if not new_business_df.empty else 0,
        }