# utils/legal_entity_performance/metrics.py
"""
Metrics Calculator for Legal Entity Performance
Aligned with kpi_center_performance/metrics.py

VERSION: 2.0.0
- Uses consistent column naming (revenue, gross_profit, gp1)
- analyze_in_period_backlog synced with KPI center
"""

import logging
from datetime import date
from typing import Dict, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class LegalEntityMetrics:
    """Calculate performance metrics from processed sales data."""
    
    def __init__(self, sales_df: pd.DataFrame):
        self.sales_df = sales_df
    
    def calculate_overview_metrics(self) -> Dict:
        """Calculate top-level overview metrics."""
        df = self.sales_df
        
        if df.empty:
            return self._empty_metrics()
        
        total_revenue = df['calculated_invoiced_amount_usd'].sum()
        total_gp = df['invoiced_gross_profit_usd'].sum()
        total_gp1 = df['invoiced_gp1_usd'].sum()
        total_commission = df['broker_commission_usd'].sum()
        
        gp_percent = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
        gp1_percent = (total_gp1 / total_revenue * 100) if total_revenue > 0 else 0
        
        num_customers = df['customer_id'].nunique() if 'customer_id' in df.columns else 0
        num_products = df['product_id'].nunique() if 'product_id' in df.columns else 0
        num_invoices = df['inv_number'].nunique() if 'inv_number' in df.columns else 0
        
        return {
            'total_revenue': total_revenue,
            'total_gp': total_gp,
            'total_gp1': total_gp1,
            'total_commission': total_commission,
            'gp_percent': gp_percent,
            'gp1_percent': gp1_percent,
            'total_customers': num_customers,
            'total_products': num_products,
            'total_orders': num_invoices,
            'total_records': len(df),
        }
    
    def calculate_yoy_metrics(self, current_df: pd.DataFrame,
                               prev_df: pd.DataFrame) -> Dict:
        """Calculate Year-over-Year comparison metrics."""
        curr_rev = current_df['calculated_invoiced_amount_usd'].sum() if not current_df.empty else 0
        prev_rev = prev_df['calculated_invoiced_amount_usd'].sum() if not prev_df.empty else 0
        
        curr_gp = current_df['invoiced_gross_profit_usd'].sum() if not current_df.empty else 0
        prev_gp = prev_df['invoiced_gross_profit_usd'].sum() if not prev_df.empty else 0
        
        curr_gp1 = current_df['invoiced_gp1_usd'].sum() if not current_df.empty else 0
        prev_gp1 = prev_df['invoiced_gp1_usd'].sum() if not prev_df.empty else 0
        
        def _delta(curr, prev):
            if prev == 0:
                return None
            return (curr - prev) / abs(prev) * 100
        
        return {
            'curr_revenue': curr_rev,
            'prev_revenue': prev_rev,
            'revenue_delta_pct': _delta(curr_rev, prev_rev),
            'curr_gp': curr_gp,
            'prev_gp': prev_gp,
            'gp_delta_pct': _delta(curr_gp, prev_gp),
            'curr_gp1': curr_gp1,
            'prev_gp1': prev_gp1,
            'gp1_delta_pct': _delta(curr_gp1, prev_gp1),
        }
    
    def calculate_backlog_metrics(self, backlog_df: pd.DataFrame,
                                   in_period_df: pd.DataFrame) -> Dict:
        """Calculate backlog summary metrics."""
        if backlog_df.empty:
            return {
                'total_backlog_usd': 0,
                'total_backlog_gp_usd': 0,
                'in_period_backlog_usd': 0,
                'overdue_count': 0,
                'overdue_amount_usd': 0,
                'total_orders': 0,
            }
        
        total_backlog = backlog_df['outstanding_amount_usd'].sum()
        total_gp = backlog_df['outstanding_gross_profit_usd'].sum()
        in_period = in_period_df['outstanding_amount_usd'].sum() if not in_period_df.empty else 0
        
        overdue_mask = backlog_df['days_until_etd'] < 0
        overdue_df = backlog_df[overdue_mask]
        
        return {
            'total_backlog_usd': total_backlog,
            'total_backlog_gp_usd': total_gp,
            'in_period_backlog_usd': in_period,
            'overdue_count': len(overdue_df),
            'overdue_amount_usd': overdue_df['outstanding_amount_usd'].sum() if not overdue_df.empty else 0,
            'total_orders': backlog_df['oc_number'].nunique() if 'oc_number' in backlog_df.columns else len(backlog_df),
        }
    
    @staticmethod
    def analyze_in_period_backlog(
        backlog_detail_df: pd.DataFrame,
        start_date,
        end_date
    ) -> Dict:
        """
        Analyze backlog with ETD within selected period.
        Synced with kpi_center_performance/metrics.py
        """
        today = date.today()
        result = {
            'total_value': 0, 'total_gp': 0, 'total_count': 0,
            'overdue_value': 0, 'overdue_gp': 0, 'overdue_count': 0,
            'on_track_value': 0, 'on_track_gp': 0, 'on_track_count': 0,
            'status': 'empty', 'overdue_warning': None
        }
        
        if backlog_detail_df.empty:
            return result
        
        df = backlog_detail_df.copy()
        if 'etd' in df.columns:
            df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
        else:
            return result
        
        in_period = df[
            (df['etd'].dt.date >= start_date) &
            (df['etd'].dt.date <= end_date)
        ]
        
        if in_period.empty:
            return result
        
        # Detect column names
        value_col = next((c for c in ['outstanding_amount_usd', 'backlog_usd'] if c in in_period.columns), None)
        gp_col = next((c for c in ['outstanding_gross_profit_usd', 'backlog_gp_usd'] if c in in_period.columns), None)
        
        result['total_count'] = len(in_period)
        if value_col:
            result['total_value'] = in_period[value_col].sum()
        if gp_col:
            result['total_gp'] = in_period[gp_col].sum()
        
        overdue = in_period[in_period['etd'].dt.date < today]
        on_track = in_period[in_period['etd'].dt.date >= today]
        
        result['overdue_count'] = len(overdue)
        if value_col and not overdue.empty:
            result['overdue_value'] = overdue[value_col].sum()
        if gp_col and not overdue.empty:
            result['overdue_gp'] = overdue[gp_col].sum()
        
        result['on_track_count'] = len(on_track)
        if value_col and not on_track.empty:
            result['on_track_value'] = on_track[value_col].sum()
        if gp_col and not on_track.empty:
            result['on_track_gp'] = on_track[gp_col].sum()
        
        is_historical = end_date < today
        if is_historical:
            result['status'] = 'historical'
        elif result['overdue_count'] > 0:
            result['status'] = 'has_overdue'
            result['overdue_warning'] = (
                f"⚠️ {result['overdue_count']} orders past ETD. "
                f"Value: ${result['overdue_value']:,.0f}"
            )
        else:
            result['status'] = 'healthy'
        
        return result
    
    def _empty_metrics(self) -> Dict:
        return {
            'total_revenue': 0, 'total_gp': 0, 'total_gp1': 0,
            'total_commission': 0, 'gp_percent': 0, 'gp1_percent': 0,
            'total_customers': 0, 'total_products': 0,
            'total_orders': 0, 'total_records': 0,
        }
    
    # =========================================================================
    # PIPELINE & FORECAST METRICS (Synced with KPC v4.0.1)
    # =========================================================================
    
    @staticmethod
    def calculate_pipeline_metrics(
        sales_df: pd.DataFrame,
        backlog_df: pd.DataFrame,
        backlog_in_period_df: pd.DataFrame,
    ) -> Dict:
        """
        Calculate pipeline & forecast metrics for Legal Entity.
        
        Synced with KPC calculate_pipeline_forecast_metrics pattern.
        LE has NO target system → Target = None, GAP = None.
        
        Forecast = Invoiced + In-Period Backlog.
        
        Returns dict with same structure as KPC pipeline_metrics:
        {
            'revenue': {invoiced, in_period_backlog, target, forecast, gap, ...},
            'gross_profit': {...},
            'gp1': {...},
            'summary': {total_backlog_revenue, total_backlog_gp, ...},
        }
        """
        # Column mappings (LE columns)
        SALES_COL_MAP = {
            'revenue': 'calculated_invoiced_amount_usd',
            'gp': 'invoiced_gross_profit_usd',
            'gp1': 'invoiced_gp1_usd',
        }
        BACKLOG_COL_MAP = {
            'revenue': 'outstanding_amount_usd',
            'gp': 'outstanding_gross_profit_usd',
        }
        
        # GP1/GP ratio for backlog GP1 estimation
        gp1_gp_ratio = 1.0
        if not sales_df.empty:
            total_gp = sales_df[SALES_COL_MAP['gp']].sum() if SALES_COL_MAP['gp'] in sales_df.columns else 0
            total_gp1 = sales_df[SALES_COL_MAP['gp1']].sum() if SALES_COL_MAP['gp1'] in sales_df.columns else 0
            if total_gp > 0:
                gp1_gp_ratio = total_gp1 / total_gp
        
        def _calc_metric(metric_type):
            sales_col = SALES_COL_MAP.get(metric_type)
            backlog_col = BACKLOG_COL_MAP.get(metric_type, BACKLOG_COL_MAP.get('gp'))
            use_ratio = (metric_type == 'gp1')
            
            # Invoiced
            invoiced = 0
            if not sales_df.empty and sales_col and sales_col in sales_df.columns:
                invoiced = sales_df[sales_col].sum()
            
            # In-period backlog
            in_period_backlog = 0
            if not backlog_in_period_df.empty and backlog_col and backlog_col in backlog_in_period_df.columns:
                in_period_backlog = backlog_in_period_df[backlog_col].sum()
                if use_ratio:
                    in_period_backlog *= gp1_gp_ratio
            
            # Forecast = Invoiced + In-Period
            forecast = invoiced + in_period_backlog
            
            # No target system in LE
            return {
                'invoiced': invoiced,
                'in_period_backlog': in_period_backlog,
                'target': None,
                'forecast': forecast,
                'gap': None,
                'gap_percent': None,
                'forecast_achievement': None,
                'kpi_center_count': 0,
            }
        
        # Summary (total backlog across all)
        rev_col = BACKLOG_COL_MAP['revenue']
        gp_col = BACKLOG_COL_MAP['gp']
        
        total_backlog_rev = backlog_df[rev_col].sum() if not backlog_df.empty and rev_col in backlog_df.columns else 0
        total_backlog_gp = backlog_df[gp_col].sum() if not backlog_df.empty and gp_col in backlog_df.columns else 0
        total_backlog_gp1 = total_backlog_gp * gp1_gp_ratio
        backlog_orders = backlog_df['oc_number'].nunique() if not backlog_df.empty and 'oc_number' in backlog_df.columns else 0
        
        # Overdue
        overdue_orders = 0
        overdue_revenue = 0
        if not backlog_df.empty and 'days_until_etd' in backlog_df.columns:
            overdue_mask = backlog_df['days_until_etd'] < 0
            overdue_df = backlog_df[overdue_mask]
            overdue_orders = overdue_df['oc_number'].nunique() if 'oc_number' in overdue_df.columns else len(overdue_df)
            overdue_revenue = overdue_df[rev_col].sum() if rev_col in overdue_df.columns else 0
        
        return {
            'revenue': _calc_metric('revenue'),
            'gross_profit': _calc_metric('gp'),
            'gp1': _calc_metric('gp1'),
            'summary': {
                'total_backlog_revenue': total_backlog_rev,
                'total_backlog_gp': total_backlog_gp,
                'total_backlog_gp1': total_backlog_gp1,
                'backlog_orders': int(backlog_orders),
                'gp1_gp_ratio': gp1_gp_ratio,
                'overdue_orders': int(overdue_orders),
                'overdue_revenue': float(overdue_revenue),
            },
        }