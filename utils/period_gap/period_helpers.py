# utils/period_gap/period_helpers.py
"""
Helper Functions for Period GAP Analysis
Period manipulation, data preparation, and display formatting
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict
import logging

logger = logging.getLogger(__name__)

# === PERIOD CONVERSION FUNCTIONS ===

def convert_to_period(date_value, period_type: str) -> Optional[str]:
    """
    Convert date to period string
    
    Args:
        date_value: Date value (single date or series)
        period_type: Type of period ('Daily', 'Weekly', 'Monthly')
    
    Returns:
        Period string or None if invalid
    """
    try:
        if pd.isna(date_value):
            return None
        
        date_val = pd.to_datetime(date_value, errors='coerce')
        if pd.isna(date_val):
            return None
        
        if period_type == "Daily":
            return date_val.strftime('%Y-%m-%d')
        elif period_type == "Weekly":
            # FIXED: Use ISO calendar year to handle year-end weeks correctly
            # isocalendar() returns (iso_year, week_number, weekday)
            # iso_year correctly handles weeks that span year boundaries
            iso_year, week_num, _ = date_val.isocalendar()
            return f"Week {week_num} - {iso_year}"
        elif period_type == "Monthly":
            return date_val.strftime('%b %Y')
        else:
            # Fallback for any other period type
            return str(date_val)
    except Exception as e:
        logger.debug(f"Error converting date to period: {e}")
        return None

def parse_week_period(period_str: str) -> Tuple[int, int]:
    """
    Parse week period string for sorting
    
    Args:
        period_str: Week period string (e.g., "Week 5 - 2024")
    
    Returns:
        Tuple of (year, week) for sorting
    """
    try:
        if pd.isna(period_str) or not period_str:
            return (9999, 99)
        
        period_str = str(period_str).strip()
        
        # Handle standard format "Week X - YYYY"
        if " - " in period_str:
            parts = period_str.split(" - ")
            if len(parts) == 2 and parts[0].startswith("Week "):
                week_str = parts[0].replace("Week ", "").strip()
                year_str = parts[1].strip()
                
                week = int(week_str)
                year = int(year_str)
                
                if 1 <= week <= 53:
                    return (year, week)
    except (ValueError, AttributeError) as e:
        logger.debug(f"Error parsing week period '{period_str}': {e}")
    
    return (9999, 99)


def parse_month_period(period_str: str) -> pd.Timestamp:
    """
    Parse month period string for sorting
    
    Args:
        period_str: Month period string (e.g., "Jan 2024")
    
    Returns:
        Timestamp for sorting
    """
    try:
        if pd.isna(period_str) or not period_str:
            return pd.Timestamp.max
        
        period_str = str(period_str).strip()
        return pd.to_datetime(f"01 {period_str}", format="%d %b %Y")
    except Exception as e:
        logger.debug(f"Error parsing month period '{period_str}': {e}")
        return pd.Timestamp.max


def is_past_period(period_str: str, period_type: str, 
                   reference_date: Optional[datetime] = None) -> bool:
    """
    Check if a period string represents a past period
    
    Args:
        period_str: Period string to check
        period_type: Type of period
        reference_date: Reference date for comparison (default: today)
    
    Returns:
        True if period is in the past
    """
    if reference_date is None:
        reference_date = datetime.now()
    
    try:
        if pd.isna(period_str) or not period_str:
            return False
        
        period_str = str(period_str).strip()
        
        if period_type == "Daily":
            period_date = pd.to_datetime(period_str, errors='coerce')
            if pd.notna(period_date):
                return period_date.date() < reference_date.date()
        
        elif period_type == "Weekly":
            year, week = parse_week_period(period_str)
            if year < 9999:
                jan4 = datetime(year, 1, 4)
                week_start = jan4 - timedelta(days=jan4.isoweekday() - 1)
                target_week_start = week_start + timedelta(weeks=week - 1)
                target_week_end = target_week_start + timedelta(days=6)
                return target_week_end.date() < reference_date.date()
        
        elif period_type == "Monthly":
            period_date = parse_month_period(period_str)
            if period_date != pd.Timestamp.max:
                next_month = period_date + pd.DateOffset(months=1)
                return next_month.date() <= reference_date.date()
    
    except Exception as e:
        logger.debug(f"Error checking if period is past: {e}")
    
    return False


def format_period_with_dates(period_str: str, period_type: str) -> str:
    """
    Format period string with date range (WITHOUT past indicator)
    E.g., "Week 41 - 2025" -> "Week 41 (Oct 06 - Oct 12, 2025)"
    
    Args:
        period_str: Period string
        period_type: Type of period
    
    Returns:
        Formatted period string with date range
    """
    try:
        clean_period = str(period_str).strip()
        
        if period_type == "Weekly" and "Week" in clean_period:
            if " - " in clean_period:
                parts = clean_period.split(" - ")
                week_part = parts[0].replace("Week ", "").strip()
                year = int(parts[1].strip())
                week = int(week_part)
                
                # Calculate the date range for this week (ISO week)
                jan4 = datetime(year, 1, 4)
                week_start = jan4 - timedelta(days=jan4.isoweekday() - 1)
                target_week_start = week_start + timedelta(weeks=week - 1)
                target_week_end = target_week_start + timedelta(days=6)
                
                # Format the dates
                start_str = target_week_start.strftime("%b %d")
                end_str = target_week_end.strftime("%b %d, %Y")
                
                return f"Week {week} ({start_str} - {end_str})"
        
        elif period_type == "Monthly":
            try:
                date = pd.to_datetime(f"01 {clean_period}", format="%d %b %Y")
                
                # Get last day of month
                next_month = date + pd.DateOffset(months=1)
                last_day = next_month - pd.DateOffset(days=1)
                
                start_str = date.strftime("%b %d")
                end_str = last_day.strftime("%b %d, %Y")
                
                return f"{clean_period} ({start_str} - {end_str})"
            except:
                pass
        
        elif period_type == "Daily":
            try:
                date = pd.to_datetime(clean_period, errors='coerce')
                if pd.notna(date):
                    formatted_date = date.strftime("%Y-%m-%d (%a)")
                    return formatted_date
            except:
                pass
            
    except Exception as e:
        logger.debug(f"Error formatting period with dates: {e}")
    
    return str(period_str).strip()


# === DATE COLUMN HELPERS ===

def get_demand_date_column(df: pd.DataFrame) -> str:
    """Get demand date column (always 'etd' for simplified version)"""
    return 'etd'


def get_supply_date_column(df: pd.DataFrame, source_type: str) -> str:
    """
    Get appropriate supply date column based on source type
    
    Args:
        df: Supply dataframe
        source_type: Type of supply source
    
    Returns:
        Date column name
    """
    date_mapping = {
        'Inventory': 'date_ref',
        'Pending CAN': 'arrival_date',
        'Pending PO': 'eta',
        'Pending WH Transfer': 'transfer_date'
    }
    
    return date_mapping.get(source_type, 'date_ref')


# === DISPLAY PREPARATION FUNCTIONS ===

def prepare_gap_detail_display(
    display_df: pd.DataFrame, 
    display_filters: dict,
    df_demand_filtered: Optional[pd.DataFrame] = None,
    df_supply_filtered: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Prepare GAP dataframe for detail display
    
    Args:
        display_df: GAP analysis results
        display_filters: Display filter options
        df_demand_filtered: Filtered demand data
        df_supply_filtered: Filtered supply data
    
    Returns:
        Prepared dataframe for display
    """
    if display_df.empty:
        return display_df
    
    display_df = display_df.copy()
    period_type = display_filters.get("period_type", "Weekly")
    
    # Keep original index order
    display_df = display_df.reset_index(drop=True)
    
    # Add is_past column for period status
    display_df['is_past'] = display_df['period'].apply(
        lambda x: is_past_period(x, period_type)
    )
    
    # Format period with dates (without indicator)
    display_df['period_display'] = display_df['period'].apply(
        lambda x: format_period_with_dates(x, period_type)
    )
    
    # Add Product Type column if we have demand/supply data
    if df_demand_filtered is not None and df_supply_filtered is not None:
        demand_products = set()
        supply_products = set()
        
        if not df_demand_filtered.empty and 'pt_code' in df_demand_filtered.columns:
            demand_products = set(df_demand_filtered['pt_code'].unique())
        
        if not df_supply_filtered.empty and 'pt_code' in df_supply_filtered.columns:
            supply_products = set(df_supply_filtered['pt_code'].unique())
        
        if demand_products or supply_products:
            def get_product_type(pt_code):
                if pt_code in demand_products and pt_code in supply_products:
                    return "Matched"
                elif pt_code in demand_products:
                    return "Demand Only"
                elif pt_code in supply_products:
                    return "Supply Only"
                return "Unknown"
            
            display_df['product_type'] = display_df['pt_code'].apply(get_product_type)
    
    # Add Backlog Status column if tracking backlog
    if 'backlog_to_next' in display_df.columns and display_filters.get('track_backlog', True):
        def get_backlog_status(row):
            try:
                backlog = float(str(row.get('backlog_to_next', 0)).replace(',', ''))
                if backlog > 0:
                    return "Has Backlog"
                else:
                    return "No Backlog"
            except:
                return "No Backlog"
        
        display_df['backlog_status'] = display_df.apply(get_backlog_status, axis=1)
    
    return display_df


