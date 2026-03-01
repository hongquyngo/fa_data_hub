# utils/salesperson_performance/queries.py
"""
SQL Queries and Data Loading for Salesperson Performance

Handles all database interactions:
- Sales data from unified_sales_by_salesperson_view
- Lookback data for Complex KPIs AND sidebar options (via get_lookback_sales_data)
- KPI targets from sales_employee_kpi_assignments_view
- Backlog data from backlog_by_salesperson_looker_view
- Lookup data (salespeople list, entities, years)
- KPI type weights from kpi_types table (NEW v3.2.0)

All queries respect access control filtering.
Uses @st.cache_data for performance.

CHANGELOG:
- v3.2.0: ADDED get_kpi_type_weights() and get_kpi_type_weights_cached()
          - Dynamically load KPI type default_weight from kpi_types table
          - Used for Team Overall Achievement calculation
          - Cached for 1 hour (KPI types rarely change)
          - Fallback to hardcoded weights if database unavailable
- v3.1.0: UPDATED get_lookback_sales_data() for sidebar options
          - Added columns: sales_email, legal_entity_id, legal_entity, inv_number, invoice_year
          - Enables extraction of sidebar options from lookback data
          - Eliminates need for 3 separate sidebar SQL queries (7.33s savings)
          - See: sidebar_options_extractor.py for Pandas extraction
- v3.0.0: REMOVED deprecated Complex KPI SQL methods (replaced by Pandas)
          - Removed: get_new_customers(), get_new_products(), 
                    get_new_business_revenue(), get_new_business_detail(),
                    calculate_complex_kpi_value()
          - Added: get_lookback_sales_data() - single query for Pandas processing
          - See: complex_kpi_calculator.py for new implementation
          - Performance: 14.76s -> ~3.0s (80% faster)
          - Removed ~600 lines of Complex KPI SQL code
- v1.7.0: FIXED get_backlog_detail() LIMIT issue
          - Changed limit parameter: int = 100 -> Optional[int] = None
          - Default is now None (no limit) to avoid data truncation
          - LIMIT clause only added when limit is explicitly provided
          - Fixes mismatch between Backlog Tab totals and Overview totals
- v1.6.0: ADDED calculate_complex_kpi_value() helper method (DEPRECATED in v3.0.0)
          - Calculates single complex KPI for specific employees
          - Used by KPI Progress to filter by employees with target
          - Supports: num_new_customers, num_new_products, new_business_revenue
- v1.5.0: FIXED backlog queries to filter uninvoiced only
          - Added condition: invoice_completion_percent < 100 OR IS NULL
          - Affects: get_backlog_data, get_backlog_in_period, 
                     get_backlog_by_month, get_backlog_detail
          - Backlog now correctly represents UNINVOICED value only
- v1.4.0: REFACTORED get_new_products() to use legacy_code from unified view
          - No longer needs JOIN with products table
          - Uses COALESCE(product_id, legacy_code) as unified product key
          - Correctly identifies products sold in history (via legacy_code) 
            that appear in realtime (via product_id)
          - Handles edge cases: NULL product_id in history, NULL legacy_code in old realtime
- v1.3.0: Fixed duplicate counting bug - unified view has multiple rows per invoice (1 per product)
          Added GROUP BY deduplication: each customer/product + salesperson combo counted once
          NEW BUSINESS REVENUE: Now includes ALL revenue from new combos in period (not just first day)
          A combo is "new" if first sale (in 5yr lookback) falls within selected period
- v1.2.0: Fixed lookback calculation - now uses end_date.year instead of start_date.year
          Fixed RANK() instead of ROW_NUMBER() to credit all salespeople who made
          first sale on same day (split credit scenario)
- v1.1.0: Fixed num_new_customers logic - now "new to company" instead of "new to salesperson"
          Changed PARTITION BY customer_id, sales_id -> PARTITION BY customer_id

VERSION: 3.1.0
"""

import logging
from datetime import date, datetime
from typing import List, Optional, Tuple, Dict
import pandas as pd
import streamlit as st
from sqlalchemy import text
import time

from utils.db import get_db_engine
from .constants import CACHE_TTL_SECONDS
from .access_control import AccessControl

logger = logging.getLogger(__name__)

# Debug timing flag - set to True to see query timings
DEBUG_QUERY_TIMING = True


