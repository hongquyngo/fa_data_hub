# utils/kpi_center_performance/constants.py
"""
Constants for KPI Center Performance Module

VERSION: 4.0.0
CHANGELOG:
- v4.0.0: Unified data loading architecture
  - Added DATA_LOADING_SETTINGS section
  - Added SESSION_STATE_KEYS section
  - Centralized all previously hard-coded values
"""

# =============================================================================
# ROLE DEFINITIONS
# =============================================================================

# Roles allowed to access this page
ALLOWED_ROLES = ['admin', 'GM', 'MD', 'sales_manager']

# =============================================================================
# DATA LOADING SETTINGS - NEW v4.0.0
# =============================================================================

# Lookback period for all data (sales, targets, complex KPIs)
# Used to determine "new" customer/product (first sale within lookback period)
LOOKBACK_YEARS = 5

# Minimum year for data loading (safety floor)
# NOTE: Actual data in DB starts from 2015
MIN_DATA_YEAR = 2015

# Maximum future years to include (for targets/forecasts)
MAX_FUTURE_YEARS = 1

# =============================================================================
# CACHE SETTINGS
# =============================================================================

# Cache TTL in seconds (2 hours)
CACHE_TTL_SECONDS = 7200

# =============================================================================
# SESSION STATE KEYS - NEW v4.0.0
# =============================================================================

# Unified raw data cache key
CACHE_KEY_UNIFIED = '_kpc_unified_cache'

# Processed data cache key (after filtering)
CACHE_KEY_PROCESSED = '_kpc_processed_data'

# Applied filters cache key
CACHE_KEY_FILTERS = '_kpc_applied_filters'

# Timing data key
CACHE_KEY_TIMING = '_kpc_timing_data'

# =============================================================================
# COLOR SCHEME - SYNCED with Salesperson page
# =============================================================================

COLORS = {
    # Primary colors for charts
    "primary": "#1f77b4",              # Blue
    "secondary": "#aec7e8",            # Light Blue
    "neutral": "#d3d3d3",              # Light Gray
    
    # Metric colors
    "revenue": "#FFA500",              # Orange
    "gross_profit": "#1f77b4",         # Blue
    "gp1": "#2ca02c",                  # Green
    "gross_profit_1": "#2ca02c",       # Green (same as gp1)
    "gross_profit_percent": "#800080", # Purple
    
    # Target & Achievement
    "target": "#d62728",               # Red
    "achievement": "#2ca02c",          # Green
    "achievement_good": "#28a745",     # Green (≥100%)
    "achievement_bad": "#dc3545",      # Red (<100%)
    
    # Complex KPIs
    "new_customer": "#17becf",         # Cyan
    "new_product": "#bcbd22",          # Olive
    "new_business": "#e377c2",         # Pink
    
    # YoY Comparison
    "current_year": "#1f77b4",         # Blue
    "previous_year": "#aec7e8",        # Light Blue
    "yoy_positive": "#28a745",         # Green
    "yoy_negative": "#dc3545",         # Red
    
    # Customer count
    "customer_count": "#27ae60",       # Green
    
    # Risk indicators
    "overdue": "#dc3545",              # Red
    "at_risk": "#ffc107",              # Yellow
    "ok": "#28a745",                   # Green
    
    # Misc
    "text_dark": "#333333",
    "text_light": "#666666",
    "grid": "#e0e0e0",
}

# =============================================================================
# MONTH ORDER
# =============================================================================

MONTH_ORDER = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]

# =============================================================================
# PERIOD DEFINITIONS
# =============================================================================

PERIOD_TYPES = ['YTD', 'QTD', 'MTD', 'LY', 'Custom']

# KPI Center Types - REMOVED v4.1.0 (unused)

# =============================================================================
# CHART DIMENSIONS
# =============================================================================

CHART_WIDTH = 'container'  # Use container width for responsive charts
CHART_HEIGHT = 350

# =============================================================================
# EXPORT SETTINGS
# =============================================================================

EXCEL_STYLES = {
    "header_fill_color": "1f77b4",
    "header_font_color": "FFFFFF",
    "currency_format": '#,##0',
    "percent_format": '0.0%',
    "date_format": 'YYYY-MM-DD',
}

# =============================================================================
# DEBUG SETTINGS
# =============================================================================

# Set to True to see timing output in terminal
DEBUG_TIMING = True
DEBUG_QUERY_TIMING = True