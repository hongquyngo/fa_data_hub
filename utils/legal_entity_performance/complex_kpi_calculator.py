# utils/legal_entity_performance/complex_kpi_calculator.py
"""
Complex KPI Calculator for Legal Entity Performance.
Adapted from kpi_center_performance/complex_kpi_calculator.py

Differences from KPC version:
- No kpi_center_id / split_rate_percent (LE has no split concept)
- Column mapping: calculated_invoiced_amount_usd instead of sales_by_kpi_center_usd
- Groups by legal_entity_id instead of kpi_center_id
- Counts are direct (1 per item) not weighted by split %

VERSION: 1.0.0
"""

import pandas as pd
import numpy as np
from datetime import date
from typing import List, Optional, Dict, Any
import time
import logging

from .constants import DEBUG_TIMING

logger = logging.getLogger(__name__)


class ComplexKPICalculator:
    """
    Calculate Complex KPIs (New Customers/Products/Combos/Business Revenue)
    using Pandas on the lookback sales data.
    
    Pre-calculates "first dates" on initialization for instant subsequent calls.
    """
    
    def __init__(self, lookback_df: pd.DataFrame, exclude_internal: bool = True):
        """
        Initialize with lookback data and pre-calculate first dates.
        
        Args:
            lookback_df: Sales data from unified data loader (N years)
            exclude_internal: If True, exclude Internal customers
        """
        start_time = time.perf_counter()
        
        self._df = lookback_df.copy() if not lookback_df.empty else pd.DataFrame()
        self._exclude_internal = exclude_internal
        
        if self._df.empty:
            self._first_customer_dates = pd.Series(dtype='datetime64[ns]')
            self._first_product_dates = pd.Series(dtype='datetime64[ns]')
            self._first_combo_dates = pd.Series(dtype='datetime64[ns]')
            return
        
        # Filter internal customers if requested
        if exclude_internal and 'customer_type' in self._df.columns:
            before_count = len(self._df)
            self._df = self._df[
                self._df['customer_type'].str.lower() != 'internal'
            ]
            if DEBUG_TIMING:
                print(f"   📊 [LE preprocess] Filtered internal: {before_count:,} → {len(self._df):,} rows")
        
        # Create unified product key
        if 'product_id' in self._df.columns:
            self._df['product_key'] = self._df['product_id'].apply(
                lambda x: str(int(x)) if pd.notna(x) else None
            )
        else:
            self._df['product_key'] = None
        
        # Create combo key (customer + product)
        self._df['combo_key'] = (
            self._df['customer_id'].astype(str) + '_' +
            self._df['product_key'].fillna('')
        )
        
        # Pre-calculate first dates
        self._precalculate_first_dates()
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [LE preprocess] Completed in {elapsed:.3f}s → {len(self._df):,} rows")
    
    def _precalculate_first_dates(self):
        """Pre-calculate first occurrence dates for customers, products, and combos."""
        if self._df.empty:
            self._first_customer_dates = pd.Series(dtype='datetime64[ns]')
            self._first_product_dates = pd.Series(dtype='datetime64[ns]')
            self._first_combo_dates = pd.Series(dtype='datetime64[ns]')
            return
        
        if not pd.api.types.is_datetime64_any_dtype(self._df['inv_date']):
            self._df['inv_date'] = pd.to_datetime(self._df['inv_date'])
        
        # Global first dates (across ALL legal entities)
        self._first_customer_dates = self._df.groupby('customer_id')['inv_date'].min()
        self._first_product_dates = self._df.groupby('product_key')['inv_date'].min()
        self._first_combo_dates = self._df.groupby('combo_key')['inv_date'].min()
        
        if DEBUG_TIMING:
            print(f"   📊 [LE precalculate] customers={len(self._first_customer_dates):,}, "
                  f"products={len(self._first_product_dates):,}, "
                  f"combos={len(self._first_combo_dates):,}")
    
    # =========================================================================
    # NEW CUSTOMERS
    # =========================================================================
    
    def calculate_new_customers(
        self,
        start_date: date,
        end_date: date,
        entity_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        New customers: customers whose FIRST invoice falls in period.
        
        Returns DataFrame with:
        - legal_entity_id, legal_entity
        - customer_id, customer, customer_code
        - first_sale_date
        """
        if self._df.empty:
            return pd.DataFrame()
        
        start_dt, end_dt = pd.Timestamp(start_date), pd.Timestamp(end_date)
        
        mask = (self._first_customer_dates >= start_dt) & (self._first_customer_dates <= end_dt)
        new_ids = self._first_customer_dates[mask].index.tolist()
        
        if not new_ids:
            return pd.DataFrame()
        
        result = self._df[
            (self._df['customer_id'].isin(new_ids)) &
            (self._df['inv_date'] == self._df['customer_id'].map(self._first_customer_dates))
        ].copy()
        
        if entity_ids:
            result = result[result['legal_entity_id'].isin(entity_ids)]
        
        # Deduplicate: one row per customer per legal entity
        dedup_cols = ['legal_entity_id', 'customer_id'] if 'legal_entity_id' in result.columns else ['customer_id']
        result = result.drop_duplicates(subset=dedup_cols)
        result['first_sale_date'] = result['customer_id'].map(self._first_customer_dates)
        
        return result
    
    # =========================================================================
    # NEW PRODUCTS
    # =========================================================================
    
    def calculate_new_products(
        self,
        start_date: date,
        end_date: date,
        entity_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        New products: products whose FIRST sale falls in period.
        
        Returns DataFrame with:
        - legal_entity_id, legal_entity
        - product_id, product_pn, brand
        - first_sale_date
        """
        if self._df.empty:
            return pd.DataFrame()
        
        start_dt, end_dt = pd.Timestamp(start_date), pd.Timestamp(end_date)
        
        mask = (self._first_product_dates >= start_dt) & (self._first_product_dates <= end_dt)
        new_keys = self._first_product_dates[mask].index.tolist()
        
        if not new_keys:
            return pd.DataFrame()
        
        result = self._df[
            (self._df['product_key'].isin(new_keys)) &
            (self._df['inv_date'] == self._df['product_key'].map(self._first_product_dates))
        ].copy()
        
        if entity_ids:
            result = result[result['legal_entity_id'].isin(entity_ids)]
        
        dedup_cols = ['legal_entity_id', 'product_key'] if 'legal_entity_id' in result.columns else ['product_key']
        result = result.drop_duplicates(subset=dedup_cols)
        result['first_sale_date'] = result['product_key'].map(self._first_product_dates)
        
        return result
    
    # =========================================================================
    # NEW BUSINESS (customer-product combos)
    # =========================================================================
    
    def calculate_new_business(
        self,
        start_date: date,
        end_date: date,
        entity_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        New business: revenue from new customer-product combinations.
        A combo is "new" if its FIRST invoice falls in the period.
        
        Returns ALL invoices in period for these new combos.
        """
        if self._df.empty:
            return pd.DataFrame()
        
        start_dt, end_dt = pd.Timestamp(start_date), pd.Timestamp(end_date)
        
        mask = (self._first_combo_dates >= start_dt) & (self._first_combo_dates <= end_dt)
        new_combo_keys = self._first_combo_dates[mask].index.tolist()
        
        if not new_combo_keys:
            return pd.DataFrame()
        
        result = self._df[
            (self._df['combo_key'].isin(new_combo_keys)) &
            (self._df['inv_date'] >= start_dt) &
            (self._df['inv_date'] <= end_dt)
        ].copy()
        
        if entity_ids:
            result = result[result['legal_entity_id'].isin(entity_ids)]
        
        result['first_combo_date'] = result['combo_key'].map(self._first_combo_dates)
        
        return result
    
    # =========================================================================
    # COMBINED CALCULATION
    # =========================================================================
    
    def calculate_all(
        self,
        start_date: date,
        end_date: date,
        entity_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Calculate all complex KPIs at once.
        
        Returns dict with:
        - new_customers_df, num_new_customers
        - new_products_df, num_new_products
        - new_business_detail_df, new_combos_detail_df, num_new_combos
        - new_business_revenue
        """
        start_time = time.perf_counter()
        
        new_customers_df = self.calculate_new_customers(start_date, end_date, entity_ids)
        new_products_df = self.calculate_new_products(start_date, end_date, entity_ids)
        new_business_detail_df = self.calculate_new_business(start_date, end_date, entity_ids)
        
        # Counts (direct count, no split weighting for LE)
        num_new_customers = new_customers_df['customer_id'].nunique() if not new_customers_df.empty else 0
        num_new_products = new_products_df['product_key'].nunique() if not new_products_df.empty and 'product_key' in new_products_df.columns else 0
        
        # New combos count (unique customer-product pairs)
        if not new_business_detail_df.empty and 'combo_key' in new_business_detail_df.columns:
            num_new_combos = new_business_detail_df['combo_key'].nunique()
        else:
            num_new_combos = 0
        
        # Deduplicated combos for display
        new_combos_detail_df = pd.DataFrame()
        if not new_business_detail_df.empty and 'combo_key' in new_business_detail_df.columns:
            agg_dict = {}
            for col in ['calculated_invoiced_amount_usd', 'invoiced_gross_profit_usd', 'invoiced_gp1_usd']:
                if col in new_business_detail_df.columns:
                    agg_dict[col] = 'sum'
            for col in ['customer_id', 'customer', 'customer_code', 'product_id', 'product_pn',
                        'brand', 'legal_entity_id', 'legal_entity', 'first_combo_date']:
                if col in new_business_detail_df.columns:
                    agg_dict[col] = 'first'
            if agg_dict:
                new_combos_detail_df = new_business_detail_df.groupby('combo_key', as_index=False).agg(agg_dict)
        
        # Total new business revenue
        rev_col = 'calculated_invoiced_amount_usd'
        if not new_business_detail_df.empty and rev_col in new_business_detail_df.columns:
            new_business_revenue = new_business_detail_df[rev_col].sum()
        else:
            new_business_revenue = 0
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [LE calculate_all] {elapsed:.3f}s")
            print(f"      → New Customers: {num_new_customers}")
            print(f"      → New Products: {num_new_products}")
            print(f"      → New Combos: {num_new_combos}")
            print(f"      → New Business Revenue: ${new_business_revenue:,.0f}")
        
        return {
            'new_customers_df': new_customers_df,
            'new_products_df': new_products_df,
            'new_business_detail_df': new_business_detail_df,
            'new_combos_detail_df': new_combos_detail_df,
            'num_new_customers': num_new_customers,
            'num_new_products': num_new_products,
            'num_new_combos': num_new_combos,
            'new_business_revenue': new_business_revenue,
        }