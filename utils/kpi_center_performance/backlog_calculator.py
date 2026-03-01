# utils/kpi_center_performance/backlog_calculator.py
"""
Backlog Calculator - Pandas-based calculations for KPI Center Performance

"""

import pandas as pd
import numpy as np
from datetime import date, datetime
from typing import List, Optional, Dict, Any
import time
import logging

from .constants import DEBUG_TIMING

logger = logging.getLogger(__name__)


class BacklogCalculator:
    """
    Calculate Backlog metrics using Pandas instead of multiple SQL queries.
    
    The key optimization is loading raw backlog data ONCE, then performing
    all aggregations in Pandas (much faster than multiple SQL round-trips).
    
    Attributes:
        _df: The raw backlog data (already filtered by kpi_center_ids, entity_ids)
        _exclude_internal: Whether to exclude Internal customer revenue
    """
    
    def __init__(self, backlog_raw_df: pd.DataFrame, exclude_internal: bool = True):
        """
        Initialize with raw backlog data.
        
        Args:
            backlog_raw_df: Raw backlog data from get_all_backlog_raw()
            exclude_internal: If True, set revenue = 0 for Internal customers (keep GP)
        """
        start_time = time.perf_counter()
        
        self._df = backlog_raw_df.copy() if not backlog_raw_df.empty else pd.DataFrame()
        self._exclude_internal = exclude_internal
        
        if self._df.empty:
            if DEBUG_TIMING:
                print(f"   📊 [BacklogCalculator] Empty data, skipping preprocessing")
            return
        
        # Apply exclude_internal logic at initialization
        # This mimics the SQL CASE WHEN logic
        if exclude_internal and 'customer_type' in self._df.columns:
            # Create adjusted revenue column (0 for Internal, original for others)
            self._df['backlog_usd_adjusted'] = self._df.apply(
                lambda r: 0 if str(r.get('customer_type', '')).lower() == 'internal' 
                          else r.get('backlog_by_kpi_center_usd', 0),
                axis=1
            )
        else:
            self._df['backlog_usd_adjusted'] = self._df['backlog_by_kpi_center_usd']
        
        # Ensure numeric columns
        numeric_cols = ['backlog_by_kpi_center_usd', 'backlog_gp_by_kpi_center_usd', 
                        'backlog_usd_adjusted', 'days_until_etd', 'days_since_order',
                        'invoice_completion_percent']
        for col in numeric_cols:
            if col in self._df.columns:
                self._df[col] = pd.to_numeric(self._df[col], errors='coerce').fillna(0)
        
        # Ensure ETD is datetime
        if 'etd' in self._df.columns:
            self._df['etd'] = pd.to_datetime(self._df['etd'], errors='coerce')
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [BacklogCalculator] Initialized: {len(self._df):,} rows, "
                  f"exclude_internal={exclude_internal} in {elapsed:.3f}s")
        
        logger.info(f"BacklogCalculator initialized: {len(self._df):,} rows, exclude_internal={exclude_internal}")
    
    # =========================================================================
    # BACKLOG SUMMARY (by KPI Center)
    # =========================================================================
    
    def calculate_summary(self) -> pd.DataFrame:
        """
        Calculate backlog summary by KPI Center.
        
        Replaces: get_backlog_data()
        
        Returns DataFrame with columns:
        - kpi_center_id, kpi_center, kpi_type
        - backlog_orders (distinct OC count)
        - total_backlog_usd (adjusted for exclude_internal)
        - total_backlog_gp_usd
        """
        start_time = time.perf_counter()
        
        if self._df.empty:
            return pd.DataFrame(columns=[
                'kpi_center_id', 'kpi_center', 'kpi_type',
                'backlog_orders', 'total_backlog_usd', 'total_backlog_gp_usd'
            ])
        
        result = self._df.groupby(['kpi_center_id', 'kpi_center', 'kpi_type']).agg(
            backlog_orders=('oc_number', 'nunique'),
            total_backlog_usd=('backlog_usd_adjusted', 'sum'),
            total_backlog_gp_usd=('backlog_gp_by_kpi_center_usd', 'sum')
        ).reset_index()
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [backlog_summary] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # BACKLOG IN-PERIOD (filtered by ETD)
    # =========================================================================
    
    def calculate_in_period(
        self,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """
        Calculate backlog with ETD within specified period.
        
        Replaces: get_backlog_in_period()
        
        Args:
            start_date: Period start date
            end_date: Period end date
            
        Returns DataFrame with columns:
        - kpi_center_id, kpi_center, kpi_type
        - in_period_orders
        - in_period_backlog_usd (adjusted)
        - in_period_backlog_gp_usd
        """
        start_time = time.perf_counter()
        
        if self._df.empty:
            return pd.DataFrame(columns=[
                'kpi_center_id', 'kpi_center', 'kpi_type',
                'in_period_orders', 'in_period_backlog_usd', 'in_period_backlog_gp_usd'
            ])
        
        # Filter by ETD date range
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        
        filtered = self._df[
            (self._df['etd'] >= start_dt) & 
            (self._df['etd'] <= end_dt)
        ]
        
        if filtered.empty:
            result = pd.DataFrame(columns=[
                'kpi_center_id', 'kpi_center', 'kpi_type',
                'in_period_orders', 'in_period_backlog_usd', 'in_period_backlog_gp_usd'
            ])
        else:
            result = filtered.groupby(['kpi_center_id', 'kpi_center', 'kpi_type']).agg(
                in_period_orders=('oc_number', 'nunique'),
                in_period_backlog_usd=('backlog_usd_adjusted', 'sum'),
                in_period_backlog_gp_usd=('backlog_gp_by_kpi_center_usd', 'sum')
            ).reset_index()
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [backlog_in_period] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # BACKLOG BY MONTH
    # =========================================================================
    
    def calculate_by_month(self) -> pd.DataFrame:
        """
        Calculate backlog grouped by ETD month/year.
        
        Replaces: get_backlog_by_month()
        
        Returns DataFrame with columns:
        - etd_year, etd_month
        - backlog_orders
        - backlog_usd (adjusted)
        - backlog_gp_usd
        """
        start_time = time.perf_counter()
        
        if self._df.empty:
            return pd.DataFrame(columns=[
                'etd_year', 'etd_month', 'backlog_orders', 'backlog_usd', 'backlog_gp_usd'
            ])
        
        # Extract year/month from ETD if not already present
        if 'etd_year' not in self._df.columns and 'etd' in self._df.columns:
            self._df['etd_year'] = self._df['etd'].dt.year
        if 'etd_month' not in self._df.columns and 'etd' in self._df.columns:
            # Convert to month abbreviation (Jan, Feb, etc.)
            self._df['etd_month'] = self._df['etd'].dt.strftime('%b')
        
        result = self._df.groupby(['etd_year', 'etd_month']).agg(
            backlog_orders=('oc_number', 'nunique'),
            backlog_usd=('backlog_usd_adjusted', 'sum'),
            backlog_gp_usd=('backlog_gp_by_kpi_center_usd', 'sum')
        ).reset_index()
        
        # Sort by year and month order
        month_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        result['month_num'] = result['etd_month'].apply(
            lambda x: month_order.index(x) if x in month_order else 99
        )
        result = result.sort_values(['etd_year', 'month_num']).drop(columns=['month_num'])
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [backlog_by_month] {len(result):,} rows in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # BACKLOG RISK ANALYSIS
    # =========================================================================
    
    def calculate_risk_analysis(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Analyze backlog for overdue and risk factors.
        
        Replaces: get_backlog_risk_analysis()
        
        Args:
            start_date: Optional period start for in-period analysis
            end_date: Optional period end for in-period analysis
            
        Returns:
            Dictionary with risk metrics
        """
        start_time = time.perf_counter()
        
        if self._df.empty:
            return {
                'overdue_orders': 0,
                'overdue_revenue': 0.0,
                'overdue_gp': 0.0,
                'at_risk_orders': 0,
                'at_risk_revenue': 0.0,
                'total_orders': 0,
                'total_backlog': 0.0,
                'in_period_overdue': 0,
                'in_period_overdue_revenue': 0.0,
                'overdue_percent': 0.0
            }
        
        df = self._df
        
        # Overdue: days_until_etd < 0
        overdue_mask = df['days_until_etd'] < 0
        overdue_df = df[overdue_mask]
        
        overdue_orders = overdue_df['oc_number'].nunique()
        overdue_revenue = overdue_df['backlog_usd_adjusted'].sum()
        overdue_gp = overdue_df['backlog_gp_by_kpi_center_usd'].sum()
        
        # At Risk: 0 <= days_until_etd <= 7
        at_risk_mask = (df['days_until_etd'] >= 0) & (df['days_until_etd'] <= 7)
        at_risk_df = df[at_risk_mask]
        
        at_risk_orders = at_risk_df['oc_number'].nunique()
        at_risk_revenue = at_risk_df['backlog_usd_adjusted'].sum()
        
        # Totals
        total_orders = df['oc_number'].nunique()
        total_backlog = df['backlog_usd_adjusted'].sum()
        
        # In-period overdue (if dates provided)
        in_period_overdue = 0
        in_period_overdue_revenue = 0.0
        
        if start_date and end_date:
            start_dt = pd.Timestamp(start_date)
            end_dt = pd.Timestamp(end_date)
            
            in_period_mask = (
                (df['etd'] >= start_dt) & 
                (df['etd'] <= end_dt) &
                (df['days_until_etd'] < 0)
            )
            in_period_df = df[in_period_mask]
            
            in_period_overdue = in_period_df['oc_number'].nunique()
            in_period_overdue_revenue = in_period_df['backlog_usd_adjusted'].sum()
        
        # Calculate overdue percent
        overdue_percent = (overdue_revenue / total_backlog * 100) if total_backlog > 0 else 0.0
        
        result = {
            'overdue_orders': int(overdue_orders),
            'overdue_revenue': float(overdue_revenue),
            'overdue_gp': float(overdue_gp),
            'at_risk_orders': int(at_risk_orders),
            'at_risk_revenue': float(at_risk_revenue),
            'total_orders': int(total_orders),
            'total_backlog': float(total_backlog),
            'in_period_overdue': int(in_period_overdue),
            'in_period_overdue_revenue': float(in_period_overdue_revenue),
            'overdue_percent': float(overdue_percent)
        }
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [backlog_risk] Overdue: {overdue_orders} orders, "
                  f"${overdue_revenue:,.0f} in {elapsed:.3f}s")
        
        return result
    
    # =========================================================================
    # GET DETAIL DATA (passthrough)
    # =========================================================================
    
    def get_detail(self) -> pd.DataFrame:
        """
        Return raw detail data (for backlog list view).
        
        Note: This returns the original data without exclude_internal adjustment
        because detail tables should show all records.
        """
        return self._df.copy()
    
    # =========================================================================
    # COMBINED CALCULATION
    # =========================================================================
    
    def calculate_all(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Calculate all backlog metrics at once.
        
        Returns dict with:
        - backlog_summary_df: Summary by KPI Center
        - backlog_in_period_df: In-period backlog
        - backlog_by_month_df: By ETD month
        - backlog_detail_df: Raw detail records
        - backlog_risk: Risk analysis dict
        """
        start_time = time.perf_counter()
        
        summary_df = self.calculate_summary()
        in_period_df = self.calculate_in_period(start_date, end_date)
        by_month_df = self.calculate_by_month()
        detail_df = self.get_detail()
        risk_analysis = self.calculate_risk_analysis(start_date, end_date)
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [calculate_all_backlog] Total: {elapsed:.3f}s")
        
        return {
            'backlog_summary_df': summary_df,
            'backlog_in_period_df': in_period_df,
            'backlog_by_month_df': by_month_df,
            'backlog_detail_df': detail_df,
            'backlog_risk': risk_analysis
        }