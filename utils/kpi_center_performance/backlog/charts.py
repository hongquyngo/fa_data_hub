# utils/kpi_center_performance/backlog/charts.py
"""
Backlog Tab Charts for KPI Center Performance

VERSION: 4.3.0
EXTRACTED FROM: charts.py v3.3.2

Contains:
- build_forecast_waterfall_chart: Invoiced + Backlog = Forecast vs Target
- build_gap_analysis_chart: Bullet/progress chart for target comparison
- build_backlog_by_month_chart: Simple backlog by month (single year)
- build_backlog_by_month_chart_multiyear: Timeline across multiple years
- build_backlog_by_month_stacked: Stacked bars comparing same months across years
"""

import logging
from typing import Dict, List
import pandas as pd
import altair as alt

from ..constants import COLORS, MONTH_ORDER
from ..common.charts import empty_chart

logger = logging.getLogger(__name__)



# =============================================================================
# BACKLOG BY MONTH CHARTS - v3.0.0
# =============================================================================

def build_backlog_by_month_chart(
    monthly_df: pd.DataFrame,
    revenue_col: str = 'backlog_revenue',
    gp_col: str = 'backlog_gp',
    month_col: str = 'etd_month',
    title: str = "Backlog by ETD Month"
) -> alt.Chart:
    """
    Build simple backlog by month bar chart for single year view.
    
    Args:
        monthly_df: DataFrame with month and backlog values
        revenue_col: Column name for revenue values
        gp_col: Column name for GP values
        month_col: Column name for month
        title: Chart title
        
    Returns:
        Altair layered chart with bars
    """
    if monthly_df.empty:
        return empty_chart("No backlog data")
    
    df = monthly_df.copy()
    
    # Ensure columns exist
    if revenue_col not in df.columns:
        return empty_chart(f"Missing column: {revenue_col}")
    
    # Revenue bars
    bars = alt.Chart(df).mark_bar(
        color=COLORS.get('revenue', '#FFA500'),
        opacity=0.8
    ).encode(
        x=alt.X(f'{month_col}:N', sort=MONTH_ORDER, title='Month'),
        y=alt.Y(f'{revenue_col}:Q', title='Backlog (USD)', axis=alt.Axis(format='~s')),
        tooltip=[
            alt.Tooltip(f'{month_col}:N', title='Month'),
            alt.Tooltip(f'{revenue_col}:Q', title='Revenue', format='$,.0f'),
        ]
    )
    
    # Add GP bars if available
    if gp_col and gp_col in df.columns:
        gp_bars = alt.Chart(df).mark_bar(
            color=COLORS.get('gross_profit', '#1f77b4'),
            opacity=0.6,
            xOffset=15
        ).encode(
            x=alt.X(f'{month_col}:N', sort=MONTH_ORDER),
            y=alt.Y(f'{gp_col}:Q'),
            tooltip=[
                alt.Tooltip(f'{month_col}:N', title='Month'),
                alt.Tooltip(f'{gp_col}:Q', title='GP', format='$,.0f'),
            ]
        )
        chart = alt.layer(bars, gp_bars)
    else:
        chart = bars
    
    # Add value labels
    labels = alt.Chart(df).mark_text(
        dy=-10,
        fontSize=10,
        color='#333'
    ).encode(
        x=alt.X(f'{month_col}:N', sort=MONTH_ORDER),
        y=alt.Y(f'{revenue_col}:Q'),
        text=alt.Text(f'{revenue_col}:Q', format=',.0f')
    )
    
    return alt.layer(chart, labels).properties(
        width='container',
        height=350,
        title=title
    )


def build_backlog_by_month_chart_multiyear(
    monthly_df: pd.DataFrame,
    revenue_col: str = 'backlog_revenue',
    title: str = "Backlog Timeline"
) -> alt.Chart:
    """
    Build timeline backlog chart across multiple years.
    X-axis shows "Jan'25, Feb'25, ..., Jan'26" format.
    
    Args:
        monthly_df: DataFrame with year_month, etd_year, and backlog values
        revenue_col: Column name for revenue values
        title: Chart title
        
    Returns:
        Altair bar chart with color by year
    """
    if monthly_df.empty:
        return empty_chart("No backlog data")
    
    df = monthly_df.copy()
    
    if revenue_col not in df.columns:
        return empty_chart(f"Missing column: {revenue_col}")
    
    # Ensure year_month column exists
    if 'year_month' not in df.columns:
        df['year_month'] = df['etd_month'] + "'" + df['etd_year'].astype(str).str[-2:]
    
    # Convert etd_year to string for color encoding
    df['year_str'] = df['etd_year'].astype(str)
    
    # Get unique years for color scale
    unique_years = sorted(df['etd_year'].unique())
    year_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    color_scale = alt.Scale(
        domain=[str(y) for y in unique_years],
        range=year_colors[:len(unique_years)]
    )
    
    # Build chart
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X('year_month:N', title='ETD Month', sort=None),
        y=alt.Y(f'{revenue_col}:Q', title='Backlog (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('year_str:N', scale=color_scale, title='Year'),
        tooltip=[
            alt.Tooltip('year_month:N', title='Month'),
            alt.Tooltip('etd_year:O', title='Year'),
            alt.Tooltip(f'{revenue_col}:Q', title='Revenue', format='$,.0f'),
        ]
    )
    
    # Add value labels on top
    labels = alt.Chart(df).mark_text(
        dy=-8,
        fontSize=9,
        color='#333'
    ).encode(
        x=alt.X('year_month:N', sort=None),
        y=alt.Y(f'{revenue_col}:Q'),
        text=alt.Text(f'{revenue_col}:Q', format=',.0f')
    )
    
    return alt.layer(bars, labels).properties(
        width='container',
        height=350,
        title=title
    )


def build_backlog_by_month_stacked(
    monthly_df: pd.DataFrame,
    revenue_col: str = 'backlog_revenue',
    title: str = "Backlog by Month (Stacked)"
) -> alt.Chart:
    """
    Build stacked bar chart comparing same months across years.
    
    Args:
        monthly_df: DataFrame with etd_month, etd_year, and backlog values
        revenue_col: Column name for revenue values
        title: Chart title
        
    Returns:
        Altair stacked bar chart
    """
    if monthly_df.empty:
        return empty_chart("No backlog data")
    
    df = monthly_df.copy()
    
    if revenue_col not in df.columns:
        return empty_chart(f"Missing column: {revenue_col}")
    
    # Convert etd_year to string for color encoding
    df['year_str'] = df['etd_year'].astype(str)
    
    # Get unique years for color scale
    unique_years = sorted(df['etd_year'].unique())
    year_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    color_scale = alt.Scale(
        domain=[str(y) for y in unique_years],
        range=year_colors[:len(unique_years)]
    )
    
    # Build stacked bar chart
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X('etd_month:N', sort=MONTH_ORDER, title='Month'),
        y=alt.Y(f'{revenue_col}:Q', title='Backlog (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('year_str:N', scale=color_scale, title='Year', 
                      legend=alt.Legend(orient='bottom')),
        tooltip=[
            alt.Tooltip('etd_month:N', title='Month'),
            alt.Tooltip('etd_year:O', title='Year'),
            alt.Tooltip(f'{revenue_col}:Q', title='Revenue', format='$,.0f'),
        ]
    )
    
    return chart.properties(
        width='container',
        height=350,
        title=title
    )
