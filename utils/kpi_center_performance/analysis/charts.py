# utils/kpi_center_performance/analysis/charts.py
"""
Analysis Tab Charts for KPI Center Performance.

VERSION: 6.2.0

Changes:
- v6.2.0: Added growth analysis charts (movers, waterfall, new/lost)
- v6.1.0: Charts matching Salesperson Performance reference code style.
"""

import logging
import pandas as pd
import altair as alt

logger = logging.getLogger(__name__)

# =============================================================================
# COLOR CONFIGURATION - Match reference
# =============================================================================

METRIC_COLORS = {
    'revenue': '#FFA500',       # Orange
    'gross_profit': '#1f77b4',  # Blue
    'gp1': '#2ca02c',           # Green
}

LINE_COLOR = '#800080'  # Purple for cumulative line
TEXT_COLOR = '#333333'

# Growth colors
GROWTH_COLORS = {
    'gainer': '#2ca02c',        # Green
    'decliner': '#d62728',      # Red
    'new': '#17becf',           # Cyan
    'lost': '#ff7f0e',          # Orange
    'current': '#1f77b4',       # Blue
    'previous': '#aec7e8',      # Light blue
}


# =============================================================================
# PARETO CHART - Match reference exactly
# =============================================================================

def build_pareto_chart(
    data_df: pd.DataFrame,
    value_col: str,
    label_col: str,
    title: str = "Pareto Analysis",
    metric_type: str = "revenue",
    **kwargs  # Accept extra args for compatibility
) -> alt.Chart:
    """
    Build Pareto chart: Bar (metric) + Line (cumulative %).
    
    Matches Salesperson Performance reference code exactly.
    
    Args:
        data_df: DataFrame with label, value, cumulative_percent, percent_contribution
        value_col: Column name for values (e.g., 'revenue')
        label_col: Column name for labels (e.g., 'customer')
        title: Chart title
        metric_type: 'revenue', 'gross_profit', or 'gp1' (for color)
        
    Returns:
        Altair layered chart with dual Y-axis
    """
    if data_df.empty:
        return _empty_chart("No data available")
    
    df = data_df.copy()
    
    # Verify required columns
    if value_col not in df.columns or label_col not in df.columns:
        return _empty_chart("Missing required columns")
    
    if df[value_col].sum() == 0:
        return _empty_chart("No data (total = 0)")
    
    # Config
    metric_label = {'revenue': 'Revenue', 'gross_profit': 'Gross Profit', 'gp1': 'GP1'}.get(metric_type, 'Value')
    bar_color = METRIC_COLORS.get(metric_type, '#FFA500')
    
    # === Layer 1: Bar Chart ===
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
    
    # === Layer 2: Bar Text Labels ===
    bar_text = alt.Chart(df).mark_text(
        align='center', baseline='bottom', dy=-5, fontSize=9
    ).encode(
        x=alt.X(f'{label_col}:N', sort='-y'),
        y=alt.Y(f'{value_col}:Q'),
        text=alt.Text(f'{value_col}:Q', format=',.0f'),
        color=alt.value(TEXT_COLOR)
    )
    
    # === Layer 3: Cumulative % Line ===
    line = alt.Chart(df).mark_line(
        point=True,
        color=LINE_COLOR,
        strokeWidth=2
    ).encode(
        x=alt.X(f'{label_col}:N', sort='-y'),
        y=alt.Y('cumulative_percent:Q', title='Cumulative %', axis=alt.Axis(format='.0%')),
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip('cumulative_percent:Q', title='Cumulative %', format='.1%')
        ]
    )
    
    # === Layer 4: Line Text Labels ===
    line_text = alt.Chart(df).mark_text(
        align='center', baseline='bottom', dy=-8, fontSize=9,
        color=LINE_COLOR
    ).encode(
        x=alt.X(f'{label_col}:N', sort='-y'),
        y=alt.Y('cumulative_percent:Q'),
        text=alt.Text('cumulative_percent:Q', format='.1%')
    )
    
    # === Combine with DUAL Y-AXIS ===
    chart = alt.layer(bars, bar_text, line, line_text).resolve_scale(
        y='independent'  # Important: separate Y scales
    ).properties(
        width='container',
        height=400,
        title=title
    )
    
    return chart


# =============================================================================
# GROWTH COMPARISON CHART
# =============================================================================

