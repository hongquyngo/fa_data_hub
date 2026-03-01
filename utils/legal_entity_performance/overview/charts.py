# utils/legal_entity_performance/overview/charts.py
"""
Overview Tab Charts for Legal Entity Performance
Adapted from kpi_center_performance/overview/charts.py

VERSION: 2.2.0
CHANGELOG:
- v2.2.0: Removed backlog from render_kpi_cards, replaced render_backlog_summary_section
           with KPC-style _render_backlog_forecast_section (5 metrics + waterfall + bullet, 3 tabs)
           Added build_forecast_waterfall_chart, build_gap_analysis_chart, convert_pipeline_to_backlog_metrics
- v2.1.0: Added render_new_business_cards
Charts:
- render_kpi_cards: Performance metrics only (no backlog)
- render_new_business_cards: New Customers/Products/Combos/Biz Revenue
- _render_backlog_forecast_section: 5 metrics per tab + waterfall + bullet
- build_forecast_waterfall_chart: Invoiced + In-Period = Forecast vs Target
- build_gap_analysis_chart: Bullet chart (Invoiced / Forecast / Target)
- build_monthly_trend_dual_chart: Revenue + GP bars with GP% line
- build_cumulative_dual_chart: Cumulative Revenue + GP lines
- build_yoy_comparison_chart: YoY grouped bars
- build_yoy_cumulative_chart: YoY cumulative lines
"""

import logging
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import altair as alt
import streamlit as st

from ..constants import COLORS, MONTH_ORDER, CHART_WIDTH, CHART_HEIGHT
from ..common.charts import empty_chart

logger = logging.getLogger(__name__)


# =============================================================================
# KPI CARDS - Adapted from KPI center (simplified: no complex KPIs, no targets)
# =============================================================================

def render_kpi_cards(
    metrics: Dict,
    yoy_metrics: Dict = None,
):
    """
    Render KPI summary cards using Streamlit metrics.
    Adapted from KPI center render_kpi_cards.
    
    NOTE v2.2.0: Backlog removed from KPI cards → moved to dedicated Backlog & Forecast section.
    """
    # =========================================================================
    # PERFORMANCE SECTION
    # =========================================================================
    with st.container(border=True):
        st.markdown("**💰 PERFORMANCE**")
        
        # Row 1: Revenue | GP | GP1 | Commission
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            delta = None
            if yoy_metrics and yoy_metrics.get('revenue_delta_pct') is not None:
                delta = f"{yoy_metrics['revenue_delta_pct']:+.1f}% YoY"
            st.metric(
                label="Revenue",
                value=f"${metrics['total_revenue']:,.0f}",
                delta=delta,
                help="Total invoiced revenue. Formula: Σ calculated_invoiced_amount_usd"
            )
        
        with col2:
            delta = None
            if yoy_metrics and yoy_metrics.get('gp_delta_pct') is not None:
                delta = f"{yoy_metrics['gp_delta_pct']:+.1f}% YoY"
            st.metric(
                label="Gross Profit",
                value=f"${metrics['total_gp']:,.0f}",
                delta=delta,
                help="Revenue minus COGS. Formula: Σ invoiced_gross_profit_usd"
            )
        
        with col3:
            delta = None
            if yoy_metrics and yoy_metrics.get('gp1_delta_pct') is not None:
                delta = f"{yoy_metrics['gp1_delta_pct']:+.1f}% YoY"
            st.metric(
                label="GP1",
                value=f"${metrics['total_gp1']:,.0f}",
                delta=delta,
                help="Gross Profit after deducting broker commission"
            )
        
        with col4:
            st.metric(
                label="Commission",
                value=f"${metrics['total_commission']:,.0f}",
                help="Broker commission. Formula: Σ broker_commission_usd"
            )
        
        # Row 2: Customers | GP% | GP1% | Orders
        col5, col6, col7, col8 = st.columns(4)
        
        with col5:
            st.metric(
                label="Customers",
                value=f"{metrics['total_customers']:,}",
                help="Unique customers served in period"
            )
        
        with col6:
            gp_pct = metrics.get('gp_percent', 0)
            st.metric(
                label="GP %",
                value=f"{gp_pct:.1f}%",
                delta="↑ margin" if gp_pct > 30 else None,
                delta_color="off",
                help="Gross Profit Margin. Formula: GP / Revenue × 100%"
            )
        
        with col7:
            gp1_pct = metrics.get('gp1_percent', 0)
            st.metric(
                label="GP1 %",
                value=f"{gp1_pct:.1f}%",
                delta="↑ margin" if gp1_pct > 25 else None,
                delta_color="off",
                help="GP1 Margin. Formula: GP1 / Revenue × 100%"
            )
        
        with col8:
            st.metric(
                label="Invoices",
                value=f"{metrics['total_orders']:,}",
                help="Unique invoices in period"
            )


# =============================================================================
# MONTHLY TREND DUAL CHART - Adapted from KPI center
# =============================================================================

