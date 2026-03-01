# utils/legal_entity_performance/backlog/charts.py
"""
Backlog Tab Charts for Legal Entity Performance.
Adapted from kpi_center_performance/backlog/charts.py

VERSION: 2.0.0
"""

import logging
from typing import List
import pandas as pd
import altair as alt

from ..constants import COLORS, MONTH_ORDER
from ..common.charts import empty_chart

logger = logging.getLogger(__name__)


def build_backlog_by_month_chart(
    monthly_df: pd.DataFrame,
    revenue_col: str = 'backlog_revenue',
    gp_col: str = 'backlog_gp',
    month_col: str = 'etd_month',
    title: str = "Backlog by ETD Month"
) -> alt.Chart:
    """Simple backlog by month bar chart for single year view."""
    if monthly_df.empty:
        return empty_chart("No backlog data")
    
    df = monthly_df.copy()
    if revenue_col not in df.columns:
        return empty_chart(f"Missing column: {revenue_col}")
    
    bars = alt.Chart(df).mark_bar(
        color=COLORS['revenue'], opacity=0.8
    ).encode(
        x=alt.X(f'{month_col}:N', sort=MONTH_ORDER, title='Month'),
        y=alt.Y(f'{revenue_col}:Q', title='Backlog (USD)', axis=alt.Axis(format='~s')),
        tooltip=[
            alt.Tooltip(f'{month_col}:N', title='Month'),
            alt.Tooltip(f'{revenue_col}:Q', title='Revenue', format='$,.0f'),
        ]
    )
    
    chart = bars
    if gp_col and gp_col in df.columns:
        gp_bars = alt.Chart(df).mark_bar(
            color=COLORS['gross_profit'], opacity=0.6, xOffset=15
        ).encode(
            x=alt.X(f'{month_col}:N', sort=MONTH_ORDER),
            y=alt.Y(f'{gp_col}:Q'),
            tooltip=[
                alt.Tooltip(f'{month_col}:N', title='Month'),
                alt.Tooltip(f'{gp_col}:Q', title='GP', format='$,.0f'),
            ]
        )
        chart = alt.layer(bars, gp_bars)
    
    labels = alt.Chart(df).mark_text(
        dy=-10, fontSize=10, color=COLORS['text_dark']
    ).encode(
        x=alt.X(f'{month_col}:N', sort=MONTH_ORDER),
        y=alt.Y(f'{revenue_col}:Q'),
        text=alt.Text(f'{revenue_col}:Q', format=',.0f')
    )
    
    return alt.layer(chart, labels).properties(
        width='container', height=350, title=title
    )


def build_backlog_by_month_chart_multiyear(
    monthly_df: pd.DataFrame,
    revenue_col: str = 'backlog_revenue',
    title: str = "Backlog Timeline"
) -> alt.Chart:
    """Timeline backlog chart across multiple years."""
    if monthly_df.empty:
        return empty_chart("No backlog data")
    
    df = monthly_df.copy()
    if revenue_col not in df.columns:
        return empty_chart(f"Missing column: {revenue_col}")
    
    if 'year_month' not in df.columns:
        df['year_month'] = df['etd_month'] + "'" + df['etd_year'].astype(str).str[-2:]
    
    df['year_str'] = df['etd_year'].astype(str)
    unique_years = sorted(df['etd_year'].unique())
    year_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    color_scale = alt.Scale(
        domain=[str(y) for y in unique_years],
        range=year_colors[:len(unique_years)]
    )
    
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
    
    labels = alt.Chart(df).mark_text(
        dy=-8, fontSize=9, color=COLORS['text_dark']
    ).encode(
        x=alt.X('year_month:N', sort=None),
        y=alt.Y(f'{revenue_col}:Q'),
        text=alt.Text(f'{revenue_col}:Q', format=',.0f')
    )
    
    return alt.layer(bars, labels).properties(
        width='container', height=350, title=title
    )


def build_backlog_by_month_stacked(
    monthly_df: pd.DataFrame,
    revenue_col: str = 'backlog_revenue',
    title: str = "Backlog by Month (Stacked)"
) -> alt.Chart:
    """Stacked bar chart comparing same months across years."""
    if monthly_df.empty:
        return empty_chart("No backlog data")
    
    df = monthly_df.copy()
    if revenue_col not in df.columns:
        return empty_chart(f"Missing column: {revenue_col}")
    
    df['year_str'] = df['etd_year'].astype(str)
    unique_years = sorted(df['etd_year'].unique())
    year_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    color_scale = alt.Scale(
        domain=[str(y) for y in unique_years],
        range=year_colors[:len(unique_years)]
    )
    
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
    
    return chart.properties(width='container', height=350, title=title)