def build_growth_comparison_chart(
    data_df: pd.DataFrame,
    current_col: str,
    previous_col: str,
    label_col: str,
    title: str = "Growth Comparison",
    top_n: int = 15
) -> alt.Chart:
    """Build grouped bar chart for growth comparison."""
    if data_df.empty:
        return _empty_chart("No data available")
    
    chart_df = data_df.nlargest(top_n, current_col).copy()
    
    melted = chart_df.melt(
        id_vars=[label_col],
        value_vars=[current_col, previous_col],
        var_name='Period',
        value_name='Value'
    )
    
    melted['Period'] = melted['Period'].map({
        current_col: 'Current',
        previous_col: 'Previous'
    })
    
    chart = alt.Chart(melted).mark_bar().encode(
        x=alt.X(f'{label_col}:N', sort='-y', title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('Value:Q', title='Value'),
        color=alt.Color(
            'Period:N',
            scale=alt.Scale(
                domain=['Current', 'Previous'],
                range=[METRIC_COLORS['revenue'], '#aec7e8']
            )
        ),
        xOffset='Period:N',
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip('Period:N', title='Period'),
            alt.Tooltip('Value:Q', title='Value', format='$,.0f'),
        ]
    ).properties(width='container', height=350, title=title)
    
    return chart


# =============================================================================
# GROWTH ANALYSIS CHARTS
# =============================================================================

def build_movers_bar_chart(
    gainers_df: pd.DataFrame,
    decliners_df: pd.DataFrame,
    label_col: str,
    title: str = "Top Movers",
    top_n: int = 10
) -> alt.Chart:
    """
    Build horizontal butterfly bar chart for top gainers and decliners.
    
    Args:
        gainers_df: DataFrame with gainers (must have 'change' column)
        decliners_df: DataFrame with decliners (must have 'change' column)
        label_col: Column name for labels
        title: Chart title
        top_n: Number of items per side
        
    Returns:
        Altair horizontal bar chart
    """
    if gainers_df.empty and decliners_df.empty:
        return _empty_chart("No movers data available")
    
    # Prepare data
    chart_data = []
    
    # Top gainers
    for _, row in gainers_df.head(top_n).iterrows():
        chart_data.append({
            'name': row[label_col][:25],  # Truncate long names
            'value': row['change'],
            'type': 'Gainer',
            'display_value': row['change']
        })
    
    # Top decliners (use absolute value for display but keep negative for sorting)
    for _, row in decliners_df.head(top_n).iterrows():
        chart_data.append({
            'name': row[label_col][:25],
            'value': row['change'],  # Keep negative
            'type': 'Decliner',
            'display_value': row['change']
        })
    
    if not chart_data:
        return _empty_chart("No movers data available")
    
    df = pd.DataFrame(chart_data)
    
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X('value:Q', title='Change ($)', axis=alt.Axis(format='~s')),
        y=alt.Y('name:N', sort='-x', title=None, axis=alt.Axis(labelLimit=150)),
        color=alt.Color(
            'type:N',
            scale=alt.Scale(
                domain=['Gainer', 'Decliner'],
                range=[GROWTH_COLORS['gainer'], GROWTH_COLORS['decliner']]
            ),
            legend=alt.Legend(title='Type', orient='top')
        ),
        tooltip=[
            alt.Tooltip('name:N', title='Name'),
            alt.Tooltip('value:Q', title='Change', format='$,.0f'),
            alt.Tooltip('type:N', title='Type')
        ]
    ).properties(
        width='container',
        height=350,
        title=title
    )
    
    return chart


def build_waterfall_chart(
    compare_df: pd.DataFrame,
    label_col: str,
    title: str = "Growth Contribution",
    top_n: int = 10
) -> alt.Chart:
    """
    Build waterfall-style chart showing contribution to growth.
    
    Shows: Previous Total -> Top Contributors -> Current Total
    """
    if compare_df.empty:
        return _empty_chart("No data available")
    
    # Get top positive and negative contributors
    sorted_df = compare_df.sort_values('change', key=abs, ascending=False)
    top_contributors = sorted_df.head(top_n).copy()
    
    # Calculate totals
    total_previous = compare_df['previous'].sum()
    total_current = compare_df['current'].sum()
    others_change = compare_df['change'].sum() - top_contributors['change'].sum()
    
    # Build waterfall data
    waterfall_data = []
    running_total = total_previous
    
    # Starting point
    waterfall_data.append({
        'name': 'Previous',
        'start': 0,
        'end': total_previous,
        'value': total_previous,
        'type': 'total'
    })
    
    # Add contributors sorted by change (positive first, then negative)
    for _, row in top_contributors.sort_values('change', ascending=False).iterrows():
        change = row['change']
        waterfall_data.append({
            'name': row[label_col][:20],
            'start': running_total,
            'end': running_total + change,
            'value': change,
            'type': 'increase' if change >= 0 else 'decrease'
        })
        running_total += change
    
    # Others
    if abs(others_change) > 0:
        waterfall_data.append({
            'name': 'Others',
            'start': running_total,
            'end': running_total + others_change,
            'value': others_change,
            'type': 'increase' if others_change >= 0 else 'decrease'
        })
        running_total += others_change
    
    # End point
    waterfall_data.append({
        'name': 'Current',
        'start': 0,
        'end': total_current,
        'value': total_current,
        'type': 'total'
    })
    
    df = pd.DataFrame(waterfall_data)
    
    # Create order for x-axis
    df['order'] = range(len(df))
    
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X('name:N', sort=alt.EncodingSortField(field='order'), title=None,
                axis=alt.Axis(labelAngle=-45, labelLimit=100)),
        y=alt.Y('start:Q', title='Value ($)', axis=alt.Axis(format='~s')),
        y2='end:Q',
        color=alt.Color(
            'type:N',
            scale=alt.Scale(
                domain=['total', 'increase', 'decrease'],
                range=['#4a90d9', GROWTH_COLORS['gainer'], GROWTH_COLORS['decliner']]
            ),
            legend=alt.Legend(title='Type', orient='top')
        ),
        tooltip=[
            alt.Tooltip('name:N', title='Name'),
            alt.Tooltip('value:Q', title='Value', format='$,.0f'),
        ]
    ).properties(
        width='container',
        height=350,
        title=title
    )
    
    return bars


