# utils/period_gap/helpers.py
"""
General Helper Functions
Excel export, period manipulation, session state management
Version 3.0 - Enhanced Excel Export with:
  - User-friendly column names
  - Category and Product Type columns
  - Conditional formatting
  - Period Summary sheet
  - Pivot View sheet
  - Action Items sheet
  - Past period indicator
"""

import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
import logging

logger = logging.getLogger(__name__)

# === CONSTANTS ===
EXCEL_SHEET_NAME_LIMIT = 31
DEFAULT_EXCEL_ENGINE = "xlsxwriter"

EXCEL_HEADER_FORMAT = {
    'bold': True,
    'text_wrap': True,
    'valign': 'top',
    'fg_color': '#D7E4BD',
    'border': 1
}

# Column rename mapping for user-friendly names
COLUMN_RENAME_MAP = {
    'pt_code': 'PT Code',
    'brand': 'Brand',
    'product_name': 'Product',
    'package_size': 'Pack Size',
    'standard_uom': 'UOM',
    'period': 'Period',
    'begin_inventory': 'Begin Inv',
    'supply_in_period': 'Supply In',
    'total_available': 'Available',
    'total_demand_qty': 'Demand',
    'gap_quantity': 'GAP',
    'fulfillment_rate_percent': 'Fill %',
    'fulfillment_status': 'Status',
    'backlog_qty': 'Backlog In',
    'effective_demand': 'Total Need',
    'backlog_to_next': 'Carry Backlog',
    'category': 'Category',
    'product_type': 'Product Type',
    'is_past_period': 'Past',
    'recommended_action': 'Action'
}

# Category icons
CATEGORY_ICONS = {
    'Net Shortage': '🚨',
    'Net Surplus': '📈',
    'Balanced': '✅',
    'Unknown': '❓'
}

# === EXCEL EXPORT FUNCTIONS ===

def convert_df_to_excel(df: pd.DataFrame, sheet_name: str = "Data") -> bytes:
    """Convert dataframe to Excel bytes with auto-formatting"""
    if df.empty:
        logger.warning("Attempting to convert empty DataFrame to Excel")
        return BytesIO().getvalue()
    
    output = BytesIO()
    
    try:
        with pd.ExcelWriter(output, engine=DEFAULT_EXCEL_ENGINE) as writer:
            sheet_name = sheet_name[:EXCEL_SHEET_NAME_LIMIT]
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]
            
            header_format = workbook.add_format(EXCEL_HEADER_FORMAT)
            
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            for i, col in enumerate(df.columns):
                try:
                    max_len = df[col].astype(str).map(len).max()
                    max_len = max(max_len, len(str(col))) + 2
                    worksheet.set_column(i, i, min(max_len, 50))
                except Exception as e:
                    logger.debug(f"Could not calculate width for column {col}: {e}")
                    worksheet.set_column(i, i, 15)
        
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Error converting DataFrame to Excel: {e}")
        raise


def export_multiple_sheets_with_formatting(
    dataframes_dict: Dict[str, pd.DataFrame],
    formatting_config: Optional[Dict[str, Any]] = None
) -> bytes:
    """
    Export multiple dataframes to different sheets with conditional formatting
    
    Args:
        dataframes_dict: Dict of sheet_name -> DataFrame
        formatting_config: Optional dict with formatting rules per sheet
    
    Returns:
        Excel file bytes
    """
    if not dataframes_dict:
        logger.warning("No DataFrames provided for multi-sheet export")
        return BytesIO().getvalue()
    
    output = BytesIO()
    formatting_config = formatting_config or {}
    
    try:
        with pd.ExcelWriter(output, engine=DEFAULT_EXCEL_ENGINE) as writer:
            workbook = writer.book
            
            # Define formats
            header_format = workbook.add_format(EXCEL_HEADER_FORMAT)
            
            # Conditional formats
            shortage_format = workbook.add_format({
                'bg_color': '#f8d7da',  # Light red
                'font_color': '#721c24'
            })
            surplus_format = workbook.add_format({
                'bg_color': '#d4edda',  # Light green
                'font_color': '#155724'
            })
            backlog_format = workbook.add_format({
                'bg_color': '#fff3cd',  # Light yellow
                'font_color': '#856404'
            })
            past_period_format = workbook.add_format({
                'bg_color': '#e9ecef',  # Light gray
                'font_color': '#6c757d'
            })
            
            # Number formats
            number_format = workbook.add_format({'num_format': '#,##0'})
            percent_format = workbook.add_format({'num_format': '0.0%'})
            currency_format = workbook.add_format({'num_format': '$#,##0.00'})
            
            for sheet_name, df in dataframes_dict.items():
                if df is None or df.empty:
                    logger.debug(f"Skipping empty sheet: {sheet_name}")
                    continue
                    
                truncated_name = sheet_name[:EXCEL_SHEET_NAME_LIMIT]
                df.to_excel(writer, index=False, sheet_name=truncated_name)
                
                worksheet = writer.sheets[truncated_name]
                
                # Write headers with format
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                # Auto-fit columns
                for i, col in enumerate(df.columns):
                    try:
                        max_len = df[col].astype(str).map(len).max()
                        max_len = max(max_len, len(str(col))) + 2
                        worksheet.set_column(i, i, min(max_len, 50))
                    except:
                        worksheet.set_column(i, i, 15)
                
                # Apply conditional formatting for specific sheets
                sheet_config = formatting_config.get(sheet_name, {})
                
                if sheet_config.get('apply_gap_formatting', False):
                    _apply_gap_sheet_formatting(
                        worksheet, df, workbook,
                        shortage_format, surplus_format, 
                        backlog_format, past_period_format
                    )
                
                # Freeze panes (header row)
                if sheet_config.get('freeze_header', True):
                    worksheet.freeze_panes(1, 0)
                
                # Auto-filter
                if sheet_config.get('auto_filter', True) and len(df) > 0:
                    worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
        
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Error exporting multiple sheets: {e}")
        raise


