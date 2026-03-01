# utils/kpi_center_performance/common/fragments.py
"""
Common helper functions for KPI Center Performance fragments.

These are shared utilities used across multiple tab fragments.
"""

import logging
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Clean dataframe for display."""
    if df.empty:
        return df
    
    df = df.copy()
    
    date_cols = ['inv_date', 'oc_date', 'etd', 'first_sale_date']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    str_cols = df.select_dtypes(include=['object']).columns
    df[str_cols] = df[str_cols].fillna('')
    
    return df


def prepare_monthly_summary(sales_df: pd.DataFrame, debug_label: str = "") -> pd.DataFrame:
    """Prepare monthly summary from sales data."""
    from ..constants import MONTH_ORDER
    
    if sales_df.empty:
        return pd.DataFrame()
    
    df = sales_df.copy()
    
    # Ensure invoice_month column
    if 'invoice_month' not in df.columns:
        if 'inv_date' in df.columns:
            df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
            df['invoice_month'] = df['inv_date'].dt.strftime('%b')
        else:
            return pd.DataFrame()
    
    # Aggregate by month
    try:
        monthly = df.groupby('invoice_month').agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in df.columns else 'first',
            'inv_number': pd.Series.nunique,
            'customer_id': pd.Series.nunique
        }).reset_index()
        
        monthly.columns = ['month', 'revenue', 'gross_profit', 'gp1', 'orders', 'customers']
    except Exception as e:
        logger.error(f"Error in prepare_monthly_summary: {e}")
        return pd.DataFrame()
    
    # Add GP%
    monthly['gp_percent'] = (monthly['gross_profit'] / monthly['revenue'] * 100).fillna(0).round(1)
    
    # Sort by month order
    monthly['month_order'] = monthly['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
    monthly = monthly.sort_values('month_order')
    
    return monthly


def format_product_display(row) -> str:
    """Format product as 'pt_code | Name | Package size'."""
    parts = []
    if pd.notna(row.get('pt_code')) and row.get('pt_code'):
        parts.append(str(row['pt_code']))
    if pd.notna(row.get('product_pn')) and row.get('product_pn'):
        parts.append(str(row['product_pn']))
    if pd.notna(row.get('package_size')) and row.get('package_size'):
        parts.append(str(row['package_size']))
    return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))


def format_oc_po(row) -> str:
    """Format OC with Customer PO: 'OC#\\n(PO: xxx)'."""
    oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
    po_col = 'customer_po_number' if 'customer_po_number' in row.index else 'customer_po'
    po = str(row.get(po_col, '')) if pd.notna(row.get(po_col)) else ''
    if oc and po:
        return f"{oc}\n(PO: {po})"
    elif oc:
        return oc
    elif po:
        return f"(PO: {po})"
    return ''


def format_currency(val) -> str:
    """Format currency value with K/M suffix."""
    if pd.isna(val) or val is None:
        return "-"
    if abs(val) >= 1_000_000:
        return f"${val/1_000_000:,.1f}M"
    elif abs(val) >= 1_000:
        return f"${val/1_000:,.0f}K"
    else:
        return f"${val:,.0f}"


def get_rank_display(rank: int) -> str:
    """Get rank display with medals for top 3."""
    if rank == 1:
        return "🥇"
    elif rank == 2:
        return "🥈"
    elif rank == 3:
        return "🥉"
    else:
        return f"#{rank}"
