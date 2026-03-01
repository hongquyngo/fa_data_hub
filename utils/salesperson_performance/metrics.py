# utils/salesperson_performance/metrics.py
"""
KPI Calculations for Salesperson Performance

Handles all metric calculations:
- Period aggregations (YTD/QTD/MTD)
- Target comparisons and achievement rates
- YoY growth calculations
- Complex KPI metrics (new customers/products/business)
- Data aggregations by salesperson/period

CHANGELOG:
- v2.9.4: FIXED KPI name mismatch bug causing Individual Overall Achievement to be wrong
          - Bug 1: Database stores "Gross Profit 1" but code expects "gross_profit_1"
            * Root cause: .lower() produces "gross profit 1" (space) but kpi_column_map 
              uses "gross_profit_1" (underscore) → KPIs not matched → skipped
            * Fix: Normalize kpi_name with .lower().replace(' ', '_')
          - Bug 2: Complex KPIs with actual=0 were excluded from Overall calculation
            * Root cause: Code checked "kpi_name in sp_complex_kpis" but sp_complex_kpis
              only contains keys for salespeople who HAVE data (actual > 0)
            * Result: When Wilson has New Business=$0, key doesn't exist → skip → excluded
            * Fix: Check "kpi_name in {'num_new_customers', ...}" instead, then use .get(kpi_name, 0)
          - Before fix: (141.8×50 + 149.8×50) / 100 = 145.8% (only 2 KPIs counted)
          - After fix: (141.8×20 + 149.8×20 + 0×30 + 0×30) / 100 = 58.3% (all 4 KPIs)
- v2.9.3: FIXED calculate_overall_kpi_achievement() for single person mode
          - Bug: Single person showed Total Weight = 260 (default_weight sum)
                 but should show 100 (assignment weight_numeric sum)
          - Fix: Detect single person (unique employee_id = 1) and use weight_numeric
          - Returns `is_single_person` flag for UI to show correct help text
          - Single: Σ(Achievement × assignment_weight) / Σ(assignment_weight)
          - Team: Σ(KPI_Type_Achievement × default_weight) / Σ(default_weight)
- v2.9.2: REVERTED Individual Overall to use weight_numeric from assignment
          - Team Overall: Uses default_weight from kpi_types table
          - Individual Overall: Uses weight_numeric from sales_employee_kpi_assignments
          - Removed kpi_type_weights parameter from aggregate_by_salesperson()
- v2.9.1: FIXED Complex KPI actual calculation bug in calculate_overall_kpi_achievement()
          - Bug: Used team-wide actual vs single person's target
          - Fix: Filter actual to only employees who have that specific KPI target
- v2.9.0: UPDATED kpi_type_weights to load dynamically from database
- v2.8.0: CHANGED Overall Achievement formula to use KPI Type default_weight
          - Old formula: Σ(Individual_Employee_Achievement × Individual_Weight) / Σ(Weight)
          - New formula: Σ(KPI_Type_Achievement × default_weight) / Σ(default_weight)
          - KPI_Type_Achievement = aggregate actual / aggregate prorated target
          - default_weight from kpi_types table (revenue=90, gp1=100, etc.)
          - More intuitive and easier to verify manually
          - aggregate_by_salesperson() also updated to use default_weight
- v2.7.0: ADDED overall_achievement per salesperson in aggregate_by_salesperson()
          - New column: overall_achievement = weighted avg of ALL KPIs
          - Same formula as calculate_overall_kpi_achievement() but per-person
          - Formula: Σ(KPI_Achievement × Weight) / Σ(Weight)
          - Includes Revenue, GP, GP1 achievements weighted by their KPI weights
          - Table "Performance by Salesperson" now shows same Achievement % as Overview
- v2.6.0: FIXED Achievement consistency in aggregate_by_salesperson()
          - Bug: Used ANNUAL target instead of PRORATED target
          - Result: Table Achievement % differed from Overall Achievement
          - Fix: Added period_type, year parameters to aggregate_by_salesperson()
          - Now uses same proration logic as calculate_overall_kpi_achievement()
          - Added GP1 Achievement calculation
          - Dropped annual target columns from output (only prorated)
- v2.5.0: FIXED weighted average calculation in calculate_overall_kpi_achievement()
          - Old bug: Used mean weight across salespeople (incorrect when weights differ)
          - New fix: Calculates at individual employee level
          - Formula: Overall = Σ(Individual_Achievement × Individual_Weight) / Σ(Weight)
          - Added _get_individual_employee_actual() helper method
- v2.4.0: UPDATED calculate_backlog_metrics() for PIPELINE & FORECAST enhancement
          - Added calculate_pipeline_forecast_metrics() method
          - For each KPI (Revenue/GP/GP1): Only includes invoiced + backlog from 
            employees who have that specific KPI target assigned
          - Returns detailed breakdown: invoiced, in_period_backlog, forecast, 
            target, gap for Revenue, GP, and GP1 separately
          - employee_count for each metric shows # employees with that KPI target
- v2.3.0: FIXED KPI Achievement calculation bug
          - calculate_overview_metrics(): Now calculates achievements using
            actuals from ONLY employees who have that specific KPI target
          - calculate_overall_kpi_achievement(): Same fix applied
          - Added _get_actual_for_kpi() helper method
          - Example fix: GP Achievement now only includes GP from employees
            who have GP target assigned, not from all selected employees
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import time

from .constants import MONTH_ORDER, QUARTER_MONTHS, KPI_TYPES

logger = logging.getLogger(__name__)

# Debug timing flag
DEBUG_METRICS_TIMING = True


def get_full_period_end_date(period_type: str, year: int) -> date:
    """
    Get the full end date for a period type.
    
    ADDED v2.10.0: Fix for In-Period backlog calculation.
    
    Backlog is FUTURE orders, so we need the FULL period end date,
    not today's date. This ensures In-Period includes all backlog
    with ETD within the full period.
    
    Args:
        period_type: 'YTD', 'QTD', 'MTD', 'LY', or 'Custom'
        year: Year for the period
        
    Returns:
        Full end date of the period:
        - YTD: Dec 31 of year
        - QTD: End of current quarter
        - MTD: End of current month
        - LY: Dec 31 of previous year
        - Custom: Returns None (caller should use custom end_date)
    """
    today = date.today()
    
    if period_type == 'YTD':
        return date(year, 12, 31)
    
    elif period_type == 'QTD':
        # Get current quarter end
        current_quarter = (today.month - 1) // 3 + 1
        quarter_end_month = current_quarter * 3
        if quarter_end_month == 12:
            return date(year, 12, 31)
        else:
            # Last day of quarter end month
            import calendar
            last_day = calendar.monthrange(year, quarter_end_month)[1]
            return date(year, quarter_end_month, last_day)
    
    elif period_type == 'MTD':
        # End of current month
        import calendar
        last_day = calendar.monthrange(year, today.month)[1]
        return date(year, today.month, last_day)
    
    elif period_type == 'LY':
        # Last year full year
        return date(year - 1, 12, 31)
    
    else:
        # Custom - return None, caller uses custom end_date
        return None


class SalespersonMetrics:
    """
    KPI calculations for salesperson performance.
    
    Usage:
        metrics = SalespersonMetrics(sales_df, targets_df)
        
        overview = metrics.calculate_overview_metrics('YTD', 2025)
        monthly = metrics.prepare_monthly_summary()
        by_salesperson = metrics.aggregate_by_salesperson()
    """
    
    def __init__(
        self, 
        sales_df: pd.DataFrame, 
        targets_df: pd.DataFrame = None
    ):
        """
        Initialize with data.
        
        Args:
            sales_df: Sales data from unified view
            targets_df: KPI targets (optional)
        """
        self.sales_df = sales_df
        self.targets_df = targets_df if targets_df is not None else pd.DataFrame()
    
    # =========================================================================
    # PERIOD CONTEXT ANALYSIS
    # =========================================================================
    
    @staticmethod
    def analyze_period_context(start_date: date, end_date: date) -> Dict:
        """
        Analyze the selected period relative to today.
        
        Determines if period is historical, current, or future for proper
        handling of backlog and forecast displays.
        
        Args:
            start_date: Period start date
            end_date: Period end date
            
        Returns:
            Dict with period context information:
            {
                'is_historical': bool,  # end_date < today
                'is_current': bool,     # start_date <= today <= end_date
                'is_future': bool,      # start_date > today
                'today': date,
                'days_until_end': int,  # negative if past
                'period_status': str,   # 'historical', 'current', 'future'
                'show_forecast': bool,  # Whether forecast is applicable
                'forecast_message': str # Message to display if forecast N/A
            }
        """
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
    
    @staticmethod
    def analyze_in_period_backlog(
        backlog_detail_df: pd.DataFrame,
        start_date: date,
        end_date: date,
        period_type: str = None,
        year: int = None
    ) -> Dict:
        """
        Analyze backlog with ETD within the selected period.
        
        Provides detailed breakdown of overdue vs on-track orders.
        
        FIXED v2.10.0: Added period_type and year parameters
        - For YTD/QTD/MTD: Uses full period end date (e.g., Dec 31 for YTD)
        - For Custom: Uses provided end_date
        - Backlog is FUTURE orders, so need full period for correct In-Period calculation
        
        Args:
            backlog_detail_df: Detailed backlog data with ETD
            start_date: Period start date
            end_date: Period end date (used for Custom, display only for others)
            period_type: Optional - 'YTD', 'QTD', 'MTD', 'LY', 'Custom'
            year: Optional - Year for period calculation
            
        Returns:
            Dict with detailed backlog analysis:
            {
                'total_value': float,
                'total_gp': float,
                'total_count': int,
                'overdue_value': float,
                'overdue_gp': float,
                'overdue_count': int,
                'on_track_value': float,
                'on_track_gp': float,
                'on_track_count': int,
                'status': str,  # 'empty', 'historical', 'has_overdue', 'healthy'
                'overdue_warning': str  # Warning message if applicable
            }
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
        
        # FIXED v2.10.0: Get full period end date for backlog
        # Backlog is FUTURE orders, so need full period (not today)
        if period_type and year:
            backlog_period_end = get_full_period_end_date(period_type, year)
            if backlog_period_end is None:
                backlog_period_end = end_date
        else:
            backlog_period_end = end_date
        
        # Filter to in-period (ETD within date range using full period end)
        in_period = df[
            (df['etd'].dt.date >= start_date) & 
            (df['etd'].dt.date <= backlog_period_end)
        ]
        
        if in_period.empty:
            return result
        
        # Get value columns
        value_col = 'backlog_sales_by_split_usd' if 'backlog_sales_by_split_usd' in in_period.columns else None
        gp_col = 'backlog_gp_by_split_usd' if 'backlog_gp_by_split_usd' in in_period.columns else None
        
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
        is_historical_period = backlog_period_end < today
        
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
    
    # =========================================================================
    # PERIOD DATE CALCULATIONS
    # =========================================================================
    
    @staticmethod
    def calculate_period_dates(
        period_type: str,
        year: int,
        custom_start: date = None,
        custom_end: date = None
    ) -> Tuple[date, date]:
        """
        Calculate start and end dates for a period type.
        
        Args:
            period_type: 'YTD', 'QTD', 'MTD', or 'Custom'
            year: Year for calculation
            custom_start: Custom start date (for 'Custom' period)
            custom_end: Custom end date (for 'Custom' period)
            
        Returns:
            Tuple of (start_date, end_date)
        """
        today = date.today()
        
        # Ensure year is integer
        year = int(year)
        
        if period_type == 'YTD':
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        elif period_type == 'QTD':
            current_quarter = (today.month - 1) // 3 + 1
            quarter_start_month = (current_quarter - 1) * 3 + 1
            start = date(year, quarter_start_month, 1)
            end = min(today, date(year, 12, 31))
        
        elif period_type == 'MTD':
            start = date(year, today.month, 1)
            end = today
        
        elif period_type == 'Custom' and custom_start and custom_end:
            start = custom_start
            end = custom_end
        
        else:
            # Default to YTD
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        return start, end
    
    @staticmethod
    def get_elapsed_months(year: int, as_of_date: date = None) -> int:
        """Get number of elapsed months in year as of given date."""
        if as_of_date is None:
            as_of_date = date.today()
        
        if as_of_date.year == year:
            return as_of_date.month
        elif as_of_date.year > year:
            return 12
        else:
            return 0
    
    # =========================================================================
    # HELPER: GET EMPLOYEES WITH SPECIFIC KPI TARGET
    # =========================================================================
    
    def _get_employees_with_kpi(self, kpi_name: str) -> List[int]:
        """
        Get list of employee IDs who have a specific KPI target assigned.
        
        Args:
            kpi_name: KPI name (e.g., 'revenue', 'gross_profit', 'gross_profit_1')
            
        Returns:
            List of employee_ids with the KPI target
        """
        if self.targets_df.empty:
            return []
        
        employees = self.targets_df[
            self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        ]['employee_id'].unique().tolist()
        
        return employees
    
    def _get_employees_with_kpi_count(self, kpi_name: str) -> int:
        """Get count of employees with a specific KPI target."""
        return len(self._get_employees_with_kpi(kpi_name))
    
    # =========================================================================
    # OVERVIEW METRICS
    # =========================================================================
    
    def calculate_overview_metrics(
        self,
        period_type: str = 'YTD',
        year: int = None
    ) -> Dict:
        """
        Calculate overview KPIs for display in metric cards.
        
        FIXED v2.3.0: Achievement calculations now only include actual values
        from employees who have the corresponding KPI target assigned.
        
        Args:
            period_type: Period type for target proration
            year: Year for target lookup
            
        Returns:
            Dict with all overview metrics
        """
        if year is None:
            year = datetime.now().year
        
        df = self.sales_df
        
        if df.empty:
            return self._get_empty_metrics()
        
        # === Basic Counts (from ALL selected salespeople) ===
        total_customers = df['customer_id'].nunique()
        total_invoices = df['inv_number'].nunique()
        total_orders = df['oc_number'].nunique()
        
        # === Financial Metrics (from ALL selected salespeople - for display) ===
        total_revenue = df['sales_by_split_usd'].sum()
        total_gp = df['gross_profit_by_split_usd'].sum()
        total_gp1 = df['gp1_by_split_usd'].sum()
        total_commission = df['allocated_broker_commission_usd'].sum()
        
        # === Percentages ===
        gp_percent = (total_gp / total_revenue * 100) if total_revenue else 0
        gp1_percent = (total_gp1 / total_revenue * 100) if total_revenue else 0
        
        # === Target Comparison ===
        # FIXED v2.3.0: Get targets and calculate actuals only from employees with targets
        revenue_target = self._get_prorated_target('revenue', period_type, year)
        gp_target = self._get_prorated_target('gross_profit', period_type, year)
        gp1_target = self._get_prorated_target('gross_profit_1', period_type, year)
        
        # Get actuals only from employees who have each specific KPI target
        revenue_actual_for_achievement = self._get_actual_for_kpi('revenue', 'sales_by_split_usd')
        gp_actual_for_achievement = self._get_actual_for_kpi('gross_profit', 'gross_profit_by_split_usd')
        gp1_actual_for_achievement = self._get_actual_for_kpi('gross_profit_1', 'gp1_by_split_usd')
        
        # Calculate achievements using filtered actuals
        revenue_achievement = (revenue_actual_for_achievement / revenue_target * 100) if revenue_target else None
        gp_achievement = (gp_actual_for_achievement / gp_target * 100) if gp_target else None
        gp1_achievement = (gp1_actual_for_achievement / gp1_target * 100) if gp1_target else None
        
        return {
            # Counts
            'total_customers': total_customers,
            'total_invoices': total_invoices,
            'total_orders': total_orders,
            
            # Financial (ALL salespeople - for display)
            'total_revenue': total_revenue,
            'total_gp': total_gp,
            'total_gp1': total_gp1,
            'total_commission': total_commission,
            
            # Percentages
            'gp_percent': round(gp_percent, 2),
            'gp1_percent': round(gp1_percent, 2),
            
            # Targets
            'revenue_target': revenue_target,
            'gp_target': gp_target,
            'gp1_target': gp1_target,
            
            # Achievements (from employees with corresponding targets only)
            'revenue_achievement': round(revenue_achievement, 1) if revenue_achievement else None,
            'gp_achievement': round(gp_achievement, 1) if gp_achievement else None,
            'gp1_achievement': round(gp1_achievement, 1) if gp1_achievement else None,
            
            # Actuals for achievement (for reference)
            'revenue_actual_for_achievement': revenue_actual_for_achievement,
            'gp_actual_for_achievement': gp_actual_for_achievement,
            'gp1_actual_for_achievement': gp1_actual_for_achievement,
        }
    
    def _get_empty_metrics(self) -> Dict:
        """Return empty metrics dict."""
        return {
            'total_customers': 0,
            'total_invoices': 0,
            'total_orders': 0,
            'total_revenue': 0,
            'total_gp': 0,
            'total_gp1': 0,
            'total_commission': 0,
            'gp_percent': 0,
            'gp1_percent': 0,
            'revenue_target': None,
            'gp_target': None,
            'gp1_target': None,
            'revenue_achievement': None,
            'gp_achievement': None,
            'gp1_achievement': None,
            'revenue_actual_for_achievement': 0,
            'gp_actual_for_achievement': 0,
            'gp1_actual_for_achievement': 0,
        }
    
    def _get_actual_for_kpi(
        self,
        kpi_name: str,
        value_column: str
    ) -> float:
        """
        Get actual value for a KPI from ONLY employees who have that KPI target.
        
        ADDED v2.3.0: Fixes the bug where achievements were calculated using
        all employees' values even if they didn't have the corresponding target.
        
        Args:
            kpi_name: KPI name (e.g., 'revenue', 'gross_profit', 'gross_profit_1')
            value_column: Column name in sales_df to sum
            
        Returns:
            Sum of value_column from employees with the KPI target
        """
        if self.targets_df.empty or self.sales_df.empty:
            return 0
        
        # Get employee IDs who have this specific KPI target
        employees_with_target = self._get_employees_with_kpi(kpi_name)
        
        if not employees_with_target:
            return 0
        
        # Filter sales data to only these employees
        filtered_sales = self.sales_df[
            self.sales_df['sales_id'].isin(employees_with_target)
        ]
        
        if filtered_sales.empty or value_column not in filtered_sales.columns:
            return 0
        
        return filtered_sales[value_column].sum()
    
    def _get_individual_employee_actual(
        self,
        employee_id: int,
        value_column: str
    ) -> float:
        """
        Get actual value for a specific employee from sales data.
        
        NEW v2.5.0: Helper method for individual-level achievement calculation.
        
        Args:
            employee_id: Employee ID to filter
            value_column: Column name in sales_df to sum
            
        Returns:
            Sum of value_column for this specific employee
        """
        if self.sales_df.empty:
            return 0
        
        if 'sales_id' not in self.sales_df.columns:
            return 0
        
        if value_column not in self.sales_df.columns:
            return 0
        
        employee_sales = self.sales_df[
            self.sales_df['sales_id'] == employee_id
        ]
        
        if employee_sales.empty:
            return 0
        
        return employee_sales[value_column].sum()
    
    # =========================================================================
    # TARGET CALCULATIONS
    # =========================================================================
    
    def _get_prorated_target(
        self,
        kpi_name: str,
        period_type: str,
        year: int
    ) -> Optional[float]:
        """
        Get prorated target based on period type.
        
        Proration logic:
        - YTD: annual × (elapsed_months / 12)
        - QTD: annual / 4
        - MTD: annual / 12
        - LY: annual (full year)
        - Custom: annual (full year)
        """
        if self.targets_df.empty:
            return None
        
        # Filter for this KPI
        kpi_rows = self.targets_df[
            self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        ]
        
        if kpi_rows.empty:
            return None
        
        # Sum annual targets across all filtered salespeople
        annual_target = kpi_rows['annual_target_value_numeric'].sum()
        
        if annual_target <= 0:
            return None
        
        # Prorate based on period
        if period_type == 'YTD':
            elapsed_months = self.get_elapsed_months(year)
            return annual_target * elapsed_months / 12
        
        elif period_type == 'QTD':
            return annual_target / 4
        
        elif period_type == 'MTD':
            return annual_target / 12
        
        elif period_type == 'LY':
            # Last Year = full annual target
            return annual_target
        
        else:
            # For custom, return full annual
            return annual_target
    
    def get_target_for_salesperson(
        self,
        employee_id: int,
        kpi_name: str,
        period_type: str = 'YTD',
        year: int = None
    ) -> Optional[float]:
        """Get prorated target for a specific salesperson."""
        if self.targets_df.empty:
            return None
        
        if year is None:
            year = datetime.now().year
        
        row = self.targets_df[
            (self.targets_df['employee_id'] == employee_id) &
            (self.targets_df['kpi_name'].str.lower() == kpi_name.lower())
        ]
        
        if row.empty:
            return None
        
        annual_target = float(row['annual_target_value_numeric'].iloc[0])
        
        if period_type == 'YTD':
            elapsed_months = self.get_elapsed_months(year)
            return annual_target * elapsed_months / 12
        elif period_type == 'QTD':
            return annual_target / 4
        elif period_type == 'MTD':
            return annual_target / 12
        else:
            return annual_target
    
    def _get_full_period_target(
        self,
        kpi_name: str,
        period_type: str,
        year: int
    ) -> Optional[float]:
        """
        Get target for FULL period (used in Pipeline & Forecast).
        
        ADDED v2.11.0: For Pipeline Forecast comparison with In-Period Backlog.
        
        Since In-Period Backlog uses full period end date (e.g., Dec 31 for YTD),
        Target should also use full period proration for fair comparison.
        
        Proration logic for full period:
        - YTD: Full annual target (12/12)
        - QTD: 1/4 of annual target
        - MTD: 1/12 of annual target
        - LY: Full annual target
        - Custom: Full annual target
        
        Args:
            kpi_name: KPI name (e.g., 'revenue', 'gross_profit')
            period_type: Period type
            year: Year for target lookup
            
        Returns:
            Target value for full period
        """
        if self.targets_df.empty:
            return None
        
        # Filter for this KPI
        kpi_rows = self.targets_df[
            self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        ]
        
        if kpi_rows.empty:
            return None
        
        # Sum annual targets across all filtered salespeople
        annual_target = kpi_rows['annual_target_value_numeric'].sum()
        
        if annual_target <= 0:
            return None
        
        # Prorate based on FULL period (not elapsed time)
        if period_type == 'YTD':
            # Full year target
            return annual_target
        
        elif period_type == 'QTD':
            # Quarter target
            return annual_target / 4
        
        elif period_type == 'MTD':
            # Month target
            return annual_target / 12
        
        elif period_type == 'LY':
            # Last Year = full annual target
            return annual_target
        
        else:
            # For custom, return full annual
            return annual_target
    
    # =========================================================================
    # COMPLEX KPI METRICS
    # =========================================================================
    
    def calculate_complex_kpis(
        self,
        new_customers_df: pd.DataFrame,
        new_products_df: pd.DataFrame,
        new_business_df: pd.DataFrame,
        new_combos_detail_df: pd.DataFrame = None  # NEW v1.1.0
    ) -> Dict:
        """
        Calculate complex KPIs with proportional split counting.
        
        UPDATED v1.1.0: Added num_new_combos from new_combos_detail_df
        
        Args:
            new_customers_df: New customers data
            new_products_df: New products data
            new_business_df: New business revenue data
            new_combos_detail_df: New combos detail data (NEW v1.1.0)
            
        Returns:
            Dict with complex KPI metrics
        """
        # New customers: count × split_rate / 100 (proportional)
        if not new_customers_df.empty:
            new_customer_count = new_customers_df['split_rate_percent'].sum() / 100
        else:
            new_customer_count = 0
        
        # New products: count × split_rate / 100 (proportional)
        if not new_products_df.empty:
            new_product_count = new_products_df['split_rate_percent'].sum() / 100
        else:
            new_product_count = 0
        
        # NEW v1.1.0: New combos count (distinct count, not weighted)
        if new_combos_detail_df is not None and not new_combos_detail_df.empty:
            num_new_combos = len(new_combos_detail_df)
        else:
            num_new_combos = 0
        
        # New business revenue (already split in query)
        if not new_business_df.empty:
            new_business_revenue = new_business_df['new_business_revenue'].sum()
            new_business_gp = new_business_df['new_business_gp'].sum() if 'new_business_gp' in new_business_df.columns else 0
        else:
            new_business_revenue = 0
            new_business_gp = 0
        
        # Get targets for complex KPIs
        customer_target = self._get_kpi_target_value('num_new_customers')
        product_target = self._get_kpi_target_value('num_new_products')
        combo_target = self._get_kpi_target_value('num_new_combos')  # NEW v1.1.0
        business_target = self._get_kpi_target_value('new_business_revenue')
        
        return {
            'new_customer_count': round(new_customer_count, 1),
            'new_product_count': round(new_product_count, 1),
            'num_new_combos': num_new_combos,  # NEW v1.1.0
            'new_business_revenue': new_business_revenue,
            'new_business_gp': new_business_gp,
            
            'new_customer_target': customer_target,
            'new_product_target': product_target,
            'new_combo_target': combo_target,  # NEW v1.1.0
            'new_business_target': business_target,
            
            'new_customer_achievement': self._calc_achievement(new_customer_count, customer_target),
            'new_product_achievement': self._calc_achievement(new_product_count, product_target),
            'new_combo_achievement': self._calc_achievement(num_new_combos, combo_target),  # NEW v1.1.0
            'new_business_achievement': self._calc_achievement(new_business_revenue, business_target),
        }
    
    def _get_kpi_target_value(self, kpi_name: str) -> Optional[float]:
        """Get total target value for a KPI (sum across all salespeople)."""
        if self.targets_df.empty:
            return None
        
        rows = self.targets_df[
            self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        ]
        
        if rows.empty:
            return None
        
        return rows['annual_target_value_numeric'].sum()
    
    @staticmethod
    def _calc_achievement(actual: float, target: Optional[float]) -> Optional[float]:
        """Calculate achievement percentage."""
        if target is None or target <= 0:
            return None
        return round(actual / target * 100, 1)
    
    # =========================================================================
    # OVERALL KPI ACHIEVEMENT (Weighted Average by KPI Type)
    # =========================================================================
    
    def calculate_overall_kpi_achievement(
        self,
        overview_metrics: Dict,
        complex_kpis: Dict = None,
        period_type: str = 'YTD',
        year: int = None,
        kpi_type_weights: Dict[str, int] = None,
        new_customers_df: pd.DataFrame = None,
        new_products_df: pd.DataFrame = None,
        new_business_df: pd.DataFrame = None
    ) -> Dict:
        """
        Calculate overall weighted KPI achievement using KPI Type default weights.
        
        UPDATED v2.8.0: Simplified formula using KPI Type level aggregation
        UPDATED v2.9.0: kpi_type_weights loaded dynamically from database
        FIXED v2.9.1: Complex KPIs now correctly filter actual by employees with target
                      - Bug: Used team-wide actual (351 products) vs 1 person's target (20)
                      - Fix: Filter actual to only employees who have that KPI target
        
        Formula: Overall = Σ(KPI_Type_Achievement × default_weight) / Σ(default_weight)
        
        Args:
            overview_metrics: Basic metrics from calculate_overview_metrics()
            complex_kpis: Complex KPIs from calculate_complex_kpis() (for backward compat)
            period_type: Period type for target proration
            year: Year for calculation
            kpi_type_weights: Dict of KPI name -> default_weight from database
            new_customers_df: Raw new customers DataFrame with sales_id for filtering
            new_products_df: Raw new products DataFrame with sales_id for filtering
            new_business_df: Raw new business DataFrame with sales_id for filtering
            
        Returns:
            Dict with overall_achievement, kpi_details, kpi_count, total_weight
        """
        _start_time = time.perf_counter()
        
        if self.targets_df.empty:
            return {
                'overall_achievement': None,
                'kpi_details': [],
                'kpi_count': 0,
                'total_weight': 0
            }
        
        if year is None:
            year = datetime.now().year
        
        # Fallback weights if not provided
        if kpi_type_weights is None:
            kpi_type_weights = {
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
            logger.warning("kpi_type_weights not provided, using fallback values")
            if DEBUG_METRICS_TIMING:
                print(f"   ⚠️ WARNING: kpi_type_weights not provided, using FALLBACK")
        else:
            if DEBUG_METRICS_TIMING:
                print(f"   ✅ kpi_type_weights loaded from database: {len(kpi_type_weights)} types")
                print(f"      Keys: {list(kpi_type_weights.keys())}")
        
        # Map KPI names to value columns for sales-based KPIs
        kpi_column_map = {
            'revenue': 'sales_by_split_usd',
            'gross_profit': 'gross_profit_by_split_usd',
            'gross_profit_1': 'gp1_by_split_usd',
        }
        
        # FIXED v2.9.1: Pre-calculate complex KPI actual per employee (filtered by those with target)
        # Previously: Used team-wide actual which was wrong when only some employees had target
        def get_complex_kpi_actual_for_employees(kpi_name: str, employee_ids: List[int]) -> float:
            """Get complex KPI actual filtered to only specific employees."""
            if not employee_ids:
                return 0
            
            if kpi_name == 'num_new_customers' and new_customers_df is not None and not new_customers_df.empty:
                if 'sales_id' in new_customers_df.columns:
                    filtered = new_customers_df[new_customers_df['sales_id'].isin(employee_ids)]
                    return filtered['split_rate_percent'].sum() / 100 if not filtered.empty else 0
                    
            elif kpi_name == 'num_new_products' and new_products_df is not None and not new_products_df.empty:
                if 'sales_id' in new_products_df.columns:
                    filtered = new_products_df[new_products_df['sales_id'].isin(employee_ids)]
                    return filtered['split_rate_percent'].sum() / 100 if not filtered.empty else 0
                    
            elif kpi_name == 'new_business_revenue' and new_business_df is not None and not new_business_df.empty:
                if 'sales_id' in new_business_df.columns:
                    filtered = new_business_df[new_business_df['sales_id'].isin(employee_ids)]
                    return filtered['new_business_revenue'].sum() if not filtered.empty else 0
            
            # Fallback to old behavior if dataframes not provided
            if complex_kpis:
                return complex_kpis.get({
                    'num_new_customers': 'new_customer_count',
                    'num_new_products': 'new_product_count',
                    'new_business_revenue': 'new_business_revenue'
                }.get(kpi_name, ''), 0)
            
            return 0
        
        # Complex KPI names for reference
        complex_kpi_names = {'num_new_customers', 'num_new_products', 'new_business_revenue'}
        
        # FIXED v2.9.3: Detect single person to use weight_numeric instead of default_weight
        unique_employees = self.targets_df['employee_id'].nunique()
        is_single_person = unique_employees == 1
        
        if DEBUG_METRICS_TIMING:
            if is_single_person:
                print(f"   👤 Single person mode: using weight_numeric from KPI assignment")
            else:
                print(f"   👥 Team mode ({unique_employees} people): using default_weight from kpi_types")
        
        # =====================================================================
        # STEP 1: Calculate aggregate metrics for each KPI TYPE
        # =====================================================================
        
        # Group targets by KPI type
        kpi_type_aggregates = {}
        
        for _, row in self.targets_df.iterrows():
            employee_id = row['employee_id']
            # FIXED: Normalize KPI name - replace spaces with underscores to match kpi_column_map keys
            kpi_name = row['kpi_name'].lower().replace(' ', '_')
            annual_target = row['annual_target_value_numeric']
            
            if annual_target <= 0:
                continue
            
            # Prorate target based on period
            if period_type == 'YTD':
                elapsed_months = self.get_elapsed_months(year)
                prorated_target = annual_target * elapsed_months / 12
            elif period_type == 'QTD':
                prorated_target = annual_target / 4
            elif period_type == 'MTD':
                prorated_target = annual_target / 12
            else:
                prorated_target = annual_target
            
            if prorated_target <= 0:
                continue
            
            # Aggregate by KPI type first (we'll calculate actual later for complex KPIs)
            if kpi_name not in kpi_type_aggregates:
                kpi_type_aggregates[kpi_name] = {
                    'actual_sum': 0,
                    'target_annual_sum': 0,
                    'target_prorated_sum': 0,
                    'employee_count': 0,
                    'employee_ids': [],  # Track employees with this KPI for complex KPI filtering
                    'weight_numeric': 0  # For single person mode - store assignment weight
                }
            
            # For sales-based KPIs, get actual per employee and accumulate
            if kpi_name in kpi_column_map:
                actual = self._get_individual_employee_actual(
                    employee_id, 
                    kpi_column_map[kpi_name]
                )
                kpi_type_aggregates[kpi_name]['actual_sum'] += actual
            
            # For complex KPIs, just track employee IDs (we'll calculate actual after grouping)
            if kpi_name in complex_kpi_names:
                kpi_type_aggregates[kpi_name]['employee_ids'].append(employee_id)
            
            kpi_type_aggregates[kpi_name]['target_annual_sum'] += annual_target
            kpi_type_aggregates[kpi_name]['target_prorated_sum'] += prorated_target
            kpi_type_aggregates[kpi_name]['employee_count'] += 1
            
            # Store weight_numeric for single person mode
            assignment_weight = row.get('weight_numeric', 50)
            if pd.isna(assignment_weight) or assignment_weight <= 0:
                assignment_weight = 50
            kpi_type_aggregates[kpi_name]['weight_numeric'] = assignment_weight
        
        # FIXED v2.9.1: Calculate actual for complex KPIs using filtered data
        # Now we have employee_ids list for each complex KPI, filter actual to only those employees
        for kpi_name in complex_kpi_names:
            if kpi_name in kpi_type_aggregates:
                employee_ids = kpi_type_aggregates[kpi_name]['employee_ids']
                actual = get_complex_kpi_actual_for_employees(kpi_name, employee_ids)
                kpi_type_aggregates[kpi_name]['actual_sum'] = actual
                
                if DEBUG_METRICS_TIMING:
                    print(f"      📊 Complex KPI '{kpi_name}': actual={actual:.1f} from {len(employee_ids)} employees with target")
        
        # =====================================================================
        # STEP 2: Calculate achievement for each KPI TYPE and build kpi_details
        # =====================================================================
        
        kpi_details = []
        
        for kpi_name, data in kpi_type_aggregates.items():
            # Calculate aggregate achievement for this KPI type
            if data['target_prorated_sum'] > 0:
                kpi_achievement = (data['actual_sum'] / data['target_prorated_sum']) * 100
            else:
                kpi_achievement = 0
            
            # FIXED v2.9.3: Choose weight source based on single person vs team
            if is_single_person:
                # Single person: use weight_numeric from KPI assignment
                weight = data.get('weight_numeric', 50)
            else:
                # Team: use default_weight from kpi_types table
                weight = kpi_type_weights.get(kpi_name, 50)
                
                # DEBUG: Check if key was found
                if DEBUG_METRICS_TIMING and kpi_name not in kpi_type_weights:
                    print(f"      ⚠️ Key '{kpi_name}' not found in kpi_type_weights, using default=50")
            
            kpi_details.append({
                'kpi_name': kpi_name,
                'actual': data['actual_sum'],
                'target_annual': data['target_annual_sum'],
                'target_prorated': data['target_prorated_sum'],
                'achievement': round(kpi_achievement, 1),
                'weight': weight,  # Renamed from default_weight to be generic
                'default_weight': weight,  # Keep for backward compatibility
                'employee_count': data['employee_count']
            })
        
        # =====================================================================
        # STEP 3: Calculate OVERALL using KPI Achievement × Weight
        # Single person: Σ(Achievement × assignment_weight) / Σ(assignment_weight)
        # Team: Σ(KPI_Type_Achievement × default_weight) / Σ(default_weight)
        # =====================================================================
        
        weighted_sum = 0
        total_weight = 0
        
        # DEBUG: Print KPI details for verification
        if DEBUG_METRICS_TIMING:
            weight_source = "assignment_weight" if is_single_person else "default_weight"
            print(f"\n   📊 [Overall Achievement Calculation - v2.9.3]")
            print(f"   Weight source: {weight_source}")
            print(f"   {'KPI Type':<25} {'Achievement':>12} {'Weight':>10} {'Weighted':>12}")
            print(f"   {'-'*25} {'-'*12} {'-'*10} {'-'*12}")
        
        for kpi in kpi_details:
            kpi_weighted = kpi['achievement'] * kpi['weight']
            weighted_sum += kpi_weighted
            total_weight += kpi['weight']
            
            if DEBUG_METRICS_TIMING:
                print(f"   {kpi['kpi_name']:<25} {kpi['achievement']:>11.1f}% {kpi['weight']:>10} {kpi_weighted:>12.1f}")
        
        if DEBUG_METRICS_TIMING:
            print(f"   {'-'*25} {'-'*12} {'-'*10} {'-'*12}")
            print(f"   {'TOTAL':<25} {'':<12} {total_weight:>10} {weighted_sum:>12.1f}")
        
        overall_achievement = (weighted_sum / total_weight) if total_weight > 0 else None
        
        if DEBUG_METRICS_TIMING:
            print(f"\n   🎯 Overall = {weighted_sum:.1f} / {total_weight} = {overall_achievement:.1f}%" if overall_achievement else "   🎯 Overall = N/A")
        
        return {
            'overall_achievement': round(overall_achievement, 1) if overall_achievement else None,
            'kpi_details': kpi_details,
            'kpi_count': len(kpi_details),
            'total_weight': total_weight,
            'is_single_person': is_single_person  # NEW v2.9.3: For UI to show correct help text
        }

    # =========================================================================
    # PIPELINE & FORECAST METRICS (NEW v2.4.0)
    # =========================================================================
    
    def calculate_pipeline_forecast_metrics(
        self,
        total_backlog_df: pd.DataFrame,
        in_period_backlog_df: pd.DataFrame,
        backlog_detail_df: pd.DataFrame,
        period_type: str = 'YTD',
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> Dict:
        """
        Calculate Pipeline & Forecast metrics for Revenue, GP, and GP1.
        
        NEW v2.4.0: For each KPI type, ONLY includes invoiced + backlog from 
        employees who have that specific KPI target assigned.
        
        FIXED v2.10.0: 
        - In-Period backlog now uses FULL period end date (not today)
          * YTD: Jan 1 to Dec 31 (not Jan 1 to today)
          * Backlog is FUTURE orders, so need full period
        - Summary totals now calculated from backlog_detail_df (filtered by salesperson)
          instead of total_backlog_df (pre-aggregated, not filtered)
        
        Args:
            total_backlog_df: Total backlog data (aggregated) - DEPRECATED for summary
            in_period_backlog_df: Backlog with ETD in period (aggregated) - DEPRECATED
            backlog_detail_df: Detailed backlog with sales_id for filtering
            period_type: Period type for target proration
            year: Year for target lookup
            start_date: Period start date
            end_date: Period end date (for display only, in-period uses full period)
            
        Returns:
            Dict with:
            - period_context: Dict with period analysis
            - revenue: Dict with invoiced, backlog, forecast, target, gap
            - gross_profit: Dict with invoiced, backlog, forecast, target, gap
            - gp1: Dict with invoiced, backlog, forecast, target, gap
            - summary: Dict with totals (for backward compatibility)
        """
        _start_time = time.perf_counter()
        if DEBUG_METRICS_TIMING:
            print(f"   📊 [pipeline_forecast] Starting calculation...")
        
        if year is None:
            year = datetime.now().year
        
        # Analyze period context
        today = date.today()
        if start_date is None:
            start_date = date(year, 1, 1)
        if end_date is None:
            end_date = today
        
        # FIXED v2.10.0: Get FULL period end date for in-period backlog calculation
        # Backlog is FUTURE orders, so we need full period end (e.g., Dec 31 for YTD)
        # not today's date
        backlog_period_end = get_full_period_end_date(period_type, year)
        if backlog_period_end is None:
            # Custom period - use provided end_date
            backlog_period_end = end_date
        
        if DEBUG_METRICS_TIMING:
            print(f"   📊 [pipeline_forecast] Period: {period_type}, "
                  f"Sales: {start_date} to {end_date}, "
                  f"Backlog In-Period: {start_date} to {backlog_period_end}")
        
        period_context = self.analyze_period_context(start_date, end_date)
        show_forecast = period_context['show_forecast']
        
        # Calculate GP1/GP ratio from current sales data for backlog estimation
        gp1_gp_ratio = 1.0  # Default: GP1 = GP (no commission)
        if not self.sales_df.empty:
            total_gp = self.sales_df['gross_profit_by_split_usd'].sum()
            total_gp1 = self.sales_df['gp1_by_split_usd'].sum()
            if total_gp > 0:
                gp1_gp_ratio = total_gp1 / total_gp
        
        # Helper to calculate in-period backlog from detail df for specific employees
        # FIXED v2.10.0: Uses backlog_period_end instead of end_date
        def get_in_period_backlog_for_employees(
            employee_ids: List[int],
            detail_df: pd.DataFrame,
            start: date,
            end: date
        ) -> Dict:
            """Calculate in-period backlog metrics for specific employees."""
            result = {'revenue': 0, 'gp': 0, 'gp1': 0, 'orders': 0}
            
            if detail_df.empty or not employee_ids:
                return result
            
            df = detail_df.copy()
            
            # Filter by employees
            if 'sales_id' in df.columns:
                df = df[df['sales_id'].isin(employee_ids)]
            
            if df.empty:
                return result
            
            # Filter by ETD in period
            if 'etd' in df.columns:
                df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
                df = df[
                    (df['etd'].dt.date >= start) & 
                    (df['etd'].dt.date <= end)
                ]
            
            if df.empty:
                return result
            
            # Sum values
            if 'backlog_sales_by_split_usd' in df.columns:
                result['revenue'] = df['backlog_sales_by_split_usd'].sum()
            if 'backlog_gp_by_split_usd' in df.columns:
                result['gp'] = df['backlog_gp_by_split_usd'].sum()
                # Estimate GP1 from GP using ratio
                result['gp1'] = result['gp'] * gp1_gp_ratio
            
            result['orders'] = len(df)
            
            return result
        
        # =====================================================================
        # REVENUE METRICS - Only from employees with Revenue KPI target
        # FIXED v2.10.0: Use backlog_period_end for in-period calculation
        # FIXED v2.11.0: Use _get_full_period_target for fair comparison with In-Period Backlog
        # =====================================================================
        revenue_employees = self._get_employees_with_kpi('revenue')
        # Use full period target (not prorated by elapsed time)
        revenue_target = self._get_full_period_target('revenue', period_type, year)
        
        # Invoiced revenue from employees with Revenue KPI
        revenue_invoiced = self._get_actual_for_kpi('revenue', 'sales_by_split_usd')
        
        # In-period backlog from employees with Revenue KPI
        # FIXED v2.10.0: Use backlog_period_end (full period) instead of end_date
        revenue_backlog_data = get_in_period_backlog_for_employees(
            revenue_employees, backlog_detail_df, start_date, backlog_period_end
        )
        revenue_in_period_backlog = revenue_backlog_data['revenue']
        
        # Forecast and GAP
        if show_forecast:
            revenue_forecast = revenue_invoiced + revenue_in_period_backlog
            revenue_gap = (revenue_forecast - revenue_target) if revenue_target else None
            revenue_gap_percent = (revenue_gap / revenue_target * 100) if revenue_target and revenue_gap is not None else None
            revenue_forecast_achievement = (revenue_forecast / revenue_target * 100) if revenue_target else None
        else:
            revenue_forecast = None
            revenue_gap = None
            revenue_gap_percent = None
            revenue_forecast_achievement = None
        
        revenue_metrics = {
            'invoiced': revenue_invoiced,
            'in_period_backlog': revenue_in_period_backlog,
            'forecast': revenue_forecast,
            'target': revenue_target,
            'gap': revenue_gap,
            'gap_percent': round(revenue_gap_percent, 1) if revenue_gap_percent is not None else None,
            'forecast_achievement': round(revenue_forecast_achievement, 1) if revenue_forecast_achievement is not None else None,
            'employee_count': len(revenue_employees),
            'backlog_orders': revenue_backlog_data['orders'],
        }
        
        # =====================================================================
        # GROSS PROFIT METRICS - Only from employees with GP KPI target
        # FIXED v2.10.0: Use backlog_period_end for in-period calculation
        # FIXED v2.11.0: Use _get_full_period_target for fair comparison
        # =====================================================================
        gp_employees = self._get_employees_with_kpi('gross_profit')
        # Use full period target (not prorated by elapsed time)
        gp_target = self._get_full_period_target('gross_profit', period_type, year)
        
        # Invoiced GP from employees with GP KPI
        gp_invoiced = self._get_actual_for_kpi('gross_profit', 'gross_profit_by_split_usd')
        
        # In-period backlog GP from employees with GP KPI
        # FIXED v2.10.0: Use backlog_period_end (full period) instead of end_date
        gp_backlog_data = get_in_period_backlog_for_employees(
            gp_employees, backlog_detail_df, start_date, backlog_period_end
        )
        gp_in_period_backlog = gp_backlog_data['gp']
        
        # Forecast and GAP
        if show_forecast:
            gp_forecast = gp_invoiced + gp_in_period_backlog
            gp_gap = (gp_forecast - gp_target) if gp_target else None
            gp_gap_percent = (gp_gap / gp_target * 100) if gp_target and gp_gap is not None else None
            gp_forecast_achievement = (gp_forecast / gp_target * 100) if gp_target else None
        else:
            gp_forecast = None
            gp_gap = None
            gp_gap_percent = None
            gp_forecast_achievement = None
        
        gp_metrics = {
            'invoiced': gp_invoiced,
            'in_period_backlog': gp_in_period_backlog,
            'forecast': gp_forecast,
            'target': gp_target,
            'gap': gp_gap,
            'gap_percent': round(gp_gap_percent, 1) if gp_gap_percent is not None else None,
            'forecast_achievement': round(gp_forecast_achievement, 1) if gp_forecast_achievement is not None else None,
            'employee_count': len(gp_employees),
            'backlog_orders': gp_backlog_data['orders'],
        }
        
        # =====================================================================
        # GP1 METRICS - Only from employees with GP1 KPI target
        # FIXED v2.10.0: Use backlog_period_end for in-period calculation
        # FIXED v2.11.0: Use _get_full_period_target for fair comparison
        # =====================================================================
        gp1_employees = self._get_employees_with_kpi('gross_profit_1')
        # Use full period target (not prorated by elapsed time)
        gp1_target = self._get_full_period_target('gross_profit_1', period_type, year)
        
        # Invoiced GP1 from employees with GP1 KPI
        gp1_invoiced = self._get_actual_for_kpi('gross_profit_1', 'gp1_by_split_usd')
        
        # In-period backlog GP1 from employees with GP1 KPI
        # FIXED v2.10.0: Use backlog_period_end (full period) instead of end_date
        gp1_backlog_data = get_in_period_backlog_for_employees(
            gp1_employees, backlog_detail_df, start_date, backlog_period_end
        )
        gp1_in_period_backlog = gp1_backlog_data['gp1']
        
        # Forecast and GAP
        if show_forecast:
            gp1_forecast = gp1_invoiced + gp1_in_period_backlog
            gp1_gap = (gp1_forecast - gp1_target) if gp1_target else None
            gp1_gap_percent = (gp1_gap / gp1_target * 100) if gp1_target and gp1_gap is not None else None
            gp1_forecast_achievement = (gp1_forecast / gp1_target * 100) if gp1_target else None
        else:
            gp1_forecast = None
            gp1_gap = None
            gp1_gap_percent = None
            gp1_forecast_achievement = None
        
        gp1_metrics = {
            'invoiced': gp1_invoiced,
            'in_period_backlog': gp1_in_period_backlog,
            'forecast': gp1_forecast,
            'target': gp1_target,
            'gap': gp1_gap,
            'gap_percent': round(gp1_gap_percent, 1) if gp1_gap_percent is not None else None,
            'forecast_achievement': round(gp1_forecast_achievement, 1) if gp1_forecast_achievement is not None else None,
            'employee_count': len(gp1_employees),
            'backlog_orders': gp1_backlog_data['orders'],
        }
        
        # =====================================================================
        # SUMMARY - Total backlog (all selected employees)
        # FIXED v2.10.0: Calculate from backlog_detail_df instead of total_backlog_df
        # total_backlog_df is pre-aggregated and doesn't filter by selected salesperson
        # backlog_detail_df is already filtered by salesperson in filter_data_client_side
        # =====================================================================
        total_backlog_revenue = 0
        total_backlog_gp = 0
        backlog_orders = 0
        
        if not backlog_detail_df.empty:
            # Calculate from detail df - this respects salesperson filter
            if 'backlog_sales_by_split_usd' in backlog_detail_df.columns:
                total_backlog_revenue = backlog_detail_df['backlog_sales_by_split_usd'].sum()
            if 'backlog_gp_by_split_usd' in backlog_detail_df.columns:
                total_backlog_gp = backlog_detail_df['backlog_gp_by_split_usd'].sum()
            if 'oc_number' in backlog_detail_df.columns:
                backlog_orders = backlog_detail_df['oc_number'].nunique()
        
        summary = {
            'total_backlog_revenue': total_backlog_revenue,
            'total_backlog_gp': total_backlog_gp,
            'total_backlog_gp1': total_backlog_gp * gp1_gp_ratio,
            'backlog_orders': backlog_orders,
            'gp1_gp_ratio': round(gp1_gp_ratio, 4),
            'backlog_period_end': backlog_period_end,  # For display in UI
        }
        
        if DEBUG_METRICS_TIMING:
            _elapsed = time.perf_counter() - _start_time
            print(f"   📊 [pipeline_forecast] Completed in {_elapsed:.3f}s")
        
        return {
            'period_context': period_context,
            'revenue': revenue_metrics,
            'gross_profit': gp_metrics,
            'gp1': gp1_metrics,
            'summary': summary,
        }
    
    # =========================================================================
    # BACKLOG & FORECAST CALCULATIONS (LEGACY - kept for backward compatibility)
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
        Calculate backlog and forecast metrics for Revenue, GP, and GP1.
        
        Note: This is the LEGACY method. For the updated logic that filters by 
        employees with KPI targets, use calculate_pipeline_forecast_metrics().
        
        Note: Backlog view doesn't have GP1 directly (no commission data for pending orders).
        We estimate GP1 backlog = GP backlog (conservative assumption - no commission deduction).
        
        Args:
            total_backlog_df: Total backlog data
            in_period_backlog_df: Backlog with ETD in period
            period_type: Period type for target lookup
            year: Year for target lookup
            start_date: Period start date (for context analysis)
            end_date: Period end date (for context analysis)
            
        Returns:
            Dict with backlog metrics for all 3 metrics, including period context
        """
        if year is None:
            year = datetime.now().year
        
        # Analyze period context
        today = date.today()
        if start_date is None:
            start_date = date(year, 1, 1)
        if end_date is None:
            end_date = today
        
        period_context = self.analyze_period_context(start_date, end_date)
        
        # Calculate GP1/GP ratio from current sales data for estimation
        gp1_gp_ratio = 1.0  # Default: GP1 = GP (no commission)
        if not self.sales_df.empty:
            total_gp = self.sales_df['gross_profit_by_split_usd'].sum()
            total_gp1 = self.sales_df['gp1_by_split_usd'].sum()
            if total_gp > 0:
                gp1_gp_ratio = total_gp1 / total_gp
        
        # Total backlog (all outstanding)
        total_backlog_revenue = 0
        total_backlog_gp = 0
        total_backlog_gp1 = 0
        backlog_orders = 0
        backlog_customers = 0
        
        if not total_backlog_df.empty:
            total_backlog_revenue = total_backlog_df['total_backlog_revenue'].sum()
            total_backlog_gp = total_backlog_df['total_backlog_gp'].sum()
            # GP1 backlog: use actual if available, otherwise estimate from GP using ratio
            if 'total_backlog_gp1' in total_backlog_df.columns:
                total_backlog_gp1 = total_backlog_df['total_backlog_gp1'].sum()
            else:
                total_backlog_gp1 = total_backlog_gp * gp1_gp_ratio
            backlog_orders = total_backlog_df['backlog_orders'].sum() if 'backlog_orders' in total_backlog_df.columns else 0
            backlog_customers = total_backlog_df['backlog_customers'].sum() if 'backlog_customers' in total_backlog_df.columns else 0
        
        # In-period backlog (ETD within period)
        in_period_backlog_revenue = 0
        in_period_backlog_gp = 0
        in_period_backlog_gp1 = 0
        in_period_orders = 0
        
        if not in_period_backlog_df.empty:
            in_period_backlog_revenue = in_period_backlog_df['in_period_backlog_revenue'].sum()
            in_period_backlog_gp = in_period_backlog_df['in_period_backlog_gp'].sum()
            # GP1 in-period backlog: use actual if available, otherwise estimate
            if 'in_period_backlog_gp1' in in_period_backlog_df.columns:
                in_period_backlog_gp1 = in_period_backlog_df['in_period_backlog_gp1'].sum()
            else:
                in_period_backlog_gp1 = in_period_backlog_gp * gp1_gp_ratio
            in_period_orders = in_period_backlog_df['in_period_orders'].sum() if 'in_period_orders' in in_period_backlog_df.columns else 0
        
        # Current invoiced (from sales_df)
        current_invoiced_revenue = self.sales_df['sales_by_split_usd'].sum() if not self.sales_df.empty else 0
        current_invoiced_gp = self.sales_df['gross_profit_by_split_usd'].sum() if not self.sales_df.empty else 0
        current_invoiced_gp1 = self.sales_df['gp1_by_split_usd'].sum() if not self.sales_df.empty else 0
        
        # Forecast calculation - depends on period context
        if period_context['show_forecast']:
            # For current/future periods: Forecast = Current Invoiced + In-Period Backlog
            forecast_revenue = current_invoiced_revenue + in_period_backlog_revenue
            forecast_gp = current_invoiced_gp + in_period_backlog_gp
            forecast_gp1 = current_invoiced_gp1 + in_period_backlog_gp1
        else:
            # For historical periods: Forecast is not applicable
            forecast_revenue = None
            forecast_gp = None
            forecast_gp1 = None
        
        # Get targets
        revenue_target = self._get_prorated_target('revenue', period_type, year)
        gp_target = self._get_prorated_target('gross_profit', period_type, year)
        gp1_target = self._get_prorated_target('gross_profit_1', period_type, year)  # GP1 KPI type
        
        # GAP calculations for Revenue (only if forecast available)
        gap_revenue = None
        gap_revenue_percent = None
        forecast_achievement_revenue = None
        
        if period_context['show_forecast'] and revenue_target and revenue_target > 0 and forecast_revenue is not None:
            gap_revenue = forecast_revenue - revenue_target
            gap_revenue_percent = (gap_revenue / revenue_target) * 100
            forecast_achievement_revenue = (forecast_revenue / revenue_target) * 100
        
        # GAP calculations for GP
        gap_gp = None
        gap_gp_percent = None
        forecast_achievement_gp = None
        
        if period_context['show_forecast'] and gp_target and gp_target > 0 and forecast_gp is not None:
            gap_gp = forecast_gp - gp_target
            gap_gp_percent = (gap_gp / gp_target) * 100
            forecast_achievement_gp = (forecast_gp / gp_target) * 100
        
        # GAP calculations for GP1
        gap_gp1 = None
        gap_gp1_percent = None
        forecast_achievement_gp1 = None
        
        if period_context['show_forecast'] and gp1_target and gp1_target > 0 and forecast_gp1 is not None:
            gap_gp1 = forecast_gp1 - gp1_target
            gap_gp1_percent = (gap_gp1 / gp1_target) * 100
            forecast_achievement_gp1 = (forecast_gp1 / gp1_target) * 100
        
        return {
            # Period Context
            'period_context': period_context,
            
            # Total Backlog
            'total_backlog_revenue': total_backlog_revenue,
            'total_backlog_gp': total_backlog_gp,
            'total_backlog_gp1': total_backlog_gp1,
            'backlog_orders': backlog_orders,
            'backlog_customers': backlog_customers,
            
            # In-Period Backlog
            'in_period_backlog_revenue': in_period_backlog_revenue,
            'in_period_backlog_gp': in_period_backlog_gp,
            'in_period_backlog_gp1': in_period_backlog_gp1,
            'in_period_orders': in_period_orders,
            
            # Current Invoiced
            'current_invoiced_revenue': current_invoiced_revenue,
            'current_invoiced_gp': current_invoiced_gp,
            'current_invoiced_gp1': current_invoiced_gp1,
            
            # Forecast (None if historical period)
            'forecast_revenue': forecast_revenue,
            'forecast_gp': forecast_gp,
            'forecast_gp1': forecast_gp1,
            
            # Targets
            'revenue_target': revenue_target,
            'gp_target': gp_target,
            'gp1_target': gp1_target,
            
            # GAP - Revenue
            'gap_revenue': gap_revenue,
            'gap_revenue_percent': round(gap_revenue_percent, 1) if gap_revenue_percent else None,
            
            # GAP - GP
            'gap_gp': gap_gp,
            'gap_gp_percent': round(gap_gp_percent, 1) if gap_gp_percent else None,
            
            # GAP - GP1
            'gap_gp1': gap_gp1,
            'gap_gp1_percent': round(gap_gp1_percent, 1) if gap_gp1_percent else None,
            
            # Forecast Achievement
            'forecast_achievement_revenue': round(forecast_achievement_revenue, 1) if forecast_achievement_revenue else None,
            'forecast_achievement_gp': round(forecast_achievement_gp, 1) if forecast_achievement_gp else None,
            'forecast_achievement_gp1': round(forecast_achievement_gp1, 1) if forecast_achievement_gp1 else None,
            
            # Backlog as % of Target (Revenue)
            'backlog_coverage_percent': round((in_period_backlog_revenue / revenue_target * 100), 1) if revenue_target else None,
            
            # GP1/GP ratio used for estimation
            'gp1_gp_ratio': round(gp1_gp_ratio, 4),
        }
    
    def prepare_backlog_by_month(
        self,
        backlog_by_month_df: pd.DataFrame,
        year: int = None
    ) -> pd.DataFrame:
        """
        Prepare backlog by month for chart display.
        
        Args:
            backlog_by_month_df: Backlog data grouped by ETD month
            year: Year to filter
            
        Returns:
            DataFrame with monthly backlog
        """
        if backlog_by_month_df.empty:
            return self._get_empty_backlog_monthly()
        
        if year is None:
            year = datetime.now().year
        
        # Filter to specified year
        df = backlog_by_month_df.copy()
        df['etd_year'] = df['etd_year'].astype(str)
        df = df[df['etd_year'] == str(year)]
        
        if df.empty:
            return self._get_empty_backlog_monthly()
        
        # Rename for consistency
        df = df.rename(columns={'etd_month': 'month'})
        
        # Ensure all months present
        all_months = pd.DataFrame({'month': MONTH_ORDER})
        df = all_months.merge(df, on='month', how='left').fillna(0)
        
        return df
    
    def prepare_backlog_by_month_multiyear(
        self,
        backlog_by_month_df: pd.DataFrame,
        include_empty_months: bool = False
    ) -> pd.DataFrame:
        """
        Prepare backlog by month for multi-year chart display.
        
        Unlike prepare_backlog_by_month(), this method:
        - Does NOT filter to a single year
        - Creates combined year-month labels (e.g., "Jan'25", "Feb'26")
        - Sorts chronologically across years
        - Supports color-coding by year
        
        Args:
            backlog_by_month_df: Backlog data grouped by ETD year/month
                Expected columns: etd_year, etd_month, backlog_revenue, backlog_gp, order_count
            include_empty_months: If True, include months with zero backlog
                (fills gaps between first and last month with data)
        
        Returns:
            DataFrame with columns:
            - year_month: Combined label (e.g., "Jan'25")
            - etd_year: Year as int
            - etd_month: Month abbreviation
            - month_num: Month number (1-12) for sorting
            - sort_order: Integer for chronological sorting (year*100 + month)
            - backlog_revenue: Revenue amount
            - backlog_gp: Gross profit amount
            - order_count: Number of orders
        
        Example output:
            year_month | etd_year | etd_month | sort_order | backlog_revenue
            Jan'25     | 2025     | Jan       | 202501     | 27,249
            Feb'25     | 2025     | Feb       | 202502     | 21,502
            ...
            Jan'26     | 2026     | Jan       | 202601     | 45,000
        
        CHANGELOG:
        - v1.0.0: Initial implementation for multi-year backlog view
        """
        if backlog_by_month_df.empty:
            return pd.DataFrame({
                'year_month': [],
                'etd_year': [],
                'etd_month': [],
                'month_num': [],
                'sort_order': [],
                'backlog_revenue': [],
                'backlog_gp': [],
                'order_count': [],
            })
        
        df = backlog_by_month_df.copy()
        
        # Ensure etd_year is integer
        df['etd_year'] = pd.to_numeric(df['etd_year'], errors='coerce').fillna(0).astype(int)
        
        # Create month number for sorting
        month_to_num = {m: i+1 for i, m in enumerate(MONTH_ORDER)}
        df['month_num'] = df['etd_month'].map(month_to_num)
        
        # Create sort order: year * 100 + month (e.g., 202501, 202502, ..., 202601)
        df['sort_order'] = df['etd_year'] * 100 + df['month_num']
        
        # Create combined year-month label
        # Format: "Jan'25", "Feb'25", etc.
        df['year_month'] = df.apply(
            lambda row: f"{row['etd_month']}'{str(row['etd_year'])[-2:]}", 
            axis=1
        )
        
        # Sort chronologically
        df = df.sort_values('sort_order').reset_index(drop=True)
        
        # Optionally fill empty months (gaps between first and last data point)
        if include_empty_months and len(df) > 0:
            min_order = df['sort_order'].min()
            max_order = df['sort_order'].max()
            
            # Generate all year-months between min and max
            all_periods = []
            current = min_order
            while current <= max_order:
                year = current // 100
                month = current % 100
                if 1 <= month <= 12:
                    month_abbr = MONTH_ORDER[month - 1]
                    all_periods.append({
                        'sort_order': current,
                        'etd_year': year,
                        'etd_month': month_abbr,
                        'month_num': month,
                        'year_month': f"{month_abbr}'{str(year)[-2:]}",
                    })
                # Move to next month
                if month == 12:
                    current = (year + 1) * 100 + 1
                else:
                    current += 1
            
            all_periods_df = pd.DataFrame(all_periods)
            
            # Merge with actual data
            df = all_periods_df.merge(
                df[['sort_order', 'backlog_revenue', 'backlog_gp', 'order_count']],
                on='sort_order',
                how='left'
            ).fillna(0)
        
        # Ensure numeric columns
        for col in ['backlog_revenue', 'backlog_gp', 'order_count']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Select and order columns
        result_cols = ['year_month', 'etd_year', 'etd_month', 'month_num', 
                    'sort_order', 'backlog_revenue', 'backlog_gp', 'order_count']
        result_cols = [c for c in result_cols if c in df.columns]
        
        return df[result_cols]


    def get_backlog_year_summary(
        self,
        backlog_by_month_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Get summary of backlog by year for legend/info display.
        
        Returns:
            DataFrame with columns: etd_year, total_revenue, total_gp, total_orders
        """
        if backlog_by_month_df.empty:
            return pd.DataFrame()
        
        df = backlog_by_month_df.copy()
        df['etd_year'] = pd.to_numeric(df['etd_year'], errors='coerce').fillna(0).astype(int)
        
        summary = df.groupby('etd_year').agg({
            'backlog_revenue': 'sum',
            'backlog_gp': 'sum',
            'order_count': 'sum'
        }).reset_index()
        
        summary.columns = ['etd_year', 'total_revenue', 'total_gp', 'total_orders']
        summary = summary.sort_values('etd_year')
        
        return summary


    def _get_empty_backlog_monthly(self) -> pd.DataFrame:
        """Return empty backlog monthly summary."""
        return pd.DataFrame({
            'month': MONTH_ORDER,
            'backlog_revenue': [0] * 12,
            'backlog_gp': [0] * 12,
            'order_count': [0] * 12,
        })
    
    # =========================================================================
    # YOY COMPARISON
    # =========================================================================
    
    def calculate_yoy_comparison(
        self,
        current_metrics: Dict,
        previous_metrics: Dict
    ) -> Dict:
        """
        Calculate YoY growth percentages.
        
        Args:
            current_metrics: Metrics from current period
            previous_metrics: Metrics from same period last year
            
        Returns:
            Dict with YoY growth percentages
        """
        def calc_yoy(current, previous):
            if previous and previous > 0:
                return ((current - previous) / previous) * 100
            return None
        
        return {
            'total_revenue_yoy': calc_yoy(
                current_metrics.get('total_revenue', 0),
                previous_metrics.get('total_revenue', 0)
            ),
            'total_gp_yoy': calc_yoy(
                current_metrics.get('total_gp', 0),
                previous_metrics.get('total_gp', 0)
            ),
            'total_gp1_yoy': calc_yoy(
                current_metrics.get('total_gp1', 0),
                previous_metrics.get('total_gp1', 0)
            ),
            'total_customers_yoy': calc_yoy(
                current_metrics.get('total_customers', 0),
                previous_metrics.get('total_customers', 0)
            ),
        }
    
    # =========================================================================
    # MONTHLY SUMMARY
    # =========================================================================
    
    def prepare_monthly_summary(self) -> pd.DataFrame:
        """
        Prepare monthly summary data for charts and tables.
        
        Returns:
            DataFrame with monthly aggregated data including cumulative values
        """
        if self.sales_df.empty:
            return self._get_empty_monthly_summary()
        
        df = self.sales_df.copy()
        
        # Ensure invoice_month exists
        if 'invoice_month' not in df.columns:
            if 'inv_date' in df.columns:
                df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
                df['invoice_month'] = df['inv_date'].dt.strftime('%b')
            else:
                return self._get_empty_monthly_summary()
        
        # Aggregate by month
        monthly = df.groupby('invoice_month').agg({
            'sales_by_split_usd': 'sum',
            'gross_profit_by_split_usd': 'sum',
            'gp1_by_split_usd': 'sum',
            'customer_id': pd.Series.nunique
        }).reset_index()
        
        monthly.columns = ['invoice_month', 'revenue', 'gross_profit', 'gp1', 'customer_count']
        
        # Calculate GP%
        monthly['gp_percent'] = (monthly['gross_profit'] / monthly['revenue'] * 100).round(2)
        monthly['gp1_percent'] = (monthly['gp1'] / monthly['revenue'] * 100).round(2)
        
        # Ensure all months present
        all_months = pd.DataFrame({'invoice_month': MONTH_ORDER})
        monthly = all_months.merge(monthly, on='invoice_month', how='left').fillna(0)
        
        # Add month order for sorting
        monthly['month_order'] = monthly['invoice_month'].apply(
            lambda x: MONTH_ORDER.index(x) if x in MONTH_ORDER else 12
        )
        monthly = monthly.sort_values('month_order')
        
        # Calculate cumulative
        monthly['cumulative_revenue'] = monthly['revenue'].cumsum()
        monthly['cumulative_gp'] = monthly['gross_profit'].cumsum()
        monthly['cumulative_gp1'] = monthly['gp1'].cumsum()
        
        return monthly
    
    def _get_empty_monthly_summary(self) -> pd.DataFrame:
        """Return empty monthly summary."""
        return pd.DataFrame({
            'invoice_month': MONTH_ORDER,
            'revenue': [0] * 12,
            'gross_profit': [0] * 12,
            'gp1': [0] * 12,
            'customer_count': [0] * 12,
            'gp_percent': [0] * 12,
            'gp1_percent': [0] * 12,
            'cumulative_revenue': [0] * 12,
            'cumulative_gp': [0] * 12,
            'cumulative_gp1': [0] * 12,
            'month_order': list(range(12)),
        })
    
    # =========================================================================
    # SALESPERSON AGGREGATION
    # =========================================================================
    
    def aggregate_by_salesperson(
        self,
        period_type: str = 'YTD',
        year: int = None,
        complex_kpis: Dict = None,
        new_customers_df: pd.DataFrame = None,
        new_products_df: pd.DataFrame = None,
        new_business_df: pd.DataFrame = None
    ) -> pd.DataFrame:
        """
        Aggregate metrics by salesperson for ranking and comparison.
        
        FIXED v2.7.0: Now calculates WEIGHTED OVERALL Achievement per salesperson
        
        REVERTED v2.9.2: Individual Overall uses weight_numeric from assignment
                         (NOT default_weight - that's for Team Overall only)
        
        Individual vs Team Overall Achievement:
        - Individual: Uses weight_numeric from sales_employee_kpi_assignments
          Formula: Σ(KPI_Achievement × assignment_weight) / Σ(assignment_weight)
        - Team: Uses default_weight from kpi_types table
          Formula: Σ(KPI_Type_Achievement × default_weight) / Σ(default_weight)
        
        Args:
            period_type: Period type for target proration ('YTD', 'QTD', 'MTD', 'LY', 'Custom')
            year: Year for elapsed months calculation (used for YTD proration)
            complex_kpis: (Deprecated) Aggregated dict - kept for backward compatibility
            new_customers_df: Raw new customers DataFrame with sales_id column
            new_products_df: Raw new products DataFrame with sales_id column
            new_business_df: Raw new business DataFrame with sales_id column
        
        Returns:
            DataFrame with per-salesperson metrics including overall_achievement
        """
        if self.sales_df.empty:
            return pd.DataFrame()
        
        if year is None:
            year = datetime.now().year
        
        df = self.sales_df.copy()
        
        # Group by salesperson
        by_sales = df.groupby(['sales_id', 'sales_name']).agg({
            'sales_by_split_usd': 'sum',
            'gross_profit_by_split_usd': 'sum',
            'gp1_by_split_usd': 'sum',
            'customer_id': pd.Series.nunique,
            'inv_number': pd.Series.nunique
        }).reset_index()
        
        by_sales.columns = ['sales_id', 'sales_name', 'revenue', 'gross_profit', 'gp1', 'customers', 'invoices']
        
        # Calculate percentages
        by_sales['gp_percent'] = (by_sales['gross_profit'] / by_sales['revenue'] * 100).round(2)
        by_sales['gp1_percent'] = (by_sales['gp1'] / by_sales['revenue'] * 100).round(2)
        
        # Calculate proration factor based on period type
        if period_type == 'YTD':
            elapsed_months = self.get_elapsed_months(year)
            proration_factor = elapsed_months / 12
        elif period_type == 'QTD':
            proration_factor = 1 / 4
        elif period_type == 'MTD':
            proration_factor = 1 / 12
        elif period_type == 'LY':
            proration_factor = 1.0
        else:
            proration_factor = 1.0
        
        # =========================================================================
        # PRE-CALCULATE COMPLEX KPI VALUES PER SALESPERSON
        # =========================================================================
        per_salesperson_complex_kpis = {}
        
        # New Customers per salesperson: count × split_rate / 100
        if new_customers_df is not None and not new_customers_df.empty and 'sales_id' in new_customers_df.columns:
            nc_by_sales = new_customers_df.groupby('sales_id').agg({
                'split_rate_percent': 'sum'
            }).reset_index()
            nc_by_sales['new_customer_count'] = nc_by_sales['split_rate_percent'] / 100
            for _, row in nc_by_sales.iterrows():
                sid = row['sales_id']
                if sid not in per_salesperson_complex_kpis:
                    per_salesperson_complex_kpis[sid] = {}
                per_salesperson_complex_kpis[sid]['num_new_customers'] = row['new_customer_count']
        
        # New Products per salesperson: count × split_rate / 100
        if new_products_df is not None and not new_products_df.empty and 'sales_id' in new_products_df.columns:
            np_by_sales = new_products_df.groupby('sales_id').agg({
                'split_rate_percent': 'sum'
            }).reset_index()
            np_by_sales['new_product_count'] = np_by_sales['split_rate_percent'] / 100
            for _, row in np_by_sales.iterrows():
                sid = row['sales_id']
                if sid not in per_salesperson_complex_kpis:
                    per_salesperson_complex_kpis[sid] = {}
                per_salesperson_complex_kpis[sid]['num_new_products'] = row['new_product_count']
        
        # New Business Revenue per salesperson
        if new_business_df is not None and not new_business_df.empty and 'sales_id' in new_business_df.columns:
            nb_by_sales = new_business_df.groupby('sales_id').agg({
                'new_business_revenue': 'sum'
            }).reset_index()
            for _, row in nb_by_sales.iterrows():
                sid = row['sales_id']
                if sid not in per_salesperson_complex_kpis:
                    per_salesperson_complex_kpis[sid] = {}
                per_salesperson_complex_kpis[sid]['new_business_revenue'] = row['new_business_revenue']
        
        # Add targets if available
        if not self.targets_df.empty:
            # FIXED: Normalize KPI names for comparison (replace spaces with underscores)
            normalized_kpi_names = self.targets_df['kpi_name'].str.lower().str.replace(' ', '_')
            
            # Get revenue targets with proration
            revenue_targets = self.targets_df[
                normalized_kpi_names == 'revenue'
            ][['employee_id', 'annual_target_value_numeric']].copy()
            revenue_targets.columns = ['sales_id', 'revenue_target_annual']
            
            by_sales = by_sales.merge(revenue_targets, on='sales_id', how='left')
            by_sales['revenue_target'] = by_sales['revenue_target_annual'] * proration_factor
            by_sales['revenue_achievement'] = (
                by_sales['revenue'] / by_sales['revenue_target'] * 100
            ).round(1)
            
            # GP targets with proration
            gp_targets = self.targets_df[
                normalized_kpi_names == 'gross_profit'
            ][['employee_id', 'annual_target_value_numeric']].copy()
            gp_targets.columns = ['sales_id', 'gp_target_annual']
            
            by_sales = by_sales.merge(gp_targets, on='sales_id', how='left')
            by_sales['gp_target'] = by_sales['gp_target_annual'] * proration_factor
            by_sales['gp_achievement'] = (
                by_sales['gross_profit'] / by_sales['gp_target'] * 100
            ).round(1)
            
            # GP1 targets with proration
            gp1_targets = self.targets_df[
                normalized_kpi_names == 'gross_profit_1'
            ][['employee_id', 'annual_target_value_numeric']].copy()
            gp1_targets.columns = ['sales_id', 'gp1_target_annual']
            
            by_sales = by_sales.merge(gp1_targets, on='sales_id', how='left')
            by_sales['gp1_target'] = by_sales['gp1_target_annual'] * proration_factor
            by_sales['gp1_achievement'] = (
                by_sales['gp1'] / by_sales['gp1_target'] * 100
            ).round(1)
            
            # =========================================================
            # CALCULATE WEIGHTED OVERALL Achievement per salesperson
            # REVERTED v2.9.2: Use weight_numeric from assignment
            # (NOT default_weight - that's for Team Overall only)
            # Formula: Σ(KPI_Achievement × assignment_weight) / Σ(assignment_weight)
            # =========================================================
            
            kpi_column_map = {
                'revenue': 'revenue',
                'gross_profit': 'gross_profit',
                'gross_profit_1': 'gp1',
            }
            
            overall_achievements = []
            
            for _, row in by_sales.iterrows():
                sales_id = row['sales_id']
                
                # Get all KPI assignments for this employee
                employee_kpis = self.targets_df[
                    self.targets_df['employee_id'] == sales_id
                ]
                
                if employee_kpis.empty:
                    overall_achievements.append(None)
                    continue
                
                weighted_sum = 0
                total_weight = 0
                
                # Get this salesperson's complex KPI values
                sp_complex_kpis = per_salesperson_complex_kpis.get(sales_id, {})
                
                # Group by KPI type to avoid double-counting (shouldn't happen but safe)
                processed_kpi_types = set()
                
                for _, kpi_row in employee_kpis.iterrows():
                    # FIXED: Normalize KPI name - replace spaces with underscores to match kpi_column_map keys
                    kpi_name = kpi_row['kpi_name'].lower().replace(' ', '_')
                    annual_target = kpi_row['annual_target_value_numeric']
                    
                    # Skip if already processed this KPI type
                    if kpi_name in processed_kpi_types:
                        continue
                    processed_kpi_types.add(kpi_name)
                    
                    if annual_target <= 0:
                        continue
                    
                    prorated_target = annual_target * proration_factor
                    
                    if prorated_target <= 0:
                        continue
                    
                    # Get actual value for this KPI
                    if kpi_name in kpi_column_map:
                        # Sales-based KPIs
                        actual_col = kpi_column_map[kpi_name]
                        actual = row[actual_col] if actual_col in row.index else 0
                    elif kpi_name in {'num_new_customers', 'num_new_products', 'new_business_revenue'}:
                        # Complex KPIs - get from per_salesperson_complex_kpis, default to 0 if not found
                        # FIXED: Previously checked "kpi_name in sp_complex_kpis" which skipped KPIs 
                        # when salesperson had no data (actual=0), causing them to be excluded from Overall
                        actual = sp_complex_kpis.get(kpi_name, 0)
                    else:
                        # Unknown KPI type, skip
                        continue
                    
                    # REVERTED v2.9.2: Use weight_numeric from individual assignment
                    # (NOT default_weight - that's for Team Overall only)
                    individual_weight = kpi_row.get('weight_numeric', 50)
                    if pd.isna(individual_weight) or individual_weight <= 0:
                        individual_weight = 50  # Fallback
                    
                    # Calculate achievement
                    achievement = (actual / prorated_target) * 100
                    weighted_sum += achievement * individual_weight
                    total_weight += individual_weight
                
                if total_weight > 0:
                    overall_achievements.append(round(weighted_sum / total_weight, 1))
                else:
                    overall_achievements.append(None)
            
            by_sales['overall_achievement'] = overall_achievements
            
            # Drop annual target columns
            cols_to_drop = ['revenue_target_annual', 'gp_target_annual', 'gp1_target_annual']
            by_sales = by_sales.drop(columns=[c for c in cols_to_drop if c in by_sales.columns], errors='ignore')
        
        return by_sales.sort_values('revenue', ascending=False)
    
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
        
        Args:
            metric: 'revenue', 'gross_profit', or 'gp1'
            top_percent: Percentage threshold (default 0.8 = 80%)
            
        Returns:
            DataFrame with top customers and their contribution
        """
        if self.sales_df.empty:
            return pd.DataFrame()
        
        df = self.sales_df.copy()
        
        # Map metric to column
        metric_map = {
            'revenue': 'sales_by_split_usd',
            'gross_profit': 'gross_profit_by_split_usd',
            'gp1': 'gp1_by_split_usd'
        }
        col = metric_map.get(metric, 'sales_by_split_usd')
        
        # Group by customer
        customer_data = df.groupby(['customer_id', 'customer']).agg({
            'sales_by_split_usd': 'sum',
            'gross_profit_by_split_usd': 'sum',
            'gp1_by_split_usd': 'sum'
        }).reset_index()
        
        customer_data.columns = ['customer_id', 'customer', 'revenue', 'gross_profit', 'gp1']
        
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
            'revenue': 'sales_by_split_usd',
            'gross_profit': 'gross_profit_by_split_usd',
            'gp1': 'gp1_by_split_usd'
        }
        col = metric_map.get(metric, 'sales_by_split_usd')
        
        # Group by brand
        brand_data = df.groupby('brand').agg({
            'sales_by_split_usd': 'sum',
            'gross_profit_by_split_usd': 'sum',
            'gp1_by_split_usd': 'sum'
        }).reset_index()
        
        brand_data.columns = ['brand', 'revenue', 'gross_profit', 'gp1']
        
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