def _apply_gap_sheet_formatting(
    worksheet, 
    df: pd.DataFrame, 
    workbook,
    shortage_format,
    surplus_format,
    backlog_format,
    past_period_format
):
    """Apply conditional formatting to GAP analysis sheet"""
    
    # Find column indices
    col_indices = {col: i for i, col in enumerate(df.columns)}
    
    gap_col = col_indices.get('GAP', col_indices.get('gap_quantity', -1))
    fill_col = col_indices.get('Fill %', col_indices.get('fulfillment_rate_percent', -1))
    backlog_col = col_indices.get('Carry Backlog', col_indices.get('backlog_to_next', -1))
    past_col = col_indices.get('Past', col_indices.get('is_past_period', -1))
    status_col = col_indices.get('Status', col_indices.get('fulfillment_status', -1))
    
    num_rows = len(df) + 1  # +1 for header
    num_cols = len(df.columns)
    
    # GAP column formatting
    if gap_col >= 0:
        col_letter = _get_column_letter(gap_col)
        
        # Red for negative GAP
        worksheet.conditional_format(
            1, gap_col, num_rows, gap_col,
            {
                'type': 'cell',
                'criteria': '<',
                'value': 0,
                'format': shortage_format
            }
        )
        
        # Green for positive GAP
        worksheet.conditional_format(
            1, gap_col, num_rows, gap_col,
            {
                'type': 'cell',
                'criteria': '>',
                'value': 0,
                'format': surplus_format
            }
        )
    
    # Fill % column formatting (color scale)
    if fill_col >= 0:
        worksheet.conditional_format(
            1, fill_col, num_rows, fill_col,
            {
                'type': '3_color_scale',
                'min_color': '#f8d7da',  # Red for low
                'mid_color': '#fff3cd',  # Yellow for medium
                'max_color': '#d4edda',  # Green for high
                'min_value': 0,
                'mid_value': 80,
                'max_value': 100
            }
        )
    
    # Backlog column formatting
    if backlog_col >= 0:
        worksheet.conditional_format(
            1, backlog_col, num_rows, backlog_col,
            {
                'type': 'cell',
                'criteria': '>',
                'value': 0,
                'format': backlog_format
            }
        )


def _get_column_letter(col_index: int) -> str:
    """Convert column index to Excel column letter"""
    result = ""
    while col_index >= 0:
        result = chr(col_index % 26 + ord('A')) + result
        col_index = col_index // 26 - 1
    return result


def export_multiple_sheets(dataframes_dict: Dict[str, pd.DataFrame]) -> bytes:
    """Export multiple dataframes to different sheets in one Excel file (legacy support)"""
    return export_multiple_sheets_with_formatting(dataframes_dict)


# === METADATA SHEET ===

