# utils/period_gap/shortage_analyzer.py
"""
Shortage & Surplus Analyzer Module
Version 3.0 - Refactored with mutually exclusive main categories
Main Categories: Net Shortage, Net Surplus, Balanced (based on total supply vs demand)
Sub-Categories: Timing Shortage, Timing Surplus (cross-cutting, based on period variations)
"""

import pandas as pd
from typing import Dict, Set
import logging

logger = logging.getLogger(__name__)


def categorize_main_category(gap_df: pd.DataFrame) -> Dict[str, Set[str]]:
    """
    Categorize products into MUTUALLY EXCLUSIVE main categories based on net position:
    - Net Shortage: Total supply < Total demand
    - Net Surplus: Total supply > Total demand
    - Balanced: Total supply == Total demand (exactly equal)
    
    Args:
        gap_df: GAP analysis dataframe with columns:
                - pt_code: Product code
                - total_demand_qty: Demand quantity per period
                - supply_in_period: Supply quantity per period
    
    Returns:
        Dictionary with three keys (mutually exclusive):
        - 'net_shortage': Set of product codes with net shortage
        - 'net_surplus': Set of product codes with net surplus
        - 'balanced': Set of product codes with exact balance
    """
    
    if gap_df.empty:
        return {'net_shortage': set(), 'net_surplus': set(), 'balanced': set()}
    
    net_shortage_products = set()
    net_surplus_products = set()
    balanced_products = set()
    
    # Group by product
    for pt_code in gap_df['pt_code'].unique():
        product_df = gap_df[gap_df['pt_code'] == pt_code].copy()
        
        # Calculate totals
        total_demand = product_df['total_demand_qty'].sum()
        total_supply = product_df['supply_in_period'].sum()
        
        # Categorize based on net position (mutually exclusive)
        if total_supply < total_demand:
            net_shortage_products.add(pt_code)
        elif total_supply > total_demand:
            net_surplus_products.add(pt_code)
        else:
            # Exactly equal (balanced)
            balanced_products.add(pt_code)
    
    logger.info(f"Main categorization: {len(net_shortage_products)} net shortage, "
                f"{len(net_surplus_products)} net surplus, {len(balanced_products)} balanced")
    
    return {
        'net_shortage': net_shortage_products,
        'net_surplus': net_surplus_products,
        'balanced': balanced_products
    }


def categorize_timing_issues(gap_df: pd.DataFrame) -> Dict[str, Set[str]]:
    """
    Categorize products with TIMING ISSUES (cross-cutting, not mutually exclusive):
    - Timing Shortage: Has at least one period with shortage (gap_quantity < 0)
    - Timing Surplus: Has at least one period with surplus (gap_quantity > 0)
    
    Note: A product can have BOTH timing shortage and timing surplus
    
    Args:
        gap_df: GAP analysis dataframe with columns:
                - pt_code: Product code
                - gap_quantity: GAP amount for each period
    
    Returns:
        Dictionary with two keys (NOT mutually exclusive):
        - 'timing_shortage': Set of product codes with period shortages
        - 'timing_surplus': Set of product codes with period surpluses
    """
    
    if gap_df.empty:
        return {'timing_shortage': set(), 'timing_surplus': set()}
    
    timing_shortage_products = set()
    timing_surplus_products = set()
    
    # Group by product
    for pt_code in gap_df['pt_code'].unique():
        product_df = gap_df[gap_df['pt_code'] == pt_code].copy()
        
        # Check for timing issues
        has_shortage_periods = (product_df['gap_quantity'] < 0).any()
        has_surplus_periods = (product_df['gap_quantity'] > 0).any()
        
        if has_shortage_periods:
            timing_shortage_products.add(pt_code)
        
        if has_surplus_periods:
            timing_surplus_products.add(pt_code)
    
    logger.info(f"Timing categorization: {len(timing_shortage_products)} with timing shortage, "
                f"{len(timing_surplus_products)} with timing surplus")
    
    return {
        'timing_shortage': timing_shortage_products,
        'timing_surplus': timing_surplus_products
    }


