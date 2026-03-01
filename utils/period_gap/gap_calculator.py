# utils/period_gap/gap_calculator.py
"""
GAP Calculation with Carry Forward Logic
Core calculation engine for Period GAP Analysis
"""

import pandas as pd
import streamlit as st
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def calculate_gap_with_carry_forward(
    df_demand: pd.DataFrame, 
    df_supply: pd.DataFrame, 
    period_type: str = "Weekly",
    track_backlog: bool = True
) -> pd.DataFrame:
    """
    Calculate GAP with carry forward logic - SIMPLIFIED VERSION
    
    Args:
        df_demand: Demand dataframe
        df_supply: Supply dataframe
        period_type: Period type for grouping
        track_backlog: Whether to track negative carry forward (backlog)
    
    Returns:
        DataFrame with GAP analysis by product and period
    """
    from .period_processor import PeriodBasedGAPProcessor
    from .period_helpers import parse_week_period, parse_month_period
    
    # Early return if both empty
    if df_demand.empty and df_supply.empty:
        st.warning("No data available for GAP calculation")
        return pd.DataFrame()
    
    # Initialize processor
    processor = PeriodBasedGAPProcessor(period_type)
    
    # Process all data by period
    with st.spinner("Processing data by period..."):
        period_data = processor.process_for_gap(df_demand, df_supply)
    
    if period_data.empty:
        st.warning("No valid period data for GAP calculation")
        return pd.DataFrame()
    
    # Apply carry forward logic with proper backlog tracking
    results = []
    products = period_data['pt_code'].unique()
    
    for product in products:
        product_data = period_data[period_data['pt_code'] == product].copy()
        
        # Sort by period BEFORE any processing
        if period_type == "Weekly":
            product_data['sort_key'] = product_data['period'].apply(parse_week_period)
        elif period_type == "Monthly":
            product_data['sort_key'] = product_data['period'].apply(parse_month_period)
        else:
            product_data['sort_key'] = pd.to_datetime(product_data['period'], errors='coerce')
        
        # Sort by the sort key
        product_data = product_data.sort_values('sort_key')
        product_data = product_data.drop(columns=['sort_key'])
        
        # Initialize tracking variables
        carry_forward = 0  # Positive inventory carried forward
        backlog = 0        # Negative balance (unfulfilled demand) from previous period
        
        for idx, (_, row) in enumerate(product_data.iterrows()):
            # Store values at beginning of period
            begin_inventory = carry_forward
            backlog_from_previous = backlog
            
            if track_backlog:
                # ENHANCED LOGIC: Track both positive and negative balances
                
                # Calculate effective demand (current demand + backlog from previous)
                effective_demand = row['demand_quantity'] + backlog
                
                # Total available = current supply + carried forward inventory
                total_available = row['supply_quantity'] + carry_forward
                
                # Calculate gap
                gap = total_available - effective_demand
                
                # Update tracking variables for NEXT period
                if gap >= 0:
                    # Surplus: clear backlog, set carry forward
                    carry_forward = gap
                    backlog = 0
                else:
                    # Shortage: clear carry forward, set backlog to negative gap
                    carry_forward = 0
                    backlog = abs(gap)
                
                # Calculate fulfillment rate based on effective demand
                if effective_demand > 0:
                    fulfillment_rate = min(100, (total_available / effective_demand * 100))
                else:
                    fulfillment_rate = 100 if total_available > 0 else 0
                
            else:
                # ORIGINAL LOGIC: Only positive carry forward
                total_available = row['supply_quantity'] + carry_forward
                gap = total_available - row['demand_quantity']
                
                if row['demand_quantity'] > 0:
                    fulfillment_rate = min(100, (total_available / row['demand_quantity'] * 100))
                else:
                    fulfillment_rate = 100 if total_available > 0 else 0
                
                # Update carry forward (original logic)
                carry_forward = max(0, gap)
                
                # No backlog tracking
                effective_demand = row['demand_quantity']
                backlog_from_previous = 0
            
            # Determine status
            if gap >= 0:
                status = "✅ Fulfilled"
            else:
                status = "❌ Shortage"
            
            # Build result row
            result_row = {
                'pt_code': row['pt_code'],
                'brand': row.get('brand', ''),
                'product_name': row.get('product_name', ''),
                'package_size': row.get('package_size', ''),
                'standard_uom': row.get('standard_uom', ''),
                'period': row['period'],  # Keep clean period format
                'begin_inventory': begin_inventory,
                'supply_in_period': row['supply_quantity'],
                'total_available': total_available,
                'total_demand_qty': row['demand_quantity'],
                'gap_quantity': gap,
                'fulfillment_rate_percent': fulfillment_rate,
                'fulfillment_status': status
            }
            
            # Add backlog info if tracking
            if track_backlog:
                result_row['backlog_qty'] = backlog_from_previous
                result_row['effective_demand'] = effective_demand
                result_row['backlog_to_next'] = backlog
            
            results.append(result_row)
    
    gap_df = pd.DataFrame(results)
    
    # Sort the entire result dataframe by product and period
    if not gap_df.empty:
        if period_type == "Weekly":
            gap_df['_sort_product'] = gap_df['pt_code']
            gap_df['_sort_period'] = gap_df['period'].apply(parse_week_period)
        elif period_type == "Monthly":
            gap_df['_sort_product'] = gap_df['pt_code']
            gap_df['_sort_period'] = gap_df['period'].apply(parse_month_period)
        else:
            gap_df['_sort_product'] = gap_df['pt_code']
            gap_df['_sort_period'] = pd.to_datetime(gap_df['period'], errors='coerce')
        
        gap_df = gap_df.sort_values(['_sort_product', '_sort_period'])
        gap_df = gap_df.drop(columns=['_sort_product', '_sort_period'])
        gap_df = gap_df.reset_index(drop=True)
    
    logger.info(f"GAP calculation complete: {len(gap_df)} rows, {gap_df['pt_code'].nunique()} products")
    
    return gap_df


