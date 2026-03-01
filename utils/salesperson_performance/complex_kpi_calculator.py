# utils/salesperson_performance/complex_kpi_calculator.py
"""
Pandas-based Complex KPI Calculator

Replaces expensive SQL CTEs with in-memory Pandas operations.
Loads 5-year lookback data once, caches, and calculates on demand.

Performance Comparison:
- SQL CTEs: 14.76s (4 queries with recursive CTEs)
- Pandas: ~0.3s (in-memory groupby + filter)

CHANGELOG:
- v1.2.0: EXCLUDE service products from New Products and New Combos
          - Added is_service check in _precalculate_first_dates()
          - Products with is_service=1 are excluded from New Products count
          - Combos with service products are excluded from New Combos count
          - New Customers NOT affected (counts customers, not products)
- v1.1.0: ADDED calculate_new_combos_detail() method
          - Returns deduplicated list of new customer-product combos
          - Used for New Combos metric display in Overview tab
          - Distinct from new_business_detail (which has revenue per combo)
          - Updated calculate_all() to include new_combos_detail
- v1.0.0: Initial implementation
          - calculate_new_customers(): Customers new to COMPANY in period
          - calculate_new_products(): Products first sold ever in period
          - calculate_new_business_revenue(): First customer-product combos
          - calculate_new_business_detail(): Line-by-line combo detail

VERSION: 1.2.0
"""

import logging
from datetime import date
from typing import List, Optional, Tuple
import pandas as pd
import numpy as np
import time

logger = logging.getLogger(__name__)

# Debug timing flag
DEBUG_TIMING = True


