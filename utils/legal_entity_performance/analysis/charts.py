# utils/legal_entity_performance/analysis/charts.py
"""
Analysis Tab Charts for Legal Entity Performance.
Adapted from kpi_center_performance/analysis/charts.py v6.2.0

VERSION: 2.0.0
"""

import logging
import pandas as pd
import altair as alt

from ..constants import COLORS

logger = logging.getLogger(__name__)

METRIC_COLORS = {
    'revenue': COLORS['revenue'],
    'gross_profit': COLORS['gross_profit'],
    'gp1': COLORS.get('gp1', '#2ca02c'),
}
LINE_COLOR = COLORS['gross_profit_percent']
TEXT_COLOR = COLORS['text_dark']

GROWTH_COLORS = {
    'gainer': '#2ca02c', 'decliner': '#d62728',
    'new': '#17becf', 'lost': '#ff7f0e',
    'current': '#1f77b4', 'previous': '#aec7e8',
}


def _empty_chart(message: str = "No data available") -> alt.Chart:
    return alt.Chart(pd.DataFrame({'note': [message]})).mark_text(
        text=message, fontSize=16, color='#666666'
    ).properties(width=400, height=200)


# =============================================================================
# PARETO CHART - Dual Y-axis (bars + cumulative % line)
# =============================================================================

def build_pareto_chart(
    data_df: pd.DataFrame, value_col: str, label_col: str,
    title: str = "Pareto Analysis", metric_type: str = "revenue", **kwargs
) -> alt.Chart:
    if data_df.empty:
        return _empty_chart("No data available")
    
    df = data_df.copy()
    if value_col not in df.columns or label_col not in df.columns:
        return _empty_chart("Missing required columns")
    if df[value_col].sum() == 0:
        return _empty_chart("No data (total = 0)")
    
    metric_label = {'revenue': 'Revenue', 'gross_profit': 'Gross Profit', 'gp1': 'GP1'}.get(metric_type, 'Value')
    bar_color = METRIC_COLORS.get(metric_type, '#FFA500')
    
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X(f'{label_col}:N', sort='-y', title=None, axis=alt.Axis(labelAngle=-45, labelLimit=100)),
        y=alt.Y(f'{value_col}:Q', title=f'{metric_label} (USD)', axis=alt.Axis(format='~s')),
        color=alt.value(bar_color),
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip(f'{value_col}:Q', title=metric_label, format='$,.0f'),
            alt.Tooltip('percent_contribution:Q', title='% of Total', format='.1f')
        ]
    )
    
    bar_text = alt.Chart(df).mark_text(
        align='center', baseline='bottom', dy=-5, fontSize=9
    ).encode(
        x=alt.X(f'{label_col}:N', sort='-y'),
        y=alt.Y(f'{value_col}:Q'),
        text=alt.Text(f'{value_col}:Q', format=',.0f'),
        color=alt.value(TEXT_COLOR)
    )
    
    line = alt.Chart(df).mark_line(
        point=True, color=LINE_COLOR, strokeWidth=2
    ).encode(
        x=alt.X(f'{label_col}:N', sort='-y'),
        y=alt.Y('cumulative_percent:Q', title='Cumulative %', axis=alt.Axis(format='.0%')),
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip('cumulative_percent:Q', title='Cumulative %', format='.1%')
        ]
    )
    
    line_text = alt.Chart(df).mark_text(
        align='center', baseline='bottom', dy=-8, fontSize=9, color=LINE_COLOR
    ).encode(
        x=alt.X(f'{label_col}:N', sort='-y'),
        y=alt.Y('cumulative_percent:Q'),
        text=alt.Text('cumulative_percent:Q', format='.1%')
    )
    
    return alt.layer(bars, bar_text, line, line_text).resolve_scale(
        y='independent'
    ).properties(width='container', height=400, title=title)


# =============================================================================
# GROWTH CHARTS
# =============================================================================