def categorize_products(gap_df: pd.DataFrame) -> Dict[str, Set[str]]:
    """
    Unified categorization function that combines main categories and timing issues
    
    This function provides a complete categorization by merging results from:
    - categorize_main_category(): Mutually exclusive categories (net_shortage, net_surplus, balanced)
    - categorize_timing_issues(): Cross-cutting timing flags (timing_shortage, timing_surplus)
    
    Args:
        gap_df: GAP analysis dataframe with required columns:
                - pt_code: Product code
                - total_demand_qty: Demand quantity per period
                - supply_in_period: Supply quantity per period
                - gap_quantity: GAP amount for each period
    
    Returns:
        Dictionary with 5 keys:
        - 'net_shortage': Set of product codes with net shortage (main category)
        - 'net_surplus': Set of product codes with net surplus (main category)
        - 'balanced': Set of product codes with exact balance (main category)
        - 'timing_shortage': Set of product codes with period shortages (timing flag)
        - 'timing_surplus': Set of product codes with period surpluses (timing flag)
    """
    
    if gap_df.empty:
        return {
            'net_shortage': set(),
            'net_surplus': set(),
            'balanced': set(),
            'timing_shortage': set(),
            'timing_surplus': set()
        }
    
    # Get main categorization (mutually exclusive)
    main_cats = categorize_main_category(gap_df)
    
    # Get timing categorization (cross-cutting)
    timing_cats = categorize_timing_issues(gap_df)
    
    # Combine results
    result = {
        'net_shortage': main_cats['net_shortage'],
        'net_surplus': main_cats['net_surplus'],
        'balanced': main_cats['balanced'],
        'timing_shortage': timing_cats['timing_shortage'],
        'timing_surplus': timing_cats['timing_surplus']
    }
    
    logger.info(f"Complete categorization: {len(result['net_shortage'])} net shortage, "
                f"{len(result['net_surplus'])} net surplus, {len(result['balanced'])} balanced, "
                f"{len(result['timing_shortage'])} timing shortage, {len(result['timing_surplus'])} timing surplus")
    
    return result


def categorize_shortage_type(gap_df: pd.DataFrame) -> Dict[str, Set[str]]:
    """
    Legacy function for backward compatibility
    Maps old logic to new main category logic
    
    Returns:
        Dictionary with keys:
        - 'net_shortage': Products with net shortage
        - 'timing_gap': Products with timing shortage (but not net shortage)
    """
    main_cats = categorize_main_category(gap_df)
    timing_cats = categorize_timing_issues(gap_df)
    
    # Timing Gap = Has timing shortage but NOT net shortage
    timing_gap_products = timing_cats['timing_shortage'] - main_cats['net_shortage']
    
    return {
        'net_shortage': main_cats['net_shortage'],
        'timing_gap': timing_gap_products
    }


def categorize_surplus_type(gap_df: pd.DataFrame) -> Dict[str, Set[str]]:
    """
    Legacy function for backward compatibility
    Maps old logic to new main category logic
    
    Returns:
        Dictionary with keys:
        - 'net_surplus': Products with net surplus
        - 'timing_surplus': Products with timing surplus (but not net surplus)
    """
    main_cats = categorize_main_category(gap_df)
    timing_cats = categorize_timing_issues(gap_df)
    
    # Timing Surplus (for old logic) = Has timing surplus but NOT net surplus
    timing_surplus_products = timing_cats['timing_surplus'] - main_cats['net_surplus']
    
    return {
        'net_surplus': main_cats['net_surplus'],
        'timing_surplus': timing_surplus_products
    }


def get_product_main_category(pt_code: str, gap_df: pd.DataFrame) -> str:
    """
    Get the main category for a single product
    
    Args:
        pt_code: Product code
        gap_df: GAP analysis dataframe
    
    Returns:
        Main category: "Net Shortage", "Net Surplus", or "Balanced"
    """
    main_cats = categorize_main_category(gap_df)
    
    if pt_code in main_cats['net_shortage']:
        return "Net Shortage"
    elif pt_code in main_cats['net_surplus']:
        return "Net Surplus"
    else:
        return "Balanced"