class ComplexKPICalculator:
    """
    Calculate Complex KPIs using Pandas instead of SQL CTEs.
    
    Complex KPIs:
    1. New Customers - Customers with first invoice to COMPANY in period
    2. New Products - Products with first sale ever (any customer) in period
    3. New Combos - Unique customer-product pairs with first sale in period (NEW v1.1.0)
    4. New Business Revenue - Revenue from first customer-product combos
    
    Usage:
        # Load lookback data once (cached in session_state)
        lookback_df = queries.get_lookback_sales_data()
        
        # Create calculator
        calc = ComplexKPICalculator(lookback_df, exclude_internal=True)
        
        # Calculate KPIs for specific period and employees
        new_customers = calc.calculate_new_customers(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            employee_ids=[1, 2, 3]
        )
    """
    
    def __init__(
        self, 
        lookback_df: pd.DataFrame,
        exclude_internal: bool = True
    ):
        """
        Initialize with lookback sales data.
        
        Args:
            lookback_df: Sales data from unified_sales_by_salesperson_view
                        covering 5-year lookback period
            exclude_internal: If True, exclude internal customers from calculations
        """
        self.exclude_internal = exclude_internal
        
        # Store and preprocess data
        self._raw_df = lookback_df.copy() if not lookback_df.empty else pd.DataFrame()
        self._df = self._preprocess_data(self._raw_df)
        
        # Pre-calculate first dates for performance
        self._first_customer_dates: Optional[pd.DataFrame] = None
        self._first_product_dates: Optional[pd.DataFrame] = None
        self._first_combo_dates: Optional[pd.DataFrame] = None
        
        if not self._df.empty:
            self._precalculate_first_dates()
        
        logger.info(
            f"ComplexKPICalculator initialized: {len(self._df):,} rows, "
            f"exclude_internal={exclude_internal}"
        )
    
    # =========================================================================
    # PREPROCESSING
    # =========================================================================
    
    def _preprocess_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Preprocess raw data for calculations.
        
        Steps:
        1. Filter out internal customers (if exclude_internal=True)
        2. Convert inv_date to datetime
        3. Create product_key (unified product identifier)
        4. Create combo_key (customer + product)
        """
        if df.empty:
            return df
        
        start_time = time.perf_counter()
        
        df = df.copy()
        
        # 1. Filter internal customers
        if self.exclude_internal and 'customer_type' in df.columns:
            before = len(df)
            df = df[df['customer_type'].str.lower() != 'internal']
            after = len(df)
            if DEBUG_TIMING:
                print(f"   📊 [preprocess] Filtered internal: {before:,} → {after:,} rows")
        
        # 2. Convert inv_date to datetime
        if 'inv_date' in df.columns:
            df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
            # Remove rows with invalid dates
            df = df[df['inv_date'].notna()]
        
        # 3. Create product_key (prefer product_id, fallback to legacy_code)
        # This matches the SQL logic: COALESCE(CAST(product_id AS CHAR), legacy_code)
        if 'product_id' in df.columns and 'legacy_code' in df.columns:
            df['product_key'] = df.apply(
                lambda row: str(int(row['product_id'])) if pd.notna(row['product_id']) 
                           else (str(row['legacy_code']) if pd.notna(row['legacy_code']) else None),
                axis=1
            )
        elif 'product_id' in df.columns:
            df['product_key'] = df['product_id'].astype(str)
        elif 'legacy_code' in df.columns:
            df['product_key'] = df['legacy_code'].astype(str)
        else:
            df['product_key'] = None
        
        # 4. Create combo_key (customer_id + product_key)
        if 'customer_id' in df.columns and 'product_key' in df.columns:
            df['combo_key'] = df['customer_id'].astype(str) + '|' + df['product_key'].fillna('')
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [preprocess] Completed in {elapsed:.3f}s → {len(df):,} rows")
        
        return df
    
    def _precalculate_first_dates(self):
        """
        Pre-calculate first invoice/sale dates for each entity.
        This is done once during initialization for performance.
        
        UPDATED v1.2.0: Exclude service products (is_service=1) from 
        New Products and New Combos calculations.
        """
        start_time = time.perf_counter()
        
        df = self._df
        
        # 1. First invoice date per customer (globally - any salesperson)
        # Note: Customers are NOT filtered by is_service
        self._first_customer_dates = df.groupby('customer_id').agg(
            first_invoice_date=('inv_date', 'min')
        ).reset_index()
        
        # 2. First sale date per product_key (globally)
        # UPDATED v1.2.0: Exclude service products
        if 'product_key' in df.columns:
            valid_products = df[df['product_key'].notna()]
            # Exclude service products if is_service column exists
            if 'is_service' in valid_products.columns:
                valid_products = valid_products[valid_products['is_service'] != 1]
            self._first_product_dates = valid_products.groupby('product_key').agg(
                first_sale_date=('inv_date', 'min')
            ).reset_index()
        else:
            self._first_product_dates = pd.DataFrame(columns=['product_key', 'first_sale_date'])
        
        # 3. First date per customer-product combo
        # UPDATED v1.2.0: Exclude service products
        if 'combo_key' in df.columns:
            valid_combos = df[df['combo_key'].notna() & (df['combo_key'] != '|')]
            # Exclude service products if is_service column exists
            if 'is_service' in valid_combos.columns:
                valid_combos = valid_combos[valid_combos['is_service'] != 1]
            self._first_combo_dates = valid_combos.groupby(['customer_id', 'product_key']).agg(
                first_combo_date=('inv_date', 'min')
            ).reset_index()
        else:
            self._first_combo_dates = pd.DataFrame(
                columns=['customer_id', 'product_key', 'first_combo_date']
            )
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(
                f"   📊 [precalculate] First dates: "
                f"customers={len(self._first_customer_dates):,}, "
                f"products={len(self._first_product_dates):,}, "
                f"combos={len(self._first_combo_dates):,} "
                f"in {elapsed:.3f}s"
            )
    
    # =========================================================================
    # NEW CUSTOMERS
    # =========================================================================
    
    def calculate_new_customers(
        self,
        start_date: date,
        end_date: date,
        employee_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Get customers with first invoice to COMPANY in period.
        
        A customer is "new to company" if:
        - Their first invoice ever (globally, any salesperson)
        - Falls within the specified date range
        
        Credit is given to all salespeople who made sales on the first day.
        
        Args:
            start_date: Period start date
            end_date: Period end date
            employee_ids: Optional list of employee IDs to filter results
            
        Returns:
            DataFrame with columns:
            - customer_id, customer_code, customer
            - sales_id, sales_name, split_rate_percent
            - first_invoice_date
        """
        start_time = time.perf_counter()
        
        if self._df.empty or self._first_customer_dates is None:
            return pd.DataFrame()
        
        # Convert dates
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        
        # Step 1: Filter to customers whose first invoice is within period
        new_customers = self._first_customer_dates[
            (self._first_customer_dates['first_invoice_date'] >= start_ts) &
            (self._first_customer_dates['first_invoice_date'] <= end_ts)
        ].copy()
        
        if new_customers.empty:
            return pd.DataFrame()
        
        # Step 2: Get all records from first invoice date for these customers
        # This credits all salespeople who sold on the first day
        first_day_records = self._df.merge(
            new_customers[['customer_id', 'first_invoice_date']],
            on='customer_id'
        )
        first_day_records = first_day_records[
            first_day_records['inv_date'] == first_day_records['first_invoice_date']
        ]
        
        # Step 3: Deduplicate per (customer_id, sales_id)
        # Each customer-salesperson combo counted once
        result = first_day_records.groupby(['customer_id', 'sales_id']).agg({
            'customer_code': 'first',
            'customer': 'first',
            'sales_name': 'first',
            'split_rate_percent': 'first',
            'first_invoice_date': 'first'
        }).reset_index()
        
        # Step 4: Filter by employee_ids if provided
        if employee_ids:
            result = result[result['sales_id'].isin(employee_ids)]
        
        # Sort by date descending
        result = result.sort_values('first_invoice_date', ascending=False)
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [new_customers] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # NEW PRODUCTS
    # =========================================================================
    
    def calculate_new_products(
        self,
        start_date: date,
        end_date: date,
        employee_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Get products with first sale ever in period (any customer).
        
        UPDATED v1.2.0: Excludes service products (is_service=1)
        
        A product is "new" if:
        - Its first sale ever (globally, any customer, any salesperson)
        - Falls within the specified date range
        - Product is NOT a service (is_service=0)
        
        Credit is given to all salespeople who sold on the first day.
        
        Args:
            start_date: Period start date
            end_date: Period end date
            employee_ids: Optional list of employee IDs to filter results
            
        Returns:
            DataFrame with columns:
            - product_id, product_pn, pt_code, package_size, legacy_code, brand
            - sales_id, sales_name, split_rate_percent
            - first_sale_date
        """
        start_time = time.perf_counter()
        
        if self._df.empty or self._first_product_dates is None:
            return pd.DataFrame()
        
        # Convert dates
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        
        # Step 1: Filter to products whose first sale is within period
        new_products = self._first_product_dates[
            (self._first_product_dates['first_sale_date'] >= start_ts) &
            (self._first_product_dates['first_sale_date'] <= end_ts)
        ].copy()
        
        if new_products.empty:
            return pd.DataFrame()
        
        # Step 2: Get all records from first sale date for these products
        first_day_records = self._df.merge(
            new_products[['product_key', 'first_sale_date']],
            on='product_key'
        )
        first_day_records = first_day_records[
            first_day_records['inv_date'] == first_day_records['first_sale_date']
        ]
        
        # Step 3: Deduplicate per (product_key, sales_id)
        result = first_day_records.groupby(['product_key', 'sales_id']).agg({
            'product_id': 'first',
            'product_pn': 'first',
            'pt_code': 'first',
            'package_size': 'first',
            'legacy_code': 'first',
            'brand': 'first',
            'sales_name': 'first',
            'split_rate_percent': 'first',
            'first_sale_date': 'first'
        }).reset_index()
        
        # Step 4: Filter by employee_ids if provided
        if employee_ids:
            result = result[result['sales_id'].isin(employee_ids)]
        
        # Sort by date descending
        result = result.sort_values('first_sale_date', ascending=False)
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [new_products] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # NEW COMBOS DETAIL - NEW v1.1.0, UPDATED v1.2.0
    # =========================================================================
    
    def calculate_new_combos_detail(
        self,
        start_date: date,
        end_date: date,
        employee_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Get deduplicated list of new customer-product combos.
        
        NEW v1.1.0: Distinct from new_business_detail which includes revenue.
        This returns unique combos for the New Combos metric display.
        
        UPDATED v1.2.0: Excludes service products (is_service=1)
        
        A combo is "new" if:
        - First time this specific product is sold to this specific customer
        - The first sale falls within the specified date range
        - Product is NOT a service (is_service=0)
        
        Args:
            start_date: Period start date
            end_date: Period end date
            employee_ids: Optional list of employee IDs to filter results
            
        Returns:
            DataFrame with columns:
            - customer_id, customer, customer_code
            - product_key, product_pn, brand
            - sales_id, sales_name
            - first_combo_date
        """
        start_time = time.perf_counter()
        
        if self._df.empty or self._first_combo_dates is None:
            return pd.DataFrame()
        
        # Convert dates
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        
        # Step 1: Identify new combos (first sale within period)
        new_combos = self._first_combo_dates[
            (self._first_combo_dates['first_combo_date'] >= start_ts) &
            (self._first_combo_dates['first_combo_date'] <= end_ts)
        ].copy()
        
        if new_combos.empty:
            return pd.DataFrame()
        
        # Step 2: Get details for these combos from sales data
        # Join to get combo details
        df_period = self._df[
            (self._df['inv_date'] >= start_ts) & 
            (self._df['inv_date'] <= end_ts)
        ]
        
        combo_details = df_period.merge(
            new_combos,
            on=['customer_id', 'product_key'],
            how='inner'
        )
        
        # Filter to only rows on first combo date (credit to first sellers)
        combo_details = combo_details[
            combo_details['inv_date'] == combo_details['first_combo_date']
        ]
        
        # Step 3: Filter by employee_ids if provided
        if employee_ids:
            combo_details = combo_details[combo_details['sales_id'].isin(employee_ids)]
        
        if combo_details.empty:
            return pd.DataFrame()
        
        # Step 4: Deduplicate - one row per combo + salesperson
        result = combo_details.groupby(['customer_id', 'product_key', 'sales_id']).agg({
            'customer': 'first',
            'customer_code': 'first',
            'product_pn': 'first',
            'brand': 'first',
            'sales_name': 'first',
            'first_combo_date': 'first'
        }).reset_index()
        
        # Sort by date descending
        result = result.sort_values('first_combo_date', ascending=False)
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [new_combos_detail] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # NEW BUSINESS REVENUE (Aggregated)
    # =========================================================================
    
    def calculate_new_business_revenue(
        self,
        start_date: date,
        end_date: date,
        employee_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Get aggregated revenue from first customer-product combos.
        
        "New business" = first time a specific product is sold to a specific customer.
        Includes ALL revenue from new combos within period (not just first day).
        
        Args:
            start_date: Period start date
            end_date: Period end date
            employee_ids: Optional list of employee IDs to filter results
            
        Returns:
            DataFrame with columns:
            - sales_id, sales_name
            - new_business_revenue, new_business_gp, new_business_gp1
            - new_combos_count
        """
        start_time = time.perf_counter()
        
        if self._df.empty or self._first_combo_dates is None:
            return pd.DataFrame()
        
        # Convert dates
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        
        # Step 1: Identify combos that are "new" (first sale within period)
        new_combos = self._first_combo_dates[
            (self._first_combo_dates['first_combo_date'] >= start_ts) &
            (self._first_combo_dates['first_combo_date'] <= end_ts)
        ][['customer_id', 'product_key', 'first_combo_date']].copy()
        
        if new_combos.empty:
            return pd.DataFrame()
        
        # Step 2: Get ALL revenue from new combos within period
        # (not just first day - includes repeat orders of new combos)
        df_period = self._df[
            (self._df['inv_date'] >= start_ts) & 
            (self._df['inv_date'] <= end_ts)
        ]
        
        # Join with new combos
        revenue_df = df_period.merge(
            new_combos[['customer_id', 'product_key']],
            on=['customer_id', 'product_key'],
            how='inner'
        )
        
        # Step 3: Filter by employee_ids if provided
        if employee_ids:
            revenue_df = revenue_df[revenue_df['sales_id'].isin(employee_ids)]
        
        if revenue_df.empty:
            return pd.DataFrame()
        
        # Step 4: Aggregate by salesperson
        result = revenue_df.groupby(['sales_id', 'sales_name']).agg(
            new_business_revenue=('sales_by_split_usd', 'sum'),
            new_business_gp=('gross_profit_by_split_usd', 'sum'),
            new_business_gp1=('gp1_by_split_usd', 'sum'),
            new_combos_count=('combo_key', 'nunique')
        ).reset_index()
        
        # Sort by revenue descending
        result = result.sort_values('new_business_revenue', ascending=False)
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [new_business_revenue] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # NEW BUSINESS DETAIL (Line-by-line)
    # =========================================================================
    
    def calculate_new_business_detail(
        self,
        start_date: date,
        end_date: date,
        employee_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Get line-by-line detail of new business combos.
        
        Returns each unique customer-product combo that was first sold within period,
        with the first sale date and total revenue.
        
        Args:
            start_date: Period start date
            end_date: Period end date
            employee_ids: Optional list of employee IDs to filter results
            
        Returns:
            DataFrame with columns:
            - customer_id, customer, customer_code
            - product_pn, brand
            - sales_id, sales_name
            - first_combo_date
            - combo_revenue, combo_gp, combo_gp1
        """
        start_time = time.perf_counter()
        
        if self._df.empty or self._first_combo_dates is None:
            return pd.DataFrame()
        
        # Convert dates
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        
        # Step 1: Identify new combos
        new_combos = self._first_combo_dates[
            (self._first_combo_dates['first_combo_date'] >= start_ts) &
            (self._first_combo_dates['first_combo_date'] <= end_ts)
        ].copy()
        
        if new_combos.empty:
            return pd.DataFrame()
        
        # Step 2: Get all revenue from new combos within period
        df_period = self._df[
            (self._df['inv_date'] >= start_ts) & 
            (self._df['inv_date'] <= end_ts)
        ]
        
        revenue_df = df_period.merge(
            new_combos,
            on=['customer_id', 'product_key'],
            how='inner'
        )
        
        # Step 3: Filter by employee_ids if provided
        if employee_ids:
            revenue_df = revenue_df[revenue_df['sales_id'].isin(employee_ids)]
        
        if revenue_df.empty:
            return pd.DataFrame()
        
        # Step 4: Aggregate by combo + salesperson
        result = revenue_df.groupby([
            'customer_id', 'product_key', 'sales_id'
        ]).agg({
            'customer': 'first',
            'customer_code': 'first',
            'product_pn': 'first',
            'brand': 'first',
            'sales_name': 'first',
            'first_combo_date': 'first',
            'sales_by_split_usd': 'sum',
            'gross_profit_by_split_usd': 'sum',
            'gp1_by_split_usd': 'sum'
        }).reset_index()
        
        # Rename columns
        result = result.rename(columns={
            'sales_by_split_usd': 'combo_revenue',
            'gross_profit_by_split_usd': 'combo_gp',
            'gp1_by_split_usd': 'combo_gp1'
        })
        
        # Sort by date descending
        result = result.sort_values('first_combo_date', ascending=False)
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [new_business_detail] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # SUMMARY METHOD (All KPIs at once)
    # =========================================================================
    
    def calculate_all(
        self,
        start_date: date,
        end_date: date,
        employee_ids: Optional[List[int]] = None
    ) -> dict:
        """
        Calculate all Complex KPIs at once.
        
        UPDATED v1.1.0: Added new_combos_detail to output.
        
        Args:
            start_date: Period start date
            end_date: Period end date
            employee_ids: Optional list of employee IDs to filter
            
        Returns:
            Dict with:
            - new_customers: DataFrame
            - new_products: DataFrame
            - new_combos_detail: DataFrame (NEW v1.1.0)
            - new_business: DataFrame (aggregated)
            - new_business_detail: DataFrame (line-by-line with revenue)
            - summary: Dict with counts
        """
        start_time = time.perf_counter()
        
        new_customers = self.calculate_new_customers(start_date, end_date, employee_ids)
        new_products = self.calculate_new_products(start_date, end_date, employee_ids)
        new_combos_detail = self.calculate_new_combos_detail(start_date, end_date, employee_ids)
        new_business = self.calculate_new_business_revenue(start_date, end_date, employee_ids)
        new_business_detail = self.calculate_new_business_detail(start_date, end_date, employee_ids)
        
        # Summary counts
        # UPDATED v1.1.0: num_new_combos from new_combos_detail (unique combos)
        summary = {
            'num_new_customers': len(new_customers['customer_id'].unique()) if not new_customers.empty else 0,
            'num_new_products': len(new_products['product_key'].unique()) if not new_products.empty else 0,
            'num_new_combos': len(new_combos_detail) if not new_combos_detail.empty else 0,
            'new_business_revenue': new_business['new_business_revenue'].sum() if not new_business.empty else 0,
            'new_business_gp': new_business['new_business_gp'].sum() if not new_business.empty else 0,
        }
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [calculate_all] Total: {elapsed:.3f}s")
            print(f"      → New Customers: {summary['num_new_customers']}")
            print(f"      → New Products: {summary['num_new_products']}")
            print(f"      → New Combos: {summary['num_new_combos']}")
            print(f"      → New Business Revenue: ${summary['new_business_revenue']:,.0f}")
        
        return {
            'new_customers': new_customers,
            'new_products': new_products,
            'new_combos_detail': new_combos_detail,
            'new_business': new_business,
            'new_business_detail': new_business_detail,
            'summary': summary
        }
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_data_stats(self) -> dict:
        """Get statistics about the loaded data."""
        if self._df.empty:
            return {'rows': 0, 'date_range': None}
        
        return {
            'rows': len(self._df),
            'date_range': (
                self._df['inv_date'].min().strftime('%Y-%m-%d'),
                self._df['inv_date'].max().strftime('%Y-%m-%d')
            ),
            'unique_customers': self._df['customer_id'].nunique(),
            'unique_products': self._df['product_key'].nunique() if 'product_key' in self._df.columns else 0,
            'unique_salespeople': self._df['sales_id'].nunique(),
        }


# =============================================================================
# HELPER FUNCTION FOR STREAMLIT CACHING
# =============================================================================

def get_lookback_years() -> int:
    """Get lookback years from constants."""
    try:
        from .constants import LOOKBACK_YEARS
        return LOOKBACK_YEARS
    except ImportError:
        return 5  # Default


def calculate_lookback_start(end_date: date) -> date:
    """Calculate lookback start date (5 years from end_date's year)."""
    lookback_years = get_lookback_years()
    return date(end_date.year - lookback_years, 1, 1)