def get_gap_summary_metrics(gap_df: pd.DataFrame, track_backlog: bool = True) -> Dict[str, Any]:
    """
    Calculate summary metrics from GAP results
    
    Args:
        gap_df: GAP analysis results
        track_backlog: Whether backlog tracking was enabled
    
    Returns:
        Dictionary with summary metrics
    """
    if gap_df.empty:
        return {}
    
    metrics = {
        'total_products': gap_df['pt_code'].nunique(),
        'total_periods': gap_df['period'].nunique(),
        'shortage_products': gap_df[gap_df['gap_quantity'] < 0]['pt_code'].nunique(),
        'total_shortage_qty': gap_df[gap_df['gap_quantity'] < 0]['gap_quantity'].abs().sum(),
        'avg_fulfillment_rate': gap_df['fulfillment_rate_percent'].mean(),
    }
    
    # Add backlog metrics if tracking
    if track_backlog and 'backlog_qty' in gap_df.columns:
        final_backlog_by_product = gap_df.groupby('pt_code')['backlog_to_next'].last()
        metrics['total_backlog'] = final_backlog_by_product.sum()
        metrics['products_with_backlog'] = (final_backlog_by_product > 0).sum()
        
        max_backlog_by_product = gap_df.groupby('pt_code')['backlog_qty'].max()
        metrics['peak_total_backlog'] = max_backlog_by_product.sum()
    
    return metrics


def identify_critical_products(gap_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """
    Identify products with critical shortage
    
    Args:
        gap_df: GAP analysis results
        top_n: Number of top products to return
    
    Returns:
        DataFrame with critical products
    """
    if gap_df.empty:
        return pd.DataFrame()
    
    # Group by product
    product_summary = gap_df.groupby(['pt_code', 'product_name', 'brand']).agg({
        'gap_quantity': lambda x: x[x < 0].sum() if any(x < 0) else 0,
        'fulfillment_rate_percent': 'mean',
        'period': 'count'
    }).reset_index()
    
    product_summary.columns = [
        'pt_code', 'product_name', 'brand', 
        'total_shortage', 'avg_fulfillment_rate', 'periods_analyzed'
    ]
    
    # Filter to only products with shortage
    critical = product_summary[product_summary['total_shortage'] < 0].copy()
    critical['total_shortage'] = critical['total_shortage'].abs()
    
    # Sort by shortage amount
    critical = critical.sort_values('total_shortage', ascending=False).head(top_n)
    
    return critical


def identify_critical_periods(gap_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """
    Identify periods with critical shortage
    
    Args:
        gap_df: GAP analysis results
        top_n: Number of top periods to return
    
    Returns:
        DataFrame with critical periods
    """
    if gap_df.empty:
        return pd.DataFrame()
    
    # Group by period
    period_summary = gap_df.groupby('period').agg({
        'gap_quantity': lambda x: x[x < 0].sum() if any(x < 0) else 0,
        'pt_code': 'nunique',
        'fulfillment_rate_percent': 'mean'
    }).reset_index()
    
    period_summary.columns = [
        'period', 'total_shortage', 'products_affected', 'avg_fulfillment_rate'
    ]
    
    # Filter to only periods with shortage
    critical = period_summary[period_summary['total_shortage'] < 0].copy()
    critical['total_shortage'] = critical['total_shortage'].abs()
    
    # Sort by shortage amount
    critical = critical.sort_values('total_shortage', ascending=False).head(top_n)
    
    return critical


def calculate_product_coverage(gap_df: pd.DataFrame) -> Dict[str, int]:
    """
    Calculate product coverage statistics
    
    Args:
        gap_df: GAP analysis results
    
    Returns:
        Dictionary with coverage statistics
    """
    if gap_df.empty:
        return {}
    
    total_products = gap_df['pt_code'].nunique()
    
    # Products with any shortage
    shortage_products = gap_df[gap_df['gap_quantity'] < 0]['pt_code'].nunique()
    
    # Products fully covered (no shortage in any period)
    products_by_status = gap_df.groupby('pt_code')['gap_quantity'].min()
    fully_covered = (products_by_status >= 0).sum()
    
    coverage = {
        'total_products': total_products,
        'fully_covered': fully_covered,
        'partial_shortage': shortage_products,
        'coverage_rate': (fully_covered / total_products * 100) if total_products > 0 else 0
    }
    
    return coverage