def build_growth_comparison_chart(
    data_df: pd.DataFrame, current_col: str, previous_col: str,
    label_col: str, title: str = "Growth Comparison", top_n: int = 15
) -> alt.Chart:
    if data_df.empty:
        return _empty_chart("No data available")
    
    chart_df = data_df.nlargest(top_n, current_col).copy()
    melted = chart_df.melt(
        id_vars=[label_col], value_vars=[current_col, previous_col],
        var_name='Period', value_name='Value'
    )
    melted['Period'] = melted['Period'].map({current_col: 'Current', previous_col: 'Previous'})
    
    return alt.Chart(melted).mark_bar().encode(
        x=alt.X(f'{label_col}:N', sort='-y', title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('Value:Q', title='Value'),
        color=alt.Color('Period:N', scale=alt.Scale(
            domain=['Current', 'Previous'], range=[METRIC_COLORS['revenue'], '#aec7e8']
        )),
        xOffset='Period:N',
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip('Period:N'), alt.Tooltip('Value:Q', format='$,.0f'),
        ]
    ).properties(width='container', height=350, title=title)


def build_movers_bar_chart(
    gainers_df: pd.DataFrame, decliners_df: pd.DataFrame,
    label_col: str, title: str = "Top Movers", top_n: int = 10
) -> alt.Chart:
    if gainers_df.empty and decliners_df.empty:
        return _empty_chart("No movers data")
    
    chart_data = []
    for _, row in gainers_df.head(top_n).iterrows():
        chart_data.append({'name': row[label_col][:25], 'value': row['change'], 'type': 'Gainer'})
    for _, row in decliners_df.head(top_n).iterrows():
        chart_data.append({'name': row[label_col][:25], 'value': row['change'], 'type': 'Decliner'})
    
    if not chart_data:
        return _empty_chart("No movers data")
    
    df = pd.DataFrame(chart_data)
    return alt.Chart(df).mark_bar().encode(
        x=alt.X('value:Q', title='Change ($)', axis=alt.Axis(format='~s')),
        y=alt.Y('name:N', sort='-x', title=None, axis=alt.Axis(labelLimit=150)),
        color=alt.Color('type:N', scale=alt.Scale(
            domain=['Gainer', 'Decliner'], range=[GROWTH_COLORS['gainer'], GROWTH_COLORS['decliner']]
        ), legend=alt.Legend(title='Type', orient='top')),
        tooltip=[alt.Tooltip('name:N'), alt.Tooltip('value:Q', format='$,.0f'), alt.Tooltip('type:N')]
    ).properties(width='container', height=350, title=title)


def build_waterfall_chart(
    compare_df: pd.DataFrame, label_col: str,
    title: str = "Growth Contribution", top_n: int = 10
) -> alt.Chart:
    if compare_df.empty:
        return _empty_chart("No data available")
    
    sorted_df = compare_df.sort_values('change', key=abs, ascending=False)
    top = sorted_df.head(top_n).copy()
    
    total_prev = compare_df['previous'].sum()
    total_curr = compare_df['current'].sum()
    others_change = compare_df['change'].sum() - top['change'].sum()
    
    data = []
    running = total_prev
    data.append({'name': 'Previous', 'start': 0, 'end': total_prev, 'value': total_prev, 'type': 'total'})
    
    for _, row in top.sort_values('change', ascending=False).iterrows():
        c = row['change']
        data.append({
            'name': row[label_col][:20], 'start': running, 'end': running + c,
            'value': c, 'type': 'increase' if c >= 0 else 'decrease'
        })
        running += c
    
    if abs(others_change) > 0:
        data.append({
            'name': 'Others', 'start': running, 'end': running + others_change,
            'value': others_change, 'type': 'increase' if others_change >= 0 else 'decrease'
        })
        running += others_change
    
    data.append({'name': 'Current', 'start': 0, 'end': total_curr, 'value': total_curr, 'type': 'total'})
    
    df = pd.DataFrame(data)
    df['order'] = range(len(df))
    
    return alt.Chart(df).mark_bar().encode(
        x=alt.X('name:N', sort=alt.EncodingSortField(field='order'), title=None,
                axis=alt.Axis(labelAngle=-45, labelLimit=100)),
        y=alt.Y('start:Q', title='Value ($)', axis=alt.Axis(format='~s')),
        y2='end:Q',
        color=alt.Color('type:N', scale=alt.Scale(
            domain=['total', 'increase', 'decrease'],
            range=['#4a90d9', GROWTH_COLORS['gainer'], GROWTH_COLORS['decliner']]
        ), legend=alt.Legend(title='Type', orient='top')),
        tooltip=[alt.Tooltip('name:N'), alt.Tooltip('value:Q', format='$,.0f')]
    ).properties(width='container', height=350, title=title)


