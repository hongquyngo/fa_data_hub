# utils/legal_entity_performance/constants.py
"""
Constants for Legal Entity Performance Module
Aligned with kpi_center_performance/constants.py

VERSION: 2.0.0
"""

# =============================================================================
# ROLE DEFINITIONS (synced with KPI center)
# =============================================================================
ALLOWED_ROLES = ['admin', 'GM', 'MD', 'sales_manager']

# =============================================================================
# DATA LOADING SETTINGS (synced with KPI center)
# =============================================================================
LOOKBACK_YEARS = 5
MIN_DATA_YEAR = 2015
MAX_FUTURE_YEARS = 1

# =============================================================================
# CACHE SETTINGS (synced with KPI center)
# =============================================================================
CACHE_TTL_SECONDS = 7200  # 2 hours

# =============================================================================
# SESSION STATE KEYS (prefixed _le_ to avoid collision with KPI center _kpc_)
# =============================================================================
CACHE_KEY_UNIFIED = '_le_unified_cache'
CACHE_KEY_PROCESSED = '_le_processed_data'
CACHE_KEY_FILTERS = '_le_applied_filters'
CACHE_KEY_TIMING = '_le_timing_data'

# =============================================================================
# PERIOD DEFINITIONS (synced with KPI center)
# =============================================================================
PERIOD_TYPES = ['YTD', 'QTD', 'MTD', 'LY', 'Custom']

# =============================================================================
# COLOR SCHEME (synced with KPI center)
# =============================================================================
COLORS = {
    "primary": "#1f77b4",
    "secondary": "#aec7e8",
    "neutral": "#d3d3d3",
    "revenue": "#FFA500",
    "gross_profit": "#1f77b4",
    "gp1": "#2ca02c",
    "gross_profit_percent": "#800080",
    "target": "#d62728",
    "current_year": "#1f77b4",
    "previous_year": "#aec7e8",
    "yoy_positive": "#28a745",
    "yoy_negative": "#dc3545",
    "overdue": "#dc3545",
    "at_risk": "#ffc107",
    "ok": "#28a745",
    "new_customer": "#17becf",
    "achievement_good": "#28a745",
    "achievement_bad": "#dc3545",
    "forecast_line": "#800080",
    "text_dark": "#333333",
    "text_light": "#666666",
    "grid": "#e0e0e0",
}

MONTH_ORDER = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]

# =============================================================================
# CHART DIMENSIONS (synced with KPI center)
# =============================================================================
CHART_WIDTH = 'container'
CHART_HEIGHT = 350

# =============================================================================
# EXPORT SETTINGS (synced with KPI center)
# =============================================================================
EXCEL_STYLES = {
    "header_fill_color": "1f77b4",
    "header_font_color": "FFFFFF",
    "currency_format": '#,##0',
    "percent_format": '0.0%',
    "date_format": 'YYYY-MM-DD',
}

# =============================================================================
# DEBUG SETTINGS (synced with KPI center)
# Use environment variables to enable: LE_DEBUG_TIMING=true / LE_DEBUG_QUERY=true
# =============================================================================
import os as _os
DEBUG_TIMING = _os.getenv('LE_DEBUG_TIMING', 'false').lower() == 'true'
DEBUG_QUERY_TIMING = _os.getenv('LE_DEBUG_QUERY', 'false').lower() == 'true'

# =============================================================================
# METRIC DISPLAY
# =============================================================================
CURRENCY_FORMAT = "${:,.0f}"
PERCENT_FORMAT = "{:.1f}%"
NUMBER_FORMAT = "{:,.0f}"

# =============================================================================
# COLUMN MAPPINGS (unified_sales_by_legal_entity_view → display names)
# =============================================================================
SALES_DISPLAY_COLUMNS = {
    'inv_date': 'Invoice Date',
    'inv_number': 'Invoice #',
    'vat_number': 'VAT #',
    'legal_entity': 'Legal Entity',
    'customer': 'Customer',
    'customer_code': 'Customer Code',
    'product_pn': 'Product',
    'pt_code': 'PT Code',
    'brand': 'Brand',
    'standard_uom': 'UOM',
    'invoiced_quantity': 'Qty',
    'calculated_invoiced_amount_usd': 'Sales (USD)',
    'invoiced_gross_profit_usd': 'GP (USD)',
    'gross_profit_percent': 'GP%',
    'invoiced_gp1_usd': 'GP1 (USD)',
    'broker_commission_usd': 'Commission (USD)',
    'payment_status': 'Payment Status',
    'customer_type': 'Type',
    'cost_source': 'Cost Source',
}

BACKLOG_DISPLAY_COLUMNS = {
    'oc_number': 'OC #',
    'oc_date': 'OC Date',
    'etd': 'ETD',
    'legal_entity': 'Legal Entity',
    'customer': 'Customer',
    'product_pn': 'Product',
    'pt_code': 'PT Code',
    'brand': 'Brand',
    'selling_quantity': 'Order Qty',
    'pending_invoice_selling_quantity': 'Pending Qty',
    'outstanding_amount_usd': 'Backlog (USD)',
    'outstanding_gross_profit_usd': 'Backlog GP (USD)',
    'days_until_etd': 'Days to ETD',
    'pending_type': 'Pending Type',
    'status': 'Status',
    'customer_type': 'Type',
}