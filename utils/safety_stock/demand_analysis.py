# utils/safety_stock/demand_analysis.py
"""
Demand Analysis Module for Safety Stock Management
Fetches and analyzes historical demand from delivery_full_view
Provides reference data for safety stock calculations
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from sqlalchemy import text
from ..db import get_db_engine
import logging

logger = logging.getLogger(__name__)


def fetch_demand_stats(
    product_id: int,
    entity_id: int, 
    customer_id: Optional[int] = None,
    days_back: int = 90,
    exclude_pending: bool = True
) -> Dict:
    """
    Fetch demand statistics from underlying delivery tables directly.
    Queries stock_out_delivery + stock_out_delivery_request_details via IDs
    to avoid company_code subquery issues (company_code is not UNIQUE constrained).
    
    Args:
        product_id: Product ID
        entity_id: Legal entity ID (seller_company_id)
        customer_id: Optional customer ID (buyer_company_id) — None = all customers
        days_back: Number of days to analyze
        exclude_pending: Exclude deliveries with PENDING status
        
    Returns:
        Dictionary with demand statistics for reference
    """
    try:
        engine = get_db_engine()
        
        # Build WHERE conditions using IDs directly — no company_code subquery
        conditions = [
            "sodrd.product_id = :product_id",
            "sod.seller_company_id = :entity_id",
            "sodrd.delete_flag = 0",
            "sod.delete_flag = 0",
            "COALESCE(sod.adjust_etd_date, sod.etd_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL :days_back DAY)",
            "COALESCE(sod.adjust_etd_date, sod.etd_date) IS NOT NULL",
            "sodrd.stock_out_request_quantity > 0"
        ]
        
        if customer_id:
            conditions.append("sod.buyer_company_id = :customer_id")
        
        if exclude_pending:
            conditions.append("sod.shipment_status != 'PENDING'")
        
        where_clause = " AND ".join(conditions)
        
        # Query underlying tables directly — avoids view + company_code subquery
        query = text(f"""
        WITH daily_demand AS (
            SELECT 
                DATE(COALESCE(sod.adjust_etd_date, sod.etd_date)) AS demand_date,
                SUM(sodrd.stock_out_request_quantity) AS daily_quantity
            FROM stock_out_delivery_request_details sodrd
            JOIN stock_out_delivery sod ON sodrd.delivery_id = sod.id
            WHERE {where_clause}
            GROUP BY DATE(COALESCE(sod.adjust_etd_date, sod.etd_date))
        ),
        demand_stats AS (
            SELECT 
                AVG(daily_quantity)    AS avg_daily_demand,
                STDDEV(daily_quantity) AS demand_std_dev,
                MAX(daily_quantity)    AS max_daily_demand,
                MIN(daily_quantity)    AS min_daily_demand,
                COUNT(*)               AS data_points
            FROM daily_demand
        )
        SELECT 
            COALESCE(avg_daily_demand, 0)    AS avg_daily_demand,
            COALESCE(demand_std_dev, 0)      AS demand_std_dev,
            COALESCE(max_daily_demand, 0)    AS max_daily_demand,
            COALESCE(min_daily_demand, 0)    AS min_daily_demand,
            COALESCE(data_points, 0)         AS data_points,
            CASE 
                WHEN avg_daily_demand > 0 
                THEN (demand_std_dev / avg_daily_demand * 100)
                ELSE 0
            END AS cv_percent
        FROM demand_stats
        """)
        
        params = {
            'product_id': product_id,
            'entity_id': entity_id,
            'days_back': days_back
        }
        if customer_id:
            params['customer_id'] = customer_id
        
        with engine.connect() as conn:
            result = conn.execute(query, params).fetchone()
        
        if result:
            stats = dict(result._mapping)
            
            # Round values for display
            stats['avg_daily_demand'] = round(float(stats['avg_daily_demand']), 2)
            stats['demand_std_dev'] = round(float(stats['demand_std_dev']), 2)
            stats['cv_percent'] = round(float(stats['cv_percent']), 1)
            stats['data_points'] = int(stats['data_points'])
            
            # Add metadata
            stats['fetch_date'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            stats['days_analyzed'] = days_back
            stats['customer_specific'] = customer_id is not None
            
            # Add method suggestion based on CV%
            stats['suggested_method'] = suggest_calculation_method(stats['cv_percent'], stats['data_points'])
            
            return stats
        else:
            return get_empty_stats()
            
    except Exception as e:
        logger.error(f"Error fetching demand stats: {e}")
        return get_empty_stats()


def get_empty_stats() -> Dict:
    """Return empty statistics structure"""
    return {
        'avg_daily_demand': 0.0,
        'demand_std_dev': 0.0,
        'max_daily_demand': 0.0,
        'min_daily_demand': 0.0,
        'data_points': 0,
        'cv_percent': 0.0,
        'fetch_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'days_analyzed': 0,
        'customer_specific': False,
        'suggested_method': 'FIXED'
    }


def suggest_calculation_method(cv_percent: float, data_points: int) -> str:
    """
    Suggest best calculation method based on demand variability
    
    Args:
        cv_percent: Coefficient of variation (%)
        data_points: Number of data points available
        
    Returns:
        Suggested method: 'FIXED', 'DAYS_OF_SUPPLY', or 'LEAD_TIME_BASED'
    """
    # Insufficient data
    if data_points < 10:
        return 'FIXED'
    
    # Low variability - simple method works well
    if cv_percent < 20:
        return 'DAYS_OF_SUPPLY'
    
    # Moderate to high variability - use statistical method
    elif cv_percent >= 20 and data_points >= 30:
        return 'LEAD_TIME_BASED'
    
    # Some data but not enough for statistical
    else:
        return 'DAYS_OF_SUPPLY'


def get_lead_time_estimate(
    product_id: int,
    entity_id: int,
    customer_id: Optional[int] = None
) -> Dict:
    """
    Estimate lead time from historical delivery data.
    Calculates from OC date to date_delivered.
    Queries underlying tables directly to avoid company_code subquery issues
    and to get accurate delivery-level COUNT (not line-level).
    
    Args:
        product_id: Product ID
        entity_id: Entity ID (seller_company_id)
        customer_id: Optional customer ID (buyer_company_id)
        
    Returns:
        Dictionary with lead time estimates
    """
    try:
        engine = get_db_engine()
        
        # Query underlying tables directly:
        # - Use seller_company_id / buyer_company_id (IDs, not codes)
        # - COUNT(DISTINCT sod.id) to count deliveries, not lines
        # - sod.date_delivered is the actual column name in stock_out_delivery
        query = text("""
        SELECT 
            AVG(DATEDIFF(sod.date_delivered, oc.oc_date))    AS avg_lead_time_days,
            MIN(DATEDIFF(sod.date_delivered, oc.oc_date))    AS min_lead_time_days,
            MAX(DATEDIFF(sod.date_delivered, oc.oc_date))    AS max_lead_time_days,
            COUNT(DISTINCT sod.id)                            AS sample_size
        FROM stock_out_delivery sod
        JOIN stock_out_delivery_request_details sodrd
            ON sodrd.delivery_id = sod.id AND sodrd.delete_flag = 0
        JOIN order_confirmations oc
            ON sodrd.order_confirmation_id = oc.id AND oc.delete_flag = 0
        WHERE sod.seller_company_id  = :entity_id
            AND sodrd.product_id     = :product_id
            AND sod.shipment_status  = 'DELIVERED'
            AND sod.date_delivered   IS NOT NULL
            AND oc.oc_date           IS NOT NULL
            AND sod.delete_flag      = 0
            AND DATEDIFF(sod.date_delivered, oc.oc_date) > 0
            AND DATEDIFF(sod.date_delivered, oc.oc_date) < 365
        """)
        
        params = {'product_id': product_id, 'entity_id': entity_id}
        
        with engine.connect() as conn:
            result = conn.execute(query, params).fetchone()
        
        if result and result.avg_lead_time_days:
            return {
                'avg_lead_time_days': round(float(result.avg_lead_time_days), 0),
                'min_lead_time_days': int(result.min_lead_time_days) if result.min_lead_time_days else 0,
                'max_lead_time_days': int(result.max_lead_time_days) if result.max_lead_time_days else 0,
                'sample_size': int(result.sample_size) if result.sample_size else 0,
                'is_estimate': True,
                'calculation_basis': 'OC to Delivery'
            }
    except Exception as e:
        logger.error(f"Error estimating lead time: {e}")
    
    # Default fallback
    return {
        'avg_lead_time_days': 7,
        'min_lead_time_days': 0,
        'max_lead_time_days': 0,
        'sample_size': 0,
        'is_estimate': False,
        'note': 'Default value - no historical data available'
    }


def format_demand_summary(stats: Dict) -> str:
    """
    Format demand statistics for display (simplified version)
    
    Args:
        stats: Dictionary with demand statistics
        
    Returns:
        Formatted string for UI display
    """
    if stats['data_points'] == 0:
        return "No historical data found for the selected period"
    
    # Simplified summary - không cần hiển thị chi tiết vì đã có metrics
    summary = f"Analysis complete: {stats['data_points']} data points analyzed"
    
    return summary