def build_new_lost_chart(
    new_df: pd.DataFrame, lost_df: pd.DataFrame,
    label_col: str, title: str = "New vs Lost", top_n: int = 10
) -> alt.Chart:
    if new_df.empty and lost_df.empty:
        return _empty_chart("No new/lost data")
    
    total_new = new_df['current'].sum() if not new_df.empty else 0
    total_lost = lost_df['previous'].sum() if not lost_df.empty else 0
    net = total_new - total_lost
    
    summary = pd.DataFrame([
        {'Category': 'New', 'Value': total_new, 'Type': 'New'},
        {'Category': 'Lost', 'Value': -total_lost, 'Type': 'Lost'},
        {'Category': 'Net Impact', 'Value': net, 'Type': 'Net'}
    ])
    
    bars = alt.Chart(summary).mark_bar().encode(
        x=alt.X('Category:N', title=None, sort=['New', 'Lost', 'Net Impact'], axis=alt.Axis(labelAngle=0)),
        y=alt.Y('Value:Q', title='Value ($)', axis=alt.Axis(format='~s')),
        color=alt.Color('Type:N', scale=alt.Scale(
            domain=['New', 'Lost', 'Net'], range=[GROWTH_COLORS['new'], GROWTH_COLORS['lost'], '#666666']
        ), legend=None),
        tooltip=[alt.Tooltip('Category:N'), alt.Tooltip('Value:Q', format='$,.0f')]
    ).properties(width='container', height=200, title=title)
    
    text = alt.Chart(summary).mark_text(
        align='center', baseline='bottom', dy=-5, fontSize=12, fontWeight='bold'
    ).encode(
        x=alt.X('Category:N', sort=['New', 'Lost', 'Net Impact']),
        y=alt.Y('Value:Q'),
        text=alt.Text('Value:Q', format='$,.0f'),
        color=alt.value(TEXT_COLOR)
    )
    
    return bars + text


def build_status_distribution_chart(compare_df: pd.DataFrame, title: str = "Status Distribution") -> alt.Chart:
    if compare_df.empty:
        return _empty_chart("No data available")
    
    status_counts = compare_df['status'].value_counts().reset_index()
    status_counts.columns = ['status', 'count']
    
    status_colors = {
        '🆕 New': GROWTH_COLORS['new'], '❌ Lost': GROWTH_COLORS['decliner'],
        '📈 Growing': GROWTH_COLORS['gainer'], '📉 Declining': '#ff9896', '➡️ Stable': '#c7c7c7'
    }
    
    return alt.Chart(status_counts).mark_arc(innerRadius=50).encode(
        theta=alt.Theta('count:Q'),
        color=alt.Color('status:N', scale=alt.Scale(
            domain=list(status_colors.keys()), range=list(status_colors.values())
        ), legend=alt.Legend(title='Status', orient='right')),
        tooltip=[alt.Tooltip('status:N'), alt.Tooltip('count:Q', title='Count')]
    ).properties(width=250, height=250, title=title)