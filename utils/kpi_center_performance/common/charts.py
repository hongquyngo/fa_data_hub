# utils/kpi_center_performance/common/charts.py
"""
Shared Chart Utilities for KPI Center Performance

VERSION: 4.3.0
EXTRACTED FROM: charts.py v3.3.2
"""

import logging
from typing import Dict
import pandas as pd
import altair as alt

logger = logging.getLogger(__name__)


def empty_chart(message: str = "No data") -> alt.Chart:
    """Return an empty chart with a message."""
    return alt.Chart(pd.DataFrame({'text': [message]})).mark_text(
        fontSize=14,
        color='gray'
    ).encode(
        text='text:N'
    ).properties(
        width=400,
        height=200
    )


def convert_pipeline_to_backlog_metrics(pipeline_metrics: Dict) -> Dict:
    """
    Convert pipeline metrics format to backlog metrics format.
    
    Args:
        pipeline_metrics: Dict with 'summary', 'revenue', 'gross_profit', 'gp1' keys
        
    Returns:
        Dict with flattened backlog metrics format
    """
    if not pipeline_metrics:
        return {}
    
    summary = pipeline_metrics.get('summary', {})
    revenue_data = pipeline_metrics.get('revenue', {})
    gp_data = pipeline_metrics.get('gross_profit', {})
    gp1_data = pipeline_metrics.get('gp1', {})
    
    return {
        # Total backlog
        'total_backlog_revenue': summary.get('total_backlog_revenue', 0),
        'total_backlog_gp': summary.get('total_backlog_gp', 0),
        'total_backlog_gp1': summary.get('total_backlog_gp1', 0),
        'backlog_orders': summary.get('backlog_orders', 0),
        
        # In-period backlog
        'in_period_backlog_revenue': revenue_data.get('in_period_backlog', 0),
        'in_period_backlog_gp': gp_data.get('in_period_backlog', 0),
        'in_period_backlog_gp1': gp1_data.get('in_period_backlog', 0),
        
        # Invoiced
        'invoiced_revenue': revenue_data.get('invoiced', 0),
        'invoiced_gp': gp_data.get('invoiced', 0),
        'invoiced_gp1': gp1_data.get('invoiced', 0),
        
        # Targets
        'target_revenue': revenue_data.get('target', 0),
        'target_gp': gp_data.get('target', 0),
        'target_gp1': gp1_data.get('target', 0),
        
        # Forecast
        'forecast_revenue': revenue_data.get('forecast', 0),
        'forecast_gp': gp_data.get('forecast', 0),
        'forecast_gp1': gp1_data.get('forecast', 0),
        
        # GAP
        'gap_revenue': revenue_data.get('gap', 0),
        'gap_gp': gp_data.get('gap', 0),
        'gap_gp1': gp1_data.get('gap', 0),
        
        # Achievement
        'achievement_revenue': revenue_data.get('forecast_achievement', 0),
        'achievement_gp': gp_data.get('forecast_achievement', 0),
        'achievement_gp1': gp1_data.get('forecast_achievement', 0),
        
        # KPI Center count
        'kpi_center_count_revenue': revenue_data.get('kpi_center_count', 0),
        'kpi_center_count_gp': gp_data.get('kpi_center_count', 0),
        'kpi_center_count_gp1': gp1_data.get('kpi_center_count', 0),
    }
