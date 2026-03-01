# utils/salesperson_performance/__init__.py
"""
Salesperson Performance Module

Isolated utilities for salesperson performance tracking page.
All components are self-contained within this module.

Components:
- access_control: Role-based data access (sales/manager/admin)
- queries: SQL queries and data loading with caching
- metrics: KPI calculations and aggregations
- filters: Sidebar filter components
- charts: Altair visualizations
- export: Formatted Excel report generation

Usage:
    from utils.salesperson_performance import (
        AccessControl,
        SalespersonQueries,
        SalespersonMetrics,
        SalespersonFilters,
        SalespersonCharts,
        SalespersonExport,
        CONSTANTS
    )
"""

from .access_control import AccessControl
from .queries import SalespersonQueries
from .metrics import SalespersonMetrics
from .filters import SalespersonFilters
from .charts import SalespersonCharts
from .export import SalespersonExport

# Fragments
from .fragments import kpi_progress_fragment

# Constants
from .constants import (
    COLORS,
    MONTH_ORDER,
    PERIOD_TYPES,
    KPI_TYPES,
    FULL_ACCESS_ROLES,
    TEAM_ACCESS_ROLES,
    SELF_ACCESS_ROLES,
    LOOKBACK_YEARS,
    CHART_WIDTH,
    CHART_HEIGHT,
)

__all__ = [
    # Classes
    'AccessControl',
    'SalespersonQueries',
    'SalespersonMetrics',
    'SalespersonFilters',
    'SalespersonCharts',
    'SalespersonExport',
    
    # Fragments
    'kpi_progress_fragment',
    
    # Constants
    'COLORS',
    'MONTH_ORDER',
    'PERIOD_TYPES',
    'KPI_TYPES',
    'FULL_ACCESS_ROLES',
    'TEAM_ACCESS_ROLES',
    'SELF_ACCESS_ROLES',
    'LOOKBACK_YEARS',
    'CHART_WIDTH',
    'CHART_HEIGHT',
]

__version__ = '3.3.0'