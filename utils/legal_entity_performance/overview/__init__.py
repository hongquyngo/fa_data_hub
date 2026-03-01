# utils/legal_entity_performance/overview/__init__.py
"""
Overview tab for Legal Entity Performance.
"""

from .fragments import (
    overview_tab_fragment,
    monthly_trend_fragment,
    yoy_comparison_fragment,
)

from .charts import (
    render_kpi_cards,
    render_new_business_cards,
    build_forecast_waterfall_chart,
    build_gap_analysis_chart,
    convert_pipeline_to_backlog_metrics,
    _render_backlog_forecast_section,
    build_yearly_total_chart,
    build_monthly_trend_dual_chart,
    build_cumulative_dual_chart,
    build_yoy_comparison_chart,
    build_yoy_cumulative_chart,
    build_multi_year_monthly_chart,
    build_multi_year_cumulative_chart,
)

__all__ = [
    'overview_tab_fragment',
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'render_kpi_cards',
    'render_new_business_cards',
    'build_forecast_waterfall_chart',
    'build_gap_analysis_chart',
    'convert_pipeline_to_backlog_metrics',
    '_render_backlog_forecast_section',
    'build_yearly_total_chart',
    'build_monthly_trend_dual_chart',
    'build_cumulative_dual_chart',
    'build_yoy_comparison_chart',
    'build_yoy_cumulative_chart',
    'build_multi_year_monthly_chart',
    'build_multi_year_cumulative_chart',
]