def create_metadata_sheet(
    filter_values: Dict[str, Any],
    calc_options: Dict[str, Any],
    gap_df: pd.DataFrame,
    display_filters: Dict[str, Any],
    df_demand_filtered: pd.DataFrame,
    df_supply_filtered: pd.DataFrame
) -> pd.DataFrame:
    """
    Create Export_Info metadata sheet with analysis parameters and summary statistics
    """
    from .shortage_analyzer import categorize_products
    
    metadata_rows = []
    
    # === EXPORT INFORMATION ===
    metadata_rows.append(['EXPORT INFORMATION', ''])
    metadata_rows.append(['Export Date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    metadata_rows.append(['Report Type', 'Period GAP Analysis'])
    metadata_rows.append(['Version', '3.0'])
    metadata_rows.append(['', ''])
    
    # === CALCULATION PARAMETERS ===
    metadata_rows.append(['CALCULATION PARAMETERS', ''])
    metadata_rows.append(['Period Type', calc_options.get('period_type', 'Weekly')])
    metadata_rows.append(['Track Backlog', 'Yes' if calc_options.get('track_backlog', True) else 'No'])
    metadata_rows.append(['Exclude Missing Dates', 'Yes' if calc_options.get('exclude_missing_dates', True) else 'No'])
    metadata_rows.append(['OC Date Field', calc_options.get('oc_date_field', 'ETA')])
    metadata_rows.append(['', ''])
    
    # === DATA FILTERS ===
    metadata_rows.append(['DATA FILTERS', ''])
    
    if filter_values.get('entity'):
        entity_mode = "Excluded" if filter_values.get('exclude_entity', False) else "Included"
        metadata_rows.append(['Legal Entity', f"{entity_mode}: {', '.join(filter_values['entity'])}"])
    else:
        metadata_rows.append(['Legal Entity', 'All'])
    
    if filter_values.get('brand'):
        brand_mode = "Excluded" if filter_values.get('exclude_brand', False) else "Included"
        metadata_rows.append(['Brand', f"{brand_mode}: {', '.join(filter_values['brand'])}"])
    else:
        metadata_rows.append(['Brand', 'All'])
    
    if filter_values.get('product'):
        product_mode = "Excluded" if filter_values.get('exclude_product', False) else "Included"
        metadata_rows.append(['Products', f"{product_mode}: {len(filter_values['product'])} products"])
    else:
        metadata_rows.append(['Products', 'All'])
    
    if filter_values.get('start_date') and filter_values.get('end_date'):
        metadata_rows.append(['Date Range', f"{filter_values['start_date']} to {filter_values['end_date']}"])
    
    metadata_rows.append(['', ''])
    
    # === DISPLAY FILTERS ===
    metadata_rows.append(['DISPLAY FILTERS', ''])
    metadata_rows.append(['Period Filter', display_filters.get('period_filter', 'All')])
    
    product_types = []
    if display_filters.get('show_matched', True):
        product_types.append('Matched')
    if display_filters.get('show_demand_only', True):
        product_types.append('Demand Only')
    if display_filters.get('show_supply_only', True):
        product_types.append('Supply Only')
    metadata_rows.append(['Product Types', ', '.join(product_types)])
    metadata_rows.append(['', ''])
    
    # === SUMMARY STATISTICS ===
    metadata_rows.append(['SUMMARY STATISTICS', ''])
    
    if not gap_df.empty:
        total_products = gap_df['pt_code'].nunique()
        total_periods = gap_df['period'].nunique()
        
        metadata_rows.append(['Total Products', total_products])
        metadata_rows.append(['Total Periods', total_periods])
        metadata_rows.append(['Total Records', len(gap_df)])
        metadata_rows.append(['', ''])
        
        # Shortage & Surplus categorization
        categorization = categorize_products(gap_df)
        
        metadata_rows.append(['CATEGORIZATION', ''])
        metadata_rows.append(['🚨 Net Shortage Products', len(categorization['net_shortage'])])
        metadata_rows.append(['✅ Balanced Products', len(categorization['balanced'])])
        metadata_rows.append(['📈 Net Surplus Products', len(categorization['net_surplus'])])
        metadata_rows.append(['', ''])
        metadata_rows.append(['TIMING FLAGS', ''])
        metadata_rows.append(['⚠️ Timing Shortage Products', len(categorization['timing_shortage'])])
        metadata_rows.append(['⏰ Timing Surplus Products', len(categorization['timing_surplus'])])
        metadata_rows.append(['', ''])
        
        # Supply vs Demand totals
        total_demand = gap_df['total_demand_qty'].sum()
        total_supply = gap_df['supply_in_period'].sum()
        net_position = total_supply - total_demand
        
        metadata_rows.append(['SUPPLY vs DEMAND', ''])
        metadata_rows.append(['Total Demand', f"{total_demand:,.2f}"])
        metadata_rows.append(['Total Supply', f"{total_supply:,.2f}"])
        metadata_rows.append(['Net Position', f"{net_position:,.2f}"])
        
        if total_demand > 0:
            fill_rate = min(100, total_supply / total_demand * 100)
            metadata_rows.append(['Overall Fill Rate', f"{fill_rate:.1f}%"])
        
        metadata_rows.append(['', ''])
        
        # Shortage/Surplus quantities
        total_shortage = abs(gap_df[gap_df['gap_quantity'] < 0]['gap_quantity'].sum())
        total_surplus = gap_df[gap_df['gap_quantity'] > 0]['gap_quantity'].sum()
        
        metadata_rows.append(['Total Shortage Quantity', f"{total_shortage:,.2f}"])
        metadata_rows.append(['Total Surplus Quantity', f"{total_surplus:,.2f}"])
        
        # Backlog info if tracking
        if calc_options.get('track_backlog', True) and 'backlog_to_next' in gap_df.columns:
            final_backlog = gap_df.groupby('pt_code')['backlog_to_next'].last().sum()
            products_with_backlog = (gap_df.groupby('pt_code')['backlog_to_next'].last() > 0).sum()
            
            metadata_rows.append(['', ''])
            metadata_rows.append(['Final Backlog', f"{final_backlog:,.2f}"])
            metadata_rows.append(['Products with Backlog', products_with_backlog])
    
    metadata_rows.append(['', ''])
    
    # === SOURCE DATA COUNTS ===
    metadata_rows.append(['SOURCE DATA COUNTS', ''])
    metadata_rows.append(['Demand Records', len(df_demand_filtered)])
    metadata_rows.append(['Supply Records', len(df_supply_filtered)])
    
    # === SHEETS GUIDE ===
    metadata_rows.append(['', ''])
    metadata_rows.append(['SHEETS IN THIS WORKBOOK', ''])
    metadata_rows.append(['Export_Info', 'This sheet - export metadata and summary'])
    metadata_rows.append(['GAP_Analysis', 'Detailed GAP analysis by product and period'])
    metadata_rows.append(['Product_Summary', 'One row per product with totals and category'])
    metadata_rows.append(['Period_Summary', 'One row per period with aggregated metrics'])
    metadata_rows.append(['Pivot_View', 'Products x Periods matrix view'])
    metadata_rows.append(['Action_Items', 'Recommended actions for shortage/surplus'])
    
    # Convert to DataFrame
    metadata_df = pd.DataFrame(metadata_rows, columns=['Parameter', 'Value'])
    
    return metadata_df


# === ENHANCED GAP EXPORT ===

def export_gap_with_metadata(
    gap_df: pd.DataFrame,
    filter_values: Dict[str, Any],
    display_filters: Dict[str, Any],
    calc_options: Dict[str, Any],
    df_demand_filtered: pd.DataFrame,
    df_supply_filtered: pd.DataFrame
) -> bytes:
    """
    Export GAP analysis with metadata sheet and enhanced formatting
    
    Version 3.0 features:
    - User-friendly column names
    - Category and Product Type columns
    - Conditional formatting
    - Period Summary sheet
    - Pivot View sheet
    - Action Items sheet
    - Past period indicator
    """
    from .period_helpers import format_period_with_dates, is_past_period
    from .shortage_analyzer import categorize_products
    
    if gap_df.empty:
        logger.warning("Empty GAP dataframe for export")
        return BytesIO().getvalue()
    
    period_type = calc_options.get('period_type', 'Weekly')
    
    # === PREPARE GAP DETAIL DATA ===
    export_df = _prepare_gap_export_df(
        gap_df, df_demand_filtered, df_supply_filtered, 
        period_type, calc_options
    )
    
    # === CREATE ALL SHEETS ===
    
    # 1. Metadata sheet
    metadata_df = create_metadata_sheet(
        filter_values=filter_values,
        calc_options=calc_options,
        gap_df=gap_df,
        display_filters=display_filters,
        df_demand_filtered=df_demand_filtered,
        df_supply_filtered=df_supply_filtered
    )
    
    # 2. Product summary sheet
    summary_df = create_product_summary(gap_df, calc_options)
    
    # 3. Period summary sheet (NEW)
    period_summary_df = create_period_summary(gap_df, period_type)
    
    # 4. Pivot view sheet (NEW)
    pivot_df = create_pivot_view(gap_df, period_type)
    
    # 5. Action items sheet (NEW)
    action_df = create_action_items(gap_df, df_supply_filtered, calc_options)
    
    # Prepare sheets dictionary
    sheets_dict = {
        'Export_Info': metadata_df,
        'GAP_Analysis': export_df,
        'Product_Summary': summary_df,
        'Period_Summary': period_summary_df,
        'Pivot_View': pivot_df,
        'Action_Items': action_df
    }
    
    # Formatting config
    formatting_config = {
        'GAP_Analysis': {
            'apply_gap_formatting': True,
            'freeze_header': True,
            'auto_filter': True
        },
        'Product_Summary': {
            'freeze_header': True,
            'auto_filter': True
        },
        'Period_Summary': {
            'freeze_header': True,
            'auto_filter': True
        },
        'Pivot_View': {
            'freeze_header': True,
            'auto_filter': False
        },
        'Action_Items': {
            'freeze_header': True,
            'auto_filter': True
        }
    }
    
    # Export to Excel with formatting
    return export_multiple_sheets_with_formatting(sheets_dict, formatting_config)


def _prepare_gap_export_df(
    gap_df: pd.DataFrame,
    df_demand_filtered: pd.DataFrame,
    df_supply_filtered: pd.DataFrame,
    period_type: str,
    calc_options: Dict[str, Any]
) -> pd.DataFrame:
    """Prepare GAP dataframe for export with all enhancements"""
    from .period_helpers import format_period_with_dates, is_past_period
    from .shortage_analyzer import categorize_products
    
    export_df = gap_df.copy()
    
    # Get categorization
    categorization = categorize_products(gap_df)
    
    # Build product lookup sets
    demand_products = set(df_demand_filtered['pt_code'].unique()) if not df_demand_filtered.empty else set()
    supply_products = set(df_supply_filtered['pt_code'].unique()) if not df_supply_filtered.empty else set()
    
    # === ADD CATEGORY COLUMN ===
    def get_category(pt_code):
        if pt_code in categorization['net_shortage']:
            return f"{CATEGORY_ICONS['Net Shortage']} Net Shortage"
        elif pt_code in categorization['net_surplus']:
            return f"{CATEGORY_ICONS['Net Surplus']} Net Surplus"
        elif pt_code in categorization['balanced']:
            return f"{CATEGORY_ICONS['Balanced']} Balanced"
        return f"{CATEGORY_ICONS['Unknown']} Unknown"
    
    export_df['category'] = export_df['pt_code'].apply(get_category)
    
    # === ADD PRODUCT TYPE COLUMN ===
    def get_product_type(pt_code):
        in_demand = pt_code in demand_products
        in_supply = pt_code in supply_products
        
        if in_demand and in_supply:
            return "Matched"
        elif in_demand:
            return "Demand Only"
        elif in_supply:
            return "Supply Only"
        return "Unknown"
    
    export_df['product_type'] = export_df['pt_code'].apply(get_product_type)
    
    # === ADD PAST PERIOD INDICATOR ===
    def check_past_period(period):
        try:
            return "🔴" if is_past_period(period, period_type) else ""
        except:
            return ""
    
    export_df['is_past_period'] = export_df['period'].apply(check_past_period)
    
    # === ADD RECOMMENDED ACTION ===
    def get_recommended_action(row):
        gap = row.get('gap_quantity', 0)
        category = row.get('category', '')
        is_past = row.get('is_past_period', '')
        
        if is_past == "🔴":
            return ""  # No action for past periods
        
        if gap < 0:
            if 'Net Shortage' in category:
                return "📦 Create PO"
            else:
                return "⏱️ Expedite"
        elif gap > 0:
            if 'Net Surplus' in category:
                return "📈 Review excess"
            else:
                return ""
        return ""
    
    export_df['recommended_action'] = export_df.apply(get_recommended_action, axis=1)
    
    # === FORMAT PERIOD WITH DATES ===
    export_df['period'] = export_df['period'].apply(
        lambda x: format_period_with_dates(x, period_type)
    )
    
    # === REORDER COLUMNS ===
    column_order = [
        'is_past_period',
        'pt_code', 
        'brand',
        'product_name',
        'package_size',
        'standard_uom',
        'category',
        'product_type',
        'period',
        'begin_inventory',
        'supply_in_period',
        'total_available',
        'total_demand_qty',
        'backlog_qty',
        'effective_demand',
        'gap_quantity',
        'fulfillment_rate_percent',
        'fulfillment_status',
        'backlog_to_next',
        'recommended_action'
    ]
    
    # Only include columns that exist
    final_columns = [col for col in column_order if col in export_df.columns]
    export_df = export_df[final_columns]
    
    # === RENAME COLUMNS ===
    export_df = export_df.rename(columns=COLUMN_RENAME_MAP)
    
    return export_df


# === PRODUCT SUMMARY SHEET ===

def create_product_summary(gap_df: pd.DataFrame, calc_options: Dict[str, Any]) -> pd.DataFrame:
    """Create product-level summary for export with category icons"""
    from .shortage_analyzer import categorize_products
    
    if gap_df.empty:
        return pd.DataFrame()
    
    # Get categorization
    categorization = categorize_products(gap_df)
    
    summary_data = []
    
    for pt_code in gap_df['pt_code'].unique():
        product_df = gap_df[gap_df['pt_code'] == pt_code]
        
        # Basic info
        product_name = product_df['product_name'].iloc[0] if 'product_name' in product_df.columns else ''
        brand = product_df['brand'].iloc[0] if 'brand' in product_df.columns else ''
        package_size = product_df['package_size'].iloc[0] if 'package_size' in product_df.columns else ''
        standard_uom = product_df['standard_uom'].iloc[0] if 'standard_uom' in product_df.columns else ''
        
        # Totals
        total_demand = product_df['total_demand_qty'].sum()
        total_supply = product_df['supply_in_period'].sum()
        net_position = total_supply - total_demand
        
        # Period counts
        total_periods = len(product_df)
        shortage_periods = (product_df['gap_quantity'] < 0).sum()
        surplus_periods = (product_df['gap_quantity'] > 0).sum()
        balanced_periods = total_periods - shortage_periods - surplus_periods
        
        # Max shortage/surplus
        max_shortage = abs(product_df[product_df['gap_quantity'] < 0]['gap_quantity'].min()) if shortage_periods > 0 else 0
        max_surplus = product_df[product_df['gap_quantity'] > 0]['gap_quantity'].max() if surplus_periods > 0 else 0
        
        # Main categorization with icons
        if pt_code in categorization['net_shortage']:
            category = f"{CATEGORY_ICONS['Net Shortage']} Net Shortage"
        elif pt_code in categorization['net_surplus']:
            category = f"{CATEGORY_ICONS['Net Surplus']} Net Surplus"
        elif pt_code in categorization['balanced']:
            category = f"{CATEGORY_ICONS['Balanced']} Balanced"
        else:
            category = f"{CATEGORY_ICONS['Unknown']} Unknown"
        
        # Timing flags
        timing_flags = []
        if pt_code in categorization['timing_shortage']:
            timing_flags.append("⚠️ Timing Shortage")
        if pt_code in categorization['timing_surplus']:
            timing_flags.append("⏰ Timing Surplus")
        timing_flag_str = " | ".join(timing_flags) if timing_flags else "None"
        
        # Fill rate
        fill_rate = min(100, (total_supply / total_demand * 100)) if total_demand > 0 else 100
        
        # Backlog info
        if calc_options.get('track_backlog', True) and 'backlog_to_next' in product_df.columns:
            final_backlog = product_df['backlog_to_next'].iloc[-1] if not product_df.empty else 0
        else:
            final_backlog = 0
        
        # First shortage period
        shortage_mask = product_df['gap_quantity'] < 0
        first_shortage = product_df[shortage_mask]['period'].iloc[0] if shortage_mask.any() else ""
        
        summary_data.append({
            'PT Code': pt_code,
            'Product': product_name,
            'Brand': brand,
            'Pack Size': package_size,
            'UOM': standard_uom,
            'Category': category,
            'Timing Flags': timing_flag_str,
            'Total Demand': total_demand,
            'Total Supply': total_supply,
            'Net Position': net_position,
            'Fill Rate %': round(fill_rate, 1),
            'Total Periods': total_periods,
            'Shortage Periods': shortage_periods,
            'Surplus Periods': surplus_periods,
            'Balanced Periods': balanced_periods,
            'Max Shortage': max_shortage,
            'Max Surplus': max_surplus,
            'Final Backlog': final_backlog,
            'First Shortage': first_shortage
        })
    
    summary_df = pd.DataFrame(summary_data)
    
    # Sort by category priority and net position
    category_order = {
        f"{CATEGORY_ICONS['Net Shortage']} Net Shortage": 1,
        f"{CATEGORY_ICONS['Balanced']} Balanced": 2,
        f"{CATEGORY_ICONS['Net Surplus']} Net Surplus": 3,
        f"{CATEGORY_ICONS['Unknown']} Unknown": 4
    }
    
    if not summary_df.empty:
        summary_df['_sort_order'] = summary_df['Category'].map(category_order).fillna(4)
        summary_df = summary_df.sort_values(['_sort_order', 'Net Position'])
        summary_df = summary_df.drop(columns=['_sort_order'])
    
    return summary_df


# === PERIOD SUMMARY SHEET (NEW) ===

def create_period_summary(gap_df: pd.DataFrame, period_type: str) -> pd.DataFrame:
    """
    Create period-level summary for export
    
    One row per period with aggregated metrics
    """
    from .period_helpers import format_period_with_dates, is_past_period, parse_week_period, parse_month_period
    
    if gap_df.empty:
        return pd.DataFrame()
    
    summary_data = []
    
    for period in gap_df['period'].unique():
        period_df = gap_df[gap_df['period'] == period]
        
        # Basic metrics
        total_products = period_df['pt_code'].nunique()
        total_demand = period_df['total_demand_qty'].sum()
        total_supply = period_df['supply_in_period'].sum()
        total_available = period_df['total_available'].sum()
        net_gap = period_df['gap_quantity'].sum()
        
        # Product counts by status
        shortage_products = (period_df['gap_quantity'] < 0).sum()
        surplus_products = (period_df['gap_quantity'] > 0).sum()
        balanced_products = total_products - shortage_products - surplus_products
        
        # Quantities
        shortage_qty = abs(period_df[period_df['gap_quantity'] < 0]['gap_quantity'].sum())
        surplus_qty = period_df[period_df['gap_quantity'] > 0]['gap_quantity'].sum()
        
        # Fill rate
        fill_rate = min(100, (total_supply / total_demand * 100)) if total_demand > 0 else 100
        
        # Period status
        try:
            is_past = is_past_period(period, period_type)
            period_status = "🔴 Past" if is_past else "⚫ Future"
        except:
            period_status = "⚫ Future"
        
        # Format period with dates
        period_formatted = format_period_with_dates(period, period_type)
        
        summary_data.append({
            'Period': period_formatted,
            'Status': period_status,
            'Total Products': total_products,
            'Total Demand': total_demand,
            'Total Supply': total_supply,
            'Total Available': total_available,
            'Net GAP': net_gap,
            'Fill Rate %': round(fill_rate, 1),
            '🚨 Shortage Products': shortage_products,
            '📈 Surplus Products': surplus_products,
            '✅ Balanced Products': balanced_products,
            'Shortage Qty': shortage_qty,
            'Surplus Qty': surplus_qty,
            '_period_raw': period  # For sorting
        })
    
    summary_df = pd.DataFrame(summary_data)
    
    # Sort by period
    if not summary_df.empty:
        try:
            if period_type == "Weekly":
                summary_df['_sort_key'] = summary_df['_period_raw'].apply(parse_week_period)
            elif period_type == "Monthly":
                summary_df['_sort_key'] = summary_df['_period_raw'].apply(parse_month_period)
            else:
                summary_df['_sort_key'] = summary_df['_period_raw']
            
            summary_df = summary_df.sort_values('_sort_key')
        except Exception as e:
            logger.warning(f"Could not sort periods: {e}")
        
        # Remove helper columns
        summary_df = summary_df.drop(columns=['_period_raw', '_sort_key'], errors='ignore')
    
    return summary_df


# === PIVOT VIEW SHEET (NEW) ===

def create_pivot_view(gap_df: pd.DataFrame, period_type: str) -> pd.DataFrame:
    """
    Create Products x Periods matrix view
    
    Shows GAP values for each product-period combination
    """
    from .period_helpers import parse_week_period, parse_month_period, format_period_with_dates
    
    if gap_df.empty:
        return pd.DataFrame()
    
    try:
        # Create pivot
        pivot_df = gap_df.pivot_table(
            index=['pt_code', 'product_name', 'brand'],
            columns='period',
            values='gap_quantity',
            aggfunc='sum',
            fill_value=0
        ).reset_index()
        
        # Sort columns by period
        info_cols = ['pt_code', 'product_name', 'brand']
        period_cols = [col for col in pivot_df.columns if col not in info_cols]
        
        # Sort period columns
        try:
            if period_type == "Weekly":
                sorted_periods = sorted(period_cols, key=parse_week_period)
            elif period_type == "Monthly":
                sorted_periods = sorted(period_cols, key=parse_month_period)
            else:
                sorted_periods = sorted(period_cols)
        except:
            sorted_periods = period_cols
        
        # Reorder columns
        pivot_df = pivot_df[info_cols + sorted_periods]
        
        # Add total column
        pivot_df['Total GAP'] = pivot_df[sorted_periods].sum(axis=1)
        
        # Rename info columns
        pivot_df = pivot_df.rename(columns={
            'pt_code': 'PT Code',
            'product_name': 'Product',
            'brand': 'Brand'
        })
        
        # Format period columns with dates
        rename_map = {}
        for period in sorted_periods:
            formatted = format_period_with_dates(period, period_type)
            # Shorten for pivot view
            if period_type == "Weekly" and "Week" in str(period):
                rename_map[period] = period  # Keep short format
            else:
                rename_map[period] = formatted
        
        pivot_df = pivot_df.rename(columns=rename_map)
        
        # Sort by Total GAP (shortage first)
        pivot_df = pivot_df.sort_values('Total GAP')
        
        return pivot_df
        
    except Exception as e:
        logger.error(f"Error creating pivot view: {e}")
        return pd.DataFrame()


# === ACTION ITEMS SHEET (NEW) ===

def create_action_items(
    gap_df: pd.DataFrame,
    df_supply_filtered: pd.DataFrame,
    calc_options: Dict[str, Any]
) -> pd.DataFrame:
    """
    Create Action Items sheet with recommendations
    
    Includes:
    - Products needing new PO
    - Products needing expedite
    - Products with excess to review
    """
    from .shortage_analyzer import categorize_products, calculate_order_requirements, identify_expedite_candidates
    from .period_helpers import is_past_period
    
    if gap_df.empty:
        return pd.DataFrame()
    
    period_type = calc_options.get('period_type', 'Weekly')
    categorization = categorize_products(gap_df)
    
    action_items = []
    
    # === NEW PO REQUIREMENTS ===
    order_requirements_df = calculate_order_requirements(gap_df)
    
    if not order_requirements_df.empty:
        for _, row in order_requirements_df.iterrows():
            order_qty = row.get('order_quantity', 0)
            action_items.append({
                'Priority': '🔴 High' if order_qty > 500 else '🟡 Medium',
                'Action Type': '📦 Create PO',
                'PT Code': row.get('pt_code', ''),
                'Product': row.get('product_name', ''),
                'Brand': row.get('brand', ''),
                'Required Qty': order_qty,
                'First Need Date': row.get('first_shortage_period', ''),
                'Periods Affected': row.get('coverage_periods', 0),
                'Details': f"Net shortage of {order_qty:,.0f} units. {row.get('urgency', '')} action required.",
                'Status': 'Pending'
            })
    
    # === EXPEDITE CANDIDATES ===
    expedite_candidates_df = identify_expedite_candidates(gap_df, df_supply_filtered)
    
    if not expedite_candidates_df.empty:
        for _, row in expedite_candidates_df.iterrows():
            action_items.append({
                'Priority': '🟡 Medium',
                'Action Type': '⏱️ Expedite',
                'PT Code': row.get('pt_code', ''),
                'Product': row.get('product_name', ''),
                'Brand': '',
                'Required Qty': row.get('shortage_qty', 0),
                'First Need Date': row.get('shortage_period', ''),
                'Periods Affected': 1,
                'Details': f"Expedite {row.get('supply_source', '')} {row.get('supply_number', '')} (Qty: {row.get('supply_qty', 0):,.0f}) from {row.get('current_eta', '')}",
                'Status': 'Pending'
            })
    
    # === SURPLUS TO REVIEW ===
    for pt_code in categorization['net_surplus']:
        product_df = gap_df[gap_df['pt_code'] == pt_code]
        
        if product_df.empty:
            continue
        
        total_surplus = product_df[product_df['gap_quantity'] > 0]['gap_quantity'].sum()
        total_demand = product_df['total_demand_qty'].sum()
        
        # Only flag significant surplus (> 50% of demand)
        if total_demand > 0 and total_surplus > total_demand * 0.5:
            surplus_pct = (total_surplus / total_demand) * 100
            
            action_items.append({
                'Priority': '🔵 Low',
                'Action Type': '📈 Review Excess',
                'PT Code': pt_code,
                'Product': product_df['product_name'].iloc[0] if 'product_name' in product_df.columns else '',
                'Brand': product_df['brand'].iloc[0] if 'brand' in product_df.columns else '',
                'Required Qty': total_surplus,
                'First Need Date': '',
                'Periods Affected': (product_df['gap_quantity'] > 0).sum(),
                'Details': f"Excess of {total_surplus:,.0f} units ({surplus_pct:.0f}% of demand). Consider deferring orders.",
                'Status': 'Pending'
            })
    
    action_df = pd.DataFrame(action_items)
    
    # Sort by priority and action type
    if not action_df.empty:
        priority_order = {'🔴 High': 1, '🟡 Medium': 2, '🔵 Low': 3}
        action_df['_sort'] = action_df['Priority'].map(priority_order).fillna(4)
        action_df = action_df.sort_values(['_sort', 'Required Qty'], ascending=[True, False])
        action_df = action_df.drop(columns=['_sort'])
    
    return action_df


# === SESSION STATE HELPERS ===

def save_to_session_state(key: str, value: Any, add_timestamp: bool = True):
    """Save value to session state with optional timestamp"""
    st.session_state[key] = value
    if add_timestamp:
        st.session_state[f"{key}_timestamp"] = datetime.now()


def get_from_session_state(key: str, default: Any = None) -> Any:
    """Get value from session state"""
    return st.session_state.get(key, default)


def clear_session_state_pattern(pattern: str):
    """Clear session state keys matching pattern"""
    keys_to_clear = [key for key in st.session_state.keys() if pattern in key]
    for key in keys_to_clear:
        del st.session_state[key]
    
    if keys_to_clear:
        logger.debug(f"Cleared {len(keys_to_clear)} session state keys matching '{pattern}'")


# === STANDARDIZED PERIOD HANDLING ===

def create_period_pivot(
    df: pd.DataFrame,
    group_cols: List[str],
    period_col: str,
    value_col: str,
    agg_func: str = "sum",
    period_type: str = "Weekly",
    show_only_nonzero: bool = True,
    fill_value: Any = 0
) -> pd.DataFrame:
    """Create standardized pivot table for any analysis page"""
    from .period_helpers import parse_week_period, parse_month_period
    
    if df.empty:
        return pd.DataFrame()
    
    missing_cols = [col for col in group_cols + [period_col, value_col] if col not in df.columns]
    if missing_cols:
        logger.error(f"Missing columns in dataframe: {missing_cols}")
        return pd.DataFrame()
    
    try:
        pivot_df = df.pivot_table(
            index=group_cols,
            columns=period_col,
            values=value_col,
            aggfunc=agg_func,
            fill_value=fill_value
        ).reset_index()
        
        if show_only_nonzero and len(pivot_df.columns) > len(group_cols):
            numeric_cols = [col for col in pivot_df.columns if col not in group_cols]
            if numeric_cols:
                row_sums = pivot_df[numeric_cols].sum(axis=1)
                pivot_df = pivot_df[row_sums > 0]
        
        # Sort columns by period
        info_cols = group_cols
        period_cols = [col for col in pivot_df.columns if col not in info_cols]
        
        valid_period_cols = [col for col in period_cols 
                            if pd.notna(col) and str(col).strip() != "" and str(col) != "nan"]
        
        try:
            if period_type == "Weekly":
                sorted_periods = sorted(valid_period_cols, key=parse_week_period)
            elif period_type == "Monthly":
                sorted_periods = sorted(valid_period_cols, key=parse_month_period)
            else:
                sorted_periods = sorted(valid_period_cols)
        except Exception as e:
            logger.error(f"Error sorting period columns: {e}")
            sorted_periods = valid_period_cols
        
        return pivot_df[info_cols + sorted_periods]
        
    except Exception as e:
        logger.error(f"Error creating pivot: {str(e)}")
        return pd.DataFrame()


def create_download_button(df: pd.DataFrame, filename: str, 
                         button_label: str = "📥 Download Excel",
                         key: Optional[str] = None) -> None:
    """Create a download button for dataframe"""
    if df.empty:
        st.warning("No data available for download")
        return
        
    try:
        excel_data = convert_df_to_excel(df)
        
        st.download_button(
            label=button_label,
            data=excel_data,
            file_name=f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=key
        )
    except Exception as e:
        st.error(f"Error creating download: {str(e)}")


# === ANALYSIS FUNCTIONS ===

def calculate_fulfillment_rate(available: float, demand: float) -> float:
    """Calculate fulfillment rate percentage"""
    if demand <= 0:
        return 100.0 if available >= 0 else 0.0
    return min(100.0, max(0.0, (available / demand) * 100))


def calculate_days_of_supply(inventory: float, daily_demand: float) -> float:
    """Calculate days of supply"""
    if daily_demand <= 0:
        return float('inf') if inventory > 0 else 0.0
    return max(0.0, inventory / daily_demand)


def calculate_working_days(start_date: datetime, end_date: datetime, 
                         working_days_per_week: int = 5) -> int:
    """Calculate number of working days between two dates"""
    if pd.isna(start_date) or pd.isna(end_date):
        return 0
    
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    working_days_per_week = max(1, min(7, working_days_per_week))
    
    total_days = (end_date - start_date).days + 1
    
    if working_days_per_week == 7:
        return total_days
    
    full_weeks = total_days // 7
    remaining_days = total_days % 7
    
    working_days = full_weeks * working_days_per_week
    
    current_date = start_date + timedelta(days=full_weeks * 7)
    for _ in range(remaining_days):
        if current_date.weekday() < working_days_per_week:
            working_days += 1
        current_date += timedelta(days=1)
    
    return max(0, working_days)


# === NOTIFICATION HELPERS ===

def show_success_message(message: str, duration: int = 3):
    """Show success message that auto-disappears"""
    placeholder = st.empty()
    placeholder.success(message)
    
    import time
    time.sleep(duration)
    placeholder.empty()


# === EXPORT HELPERS ===

def create_multi_sheet_export(
    sheets_config: List[Dict[str, Any]],
    filename_prefix: str
) -> Tuple[Optional[bytes], Optional[str]]:
    """Create multi-sheet Excel export"""
    sheets_dict = {}
    
    for config in sheets_config:
        if 'name' not in config or 'data' not in config:
            logger.warning(f"Invalid sheet config: {config}")
            continue
            
        df = config['data']
        if df is not None and not df.empty:
            if 'formatter' in config and callable(config['formatter']):
                try:
                    df = config['formatter'](df)
                except Exception as e:
                    logger.error(f"Error applying formatter to sheet '{config['name']}': {e}")
            
            sheet_name = str(config['name'])[:EXCEL_SHEET_NAME_LIMIT]
            sheets_dict[sheet_name] = df
    
    if sheets_dict:
        try:
            excel_data = export_multiple_sheets(sheets_dict)
            filename = f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            return excel_data, filename
        except Exception as e:
            logger.error(f"Error creating multi-sheet export: {e}")
            return None, None
    
    return None, None