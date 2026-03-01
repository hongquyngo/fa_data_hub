# utils/legal_entity_performance/analysis/__init__.py
"""Analysis tab module for Legal Entity Performance. VERSION: 2.0.0"""

from .fragments import analysis_tab_fragment
from .charts import (
    build_pareto_chart,
    build_growth_comparison_chart,
    build_movers_bar_chart,
    build_waterfall_chart,
    build_new_lost_chart,
    build_status_distribution_chart,
)

__all__ = [
    'analysis_tab_fragment',
    'build_pareto_chart',
    'build_growth_comparison_chart',
    'build_movers_bar_chart',
    'build_waterfall_chart',
    'build_new_lost_chart',
    'build_status_distribution_chart',
]