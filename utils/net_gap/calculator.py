# utils/net_gap/calculator.py - VERSION 4.5

"""
GAP Calculator - IMPROVED VERSION 4.5
KEY CHANGE: Status classification based on Net GAP SIGN first
- net_gap < 0 → Always SHORTAGE (with severity based on coverage)
- net_gap = 0 → BALANCED  
- net_gap > 0 → Always SURPLUS (with severity based on coverage)

This eliminates confusion where items with shortage (negative net_gap) 
were incorrectly classified as "Balanced"
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

from .calculation_result import GAPCalculationResult, CustomerImpact
from .constants import THRESHOLDS, GAP_CATEGORIES, STATUS_CONFIG

logger = logging.getLogger(__name__)


class GAPCalculator:
    """GAP calculation engine - v4.5 with improved status classification"""
    
    def calculate_net_gap(
        self,
        supply_df: pd.DataFrame,
        demand_df: pd.DataFrame,
        safety_stock_df: Optional[pd.DataFrame] = None,
        expired_inventory_df: Optional[pd.DataFrame] = None,
        group_by: str = 'product',
        selected_supply_sources: Optional[List[str]] = None,
        selected_demand_sources: Optional[List[str]] = None,
        include_safety_stock: bool = False
    ) -> GAPCalculationResult:
        """Calculate net GAP analysis"""
        try:
            # Log incoming data structure
            logger.info(f"GAP Calculation started (v4.5):")
            logger.info(f"  - Supply rows: {len(supply_df)}, columns: {list(supply_df.columns) if not supply_df.empty else 'EMPTY'}")
            logger.info(f"  - Demand rows: {len(demand_df)}, columns: {list(demand_df.columns) if not demand_df.empty else 'EMPTY'}")
            logger.info(f"  - Selected supply sources: {selected_supply_sources}")
            logger.info(f"  - Selected demand sources: {selected_demand_sources}")
            
            # Validate group_by
            if group_by not in ['product', 'brand']:
                group_by = 'product'
            
            # Filter by selected sources (with defensive checks)
            if selected_supply_sources and not supply_df.empty:
                if 'supply_source' in supply_df.columns:
                    supply_df = supply_df[supply_df['supply_source'].isin(selected_supply_sources)]
                    logger.info(f"Filtered supply by sources: {selected_supply_sources}")
                else:
                    logger.warning("supply_source column not found in supply_df, skipping source filter")
            
            if selected_demand_sources and not demand_df.empty:
                if 'demand_source' in demand_df.columns:
                    demand_df = demand_df[demand_df['demand_source'].isin(selected_demand_sources)]
                    logger.info(f"Filtered demand by sources: {selected_demand_sources}")
                else:
                    logger.warning("demand_source column not found in demand_df, skipping source filter")
            
            # Get grouping columns
            group_cols = self._get_group_columns(group_by)
            
            # Aggregate data
            supply_agg = self._aggregate_supply(supply_df, group_cols, group_by)
            demand_agg = self._aggregate_demand(demand_df, group_cols, group_by)
            
            # Merge data
            gap_df = self._merge_data(supply_agg, demand_agg, group_by)
            
            # Add safety stock if needed
            if include_safety_stock and safety_stock_df is not None:
                gap_df = self._add_safety_stock(gap_df, safety_stock_df, group_by)
            
            # Calculate GAP metrics
            gap_df = self._calculate_metrics(gap_df, include_safety_stock)
            
            # Add expired inventory data if provided
            if expired_inventory_df is not None and not expired_inventory_df.empty and group_by == "product":
                gap_df = gap_df.merge(
                    expired_inventory_df[["product_id", "expired_quantity", "expired_batches_info"]],
                    on="product_id",
                    how="left"
                )
                gap_df["expired_quantity"] = gap_df["expired_quantity"].fillna(0)
                gap_df["expired_batches_info"] = gap_df["expired_batches_info"].fillna("")
            else:
                gap_df["expired_quantity"] = 0
                gap_df["expired_batches_info"] = ""
            
            # Sort by priority
            gap_df = gap_df.sort_values(['priority', 'net_gap'], ascending=[True, True])
            
            # Calculate summary metrics
            metrics = self._calculate_summary_metrics(gap_df, demand_df, include_safety_stock)
            
            # Calculate customer impact
            customer_impact = None
            if group_by == 'product':
                customer_impact = self._calculate_customer_impact(gap_df, demand_df)
            
            # Create result
            filters_used = {
                'group_by': group_by,
                'supply_sources': selected_supply_sources or ['ALL'],
                'demand_sources': selected_demand_sources or ['ALL'],
                'include_safety_stock': include_safety_stock
            }
            
            result = GAPCalculationResult(
                gap_df=gap_df,
                metrics=metrics,
                customer_impact=customer_impact,
                filters_used=filters_used,
                supply_df=supply_df,
                demand_df=demand_df,
                safety_df=safety_stock_df
            )
            
            logger.info(f"GAP calculation completed: {len(gap_df)} items")
            return result
            
        except Exception as e:
            logger.error(f"GAP calculation failed: {e}", exc_info=True)
            raise
    
    def _get_group_columns(self, group_by: str) -> List[str]:
        """Get columns for grouping"""
        if group_by == 'product':
            return ['product_id']
        else:
            return ['brand']
    
    def _aggregate_supply(self, df: pd.DataFrame, group_cols: List[str], group_by: str) -> pd.DataFrame:
        """Aggregate supply data"""
        if df.empty:
            return pd.DataFrame()
        
        supply_df = df.copy()
        
        agg_dict = {
            'available_quantity': 'sum',
            'total_value_usd': 'sum'
        }
        
        if group_by == 'product':
            agg_dict.update({
                'product_name': 'first',
                'pt_code': 'first',
                'brand': 'first',
                'standard_uom': 'first'
            })
        
        for source in supply_df['supply_source'].unique():
            col_name = f'supply_{source.lower()}'
            supply_df[col_name] = np.where(
                supply_df['supply_source'] == source,
                supply_df['available_quantity'],
                0
            )
            agg_dict[col_name] = 'sum'
        
        if 'unit_cost_usd' in supply_df.columns:
            supply_df['cost_x_qty'] = supply_df['unit_cost_usd'] * supply_df['available_quantity']
            agg_dict['cost_x_qty'] = 'sum'
        
        supply_agg = supply_df.groupby(group_cols, as_index=False).agg(agg_dict)
        
        supply_agg.rename(columns={
            'available_quantity': 'total_supply',
            'total_value_usd': 'supply_value_usd'
        }, inplace=True)
        
        if 'cost_x_qty' in supply_agg.columns:
            supply_agg['avg_unit_cost_usd'] = np.where(
                supply_agg['total_supply'] > 0,
                supply_agg['cost_x_qty'] / supply_agg['total_supply'],
                0
            )
            supply_agg.drop('cost_x_qty', axis=1, inplace=True)
        
        return supply_agg
    
    def _aggregate_demand(self, df: pd.DataFrame, group_cols: List[str], group_by: str) -> pd.DataFrame:
        """Aggregate demand data"""
        if df.empty:
            return pd.DataFrame()
        
        demand_df = df.copy()
        
        agg_dict = {
            'required_quantity': 'sum',
            'total_value_usd': 'sum',
            'customer': 'nunique'
        }
        
        if group_by == 'product':
            agg_dict.update({
                'product_name': 'first',
                'pt_code': 'first',
                'brand': 'first',
                'standard_uom': 'first'
            })
        
        for source in demand_df['demand_source'].unique():
            col_name = f'demand_{source.lower()}'
            demand_df[col_name] = np.where(
                demand_df['demand_source'] == source,
                demand_df['required_quantity'],
                0
            )
            agg_dict[col_name] = 'sum'
        
        if 'urgency_level' in demand_df.columns:
            urgency_map = {'OVERDUE': 1, 'URGENT': 2, 'UPCOMING': 3, 'FUTURE': 4}
            demand_df['urgency_numeric'] = demand_df['urgency_level'].map(urgency_map).fillna(5)
            agg_dict['urgency_numeric'] = 'min'
        
        demand_agg = demand_df.groupby(group_cols, as_index=False).agg(agg_dict)
        
        demand_agg.rename(columns={
            'required_quantity': 'total_demand',
            'total_value_usd': 'demand_value_usd',
            'customer': 'customer_count'
        }, inplace=True)
        
        demand_agg['avg_selling_price_usd'] = np.where(
            demand_agg['total_demand'] > 0,
            demand_agg['demand_value_usd'] / demand_agg['total_demand'],
            0
        )
        
        if 'urgency_numeric' in demand_agg.columns:
            urgency_reverse = {1: 'OVERDUE', 2: 'URGENT', 3: 'UPCOMING', 4: 'FUTURE', 5: 'N/A'}
            demand_agg['urgency'] = demand_agg['urgency_numeric'].map(urgency_reverse)
            demand_agg.drop('urgency_numeric', axis=1, inplace=True)
        
        return demand_agg
    
    def _merge_data(
        self,
        supply_df: pd.DataFrame,
        demand_df: pd.DataFrame,
        group_by: str
    ) -> pd.DataFrame:
        """Merge supply and demand data"""
        
        if group_by == 'product':
            merge_cols = ['product_id']
        else:
            merge_cols = ['brand']
        
        if not supply_df.empty and not demand_df.empty:
            gap_df = pd.merge(supply_df, demand_df, on=merge_cols, how='outer', suffixes=('_supply', '_demand'))
            
            if group_by == 'product':
                for col in ['product_name', 'pt_code', 'brand', 'standard_uom']:
                    if f'{col}_supply' in gap_df.columns and f'{col}_demand' in gap_df.columns:
                        gap_df[col] = gap_df[f'{col}_supply'].fillna(gap_df[f'{col}_demand'])
                        gap_df.drop([f'{col}_supply', f'{col}_demand'], axis=1, inplace=True)
                    elif f'{col}_supply' in gap_df.columns:
                        gap_df.rename(columns={f'{col}_supply': col}, inplace=True)
                    elif f'{col}_demand' in gap_df.columns:
                        gap_df.rename(columns={f'{col}_demand': col}, inplace=True)
        elif not supply_df.empty:
            gap_df = supply_df.copy()
        elif not demand_df.empty:
            gap_df = demand_df.copy()
        else:
            return pd.DataFrame()
        
        numeric_cols = gap_df.select_dtypes(include=[np.number]).columns.tolist()
        gap_df[numeric_cols] = gap_df[numeric_cols].fillna(0)
        
        return gap_df
    
    def _add_safety_stock(
        self,
        gap_df: pd.DataFrame,
        safety_df: pd.DataFrame,
        group_by: str
    ) -> pd.DataFrame:
        """Add safety stock data"""
        
        if safety_df.empty or group_by != 'product':
            gap_df['safety_stock_qty'] = 0
            gap_df['reorder_point'] = 0
            return gap_df
        
        available_cols = ['product_id']
        desired_cols = ['safety_stock_qty', 'reorder_point', 'avg_daily_demand']
        
        for col in desired_cols:
            if col in safety_df.columns:
                available_cols.append(col)
            else:
                logger.warning(f"Column {col} not found in safety_stock_df, using default value 0")
        
        safety_data = safety_df[available_cols].copy()
        safety_data = safety_data.groupby('product_id').first().reset_index()
        gap_df = pd.merge(gap_df, safety_data, on='product_id', how='left')
        
        for col in desired_cols:
            if col not in gap_df.columns:
                gap_df[col] = 0
            else:
                gap_df[col] = gap_df[col].fillna(0)
        
        return gap_df
    
    def _calculate_metrics(self, gap_df: pd.DataFrame, include_safety: bool) -> pd.DataFrame:
        """
        Calculate GAP metrics
        v4.5: Improved status classification based on net_gap sign
        """
        
        if 'total_supply' not in gap_df.columns:
            gap_df['total_supply'] = 0
            logger.warning("total_supply column missing, initialized to 0")
        
        if 'total_demand' not in gap_df.columns:
            gap_df['total_demand'] = 0
            logger.warning("total_demand column missing, initialized to 0")
        
        # Available supply (considering safety stock)
        if include_safety and 'safety_stock_qty' in gap_df.columns:
            gap_df['available_supply'] = np.maximum(
                0,
                gap_df['total_supply'] - gap_df['safety_stock_qty']
            )
        else:
            gap_df['available_supply'] = gap_df['total_supply']
        
        # Net GAP
        gap_df['net_gap'] = gap_df['available_supply'] - gap_df['total_demand']
        
        # True GAP (always ignores safety stock)
        gap_df['true_gap'] = gap_df['total_supply'] - gap_df['total_demand']
        
        # Safety Gap = Total Supply - Safety Stock (can be negative)
        if include_safety and 'safety_stock_qty' in gap_df.columns:
            gap_df['safety_gap'] = gap_df['total_supply'] - gap_df['safety_stock_qty']
        else:
            gap_df['safety_gap'] = np.nan
        
        # Coverage ratio
        gap_df['coverage_ratio'] = np.where(
            gap_df['total_demand'] > 0,
            gap_df['available_supply'] / gap_df['total_demand'],
            np.nan
        )
        
        # GAP percentage
        gap_df['gap_percentage'] = np.where(
            gap_df['total_demand'] > 0,
            (gap_df['net_gap'] / gap_df['total_demand']) * 100,
            np.nan
        )
        
        # Safety metrics
        if include_safety and 'safety_stock_qty' in gap_df.columns:
            gap_df['safety_coverage'] = np.where(
                gap_df['safety_stock_qty'] > 0,
                gap_df.get('supply_inventory', gap_df['total_supply']) / gap_df['safety_stock_qty'],
                np.nan
            )
            
            gap_df['below_reorder'] = (
                gap_df.get('supply_inventory', gap_df['total_supply']) <= gap_df['reorder_point']
            ) & (gap_df['reorder_point'] > 0)
        
        # v4.5: Status classification with NEW logic
        gap_df['gap_status'] = gap_df.apply(
            lambda row: self._classify_status_v45(row, include_safety), 
            axis=1
        )
        
        # Priority
        gap_df['priority'] = gap_df.apply(self._get_priority, axis=1)
        
        # Suggested action
        gap_df['suggested_action'] = gap_df.apply(self._get_action, axis=1)
        
        # Shortage cause
        gap_df['shortage_cause'] = gap_df.apply(
            lambda row: self._classify_shortage_cause(row, include_safety), 
            axis=1
        )
        
        # Financial metrics
        if 'avg_unit_cost_usd' not in gap_df.columns:
            gap_df['avg_unit_cost_usd'] = 0
        
        if 'avg_selling_price_usd' not in gap_df.columns:
            gap_df['avg_selling_price_usd'] = 0
        
        if 'supply_value_usd' not in gap_df.columns:
            gap_df['supply_value_usd'] = 0
        
        if 'demand_value_usd' not in gap_df.columns:
            gap_df['demand_value_usd'] = 0
        
        gap_df['gap_value_usd'] = gap_df['net_gap'] * gap_df['avg_unit_cost_usd']
        
        gap_df['at_risk_value_usd'] = np.where(
            gap_df['net_gap'] < 0,
            abs(gap_df['net_gap']) * gap_df['avg_selling_price_usd'],
            0
        )
        
        return gap_df
    
    def _classify_status_v45(self, row: pd.Series, include_safety: bool) -> str:
        """
        v4.5 STATUS CLASSIFICATION LOGIC - FIXED
        
        PRINCIPLE: Net GAP sign determines GROUP (PRIMARY), Coverage determines SEVERITY
        - net_gap < 0 → SHORTAGE group (ALWAYS!)
        - net_gap = 0 → BALANCED
        - net_gap > 0 → SURPLUS group (ALWAYS!)
        
        Safety stock info is shown in:
        - Shortage Cause column (e.g., "🔒 Supply < Safety Req.")
        - Action column (e.g., "🚨 CRITICAL: Only 3 vs 25 safety")
        
        NOT in Status column - to maintain consistency with Option A logic
        """
        
        demand = row.get('total_demand', 0)
        supply = row.get('total_supply', 0)
        net_gap = row.get('net_gap', 0)
        coverage = row.get('coverage_ratio')
        
        # ===== STEP 1: Check for NO DEMAND cases =====
        if demand == 0:
            if supply > 0:
                return 'NO_DEMAND'
            else:
                return 'NO_ACTIVITY'
        
        # ===== STEP 2: Classify by NET GAP SIGN (PRIMARY LOGIC) =====
        # Safety info is handled separately in Shortage Cause and Action columns
        
        # Handle NaN coverage
        if pd.isna(coverage):
            coverage = 0 if net_gap < 0 else 1
        
        # ---------- SHORTAGE GROUP (net_gap < 0) ----------
        if net_gap < 0:
            shortage_thresholds = THRESHOLDS.get('shortage', {})
            
            if coverage < shortage_thresholds.get('critical', 0.25):
                return 'CRITICAL_SHORTAGE'
            elif coverage < shortage_thresholds.get('severe', 0.50):
                return 'SEVERE_SHORTAGE'
            elif coverage < shortage_thresholds.get('high', 0.75):
                return 'HIGH_SHORTAGE'
            elif coverage < shortage_thresholds.get('moderate', 0.90):
                return 'MODERATE_SHORTAGE'
            else:
                return 'LIGHT_SHORTAGE'
        
        # ---------- BALANCED (net_gap = 0) ----------
        elif net_gap == 0:
            return 'BALANCED'
        
        # ---------- SURPLUS GROUP (net_gap > 0) ----------
        else:
            surplus_thresholds = THRESHOLDS.get('surplus', {})
            
            if coverage <= surplus_thresholds.get('light', 1.25):
                return 'LIGHT_SURPLUS'
            elif coverage <= surplus_thresholds.get('moderate', 1.75):
                return 'MODERATE_SURPLUS'
            elif coverage <= surplus_thresholds.get('high', 2.50):
                return 'HIGH_SURPLUS'
            else:
                return 'SEVERE_SURPLUS'
    
    def _get_priority(self, row: pd.Series) -> int:
        """
        Get priority level based on status
        UPDATED: Safety severity is factored into shortage priority
        """
        
        status = row.get('gap_status', '')
        net_gap = row.get('net_gap', 0)
        safety_gap = row.get('safety_gap', 0) if 'safety_gap' in row.index else None
        
        # Critical priority (P1) - Critical/Severe shortage OR any shortage with critical safety breach
        if status in ['CRITICAL_SHORTAGE', 'SEVERE_SHORTAGE']:
            return THRESHOLDS['priority']['critical']
        
        # Check if shortage + critical safety issue (supply < 50% safety)
        if status in ['HIGH_SHORTAGE', 'MODERATE_SHORTAGE', 'LIGHT_SHORTAGE']:
            if safety_gap is not None and not pd.isna(safety_gap):
                safety_stock = row.get('safety_stock_qty', 0)
                supply = row.get('total_supply', 0)
                if safety_stock > 0 and supply < safety_stock * 0.5:
                    return THRESHOLDS['priority']['critical']  # Upgrade to P1
        
        # High priority (P2)
        if status in ['HIGH_SHORTAGE', 'SEVERE_SURPLUS']:
            return THRESHOLDS['priority']['high']
        
        # Medium priority (P3)
        if status in ['MODERATE_SHORTAGE', 'HIGH_SURPLUS', 'MODERATE_SURPLUS']:
            return THRESHOLDS['priority']['medium']
        
        # Low priority (P4)
        if status in ['LIGHT_SHORTAGE', 'LIGHT_SURPLUS']:
            return THRESHOLDS['priority']['low']
        
        # OK (P99)
        return THRESHOLDS['priority']['ok']
    
    def _get_action(self, row: pd.Series) -> str:
        """
        Get suggested action based on status - ENHANCED VERSION v4.5
        Includes: $ at risk, PO incoming, timeline, coverage %, days of stock
        Safety warnings are integrated into shortage actions
        """
        
        status = row.get('gap_status', '')
        net_gap = row.get('net_gap', 0)
        true_gap = row.get('true_gap', 0)
        at_risk = row.get('at_risk_value_usd', 0) or 0
        safety_gap = row.get('safety_gap', 0) or 0
        safety_stock = row.get('safety_stock_qty', 0) or 0
        total_supply = row.get('total_supply', 0) or 0
        total_demand = row.get('total_demand', 0) or 0
        coverage = row.get('coverage_ratio', 0) or 0
        
        # Check incoming PO
        incoming_po = row.get('supply_purchase_order', 0) or 0
        
        # Check safety severity
        is_critical_safety = safety_stock > 0 and total_supply < safety_stock * 0.5
        is_below_safety = safety_stock > 0 and total_supply < safety_stock
        
        # ===== CRITICAL SHORTAGE =====
        if status == 'CRITICAL_SHORTAGE':
            action = f"🚨 ORDER {abs(net_gap):.0f} units TODAY"
            if is_critical_safety:
                action += f" | ⚠️ Only {total_supply:.0f} vs {safety_stock:.0f} safety!"
            elif at_risk > 0:
                action += f" | ${at_risk:,.0f} at risk"
            if incoming_po > 0:
                action += f" | PO: {incoming_po:.0f} coming"
            return action
        
        # ===== SEVERE SHORTAGE =====
        elif status == 'SEVERE_SHORTAGE':
            action = f"🔴 Order {abs(net_gap):.0f} units within 24h"
            if is_critical_safety:
                action += f" | ⚠️ Below 50% safety!"
            elif at_risk > 0:
                action += f" | ${at_risk:,.0f} at risk"
            if incoming_po > 0:
                action += f" | PO: {incoming_po:.0f}"
            return action
        
        # ===== HIGH SHORTAGE =====
        elif status == 'HIGH_SHORTAGE':
            action = f"🟠 Order {abs(net_gap):.0f} units within 48h"
            if is_below_safety:
                action += f" | ⚠️ Below safety ({total_supply:.0f}/{safety_stock:.0f})"
            elif incoming_po > 0:
                action += f" | PO incoming: {incoming_po:.0f}"
            elif at_risk > 0:
                action += f" | ${at_risk:,.0f} at risk"
            return action
        
        # ===== MODERATE SHORTAGE =====
        elif status == 'MODERATE_SHORTAGE':
            action = f"🟡 Order {abs(net_gap):.0f} units this week"
            if is_below_safety:
                action += f" | ⚠️ Below safety"
            elif coverage > 0:
                action += f" | Coverage: {coverage*100:.0f}%"
            return action
        
        # ===== LIGHT SHORTAGE =====
        elif status == 'LIGHT_SHORTAGE':
            # Special case: Light shortage but critical safety issue
            if is_critical_safety:
                return f"⚠️ Gap: {abs(net_gap):.0f} | 🚨 Only {total_supply:.0f} vs {safety_stock:.0f} safety!"
            elif is_below_safety:
                gap_to_safety = abs(safety_gap)
                return f"⚠️ Gap: {abs(net_gap):.0f} | Need +{gap_to_safety:.0f} to reach safety"
            elif incoming_po >= abs(net_gap):
                return f"⚠️ Gap: {abs(net_gap):.0f} | PO covers: {incoming_po:.0f} incoming"
            
            action = f"⚠️ Consider ordering {abs(net_gap):.0f} units"
            if coverage > 0:
                action += f" | Coverage: {coverage*100:.0f}%"
            return action
        
        # ===== BALANCED =====
        elif status == 'BALANCED':
            if is_below_safety:
                return f"✅ Demand met | ⚠️ But below safety ({total_supply:.0f}/{safety_stock:.0f})"
            return "✅ OK - Monitor weekly"
        
        # ===== LIGHT SURPLUS =====
        elif status == 'LIGHT_SURPLUS':
            return f"🔵 +{net_gap:.0f} surplus | OK - Reduce next order"
        
        # ===== MODERATE SURPLUS =====
        elif status == 'MODERATE_SURPLUS':
            return f"🟣 +{net_gap:.0f} surplus | Hold new orders | Consider promotion"
        
        # ===== HIGH SURPLUS =====
        elif status == 'HIGH_SURPLUS':
            days_of_stock = (total_supply / total_demand * 30) if total_demand > 0 else 999
            if days_of_stock < 999:
                return f"🟠 +{net_gap:.0f} surplus (~{days_of_stock:.0f} days) | Stop ordering"
            return f"🟠 +{net_gap:.0f} surplus | Stop ordering"
        
        # ===== SEVERE SURPLUS =====
        elif status == 'SEVERE_SURPLUS':
            return f"🔴 +{net_gap:.0f} excess | Cancel PO | Transfer/discount"
        
        # ===== NO DEMAND =====
        elif status == 'NO_DEMAND':
            if total_supply > 0:
                return f"⚪ {total_supply:.0f} units idle | Review: transfer/discontinue"
            return "⚪ No demand"
        
        # ===== NO ACTIVITY =====
        elif status == 'NO_ACTIVITY':
            return "⚪ Inactive SKU - Review status"
        
        return "Review manually"
    
    def _classify_shortage_cause(self, row: pd.Series, include_safety: bool) -> str:
        """Classify the cause of shortage for better user understanding"""
        
        net_gap = row.get('net_gap', 0)
        true_gap = row.get('true_gap', 0)
        total_supply = row.get('total_supply', 0)
        total_demand = row.get('total_demand', 0)
        safety_stock = row.get('safety_stock_qty', 0) if include_safety else 0
        
        if total_demand == 0:
            if total_supply > 0:
                return "⚪ No Demand"
            return "⚪ Inactive"
        
        if net_gap >= 0:
            return "✅ OK"
        
        # Has shortage - determine cause
        if true_gap < 0:
            if include_safety and safety_stock > 0 and total_supply < safety_stock:
                return "🚨 Real + Below Safety"
            return "🚨 Real Shortage"
        elif true_gap >= 0 and net_gap < 0:
            if include_safety and total_supply < safety_stock:
                return "🔒 Supply < Safety Req."
            return "🔒 Safety Requirement"
        
        return "⚠️ Review"
    
    def _calculate_summary_metrics(
        self,
        gap_df: pd.DataFrame,
        demand_df: pd.DataFrame,
        include_safety: bool
    ) -> Dict[str, any]:
        """Calculate summary metrics"""
        
        shortage_statuses = GAP_CATEGORIES['SHORTAGE']['statuses']
        surplus_statuses = GAP_CATEGORIES['SURPLUS']['statuses']
        
        affected_customers = 0
        if 'product_id' in gap_df.columns and not demand_df.empty:
            shortage_products = gap_df[gap_df['net_gap'] < 0]['product_id'].tolist()
            if shortage_products:
                affected_demand = demand_df[demand_df['product_id'].isin(shortage_products)]
                affected_customers = affected_demand['customer'].nunique()
        
        metrics = {
            'total_products': len(gap_df),
            'total_supply': gap_df.get('total_supply', pd.Series([0])).sum(),
            'total_demand': gap_df.get('total_demand', pd.Series([0])).sum(),
            'net_gap': gap_df.get('net_gap', pd.Series([0])).sum(),
            
            'shortage_items': len(gap_df[gap_df['gap_status'].isin(shortage_statuses)]),
            'surplus_items': len(gap_df[gap_df['gap_status'].isin(surplus_statuses)]),
            'critical_items': len(gap_df[gap_df.get('priority', 99) == THRESHOLDS['priority']['critical']]),
            
            'total_shortage': abs(gap_df[gap_df['net_gap'] < 0]['net_gap'].sum()) if 'net_gap' in gap_df.columns else 0,
            'total_surplus': gap_df[gap_df['net_gap'] > 0]['net_gap'].sum() if 'net_gap' in gap_df.columns else 0,
            
            'overall_coverage': self._calculate_overall_coverage(gap_df),
            'at_risk_value_usd': gap_df.get('at_risk_value_usd', pd.Series([0])).sum(),
            'gap_value_usd': gap_df.get('gap_value_usd', pd.Series([0])).sum(),
            'total_supply_value_usd': gap_df.get('supply_value_usd', pd.Series([0])).sum(),
            'total_demand_value_usd': gap_df.get('demand_value_usd', pd.Series([0])).sum(),
            
            'affected_customers': affected_customers
        }
        
        if include_safety and 'below_reorder' in gap_df.columns:
            metrics.update({
                'below_safety_count': len(gap_df[gap_df['gap_status'].isin(['BELOW_SAFETY', 'CRITICAL_BREACH'])]),
                'at_reorder_count': len(gap_df[gap_df['below_reorder'] == True]),
                'has_expired_count': 0,
                'expiry_risk_count': 0
            })
        
        return metrics
    
    def _calculate_overall_coverage(self, gap_df: pd.DataFrame) -> float:
        """Calculate overall coverage percentage"""
        
        if 'total_demand' not in gap_df.columns or 'total_supply' not in gap_df.columns:
            logger.warning("Missing total_demand or total_supply columns for coverage calculation")
            return 0.0
        
        items_with_demand = gap_df[gap_df['total_demand'] > 0]
        
        if items_with_demand.empty:
            return 100.0
        
        if 'available_supply' in items_with_demand.columns:
            total_supply = items_with_demand['available_supply'].sum()
        else:
            total_supply = items_with_demand['total_supply'].sum()
        
        total_demand = items_with_demand['total_demand'].sum()
        
        if total_demand > 0:
            return (total_supply / total_demand) * 100
        return 100.0
    
    def _calculate_customer_impact(
        self,
        gap_df: pd.DataFrame,
        demand_df: pd.DataFrame
    ) -> Optional[CustomerImpact]:
        """Calculate customer impact for shortage items"""
        
        try:
            shortage_df = gap_df[gap_df['net_gap'] < 0]
            
            if shortage_df.empty or demand_df.empty:
                return None
            
            shortage_products = shortage_df['product_id'].tolist()
            affected_demand = demand_df[demand_df['product_id'].isin(shortage_products)].copy()
            
            if affected_demand.empty:
                return None
            
            shortage_lookup = shortage_df.set_index('product_id')[
                ['net_gap', 'total_demand', 'at_risk_value_usd', 'coverage_ratio']
            ].to_dict('index')
            
            affected_demand['product_shortage'] = affected_demand.apply(
                lambda row: abs(shortage_lookup.get(row['product_id'], {}).get('net_gap', 0)) *
                (row['required_quantity'] / shortage_lookup.get(row['product_id'], {}).get('total_demand', 1))
                if row['product_id'] in shortage_lookup and shortage_lookup[row['product_id']]['total_demand'] > 0
                else 0,
                axis=1
            )
            
            affected_demand['product_risk'] = affected_demand.apply(
                lambda row: shortage_lookup.get(row['product_id'], {}).get('at_risk_value_usd', 0) *
                (row['required_quantity'] / shortage_lookup.get(row['product_id'], {}).get('total_demand', 1))
                if row['product_id'] in shortage_lookup and shortage_lookup[row['product_id']]['total_demand'] > 0
                else 0,
                axis=1
            )
            
            customer_agg = affected_demand.groupby('customer').agg({
                'required_quantity': 'sum',
                'product_id': 'nunique',
                'total_value_usd': 'sum',
                'product_shortage': 'sum',
                'product_risk': 'sum',
                'urgency_level': 'min',
                'customer_code': 'first'
            }).reset_index()
            
            customer_agg.rename(columns={
                'required_quantity': 'total_required',
                'product_id': 'product_count',
                'total_value_usd': 'total_demand_value',
                'product_shortage': 'total_shortage',
                'product_risk': 'at_risk_value',
                'urgency_level': 'urgency'
            }, inplace=True)
            
            customer_df = customer_agg.sort_values('at_risk_value', ascending=False)
            customer_df['products'] = [[] for _ in range(len(customer_df))]
            
            return CustomerImpact(
                customer_df=customer_df,
                affected_count=len(customer_df),
                at_risk_value=customer_df['at_risk_value'].sum(),
                shortage_qty=customer_df['total_shortage'].sum()
            )
            
        except Exception as e:
            logger.error(f"Error calculating customer impact: {e}")
            return None