def build_monthly_trend_dual_chart(
    monthly_df: pd.DataFrame,
    show_gp_percent_line: bool = True
) -> alt.Chart:
    """
    Build monthly trend chart with Revenue + GP bars and GP% line.
    Adapted from kpi_center_performance/overview/charts.py
    """
    if monthly_df.empty:
        return empty_chart("No monthly data")
    
    chart_df = monthly_df.copy()
    chart_df['month_order'] = chart_df['month'].map(
        {m: i for i, m in enumerate(MONTH_ORDER)}
    )
    chart_df = chart_df.sort_values('month_order')
    
    if 'gp_percent' not in chart_df.columns:
        chart_df['gp_percent'] = (chart_df['gross_profit'] / chart_df['revenue'] * 100).fillna(0)
    
    # Prepare grouped bar data
    bar_data = []
    for _, row in chart_df.iterrows():
        bar_data.append({
            'month': row['month'], 'month_order': row['month_order'],
            'metric': 'Revenue', 'value': row.get('revenue', 0),
            'gp_percent': row.get('gp_percent', 0)
        })
        bar_data.append({
            'month': row['month'], 'month_order': row['month_order'],
            'metric': 'Gross Profit', 'value': row.get('gross_profit', 0),
            'gp_percent': row.get('gp_percent', 0)
        })
    
    bar_df = pd.DataFrame(bar_data)
    
    color_scale = alt.Scale(
        domain=['Revenue', 'Gross Profit'],
        range=[COLORS['revenue'], COLORS['gross_profit']]
    )
    
    bars = alt.Chart(bar_df).mark_bar(
        cornerRadiusTopLeft=2, cornerRadiusTopRight=2
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('metric:N', scale=color_scale, legend=alt.Legend(title='Metric', orient='bottom')),
        xOffset='metric:N',
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('metric:N', title='Metric'),
            alt.Tooltip('value:Q', title='Amount', format='$,.0f'),
        ]
    )
    
    bar_labels = alt.Chart(bar_df).mark_text(
        align='center', baseline='bottom', dy=-5, fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        xOffset='metric:N',
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.value(COLORS['text_dark'])
    )
    
    chart = bars + bar_labels
    
    if show_gp_percent_line:
        line_df = chart_df[['month', 'month_order', 'gp_percent']].copy()
        
        line = alt.Chart(line_df).mark_line(
            color=COLORS['gross_profit_percent'],
            strokeWidth=2,
            point=alt.OverlayMarkDef(color=COLORS['gross_profit_percent'], size=40)
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER),
            y=alt.Y('gp_percent:Q', title='GP %', axis=alt.Axis(format='.0f')),
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('gp_percent:Q', title='GP %', format='.1f'),
            ]
        )
        
        line_labels = alt.Chart(line_df).mark_text(
            align='center', baseline='bottom', dy=-8, fontSize=9,
            color=COLORS['gross_profit_percent']
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER),
            y=alt.Y('gp_percent:Q'),
            text=alt.Text('gp_percent:Q', format='.1f')
        )
        
        chart = alt.layer(bars + bar_labels, line + line_labels).resolve_scale(y='independent')
    
    return chart.properties(width=CHART_WIDTH, height=CHART_HEIGHT, title="Monthly Trend")


# =============================================================================
# CUMULATIVE DUAL CHART - Adapted from KPI center
# =============================================================================

def build_cumulative_dual_chart(monthly_df: pd.DataFrame) -> alt.Chart:
    """Build cumulative chart with Revenue + GP lines."""
    if monthly_df.empty:
        return empty_chart("No data")
    
    chart_df = monthly_df.copy()
    chart_df['month_order'] = chart_df['month'].map(
        {m: i for i, m in enumerate(MONTH_ORDER)}
    )
    chart_df = chart_df.sort_values('month_order')
    chart_df['cumulative_revenue'] = chart_df['revenue'].cumsum()
    chart_df['cumulative_gp'] = chart_df['gross_profit'].cumsum()
    
    line_data = []
    for _, row in chart_df.iterrows():
        line_data.append({
            'month': row['month'], 'month_order': row['month_order'],
            'metric': 'Cumulative Revenue', 'value': row['cumulative_revenue']
        })
        line_data.append({
            'month': row['month'], 'month_order': row['month_order'],
            'metric': 'Cumulative Gross Profit', 'value': row['cumulative_gp']
        })
    
    line_df = pd.DataFrame(line_data)
    
    color_scale = alt.Scale(
        domain=['Cumulative Revenue', 'Cumulative Gross Profit'],
        range=[COLORS['revenue'], COLORS['gross_profit']]
    )
    
    lines = alt.Chart(line_df).mark_line(
        strokeWidth=2, point=alt.OverlayMarkDef(size=50)
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title='Cumulative Amount (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('metric:N', scale=color_scale, legend=alt.Legend(title='Metric', orient='bottom')),
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('metric:N', title='Metric'),
            alt.Tooltip('value:Q', title='Amount', format='$,.0f'),
        ]
    )
    
    labels = alt.Chart(line_df).mark_text(
        align='left', baseline='middle', dx=5, fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.Color('metric:N', scale=color_scale, legend=None)
    )
    
    return (lines + labels).properties(width=CHART_WIDTH, height=CHART_HEIGHT, title="Cumulative Performance")


# =============================================================================
# YOY COMPARISON CHARTS - Adapted from KPI center
# =============================================================================