def get_shortage_summary(gap_df: pd.DataFrame) -> pd.DataFrame:
    """
    Get summary of categorization with actionable insights
    
    Args:
        gap_df: GAP analysis dataframe
    
    Returns:
        Summary dataframe with categorization and recommended actions
    """
    
    if gap_df.empty:
        return pd.DataFrame()
    
    main_categorization = categorize_main_category(gap_df)
    timing_categorization = categorize_timing_issues(gap_df)
    summary_data = []
    
    for pt_code in gap_df['pt_code'].unique():
        product_df = gap_df[gap_df['pt_code'] == pt_code]
        
        # Basic info
        product_name = product_df['product_name'].iloc[0] if 'product_name' in product_df.columns else ''
        brand = product_df['brand'].iloc[0] if 'brand' in product_df.columns else ''
        
        # Calculate metrics
        total_demand = product_df['total_demand_qty'].sum()
        total_supply = product_df['supply_in_period'].sum()
        net_position = total_supply - total_demand
        
        # Count shortage and surplus periods
        shortage_periods = (product_df['gap_quantity'] < 0).sum()
        surplus_periods = (product_df['gap_quantity'] > 0).sum()
        total_periods = len(product_df)
        
        # Maximum shortage and surplus in any period
        max_shortage = abs(product_df[product_df['gap_quantity'] < 0]['gap_quantity'].min()) if shortage_periods > 0 else 0
        max_surplus = product_df[product_df['gap_quantity'] > 0]['gap_quantity'].max() if surplus_periods > 0 else 0
        
        # Determine main category
        if pt_code in main_categorization['net_shortage']:
            category = "Net Shortage"
            action = "Place New Order"
            priority = "High"
        elif pt_code in main_categorization['net_surplus']:
            category = "Net Surplus"
            action = "Review Excess Stock"
            priority = "Low"
        else:
            category = "Balanced"
            # Check if has timing issues
            if pt_code in timing_categorization['timing_shortage']:
                action = "Expedite/Reschedule"
                priority = "Medium"
            else:
                action = "Monitor"
                priority = "Low"
        
        summary_data.append({
            'pt_code': pt_code,
            'product_name': product_name,
            'brand': brand,
            'category': category,
            'total_demand': total_demand,
            'total_supply': total_supply,
            'net_position': net_position,
            'shortage_periods': shortage_periods,
            'surplus_periods': surplus_periods,
            'total_periods': total_periods,
            'max_shortage': max_shortage,
            'max_surplus': max_surplus,
            'recommended_action': action,
            'priority': priority
        })
    
    summary_df = pd.DataFrame(summary_data)
    
    # Sort by priority and net position
    priority_order = {'High': 1, 'Medium': 2, 'Low': 3}
    summary_df['priority_sort'] = summary_df['priority'].map(priority_order)
    summary_df = summary_df.sort_values(['priority_sort', 'net_position'])
    summary_df = summary_df.drop(columns=['priority_sort'])
    
    return summary_df


