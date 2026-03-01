# utils/net_gap/formatters.py - Fixed display for no-demand items

"""
Formatting utilities for GAP Analysis - Fixed no-demand display
"""

import pandas as pd
from typing import Union, Optional, Any

# Fields that should show 0 instead of N/A
ZERO_DEFAULT_FIELDS = [
    'supply', 'total_supply', 'available_supply',
    'supply_inventory', 'supply_can_pending',
    'supply_warehouse_transfer', 'supply_purchase_order',
    'safety_stock_qty', 'reorder_point'
]


class GAPFormatter:
    """Handles all formatting for display and export with logical no-demand handling"""
    
    # formatters.py
    @staticmethod
    def format_number(
        value: Any,
        decimals: int = 0,
        show_sign: bool = False,
        field_name: Optional[str] = None
    ) -> str:
        """
        Format number with thousand separators
        Supply fields show 0 instead of N/A
        """
        # Check if this is a supply field
        if pd.isna(value) or value is None:
            if field_name and any(field in field_name.lower() for field in ZERO_DEFAULT_FIELDS):
                return "0"
            return "N/A"
        
        try:
            # Format number with proper rounding
            if decimals == 0:
                # ✅ Use round() instead of int() to properly round
                formatted = f"{round(value):,}"
            else:
                formatted = f"{value:,.{decimals}f}"
            
            # Add sign if requested
            if show_sign and value > 0:
                formatted = f"+{formatted}"
            
            return formatted
            
        except (ValueError, TypeError):
            return str(value)


    @staticmethod
    def format_currency(
        value: Any,
        currency: str = "USD",
        decimals: int = 2,
        abbreviate: bool = False
    ) -> str:
        """Format value as currency"""
        
        if pd.isna(value) or value is None:
            return "N/A"
        
        try:
            # Handle abbreviation
            if abbreviate:
                if abs(value) >= 1e9:
                    return f"${value/1e9:.1f}B"
                elif abs(value) >= 1e6:
                    return f"${value/1e6:.1f}M"
                elif abs(value) >= 1e3:
                    return f"${value/1e3:.1f}K"
            
            # Standard format
            if currency == "USD":
                return f"${value:,.{decimals}f}"
            else:
                return f"{value:,.{decimals}f} {currency}"
                
        except (ValueError, TypeError):
            return str(value)
    
    @staticmethod
    def format_percentage(
        value: Any,
        decimals: int = 1,
        show_sign: bool = False,
        no_demand_text: str = "N/A"
    ) -> str:
        """Format as percentage with special handling for no-demand"""
        
        if pd.isna(value) or value is None:
            return no_demand_text
        
        try:
            formatted = f"{value:.{decimals}f}%"
            
            if show_sign and value > 0:
                formatted = f"+{formatted}"
            
            return formatted
            
        except (ValueError, TypeError):
            return str(value)
    
    @staticmethod
    def format_coverage(value: Any) -> str:
        """Format coverage ratio for display with logical no-demand handling"""
        
        # Handle NaN (no demand case)
        if pd.isna(value):
            return "No Demand"
        
        if value is None:
            return "N/A"
        
        try:
            # Normal coverage formatting
            if value > 10:  # >1000%
                return ">999%"
            elif value <= 0:
                return "0%"
            else:
                return f"{value*100:.0f}%"
                
        except (ValueError, TypeError):
            return str(value)
    
    @staticmethod
    def format_gap_percentage(value: Any) -> str:
        """Format GAP percentage with no-demand handling"""
        
        # Handle NaN (no demand case)
        if pd.isna(value):
            return "No Demand"
        
        if value is None:
            return "N/A"
        
        try:
            return f"{value:.1f}%"
        except (ValueError, TypeError):
            return str(value)
    
    @staticmethod
    def format_days(value: Any) -> str:
        """Format days value"""
        
        if pd.isna(value) or value is None:
            return "N/A"
        
        try:
            days = float(value)
            
            if days >= 365:
                return f"{days/365:.1f} years"
            elif days >= 30:
                return f"{days/30:.1f} months"
            else:
                return f"{int(days)} days"
                
        except (ValueError, TypeError):
            return str(value)