def build_yoy_comparison_chart(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    metric: str = "Revenue",
    current_year: int = None,
    previous_year: int = None
) -> alt.Chart:
    """Build Year-over-Year comparison chart with grouped bars."""
    if current_df.empty and previous_df.empty:
        return empty_chart("No data")
    
    metric_col_map = {'Revenue': 'revenue', 'Gross Profit': 'gross_profit', 'GP1': 'gp1'}
    value_col = metric_col_map.get(metric, 'revenue')
    
    combined_data = []
    
    if not current_df.empty and value_col in current_df.columns:
        curr = current_df[['month', value_col]].copy()
        curr['year'] = str(current_year) if current_year else 'Current'
        curr['year_type'] = 'Current Year'
        curr['value'] = curr[value_col]
        combined_data.append(curr[['month', 'year', 'year_type', 'value']])
    
    if not previous_df.empty and value_col in previous_df.columns:
        prev = previous_df[['month', value_col]].copy()
        prev['year'] = str(previous_year) if previous_year else 'Previous'
        prev['year_type'] = 'Previous Year'
        prev['value'] = prev[value_col]
        combined_data.append(prev[['month', 'year', 'year_type', 'value']])
    
    if not combined_data:
        return empty_chart("No data")
    
    chart_df = pd.concat(combined_data, ignore_index=True)
    
    color_scale = alt.Scale(
        domain=['Current Year', 'Previous Year'],
        range=[COLORS['current_year'], COLORS['previous_year']]
    )
    
    chart = alt.Chart(chart_df).mark_bar(
        cornerRadiusTopLeft=2, cornerRadiusTopRight=2
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title=metric, axis=alt.Axis(format='~s')),
        color=alt.Color('year_type:N', scale=color_scale, legend=alt.Legend(title='Year', orient='bottom')),
        xOffset='year_type:N',
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('year:N', title='Year'),
            alt.Tooltip('value:Q', title=metric, format='$,.0f')
        ]
    )
    
    labels = alt.Chart(chart_df).mark_text(
        align='center', baseline='bottom', dy=-5, fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        xOffset='year_type:N',
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.value(COLORS['text_dark'])
    )
    
    title_text = f"Monthly {metric}: {current_year or 'Current'} vs {previous_year or 'Previous'}"
    return (chart + labels).properties(width=CHART_WIDTH, height=CHART_HEIGHT, title=title_text)


def build_yoy_cumulative_chart(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    metric: str = "Revenue",
    current_year: int = None,
    previous_year: int = None
) -> alt.Chart:
    """Build YoY cumulative comparison chart."""
    if current_df.empty and previous_df.empty:
        return empty_chart("No data")
    
    metric_col_map = {'Revenue': 'revenue', 'Gross Profit': 'gross_profit', 'GP1': 'gp1'}
    value_col = metric_col_map.get(metric, 'revenue')
    
    line_data = []
    
    if not current_df.empty and value_col in current_df.columns:
        curr = current_df.copy()
        curr['month_order'] = curr['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
        curr = curr.sort_values('month_order')
        curr['cumulative'] = curr[value_col].cumsum()
        for _, row in curr.iterrows():
            line_data.append({
                'month': row['month'], 'month_order': row['month_order'],
                'year': 'Current Year', 'value': row['cumulative']
            })
    
    if not previous_df.empty and value_col in previous_df.columns:
        prev = previous_df.copy()
        prev['month_order'] = prev['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
        prev = prev.sort_values('month_order')
        prev['cumulative'] = prev[value_col].cumsum()
        for _, row in prev.iterrows():
            line_data.append({
                'month': row['month'], 'month_order': row['month_order'],
                'year': 'Previous Year', 'value': row['cumulative']
            })
    
    if not line_data:
        return empty_chart("No data")
    
    chart_df = pd.DataFrame(line_data)
    
    color_scale = alt.Scale(
        domain=['Current Year', 'Previous Year'],
        range=[COLORS['current_year'], COLORS['previous_year']]
    )
    
    chart = alt.Chart(chart_df).mark_line(
        strokeWidth=2, point=alt.OverlayMarkDef(size=50)
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title=f'Cumulative {metric}', axis=alt.Axis(format='~s')),
        color=alt.Color('year:N', scale=color_scale, legend=alt.Legend(title='Year', orient='bottom')),
        strokeDash=alt.condition(
            alt.datum.year == 'Previous Year',
            alt.value([5, 5]),
            alt.value([0])
        ),
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('year:N', title='Year'),
            alt.Tooltip('value:Q', title=f'Cumulative {metric}', format='$,.0f')
        ]
    )
    
    labels = alt.Chart(chart_df).mark_text(
        align='left', baseline='middle', dx=5, fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.Color('year:N', scale=color_scale, legend=None)
    )
    
    cum_title = f"Cumulative {metric}: {current_year or 'Current'} vs {previous_year or 'Previous'}"
    return (chart + labels).properties(width=CHART_WIDTH, height=CHART_HEIGHT, title=cum_title)


# =============================================================================
# MULTI-YEAR CHARTS - Synced with KPI Center v5.3.2
# =============================================================================