def format_gap_display_df(df: pd.DataFrame, display_options: dict) -> pd.DataFrame:
    """
    Format GAP dataframe for display
    
    Args:
        df: GAP dataframe
        display_options: Display options
    
    Returns:
        Formatted dataframe
    """
    from .formatters import format_number, format_percentage
    
    if df.empty:
        return df
    
    df = df.copy()
    
    # Format numeric columns
    numeric_format_cols = [
        "begin_inventory", 
        "supply_in_period", 
        "total_available", 
        "total_demand_qty", 
        "gap_quantity",
        "backlog_qty",
        "effective_demand",
        "backlog_to_next"
    ]
    
    for col in numeric_format_cols:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: format_number(x))
    
    # Format percentage column
    if "fulfillment_rate_percent" in df.columns:
        df["fulfillment_rate_percent"] = df["fulfillment_rate_percent"].apply(
            lambda x: format_percentage(x)
        )
    
    # Add period status indicator as separate column
    if 'is_past' in df.columns:
        df['period_status'] = df['is_past'].apply(lambda x: "🔴" if x else "")
    
    # Use period_display instead of period
    if 'period_display' in df.columns:
        df['period'] = df['period_display']
    
    # Reorder columns
    column_order = [
        "period_status",
        "pt_code",
        "brand",
        "product_name",
        "package_size", 
        "standard_uom",
        "period",
        "begin_inventory",
        "supply_in_period",
        "total_available",
        "total_demand_qty",
        "backlog_qty",
        "effective_demand",
        "gap_quantity",
        "fulfillment_rate_percent",
        "fulfillment_status",
        "backlog_to_next"
    ]
    
    # Add metadata columns at the end
    metadata_cols = ["product_type", "backlog_status"]
    for col in df.columns:
        if col not in column_order and col in metadata_cols:
            column_order.append(col)
    
    # Keep only existing columns
    existing_ordered_cols = [col for col in column_order if col in df.columns]
    
    # Remove internal columns not needed for display
    cols_to_exclude = ['is_past', 'period_display']
    existing_ordered_cols = [col for col in existing_ordered_cols if col not in cols_to_exclude]
    
    df = df[existing_ordered_cols]
    
    # Rename columns for display
    rename_map = {
        "period_status": "",  # Empty header for indicator column
        "pt_code": "PT Code",
        "brand": "Brand",
        "product_name": "Product", 
        "package_size": "Pack Size",
        "standard_uom": "UOM",
        "period": "Period",
        "begin_inventory": "Begin Inv",
        "supply_in_period": "Supply In",
        "total_available": "Available",
        "total_demand_qty": "Demand",
        "backlog_qty": "Backlog",
        "effective_demand": "Total Need",
        "gap_quantity": "GAP",
        "fulfillment_rate_percent": "Fill %",
        "fulfillment_status": "Status",
        "backlog_to_next": "Carry Backlog",
        "product_type": "Product Type",
        "backlog_status": "Backlog Status"
    }
    
    rename_map_filtered = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=rename_map_filtered)
    
    # Drop backlog columns if not tracking
    if not display_options.get('track_backlog', True):
        backlog_display_cols = ['Backlog', 'Total Need', 'Carry Backlog', 'Backlog Status']
        cols_to_drop = [col for col in backlog_display_cols if col in df.columns]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)
    
    return df


