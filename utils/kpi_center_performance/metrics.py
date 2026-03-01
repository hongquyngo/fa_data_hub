# utils/kpi_center_performance/metrics.py
"""
KPI Calculations for KPI Center Performance

VERSION: 4.0.1
CHANGELOG:
- v4.0.1: BUGFIX - Forecast Target proration
  - Added: _calculate_forecast_proration() for full period target
  - Fixed: calculate_pipeline_forecast_metrics uses forecast proration
  - YTD: Target = 100% of annual (not prorated to filter date)
  - QTD: Target = 25% of annual (full quarter)
  - MTD: Target = 1/12 of annual (full month)
"""

import logging
import calendar
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from .constants import MONTH_ORDER

logger = logging.getLogger(__name__)


class KPICenterMetrics:
    """
    KPI calculations for KPI Center performance.
    
    Usage:
        metrics = KPICenterMetrics(sales_df, targets_df)
        overview = metrics.calculate_overview_metrics('YTD', 2025)
    
    Note: For monthly summary and KPI Center aggregation, use DataProcessor instead:
        processor = DataProcessor(unified_cache)
        monthly_df = processor.prepare_monthly_summary(sales_df)
        by_kpi_center_df = processor.aggregate_by_kpi_center(sales_df)
    """
    
    # FALLBACK weights - only used when DB doesn't have kpi_types data
    # UPDATED v5.1.0: Renamed from DEFAULT_KPI_WEIGHTS to clarify it's a fallback
    # Actual weights should come from kpi_types.default_weight in DB
    FALLBACK_KPI_WEIGHTS = {
        'gross_profit': 95,
        'gross_profit_1': 100,
        'gp1': 100,  # alias for gross_profit_1
        'revenue': 90,
        'purchase_value': 80,
        'new_business_revenue': 75,
        'num_new_customers': 60,
        'num_new_combos': 55,
        'num_new_products': 50,
        'num_new_projects': 50,
    }
    
    def __init__(
        self, 
        sales_df: pd.DataFrame, 
        targets_df: pd.DataFrame = None,
        default_weights: Dict[str, int] = None,
        hierarchy_df: pd.DataFrame = None  # NEW v5.2.0: For recursive rollup
    ):
        """
        Initialize with data.
        
        Args:
            sales_df: Sales data from unified view
            targets_df: KPI targets (optional)
            default_weights: Dict mapping kpi_name → default_weight from kpi_types table
                            Used for parent rollup when center has no direct assignment
                            PRIORITY: DB weights > fallback weights
            hierarchy_df: KPI Center hierarchy (NEW v5.2.0) - needed for recursive rollup
        """
        self.sales_df = sales_df
        self.targets_df = targets_df if targets_df is not None else pd.DataFrame()
        self.hierarchy_df = hierarchy_df if hierarchy_df is not None else pd.DataFrame()
        
        # UPDATED v5.1.0: DB weights have PRIORITY over fallback
        # Start with fallback, then override with DB values
        self.default_weights = {**self.FALLBACK_KPI_WEIGHTS}
        if default_weights:
            # DB weights override fallback
            for k, v in default_weights.items():
                key_lower = k.lower()
                self.default_weights[key_lower] = v
                # Also update alias if needed
                if key_lower == 'gross_profit_1':
                    self.default_weights['gp1'] = v
        
        # NEW v5.2.0: Build parent-children map for recursive rollup
        self._children_map = self._build_children_map()
        
        # DEBUG v5.1.0: Log loaded weights
        logger.debug(f"[KPICenterMetrics] Initialized with default_weights: {self.default_weights}")
    
    def _build_children_map(self) -> Dict[int, List[int]]:
        """
        Build a map of parent_id → [child_ids] from hierarchy_df.
        
        NEW v5.2.0: Used for recursive rollup calculation.
        """
        children_map = {}
        if self.hierarchy_df.empty:
            return children_map
        
        for _, row in self.hierarchy_df.iterrows():
            parent_id = row.get('parent_center_id')
            center_id = row.get('kpi_center_id')
            
            if pd.notna(parent_id) and center_id:
                parent_id = int(parent_id)
                center_id = int(center_id)
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(center_id)
        
        return children_map
    
    def _get_effective_centers_for_kpi(
        self,
        root_center_id: int,
        kpi_name: str,
        selected_center_ids: List[int]
    ) -> List[int]:
        """
        Get list of center IDs whose assignments should be used for rollup.
        
        NEW v5.2.0: Implements recursive rollup with STOP condition.
        
        Logic:
        - If center has assignment for this KPI → STOP, return [center_id]
        - If center has no assignment → recursively get from children
        - Only consider centers within selected_center_ids
        
        Args:
            root_center_id: Starting center ID for rollup
            kpi_name: KPI type name (e.g., 'revenue', 'gross_profit')
            selected_center_ids: List of center IDs in current selection
            
        Returns:
            List of center IDs whose assignments should be aggregated
        """
        # Check if this center is in selection
        if root_center_id not in selected_center_ids:
            return []
        
        # Check if this center has assignment for this KPI
        if not self.targets_df.empty:
            center_assignments = self.targets_df[
                (self.targets_df['kpi_center_id'] == root_center_id) &
                (self.targets_df['kpi_name'].str.lower() == kpi_name.lower())
            ]
            if not center_assignments.empty:
                # STOP condition: this center has assignment, use it directly
                return [root_center_id]
        
        # No assignment for this center, recurse to children
        children = self._children_map.get(root_center_id, [])
        effective_centers = []
        
        for child_id in children:
            if child_id in selected_center_ids:
                child_effective = self._get_effective_centers_for_kpi(
                    child_id, kpi_name, selected_center_ids
                )
                effective_centers.extend(child_effective)
        
        return effective_centers
    
    def _find_root_centers(self, selected_center_ids: List[int]) -> List[int]:
        """
        Find root center(s) in the selection - centers without parent in selection.
        
        NEW v5.2.0: Used to start recursive rollup from correct level.
        """
        if not selected_center_ids or self.hierarchy_df.empty:
            return selected_center_ids
        
        roots = []
        for center_id in selected_center_ids:
            # Find parent of this center
            center_row = self.hierarchy_df[self.hierarchy_df['kpi_center_id'] == center_id]
            if center_row.empty:
                roots.append(center_id)
                continue
            
            parent_id = center_row['parent_center_id'].iloc[0]
            # If parent is not in selection, this is a root
            if pd.isna(parent_id) or int(parent_id) not in selected_center_ids:
                roots.append(center_id)
        
        return roots
    
    def _get_all_descendants(self, center_id: int, selected_center_ids: List[int]) -> List[int]:
        """
        Get all descendants of a center that are in the selection.
        
        NEW v5.2.1: Used to get actual values from children when parent has assignment.
        
        Args:
            center_id: Parent center ID
            selected_center_ids: List of centers in current selection
            
        Returns:
            List of descendant center IDs (excluding the center itself)
        """
        descendants = []
        children = self._children_map.get(center_id, [])
        
        for child_id in children:
            if child_id in selected_center_ids:
                descendants.append(child_id)
                # Recursive get grandchildren
                descendants.extend(self._get_all_descendants(child_id, selected_center_ids))
        
        return descendants
    
    def _get_center_name(self, center_id: int) -> str:
        """
        Get center name from hierarchy_df.
        
        NEW v5.2.1: For better debug output.
        """
        if self.hierarchy_df.empty:
            return str(center_id)
        
        row = self.hierarchy_df[self.hierarchy_df['kpi_center_id'] == center_id]
        if row.empty:
            return str(center_id)
        
        # Try different possible column names
        name = None
        for col in ['kpi_center_name', 'kpi_center', 'name']:
            if col in row.columns:
                name = row[col].iloc[0]
                if name:
                    break
        
        if name is None:
            name = str(center_id)
        
        return f"{name}({center_id})"
    
    # =========================================================================
    # PERIOD CONTEXT ANALYSIS - DEPRECATED v4.1.0
    # =========================================================================
    
    @staticmethod
    def analyze_period_context(start_date: date, end_date: date) -> Dict:
        """
        DEPRECATED v4.1.0: Use filters.analyze_period() instead.
        
        This method is kept for backward compatibility but will be removed
        in a future version. The analyze_period() function now includes
        all fields from this method plus additional multi-year analysis.
        
        Analyze the selected period relative to today.
        """
        import warnings
        warnings.warn(
            "analyze_period_context() is deprecated. Use filters.analyze_period() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        today = date.today()
        
        is_historical = end_date < today
        is_future = start_date > today
        is_current = not is_historical and not is_future
        
        days_until_end = (end_date - today).days
        
        if is_historical:
            period_status = 'historical'
            show_forecast = False
            forecast_message = "📅 Forecast not available for historical periods"
        elif is_future:
            period_status = 'future'
            show_forecast = True
            forecast_message = "📅 Future period - showing projected backlog only"
        else:
            period_status = 'current'
            show_forecast = True
            forecast_message = None
        
        return {
            'is_historical': is_historical,
            'is_current': is_current,
            'is_future': is_future,
            'today': today,
            'days_until_end': days_until_end,
            'period_status': period_status,
            'show_forecast': show_forecast,
            'forecast_message': forecast_message
        }
    
    # =========================================================================
    # OVERVIEW METRICS
    # =========================================================================
    
    def calculate_overview_metrics(
        self,
        period_type: str = 'YTD',
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> Dict:
        """
        Calculate overview KPI metrics.
        
        Returns dict with:
        - total_revenue, total_gp, total_gp1
        - total_customers, total_orders
        - gp_percent, gp1_percent
        - revenue_target, revenue_achievement (if targets available)
        - gp_target, gp_achievement (if targets available)
        """
        if self.sales_df.empty:
            return self._get_empty_overview()
        
        df = self.sales_df.copy()
        
        # Calculate totals
        total_revenue = df['sales_by_kpi_center_usd'].sum()
        total_gp = df['gross_profit_by_kpi_center_usd'].sum()
        total_gp1 = df['gp1_by_kpi_center_usd'].sum() if 'gp1_by_kpi_center_usd' in df.columns else 0
        total_customers = df['customer_id'].nunique()
        total_orders = df['oc_number'].nunique() if 'oc_number' in df.columns else 0
        
        # Calculate percentages
        gp_percent = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
        gp1_percent = (total_gp1 / total_revenue * 100) if total_revenue > 0 else 0
        
        metrics = {
            'total_revenue': total_revenue,
            'total_gp': total_gp,
            'total_gp1': total_gp1,
            'total_customers': total_customers,
            'total_orders': total_orders,
            'gp_percent': round(gp_percent, 2),
            'gp1_percent': round(gp1_percent, 2),
        }
        
        # Add target-based metrics if targets available
        if not self.targets_df.empty:
            proration = self._calculate_proration(period_type, year, start_date, end_date)
            
            # Revenue target and achievement
            revenue_targets = self._get_target_for_kpi('revenue')
            if revenue_targets > 0:
                prorated_revenue_target = revenue_targets * proration
                
                # Get actual from KPI centers with revenue target
                kpi_centers_with_revenue_target = self._get_kpi_centers_with_target('revenue')
                if kpi_centers_with_revenue_target:
                    actual_revenue = df[df['kpi_center_id'].isin(kpi_centers_with_revenue_target)]['sales_by_kpi_center_usd'].sum()
                else:
                    actual_revenue = total_revenue
                
                metrics['revenue_target'] = prorated_revenue_target
                metrics['revenue_achievement'] = (actual_revenue / prorated_revenue_target * 100) if prorated_revenue_target > 0 else 0
            
            # GP target and achievement
            gp_targets = self._get_target_for_kpi('gross_profit')
            if gp_targets > 0:
                prorated_gp_target = gp_targets * proration
                
                kpi_centers_with_gp_target = self._get_kpi_centers_with_target('gross_profit')
                if kpi_centers_with_gp_target:
                    actual_gp = df[df['kpi_center_id'].isin(kpi_centers_with_gp_target)]['gross_profit_by_kpi_center_usd'].sum()
                else:
                    actual_gp = total_gp
                
                metrics['gp_target'] = prorated_gp_target
                metrics['gp_achievement'] = (actual_gp / prorated_gp_target * 100) if prorated_gp_target > 0 else 0
            
            # GP1 target and achievement
            gp1_targets = self._get_target_for_kpi('gross_profit_1')
            if gp1_targets > 0:
                prorated_gp1_target = gp1_targets * proration
                
                kpi_centers_with_gp1_target = self._get_kpi_centers_with_target('gross_profit_1')
                if kpi_centers_with_gp1_target:
                    actual_gp1 = df[df['kpi_center_id'].isin(kpi_centers_with_gp1_target)]['gp1_by_kpi_center_usd'].sum()
                else:
                    actual_gp1 = total_gp1
                
                metrics['gp1_target'] = prorated_gp1_target
                metrics['gp1_achievement'] = (actual_gp1 / prorated_gp1_target * 100) if prorated_gp1_target > 0 else 0
        
        return metrics
    
    def _get_empty_overview(self) -> Dict:
        """Return empty overview metrics."""
        return {
            'total_revenue': 0,
            'total_gp': 0,
            'total_gp1': 0,
            'total_customers': 0,
            'total_orders': 0,
            'gp_percent': 0,
            'gp1_percent': 0,
        }
    
    def _get_target_for_kpi(self, kpi_name: str) -> float:
        """Get sum of targets for a specific KPI type."""
        if self.targets_df.empty:
            return 0
        
        mask = self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        return self.targets_df[mask]['annual_target_value_numeric'].sum()
    
    def _get_kpi_centers_with_target(self, kpi_name: str) -> List[int]:
        """Get list of KPI Center IDs that have a specific KPI target."""
        if self.targets_df.empty:
            return []
        
        mask = self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        return self.targets_df[mask]['kpi_center_id'].unique().tolist()
    
    def _calculate_proration(
        self,
        period_type: str,
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> float:
        """
        Calculate proration factor for targets.
        
        Returns:
            Float between 0 and 1 representing portion of year
        """
        today = date.today()
        year = year or today.year
        
        if period_type == 'YTD':
            if year == today.year:
                days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
                days_elapsed = (today - date(year, 1, 1)).days + 1
                return days_elapsed / days_in_year
            else:
                return 1.0
        
        elif period_type == 'QTD':
            current_quarter = (today.month - 1) // 3 + 1
            quarter_start = date(year, (current_quarter - 1) * 3 + 1, 1)
            days_in_quarter = (date(year, current_quarter * 3 + 1, 1) if current_quarter < 4 
                              else date(year + 1, 1, 1)) - quarter_start
            days_elapsed = (today - quarter_start).days + 1
            return (days_elapsed / days_in_quarter.days) * 0.25
        
        elif period_type == 'MTD':
            import calendar
            days_in_month = calendar.monthrange(year, today.month)[1]
            return today.day / days_in_month / 12
        
        elif period_type == 'LY':
            # Last Year - full year proration
            return 1.0
        
        elif period_type == 'Custom' and start_date and end_date:
            total_days = (end_date - start_date).days + 1
            days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
            return total_days / days_in_year
        
        return 1.0
    
    def _calculate_forecast_proration(
        self,
        period_type: str,
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> float:
        """
        Calculate proration factor for FORECAST targets (full period).
        
        NEW v4.0.1: Different from _calculate_proration which uses current date.
        This returns proration for the FULL period boundary.
        
        Used in Backlog & Forecast section where:
        - In-Period Backlog = orders with ETD in FULL period
        - Target = FULL period target (not prorated to filter date)
        
        Returns:
            Float representing portion of year for the full period:
            - YTD: 1.0 (100% = full year)
            - QTD: 0.25 (25% = full quarter)
            - MTD: 1/12 ≈ 0.0833 (full month)
            - LY: 1.0 (100% = full year)
            - Custom: actual days / 365
        """
        year = year or date.today().year
        
        if period_type == 'YTD':
            # Full year
            return 1.0
        
        elif period_type == 'QTD':
            # Full quarter = 25% of year
            return 0.25
        
        elif period_type == 'MTD':
            # Full month = 1/12 of year
            return 1.0 / 12
        
        elif period_type == 'LY':
            # Full previous year
            return 1.0
        
        elif period_type == 'Custom' and start_date and end_date:
            # Custom period: use actual days
            total_days = (end_date - start_date).days + 1
            days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
            return total_days / days_in_year
        
        return 1.0
    
    # =========================================================================
    # YOY METRICS
    # =========================================================================
    
    def calculate_yoy_metrics(
        self,
        current_sales_df: pd.DataFrame,
        previous_sales_df: pd.DataFrame
    ) -> Dict:
        """
        Calculate Year-over-Year comparison metrics.
        
        Returns dict with YoY growth percentages.
        """
        def safe_sum(df, col):
            if df.empty or col not in df.columns:
                return 0
            return df[col].sum()
        
        def calc_growth(current, previous):
            if previous == 0:
                return None if current == 0 else 100.0
            return ((current - previous) / previous) * 100
        
        current_revenue = safe_sum(current_sales_df, 'sales_by_kpi_center_usd')
        previous_revenue = safe_sum(previous_sales_df, 'sales_by_kpi_center_usd')
        
        current_gp = safe_sum(current_sales_df, 'gross_profit_by_kpi_center_usd')
        previous_gp = safe_sum(previous_sales_df, 'gross_profit_by_kpi_center_usd')
        
        current_gp1 = safe_sum(current_sales_df, 'gp1_by_kpi_center_usd')
        previous_gp1 = safe_sum(previous_sales_df, 'gp1_by_kpi_center_usd')
        
        current_customers = current_sales_df['customer_id'].nunique() if not current_sales_df.empty else 0
        previous_customers = previous_sales_df['customer_id'].nunique() if not previous_sales_df.empty else 0
        
        return {
            'total_revenue_yoy': calc_growth(current_revenue, previous_revenue),
            'total_gp_yoy': calc_growth(current_gp, previous_gp),
            'total_gp1_yoy': calc_growth(current_gp1, previous_gp1),
            'total_customers_yoy': calc_growth(current_customers, previous_customers),
            
            'current_revenue': current_revenue,
            'previous_revenue': previous_revenue,
            'current_gp': current_gp,
            'previous_gp': previous_gp,
            'current_gp1': current_gp1,
            'previous_gp1': previous_gp1,
            'current_customers': current_customers,
            'previous_customers': previous_customers,
        }
    
    # =========================================================================
    # OVERALL KPI ACHIEVEMENT - UPDATED v5.2.0
    # =========================================================================
    
    def calculate_overall_kpi_achievement(
        self,
        period_type: str = 'YTD',
        year: int = None,
        start_date: date = None,
        end_date: date = None,
        complex_kpis_by_center: Dict = None,
        selected_kpi_center_ids: List[int] = None
    ) -> Dict:
        """
        Calculate weighted average KPI achievement across all assigned KPIs.
        
        UPDATED v5.2.0: Correct recursive rollup logic with STOP condition.
        
        For EACH KPI type:
        - Start from root center
        - If child has assignment for this KPI → STOP, use that assignment
        - If child has NO assignment → Recursively rollup from its children
        
        Example (Gross Profit):
        - ALL (no GP) → check children [PTV, OVERSEA]
          - PTV (no GP) → check children [HAN, DAN, SGN] → all have GP → SUM them
          - OVERSEA (HAS GP!) → STOP, use OVERSEA's value directly
        - Result: HAN + DAN + SGN + OVERSEA (NOT including PTP, ROSEA, ROW)
        
        Formula: Σ(KPI_Achievement × Weight) / Σ(Weights)
        """
        # DEBUG v5.2.1: Start calculation logging
        print(f"\n{'='*70}")
        print(f"📊 OVERALL ACHIEVEMENT CALCULATION - DEBUG v5.2.1 (Recursive Rollup)")
        print(f"{'='*70}")
        print(f"   Period: {period_type} | Year: {year}")
        print(f"   Date Range: {start_date} → {end_date}")
        
        # Show center names for better readability
        selected_names = [self._get_center_name(c) for c in (selected_kpi_center_ids or [])]
        print(f"   Selected KPI Centers: {selected_names}")
        print(f"   Default Weights from DB: {self.default_weights}")
        
        if self.targets_df.empty:
            print(f"   ⚠️ No targets_df - returning None")
            return {'overall_achievement': None, 'kpi_count': 0}
        
        proration = self._calculate_proration(period_type, year, start_date, end_date)
        print(f"   Proration Factor: {proration:.4f} ({proration*100:.2f}%)")
        
        # KPI column mapping
        kpi_column_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gross_profit_1': 'gp1_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd',
        }
        
        # Find root centers (centers without parent in selection)
        root_centers = self._find_root_centers(selected_kpi_center_ids or [])
        root_names = [self._get_center_name(c) for c in root_centers]
        print(f"\n   🌳 ROOT CENTERS: {root_names}")
        
        # =========================================================
        # Determine Scenario: Check if ROOT center has direct assignment
        # FIXED v5.3.2: Check ROOT center, not all expanded centers
        # 
        # When user selects "OVERSEA + include sub-centers":
        # - selected_kpi_center_ids = [OVERSEA, PTP, ROSEA, ROW, SEA] (5 centers)
        # - BUT root_centers = [OVERSEA] (1 root)
        # - OVERSEA has assignment → use assigned weights
        # =========================================================
        is_single_root = len(root_centers) == 1
        
        has_direct_assignment = False
        if is_single_root:
            root_id = root_centers[0]
            direct_assignments = self.targets_df[
                self.targets_df['kpi_center_id'] == root_id
            ]
            has_direct_assignment = not direct_assignments.empty
        
        use_assigned_weights = is_single_root and has_direct_assignment
        calculation_method = 'assigned_weight' if use_assigned_weights else 'default_weight'
        
        print(f"\n   📋 SCENARIO DETECTION (v5.3.2 - Root-based):")
        print(f"      root_centers: {root_names}")
        print(f"      is_single_root: {is_single_root}")
        print(f"      has_direct_assignment: {has_direct_assignment}")
        print(f"      calculation_method: {calculation_method}")
        
        # =========================================================
        # Step 1: For EACH KPI type, find effective centers using recursive rollup
        # =========================================================
        kpi_aggregates = {}
        
        # Get all unique KPI names from targets
        all_kpi_names = self.targets_df['kpi_name'].unique()
        
        print(f"\n   📊 KPI BREAKDOWN BY TYPE (Recursive Rollup v5.2.1):")
        print(f"   {'─'*65}")
        
        for kpi_name in all_kpi_names:
            kpi_lower = kpi_name.lower() if kpi_name else ''
            
            # Find effective centers for THIS KPI using recursive rollup
            # These are centers whose ASSIGNMENT should be used for TARGET
            target_centers = []
            for root_id in root_centers:
                centers = self._get_effective_centers_for_kpi(
                    root_id, kpi_name, selected_kpi_center_ids or []
                )
                target_centers.extend(centers)
            
            # Remove duplicates while preserving order
            target_centers = list(dict.fromkeys(target_centers))
            
            if not target_centers:
                print(f"      ⚠️ {kpi_name}: Skipped (no effective centers)")
                continue
            
            # =========================================================
            # NEW v5.2.1: For ACTUAL, include target_center + all descendants
            # Because sales are recorded at child level, not parent level
            # =========================================================
            actual_centers = []
            for center_id in target_centers:
                actual_centers.append(center_id)
                # Add all descendants of this center
                descendants = self._get_all_descendants(center_id, selected_kpi_center_ids or [])
                actual_centers.extend(descendants)
            
            # Remove duplicates
            actual_centers = list(dict.fromkeys(actual_centers))
            
            # Get targets ONLY from target_centers (assignment level)
            kpi_targets = self.targets_df[
                (self.targets_df['kpi_name'] == kpi_name) &
                (self.targets_df['kpi_center_id'].isin(target_centers))
            ]
            total_annual_target = kpi_targets['annual_target_value_numeric'].sum()
            
            if total_annual_target <= 0:
                print(f"      ⚠️ {kpi_name}: Skipped (target=0)")
                continue
            
            # Prorated target
            total_prorated_target = total_annual_target * proration
            
            # Sum actuals from actual_centers (includes descendants for parent assignments)
            total_actual = 0
            actual_source = ""
            if kpi_lower in kpi_column_map:
                col = kpi_column_map[kpi_lower]
                if not self.sales_df.empty and col in self.sales_df.columns:
                    filtered_sales = self.sales_df[
                        self.sales_df['kpi_center_id'].isin(actual_centers)
                    ]
                    total_actual = filtered_sales[col].sum() if not filtered_sales.empty else 0
                    actual_source = f"sales_df[{col}]"
            elif kpi_lower in ['new_business_revenue', 'num_new_customers', 'num_new_products', 'num_new_combos']:
                actual_source = "complex_kpis_by_center"
                if complex_kpis_by_center:
                    for center_id in actual_centers:
                        if center_id in complex_kpis_by_center:
                            total_actual += complex_kpis_by_center[center_id].get(kpi_lower, 0)
            
            # Achievement
            achievement = (total_actual / total_prorated_target * 100) if total_prorated_target > 0 else 0
            
            # Get weight based on scenario
            # FIXED v5.3.2: Get weight from ROOT center's assignment, not from kpi_targets
            if use_assigned_weights:
                # Get weight from ROOT center's assignment for this KPI
                root_id = root_centers[0]
                root_kpi_assignment = self.targets_df[
                    (self.targets_df['kpi_center_id'] == root_id) &
                    (self.targets_df['kpi_name'].str.lower() == kpi_lower)
                ]
                if not root_kpi_assignment.empty and 'weight_numeric' in root_kpi_assignment.columns:
                    assigned_weight = root_kpi_assignment['weight_numeric'].iloc[0]
                else:
                    assigned_weight = None
                
                if assigned_weight is None or pd.isna(assigned_weight):
                    assigned_weight = self.default_weights.get(kpi_lower, 50)
                weight = assigned_weight
                weight_source = 'assigned'
            else:
                weight = self.default_weights.get(kpi_lower, 50)
                weight_source = 'default'
            
            # DEBUG v5.2.1: Print each KPI detail with center NAMES
            target_names = [self._get_center_name(c) for c in target_centers]
            actual_names = [self._get_center_name(c) for c in actual_centers]
            
            print(f"      📌 {kpi_name}:")
            print(f"         Target from: {target_names}")
            print(f"         Actual from: {actual_names}")
            print(f"         Annual Target: ${total_annual_target:,.0f}")
            print(f"         Prorated Target: ${total_prorated_target:,.0f}")
            if 'usd' in kpi_lower or kpi_lower in ['revenue', 'gross_profit', 'gross_profit_1', 'gp1', 'new_business_revenue']:
                print(f"         Actual ({actual_source}): ${total_actual:,.0f}")
            else:
                print(f"         Actual ({actual_source}): {total_actual:,.0f}")
            print(f"         Achievement: {achievement:.2f}%")
            print(f"         Weight: {weight} ({weight_source})")
            
            kpi_aggregates[kpi_name] = {
                'kpi_name': kpi_name,
                'kpi_lower': kpi_lower,
                'annual_target': total_annual_target,
                'prorated_target': total_prorated_target,
                'actual': total_actual,
                'achievement': achievement,
                'weight': weight,
                'weight_source': weight_source,
                'target_centers': target_centers,
                'actual_centers': actual_centers
            }
        
        if not kpi_aggregates:
            print(f"   ⚠️ No valid KPI aggregates - returning None")
            return {'overall_achievement': None, 'kpi_count': 0}
        
        # =========================================================
        # Step 2: Calculate weighted achievement
        # Sort by weight (highest first) for better display
        # =========================================================
        total_weighted_achievement = 0
        total_weight = 0
        kpi_details = []
        
        print(f"\n   🧮 WEIGHTED CALCULATION (sorted by weight):")
        print(f"   {'─'*65}")
        
        # Sort by weight descending
        sorted_kpis = sorted(kpi_aggregates.items(), key=lambda x: -x[1]['weight'])
        
        for kpi_name, data in sorted_kpis:
            weight = data['weight']
            weighted_contrib = data['achievement'] * weight
            total_weighted_achievement += weighted_contrib
            total_weight += weight
            
            print(f"      {kpi_name}: {data['achievement']:.2f}% × {weight} = {weighted_contrib:.2f}")
            
            kpi_details.append({
                'kpi_name': kpi_name,
                'achievement': data['achievement'],
                'weight': weight,
                'weight_source': data['weight_source'],
                'actual': data['actual'],
                'prorated_target': data['prorated_target'],
                'target_centers': data['target_centers'],
                'actual_centers': data['actual_centers']
            })
        
        # =========================================================
        # Step 3: Calculate overall
        # =========================================================
        if total_weight > 0:
            overall = total_weighted_achievement / total_weight
            
            print(f"   {'─'*65}")
            print(f"   📊 FINAL CALCULATION:")
            print(f"      Total Weighted Achievement: {total_weighted_achievement:.2f}")
            print(f"      Total Weight: {total_weight}")
            print(f"      Overall = {total_weighted_achievement:.2f} / {total_weight} = {overall:.2f}%")
            print(f"{'='*70}\n")
            
            return {
                'overall_achievement': round(overall, 1),
                'kpi_count': len(kpi_aggregates),
                'total_weight': total_weight,
                'kpi_details': kpi_details,
                'calculation_method': calculation_method,
                'is_single_root': is_single_root,  # FIXED v5.3.2
                'has_direct_assignment': has_direct_assignment,
                'default_weights_used': self.default_weights,
                'root_centers': root_centers  # NEW v5.3.2
            }
        
        print(f"   ⚠️ Total weight = 0 - returning None")
        return {'overall_achievement': None, 'kpi_count': 0}
    
    # NOTE: _get_individual_kpi_center_actual() REMOVED in v4.0.0 - never called
    
    # =========================================================================
    # PRORATED TARGET HELPER - NEW v3.1.0 (synced with Salesperson)
    # =========================================================================
    
    def _get_prorated_target(
        self,
        kpi_name: str,
        period_type: str,
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> Optional[float]:
        """
        Get prorated target for a specific KPI based on period type.
        
        NEW v3.1.0: Helper for KPI Progress tab (synced with Salesperson).
        
        Args:
            kpi_name: KPI name (e.g., 'revenue', 'gross_profit')
            period_type: 'YTD', 'QTD', 'MTD', or 'Custom'
            year: Target year
            start_date: Start date for Custom period
            end_date: End date for Custom period
            
        Returns:
            Prorated target value or None if no target exists
        """
        if self.targets_df.empty:
            return None
        
        # Get annual target for this KPI
        mask = self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        kpi_targets = self.targets_df[mask]
        
        if kpi_targets.empty:
            return None
        
        annual_target = kpi_targets['annual_target_value_numeric'].sum()
        
        if annual_target <= 0:
            return None
        
        # Calculate proration factor
        proration = self._calculate_proration(period_type, year, start_date, end_date)
        
        return annual_target * proration
    
    def get_kpi_progress_data(
        self,
        period_type: str,
        year: int,
        start_date: date = None,
        end_date: date = None,
        complex_kpis: Dict = None
    ) -> List[Dict]:
        """
        Get KPI progress data for all assigned KPIs.
        
        NEW v3.1.0: Used by KPI Progress tab (synced with Salesperson).
        
        Args:
            period_type: Period type for proration
            year: Target year
            start_date: Start date
            end_date: End date
            complex_kpis: Pre-calculated complex KPIs dict
            
        Returns:
            List of dicts with KPI progress data for each KPI type
        """
        if self.targets_df.empty:
            return []
        
        # Map KPI names to column names in sales_df
        kpi_column_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gross_profit_1': 'gp1_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd',
        }
        
        # Complex KPIs that need special handling
        complex_kpi_names = ['num_new_customers', 'num_new_products', 'new_business_revenue']
        
        # Display name mapping
        kpi_display_names = {
            'revenue': 'Revenue',
            'gross_profit': 'Gross Profit',
            'gross_profit_1': 'GP1',
            'gp1': 'GP1',
            'num_new_customers': 'New Customers',
            'num_new_products': 'New Products',
            'new_business_revenue': 'New Business Revenue',
        }
        
        # KPIs that should show currency format
        currency_kpis = ['revenue', 'gross_profit', 'gross_profit_1', 'gp1', 'new_business_revenue']
        
        kpi_progress = []
        
        for kpi_name in self.targets_df['kpi_name'].str.lower().unique():
            # Get KPI Centers who have this specific KPI target
            kpi_centers_with_target = self.targets_df[
                self.targets_df['kpi_name'].str.lower() == kpi_name
            ]['kpi_center_id'].unique().tolist()
            
            # Get total annual target
            kpi_target = self.targets_df[
                self.targets_df['kpi_name'].str.lower() == kpi_name
            ]['annual_target_value_numeric'].sum()
            
            if kpi_target <= 0:
                continue
            
            # Calculate actual value - ONLY from KPI Centers who have this KPI target
            actual = 0
            if kpi_name in kpi_column_map:
                col_name = kpi_column_map[kpi_name]
                if not self.sales_df.empty and col_name in self.sales_df.columns:
                    filtered_sales = self.sales_df[
                        self.sales_df['kpi_center_id'].isin(kpi_centers_with_target)
                    ]
                    actual = filtered_sales[col_name].sum() if not filtered_sales.empty else 0
            elif kpi_name in complex_kpi_names and complex_kpis:
                # Use pre-calculated complex KPIs
                if kpi_name == 'num_new_customers':
                    actual = complex_kpis.get('num_new_customers', 0)
                elif kpi_name == 'num_new_products':
                    actual = complex_kpis.get('num_new_products', 0)
                elif kpi_name == 'new_business_revenue':
                    actual = complex_kpis.get('new_business_revenue', 0)
            
            # Get display name
            display_name = kpi_display_names.get(kpi_name, kpi_name.replace('_', ' ').title())
            
            # Get prorated target
            prorated_target = self._get_prorated_target(
                kpi_name, period_type, year, start_date, end_date
            )
            if prorated_target is None or prorated_target <= 0:
                prorated_target = kpi_target  # Fallback to annual
            
            # Calculate achievement
            achievement = (actual / prorated_target * 100) if prorated_target > 0 else 0
            
            kpi_progress.append({
                'kpi_name': kpi_name,
                'display_name': display_name,
                'actual': actual,
                'annual_target': kpi_target,
                'prorated_target': prorated_target,
                'achievement': achievement,
                'is_currency': kpi_name in currency_kpis,
                'kpi_center_count': len(kpi_centers_with_target)
            })
        
        # Sort by display name for consistent ordering
        kpi_progress.sort(key=lambda x: x['display_name'])
        
        return kpi_progress
    
    # =========================================================================
    # HIERARCHY ROLLUP TARGETS - NEW v3.2.0
    # =========================================================================
    
    def calculate_rollup_targets(
        self,
        hierarchy_df: pd.DataFrame,
        queries_instance = None
    ) -> Dict[int, Dict]:
        """
        Calculate rolled-up targets for all KPI Centers.
        
        UPDATED v5.3.1: Fixed per-KPI STOP logic (synced with Overview tab).
        
        Logic (PER KPI TYPE):
        - Start from each center
        - For each KPI type, traverse down the tree:
          - If child HAS assignment for this KPI → STOP, use that assignment
          - If child has NO assignment → Continue recursively to its children
        
        Example with Revenue KPI for ALL:
        - ALL (no Revenue assignment) → continue to children
          - PTV (no Revenue assignment) → continue to children
            - HAN (has Revenue $X) → STOP, use $X
            - DAN (has Revenue $Y) → STOP, use $Y
            - SGN (has Revenue $Z) → STOP, use $Z
          - OVERSEA (has Revenue $4.4M) → STOP, use $4.4M
            - (children NOT considered because OVERSEA already STOP)
        
        Result: ALL Revenue = HAN + DAN + SGN + OVERSEA (NOT all 7 centers)
        
        Args:
            hierarchy_df: DataFrame with kpi_center_id, level, is_leaf
            queries_instance: KPICenterQueries instance (optional)
            
        Returns:
            Dict[kpi_center_id] = {
                'targets': List[{kpi_name, annual, monthly, quarterly, unit, weight}],
                'source': 'Direct' | 'Rollup',
                'children_count': int,
                'children_names': List[str]
            }
        """
        if self.targets_df.empty or hierarchy_df.empty:
            return {}
        
        result = {}
        
        # KPI display names
        kpi_display_names = {
            'revenue': 'Revenue',
            'gross_profit': 'Gross Profit',
            'gross_profit_1': 'GP1',
            'gp1': 'GP1',
            'num_new_customers': 'Num New Customers',
            'num_new_products': 'Num New Products',
            'new_business_revenue': 'New Business Revenue',
        }
        
        # Icons for display
        kpi_icons = {
            'revenue': '💰',
            'gross_profit': '📈',
            'gross_profit_1': '📊',
            'gp1': '📊',
            'num_new_customers': '👥',
            'num_new_products': '📦',
            'new_business_revenue': '💼',
        }
        
        # =====================================================================
        # Build local children_map from hierarchy_df
        # =====================================================================
        children_map = {}
        all_center_ids = set(hierarchy_df['kpi_center_id'].tolist())
        
        for _, row in hierarchy_df.iterrows():
            center_id = row['kpi_center_id']
            parent_id = row.get('parent_center_id')
            
            if pd.notna(parent_id):
                parent_id = int(parent_id)
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(center_id)
        
        # =====================================================================
        # Helper: Get effective centers for a specific KPI (recursive with STOP)
        # =====================================================================
        def get_effective_centers_for_kpi(center_id: int, kpi_name: str) -> List[int]:
            """
            Recursive function to find centers whose assignments should be used.
            
            STOP Logic:
            - If center has assignment for this KPI → STOP, return [center_id]
            - If no assignment → recurse to children
            """
            # Only consider centers in current hierarchy
            if center_id not in all_center_ids:
                return []
            
            # Check if this center has assignment for this KPI
            center_assignment = self.targets_df[
                (self.targets_df['kpi_center_id'] == center_id) &
                (self.targets_df['kpi_name'].str.lower() == kpi_name.lower())
            ]
            
            if not center_assignment.empty:
                # STOP: this center has assignment for this KPI
                return [center_id]
            
            # No assignment for this KPI, recurse to children
            children = children_map.get(center_id, [])
            effective_centers = []
            
            for child_id in children:
                child_effective = get_effective_centers_for_kpi(child_id, kpi_name)
                effective_centers.extend(child_effective)
            
            return effective_centers
        
        # =====================================================================
        # Get all unique KPI types from targets
        # =====================================================================
        all_kpi_types = self.targets_df['kpi_name'].unique().tolist()
        
        # =====================================================================
        # Process each KPI Center
        # =====================================================================
        for _, row in hierarchy_df.iterrows():
            kpi_center_id = row['kpi_center_id']
            kpi_center_name = row['kpi_center_name']
            is_leaf = row.get('is_leaf', 1) == 1
            
            # Check if center has any direct assignment
            direct_targets = self.targets_df[
                self.targets_df['kpi_center_id'] == kpi_center_id
            ]
            has_direct = not direct_targets.empty
            
            # Build targets for this center (per KPI type with STOP logic)
            merged_targets = []
            contributing_centers_all = set()  # Track all centers that contribute
            
            for kpi_name in all_kpi_types:
                kpi_lower = kpi_name.lower() if kpi_name else ''
                
                # Get effective centers for this KPI using STOP logic
                effective_center_ids = get_effective_centers_for_kpi(kpi_center_id, kpi_name)
                
                if not effective_center_ids:
                    continue  # No targets for this KPI under this center
                
                contributing_centers_all.update(effective_center_ids)
                
                # Get targets from effective centers
                kpi_targets = self.targets_df[
                    (self.targets_df['kpi_center_id'].isin(effective_center_ids)) &
                    (self.targets_df['kpi_name'].str.lower() == kpi_lower)
                ]
                
                if kpi_targets.empty:
                    continue
                
                # Sum numeric values
                annual = kpi_targets['annual_target_value_numeric'].sum() if 'annual_target_value_numeric' in kpi_targets.columns else 0
                
                if annual <= 0:
                    continue
                
                # Monthly and quarterly
                monthly = 0
                quarterly = 0
                if 'monthly_target_value' in kpi_targets.columns:
                    try:
                        monthly = pd.to_numeric(kpi_targets['monthly_target_value'], errors='coerce').sum()
                    except:
                        monthly = annual / 12
                if 'quarterly_target_value' in kpi_targets.columns:
                    try:
                        quarterly = pd.to_numeric(kpi_targets['quarterly_target_value'], errors='coerce').sum()
                    except:
                        quarterly = annual / 4
                
                # Get unit (should be same for all)
                unit = kpi_targets['unit_of_measure'].iloc[0] if 'unit_of_measure' in kpi_targets.columns else ''
                
                # Weight: only if this center has direct assignment for this KPI
                weight = None
                if has_direct:
                    direct_kpi = direct_targets[direct_targets['kpi_name'].str.lower() == kpi_lower]
                    if not direct_kpi.empty and 'weight_numeric' in direct_kpi.columns:
                        weight = direct_kpi['weight_numeric'].iloc[0]
                
                # Get display name and icon
                display_name = kpi_display_names.get(kpi_lower, kpi_name.replace('_', ' ').title() if kpi_name else '')
                icon = kpi_icons.get(kpi_lower, '📋')
                
                merged_targets.append({
                    'kpi_name': kpi_name,
                    'display_name': f"{icon} {display_name}",
                    'annual_target': annual,
                    'monthly_target': monthly if not pd.isna(monthly) else annual / 12,
                    'quarterly_target': quarterly if not pd.isna(quarterly) else annual / 4,
                    'unit': unit,
                    'weight': weight,
                    'is_currency': kpi_lower in ['revenue', 'gross_profit', 'gross_profit_1', 'gp1', 'new_business_revenue'],
                    'effective_centers': len(effective_center_ids)  # How many centers contribute to this KPI
                })
            
            if not merged_targets:
                continue  # Skip centers with no targets
            
            # Sort by display name
            merged_targets.sort(key=lambda x: x['display_name'])
            
            # Determine source
            # Direct: if ALL KPIs come only from this center's direct assignment
            # Rollup: if ANY KPI comes from children (not just self)
            is_pure_direct = has_direct and contributing_centers_all == {kpi_center_id}
            source = 'Direct' if is_pure_direct else 'Rollup'
            
            # Get names of contributing centers (excluding self)
            children_names = []
            other_centers = contributing_centers_all - {kpi_center_id}
            if other_centers:
                children_with_names = hierarchy_df[
                    hierarchy_df['kpi_center_id'].isin(other_centers)
                ]['kpi_center_name'].unique().tolist()
                children_names = children_with_names
            
            # Build result
            result[kpi_center_id] = {
                'kpi_center_id': kpi_center_id,
                'kpi_center_name': kpi_center_name,
                'targets': merged_targets,
                'source': source,
                'level': row.get('level', 0),
                'is_leaf': is_leaf,
                'children_count': len(children_names),
                'children_names': children_names
            }
        
        return result
    
    # =========================================================================
    # PER-CENTER PROGRESS - NEW v3.2.0
    # =========================================================================
    
    def calculate_per_center_progress(
        self,
        hierarchy_df: pd.DataFrame,
        queries_instance,
        period_type: str,
        year: int,
        start_date: date = None,
        end_date: date = None,
        complex_kpis_by_center: Dict = None
    ) -> Dict[int, Dict]:
        """
        Calculate KPI progress for each KPI Center.
        
        NEW v3.2.0: Used by Progress tab for per-center breakdown.
        
        Logic:
        - Leaf nodes: Calculate achievement from direct actuals vs targets
        - Parent nodes: Weighted average of children's overall achievements
        
        Args:
            hierarchy_df: DataFrame with kpi_center_id, level, is_leaf
            queries_instance: KPICenterQueries for hierarchy lookups
            period_type: For target proration
            year: Target year
            start_date, end_date: For Custom period
            complex_kpis_by_center: Dict[kpi_center_id] = {kpi_name: actual}
            
        Returns:
            Dict[kpi_center_id] = {
                'kpi_center_id', 'kpi_center_name', 'level', 'is_leaf',
                'kpis': List[{kpi_name, actual, target, achievement, weight}],
                'overall': float (weighted average),
                'total_weight': float,
                'source': 'Direct' | 'Rollup'
            }
        """
        if hierarchy_df.empty:
            return {}
        
        # Calculate proration factor
        proration = self._calculate_proration(period_type, year, start_date, end_date)
        
        # KPI column mapping
        kpi_column_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gross_profit_1': 'gp1_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd',
        }
        
        # Display names
        kpi_display_names = {
            'revenue': 'Revenue',
            'gross_profit': 'Gross Profit',
            'gross_profit_1': 'GP1',
            'gp1': 'GP1',
            'num_new_customers': 'New Customers',
            'num_new_products': 'New Products',
            'num_new_projects': 'New Projects',
            'num_new_combos': 'New Combos',
            'new_business_revenue': 'New Business Revenue',
            'purchase_value': 'Purchase Value',
        }
        
        # Icons
        kpi_icons = {
            'revenue': '💰',
            'gross_profit': '📈',
            'gross_profit_1': '📊',
            'gp1': '📊',
            'num_new_customers': '👥',
            'num_new_products': '📦',
            'num_new_projects': '🎯',
            'num_new_combos': '🔗',
            'new_business_revenue': '💼',
            'purchase_value': '🛒',
        }
        
        # Currency KPIs
        currency_kpis = ['revenue', 'gross_profit', 'gross_profit_1', 'gp1', 'new_business_revenue', 'purchase_value']
        
        result = {}
        
        # First pass: Calculate for all leaf nodes
        for _, row in hierarchy_df.iterrows():
            kpi_center_id = row['kpi_center_id']
            kpi_center_name = row['kpi_center_name']
            is_leaf = row.get('is_leaf', 1) == 1
            level = row.get('level', 0)
            
            if not is_leaf:
                continue  # Process parents in second pass
            
            # Get targets for this center
            center_targets = self.targets_df[
                self.targets_df['kpi_center_id'] == kpi_center_id
            ]
            
            if center_targets.empty:
                continue  # Skip centers without KPI assignment
            
            # Get actuals for this center
            center_sales = self.sales_df[
                self.sales_df['kpi_center_id'] == kpi_center_id
            ] if not self.sales_df.empty else pd.DataFrame()
            
            # Calculate per-KPI progress
            kpis = []
            total_weighted_achievement = 0
            total_weight = 0
            
            for _, target in center_targets.iterrows():
                kpi_name = target['kpi_name']
                kpi_lower = kpi_name.lower() if kpi_name else ''
                annual_target = target.get('annual_target_value_numeric', 0) or 0
                weight = target.get('weight_numeric', 100) or 100
                
                if annual_target <= 0:
                    continue
                
                # Calculate prorated target
                prorated_target = annual_target * proration
                
                # Get actual value
                actual = 0
                if kpi_lower in kpi_column_map:
                    col = kpi_column_map[kpi_lower]
                    if not center_sales.empty and col in center_sales.columns:
                        actual = center_sales[col].sum()
                elif complex_kpis_by_center and kpi_center_id in complex_kpis_by_center:
                    actual = complex_kpis_by_center[kpi_center_id].get(kpi_lower, 0)
                
                # Calculate achievement
                achievement = (actual / prorated_target * 100) if prorated_target > 0 else 0
                
                # Display name and icon
                display_name = kpi_display_names.get(kpi_lower, kpi_name.replace('_', ' ').title() if kpi_name else '')
                icon = kpi_icons.get(kpi_lower, '📋')
                
                kpis.append({
                    'kpi_name': kpi_name,
                    'display_name': f"{icon} {display_name}",
                    'actual': actual,
                    'prorated_target': prorated_target,
                    'annual_target': annual_target,
                    'achievement': achievement,
                    'weight': weight,
                    'weight_source': 'assigned',  # v5.0.0: Leaf nodes use assigned weight
                    'is_currency': kpi_lower in currency_kpis
                })
                
                total_weighted_achievement += achievement * weight
                total_weight += weight
            
            if not kpis:
                continue
            
            # Calculate overall
            overall = total_weighted_achievement / total_weight if total_weight > 0 else None
            
            # Sort KPIs by weight (highest first) for better display
            kpis.sort(key=lambda x: -x['weight'])
            
            result[kpi_center_id] = {
                'kpi_center_id': kpi_center_id,
                'kpi_center_name': kpi_center_name,
                'level': level,
                'is_leaf': True,
                'kpis': kpis,
                'overall': overall,
                'total_weight': total_weight,
                'source': 'Direct',
                'calculation_method': 'assigned_weight'  # v5.0.0: Leaf nodes use assigned weight
            }
        
        # =====================================================================
        # Second pass: Calculate for parent nodes
        # UPDATED v5.0.0: Use default_weight from kpi_types for rollup
        # Synced with kpi_parent_rollup_logic.md
        # 
        # Logic:
        # 1. Aggregate targets & actuals by KPI type from all descendants
        # 2. Calculate achievement per KPI
        # 3. Use default_weight from kpi_types (NOT target-proportion)
        # 4. Calculate weighted overall
        # =====================================================================
        max_level = hierarchy_df['level'].max() if 'level' in hierarchy_df.columns else 0
        
        for current_level in range(max_level - 1, -1, -1):
            level_centers = hierarchy_df[hierarchy_df['level'] == current_level]
            
            for _, row in level_centers.iterrows():
                kpi_center_id = row['kpi_center_id']
                kpi_center_name = row['kpi_center_name']
                is_leaf = row.get('is_leaf', 1) == 1
                
                if is_leaf:
                    continue  # Already processed
                
                if kpi_center_id in result:
                    continue  # Already processed
                
                # =============================================================
                # Check if this parent has direct assignment (Scenario A)
                # =============================================================
                parent_assignments = self.targets_df[
                    self.targets_df['kpi_center_id'] == kpi_center_id
                ]
                has_direct_assignment = not parent_assignments.empty
                
                if has_direct_assignment:
                    # =============================================================
                    # Scenario A: Parent has direct assignment → use assigned weight
                    # UPDATED v5.2.1: Actual from parent + ALL descendants
                    # (because sales are recorded at child level)
                    # =============================================================
                    
                    # Get ALL descendants (children, grandchildren, etc.)
                    all_descendants = queries_instance.get_leaf_descendants(kpi_center_id)
                    actual_centers = [kpi_center_id] + (all_descendants if all_descendants else [])
                    
                    # Get sales from parent + all descendants
                    parent_sales = self.sales_df[
                        self.sales_df['kpi_center_id'].isin(actual_centers)
                    ] if not self.sales_df.empty else pd.DataFrame()
                    
                    kpis = []
                    total_weighted_achievement = 0
                    total_weight = 0
                    
                    for _, target in parent_assignments.iterrows():
                        kpi_name = target['kpi_name']
                        kpi_lower = kpi_name.lower() if kpi_name else ''
                        annual_target = target.get('annual_target_value_numeric', 0) or 0
                        weight = target.get('weight_numeric', None)
                        
                        # If weight is NULL, use default_weight
                        if weight is None or pd.isna(weight):
                            weight = self.default_weights.get(kpi_lower, 50)
                        
                        if annual_target <= 0:
                            continue
                        
                        prorated_target = annual_target * proration
                        
                        # Get actual value from parent + all descendants
                        actual = 0
                        if kpi_lower in kpi_column_map:
                            col = kpi_column_map[kpi_lower]
                            if not parent_sales.empty and col in parent_sales.columns:
                                actual = parent_sales[col].sum()
                        elif complex_kpis_by_center:
                            # Sum from all actual_centers
                            for cid in actual_centers:
                                if cid in complex_kpis_by_center:
                                    actual += complex_kpis_by_center[cid].get(kpi_lower, 0)
                        
                        achievement = (actual / prorated_target * 100) if prorated_target > 0 else 0
                        
                        display_name = kpi_display_names.get(kpi_lower, kpi_name.replace('_', ' ').title() if kpi_name else '')
                        icon = kpi_icons.get(kpi_lower, '📋')
                        
                        kpis.append({
                            'kpi_name': kpi_name,
                            'display_name': f"{icon} {display_name}",
                            'actual': actual,
                            'prorated_target': prorated_target,
                            'annual_target': annual_target,
                            'achievement': achievement,
                            'weight': weight,
                            'weight_source': 'assigned',
                            'is_currency': kpi_lower in currency_kpis,
                            'contributing_centers': len(actual_centers)  # NEW v5.2.1
                        })
                        
                        total_weighted_achievement += achievement * weight
                        total_weight += weight
                    
                    if kpis:
                        overall = total_weighted_achievement / total_weight if total_weight > 0 else None
                        # Sort KPIs by weight (highest first) for better display
                        kpis.sort(key=lambda x: -x['weight'])
                        
                        result[kpi_center_id] = {
                            'kpi_center_id': kpi_center_id,
                            'kpi_center_name': kpi_center_name,
                            'level': current_level,
                            'is_leaf': False,
                            'kpis': kpis,
                            'overall': overall,
                            'total_weight': total_weight,
                            'source': 'Direct',  # Parent with direct assignment
                            'calculation_method': 'assigned_weight',
                            'children_count': len(all_descendants) if all_descendants else 0  # NEW v5.2.1
                        }
                        continue
                
                # =============================================================
                # Scenario B: Parent has NO assignment → Rollup from children
                # Use default_weight from kpi_types
                # =============================================================
                
                # Get leaf descendants
                leaf_descendants = queries_instance.get_leaf_descendants(kpi_center_id)
                
                if not leaf_descendants:
                    continue
                
                # =========================================================
                # Step 1: Aggregate targets by KPI type from all descendants
                # =========================================================
                descendants_targets = self.targets_df[
                    self.targets_df['kpi_center_id'].isin(leaf_descendants)
                ]
                
                if descendants_targets.empty:
                    continue
                
                # Get descendants' sales data
                descendants_sales = self.sales_df[
                    self.sales_df['kpi_center_id'].isin(leaf_descendants)
                ] if not self.sales_df.empty else pd.DataFrame()
                
                # =========================================================
                # Step 2: Calculate per-KPI aggregated metrics
                # =========================================================
                kpi_aggregates = {}
                
                for kpi_name in descendants_targets['kpi_name'].unique():
                    kpi_lower = kpi_name.lower() if kpi_name else ''
                    
                    # Get targets for this KPI and which descendants have it
                    kpi_targets = descendants_targets[
                        descendants_targets['kpi_name'] == kpi_name
                    ]
                    total_annual_target = kpi_targets['annual_target_value_numeric'].sum()
                    
                    if total_annual_target <= 0:
                        continue
                    
                    # Get list of descendants that have THIS KPI target
                    descendants_with_this_kpi = kpi_targets['kpi_center_id'].unique().tolist()
                    
                    # Prorated target
                    total_prorated_target = total_annual_target * proration
                    
                    # Sum actuals ONLY from descendants that have this KPI target
                    total_actual = 0
                    if kpi_lower in kpi_column_map:
                        col = kpi_column_map[kpi_lower]
                        if not descendants_sales.empty and col in descendants_sales.columns:
                            filtered_sales = descendants_sales[
                                descendants_sales['kpi_center_id'].isin(descendants_with_this_kpi)
                            ]
                            total_actual = filtered_sales[col].sum() if not filtered_sales.empty else 0
                    elif kpi_lower in ['new_business_revenue', 'num_new_customers', 'num_new_products', 'num_new_combos']:
                        if complex_kpis_by_center:
                            for child_id in descendants_with_this_kpi:
                                if child_id in complex_kpis_by_center:
                                    total_actual += complex_kpis_by_center[child_id].get(kpi_lower, 0)
                    
                    # Achievement
                    achievement = (total_actual / total_prorated_target * 100) if total_prorated_target > 0 else 0
                    
                    kpi_aggregates[kpi_name] = {
                        'kpi_name': kpi_name,
                        'kpi_lower': kpi_lower,
                        'annual_target': total_annual_target,
                        'prorated_target': total_prorated_target,
                        'actual': total_actual,
                        'achievement': achievement,
                        'is_currency': kpi_lower in currency_kpis,
                        'contributing_centers': len(descendants_with_this_kpi)
                    }
                
                if not kpi_aggregates:
                    continue
                
                # =========================================================
                # Step 3: Use default_weight from kpi_types
                # =========================================================
                kpis = []
                total_weighted_achievement = 0
                total_weight = 0
                
                for kpi_name, data in kpi_aggregates.items():
                    # Get default_weight from kpi_types
                    default_weight = self.default_weights.get(data['kpi_lower'], 50)
                    
                    display_name = kpi_display_names.get(data['kpi_lower'], kpi_name.replace('_', ' ').title())
                    icon = kpi_icons.get(data['kpi_lower'], '📋')
                    
                    kpis.append({
                        'kpi_name': kpi_name,
                        'display_name': f"{icon} {display_name}",
                        'actual': data['actual'],
                        'prorated_target': data['prorated_target'],
                        'annual_target': data['annual_target'],
                        'achievement': data['achievement'],
                        'weight': default_weight,
                        'weight_source': 'default',
                        'is_currency': data['is_currency'],
                        'contributing_centers': data.get('contributing_centers', 0)
                    })
                    
                    total_weighted_achievement += data['achievement'] * default_weight
                    total_weight += default_weight
                
                # Calculate overall
                overall = total_weighted_achievement / total_weight if total_weight > 0 else None
                
                # Sort KPIs by weight (highest first) for better display
                kpis.sort(key=lambda x: -x['weight'])
                
                # Collect children summary for display
                children_summary = []
                for child_id in leaf_descendants:
                    if child_id in result:
                        child_data = result[child_id]
                        children_summary.append({
                            'name': child_data['kpi_center_name'],
                            'achievement': child_data.get('overall'),
                            'weight': child_data.get('total_weight', 100)
                        })
                
                result[kpi_center_id] = {
                    'kpi_center_id': kpi_center_id,
                    'kpi_center_name': kpi_center_name,
                    'level': current_level,
                    'is_leaf': False,
                    'kpis': kpis,
                    'overall': overall,
                    'total_weight': total_weight,
                    'source': 'Rollup',
                    'children_count': len(leaf_descendants),
                    'children_summary': children_summary,
                    'calculation_method': 'default_weight'
                }
        
        return result
    
    # =========================================================================
    # BACKLOG METRICS
    # =========================================================================
    
    def calculate_backlog_metrics(
        self,
        total_backlog_df: pd.DataFrame,
        in_period_backlog_df: pd.DataFrame,
        period_type: str = 'YTD',
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> Dict:
        """
        Calculate backlog and forecast metrics.
        
        GP1 backlog is estimated using GP1/GP ratio from invoiced data.
        """
        metrics = {
            'total_backlog_revenue': 0,
            'total_backlog_gp': 0,
            'total_backlog_gp1': 0,
            'backlog_orders': 0,
            'in_period_backlog_revenue': 0,
            'in_period_backlog_gp': 0,
            'in_period_backlog_gp1': 0,
            'in_period_orders': 0,
            'gp1_gp_ratio': 1.0,
        }
        
        # Calculate GP1/GP ratio from invoiced data
        if not self.sales_df.empty:
            total_gp = self.sales_df['gross_profit_by_kpi_center_usd'].sum()
            total_gp1 = self.sales_df['gp1_by_kpi_center_usd'].sum() if 'gp1_by_kpi_center_usd' in self.sales_df.columns else 0
            if total_gp > 0:
                metrics['gp1_gp_ratio'] = total_gp1 / total_gp
        
        # Total backlog
        if not total_backlog_df.empty:
            metrics['total_backlog_revenue'] = total_backlog_df['total_backlog_usd'].sum()
            metrics['total_backlog_gp'] = total_backlog_df['total_backlog_gp_usd'].sum()
            metrics['total_backlog_gp1'] = metrics['total_backlog_gp'] * metrics['gp1_gp_ratio']
            metrics['backlog_orders'] = total_backlog_df['backlog_orders'].sum()
        
        # In-period backlog
        if not in_period_backlog_df.empty:
            metrics['in_period_backlog_revenue'] = in_period_backlog_df['in_period_backlog_usd'].sum()
            metrics['in_period_backlog_gp'] = in_period_backlog_df['in_period_backlog_gp_usd'].sum()
            metrics['in_period_backlog_gp1'] = metrics['in_period_backlog_gp'] * metrics['gp1_gp_ratio']
            metrics['in_period_orders'] = in_period_backlog_df['in_period_orders'].sum()
        
        # Calculate forecast = invoiced + in-period backlog
        invoiced_revenue = self.sales_df['sales_by_kpi_center_usd'].sum() if not self.sales_df.empty else 0
        invoiced_gp = self.sales_df['gross_profit_by_kpi_center_usd'].sum() if not self.sales_df.empty else 0
        invoiced_gp1 = self.sales_df['gp1_by_kpi_center_usd'].sum() if not self.sales_df.empty else 0
        
        metrics['current_invoiced_revenue'] = invoiced_revenue
        metrics['current_invoiced_gp'] = invoiced_gp
        metrics['current_invoiced_gp1'] = invoiced_gp1
        
        metrics['forecast_revenue'] = invoiced_revenue + metrics['in_period_backlog_revenue']
        metrics['forecast_gp'] = invoiced_gp + metrics['in_period_backlog_gp']
        metrics['forecast_gp1'] = invoiced_gp1 + metrics['in_period_backlog_gp1']
        
        # Period context
        if start_date and end_date:
            metrics['period_context'] = self.analyze_period_context(start_date, end_date)
        
        return metrics
    
    def calculate_pipeline_forecast_metrics(
        self,
        total_backlog_df: pd.DataFrame,
        in_period_backlog_df: pd.DataFrame,
        period_type: str = 'YTD',
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> Dict:
        """
        Calculate pipeline & forecast metrics with KPI filtering.
        
        For each KPI (Revenue/GP/GP1): Only includes invoiced + backlog from 
        KPI centers who have that specific KPI target assigned.
        
        UPDATED v4.0.1: Uses forecast proration (full period) for target calculation.
        - YTD: Target = 100% of annual (full year forecast)
        - QTD: Target = 25% of annual (full quarter)
        - MTD: Target = 1/12 of annual (full month)
        """
        # FIXED v4.0.1: Use FORECAST proration (full period), not current date proration
        # This aligns with In-Period Backlog which also uses full period
        proration = self._calculate_forecast_proration(period_type, year, start_date, end_date)
        
        # GP1/GP ratio for estimation
        gp1_gp_ratio = 1.0
        if not self.sales_df.empty:
            total_gp = self.sales_df['gross_profit_by_kpi_center_usd'].sum()
            total_gp1 = self.sales_df['gp1_by_kpi_center_usd'].sum() if 'gp1_by_kpi_center_usd' in self.sales_df.columns else 0
            if total_gp > 0:
                gp1_gp_ratio = total_gp1 / total_gp
        
        result = {
            'revenue': self._calculate_kpi_pipeline('revenue', proration, total_backlog_df, in_period_backlog_df),
            'gross_profit': self._calculate_kpi_pipeline('gross_profit', proration, total_backlog_df, in_period_backlog_df),
            'gp1': self._calculate_kpi_pipeline('gross_profit_1', proration, total_backlog_df, in_period_backlog_df, gp1_gp_ratio),
            'summary': {
                'total_backlog_revenue': total_backlog_df['total_backlog_usd'].sum() if not total_backlog_df.empty else 0,
                'total_backlog_gp': total_backlog_df['total_backlog_gp_usd'].sum() if not total_backlog_df.empty else 0,
                'total_backlog_gp1': (total_backlog_df['total_backlog_gp_usd'].sum() * gp1_gp_ratio) if not total_backlog_df.empty else 0,
                'backlog_orders': int(total_backlog_df['backlog_orders'].sum()) if not total_backlog_df.empty else 0,
                'gp1_gp_ratio': gp1_gp_ratio,
            },
            'period_context': self.analyze_period_context(start_date, end_date) if start_date and end_date else {},
        }
        
        return result
    
    def _calculate_kpi_pipeline(
        self,
        kpi_name: str,
        proration: float,
        total_backlog_df: pd.DataFrame,
        in_period_backlog_df: pd.DataFrame,
        gp1_ratio: float = 1.0
    ) -> Dict:
        """Calculate pipeline metrics for a specific KPI type."""
        # Get KPI centers with this target
        kpi_centers = self._get_kpi_centers_with_target(kpi_name)
        
        # Get target
        target = self._get_target_for_kpi(kpi_name)
        prorated_target = target * proration if target > 0 else None
        
        # Column mapping
        if kpi_name in ['revenue']:
            sales_col = 'sales_by_kpi_center_usd'
            backlog_col = 'total_backlog_usd'
            in_period_col = 'in_period_backlog_usd'
            use_ratio = False
        elif kpi_name in ['gross_profit']:
            sales_col = 'gross_profit_by_kpi_center_usd'
            backlog_col = 'total_backlog_gp_usd'
            in_period_col = 'in_period_backlog_gp_usd'
            use_ratio = False
        else:  # gp1
            sales_col = 'gp1_by_kpi_center_usd'
            backlog_col = 'total_backlog_gp_usd'  # Will apply ratio
            in_period_col = 'in_period_backlog_gp_usd'  # Will apply ratio
            use_ratio = True
        
        # Calculate invoiced from filtered KPI centers
        if kpi_centers and not self.sales_df.empty:
            filtered_sales = self.sales_df[self.sales_df['kpi_center_id'].isin(kpi_centers)]
            invoiced = filtered_sales[sales_col].sum() if sales_col in filtered_sales.columns else 0
        else:
            invoiced = self.sales_df[sales_col].sum() if not self.sales_df.empty and sales_col in self.sales_df.columns else 0
        
        # Calculate backlog from filtered KPI centers
        if kpi_centers and not in_period_backlog_df.empty:
            filtered_backlog = in_period_backlog_df[in_period_backlog_df['kpi_center_id'].isin(kpi_centers)]
            in_period_backlog = filtered_backlog[in_period_col].sum() if in_period_col in filtered_backlog.columns else 0
        else:
            in_period_backlog = in_period_backlog_df[in_period_col].sum() if not in_period_backlog_df.empty and in_period_col in in_period_backlog_df.columns else 0
        
        # Apply GP1 ratio if needed
        if use_ratio:
            in_period_backlog *= gp1_ratio
        
        # Forecast and gap
        forecast = invoiced + in_period_backlog
        gap = (forecast - prorated_target) if prorated_target else None
        gap_percent = (gap / prorated_target * 100) if prorated_target and prorated_target > 0 else None
        forecast_achievement = (forecast / prorated_target * 100) if prorated_target and prorated_target > 0 else None
        
        # FIXED: Changed employee_count to kpi_center_count for consistency
        return {
            'invoiced': invoiced,
            'in_period_backlog': in_period_backlog,
            'target': prorated_target,
            'forecast': forecast,
            'gap': gap,
            'gap_percent': gap_percent,
            'forecast_achievement': forecast_achievement,
            'kpi_center_count': len(kpi_centers),  # FIXED: was employee_count
        }
    
    # =========================================================================
    # IN-PERIOD BACKLOG ANALYSIS
    # =========================================================================
    
    @staticmethod
    def analyze_in_period_backlog(
        backlog_detail_df: pd.DataFrame,
        start_date: date,
        end_date: date
    ) -> Dict:
        """
        Analyze backlog with ETD within the selected period.
        
        Provides detailed breakdown of overdue vs on-track orders.
        """
        today = date.today()
        result = {
            'total_value': 0,
            'total_gp': 0,
            'total_count': 0,
            'overdue_value': 0,
            'overdue_gp': 0,
            'overdue_count': 0,
            'on_track_value': 0,
            'on_track_gp': 0,
            'on_track_count': 0,
            'status': 'empty',
            'overdue_warning': None
        }
        
        if backlog_detail_df.empty:
            return result
        
        df = backlog_detail_df.copy()
        
        # Ensure ETD is datetime
        if 'etd' in df.columns:
            df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
        else:
            return result
        
        # Filter to in-period (ETD within date range)
        in_period = df[
            (df['etd'].dt.date >= start_date) & 
            (df['etd'].dt.date <= end_date)
        ]
        
        if in_period.empty:
            return result
        
        # Get value columns
        value_col = 'backlog_by_kpi_center_usd' if 'backlog_by_kpi_center_usd' in in_period.columns else None
        gp_col = 'backlog_gp_by_kpi_center_usd' if 'backlog_gp_by_kpi_center_usd' in in_period.columns else None
        
        # Total in-period
        result['total_count'] = len(in_period)
        if value_col:
            result['total_value'] = in_period[value_col].sum()
        if gp_col:
            result['total_gp'] = in_period[gp_col].sum()
        
        # Split: Overdue (ETD < today) vs On-track (ETD >= today)
        overdue = in_period[in_period['etd'].dt.date < today]
        on_track = in_period[in_period['etd'].dt.date >= today]
        
        # Overdue metrics
        result['overdue_count'] = len(overdue)
        if value_col and not overdue.empty:
            result['overdue_value'] = overdue[value_col].sum()
        if gp_col and not overdue.empty:
            result['overdue_gp'] = overdue[gp_col].sum()
        
        # On-track metrics
        result['on_track_count'] = len(on_track)
        if value_col and not on_track.empty:
            result['on_track_value'] = on_track[value_col].sum()
        if gp_col and not on_track.empty:
            result['on_track_gp'] = on_track[gp_col].sum()
        
        # Determine status
        if result['overdue_count'] > 0:
            result['status'] = 'has_overdue'
            overdue_pct = (result['overdue_value'] / result['total_value'] * 100) if result['total_value'] > 0 else 0
            result['overdue_warning'] = (
                f"⚠️ {result['overdue_count']} orders (${result['overdue_value']:,.0f}, "
                f"{overdue_pct:.0f}%) are overdue"
            )
        else:
            result['status'] = 'healthy'
        
        return result
    
    # =========================================================================
    # BACKLOG BY MONTH PREPARATION
    # =========================================================================
    
    def prepare_backlog_by_month(
        self,
        backlog_by_month_df: pd.DataFrame,
        year: int = None
    ) -> pd.DataFrame:
        """
        Prepare backlog by ETD month for display.
        """
        if backlog_by_month_df.empty:
            return pd.DataFrame()
        
        df = backlog_by_month_df.copy()
        
        # Filter to year if provided
        if year and 'etd_year' in df.columns:
            df = df[df['etd_year'] == year]
        
        return df
    
    # =========================================================================
    # TOP CUSTOMERS/BRANDS ANALYSIS
    # =========================================================================
    
    def prepare_top_customers_by_metric(
        self,
        metric: str = 'revenue',
        top_percent: float = 0.8
    ) -> pd.DataFrame:
        """
        Get top customers that make up specified percentage of metric.
        """
        if self.sales_df.empty:
            return pd.DataFrame()
        
        df = self.sales_df.copy()
        
        # Map metric to column
        metric_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd'
        }
        col = metric_map.get(metric, 'sales_by_kpi_center_usd')
        
        # Group by customer
        customer_data = df.groupby(['customer_id', 'customer']).agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in df.columns else 'count'
        }).reset_index()
        
        customer_data.columns = ['customer_id', 'customer', 'revenue', 'gross_profit', 'gp1']
        
        if 'gp1_by_kpi_center_usd' not in df.columns:
            customer_data['gp1'] = 0
        
        # Sort by selected metric
        customer_data = customer_data.sort_values(metric, ascending=False)
        total_metric = customer_data[metric].sum()
        
        if total_metric == 0:
            return pd.DataFrame()
        
        # Calculate cumulative
        customer_data['cumulative_value'] = customer_data[metric].cumsum()
        customer_data['cumulative_percent'] = customer_data['cumulative_value'] / total_metric
        customer_data['percent_contribution'] = customer_data[metric] / total_metric * 100
        
        # Find cutoff
        exceed_mask = customer_data['cumulative_percent'] > top_percent
        
        if exceed_mask.any():
            first_exceed_idx = exceed_mask.idxmax()
            top_customers = customer_data.loc[:first_exceed_idx].copy()
        else:
            top_customers = customer_data.copy()
        
        return top_customers
    
    def prepare_top_brands_by_metric(
        self,
        metric: str = 'revenue',
        top_percent: float = 0.8
    ) -> pd.DataFrame:
        """
        Get top brands that make up specified percentage of metric.
        """
        if self.sales_df.empty:
            return pd.DataFrame()
        
        df = self.sales_df.copy()
        
        # Map metric to column
        metric_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd'
        }
        col = metric_map.get(metric, 'sales_by_kpi_center_usd')
        
        # Group by brand
        brand_data = df.groupby('brand').agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in df.columns else 'count'
        }).reset_index()
        
        brand_data.columns = ['brand', 'revenue', 'gross_profit', 'gp1']
        
        if 'gp1_by_kpi_center_usd' not in df.columns:
            brand_data['gp1'] = 0
        
        # Sort by selected metric
        brand_data = brand_data.sort_values(metric, ascending=False)
        total_metric = brand_data[metric].sum()
        
        if total_metric == 0:
            return pd.DataFrame()
        
        # Calculate cumulative
        brand_data['cumulative_value'] = brand_data[metric].cumsum()
        brand_data['cumulative_percent'] = brand_data['cumulative_value'] / total_metric
        brand_data['percent_contribution'] = brand_data[metric] / total_metric * 100
        
        # Find cutoff
        exceed_mask = brand_data['cumulative_percent'] > top_percent
        
        if exceed_mask.any():
            first_exceed_idx = exceed_mask.idxmax()
            top_brands = brand_data.loc[:first_exceed_idx].copy()
        else:
            top_brands = brand_data.copy()
        
        return top_brands
    
    # =========================================================================
    # IN-PERIOD BACKLOG ANALYSIS - NEW v3.0.0 (synced with Salesperson)
    # =========================================================================
    
    @staticmethod
    def analyze_in_period_backlog(
        backlog_detail_df: pd.DataFrame,
        start_date,
        end_date
    ) -> Dict:
        """
        Analyze backlog with ETD within the selected period.
        Provides detailed breakdown of overdue vs on-track orders.
        
        SYNCED v3.0.0 with Salesperson module.
        
        Args:
            backlog_detail_df: Detailed backlog records
            start_date: Period start date
            end_date: Period end date
            
        Returns:
            Dict with:
            - total_value, total_gp, total_count
            - overdue_value, overdue_gp, overdue_count
            - on_track_value, on_track_gp, on_track_count
            - status: 'empty', 'historical', 'has_overdue', 'healthy'
            - overdue_warning: str (if applicable)
        """
        from datetime import date
        
        today = date.today()
        result = {
            'total_value': 0,
            'total_gp': 0,
            'total_count': 0,
            'overdue_value': 0,
            'overdue_gp': 0,
            'overdue_count': 0,
            'on_track_value': 0,
            'on_track_gp': 0,
            'on_track_count': 0,
            'status': 'empty',
            'overdue_warning': None
        }
        
        if backlog_detail_df.empty:
            return result
        
        df = backlog_detail_df.copy()
        
        # Ensure ETD is datetime
        if 'etd' in df.columns:
            df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
        else:
            return result
        
        # Filter to in-period (ETD within date range)
        in_period = df[
            (df['etd'].dt.date >= start_date) & 
            (df['etd'].dt.date <= end_date)
        ]
        
        if in_period.empty:
            return result
        
        # Detect column names (KPI Center uses different names)
        value_col = None
        gp_col = None
        
        for col_name in ['backlog_by_kpi_center_usd', 'backlog_usd', 'backlog_revenue']:
            if col_name in in_period.columns:
                value_col = col_name
                break
        
        for col_name in ['backlog_gp_by_kpi_center_usd', 'backlog_gp_usd', 'backlog_gp']:
            if col_name in in_period.columns:
                gp_col = col_name
                break
        
        # Total in-period
        result['total_count'] = len(in_period)
        if value_col:
            result['total_value'] = in_period[value_col].sum()
        if gp_col:
            result['total_gp'] = in_period[gp_col].sum()
        
        # Split: Overdue (ETD < today) vs On-track (ETD >= today)
        overdue = in_period[in_period['etd'].dt.date < today]
        on_track = in_period[in_period['etd'].dt.date >= today]
        
        # Overdue metrics
        result['overdue_count'] = len(overdue)
        if value_col and not overdue.empty:
            result['overdue_value'] = overdue[value_col].sum()
        if gp_col and not overdue.empty:
            result['overdue_gp'] = overdue[gp_col].sum()
        
        # On-track metrics
        result['on_track_count'] = len(on_track)
        if value_col and not on_track.empty:
            result['on_track_value'] = on_track[value_col].sum()
        if gp_col and not on_track.empty:
            result['on_track_gp'] = on_track[gp_col].sum()
        
        # Determine status
        is_historical_period = end_date < today
        
        if is_historical_period:
            result['status'] = 'historical'
            if result['overdue_count'] > 0:
                result['overdue_warning'] = (
                    f"⚠️ {result['overdue_count']} orders with ETD in period are overdue. "
                    f"Total value: ${result['overdue_value']:,.0f}. Please review and update."
                )
        elif result['overdue_count'] > 0:
            result['status'] = 'has_overdue'
            result['overdue_warning'] = (
                f"⚠️ {result['overdue_count']} orders are past ETD. "
                f"Value: ${result['overdue_value']:,.0f}"
            )
        else:
            result['status'] = 'healthy'
        
        return result