def build_new_lost_chart(
    new_df: pd.DataFrame,
    lost_df: pd.DataFrame,
    label_col: str,
    title: str = "New vs Lost",
    top_n: int = 10
) -> alt.Chart:
    """
    Build grouped bar chart comparing new and lost items.
    """
    if new_df.empty and lost_df.empty:
        return _empty_chart("No new/lost data available")
    
    # Calculate summary metrics
    total_new = new_df['current'].sum() if not new_df.empty else 0
    total_lost = lost_df['previous'].sum() if not lost_df.empty else 0
    net = total_new - total_lost
    
    # Summary chart data
    summary_data = pd.DataFrame([
        {'Category': 'New', 'Value': total_new, 'Type': 'New'},
        {'Category': 'Lost', 'Value': -total_lost, 'Type': 'Lost'},  # Negative for visual
        {'Category': 'Net Impact', 'Value': net, 'Type': 'Net'}
    ])
    
    chart = alt.Chart(summary_data).mark_bar().encode(
        x=alt.X('Category:N', title=None, sort=['New', 'Lost', 'Net Impact'],
                axis=alt.Axis(labelAngle=0)),
        y=alt.Y('Value:Q', title='Value ($)', axis=alt.Axis(format='~s')),
        color=alt.Color(
            'Type:N',
            scale=alt.Scale(
                domain=['New', 'Lost', 'Net'],
                range=[GROWTH_COLORS['new'], GROWTH_COLORS['lost'], '#666666']
            ),
            legend=None
        ),
        tooltip=[
            alt.Tooltip('Category:N', title='Category'),
            alt.Tooltip('Value:Q', title='Value', format='$,.0f'),
        ]
    ).properties(
        width='container',
        height=200,
        title=title
    )
    
    # Add text labels
    text = alt.Chart(summary_data).mark_text(
        align='center',
        baseline='bottom',
        dy=-5,
        fontSize=12,
        fontWeight='bold'
    ).encode(
        x=alt.X('Category:N', sort=['New', 'Lost', 'Net Impact']),
        y=alt.Y('Value:Q'),
        text=alt.Text('Value:Q', format='$,.0f'),
        color=alt.value(TEXT_COLOR)
    )
    
    return chart + text


def build_status_distribution_chart(
    compare_df: pd.DataFrame,
    title: str = "Status Distribution"
) -> alt.Chart:
    """
    Build donut chart showing distribution of statuses.
    """
    if compare_df.empty:
        return _empty_chart("No data available")
    
    # Count by status
    status_counts = compare_df['status'].value_counts().reset_index()
    status_counts.columns = ['status', 'count']
    
    # Define colors
    status_colors = {
        '🆕 New': GROWTH_COLORS['new'],
        '❌ Lost': GROWTH_COLORS['decliner'],
        '📈 Growing': GROWTH_COLORS['gainer'],
        '📉 Declining': '#ff9896',
        '➡️ Stable': '#c7c7c7'
    }
    
    status_counts['color'] = status_counts['status'].map(status_colors)
    
    chart = alt.Chart(status_counts).mark_arc(innerRadius=50).encode(
        theta=alt.Theta('count:Q'),
        color=alt.Color(
            'status:N',
            scale=alt.Scale(
                domain=list(status_colors.keys()),
                range=list(status_colors.values())
            ),
            legend=alt.Legend(title='Status', orient='right')
        ),
        tooltip=[
            alt.Tooltip('status:N', title='Status'),
            alt.Tooltip('count:Q', title='Count')
        ]
    ).properties(
        width=250,
        height=250,
        title=title
    )
    
    return chart


# =============================================================================
# HELPER
# =============================================================================

def _empty_chart(message: str = "No data available") -> alt.Chart:
    """Create placeholder chart when no data."""
    return alt.Chart(pd.DataFrame({'note': [message]})).mark_text(
        text=message, fontSize=16, color='#666666'
    ).properties(width=400, height=200)