# utils/salesperson_performance/constants.py
"""
Constants for Salesperson Performance Module

Centralized configuration for:
- Role definitions
- Color schemes
- Chart settings
- KPI configurations
- Period definitions

CHANGELOG:
- v1.2.0: Added 'LY' (Last Year) period type for quick last year selection
- v1.1.0: Added gross_profit_1 KPI type support (GP1 = GP - Broker Commission * 1.2)
"""

# =====================================================================
# ROLE DEFINITIONS
# =====================================================================

# Full access: can view all salespeople across all entities
FULL_ACCESS_ROLES = ['admin', 'GM', 'MD']

# Team access: can view self + direct/indirect reports
TEAM_ACCESS_ROLES = ['sales_manager']

# Self access: can only view own data
SELF_ACCESS_ROLES = ['sales', 'viewer']

# =====================================================================
# COLOR SCHEME
# =====================================================================

COLORS = {
    # Primary metrics
    "revenue": "#FFA500",              # Orange
    "gross_profit": "#1f77b4",         # Blue
    "gp1": "#2ca02c",                  # Green
    "gross_profit_1": "#2ca02c",       # Green (same as gp1)
    "gross_profit_percent": "#800080", # Purple
    
    # Target & Achievement
    "target": "#d62728",               # Red
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
    
    # Misc
    "text_dark": "#333333",
    "text_light": "#666666",
    "grid": "#e0e0e0",
}

# =====================================================================
# MONTH ORDER
# =====================================================================

MONTH_ORDER = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]

# =====================================================================
# PERIOD DEFINITIONS
# =====================================================================

# UPDATED v1.2.0: Added 'LY' for Last Year quick selection
PERIOD_TYPES = ['YTD', 'QTD', 'MTD', 'LY', 'Custom']

QUARTER_MONTHS = {
    1: [1, 2, 3],
    2: [4, 5, 6],
    3: [7, 8, 9],
    4: [10, 11, 12]
}

# =====================================================================
# KPI CONFIGURATIONS
# =====================================================================

KPI_TYPES = {
    "revenue": {
        "name": "revenue",
        "display_name": "Revenue",
        "unit": "USD",
        "format": "${:,.0f}",
        "icon": "💰"
    },
    "gross_profit": {
        "name": "gross_profit",
        "display_name": "Gross Profit",
        "unit": "USD",
        "format": "${:,.0f}",
        "icon": "📈"
    },
    # NEW: GP1 KPI type (added 2025-12-17)
    # GP1 = Gross Profit - (Broker Commission * 1.2)
    "gross_profit_1": {
        "name": "gross_profit_1",
        "display_name": "GP1",
        "unit": "USD",
        "format": "${:,.0f}",
        "icon": "📊"
    },
    "num_new_customers": {
        "name": "num_new_customers",
        "display_name": "New Customers",
        "unit": "customer",
        "format": "{:.1f}",
        "icon": "👥"
    },
    "num_new_products": {
        "name": "num_new_products",
        "display_name": "New Products",
        "unit": "product",
        "format": "{:.1f}",
        "icon": "📦"
    },
    "new_business_revenue": {
        "name": "new_business_revenue",
        "display_name": "New Business Revenue",
        "unit": "USD",
        "format": "${:,.0f}",
        "icon": "💼"
    },
}

# =====================================================================
# BUSINESS LOGIC SETTINGS
# =====================================================================

# Lookback period for "new" customer/product determination
# A customer is "new" if their first invoice is within lookback period
LOOKBACK_YEARS = 5

# =====================================================================
# CHART DIMENSIONS
# =====================================================================

CHART_WIDTH = 800
CHART_HEIGHT = 400

# =====================================================================
# KPI TYPE DEFAULT WEIGHTS - FALLBACK VALUES
# These are used only when database query fails
# Primary source: kpi_types table via queries.get_kpi_type_weights_cached()
# Formula: Overall = Σ(KPI_Type_Achievement × default_weight) / Σ(default_weight)
# =====================================================================

KPI_TYPE_DEFAULT_WEIGHTS_FALLBACK = {
    'revenue': 90,
    'gross_profit': 95,
    'num_new_customers': 60,
    'new_business_revenue': 75,
    'num_new_projects': 50,
    'num_new_products': 50,
    'purchase_value': 80,
    'gross_profit_1': 100,
    'num_new_combos': 55,
}

# =====================================================================
# CACHE SETTINGS
# =====================================================================

CACHE_TTL_SECONDS = 1800  # 30 minutes

# =====================================================================
# EXPORT SETTINGS
# =====================================================================

EXCEL_STYLES = {
    "header_fill_color": "1f77b4",
    "header_font_color": "FFFFFF",
    "currency_format": '#,##0',
    "percent_format": '0.0%',
    "date_format": 'YYYY-MM-DD',
}