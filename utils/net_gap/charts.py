# utils/net_gap/charts.py

"""
Visualization components for GAP Analysis - Optimized Version
Chart heights reduced for better screen utilization
"""

import pandas as pd
import plotly.graph_objects as go
from typing import Optional
import logging

from .constants import GAP_CATEGORIES, UI_CONFIG

logger = logging.getLogger(__name__)


class GAPCharts:
    """Essential visualizations with optimized dimensions"""
    
    def __init__(self, formatter=None):
        self.formatter = formatter
    
    def create_status_donut(self, gap_df: pd.DataFrame) -> go.Figure:
        """Create simplified status donut chart with reduced height"""
        
        if gap_df.empty:
            return self._empty_chart("No data available")
        
        # Count by simplified categories
        categories_data = []
        
        for category, config in GAP_CATEGORIES.items():
            mask = gap_df['gap_status'].isin(config['statuses'])
            count = len(gap_df[mask])
            
            if count > 0:
                categories_data.append({
                    'category': config['label'],
                    'count': count,
                    'color': config['color'],
                    'icon': config['icon']
                })
        
        if not categories_data:
            return self._empty_chart("No items to display")
        
        # Create donut chart
        df = pd.DataFrame(categories_data)
        
        fig = go.Figure(data=[go.Pie(
            values=df['count'],
            labels=df['category'],
            hole=0.6,
            marker=dict(colors=df['color']),
            textinfo='label+percent',
            textposition='outside',
            hovertemplate='<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>'
        )])
        
        # Add center annotation with key metric
        shortage_count = sum(d['count'] for d in categories_data 
                           if d['category'] == 'Shortage')
        total_count = sum(d['count'] for d in categories_data)
        
        fig.add_annotation(
            text=f"<b>{shortage_count}</b><br>Shortage Items",
            x=0.5, y=0.5,
            font=dict(size=18),
            showarrow=False
        )
        
        fig.update_layout(
            title="GAP Distribution",
            height=UI_CONFIG['chart_height_compact'],  # Reduced from 400px to 300px
            showlegend=True,
            margin=dict(t=30, b=30, l=30, r=30)  # Reduced margins
        )
        
        return fig
    
    def create_top_items_bar(
        self, 
        gap_df: pd.DataFrame, 
        chart_type: str = 'shortage',
        top_n: int = 10
    ) -> go.Figure:
        """Create bar chart with dynamic height based on items"""
        
        if gap_df.empty:
            return self._empty_chart("No data available")
        
        # Filter based on type
        if chart_type == 'shortage':
            df = gap_df[gap_df['net_gap'] < 0].copy()
            df['value'] = df['net_gap'].abs()
            title = f"Top {min(top_n, len(df))} Shortage Items"
            color = GAP_CATEGORIES['SHORTAGE']['color']
        else:  # surplus
            df = gap_df[gap_df['net_gap'] > 0].copy()
            df['value'] = df['net_gap']
            title = f"Top {min(top_n, len(df))} Surplus Items"
            color = GAP_CATEGORIES['SURPLUS']['color']
        
        if df.empty:
            return self._empty_chart(f"No {chart_type} items found")
        
        # Get top N
        df = df.nlargest(min(top_n, len(df)), 'value')
        
        # Prepare display names (shorter for compact display)
        if 'product_name' in df.columns:
            df['display'] = df.apply(
                lambda x: f"{x.get('pt_code', '')} - {x.get('product_name', '')[:25]}",
                axis=1
            )
        else:
            df['display'] = df.index.astype(str)
        
        # Create bar chart
        fig = go.Figure(data=[
            go.Bar(
                x=df['value'],
                y=df['display'],
                orientation='h',
                marker=dict(color=color),
                text=df['value'].apply(lambda x: f"{x:,.0f}"),
                textposition='outside',
                hovertemplate='<b>%{y}</b><br>Quantity: %{x:,.0f}<extra></extra>'
            )
        ])
        
        # Dynamic height calculation: min 250px, max 400px
        dynamic_height = min(400, max(250, len(df) * 35))
        
        fig.update_layout(
            title=title,
            xaxis_title=f"{chart_type.title()} Quantity",
            yaxis=dict(autorange="reversed"),
            height=dynamic_height,
            margin=dict(l=180, r=80, t=40, b=40)  # Reduced margins
        )
        
        return fig
    
    def create_value_analysis(self, gap_df: pd.DataFrame) -> go.Figure:
        """Create value at risk analysis chart with optimized height"""
        
        if gap_df.empty or 'at_risk_value_usd' not in gap_df.columns:
            return self._empty_chart("No value data available")
        
        # Get top items by at-risk value
        risk_df = gap_df[gap_df['at_risk_value_usd'] > 0].copy()
        
        if risk_df.empty:
            return self._empty_chart("No items with value at risk")
        
        # Get top 15 items
        risk_df = risk_df.nlargest(min(15, len(risk_df)), 'at_risk_value_usd')
        
        # Prepare display (more compact)
        if 'product_name' in risk_df.columns:
            risk_df['display'] = risk_df.apply(
                lambda x: f"{x.get('pt_code', '')} - {x.get('product_name', '')[:20]}",
                axis=1
            )
        else:
            risk_df['display'] = risk_df.index.astype(str)
        
        # Create bar chart
        fig = go.Figure(data=[
            go.Bar(
                x=risk_df['at_risk_value_usd'],
                y=risk_df['display'],
                orientation='h',
                marker=dict(
                    color=risk_df['at_risk_value_usd'],
                    colorscale='Reds',
                    showscale=True,
                    colorbar=dict(
                        title="USD",
                        thickness=15,
                        len=0.7
                    )
                ),
                text=risk_df['at_risk_value_usd'].apply(lambda x: f"${x:,.0f}"),
                textposition='outside',
                hovertemplate='<b>%{y}</b><br>At Risk: $%{x:,.0f}<extra></extra>'
            )
        ])
        
        # Dynamic height with limits
        dynamic_height = min(400, max(280, len(risk_df) * 32))
        
        fig.update_layout(
            title="Top Items by Value at Risk",
            xaxis_title="Value at Risk (USD)",
            yaxis=dict(autorange="reversed"),
            height=dynamic_height,
            margin=dict(l=180, r=100, t=40, b=40)
        )
        
        return fig
    
    def _empty_chart(self, message: str) -> go.Figure:
        """Create empty chart with message"""
        fig = go.Figure()
        
        fig.add_annotation(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14, color="gray")
        )
        
        fig.update_layout(
            height=UI_CONFIG['chart_height_compact'],
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        
        return fig