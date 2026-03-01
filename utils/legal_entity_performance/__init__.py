# utils/legal_entity_performance/__init__.py
"""
Legal Entity Performance Module
Independent from KPI Center Performance - copy & adapt approach.

VERSION: 2.0.0
- Aligned with kpi_center_performance v6.0.0 patterns
- Same DB access, caching, filter, metric naming conventions
"""

# Core classes
from .data_loader import UnifiedDataLoader
from .data_processor import DataProcessor
from .access_control import AccessControl
from .queries import LegalEntityQueries
from .metrics import LegalEntityMetrics
from .complex_kpi_calculator import ComplexKPICalculator
from .filters import LegalEntityFilters, analyze_period
from .export_utils import LegalEntityExport

# Executive Summary
from .executive_summary import generate_executive_summary, render_executive_summary

# Payment Analysis
from .payment_analysis import analyze_payments, render_payment_section, check_payment_alerts

# Payment Tab
from .payment import payment_tab_fragment

# Tab fragments
from .overview import overview_tab_fragment
from .overview.fragments import monthly_trend_fragment, yoy_comparison_fragment
from .overview.charts import (
    render_kpi_cards,
    render_new_business_cards,
    build_forecast_waterfall_chart,
    build_gap_analysis_chart,
    convert_pipeline_to_backlog_metrics,
    build_yearly_total_chart,
    build_monthly_trend_dual_chart,
    build_cumulative_dual_chart,
    build_yoy_comparison_chart,
    build_yoy_cumulative_chart,
    build_multi_year_monthly_chart,
    build_multi_year_cumulative_chart,
)
from .sales_detail import sales_detail_tab_fragment
from .analysis import analysis_tab_fragment
from .backlog import backlog_tab_fragment

# Common
from .common.charts import empty_chart

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

__all__ = [
    # Core classes
    'UnifiedDataLoader',
    'DataProcessor',
    'AccessControl',
    'LegalEntityQueries',
    'LegalEntityMetrics',
    'ComplexKPICalculator',
    'LegalEntityFilters',
    'LegalEntityExport',
    'analyze_period',
    'generate_executive_summary',
    'render_executive_summary',
    'analyze_payments',
    'render_payment_section',
    'check_payment_alerts',
    'payment_tab_fragment',
    
    # Tab fragments
    'overview_tab_fragment',
    'sales_detail_tab_fragment',
    'analysis_tab_fragment',
    'backlog_tab_fragment',
    
    # Constants
    'ALLOWED_ROLES', 'LOOKBACK_YEARS', 'MIN_DATA_YEAR', 'MAX_FUTURE_YEARS',
    'CACHE_TTL_SECONDS',
    'CACHE_KEY_UNIFIED', 'CACHE_KEY_PROCESSED', 'CACHE_KEY_FILTERS', 'CACHE_KEY_TIMING',
    'PERIOD_TYPES', 'MONTH_ORDER', 'COLORS',
    'CHART_WIDTH', 'CHART_HEIGHT',
    'DEBUG_TIMING', 'DEBUG_QUERY_TIMING',
]

__version__ = '3.1.0'