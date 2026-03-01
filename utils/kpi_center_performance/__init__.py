# utils/kpi_center_performance/__init__.py
"""
KPI Center Performance Module

VERSION: 6.0.0
CHANGELOG:
- v6.0.0: Unified Analysis tab (Top Performers + Concentration + Mix)
  - Removed build_top_performers_chart (unused)
  - Simplified analysis exports
- v5.0.0: New single-selection KPI Center tree selector
- v4.6.0: Added overview_tab_fragment as main Overview tab entry point
"""

# =============================================================================
# CORE CLASSES
# =============================================================================

from .data_loader import UnifiedDataLoader
from .data_processor import DataProcessor
from .access_control import AccessControl
from .queries import KPICenterQueries
from .metrics import KPICenterMetrics

# Filters
from .filters import (
    KPICenterFilters,
    analyze_period,
    FilterResult,
    render_multiselect_filter,
    apply_multiselect_filter,
    TextSearchResult,
    render_text_search_filter,
    apply_text_search_filter,
    NumberRangeResult,
    render_number_filter,
    apply_number_filter,
    clear_data_cache,
)

# KPI Center Selector
from .kpi_center_selector import (
    KPICenterNode,
    KPICenterSelection,
    KPICenterTreeBuilder,
    render_kpi_center_selector,
    get_kpi_center_selection_ids,
)

# =============================================================================
# CHARTS
# =============================================================================

from .common.charts import (
    empty_chart,
    convert_pipeline_to_backlog_metrics,
)

from .overview.charts import (
    render_kpi_cards,
    build_monthly_trend_dual_chart,
    build_cumulative_dual_chart,
    build_yoy_comparison_chart,
    build_yoy_cumulative_chart,
    build_multi_year_monthly_chart,
    build_multi_year_cumulative_chart,
    build_forecast_waterfall_chart,
    build_gap_analysis_chart,
)

from .analysis.charts import (
    build_pareto_chart,
    build_growth_comparison_chart,
)

from .backlog.charts import (
    build_backlog_by_month_chart,
    build_backlog_by_month_chart_multiyear,
    build_backlog_by_month_stacked,
)


# Backward compatibility wrapper class
class KPICenterCharts:
    """Backward compatibility wrapper for chart functions."""
    # Common
    empty_chart = staticmethod(empty_chart)
    convert_pipeline_to_backlog_metrics = staticmethod(convert_pipeline_to_backlog_metrics)
    
    # Overview
    render_kpi_cards = staticmethod(render_kpi_cards)
    build_monthly_trend_dual_chart = staticmethod(build_monthly_trend_dual_chart)
    build_cumulative_dual_chart = staticmethod(build_cumulative_dual_chart)
    build_yoy_comparison_chart = staticmethod(build_yoy_comparison_chart)
    build_yoy_cumulative_chart = staticmethod(build_yoy_cumulative_chart)
    build_multi_year_monthly_chart = staticmethod(build_multi_year_monthly_chart)
    build_multi_year_cumulative_chart = staticmethod(build_multi_year_cumulative_chart)
    
    # Analysis
    build_pareto_chart = staticmethod(build_pareto_chart)
    build_growth_comparison_chart = staticmethod(build_growth_comparison_chart)
    
    # Backlog
    build_forecast_waterfall_chart = staticmethod(build_forecast_waterfall_chart)
    build_gap_analysis_chart = staticmethod(build_gap_analysis_chart)
    build_backlog_by_month_chart = staticmethod(build_backlog_by_month_chart)
    build_backlog_by_month_chart_multiyear = staticmethod(build_backlog_by_month_chart_multiyear)
    build_backlog_by_month_stacked = staticmethod(build_backlog_by_month_stacked)


# Export
from .export import KPICenterExport

# =============================================================================
# FRAGMENTS
# =============================================================================

from .common.fragments import prepare_monthly_summary

from .overview.fragments import (
    overview_tab_fragment,
    monthly_trend_fragment,
    yoy_comparison_fragment,
    export_report_fragment,
)

from .sales_detail.fragments import (
    sales_detail_fragment,
    pivot_analysis_fragment,
    sales_detail_tab_fragment,
)

from .analysis.fragments import analysis_tab_fragment

from .backlog.fragments import (
    backlog_list_fragment,
    backlog_by_etd_fragment,
    backlog_risk_analysis_fragment,
    backlog_tab_fragment,
)