def highlight_gap_rows_enhanced(row):
    """
    Enhanced highlighting for GAP rows
    
    Args:
        row: DataFrame row
    
    Returns:
        List of styles for each cell
    """
    styles = [""] * len(row)
    
    try:
        # Priority: shortage > has backlog > past period > low fulfillment
        
        # Check fulfillment status first
        if 'Status' in row.index and "❌" in str(row['Status']):
            return ["background-color: #f8d7da"] * len(row)
        
        # Check for backlog
        backlog_cols = ['Backlog', 'Backlog Status']
        for col in backlog_cols:
            if col in row.index:
                if col == 'Backlog Status' and "Has Backlog" in str(row[col]):
                    return ["background-color: #fff3cd"] * len(row)
                elif col == 'Backlog':
                    try:
                        backlog_val = float(str(row[col]).replace(',', '').strip())
                        if backlog_val > 0:
                            return ["background-color: #fff3cd"] * len(row)
                    except:
                        pass
        
        # Check if critical shortage
        fulfillment_cols = ['Fill %']
        for col in fulfillment_cols:
            if col in row.index:
                rate_str = str(row[col]).replace('%', '').strip()
                try:
                    rate = float(rate_str)
                    if rate < 50:
                        return ["background-color: #f5c6cb"] * len(row)
                except:
                    pass
        
        # Check if past period (check empty column with indicator)
        if "" in row.index and "🔴" in str(row[""]):
            return ["background-color: #f0f0f0"] * len(row)
        
    except Exception as e:
        logger.error(f"Error highlighting rows: {str(e)}")
    
    return styles