def build_multi_year_monthly_chart(
    monthly_df: pd.DataFrame,
    metric_col: str,
    years: List[int] = None,
    title: str = ""
) -> alt.Chart:
    """
    Grouped bar chart comparing multiple years by month.
    Synced with KPI center build_multi_year_monthly_chart.
    """
    if monthly_df.empty:
        return empty_chart("No data available")
    
    df = monthly_df.copy()
    if metric_col not in df.columns or 'year' not in df.columns or 'month' not in df.columns:
        return empty_chart("Missing required columns")
    
    monthly = df[['year', 'month', metric_col]].copy()
    monthly.columns = ['year', 'month', 'amount']
    
    if years:
        monthly = monthly[monthly['year'].isin(years)]
    else:
        years = sorted(monthly['year'].unique().tolist())
    
    if monthly.empty:
        return empty_chart("No data for selected years")
    
    monthly['year'] = monthly['year'].astype(int).astype(str)
    
    year_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
    sorted_years = sorted(monthly['year'].unique().tolist())
    color_scale = alt.Scale(domain=sorted_years, range=year_colors[:len(sorted_years)])
    
    bars = alt.Chart(monthly).mark_bar().encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month'),
        y=alt.Y('amount:Q', title=f'{metric_col.replace("_", " ").title()} (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('year:N', scale=color_scale, title='Year', legend=alt.Legend(orient='bottom')),
        xOffset=alt.XOffset('year:N', sort=sorted_years),
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('year:N', title='Year'),
            alt.Tooltip('amount:Q', title='Amount', format=',.0f')
        ]
    )
    
    return bars.properties(
        width=CHART_WIDTH, height=350,
        title=title if title else f"Monthly {metric_col.replace('_', ' ').title()} by Year"
    )


def build_multi_year_cumulative_chart(
    monthly_df: pd.DataFrame,
    metric_col: str,
    years: List[int] = None,
    title: str = ""
) -> alt.Chart:
    """
    Cumulative line chart comparing multiple years.
    Synced with KPI center build_multi_year_cumulative_chart.
    """
    if monthly_df.empty:
        return empty_chart("No data available")
    
    df = monthly_df.copy()
    if metric_col not in df.columns or 'year' not in df.columns or 'month' not in df.columns:
        return empty_chart("Missing required columns")
    
    if years is None:
        years = sorted(df['year'].unique().tolist())
    
    cumulative_data = []
    for year in sorted(years):
        year_df = df[df['year'] == year][['month', metric_col]].copy()
        year_df.columns = ['month', 'amount']
        if year_df.empty:
            continue
        
        all_months = pd.DataFrame({'month': MONTH_ORDER})
        year_df = all_months.merge(year_df, on='month', how='left').fillna(0)
        year_df['month_order'] = year_df['month'].apply(lambda x: MONTH_ORDER.index(x) if x in MONTH_ORDER else 99)
        year_df = year_df.sort_values('month_order')
        year_df['cumulative'] = year_df['amount'].cumsum()
        year_df['year'] = str(year)
        
        if year_df['amount'].sum() > 0:
            last_valid = year_df[year_df['amount'] > 0]['month_order'].max()
            year_df = year_df[year_df['month_order'] <= last_valid]
        
        cumulative_data.append(year_df)
    
    if not cumulative_data:
        return empty_chart("No data for selected years")
    
    combined = pd.concat(cumulative_data, ignore_index=True)
    
    year_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
    color_scale = alt.Scale(domain=[str(y) for y in sorted(years)], range=year_colors[:len(years)])
    
    lines = alt.Chart(combined).mark_line(
        point=alt.OverlayMarkDef(size=50), strokeWidth=2.5
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month'),
        y=alt.Y('cumulative:Q', title=f'Cumulative {metric_col.replace("_", " ").title()} (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('year:N', scale=color_scale, title='Year', legend=alt.Legend(orient='bottom')),
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('year:N', title='Year'),
            alt.Tooltip('cumulative:Q', title='Cumulative', format=',.0f')
        ]
    )
    
    return lines.properties(
        width=CHART_WIDTH, height=350,
        title=title if title else f"Cumulative {metric_col.replace('_', ' ').title()}"
    )


# =============================================================================
# YEARLY TOTAL CHART - Replaces card list for multi-year comparison
# =============================================================================