from .kpi_targets.fragments import (
    kpi_assignments_fragment,
    kpi_progress_fragment,
    kpi_center_ranking_fragment,
)

from .setup import (
    SetupQueries,
    setup_tab_fragment,
    split_rules_section,
    hierarchy_section,
)

# Calculators
from .backlog_calculator import BacklogCalculator
from .complex_kpi_calculator import ComplexKPICalculator

# Constants
from .constants import (
    ALLOWED_ROLES,
    LOOKBACK_YEARS,
    MIN_DATA_YEAR,
    MAX_FUTURE_YEARS,
    CACHE_TTL_SECONDS,
    CACHE_KEY_UNIFIED,
    CACHE_KEY_PROCESSED,
    CACHE_KEY_FILTERS,
    CACHE_KEY_TIMING,
    PERIOD_TYPES,
    MONTH_ORDER,
    COLORS,
    CHART_WIDTH,
    CHART_HEIGHT,
    DEBUG_TIMING,
    DEBUG_QUERY_TIMING,
)

# =============================================================================
# ALL EXPORTS
# =============================================================================

__all__ = [
    # Core classes
    'UnifiedDataLoader',
    'DataProcessor',
    'AccessControl',
    'KPICenterQueries',
    'KPICenterMetrics',
    'KPICenterFilters',
    'KPICenterCharts',
    'KPICenterExport',
    
    # Setup
    'SetupQueries',
    
    # Calculators
    'BacklogCalculator',
    'ComplexKPICalculator',
    
    # Filter classes & functions
    'FilterResult',
    'TextSearchResult',
    'NumberRangeResult',
    'analyze_period',
    'render_multiselect_filter',
    'apply_multiselect_filter',
    'render_text_search_filter',
    'apply_text_search_filter',
    'render_number_filter',
    'apply_number_filter',
    'clear_data_cache',
    
    # KPI Center Selector
    'KPICenterNode',
    'KPICenterSelection',
    'KPICenterTreeBuilder',
    'render_kpi_center_selector',
    'get_kpi_center_selection_ids',
    
    # Charts
    'empty_chart',
    'convert_pipeline_to_backlog_metrics',
    'render_kpi_cards',
    'build_monthly_trend_dual_chart',
    'build_cumulative_dual_chart',
    'build_yoy_comparison_chart',
    'build_yoy_cumulative_chart',
    'build_multi_year_monthly_chart',
    'build_multi_year_cumulative_chart',
    'build_pareto_chart',
    'build_growth_comparison_chart',
    'build_forecast_waterfall_chart',
    'build_gap_analysis_chart',
    'build_backlog_by_month_chart',
    'build_backlog_by_month_chart_multiyear',
    'build_backlog_by_month_stacked',
    
    # Fragments - Overview
    'overview_tab_fragment',
    'prepare_monthly_summary',
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'export_report_fragment',
    
    # Fragments - Sales Detail
    'sales_detail_fragment',
    'pivot_analysis_fragment',
    'sales_detail_tab_fragment',
    
    # Fragments - Analysis
    'analysis_tab_fragment',
    
    # Fragments - Backlog
    'backlog_list_fragment',
    'backlog_by_etd_fragment',
    'backlog_risk_analysis_fragment',
    'backlog_tab_fragment',
    
    # Fragments - KPI Targets
    'kpi_assignments_fragment',
    'kpi_progress_fragment',
    'kpi_center_ranking_fragment',
    
    # Fragments - Setup
    'setup_tab_fragment',
    'split_rules_section',
    'hierarchy_section',
    
    # Constants
    'ALLOWED_ROLES',
    'LOOKBACK_YEARS',
    'MIN_DATA_YEAR',
    'MAX_FUTURE_YEARS',
    'CACHE_TTL_SECONDS',
    'CACHE_KEY_UNIFIED',
    'CACHE_KEY_PROCESSED',
    'CACHE_KEY_FILTERS',
    'CACHE_KEY_TIMING',
    'PERIOD_TYPES',
    'MONTH_ORDER',
    'COLORS',
    'CHART_WIDTH',
    'CHART_HEIGHT',
    'DEBUG_TIMING',
    'DEBUG_QUERY_TIMING',
]

__version__ = '6.0.0'