class SalespersonQueries:
    """
    Data loading class for salesperson performance.
    
    Usage:
        access = AccessControl(user_role, employee_id)
        queries = SalespersonQueries(access)
        
        sales_df = queries.get_sales_data(start_date, end_date)
        targets_df = queries.get_kpi_targets(year)
    """
    
    def __init__(self, access_control: AccessControl):
        """
        Initialize with access control.
        
        Args:
            access_control: AccessControl instance for filtering
        """
        self.access = access_control
        self._engine = None
    
    @property
    def engine(self):
        """Lazy load database engine."""
        if self._engine is None:
            self._engine = get_db_engine()
        return self._engine
    
    # =========================================================================
    # CORE SALES DATA
    # =========================================================================
    
    def get_sales_data(
        self,
        start_date: date,
        end_date: date,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Load sales data from unified_sales_by_salesperson_view.
        
        Args:
            start_date: Start date for filtering
            end_date: End date for filtering
            employee_ids: Optional list of specific employee IDs (will be validated)
            entity_ids: Optional list of legal entity IDs
            
        Returns:
            DataFrame with sales data
        """
        # Validate employee_ids against access control
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            logger.warning("No accessible employee IDs, returning empty DataFrame")
            return pd.DataFrame()
        
        # Build query
        query = """
            SELECT 
                data_source,
                unified_line_id,
                sales_id,
                sales_name,
                sales_email,
                employment_status,
                split_rate_percent,
                inv_date,
                inv_number,
                vat_number,
                legal_entity,
                legal_entity_id,
                customer,
                customer_id,
                customer_code,
                customer_type,
                customer_po_number,
                oc_number,
                oc_date,
                product_id,
                product_pn,
                pt_code,
                brand,
                sales_by_split_usd,
                gross_profit_by_split_usd,
                gp1_by_split_usd,
                allocated_broker_commission_usd,
                invoice_month,
                invoice_year
            FROM unified_sales_by_salesperson_view
            WHERE inv_date BETWEEN :start_date AND :end_date
              AND sales_id IN :employee_ids
        """
        
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'employee_ids': tuple(employee_ids)
        }
        
        # Add entity filter if provided
        if entity_ids:
            query += " AND legal_entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " ORDER BY inv_date DESC"
        
        return self._execute_query(query, params, "sales_data")
    
    def get_sales_data_cached(
        self,
        start_date: date,
        end_date: date,
        employee_ids_tuple: tuple = None,
        entity_ids_tuple: tuple = None
    ) -> pd.DataFrame:
        """
        Cached version of get_sales_data.
        Use tuples instead of lists for cache key compatibility.
        """
        return _get_sales_data_cached(
            start_date, 
            end_date,
            employee_ids_tuple or tuple(self.access.get_accessible_employee_ids()),
            entity_ids_tuple
        )
    
    # =========================================================================
    # LOOKBACK DATA FOR COMPLEX KPIs (NEW v3.0.0)
    # UPDATED v3.1.0: Added columns for sidebar options extraction
    # =========================================================================
    
    def get_lookback_sales_data(
        self,
        end_date: date,
        lookback_years: int = 5
    ) -> pd.DataFrame:
        """
        Load ALL sales data for Complex KPI calculations AND sidebar options.
        
        This replaces the expensive SQL CTEs in get_new_customers, get_new_products,
        and get_new_business_revenue with a single query + Pandas processing.
        
        UPDATED v3.1.0: Also used to extract sidebar options (salesperson, entity, years)
        - Saves additional 7.3s by eliminating 3 separate SQL queries
        
        IMPORTANT: Does NOT filter by employee_ids because Complex KPIs need
        GLOBAL first dates (first customer to COMPANY, not first to salesperson).
        
        Performance:
        - Old: 4 SQL queries with CTEs = 14.76s + 3 sidebar queries = 7.3s
        - New: 1 simple SELECT = ~2.8s + Pandas extraction = ~0.01s
        
        Args:
            end_date: End date of analysis period (lookback starts from end_date.year - lookback_years)
            lookback_years: Number of years to look back (default 5)
            
        Returns:
            DataFrame with all sales data needed for Complex KPI calculations and sidebar options
        """
        # Calculate lookback start date
        lookback_start = date(end_date.year - lookback_years, 1, 1)
        
        # Simple SELECT - no WHERE on employee_ids for global first dates
        # Include legacy_code for product_key calculation
        # UPDATED v3.1.0: Added sales_email, legal_entity_id, legal_entity, inv_number, invoice_year
        # UPDATED v3.2.0: Added is_service from products table to filter service products
        query = """
            SELECT 
                v.sales_id,
                v.sales_name,
                v.sales_email,
                v.split_rate_percent,
                v.inv_date,
                v.inv_number,
                v.invoice_year,
                v.legal_entity_id,
                v.legal_entity,
                v.customer,
                v.customer_id,
                v.customer_code,
                v.customer_type,
                v.product_id,
                v.product_pn,
                v.pt_code,
                v.package_size,
                v.legacy_code,
                v.brand,
                v.sales_by_split_usd,
                v.gross_profit_by_split_usd,
                v.gp1_by_split_usd,
                COALESCE(p.is_service, 0) AS is_service
            FROM unified_sales_by_salesperson_view v
            LEFT JOIN products p ON v.product_id = p.id
            WHERE v.inv_date >= :lookback_start
        """
        
        params = {'lookback_start': lookback_start}
        
        return self._execute_query(query, params, "lookback_sales_data")
    
    # =========================================================================
    # KPI TARGETS
    # =========================================================================
    
    def get_kpi_targets(
        self,
        year: int,
        employee_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Load KPI targets from sales_employee_kpi_assignments_view.
        
        Args:
            year: Year to get targets for
            employee_ids: Optional list of employee IDs
            
        Returns:
            DataFrame with KPI targets
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        query = """
            SELECT 
                employee_id,
                employee_name,
                email,
                status,
                year,
                kpi_type_id,
                kpi_name,
                annual_target_value,
                annual_target_value_numeric,
                unit_of_measure,
                weight_numeric,
                monthly_target_value,
                quarterly_target_value,
                is_current_year
            FROM sales_employee_kpi_assignments_view
            WHERE year = :year
              AND employee_id IN :employee_ids
        """
        
        params = {
            'year': year,
            'employee_ids': tuple(employee_ids)
        }
        
        return self._execute_query(query, params, "kpi_targets")
    

    # =========================================================================
    # COMPLEX KPIs - DEPRECATED v3.0.0
    # =========================================================================
    # The following methods have been replaced by ComplexKPICalculator (Pandas-based):
    # - get_new_customers() -> ComplexKPICalculator.calculate_new_customers()
    # - get_new_products() -> ComplexKPICalculator.calculate_new_products()
    # - get_new_business_revenue() -> ComplexKPICalculator.calculate_new_business_revenue()
    # - get_new_business_detail() -> ComplexKPICalculator.calculate_new_business_detail()
    # - calculate_complex_kpi_value() -> ComplexKPICalculator.calculate_all()
    #
    # See: utils/salesperson_performance/complex_kpi_calculator.py
    # Performance improvement: 14.76s -> ~3.0s (80% faster)
    # =========================================================================

    # =========================================================================
    # SIDEBAR OPTIONS - DEPRECATED v3.1.0
    # =========================================================================
    # The following methods have been replaced by SidebarOptionsExtractor (Pandas-based):
    # - get_salesperson_options() -> SidebarOptionsExtractor.extract_salesperson_options()
    # - get_entity_options() -> SidebarOptionsExtractor.extract_entity_options()
    # - get_available_years() -> SidebarOptionsExtractor.extract_available_years()
    # - get_default_date_range() -> SidebarOptionsExtractor.extract_date_range()
    # - get_employees_with_kpi() -> Not needed (filter in memory)
    #
    # See: utils/salesperson_performance/sidebar_options_extractor.py
    # Performance improvement: 7.33s (3 SQL queries) -> ~0.01s (Pandas extraction)
    # =========================================================================

    # =========================================================================
    # YoY COMPARISON DATA
    # =========================================================================
    
    def get_previous_year_data(
        self,
        start_date: date,
        end_date: date,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get same period data from previous year for YoY comparison.
        
        Args:
            start_date: Current period start date
            end_date: Current period end date
            employee_ids: Optional employee filter
            entity_ids: Optional entity filter
            
        Returns:
            DataFrame with previous year data
        """
        # Calculate previous year dates
        prev_start = date(start_date.year - 1, start_date.month, start_date.day)
        
        # Handle leap year for end date
        try:
            prev_end = date(end_date.year - 1, end_date.month, end_date.day)
        except ValueError:
            # Feb 29 -> Feb 28 for non-leap year
            prev_end = date(end_date.year - 1, end_date.month, 28)
        
        return self.get_sales_data(prev_start, prev_end, employee_ids, entity_ids)
    
    # =========================================================================
    # BACKLOG DATA (Outstanding)
    # =========================================================================
    
    def get_backlog_data(
        self,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None,
        exclude_internal: bool = False
    ) -> pd.DataFrame:
        """
        Get total backlog/outstanding data by salesperson.
        
        UPDATED v1.8.0: Added exclude_internal parameter to filter out internal customers
        
        Returns DataFrame with total backlog revenue and GP by salesperson.
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # Build internal filter clause
        internal_filter = "AND LOWER(customer_type) != 'internal'" if exclude_internal else ""
        
        # UPDATED: Backlog = Uninvoiced value only
        # Filter out rows where invoice_completion_percent = 100
        query = f"""
            SELECT 
                sales_id,
                sales_name,
                SUM(backlog_sales_by_split_usd) as total_backlog_revenue,
                SUM(backlog_gp_by_split_usd) as total_backlog_gp,
                COUNT(DISTINCT oc_number) as backlog_orders,
                COUNT(DISTINCT customer_id) as backlog_customers
            FROM backlog_by_salesperson_looker_view
            WHERE sales_id IN :employee_ids
              AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
              {internal_filter}
        """
        
        params = {'employee_ids': tuple(employee_ids)}
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " GROUP BY sales_id, sales_name"
        
        return self._execute_query(query, params, "backlog_data")
    
    def get_backlog_in_period(
        self,
        start_date: date,
        end_date: date,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None,
        exclude_internal: bool = False
    ) -> pd.DataFrame:
        """
        Get backlog with ETD falling within the specified period.
        This represents backlog expected to convert to invoice in the period.
        
        UPDATED v1.8.0: Added exclude_internal parameter to filter out internal customers
        
        Args:
            start_date: Period start date
            end_date: Period end date
            employee_ids: Optional employee filter
            entity_ids: Optional entity filter
            exclude_internal: If True, exclude internal customers from revenue calculation
            
        Returns DataFrame with in-period backlog by salesperson.
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # Build internal filter clause
        internal_filter = "AND LOWER(customer_type) != 'internal'" if exclude_internal else ""
        
        # UPDATED: Backlog = Uninvoiced value only
        query = f"""
            SELECT 
                sales_id,
                sales_name,
                SUM(backlog_sales_by_split_usd) as in_period_backlog_revenue,
                SUM(backlog_gp_by_split_usd) as in_period_backlog_gp,
                COUNT(DISTINCT oc_number) as in_period_orders,
                COUNT(DISTINCT customer_id) as in_period_customers
            FROM backlog_by_salesperson_looker_view
            WHERE sales_id IN :employee_ids
              AND etd BETWEEN :start_date AND :end_date
              AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
              {internal_filter}
        """
        
        params = {
            'employee_ids': tuple(employee_ids),
            'start_date': start_date,
            'end_date': end_date
        }
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " GROUP BY sales_id, sales_name"
        
        return self._execute_query(query, params, "backlog_in_period")
    
    def get_backlog_by_month(
        self,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None,
        exclude_internal: bool = False
    ) -> pd.DataFrame:
        """
        Get backlog grouped by ETD month for forecasting.
        
        UPDATED v1.8.0: Added exclude_internal parameter to filter out internal customers
        
        Returns DataFrame with backlog by ETD month.
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # Build internal filter clause
        internal_filter = "AND LOWER(customer_type) != 'internal'" if exclude_internal else ""
        
        # UPDATED: Backlog = Uninvoiced value only
        query = f"""
            SELECT 
                etd_year,
                etd_month,
                SUM(backlog_sales_by_split_usd) as backlog_revenue,
                SUM(backlog_gp_by_split_usd) as backlog_gp,
                COUNT(DISTINCT oc_number) as order_count
            FROM backlog_by_salesperson_looker_view
            WHERE sales_id IN :employee_ids
              AND etd IS NOT NULL
              AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
              {internal_filter}
        """
        
        params = {'employee_ids': tuple(employee_ids)}
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += """
            GROUP BY etd_year, etd_month
            ORDER BY etd_year, 
                     FIELD(etd_month, 'Jan','Feb','Mar','Apr','May','Jun',
                                      'Jul','Aug','Sep','Oct','Nov','Dec')
        """
        
        return self._execute_query(query, params, "backlog_by_month")
    
    def get_backlog_detail(
        self,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get detailed backlog records for drill-down.
        
        Args:
            employee_ids: Optional list of employee IDs to filter
            entity_ids: Optional list of entity IDs to filter
            limit: Optional row limit. Default is None (no limit).
                   Set to a number (e.g., 1000) to limit results for performance.
        
        Returns DataFrame with individual backlog line items.
        
        UPDATED v1.7.0: Changed limit default from 100 to None (no limit)
        to avoid data truncation and ensure accurate totals.
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # UPDATED v1.5.0: Backlog = Uninvoiced value only
        # Added: customer_po_number, pt_code, package_size for enhanced display
        query = """
            SELECT 
                oc_number,
                oc_date,
                etd,
                customer,
                customer_id,
                customer_po_number,
                product_pn,
                pt_code,
                package_size,
                brand,
                sales_name,
                sales_id,
                legal_entity,
                backlog_sales_by_split_usd,
                backlog_gp_by_split_usd,
                split_rate_percent,
                pending_type,
                days_until_etd,
                status,
                invoice_completion_percent
            FROM backlog_by_salesperson_looker_view
            WHERE sales_id IN :employee_ids
              AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
        """
        
        params = {'employee_ids': tuple(employee_ids)}
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " ORDER BY backlog_sales_by_split_usd DESC"
        
        # Only add LIMIT if explicitly provided (v1.7.0)
        if limit is not None:
            query += f" LIMIT {limit}"
        
        return self._execute_query(query, params, "backlog_detail")
    
    # =========================================================================
    # SALES SPLIT DATA
    # =========================================================================
    
    def get_sales_split_data(
        self,
        employee_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get sales split assignments for salespeople.
        
        Returns DataFrame with split assignments including customer, product, percentage.
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        query = """
            SELECT 
                ss.sales_id,
                ss.sales_name,
                ss.sales_email,
                ss.employment_status,
                c.english_name as customer,
                c.id as customer_id,
                COALESCE(p.name, 'All Products') as product_pn,
                p.id as product_id,
                ss.split_percentage,
                ss.effective_period,
                ss.approval_status
            FROM sales_split_full_looker_view ss
            LEFT JOIN companies c ON ss.customer_id = c.id
            LEFT JOIN products p ON ss.product_id = p.id
            WHERE ss.sales_id IN :employee_ids
              AND ss.approval_status = 'approved'
            ORDER BY ss.sales_name, c.english_name
        """
        
        params = {'employee_ids': tuple(employee_ids)}
        
        return self._execute_query(query, params, "sales_split_data")
    
    # =========================================================================
    # KPI TYPE WEIGHTS (Dynamic from Database)
    # =========================================================================
    
    def get_kpi_type_weights(self) -> Dict[str, int]:
        """
        Load KPI type default weights from kpi_types table.
        
        NEW v3.2.0: Dynamic loading for Team Overall Achievement calculation
        
        Returns:
            Dict mapping kpi_name (lowercase) to default_weight
            Example: {'revenue': 90, 'gross_profit': 95, 'gross_profit_1': 100, ...}
        """
        query = """
            SELECT 
                LOWER(name) as kpi_name,
                COALESCE(default_weight, 50) as default_weight
            FROM kpi_types
            WHERE delete_flag = 0
        """
        
        try:
            df = self._execute_query(query, {}, "kpi_type_weights")
            
            if df.empty:
                logger.warning("No KPI types found in database, using fallback weights")
                return _get_fallback_kpi_weights()
            
            # Convert to dict
            weights = dict(zip(df['kpi_name'], df['default_weight'].astype(int)))
            logger.info(f"Loaded {len(weights)} KPI type weights from database")
            return weights
            
        except Exception as e:
            logger.error(f"Error loading KPI type weights: {e}")
            return _get_fallback_kpi_weights()
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _execute_query(
        self, 
        query: str, 
        params: dict, 
        query_name: str = "query"
    ) -> pd.DataFrame:
        """
        Execute SQL query and return DataFrame.
        
        Args:
            query: SQL query string
            params: Query parameters
            query_name: Name for logging
            
        Returns:
            DataFrame with results
        """
        try:
            start_time = time.perf_counter()
            logger.debug(f"Executing {query_name}")
            df = pd.read_sql(text(query), self.engine, params=params)
            elapsed = time.perf_counter() - start_time
            
            if DEBUG_QUERY_TIMING:
                print(f"   📊 SQL [{query_name}]: {elapsed:.3f}s → {len(df):,} rows")
            
            logger.debug(f"{query_name} returned {len(df)} rows in {elapsed:.3f}s")
            return df
        except Exception as e:
            logger.error(f"Error executing {query_name}: {e}")
            return pd.DataFrame()


# =============================================================================
# CACHED QUERY FUNCTIONS (Module-level for st.cache_data)
# =============================================================================

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def _get_sales_data_cached(
    start_date: date,
    end_date: date,
    employee_ids: tuple,
    entity_ids: tuple = None
) -> pd.DataFrame:
    """
    Cached version of sales data query.
    Note: Uses tuple for cache key compatibility.
    """
    start_time = time.perf_counter()
    engine = get_db_engine()
    
    query = """
        SELECT 
            data_source,
            unified_line_id,
            sales_id,
            sales_name,
            sales_email,
            employment_status,
            split_rate_percent,
            inv_date,
            inv_number,
            vat_number,
            legal_entity,
            legal_entity_id,
            customer,
            customer_id,
            customer_code,
            customer_type,
            customer_po_number,
            oc_number,
            oc_date,
            product_id,
            product_pn,
            pt_code,
            brand,
            sales_by_split_usd,
            gross_profit_by_split_usd,
            gp1_by_split_usd,
            allocated_broker_commission_usd,
            invoice_month,
            invoice_year
        FROM unified_sales_by_salesperson_view
        WHERE inv_date BETWEEN :start_date AND :end_date
          AND sales_id IN :employee_ids
    """
    
    params = {
        'start_date': start_date,
        'end_date': end_date,
        'employee_ids': employee_ids
    }
    
    if entity_ids:
        query += " AND legal_entity_id IN :entity_ids"
        params['entity_ids'] = entity_ids
    
    query += " ORDER BY inv_date DESC"
    
    try:
        df = pd.read_sql(text(query), engine, params=params)
        elapsed = time.perf_counter() - start_time
        if DEBUG_QUERY_TIMING:
            print(f"   📊 SQL [cached_sales_data]: {elapsed:.3f}s → {len(df):,} rows")
        return df
    except Exception as e:
        logger.error(f"Error in cached sales query: {e}")
        return pd.DataFrame()


# =============================================================================
# KPI TYPE WEIGHTS - CACHED (Module-level for performance)
# =============================================================================

# Fallback weights if database query fails
_FALLBACK_KPI_TYPE_WEIGHTS = {
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


def _get_fallback_kpi_weights() -> Dict[str, int]:
    """Return fallback KPI weights when database is unavailable."""
    logger.warning("Using fallback KPI type weights")
    return _FALLBACK_KPI_TYPE_WEIGHTS.copy()


@st.cache_data(ttl=3600)  # Cache for 1 hour (KPI types rarely change)
def get_kpi_type_weights_cached() -> Dict[str, int]:
    """
    Cached version of KPI type weights query.
    
    KPI types rarely change, so cache for 1 hour.
    This eliminates repeated database queries for the same data.
    
    Returns:
        Dict mapping kpi_name (lowercase) to default_weight
    """
    start_time = time.perf_counter()
    engine = get_db_engine()
    
    query = """
        SELECT 
            LOWER(name) as kpi_name,
            COALESCE(default_weight, 50) as default_weight
        FROM kpi_types
        WHERE delete_flag = 0
    """
    
    try:
        df = pd.read_sql(text(query), engine)
        elapsed = time.perf_counter() - start_time
        
        if DEBUG_QUERY_TIMING:
            print(f"   📊 SQL [kpi_type_weights]: {elapsed:.3f}s → {len(df):,} rows")
        
        if df.empty:
            logger.warning("No KPI types found in database, using fallback weights")
            return _get_fallback_kpi_weights()
        
        # Convert to dict
        weights = dict(zip(df['kpi_name'], df['default_weight'].astype(int)))
        logger.info(f"Loaded {len(weights)} KPI type weights from database (cached)")
        return weights
        
    except Exception as e:
        logger.error(f"Error loading KPI type weights: {e}")
        return _get_fallback_kpi_weights()