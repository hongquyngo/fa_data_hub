# utils/net_gap/calculation_result.py

"""
GAP Calculation Result Container - Cleaned Version
Removed unused to_excel_metadata method
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class CustomerImpact:
    """Customer impact data"""
    customer_df: pd.DataFrame
    affected_count: int
    at_risk_value: float
    shortage_qty: float
    
    def is_empty(self) -> bool:
        return self.customer_df.empty or self.affected_count == 0


@dataclass
class GAPCalculationResult:
    """
    Complete GAP calculation result container
    Single source of truth for the entire calculation
    """
    gap_df: pd.DataFrame
    metrics: Dict[str, Any]
    customer_impact: Optional[CustomerImpact]
    filters_used: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Source data references (for detailed analysis)
    supply_df: Optional[pd.DataFrame] = None
    demand_df: Optional[pd.DataFrame] = None
    safety_df: Optional[pd.DataFrame] = None
    
    def __post_init__(self):
        """Validate result on creation"""
        if self.gap_df is None or self.gap_df.empty:
            logger.warning("GAP result is empty")
        
        if self.metrics is None:
            raise ValueError("Metrics dictionary is required")
        
        logger.info(f"Result created: {len(self.gap_df)} items, "
                   f"{self.metrics.get('affected_customers', 0)} customers affected")
    
    def get_shortage_products(self) -> List[int]:
        """Get product IDs with shortages"""
        if self.gap_df.empty or 'product_id' not in self.gap_df.columns:
            return []
        
        shortage_df = self.gap_df[self.gap_df['net_gap'] < 0]
        return shortage_df['product_id'].tolist()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary for display/logging"""
        return {
            'items': len(self.gap_df),
            'shortage_items': self.metrics.get('shortage_items', 0),
            'surplus_items': self.metrics.get('surplus_items', 0),
            'coverage': f"{self.metrics.get('overall_coverage', 0):.1f}%",
            'at_risk_value': f"${self.metrics.get('at_risk_value_usd', 0):,.0f}",
            'affected_customers': self.metrics.get('affected_customers', 0),
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M')
        }
    
    def get_category_summary(self) -> Dict[str, int]:
        """Get item counts by simplified category"""
        if self.gap_df.empty:
            return {'shortage': 0, 'optimal': 0, 'surplus': 0, 'inactive': 0}
        
        from .constants import GAP_CATEGORIES
        
        counts = {}
        for category, config in GAP_CATEGORIES.items():
            mask = self.gap_df['gap_status'].isin(config['statuses'])
            counts[category.lower()] = len(self.gap_df[mask])
        
        return counts