def build_yearly_total_chart(
    yearly_totals: pd.Series,
    metric_name: str = "Revenue",
) -> alt.Chart:
    """
    Bar chart showing total metric per year with YoY % change labels.
    Replaces the card-list layout when data spans many years.
    
    Args:
        yearly_totals: pd.Series indexed by year with summed metric values
        metric_name: Display name (Revenue, Gross Profit, GP1)
    """
    if yearly_totals.empty:
        return empty_chart("No yearly data")
    
    chart_data = []
    prev_value = None
    for year, value in yearly_totals.items():
        yoy_pct = None
        if prev_value is not None and prev_value > 0:
            yoy_pct = (value - prev_value) / prev_value * 100
        chart_data.append({
            'year': str(int(year)),
            'value': value,
            'yoy_pct': yoy_pct,
            'yoy_label': f"{yoy_pct:+.1f}%" if yoy_pct is not None else "",
        })
        prev_value = value
    
    df = pd.DataFrame(chart_data)
    
    # Color: positive YoY = green, negative = red, first year = primary blue
    df['bar_color'] = df['yoy_pct'].apply(
        lambda x: COLORS.get('yoy_positive', '#28a745') if x is not None and x >= 0
        else (COLORS.get('yoy_negative', '#dc3545') if x is not None
              else COLORS.get('primary', '#1f77b4'))
    )
    
    bars = alt.Chart(df).mark_bar(
        cornerRadiusTopLeft=3, cornerRadiusTopRight=3
    ).encode(
        x=alt.X('year:N', title='Year', axis=alt.Axis(labelAngle=0),
                 sort=df['year'].tolist()),
        y=alt.Y('value:Q', title=f'{metric_name} (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('bar_color:N', scale=None),
        tooltip=[
            alt.Tooltip('year:N', title='Year'),
            alt.Tooltip('value:Q', title=metric_name, format='$,.0f'),
            alt.Tooltip('yoy_label:N', title='YoY Change'),
        ]
    )
    
    # Value labels on bars
    value_labels = alt.Chart(df).mark_text(
        align='center', baseline='bottom', dy=-18, fontSize=11, fontWeight='bold'
    ).encode(
        x=alt.X('year:N', sort=df['year'].tolist()),
        y=alt.Y('value:Q'),
        text=alt.Text('value:Q', format='$,.0f'),
        color=alt.value(COLORS.get('text_dark', '#333333'))
    )
    
    # YoY % labels above value labels
    yoy_df = df[df['yoy_label'] != ''].copy()
    yoy_labels = alt.Chart(yoy_df).mark_text(
        align='center', baseline='bottom', dy=-32, fontSize=10
    ).encode(
        x=alt.X('year:N', sort=df['year'].tolist()),
        y=alt.Y('value:Q'),
        text='yoy_label:N',
        color=alt.condition(
            alt.datum.yoy_pct >= 0,
            alt.value(COLORS.get('yoy_positive', '#28a745')),
            alt.value(COLORS.get('yoy_negative', '#dc3545'))
        )
    )
    
    return alt.layer(bars, value_labels, yoy_labels).properties(
        width='container', height=280,
        title=f"Yearly {metric_name} Trend"
    )


# =============================================================================
# NEW BUSINESS CARDS - Synced with KPI Center v4.7.0 (simplified for LE)
# =============================================================================

def render_new_business_cards(
    complex_kpis: Dict,
    new_customers_df: pd.DataFrame = None,
    new_products_df: pd.DataFrame = None,
    new_combos_detail_df: pd.DataFrame = None,
    new_business_detail_df: pd.DataFrame = None,
):
    """
    Render New Business metric cards with detail popovers.
    Synced with KPI Center render_kpi_cards (New Business section).
    
    Simplified for LE: no targets/achievement, no split weighting.
    """
    with st.container(border=True):
        col_header, col_help = st.columns([6, 1])
        with col_header:
            st.markdown("**🆕 NEW BUSINESS**")
        with col_help:
            with st.popover("ℹ️ Help"):
                st.markdown("""
**🆕 New Business Metrics**

| Metric | Definition | Lookback |
|--------|------------|----------|
| **New Customers** | First-ever invoice in period | Full data range |
| **New Products** | First-ever sale in period | Full data range |
| **New Combos** | Unique customer-product pairs, first sale in period | Full data range |
| **New Biz Revenue** | Revenue from new combos | Current period |
                """)
        
        col1, col2, col3, col4 = st.columns(4)
        
        # ----- NEW CUSTOMERS -----
        with col1:
            num = complex_kpis.get('num_new_customers', 0)
            metric_col, btn_col = st.columns([4, 1])
            with metric_col:
                st.metric("New Customers", f"{num:,}",
                          help="Customers with first-ever invoice in period.")
            with btn_col:
                if new_customers_df is not None and not new_customers_df.empty:
                    with st.popover("📋"):
                        st.markdown("**📋 New Customers**")
                        display = new_customers_df.copy()
                        show_cols = []
                        if 'customer' in display.columns:
                            show_cols.append('customer')
                        if 'customer_code' in display.columns:
                            show_cols.append('customer_code')
                        if 'legal_entity' in display.columns:
                            show_cols.append('legal_entity')
                        if 'first_sale_date' in display.columns:
                            display['first_sale_date'] = pd.to_datetime(display['first_sale_date']).dt.strftime('%Y-%m-%d')
                            show_cols.append('first_sale_date')
                        if show_cols:
                            st.dataframe(display[show_cols], width="stretch", hide_index=True,
                                         height=min(400, len(display) * 35 + 40))
                        else:
                            st.caption(f"{len(display)} new customers")
        
        # ----- NEW PRODUCTS -----
        with col2:
            num = complex_kpis.get('num_new_products', 0)
            metric_col, btn_col = st.columns([4, 1])
            with metric_col:
                st.metric("New Products", f"{num:,}",
                          help="Products with first-ever sale in period.")
            with btn_col:
                if new_products_df is not None and not new_products_df.empty:
                    with st.popover("📋"):
                        st.markdown("**📋 New Products**")
                        display = new_products_df.copy()
                        show_cols = []
                        if 'product_pn' in display.columns:
                            show_cols.append('product_pn')
                        if 'brand' in display.columns:
                            show_cols.append('brand')
                        if 'legal_entity' in display.columns:
                            show_cols.append('legal_entity')
                        if 'first_sale_date' in display.columns:
                            display['first_sale_date'] = pd.to_datetime(display['first_sale_date']).dt.strftime('%Y-%m-%d')
                            show_cols.append('first_sale_date')
                        if show_cols:
                            st.dataframe(display[show_cols], width="stretch", hide_index=True,
                                         height=min(400, len(display) * 35 + 40))
                        else:
                            st.caption(f"{len(display)} new products")
        
        # ----- NEW COMBOS -----
        with col3:
            num = complex_kpis.get('num_new_combos', 0)
            metric_col, btn_col = st.columns([4, 1])
            with metric_col:
                st.metric("New Combos", f"{num:,}",
                          delta=f"{num} cust-prod pairs" if num > 0 else None,
                          delta_color="off",
                          help="Unique customer-product pairs with first sale in period.")
            with btn_col:
                if new_combos_detail_df is not None and not new_combos_detail_df.empty:
                    with st.popover("📋"):
                        st.markdown("**📋 New Combos**")
                        display = new_combos_detail_df.copy()
                        show_cols = []
                        for c in ['customer', 'product_pn', 'brand', 'legal_entity']:
                            if c in display.columns:
                                show_cols.append(c)
                        rev_col = 'calculated_invoiced_amount_usd'
                        if rev_col in display.columns:
                            display['revenue'] = display[rev_col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
                            show_cols.append('revenue')
                        if 'first_combo_date' in display.columns:
                            display['first_combo_date'] = pd.to_datetime(display['first_combo_date']).dt.strftime('%Y-%m-%d')
                            show_cols.append('first_combo_date')
                        if show_cols:
                            st.dataframe(display[show_cols], width="stretch", hide_index=True,
                                         height=min(400, len(display) * 35 + 40))
        
        # ----- NEW BUSINESS REVENUE -----
        with col4:
            rev = complex_kpis.get('new_business_revenue', 0)
            metric_col, btn_col = st.columns([4, 1])
            with metric_col:
                st.metric("New Business Revenue", f"${rev:,.0f}",
                          help="Revenue from first-time customer-product combinations.")
            with btn_col:
                if new_business_detail_df is not None and not new_business_detail_df.empty:
                    with st.popover("📋"):
                        st.markdown("**📋 New Business Revenue Detail**")
                        st.caption(f"Total: {len(new_business_detail_df)} records")
                        display = new_business_detail_df.copy()
                        show_cols = []
                        for c in ['customer', 'product_pn', 'brand']:
                            if c in display.columns:
                                show_cols.append(c)
                        rev_col = 'calculated_invoiced_amount_usd'
                        if rev_col in display.columns:
                            display['revenue'] = display[rev_col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
                            show_cols.append('revenue')
                        if show_cols:
                            agg_df = display.groupby([c for c in show_cols if c != 'revenue']).agg(
                                revenue=(rev_col, 'sum')
                            ).reset_index().sort_values('revenue', ascending=False)
                            agg_df['revenue'] = agg_df['revenue'].apply(lambda x: f"${x:,.0f}")
                            st.dataframe(agg_df, width="stretch", hide_index=True,
                                         height=min(400, len(agg_df) * 35 + 40))


# =============================================================================
# BACKLOG & FORECAST - Synced with KPC _render_backlog_forecast_section
# =============================================================================

def build_forecast_waterfall_chart(
    backlog_metrics: Dict,
    metric: str = 'revenue',
    title: str = ""
) -> alt.Chart:
    """
    Waterfall: Invoiced + In-Period Backlog = Forecast (vs Target if available).
    Synced with KPC build_forecast_waterfall_chart.
    """
    if not backlog_metrics:
        return alt.Chart().mark_text().encode(text=alt.value("No backlog data"))
    
    metric_keys = {
        'revenue': {'invoiced': 'invoiced_revenue', 'backlog': 'in_period_backlog_revenue',
                     'target': 'target_revenue', 'forecast': 'forecast_revenue', 'label': 'Revenue'},
        'gp':      {'invoiced': 'invoiced_gp', 'backlog': 'in_period_backlog_gp',
                     'target': 'target_gp', 'forecast': 'forecast_gp', 'label': 'Gross Profit'},
        'gp1':     {'invoiced': 'invoiced_gp1', 'backlog': 'in_period_backlog_gp1',
                     'target': 'target_gp1', 'forecast': 'forecast_gp1', 'label': 'GP1'},
    }
    keys = metric_keys.get(metric, metric_keys['revenue'])
    
    invoiced = backlog_metrics.get(keys['invoiced'], 0) or 0
    backlog = backlog_metrics.get(keys['backlog'], 0) or 0
    target = backlog_metrics.get(keys['target'], 0) or 0
    forecast = backlog_metrics.get(keys['forecast'], invoiced + backlog) or (invoiced + backlog)
    
    rows = [
        {'category': 'Performance', 'component': '✅ Invoiced', 'value': invoiced, 'order': 1},
        {'category': 'Performance', 'component': '📅 In-Period Backlog', 'value': backlog, 'order': 2},
    ]
    if target > 0:
        rows.append({'category': 'Target', 'component': '🎯 Target', 'value': target, 'order': 1})
    
    data = pd.DataFrame(rows)
    
    domain = ['✅ Invoiced', '📅 In-Period Backlog', '🎯 Target']
    range_colors = [COLORS.get('gross_profit', '#1f77b4'), COLORS.get('new_customer', '#17becf'), COLORS.get('target', '#d62728')]
    
    bars = alt.Chart(data).mark_bar(size=60).encode(
        x=alt.X('category:N', title='', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s'), stack='zero'),
        color=alt.Color('component:N', scale=alt.Scale(domain=domain, range=range_colors), legend=alt.Legend(orient='bottom')),
        order=alt.Order('order:Q'),
        tooltip=[
            alt.Tooltip('category:N', title='Category'),
            alt.Tooltip('component:N', title='Component'),
            alt.Tooltip('value:Q', title='Amount', format='$,.0f')
        ]
    )
    
    # Forecast dashed line
    forecast_line = alt.Chart(pd.DataFrame({'y': [forecast]})).mark_rule(
        color=COLORS.get('forecast_line', '#800080'), strokeWidth=2, strokeDash=[5, 5]
    ).encode(y='y:Q')
    
    forecast_text = alt.Chart(pd.DataFrame({
        'x': ['Performance'], 'y': [forecast],
        'label': [f'Forecast: ${forecast:,.0f}']
    })).mark_text(
        align='left', dx=35, fontSize=12, fontWeight='bold',
        color=COLORS.get('forecast_line', '#800080')
    ).encode(x='x:N', y='y:Q', text='label:N')
    
    chart = alt.layer(bars, forecast_line, forecast_text).properties(
        width=400, height=350, **({"title": title} if title else {})
    )
    return chart


def build_gap_analysis_chart(
    backlog_metrics: Dict,
    metrics_to_show: list = None,
    title: str = ""
) -> alt.Chart:
    """
    Bullet/progress chart: Invoiced / Forecast / Target.
    Synced with KPC build_gap_analysis_chart.
    Only renders metrics that have target > 0.
    """
    if metrics_to_show is None:
        metrics_to_show = ['revenue']
    if not backlog_metrics:
        return alt.Chart().mark_text().encode(text=alt.value("No data available"))
    
    metric_configs = {
        'revenue': {'invoiced_key': 'invoiced_revenue', 'target_key': 'target_revenue',
                     'forecast_key': 'forecast_revenue', 'label': 'Revenue'},
        'gp':      {'invoiced_key': 'invoiced_gp', 'target_key': 'target_gp',
                     'forecast_key': 'forecast_gp', 'label': 'Gross Profit'},
        'gp1':     {'invoiced_key': 'invoiced_gp1', 'target_key': 'target_gp1',
                     'forecast_key': 'forecast_gp1', 'label': 'GP1'},
    }
    
    all_data = []
    for m in metrics_to_show:
        cfg = metric_configs.get(m)
        if not cfg:
            continue
        target = backlog_metrics.get(cfg['target_key'], 0) or 0
        invoiced = backlog_metrics.get(cfg['invoiced_key'], 0) or 0
        forecast = backlog_metrics.get(cfg['forecast_key'], invoiced) or invoiced
        if target == 0:
            continue
        inv_pct = (invoiced / target) * 100
        fc_pct = (forecast / target) * 100
        all_data.extend([
            {'metric': cfg['label'], 'type': 'Invoiced', 'value': invoiced, 'percent': inv_pct},
            {'metric': cfg['label'], 'type': 'Forecast', 'value': forecast, 'percent': fc_pct},
            {'metric': cfg['label'], 'type': 'Target', 'value': target, 'percent': 100},
        ])
    
    if not all_data:
        return alt.Chart().mark_text().encode(text=alt.value("No target set"))
    
    data = pd.DataFrame(all_data)
    sort_order = ['Revenue', 'Gross Profit', 'GP1']
    
    base = alt.Chart(data[data['type'] == 'Target']).mark_bar(color='#e0e0e0', size=40).encode(
        x=alt.X('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
        y=alt.Y('metric:N', title='', sort=sort_order))
    forecast_bar = alt.Chart(data[data['type'] == 'Forecast']).mark_bar(
        color=COLORS.get('new_customer', '#17becf'), size=25).encode(
        x='value:Q', y=alt.Y('metric:N', sort=sort_order),
        tooltip=[alt.Tooltip('metric:N'), alt.Tooltip('value:Q', format='$,.0f'), alt.Tooltip('percent:Q', format='.1f')])
    invoiced_bar = alt.Chart(data[data['type'] == 'Invoiced']).mark_bar(
        color=COLORS.get('gross_profit', '#1f77b4'), size=15).encode(
        x='value:Q', y=alt.Y('metric:N', sort=sort_order),
        tooltip=[alt.Tooltip('metric:N'), alt.Tooltip('value:Q', format='$,.0f'), alt.Tooltip('percent:Q', format='.1f')])
    target_rule = alt.Chart(data[data['type'] == 'Target']).mark_tick(
        color=COLORS.get('target', '#d62728'), thickness=3, size=50).encode(
        x='value:Q', y=alt.Y('metric:N', sort=sort_order))
    fc_data = data[data['type'] == 'Forecast'].copy()
    text = alt.Chart(fc_data).mark_text(align='left', dx=5, fontSize=11, fontWeight='bold').encode(
        x='value:Q', y=alt.Y('metric:N', sort=sort_order), text=alt.Text('percent:Q', format='.0f'),
        color=alt.condition(alt.datum.percent >= 100,
                            alt.value(COLORS.get('achievement_good', '#28a745')),
                            alt.value(COLORS.get('achievement_bad', '#dc3545'))))
    
    chart = alt.layer(base, forecast_bar, invoiced_bar, target_rule, text).properties(
        width='container', height=80 + len(metrics_to_show) * 50, **({"title": title} if title else {}))
    return chart


def convert_pipeline_to_backlog_metrics(pipeline_metrics: Dict) -> Dict:
    """
    Convert pipeline metrics format to flat backlog metrics for chart functions.
    Synced with KPC common/charts.py convert_pipeline_to_backlog_metrics.
    """
    if not pipeline_metrics:
        return {}
    summary = pipeline_metrics.get('summary', {})
    rev = pipeline_metrics.get('revenue', {})
    gp = pipeline_metrics.get('gross_profit', {})
    gp1 = pipeline_metrics.get('gp1', {})
    return {
        'total_backlog_revenue': summary.get('total_backlog_revenue', 0),
        'total_backlog_gp': summary.get('total_backlog_gp', 0),
        'total_backlog_gp1': summary.get('total_backlog_gp1', 0),
        'backlog_orders': summary.get('backlog_orders', 0),
        'in_period_backlog_revenue': rev.get('in_period_backlog', 0),
        'in_period_backlog_gp': gp.get('in_period_backlog', 0),
        'in_period_backlog_gp1': gp1.get('in_period_backlog', 0),
        'invoiced_revenue': rev.get('invoiced', 0),
        'invoiced_gp': gp.get('invoiced', 0),
        'invoiced_gp1': gp1.get('invoiced', 0),
        'target_revenue': rev.get('target') or 0,
        'target_gp': gp.get('target') or 0,
        'target_gp1': gp1.get('target') or 0,
        'forecast_revenue': rev.get('forecast', 0),
        'forecast_gp': gp.get('forecast', 0),
        'forecast_gp1': gp1.get('forecast', 0),
        'gap_revenue': rev.get('gap') or 0,
        'gap_gp': gp.get('gap') or 0,
        'gap_gp1': gp1.get('gap') or 0,
    }


def _render_backlog_forecast_section(
    summary_metrics: Dict,
    kpi_metrics: Dict,
    metric_type: str,
    chart_backlog_metrics: Dict = None,
    gp1_gp_ratio: float = 1.0
):
    """
    Render 5 metric cards + waterfall + bullet chart for one tab.
    Synced with KPC _render_backlog_forecast_section.
    Handles Target=None gracefully (LE has no target system).
    """
    if metric_type == 'revenue':
        total_key, label_total, help_suffix, kpi_name = 'total_backlog_revenue', 'Total Backlog', 'revenue', 'Revenue'
    elif metric_type == 'gp':
        total_key, label_total, help_suffix, kpi_name = 'total_backlog_gp', 'Total GP Backlog', 'GP', 'GP'
    else:
        total_key, label_total, help_suffix, kpi_name = 'total_backlog_gp1', 'Total GP1 Backlog', 'GP1', 'GP1'
    
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    
    with col_m1:
        help_text = f"All outstanding {help_suffix} from pending orders"
        if metric_type == 'gp1' and gp1_gp_ratio != 1.0:
            help_text = f"Estimated GP1 backlog (GP × {gp1_gp_ratio:.2%})"
        st.metric(
            label=label_total,
            value=f"${summary_metrics.get(total_key, 0):,.0f}",
            delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
            delta_color="off",
            help=help_text
        )
    
    with col_m2:
        in_period = kpi_metrics.get('in_period_backlog', 0)
        target = kpi_metrics.get('target')
        pct = (in_period / target * 100) if target and target > 0 else None
        st.metric(
            label="In-Period",
            value=f"${in_period:,.0f}",
            delta=f"{pct:.0f}% of target" if pct else None,
            delta_color="off",
            help=f"Backlog with ETD in selected period"
        )
    
    with col_m3:
        target = kpi_metrics.get('target')
        if target and target > 0:
            st.metric(label="Target", value=f"${target:,.0f}",
                      help=f"Prorated {kpi_name} target")
        else:
            st.metric(label="Target", value="N/A",
                      delta="No target assigned", delta_color="off",
                      help="Legal Entity has no target system")
    
    with col_m4:
        forecast = kpi_metrics.get('forecast')
        achievement = kpi_metrics.get('forecast_achievement')
        if forecast is not None:
            delta_color = "normal" if achievement and achievement >= 100 else ("inverse" if achievement else "off")
            st.metric(
                label="Forecast",
                value=f"${forecast:,.0f}",
                delta=f"{achievement:.0f}% of target" if achievement else None,
                delta_color=delta_color,
                help="Invoiced + In-Period Backlog"
            )
        else:
            st.metric(label="Forecast", value="N/A", delta="No target", delta_color="off")
    
    with col_m5:
        gap = kpi_metrics.get('gap')
        gap_pct = kpi_metrics.get('gap_percent')
        if gap is not None:
            gap_label = "Surplus ✅" if gap >= 0 else "GAP ⚠️"
            delta_color = "normal" if gap >= 0 else "inverse"
            st.metric(label=gap_label, value=f"${gap:+,.0f}",
                      delta=f"{gap_pct:+.1f}%" if gap_pct else None,
                      delta_color=delta_color,
                      help="Forecast - Target. Positive = ahead, Negative = behind.")
        else:
            st.metric(label="GAP", value="N/A", delta="No target", delta_color="off",
                      help="No target system in Legal Entity")
    
    # Charts row
    if chart_backlog_metrics:
        col_ch1, col_ch2 = st.columns(2)
        with col_ch1:
            st.markdown(f"**{kpi_name} Forecast vs Target**")
            chart = build_forecast_waterfall_chart(chart_backlog_metrics, metric=metric_type)
            st.altair_chart(chart, width="stretch")
        with col_ch2:
            # Bullet chart only if target exists
            has_target = (chart_backlog_metrics.get(f'target_{metric_type}', 0) or 0) > 0
            if has_target:
                st.markdown(f"**{kpi_name}: Target vs Forecast**")
                gap_chart = build_gap_analysis_chart(chart_backlog_metrics, metrics_to_show=[metric_type])
                st.altair_chart(gap_chart, width="stretch")
            else:
                st.info("📊 Bullet chart requires target assignment. Legal Entity currently has no target system.")