def identify_expedite_candidates(gap_df: pd.DataFrame, 
                                supply_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Identify which supply orders could be expedited to resolve timing shortages
    
    Args:
        gap_df: GAP analysis dataframe
        supply_df: Optional supply dataframe with order details
    
    Returns:
        Dataframe of expedite candidates with recommended actions
    """
    
    timing_categorization = categorize_timing_issues(gap_df)
    timing_shortage_products = timing_categorization['timing_shortage']
    
    if not timing_shortage_products or supply_df is None or supply_df.empty:
        return pd.DataFrame()
    
    expedite_candidates = []
    
    for pt_code in timing_shortage_products:
        # Get product GAP data
        product_gap = gap_df[gap_df['pt_code'] == pt_code].copy()
        
        # Find first shortage period
        shortage_periods = product_gap[product_gap['gap_quantity'] < 0]
        if shortage_periods.empty:
            continue
            
        first_shortage_period = shortage_periods.iloc[0]['period']
        shortage_amount = abs(shortage_periods.iloc[0]['gap_quantity'])
        
        # Find supply that could be expedited
        product_supply = supply_df[supply_df['pt_code'] == pt_code].copy()
        
        # Look for supply arriving after the shortage period
        future_supply = product_supply[product_supply['source_type'].isin(['Pending PO', 'Pending CAN'])]
        
        if not future_supply.empty:
            for _, supply_row in future_supply.iterrows():
                expedite_candidates.append({
                    'pt_code': pt_code,
                    'product_name': product_gap['product_name'].iloc[0] if 'product_name' in product_gap.columns else '',
                    'shortage_period': first_shortage_period,
                    'shortage_qty': shortage_amount,
                    'supply_source': supply_row.get('source_type', ''),
                    'supply_number': supply_row.get('supply_number', ''),
                    'supply_qty': supply_row.get('quantity', 0),
                    'current_eta': supply_row.get('date_ref', ''),
                    'action': 'Expedite delivery to before ' + str(first_shortage_period)
                })
    
    return pd.DataFrame(expedite_candidates)


def calculate_order_requirements(gap_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate new order requirements for products with net shortage
    
    Args:
        gap_df: GAP analysis dataframe
    
    Returns:
        Dataframe with order requirements for each product
    """
    
    main_categorization = categorize_main_category(gap_df)
    net_shortage_products = main_categorization['net_shortage']
    
    if not net_shortage_products:
        return pd.DataFrame()
    
    order_requirements = []
    
    for pt_code in net_shortage_products:
        product_gap = gap_df[gap_df['pt_code'] == pt_code]
        
        # Calculate total shortage
        total_demand = product_gap['total_demand_qty'].sum()
        total_supply = product_gap['supply_in_period'].sum()
        net_shortage = total_demand - total_supply
        
        # Find when shortage starts
        shortage_periods = product_gap[product_gap['gap_quantity'] < 0]
        first_shortage_period = shortage_periods.iloc[0]['period'] if not shortage_periods.empty else None
        
        # Check if using backlog tracking
        if 'backlog_to_next' in product_gap.columns:
            final_backlog = product_gap['backlog_to_next'].iloc[-1] if not product_gap.empty else 0
            order_qty = max(net_shortage, final_backlog)
        else:
            order_qty = net_shortage
        
        order_requirements.append({
            'pt_code': pt_code,
            'product_name': product_gap['product_name'].iloc[0] if 'product_name' in product_gap.columns else '',
            'brand': product_gap['brand'].iloc[0] if 'brand' in product_gap.columns else '',
            'package_size': product_gap['package_size'].iloc[0] if 'package_size' in product_gap.columns else '',
            'standard_uom': product_gap['standard_uom'].iloc[0] if 'standard_uom' in product_gap.columns else '',
            'order_quantity': order_qty,
            'first_shortage_period': first_shortage_period,
            'total_demand': total_demand,
            'total_supply': total_supply,
            'coverage_periods': len(product_gap),
            'urgency': 'Immediate' if first_shortage_period else 'Plan'
        })
    
    order_df = pd.DataFrame(order_requirements)
    
    # Sort by order quantity descending
    if not order_df.empty:
        order_df = order_df.sort_values('order_quantity', ascending=False)
    
    return order_df


def calculate_surplus_review(gap_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate surplus review for products with net surplus
    
    Args:
        gap_df: GAP analysis dataframe
    
    Returns:
        Dataframe with surplus review information for each product
    """
    
    main_categorization = categorize_main_category(gap_df)
    net_surplus_products = main_categorization['net_surplus']
    
    if not net_surplus_products:
        return pd.DataFrame()
    
    surplus_review = []
    
    for pt_code in net_surplus_products:
        product_gap = gap_df[gap_df['pt_code'] == pt_code]
        
        # Calculate total surplus
        total_demand = product_gap['total_demand_qty'].sum()
        total_supply = product_gap['supply_in_period'].sum()
        net_surplus = total_supply - total_demand
        
        # Find surplus distribution
        surplus_periods = product_gap[product_gap['gap_quantity'] > 0]
        avg_surplus_per_period = surplus_periods['gap_quantity'].mean() if not surplus_periods.empty else 0
        
        # Calculate inventory holding implications
        surplus_percentage = (net_surplus / total_demand * 100) if total_demand > 0 else 0
        
        surplus_review.append({
            'pt_code': pt_code,
            'product_name': product_gap['product_name'].iloc[0] if 'product_name' in product_gap.columns else '',
            'brand': product_gap['brand'].iloc[0] if 'brand' in product_gap.columns else '',
            'package_size': product_gap['package_size'].iloc[0] if 'package_size' in product_gap.columns else '',
            'standard_uom': product_gap['standard_uom'].iloc[0] if 'standard_uom' in product_gap.columns else '',
            'surplus_quantity': net_surplus,
            'total_demand': total_demand,
            'total_supply': total_supply,
            'surplus_percentage': surplus_percentage,
            'surplus_periods': len(surplus_periods),
            'total_periods': len(product_gap),
            'avg_surplus_per_period': avg_surplus_per_period,
            'recommendation': 'Review excess stock' if surplus_percentage > 50 else 'Monitor'
        })
    
    surplus_df = pd.DataFrame(surplus_review)
    
    # Sort by surplus quantity descending
    if not surplus_df.empty:
        surplus_df = surplus_df.sort_values('surplus_quantity', ascending=False)
    
    return surplus_df


def get_action_summary(gap_df: pd.DataFrame, supply_df: pd.DataFrame = None) -> Dict[str, pd.DataFrame]:
    """
    Get comprehensive action summary for all categories
    
    Args:
        gap_df: GAP analysis dataframe
        supply_df: Optional supply dataframe
    
    Returns:
        Dictionary with action summaries:
        - 'overview': Overall categorization summary
        - 'order_requirements': New orders needed
        - 'expedite_candidates': Orders to expedite/reschedule
        - 'surplus_review': Surplus products to review
    """
    
    return {
        'overview': get_shortage_summary(gap_df),
        'order_requirements': calculate_order_requirements(gap_df),
        'expedite_candidates': identify_expedite_candidates(gap_df, supply_df),
        'surplus_review': calculate_surplus_review(gap_df)
    }