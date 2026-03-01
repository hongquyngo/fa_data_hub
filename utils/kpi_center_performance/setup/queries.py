# utils/kpi_center_performance/setup/queries.py
"""
SQL Queries for Setup Tab - KPI Center Performance

Full CRUD operations for:
- KPI Center Split Rules
- KPI Assignments
- Hierarchy Management
- Validation Dashboard


"""

import logging
from datetime import date, datetime
from typing import List, Optional, Dict, Tuple, Any
import pandas as pd
from sqlalchemy import text

from utils.db import get_db_engine

logger = logging.getLogger(__name__)


class SetupQueries:
    """
    Database queries for Setup tab functionality.
    
    Usage:
        from utils.kpi_center_performance.setup import SetupQueries
        
        setup_queries = SetupQueries()
        
        # Read
        split_df = setup_queries.get_kpi_split_data(kpi_center_ids=[1, 2, 3])
        
        # Create
        result = setup_queries.create_split_rule(
            customer_id=1, product_id=100, kpi_center_id=5,
            split_percentage=50, valid_from=date.today(), valid_to=date(2025,12,31)
        )
        
        # Update
        setup_queries.update_split_rule(rule_id=123, split_percentage=60)
        
        # Delete
        setup_queries.delete_split_rule(rule_id=123)
    """
    
    def __init__(self, user_id: str = None):
        """
        Initialize with database engine.
        
        Args:
            user_id: Current user UUID for audit trail
        """
        self._engine = None
        self.user_id = user_id
    
    @property
    def engine(self):
        """Lazy load database engine."""
        if self._engine is None:
            self._engine = get_db_engine()
        return self._engine
    
    # =========================================================================
    # KPI SPLIT RULES - READ
    # =========================================================================
    
    def get_kpi_split_data(
        self,
        # Entity filters
        kpi_center_ids: List[int] = None,
        customer_ids: List[int] = None,
        product_ids: List[int] = None,
        brand_ids: List[int] = None,
        kpi_type: str = None,
        
        # Period filters (v2.6.0)
        period_year: int = None,           # Filter by year (rules overlapping this year)
        period_start: date = None,         # Custom period start
        period_end: date = None,           # Custom period end
        
        # Rule attribute filters
        status_filter: str = None,         # 'ok', 'incomplete_split', 'over_100_split'
        approval_filter: str = None,       # 'approved', 'pending', 'all'
        split_min: float = None,           # Min split percentage
        split_max: float = None,           # Max split percentage
        
        # Audit filters (v2.6.0)
        created_by_user_id: int = None,    # Filter by creator
        approved_by_user_id: int = None,   # Filter by approver
        created_date_from: date = None,    # Created date range start
        created_date_to: date = None,      # Created date range end
        modified_date_from: date = None,   # Modified date range start
        modified_date_to: date = None,     # Modified date range end
        
        # System filters (v2.6.0 - replaces active_only)
        include_deleted: bool = False,     # Show deleted rules
        
        # Legacy support (deprecated)
        active_only: bool = None,          # DEPRECATED - use period filters instead
        expiring_days: int = None,         # Show rules expiring within N days
        
        # Pagination
        limit: int = None
    ) -> pd.DataFrame:
        """
        Get KPI Center split assignments with comprehensive filtering.
        
        v2.6.0 Changes:
        - Period filter uses OVERLAPPING logic: rule's [valid_from, valid_to] 
          overlaps with [period_start, period_end]
        - delete_flag = 0 by default (unless include_deleted=True)
        - Removed active_only logic (was confusing validity period with active status)
        - Added audit trail filters (created_by, approved_by, date ranges)
        
        Args:
            kpi_center_ids: Filter by KPI Center IDs
            customer_ids: Filter by Customer IDs
            product_ids: Filter by Product IDs
            brand_ids: Filter by Brand IDs
            kpi_type: Filter by KPI type (TERRITORY, VERTICAL, etc.)
            
            period_year: Filter rules overlapping this year
            period_start: Custom period start date
            period_end: Custom period end date
            
            status_filter: Filter by split status
            approval_filter: Filter by approval status
            split_min: Minimum split percentage
            split_max: Maximum split percentage
            
            created_by_user_id: Filter by creator user ID
            approved_by_user_id: Filter by approver user ID
            created_date_from: Filter created_date >= this
            created_date_to: Filter created_date <= this
            modified_date_from: Filter modified_date >= this
            modified_date_to: Filter modified_date <= this
            
            include_deleted: If True, show deleted rules too
            active_only: DEPRECATED - ignored, use period filters
            expiring_days: Show rules expiring within N days
            
            limit: Limit number of results
            
        Returns:
            DataFrame with split assignments
        """
        query = """
            SELECT 
                -- Primary ID
                kpi_center_split_id,
                
                -- KPI Center
                kpi_center_id,
                kpi_center_name,
                kpi_type,
                kpi_center_description,
                parent_center_id,
                
                -- Customer
                customer_id,
                company_code,
                customer_name,
                customer_display,
                
                -- Product
                product_id,
                pt_code,
                product_name,
                package_size,
                product_display,
                
                -- Brand
                brand_id,
                brand,
                
                -- Split
                split_percentage,
                split_percentage_display,
                
                -- Period
                effective_from,
                effective_to,
                effective_period,
                days_until_expiry,
                
                -- Approval
                is_approved,
                approval_status,
                
                -- Creator
                created_by_user_id,
                created_by_username,
                created_by_name,
                created_date,
                
                -- Approver
                approved_by_user_id,
                approved_by_username,
                approved_by_name,
                
                -- Modifier
                modified_by_user_id,
                modified_by_username,
                modified_by_name,
                modified_date,
                
                -- Version
                version,
                
                -- Validation
                total_split_percentage_by_type,
                kpi_split_status,
                existing_kpi_split_structure
                
            FROM kpi_center_split_looker_view
            WHERE 1=1
        """
        
        params = {}
        
        # =====================================================================
        # SYSTEM FILTER: delete_flag (v2.6.0)
        # =====================================================================
        if not include_deleted:
            query += " AND (delete_flag = 0 OR delete_flag IS NULL)"
        
        # =====================================================================
        # PERIOD FILTER - Overlapping logic (v2.6.0)
        # Rule overlaps period if: valid_from <= period_end AND valid_to >= period_start
        # =====================================================================
        if period_year:
            # Year filter: rules overlapping any part of the year
            query += """
                AND (effective_from <= :period_end OR effective_from IS NULL)
                AND (effective_to >= :period_start OR effective_to IS NULL)
            """
            params['period_start'] = date(period_year, 1, 1)
            params['period_end'] = date(period_year, 12, 31)
        elif period_start or period_end:
            # Custom date range
            if period_start:
                query += " AND (effective_to >= :period_start OR effective_to IS NULL)"
                params['period_start'] = period_start
            if period_end:
                query += " AND (effective_from <= :period_end OR effective_from IS NULL)"
                params['period_end'] = period_end
        
        # Legacy: expiring_days filter (still supported)
        if expiring_days:
            query += " AND effective_to BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL :expiring_days DAY)"
            params['expiring_days'] = expiring_days
        
        # =====================================================================
        # ENTITY FILTERS
        # =====================================================================
        if kpi_center_ids:
            query += " AND kpi_center_id IN :kpi_center_ids"
            params['kpi_center_ids'] = tuple(kpi_center_ids)
        
        if customer_ids:
            query += " AND customer_id IN :customer_ids"
            params['customer_ids'] = tuple(customer_ids)
        
        if product_ids:
            query += " AND product_id IN :product_ids"
            params['product_ids'] = tuple(product_ids)
        
        if brand_ids:
            query += """ AND product_id IN (
                SELECT id FROM products WHERE brand_id IN :brand_ids AND delete_flag = 0
            )"""
            params['brand_ids'] = tuple(brand_ids)
        
        if kpi_type:
            query += " AND kpi_type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        # =====================================================================
        # RULE ATTRIBUTE FILTERS
        # =====================================================================
        if status_filter and status_filter != 'all':
            query += " AND kpi_split_status = :status_filter"
            params['status_filter'] = status_filter
        
        if approval_filter == 'approved':
            query += " AND is_approved = 1"
        elif approval_filter == 'pending':
            query += " AND (is_approved = 0 OR is_approved IS NULL)"
        
        if split_min is not None:
            query += " AND split_percentage >= :split_min"
            params['split_min'] = split_min
        
        if split_max is not None:
            query += " AND split_percentage <= :split_max"
            params['split_max'] = split_max
        
        # =====================================================================
        # AUDIT FILTERS (v2.6.0)
        # =====================================================================
        if created_by_user_id:
            query += " AND created_by_user_id = :created_by_user_id"
            params['created_by_user_id'] = created_by_user_id
        
        if approved_by_user_id:
            query += " AND approved_by_user_id = :approved_by_user_id"
            params['approved_by_user_id'] = approved_by_user_id
        
        if created_date_from:
            query += " AND created_date >= :created_date_from"
            params['created_date_from'] = created_date_from
        
        if created_date_to:
            query += " AND created_date <= :created_date_to"
            params['created_date_to'] = created_date_to
        
        if modified_date_from:
            query += " AND modified_date >= :modified_date_from"
            params['modified_date_from'] = modified_date_from
        
        if modified_date_to:
            query += " AND modified_date <= :modified_date_to"
            params['modified_date_to'] = modified_date_to
        
        # =====================================================================
        # ORDERING & LIMIT
        # =====================================================================
        query += " ORDER BY kpi_center_name, customer_name, product_name"
        
        if limit:
            query += f" LIMIT {limit}"
        
        return self._execute_query(query, params, "kpi_split_data")
    
    def get_split_summary_stats(
        self,
        period_year: int = None,
        period_start: date = None,
        period_end: date = None,
        include_deleted: bool = False
    ) -> Dict:
        """
        Get summary statistics for split rules with period filter.
        
        v2.6.0: Added period filter to sync with comprehensive filters.
        
        Args:
            period_year: Filter by year (rules overlapping this year)
            period_start: Custom period start
            period_end: Custom period end
            include_deleted: Include deleted rules in stats
            
        Returns:
            Dict with counts: total, ok, incomplete, over_100, pending, expiring_soon
        """
        query = """
            SELECT 
                COUNT(*) as total_rules,
                SUM(CASE WHEN kpi_split_status = 'ok' THEN 1 ELSE 0 END) as ok_count,
                SUM(CASE WHEN kpi_split_status = 'incomplete_split' THEN 1 ELSE 0 END) as incomplete_count,
                SUM(CASE WHEN kpi_split_status = 'over_100_split' THEN 1 ELSE 0 END) as over_100_count,
                SUM(CASE WHEN is_approved = 0 OR is_approved IS NULL THEN 1 ELSE 0 END) as pending_count,
                SUM(CASE 
                    WHEN effective_to BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY) 
                    THEN 1 ELSE 0 
                END) as expiring_soon_count
            FROM kpi_center_split_looker_view
            WHERE 1=1
        """
        
        params = {}
        
        # Delete flag filter
        if not include_deleted:
            query += " AND (delete_flag = 0 OR delete_flag IS NULL)"
        
        # Period filter (overlapping logic)
        if period_year:
            query += """
                AND (effective_from <= :period_end OR effective_from IS NULL)
                AND (effective_to >= :period_start OR effective_to IS NULL)
            """
            params['period_start'] = date(period_year, 1, 1)
            params['period_end'] = date(period_year, 12, 31)
        elif period_start or period_end:
            if period_start:
                query += " AND (effective_to >= :period_start OR effective_to IS NULL)"
                params['period_start'] = period_start
            if period_end:
                query += " AND (effective_from <= :period_end OR effective_from IS NULL)"
                params['period_end'] = period_end
        
        df = self._execute_query(query, params, "split_summary_stats")
        
        if df.empty:
            return {
                'total_rules': 0,
                'ok_count': 0,
                'incomplete_count': 0,
                'over_100_count': 0,
                'pending_count': 0,
                'expiring_soon_count': 0
            }
        
        row = df.iloc[0]
        return {
            'total_rules': int(row.get('total_rules', 0) or 0),
            'ok_count': int(row.get('ok_count', 0) or 0),
            'incomplete_count': int(row.get('incomplete_count', 0) or 0),
            'over_100_count': int(row.get('over_100_count', 0) or 0),
            'pending_count': int(row.get('pending_count', 0) or 0),
            'expiring_soon_count': int(row.get('expiring_soon_count', 0) or 0)
        }
    
    def get_split_issues_detail(
        self,
        issue_type: str = 'over_100',
        limit: int = 50
    ) -> pd.DataFrame:
        """
        Get detailed list of split issues for display in issues panel.
        
        Args:
            issue_type: 'over_100' or 'incomplete'
            limit: Maximum number of records to return
            
        Returns:
            DataFrame with customer, product, kpi_type, total_split grouped
        """
        if issue_type == 'over_100':
            status_filter = 'over_100_split'
        else:
            status_filter = 'incomplete_split'
        
        query = f"""
            SELECT 
                customer_id,
                customer_display,
                product_id,
                product_display,
                kpi_type,
                SUM(split_percentage) as total_split,
                COUNT(*) as rule_count
            FROM kpi_center_split_looker_view
            WHERE kpi_split_status = :status_filter
              AND (effective_to >= CURDATE() OR effective_to IS NULL)
            GROUP BY customer_id, customer_display, product_id, product_display, kpi_type
            ORDER BY total_split DESC
            LIMIT {limit}
        """
        
        return self._execute_query(query, {'status_filter': status_filter}, f"split_issues_{issue_type}")
    
    def get_assignment_issues_summary(self, year: int) -> Dict:
        """
        Get assignment issues summary for display in issues panel.
        
        Args:
            year: Year to check
            
        Returns:
            Dict with no_assignment_count, weight_issues_count, and details
        """
        result = {
            'no_assignment_count': 0,
            'no_assignment_details': [],
            'weight_issues_count': 0,
            'weight_issues_details': []
        }
        
        # Centers with splits but no assignments
        no_assign_query = """
            SELECT kc.id, kc.name, kc.type
            FROM kpi_centers kc
            WHERE kc.delete_flag = 0
              AND kc.id NOT IN (
                  SELECT DISTINCT kpi_center_id 
                  FROM sales_kpi_center_assignments 
                  WHERE year = :year AND delete_flag = 0
              )
              AND kc.id IN (
                  SELECT DISTINCT kpi_center_id 
                  FROM kpi_center_split_by_customer_product 
                  WHERE delete_flag = 0 AND (valid_to >= CURDATE() OR valid_to IS NULL)
              )
            ORDER BY kc.type, kc.name
        """
        no_assign_df = self._execute_query(no_assign_query, {'year': year}, "centers_without_assignment")
        
        if not no_assign_df.empty:
            result['no_assignment_count'] = len(no_assign_df)
            result['no_assignment_details'] = no_assign_df.to_dict('records')
        
        # Weight issues
        weight_query = """
            SELECT 
                kpi_center_id,
                kpi_center_name,
                SUM(weight_numeric) as total_weight
            FROM sales_kpi_center_assignments_view
            WHERE year = :year
            GROUP BY kpi_center_id, kpi_center_name
            HAVING total_weight != 100
            ORDER BY kpi_center_name
        """
        weight_df = self._execute_query(weight_query, {'year': year}, "weight_issues")
        
        if not weight_df.empty:
            result['weight_issues_count'] = len(weight_df)
            result['weight_issues_details'] = weight_df.to_dict('records')
        
        return result
    
    def get_assignment_issues_summary_v2(self, year: int) -> Dict:
        """
        Enhanced assignment issues summary with leaf/parent distinction.
        
        NEW v2.4.0: Distinguishes between:
        - Leaf centers without assignments (CRITICAL - needs direct assignment)
        - Parent centers with children coverage (INFO - shows rollup from children)
        - Parent centers without any coverage (WARNING - no assignments anywhere in subtree)
        
        REFACTORED v2.4.1: Use same pattern as KPI & Targets tab:
        - get_all_descendants() for recursive traversal
        - Python processing for logic
        
        Args:
            year: Year to check
            
        Returns:
            Dict with:
            - leaf_missing_count, leaf_missing_details: Leaf centers needing assignment
            - parent_with_rollup_count, parent_with_rollup_details: Parents with children assignments
            - parent_no_coverage_count, parent_no_coverage_details: Parents with no coverage at all
            - weight_issues_count, weight_issues_details: Weight sum != 100%
        """
        result = {
            # Leaf centers without direct assignment (CRITICAL)
            'leaf_missing_count': 0,
            'leaf_missing_details': [],
            
            # Parent centers with rollup from children (INFO)
            'parent_with_rollup_count': 0,
            'parent_with_rollup_details': [],
            
            # Parent centers with no coverage anywhere (WARNING)
            'parent_no_coverage_count': 0,
            'parent_no_coverage_details': [],
            
            # Weight issues (same as before)
            'weight_issues_count': 0,
            'weight_issues_details': [],
            
            # Legacy compatibility
            'no_assignment_count': 0,
            'no_assignment_details': []
        }
        
        # =====================================================================
        # STEP 1: Get all centers without direct assignments that are RELEVANT
        # A center is relevant if:
        # - It has direct splits, OR
        # - Any of its descendants has splits (parent of active centers)
        # =====================================================================
        centers_query = """
            WITH RECURSIVE 
            -- All centers with active splits
            centers_with_splits AS (
                SELECT DISTINCT kpi_center_id
                FROM kpi_center_split_by_customer_product 
                WHERE delete_flag = 0 AND (valid_to >= CURDATE() OR valid_to IS NULL)
            ),
            
            -- Get all ancestors of centers with splits (parents should be included too)
            ancestors AS (
                -- Base: centers with splits
                SELECT id as kpi_center_id, id as original_id
                FROM kpi_centers
                WHERE id IN (SELECT kpi_center_id FROM centers_with_splits)
                  AND delete_flag = 0
                
                UNION
                
                -- Recursive: parents of those centers
                SELECT kc.parent_center_id as kpi_center_id, a.original_id
                FROM kpi_centers kc
                INNER JOIN ancestors a ON kc.id = a.kpi_center_id
                WHERE kc.parent_center_id IS NOT NULL
                  AND kc.delete_flag = 0
            ),
            
            -- All relevant centers (have splits OR are ancestors of centers with splits)
            relevant_centers AS (
                SELECT DISTINCT kpi_center_id FROM ancestors
            ),
            
            -- Children count for is_leaf detection
            children_count AS (
                SELECT parent_center_id, COUNT(*) as child_count
                FROM kpi_centers
                WHERE delete_flag = 0 AND parent_center_id IS NOT NULL
                GROUP BY parent_center_id
            )
            
            SELECT 
                kc.id,
                kc.name,
                kc.type,
                COALESCE(cc.child_count, 0) as children_count,
                CASE WHEN COALESCE(cc.child_count, 0) = 0 THEN 1 ELSE 0 END as is_leaf,
                CASE WHEN cws.kpi_center_id IS NOT NULL THEN 1 ELSE 0 END as has_direct_splits
            FROM kpi_centers kc
            INNER JOIN relevant_centers rc ON kc.id = rc.kpi_center_id
            LEFT JOIN children_count cc ON kc.id = cc.parent_center_id
            LEFT JOIN centers_with_splits cws ON kc.id = cws.kpi_center_id
            WHERE kc.delete_flag = 0
              -- No direct assignment for this year
              AND kc.id NOT IN (
                  SELECT DISTINCT kpi_center_id 
                  FROM sales_kpi_center_assignments 
                  WHERE year = :year AND delete_flag = 0
              )
            ORDER BY 
                CASE WHEN COALESCE(cc.child_count, 0) = 0 THEN 0 ELSE 1 END,  -- Leaves first
                kc.type, 
                kc.name
        """
        
        centers_df = self._execute_query(centers_query, {'year': year}, "centers_without_direct")
        
        if centers_df.empty:
            # No issues with missing assignments
            pass
        else:
            # =====================================================================
            # STEP 2: Get all assignments for this year (for checking descendants)
            # =====================================================================
            assignments_query = """
                SELECT DISTINCT kpi_center_id, kc.name as kpi_center_name
                FROM sales_kpi_center_assignments ska
                INNER JOIN kpi_centers kc ON ska.kpi_center_id = kc.id
                WHERE ska.year = :year 
                  AND ska.delete_flag = 0
                  AND kc.delete_flag = 0
            """
            assignments_df = self._execute_query(assignments_query, {'year': year}, "year_assignments")
            centers_with_assignments = set(assignments_df['kpi_center_id'].tolist()) if not assignments_df.empty else set()
            
            # Build lookup for center names with assignments
            assignment_names_lookup = {}
            if not assignments_df.empty:
                for _, row in assignments_df.iterrows():
                    assignment_names_lookup[row['kpi_center_id']] = row['kpi_center_name']
            
            # =====================================================================
            # STEP 3: Process each center - check if descendants have assignments
            # =====================================================================
            for _, row in centers_df.iterrows():
                center_id = row['id']
                is_leaf = row['is_leaf'] == 1
                
                center_info = {
                    'id': center_id,
                    'name': row['name'],
                    'type': row['type'],
                    'is_leaf': is_leaf,
                    'children_count': int(row['children_count']),
                    'descendants_with_assignments': 0,
                    'descendant_names': None
                }
                
                if is_leaf:
                    # Leaf without assignment - CRITICAL
                    result['leaf_missing_details'].append(center_info)
                else:
                    # Parent - check descendants using helper method
                    # (Same pattern as KPI & Targets tab: queries.get_all_descendants)
                    descendants = self.get_all_descendants(center_id)
                    
                    # Find which descendants have assignments
                    descendants_with_assign = [d for d in descendants if d in centers_with_assignments]
                    
                    if descendants_with_assign:
                        # Has rollup from children - INFO
                        center_info['descendants_with_assignments'] = len(descendants_with_assign)
                        center_info['descendant_names'] = ', '.join([
                            assignment_names_lookup.get(d, str(d)) 
                            for d in descendants_with_assign[:10]  # Limit for display
                        ])
                        if len(descendants_with_assign) > 10:
                            center_info['descendant_names'] += f' +{len(descendants_with_assign) - 10} more'
                        
                        result['parent_with_rollup_details'].append(center_info)
                    else:
                        # No coverage anywhere in subtree - WARNING
                        result['parent_no_coverage_details'].append(center_info)
            
            result['leaf_missing_count'] = len(result['leaf_missing_details'])
            result['parent_with_rollup_count'] = len(result['parent_with_rollup_details'])
            result['parent_no_coverage_count'] = len(result['parent_no_coverage_details'])
            
            # Legacy compatibility
            result['no_assignment_count'] = result['leaf_missing_count'] + result['parent_no_coverage_count']
            result['no_assignment_details'] = result['leaf_missing_details'] + result['parent_no_coverage_details']
        
        # =====================================================================
        # STEP 4: Weight issues (same logic as before)
        # =====================================================================
        weight_query = """
            SELECT 
                kpi_center_id,
                kpi_center_name,
                SUM(weight_numeric) as total_weight
            FROM sales_kpi_center_assignments_view
            WHERE year = :year
            GROUP BY kpi_center_id, kpi_center_name
            HAVING total_weight != 100
            ORDER BY kpi_center_name
        """
        weight_df = self._execute_query(weight_query, {'year': year}, "weight_issues")
        
        if not weight_df.empty:
            result['weight_issues_count'] = len(weight_df)
            result['weight_issues_details'] = weight_df.to_dict('records')
        
        return result
    
    def get_rollup_targets_for_center(self, kpi_center_id: int, year: int) -> Dict:
        """
        Get aggregated (rollup) KPI targets from all descendants.
        
        NEW v2.4.0: For displaying rollup targets in Setup tab.
        
        Args:
            kpi_center_id: Parent KPI Center ID
            year: Year to get targets for
            
        Returns:
            Dict with:
            - has_rollup: bool
            - targets: List of {kpi_name, annual_target, monthly_target, unit, source_count}
            - source_centers: List of center names contributing
            - total_source_count: Total number of centers contributing
        """
        query = """
            WITH RECURSIVE descendants AS (
                -- Get all descendants (excluding self)
                SELECT id as kpi_center_id
                FROM kpi_centers
                WHERE parent_center_id = :center_id
                  AND delete_flag = 0
                
                UNION ALL
                
                SELECT kc.id
                FROM kpi_centers kc
                INNER JOIN descendants d ON kc.parent_center_id = d.kpi_center_id
                WHERE kc.delete_flag = 0
            )
            SELECT 
                kt.name as kpi_name,
                kt.uom as unit_of_measure,
                SUM(ska.annual_target_value) as annual_target,
                COUNT(DISTINCT ska.kpi_center_id) as source_count,
                GROUP_CONCAT(DISTINCT kc.name ORDER BY kc.name SEPARATOR ', ') as source_centers
            FROM descendants d
            INNER JOIN sales_kpi_center_assignments ska 
                ON d.kpi_center_id = ska.kpi_center_id
                AND ska.year = :year
                AND ska.delete_flag = 0
            INNER JOIN kpi_types kt ON ska.kpi_type_id = kt.id
            INNER JOIN kpi_centers kc ON ska.kpi_center_id = kc.id
            GROUP BY kt.id, kt.name, kt.uom
            ORDER BY kt.name
        """
        
        df = self._execute_query(query, {
            'center_id': kpi_center_id,
            'year': year
        }, "rollup_targets")
        
        if df.empty:
            return {
                'has_rollup': False,
                'targets': [],
                'source_centers': [],
                'total_source_count': 0
            }
        
        targets = []
        all_sources = set()
        
        for _, row in df.iterrows():
            annual = float(row['annual_target']) if row['annual_target'] else 0
            targets.append({
                'kpi_name': row['kpi_name'],
                'annual_target': annual,
                'monthly_target': annual / 12,
                'quarterly_target': annual / 4,
                'unit_of_measure': row['unit_of_measure'],
                'source_count': int(row['source_count']),
                'is_currency': row['unit_of_measure'] == 'USD'
            })
            
            if row['source_centers']:
                all_sources.update(row['source_centers'].split(', '))
        
        return {
            'has_rollup': True,
            'targets': targets,
            'source_centers': sorted(list(all_sources)),
            'total_source_count': len(all_sources)
        }
    
    def get_split_by_customer_product(
        self,
        customer_id: int,
        product_id: int,
        kpi_type: str = None,
        exclude_rule_id: int = None
    ) -> pd.DataFrame:
        """
        Get all split rules for a specific customer-product combination.
        Used to show current splits when adding/editing.
        
        Args:
            customer_id: Customer ID
            product_id: Product ID
            kpi_type: Optional KPI type filter
            exclude_rule_id: Rule ID to exclude (when editing)
            
        Returns:
            DataFrame with all splits for this combo
        """
        query = """
            SELECT 
                kpi_center_split_id,
                kpi_center_id,
                kpi_center_name,
                kpi_type,
                split_percentage,
                effective_from,
                effective_to,
                is_approved,
                approval_status
            FROM kpi_center_split_looker_view
            WHERE customer_id = :customer_id
              AND product_id = :product_id
              AND (effective_to >= CURDATE() OR effective_to IS NULL)
        """
        
        params = {
            'customer_id': customer_id,
            'product_id': product_id
        }
        
        if kpi_type:
            query += " AND kpi_type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        if exclude_rule_id:
            query += " AND kpi_center_split_id != :exclude_rule_id"
            params['exclude_rule_id'] = exclude_rule_id
        
        query += " ORDER BY kpi_type, kpi_center_name"
        
        return self._execute_query(query, params, "split_by_customer_product")
    
    def validate_split_percentage(
        self,
        customer_id: int,
        product_id: int,
        kpi_type: str,
        new_percentage: float,
        exclude_rule_id: int = None
    ) -> Dict:
        """
        Validate if adding/updating a split percentage is valid.
        
        Args:
            customer_id: Customer ID
            product_id: Product ID
            kpi_type: KPI type
            new_percentage: New percentage to add/update
            exclude_rule_id: Rule ID to exclude (when editing)
            
        Returns:
            Dict with 'valid': bool, 'current_total', 'new_total', 'message'
        """
        # Get current splits for this combo
        existing_df = self.get_split_by_customer_product(
            customer_id=customer_id,
            product_id=product_id,
            kpi_type=kpi_type,
            exclude_rule_id=exclude_rule_id
        )
        
        current_total = existing_df['split_percentage'].sum() if not existing_df.empty else 0
        new_total = current_total + new_percentage
        
        if new_total > 100:
            return {
                'valid': False,
                'current_total': current_total,
                'new_total': new_total,
                'remaining': 100 - current_total,
                'message': f"Adding {new_percentage}% will result in {new_total}% (over 100% limit)"
            }
        elif new_total == 100:
            return {
                'valid': True,
                'current_total': current_total,
                'new_total': new_total,
                'remaining': 0,
                'message': f"Total will be exactly 100% ✓"
            }
        else:
            return {
                'valid': True,
                'current_total': current_total,
                'new_total': new_total,
                'remaining': 100 - new_total,
                'message': f"Total will be {new_total}% ({100 - new_total}% remaining)"
            }
    
    # =========================================================================
    # PHASE 1: PERIOD VALIDATION (v2.8.0)
    # =========================================================================
    
    def validate_period(
        self,
        valid_from: date,
        valid_to: date
    ) -> Dict:
        """
        Validate validity period dates.
        
        v2.8.0: NEW - Sync with Salesperson Performance.
        
        Rules:
        - valid_from is required
        - valid_to is required (KPI Center requires end date)
        - valid_from must be before valid_to
        - Warning if valid_from is in the past
        - Warning if period spans > 3 years
        
        Args:
            valid_from: Start date
            valid_to: End date
            
        Returns:
            Dict with is_valid, errors[], warnings[]
        """
        errors = []
        warnings = []
        
        # Required checks
        if valid_from is None:
            errors.append("Valid From date is required")
        
        if valid_to is None:
            errors.append("Valid To date is required")
        
        # Date order check
        if valid_from is not None and valid_to is not None:
            if valid_from > valid_to:
                errors.append(f"Valid From ({valid_from}) must be before Valid To ({valid_to})")
        
        # Warning for past start date
        if valid_from is not None and valid_from < date.today():
            warnings.append(f"Valid From ({valid_from}) is in the past")
        
        # Warning for very long periods (> 3 years)
        if valid_from is not None and valid_to is not None:
            days_diff = (valid_to - valid_from).days
            if days_diff > 365 * 3:
                years = days_diff / 365
                warnings.append(f"Period spans {years:.1f} years (> 3 years)")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    def check_period_overlap(
        self,
        customer_id: int,
        product_id: int,
        kpi_center_id: int,
        valid_from: date,
        valid_to: date,
        exclude_rule_id: int = None
    ) -> Dict:
        """
        Check if new period overlaps with existing rules for same customer/product/kpi_center.
        
        v2.8.0: NEW - Sync with Salesperson Performance.
        
        Overlap logic:
        - Two periods [A_start, A_end] and [B_start, B_end] overlap if:
          A_start <= B_end AND A_end >= B_start
        
        This check is for the SAME kpi_center only.
        Different kpi_centers can have overlapping periods (cross-center is allowed).
        
        Args:
            customer_id: Customer ID
            product_id: Product ID
            kpi_center_id: KPI Center ID
            valid_from: New rule's start date
            valid_to: New rule's end date
            exclude_rule_id: Rule ID to exclude (for edit mode)
            
        Returns:
            Dict with has_overlap, overlapping_rules[], overlap_count, message
        """
        query = """
            SELECT 
                ks.id as rule_id,
                ks.split_percentage,
                ks.valid_from,
                ks.valid_to,
                CONCAT(
                    DATE_FORMAT(ks.valid_from, '%Y-%m-%d'),
                    ' → ',
                    COALESCE(DATE_FORMAT(ks.valid_to, '%Y-%m-%d'), 'No End')
                ) as period_display,
                kc.name as kpi_center_name
            FROM kpi_center_split_by_customer_product ks
            JOIN kpi_centers kc ON ks.kpi_center_id = kc.id
            WHERE ks.customer_id = :customer_id
              AND ks.product_id = :product_id
              AND ks.kpi_center_id = :kpi_center_id
              AND (ks.delete_flag = 0 OR ks.delete_flag IS NULL)
        """
        
        params = {
            'customer_id': customer_id,
            'product_id': product_id,
            'kpi_center_id': kpi_center_id
        }
        
        if exclude_rule_id:
            query += " AND ks.id != :exclude_rule_id"
            params['exclude_rule_id'] = exclude_rule_id
        
        # Overlap condition: new_start <= existing_end AND new_end >= existing_start
        if valid_to is not None:
            query += """
                AND (ks.valid_from <= :new_end OR ks.valid_from IS NULL)
                AND (ks.valid_to >= :new_start OR ks.valid_to IS NULL)
            """
            params['new_start'] = valid_from
            params['new_end'] = valid_to
        else:
            # New rule has no end date - overlaps with anything that hasn't ended
            query += " AND (ks.valid_to >= :new_start OR ks.valid_to IS NULL)"
            params['new_start'] = valid_from
        
        query += " ORDER BY ks.valid_from"
        
        df = self._execute_query(query, params, "check_period_overlap")
        
        if df.empty:
            return {
                'has_overlap': False,
                'overlapping_rules': [],
                'overlap_count': 0,
                'message': 'No overlapping rules found'
            }
        
        overlapping = df.to_dict('records')
        
        return {
            'has_overlap': True,
            'overlapping_rules': overlapping,
            'overlap_count': len(overlapping),
            'message': f"Found {len(overlapping)} overlapping rule(s) for same KPI Center"
        }
    
    # =========================================================================
    # PHASE 2: ENHANCED VALIDATION (v2.8.1)
    # =========================================================================
    
    def validate_bulk_split_impact(
        self,
        rule_ids: List[int],
        new_split_percentage: float
    ) -> Dict:
        """
        Preview impact of bulk split percentage change before applying.
        
        v2.8.1: NEW - Sync with Salesperson Performance.
        
        Groups rules by customer/product/kpi_type combo and calculates
        what the new totals would be after the change.
        
        Args:
            rule_ids: List of rule IDs to update
            new_split_percentage: New split percentage to set
            
        Returns:
            Dict with can_proceed, will_be_ok, will_be_under, will_be_over, details[]
        """
        if not rule_ids:
            return {
                'can_proceed': False,
                'will_be_ok': 0,
                'will_be_under': 0,
                'will_be_over': 0,
                'details': [],
                'message': 'No rules selected'
            }
        
        # Get current state of selected rules and their combos
        query = """
            WITH selected_rules AS (
                SELECT 
                    ks.id as rule_id,
                    ks.customer_id,
                    ks.product_id,
                    kc.type as kpi_type,
                    ks.split_percentage as current_split,
                    c.english_name as customer_name,
                    p.name as product_name
                FROM kpi_center_split_by_customer_product ks
                JOIN kpi_centers kc ON ks.kpi_center_id = kc.id
                JOIN companies c ON ks.customer_id = c.id
                JOIN products p ON ks.product_id = p.id
                WHERE ks.id IN :rule_ids
                  AND (ks.delete_flag = 0 OR ks.delete_flag IS NULL)
            ),
            combo_totals AS (
                SELECT 
                    ks.customer_id,
                    ks.product_id,
                    kc.type as kpi_type,
                    SUM(ks.split_percentage) as total_split,
                    SUM(CASE WHEN ks.id IN :rule_ids THEN ks.split_percentage ELSE 0 END) as selected_split,
                    COUNT(CASE WHEN ks.id IN :rule_ids THEN 1 END) as selected_count
                FROM kpi_center_split_by_customer_product ks
                JOIN kpi_centers kc ON ks.kpi_center_id = kc.id
                WHERE (ks.delete_flag = 0 OR ks.delete_flag IS NULL)
                  AND (ks.valid_to >= CURDATE() OR ks.valid_to IS NULL)
                  AND EXISTS (
                      SELECT 1 FROM selected_rules sr 
                      WHERE sr.customer_id = ks.customer_id 
                        AND sr.product_id = ks.product_id
                        AND sr.kpi_type = kc.type
                  )
                GROUP BY ks.customer_id, ks.product_id, kc.type
            )
            SELECT 
                ct.customer_id,
                ct.product_id,
                ct.kpi_type,
                ct.total_split as current_total,
                ct.selected_split,
                ct.selected_count,
                (ct.total_split - ct.selected_split + (ct.selected_count * :new_percentage)) as new_total,
                c.english_name as customer_name,
                p.name as product_name
            FROM combo_totals ct
            JOIN companies c ON ct.customer_id = c.id
            JOIN products p ON ct.product_id = p.id
            ORDER BY ct.kpi_type, customer_name, product_name
        """
        
        params = {
            'rule_ids': tuple(rule_ids),
            'new_percentage': new_split_percentage
        }
        
        df = self._execute_query(query, params, "validate_bulk_split_impact")
        
        if df.empty:
            return {
                'can_proceed': True,
                'will_be_ok': 0,
                'will_be_under': 0,
                'will_be_over': 0,
                'details': [],
                'message': 'No affected combos found'
            }
        
        # Analyze results
        details = []
        will_be_ok = 0
        will_be_under = 0
        will_be_over = 0
        
        for _, row in df.iterrows():
            new_total = float(row['new_total'])
            current_total = float(row['current_total'])
            
            if new_total == 100:
                status = 'ok'
                will_be_ok += 1
            elif new_total < 100:
                status = 'under'
                will_be_under += 1
            else:
                status = 'over'
                will_be_over += 1
            
            details.append({
                'customer_id': int(row['customer_id']),
                'product_id': int(row['product_id']),
                'kpi_type': row['kpi_type'],
                'customer_name': row['customer_name'],
                'product_name': row['product_name'],
                'current_total': current_total,
                'new_total': new_total,
                'selected_count': int(row['selected_count']),
                'status': status
            })
        
        can_proceed = (will_be_over == 0)
        
        return {
            'can_proceed': can_proceed,
            'will_be_ok': will_be_ok,
            'will_be_under': will_be_under,
            'will_be_over': will_be_over,
            'total_combos': len(details),
            'details': details,
            'message': f"OK: {will_be_ok}, Under: {will_be_under}, Over: {will_be_over}" + 
                       ("" if can_proceed else " - BLOCKED due to over-allocation")
        }
    
    def validate_bulk_period_impact(
        self,
        rule_ids: List[int],
        valid_from: date,
        valid_to: date
    ) -> Dict:
        """
        Preview impact of bulk period update - check for overlaps.
        
        v2.8.2: NEW - Sync with Salesperson Performance.
        
        Business Rules:
        - Period errors (from > to): BLOCK
        - Period overlaps (same kpi_center): BLOCK
        - Period warnings (past date, long period): WARNING only
        
        Args:
            rule_ids: List of rule IDs to update
            valid_from: New valid_from date
            valid_to: New valid_to date
            
        Returns:
            Dict with:
            - total_rules: Number of rules being updated
            - period_errors: List of period validation errors
            - period_warnings: List of period warnings
            - overlap_warnings: List of overlap details
            - overlap_count: Number of rules with overlaps
            - can_proceed: Whether update can proceed
        """
        if not rule_ids:
            return {
                'total_rules': 0,
                'period_errors': [],
                'period_warnings': [],
                'overlap_warnings': [],
                'overlap_count': 0,
                'can_proceed': True
            }
        
        # Basic period validation
        period_validation = self.validate_period(valid_from, valid_to)
        
        if not period_validation['is_valid']:
            return {
                'total_rules': len(rule_ids),
                'period_errors': period_validation['errors'],
                'period_warnings': [],
                'overlap_warnings': [],
                'overlap_count': 0,
                'can_proceed': False
            }
        
        # Get rules info for overlap checking
        query = """
            SELECT 
                ks.id AS rule_id,
                ks.customer_id,
                ks.product_id,
                ks.kpi_center_id,
                kc.name AS kpi_center_name,
                kc.type AS kpi_type,
                c.english_name AS customer_name,
                p.name AS product_name
            FROM kpi_center_split_by_customer_product ks
            JOIN kpi_centers kc ON ks.kpi_center_id = kc.id
            JOIN companies c ON ks.customer_id = c.id
            JOIN products p ON ks.product_id = p.id
            WHERE ks.id IN :rule_ids
              AND (ks.delete_flag = 0 OR ks.delete_flag IS NULL)
        """
        
        params = {'rule_ids': tuple(rule_ids)}
        rules_df = self._execute_query(query, params, "bulk_period_rules")
        
        if rules_df.empty:
            return {
                'total_rules': 0,
                'period_errors': [],
                'period_warnings': period_validation.get('warnings', []),
                'overlap_warnings': [],
                'overlap_count': 0,
                'can_proceed': True
            }
        
        overlap_warnings = []
        
        for _, rule in rules_df.iterrows():
            # Check overlap for each rule
            overlap_check = self.check_period_overlap(
                customer_id=int(rule['customer_id']),
                product_id=int(rule['product_id']),
                kpi_center_id=int(rule['kpi_center_id']),
                valid_from=valid_from,
                valid_to=valid_to,
                exclude_rule_id=int(rule['rule_id'])
            )
            
            if overlap_check['has_overlap']:
                overlap_warnings.append({
                    'rule_id': int(rule['rule_id']),
                    'kpi_center_name': rule['kpi_center_name'],
                    'kpi_type': rule['kpi_type'],
                    'customer_name': rule['customer_name'],
                    'product_name': rule['product_name'],
                    'overlap_count': overlap_check['overlap_count'],
                    'overlapping_rules': overlap_check['overlapping_rules'],
                    'message': overlap_check['message']
                })
        
        # Block if any overlaps (pre-validation business rule)
        can_proceed = len(period_validation['errors']) == 0 and len(overlap_warnings) == 0
        
        return {
            'total_rules': len(rules_df),
            'period_errors': period_validation['errors'],
            'period_warnings': period_validation.get('warnings', []),
            'overlap_warnings': overlap_warnings,
            'overlap_count': len(overlap_warnings),
            'can_proceed': can_proceed,
            'message': f"OK" if can_proceed else f"BLOCKED: {len(overlap_warnings)} overlap(s) found"
        }
    
    def get_kpi_combo_split_structure(
        self,
        customer_id: int,
        product_id: int,
        kpi_type: str = None,
        exclude_rule_id: int = None,
        include_expired: bool = False
    ) -> pd.DataFrame:
        """
        Get detailed split structure for a customer/product combo.
        
        v2.8.1: NEW - For Edit dialog to show current allocations.
        
        Args:
            customer_id: Customer ID
            product_id: Product ID
            kpi_type: Optional filter by kpi_centers.type
            exclude_rule_id: Rule ID to exclude (current rule being edited)
            include_expired: Whether to include expired rules
            
        Returns:
            DataFrame with rule details by KPI Center
        """
        query = """
            SELECT 
                ks.id AS rule_id,
                ks.kpi_center_id,
                kc.name AS kpi_center_name,
                kc.type AS kpi_type,
                ks.split_percentage,
                ks.valid_from,
                ks.valid_to,
                CONCAT(
                    DATE_FORMAT(ks.valid_from, '%Y-%m-%d'),
                    ' → ',
                    COALESCE(DATE_FORMAT(ks.valid_to, '%Y-%m-%d'), 'No End')
                ) AS period_display,
                CASE 
                    WHEN (ks.valid_from <= CURDATE() OR ks.valid_from IS NULL)
                         AND (ks.valid_to >= CURDATE() OR ks.valid_to IS NULL)
                    THEN 1 ELSE 0 
                END AS is_current_period,
                COALESCE(ks.isApproved, 0) AS is_approved,
                CASE WHEN ks.isApproved = 1 THEN 'Approved' ELSE 'Pending' END AS approval_status,
                DATEDIFF(ks.valid_to, CURDATE()) AS days_until_expiry,
                CASE 
                    WHEN ks.valid_to < CURDATE() THEN 'expired'
                    WHEN DATEDIFF(ks.valid_to, CURDATE()) <= 7 THEN 'critical'
                    WHEN DATEDIFF(ks.valid_to, CURDATE()) <= 30 THEN 'warning'
                    WHEN ks.valid_to IS NULL THEN 'no_end'
                    ELSE 'ok'
                END AS period_status,
                ks.created_date,
                ks.modified_date
            FROM kpi_center_split_by_customer_product ks
            JOIN kpi_centers kc ON ks.kpi_center_id = kc.id
            WHERE ks.customer_id = :customer_id
              AND ks.product_id = :product_id
              AND (ks.delete_flag = 0 OR ks.delete_flag IS NULL)
        """
        
        params = {
            'customer_id': customer_id,
            'product_id': product_id
        }
        
        if kpi_type:
            query += " AND kc.type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        if exclude_rule_id:
            query += " AND ks.id != :exclude_rule_id"
            params['exclude_rule_id'] = exclude_rule_id
        
        if not include_expired:
            query += " AND (ks.valid_to >= CURDATE() OR ks.valid_to IS NULL)"
        
        query += " ORDER BY kc.type, ks.split_percentage DESC, kc.name"
        
        return self._execute_query(query, params, "kpi_combo_split_structure")
    
    def get_kpi_combo_summary(
        self,
        customer_id: int,
        product_id: int,
        kpi_type: str = None,
        exclude_rule_id: int = None
    ) -> Dict:
        """
        Get quick summary stats for a customer/product combo.
        
        v2.8.1: NEW - Lightweight method for validation display.
        
        Args:
            customer_id: Customer ID
            product_id: Product ID
            kpi_type: Optional filter by kpi_centers.type
            exclude_rule_id: Rule ID to exclude
            
        Returns:
            Dict with total_split, rule_count, approved_split, pending_split
        """
        query = """
            SELECT 
                COALESCE(SUM(ks.split_percentage), 0) AS total_split,
                COUNT(*) AS rule_count,
                SUM(CASE WHEN ks.isApproved = 1 THEN ks.split_percentage ELSE 0 END) AS approved_split,
                SUM(CASE WHEN ks.isApproved = 0 OR ks.isApproved IS NULL THEN ks.split_percentage ELSE 0 END) AS pending_split
            FROM kpi_center_split_by_customer_product ks
            JOIN kpi_centers kc ON ks.kpi_center_id = kc.id
            WHERE ks.customer_id = :customer_id
              AND ks.product_id = :product_id
              AND (ks.delete_flag = 0 OR ks.delete_flag IS NULL)
              AND (ks.valid_to >= CURDATE() OR ks.valid_to IS NULL)
        """
        
        params = {
            'customer_id': customer_id,
            'product_id': product_id
        }
        
        if kpi_type:
            query += " AND kc.type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        if exclude_rule_id:
            query += " AND ks.id != :exclude_rule_id"
            params['exclude_rule_id'] = exclude_rule_id
        
        df = self._execute_query(query, params, "kpi_combo_summary")
        
        if df.empty:
            return {
                'total_split': 0,
                'rule_count': 0,
                'approved_split': 0,
                'pending_split': 0
            }
        
        row = df.iloc[0]
        return {
            'total_split': float(row.get('total_split', 0) or 0),
            'rule_count': int(row.get('rule_count', 0) or 0),
            'approved_split': float(row.get('approved_split', 0) or 0),
            'pending_split': float(row.get('pending_split', 0) or 0)
        }
    
    # =========================================================================
    # KPI SPLIT RULES - CREATE
    # =========================================================================
    
    def create_split_rule(
        self,
        customer_id: int,
        product_id: int,
        kpi_center_id: int,
        split_percentage: float,
        valid_from: date,
        valid_to: date,
        is_approved: bool = False,
        approved_by: int = None
    ) -> Dict:
        """
        Create a new split rule.
        
        Args:
            customer_id: Customer ID
            product_id: Product ID
            kpi_center_id: KPI Center ID
            split_percentage: Split percentage (0-100)
            valid_from: Start date
            valid_to: End date
            is_approved: Whether rule is approved
            approved_by: User ID who approved (FK -> users.id)
            
        Returns:
            Dict with 'success': bool, 'id': int, 'message': str
            
        Note:
            - created_by: uses self.user_id (FK -> users.id)
            - approved_by: users.id (not employees.id)
        """
        query = """
            INSERT INTO kpi_center_split_by_customer_product (
                customer_id, product_id, kpi_center_id, split_percentage,
                valid_from, valid_to, isApproved, approved_by,
                created_date, modified_date, created_by, modified_by, delete_flag, version
            ) VALUES (
                :customer_id, :product_id, :kpi_center_id, :split_percentage,
                :valid_from, :valid_to, :is_approved, :approved_by,
                NOW(), NOW(), :created_by, :created_by, 0, 0
            )
        """
        
        params = {
            'customer_id': customer_id,
            'product_id': product_id,
            'kpi_center_id': kpi_center_id,
            'split_percentage': split_percentage,
            'valid_from': valid_from,
            'valid_to': valid_to,
            'is_approved': 1 if is_approved else 0,
            'approved_by': approved_by,
            'created_by': self.user_id  # Should be users.id (INT)
        }
        
        return self._execute_insert(query, params, "create_split_rule")
    
    # =========================================================================
    # KPI SPLIT RULES - UPDATE
    # =========================================================================
    
    def update_split_rule(
        self,
        rule_id: int,
        split_percentage: float = None,
        valid_from: date = None,
        valid_to: date = None,
        kpi_center_id: int = None
    ) -> Dict:
        """
        Update an existing split rule.
        
        Args:
            rule_id: Split rule ID
            split_percentage: New split percentage
            valid_from: New start date
            valid_to: New end date
            kpi_center_id: New KPI Center ID
            
        Returns:
            Dict with 'success': bool, 'message': str
            
        Note:
            - modified_by: uses self.user_id (FK -> users.id)
        """
        updates = []
        params = {'rule_id': rule_id, 'modified_by': self.user_id}
        
        if split_percentage is not None:
            updates.append("split_percentage = :split_percentage")
            params['split_percentage'] = split_percentage
        
        if valid_from is not None:
            updates.append("valid_from = :valid_from")
            params['valid_from'] = valid_from
        
        if valid_to is not None:
            updates.append("valid_to = :valid_to")
            params['valid_to'] = valid_to
        
        if kpi_center_id is not None:
            updates.append("kpi_center_id = :kpi_center_id")
            params['kpi_center_id'] = kpi_center_id
        
        if not updates:
            return {'success': False, 'message': 'No fields to update'}
        
        updates.append("modified_date = NOW()")
        updates.append("modified_by = :modified_by")
        updates.append("version = version + 1")
        
        query = f"""
            UPDATE kpi_center_split_by_customer_product
            SET {', '.join(updates)}
            WHERE id = :rule_id AND delete_flag = 0
        """
        
        return self._execute_update(query, params, "update_split_rule")
    
    def approve_split_rules(self, rule_ids: List[int], approved_by: int) -> Dict:
        """
        Approve multiple split rules.
        
        Args:
            rule_ids: List of rule IDs to approve
            approved_by: User ID who approved (FK -> users.id)
            
        Returns:
            Dict with 'success': bool, 'count': int, 'message': str
        """
        if not rule_ids:
            return {'success': False, 'count': 0, 'message': 'No rules to approve'}
        
        query = """
            UPDATE kpi_center_split_by_customer_product
            SET isApproved = 1,
                approved_by = :approved_by,
                modified_by = :approved_by,
                modified_date = NOW(),
                version = version + 1
            WHERE id IN :rule_ids AND delete_flag = 0
        """
        
        params = {
            'rule_ids': tuple(rule_ids),
            'approved_by': approved_by
        }
        
        return self._execute_update(query, params, "approve_split_rules")
    
    def bulk_disapprove_split_rules(self, rule_ids: List[int], modified_by: int = None) -> Dict:
        """
        Bulk disapprove (reset to pending) multiple split rules.
        
        v2.7.0: NEW - Sync with Salesperson Performance.
        
        Args:
            rule_ids: List of rule IDs to disapprove
            modified_by: User ID who made the change (FK -> users.id)
            
        Returns:
            Dict with 'success': bool, 'count': int, 'message': str
        """
        if not rule_ids:
            return {'success': False, 'count': 0, 'message': 'No rules to disapprove'}
        
        query = """
            UPDATE kpi_center_split_by_customer_product
            SET isApproved = 0,
                approved_by = NULL,
                modified_by = :modified_by,
                modified_date = NOW(),
                version = version + 1
            WHERE id IN :rule_ids 
              AND (delete_flag = 0 OR delete_flag IS NULL)
        """
        
        params = {
            'rule_ids': tuple(rule_ids),
            'modified_by': modified_by or self.user_id
        }
        
        return self._execute_update(query, params, f"bulk_disapprove_{len(rule_ids)}_rules")
    
    def bulk_update_split_period(
        self,
        rule_ids: List[int],
        valid_from: date = None,
        valid_to: date = None,
        modified_by: int = None
    ) -> Dict:
        """
        Bulk update validity period for multiple split rules.
        
        v2.7.0: NEW - Sync with Salesperson Performance.
        
        Args:
            rule_ids: List of rule IDs to update
            valid_from: New start date (optional)
            valid_to: New end date (optional)
            modified_by: User ID who made the change (FK -> users.id)
            
        Returns:
            Dict with 'success': bool, 'count': int, 'message': str
        """
        if not rule_ids:
            return {'success': False, 'count': 0, 'message': 'No rules to update'}
        
        if valid_from is None and valid_to is None:
            return {'success': False, 'count': 0, 'message': 'At least one date must be provided'}
        
        set_parts = [
            "modified_by = :modified_by",
            "modified_date = NOW()",
            "version = version + 1"
        ]
        params = {
            'rule_ids': tuple(rule_ids),
            'modified_by': modified_by or self.user_id
        }
        
        if valid_from is not None:
            set_parts.append("valid_from = :valid_from")
            params['valid_from'] = valid_from
        
        if valid_to is not None:
            set_parts.append("valid_to = :valid_to")
            params['valid_to'] = valid_to
        
        query = f"""
            UPDATE kpi_center_split_by_customer_product
            SET {', '.join(set_parts)}
            WHERE id IN :rule_ids 
              AND (delete_flag = 0 OR delete_flag IS NULL)
        """
        
        return self._execute_update(query, params, f"bulk_update_period_{len(rule_ids)}_rules")
    
    def bulk_update_split_percentage(
        self,
        rule_ids: List[int],
        split_percentage: float,
        modified_by: int = None
    ) -> Dict:
        """
        Bulk update split percentage for multiple rules.
        
        v2.7.0: NEW - Sync with Salesperson Performance.
        
        WARNING: This sets the SAME percentage for all rules.
        Use with caution - typically for resetting or adjusting en masse.
        
        Args:
            rule_ids: List of rule IDs to update
            split_percentage: New split percentage (0-100)
            modified_by: User ID who made the change (FK -> users.id)
            
        Returns:
            Dict with 'success': bool, 'count': int, 'message': str
        """
        if not rule_ids:
            return {'success': False, 'count': 0, 'message': 'No rules to update'}
        
        if split_percentage < 0 or split_percentage > 100:
            return {'success': False, 'count': 0, 'message': 'Split percentage must be between 0 and 100'}
        
        query = """
            UPDATE kpi_center_split_by_customer_product
            SET split_percentage = :split_percentage,
                modified_by = :modified_by,
                modified_date = NOW(),
                version = version + 1
            WHERE id IN :rule_ids 
              AND (delete_flag = 0 OR delete_flag IS NULL)
        """
        
        params = {
            'rule_ids': tuple(rule_ids),
            'split_percentage': split_percentage,
            'modified_by': modified_by or self.user_id
        }
        
        return self._execute_update(query, params, f"bulk_update_split_{len(rule_ids)}_rules")
    
    # =========================================================================
    # KPI SPLIT RULES - COPY TO NEW PERIOD (v2.11.0)
    # =========================================================================
    
    def validate_copy_to_period(
        self,
        rule_ids: List[int],
        new_valid_from: date,
        new_valid_to: date
    ) -> Dict:
        """
        Validate copy to new period operation before execution.
        
        v2.11.0: NEW - Pre-validation for copy operation.
        
        Checks:
        1. Period validity (from < to)
        2. Period overlap with existing rules (same customer/product/kpi_center)
        3. Split % total after copy (will it exceed 100%?)
        
        Args:
            rule_ids: List of rule IDs to copy
            new_valid_from: New period start date
            new_valid_to: New period end date
            
        Returns:
            Dict with:
            - can_proceed: bool
            - period_errors: List of period validation errors
            - period_warnings: List of period warnings
            - overlap_count: Number of rules with overlaps
            - overlap_details: List of overlap details
            - split_warnings: List of split % warnings (will exceed 100%)
        """
        if not rule_ids:
            return {
                'can_proceed': True,
                'total_rules': 0,
                'period_errors': [],
                'period_warnings': [],
                'overlap_count': 0,
                'overlap_details': [],
                'split_warnings': []
            }
        
        # 1. Basic period validation
        period_validation = self.validate_period(new_valid_from, new_valid_to)
        
        if not period_validation['is_valid']:
            return {
                'can_proceed': False,
                'total_rules': len(rule_ids),
                'period_errors': period_validation['errors'],
                'period_warnings': [],
                'overlap_count': 0,
                'overlap_details': [],
                'split_warnings': []
            }
        
        # 2. Get source rules info
        query = """
            SELECT 
                ks.id AS rule_id,
                ks.customer_id,
                ks.product_id,
                ks.kpi_center_id,
                ks.split_percentage,
                kc.name AS kpi_center_name,
                kc.type AS kpi_type,
                c.english_name AS customer_name,
                p.name AS product_name
            FROM kpi_center_split_by_customer_product ks
            JOIN kpi_centers kc ON ks.kpi_center_id = kc.id
            JOIN companies c ON ks.customer_id = c.id
            JOIN products p ON ks.product_id = p.id
            WHERE ks.id IN :rule_ids
              AND (ks.delete_flag = 0 OR ks.delete_flag IS NULL)
        """
        
        rules_df = self._execute_query(query, {'rule_ids': tuple(rule_ids)}, "copy_source_rules")
        
        if rules_df.empty:
            return {
                'can_proceed': False,
                'total_rules': 0,
                'period_errors': ['No valid rules found to copy'],
                'period_warnings': [],
                'overlap_count': 0,
                'overlap_details': [],
                'split_warnings': []
            }
        
        overlap_details = []
        split_warnings = []
        
        # 3. Check each rule for overlaps and split % impact
        for _, rule in rules_df.iterrows():
            customer_id = int(rule['customer_id'])
            product_id = int(rule['product_id'])
            kpi_center_id = int(rule['kpi_center_id'])
            split_pct = float(rule['split_percentage'])
            
            # Check period overlap (for the NEW copy, not excluding any rule)
            overlap_check = self.check_period_overlap(
                customer_id=customer_id,
                product_id=product_id,
                kpi_center_id=kpi_center_id,
                valid_from=new_valid_from,
                valid_to=new_valid_to,
                exclude_rule_id=None  # Don't exclude - we're creating NEW
            )
            
            if overlap_check['has_overlap']:
                overlap_details.append({
                    'rule_id': int(rule['rule_id']),
                    'kpi_center_name': rule['kpi_center_name'],
                    'kpi_type': rule['kpi_type'],
                    'customer_name': rule['customer_name'],
                    'product_name': rule['product_name'],
                    'overlap_count': overlap_check['overlap_count'],
                    'message': overlap_check['message']
                })
            
            # Check split % impact for new period
            # Get existing splits for the new period
            existing_query = """
                SELECT COALESCE(SUM(split_percentage), 0) AS total_split
                FROM kpi_center_split_by_customer_product ks
                JOIN kpi_centers kc ON ks.kpi_center_id = kc.id
                WHERE ks.customer_id = :customer_id
                  AND ks.product_id = :product_id
                  AND kc.type = :kpi_type
                  AND (ks.delete_flag = 0 OR ks.delete_flag IS NULL)
                  AND (ks.valid_from <= :valid_to OR ks.valid_from IS NULL)
                  AND (ks.valid_to >= :valid_from OR ks.valid_to IS NULL)
            """
            
            existing_df = self._execute_query(existing_query, {
                'customer_id': customer_id,
                'product_id': product_id,
                'kpi_type': rule['kpi_type'],
                'valid_from': new_valid_from,
                'valid_to': new_valid_to
            }, "existing_split_check")
            
            current_total = float(existing_df.iloc[0]['total_split']) if not existing_df.empty else 0
            new_total = current_total + split_pct
            
            if new_total > 100:
                split_warnings.append({
                    'rule_id': int(rule['rule_id']),
                    'kpi_center_name': rule['kpi_center_name'],
                    'kpi_type': rule['kpi_type'],
                    'customer_name': rule['customer_name'],
                    'product_name': rule['product_name'],
                    'current_total': current_total,
                    'add_pct': split_pct,
                    'new_total': new_total,
                    'message': f"Will exceed 100% ({new_total:.0f}%)"
                })
        
        # Overlaps are blocking, split warnings are not
        can_proceed = len(period_validation['errors']) == 0 and len(overlap_details) == 0
        
        return {
            'can_proceed': can_proceed,
            'total_rules': len(rules_df),
            'period_errors': period_validation['errors'],
            'period_warnings': period_validation.get('warnings', []),
            'overlap_count': len(overlap_details),
            'overlap_details': overlap_details,
            'split_warnings': split_warnings,
            'message': 'OK' if can_proceed else f"BLOCKED: {len(overlap_details)} overlap(s) found"
        }
    
    def copy_split_rules_to_period(
        self,
        rule_ids: List[int],
        new_valid_from: date,
        new_valid_to: date,
        copy_approval_status: bool = False,
        created_by: int = None
    ) -> Dict:
        """
        Copy split rules to a new validity period.
        
        v2.11.0: NEW - Copy existing rules to new period.
        
        Creates NEW records with same customer/product/kpi_center/split_percentage
        but different validity period.
        
        Args:
            rule_ids: List of rule IDs to copy
            new_valid_from: New period start date
            new_valid_to: New period end date
            copy_approval_status: If True, copy isApproved status. If False, set to pending.
            created_by: User ID who created the copies (FK -> users.id)
            
        Returns:
            Dict with:
            - success: bool
            - copied_count: Number of rules copied
            - new_rule_ids: List of new rule IDs
            - skipped_count: Number of rules skipped (due to errors)
            - message: Status message
        """
        if not rule_ids:
            return {
                'success': False,
                'copied_count': 0,
                'new_rule_ids': [],
                'skipped_count': 0,
                'message': 'No rules to copy'
            }
        
        # Get source rules
        query = """
            SELECT 
                id,
                customer_id,
                product_id,
                kpi_center_id,
                split_percentage,
                salesperson_id,
                isApproved,
                approved_by
            FROM kpi_center_split_by_customer_product
            WHERE id IN :rule_ids
              AND (delete_flag = 0 OR delete_flag IS NULL)
        """
        
        source_df = self._execute_query(query, {'rule_ids': tuple(rule_ids)}, "copy_source_rules")
        
        if source_df.empty:
            return {
                'success': False,
                'copied_count': 0,
                'new_rule_ids': [],
                'skipped_count': len(rule_ids),
                'message': 'No valid source rules found'
            }
        
        new_rule_ids = []
        skipped_count = 0
        user_id = created_by or self.user_id
        
        # Insert each rule
        for _, rule in source_df.iterrows():
            try:
                # Determine approval status
                if copy_approval_status:
                    is_approved = 1 if rule['isApproved'] else 0
                    approved_by = rule['approved_by'] if rule['isApproved'] else None
                else:
                    is_approved = 0
                    approved_by = None
                
                insert_query = """
                    INSERT INTO kpi_center_split_by_customer_product (
                        customer_id, product_id, kpi_center_id, split_percentage,
                        salesperson_id, valid_from, valid_to,
                        isApproved, approved_by,
                        created_date, modified_date, created_by, modified_by,
                        delete_flag, version
                    ) VALUES (
                        :customer_id, :product_id, :kpi_center_id, :split_percentage,
                        :salesperson_id, :valid_from, :valid_to,
                        :is_approved, :approved_by,
                        NOW(), NOW(), :created_by, :created_by,
                        0, 0
                    )
                """
                
                params = {
                    'customer_id': int(rule['customer_id']),
                    'product_id': int(rule['product_id']),
                    'kpi_center_id': int(rule['kpi_center_id']),
                    'split_percentage': float(rule['split_percentage']),
                    'salesperson_id': int(rule['salesperson_id']) if rule['salesperson_id'] else None,
                    'valid_from': new_valid_from,
                    'valid_to': new_valid_to,
                    'is_approved': is_approved,
                    'approved_by': approved_by,
                    'created_by': user_id
                }
                
                result = self._execute_insert(insert_query, params, f"copy_rule_{rule['id']}")
                
                if result['success'] and result['id']:
                    new_rule_ids.append(result['id'])
                else:
                    skipped_count += 1
                    logger.warning(f"Failed to copy rule {rule['id']}: {result.get('message')}")
                    
            except Exception as e:
                skipped_count += 1
                logger.error(f"Error copying rule {rule['id']}: {e}")
        
        copied_count = len(new_rule_ids)
        success = copied_count > 0
        
        return {
            'success': success,
            'copied_count': copied_count,
            'new_rule_ids': new_rule_ids,
            'skipped_count': skipped_count,
            'message': f"Copied {copied_count} rules" + (f", {skipped_count} skipped" if skipped_count else "")
        }
    
    # =========================================================================
    # KPI SPLIT RULES - DELETE
    # =========================================================================
    
    def delete_split_rule(self, rule_id: int) -> Dict:
        """
        Soft delete a split rule.
        
        Args:
            rule_id: Split rule ID
            
        Returns:
            Dict with 'success': bool, 'message': str
        """
        query = """
            UPDATE kpi_center_split_by_customer_product
            SET delete_flag = 1,
                modified_date = NOW(),
                version = version + 1
            WHERE id = :rule_id
        """
        
        return self._execute_update(query, {'rule_id': rule_id}, "delete_split_rule")
    
    def delete_split_rules_bulk(self, rule_ids: List[int]) -> Dict:
        """
        Bulk soft delete split rules.
        
        Args:
            rule_ids: List of rule IDs to delete
            
        Returns:
            Dict with 'success': bool, 'count': int, 'message': str
        """
        if not rule_ids:
            return {'success': False, 'count': 0, 'message': 'No rules to delete'}
        
        query = """
            UPDATE kpi_center_split_by_customer_product
            SET delete_flag = 1,
                modified_date = NOW(),
                version = version + 1
            WHERE id IN :rule_ids
        """
        
        return self._execute_update(query, {'rule_ids': tuple(rule_ids)}, "delete_split_rules_bulk")
    
    # =========================================================================
    # KPI SPLIT RULES - BULK OPERATIONS
    # =========================================================================
    
    def duplicate_split_rule(
        self,
        rule_id: int,
        new_valid_from: date,
        new_valid_to: date
    ) -> Dict:
        """
        Duplicate a split rule with new validity period.
        
        Args:
            rule_id: Source rule ID
            new_valid_from: New start date
            new_valid_to: New end date
            
        Returns:
            Dict with 'success': bool, 'id': int, 'message': str
        """
        query = """
            INSERT INTO kpi_center_split_by_customer_product (
                customer_id, product_id, kpi_center_id, split_percentage,
                valid_from, valid_to, isApproved, approved_by,
                created_date, modified_date, created_by, delete_flag, version
            )
            SELECT 
                customer_id, product_id, kpi_center_id, split_percentage,
                :new_valid_from, :new_valid_to, 0, NULL,
                NOW(), NOW(), :created_by, 0, 0
            FROM kpi_center_split_by_customer_product
            WHERE id = :rule_id AND delete_flag = 0
        """
        
        params = {
            'rule_id': rule_id,
            'new_valid_from': new_valid_from,
            'new_valid_to': new_valid_to,
            'created_by': self.user_id
        }
        
        return self._execute_insert(query, params, "duplicate_split_rule")
    
    def copy_splits_to_period(
        self,
        rule_ids: List[int],
        new_valid_from: date,
        new_valid_to: date
    ) -> Dict:
        """
        Copy multiple split rules to a new period.
        
        Args:
            rule_ids: List of source rule IDs
            new_valid_from: New start date
            new_valid_to: New end date
            
        Returns:
            Dict with 'success': bool, 'count': int, 'message': str
        """
        if not rule_ids:
            return {'success': False, 'count': 0, 'message': 'No rules to copy'}
        
        query = """
            INSERT INTO kpi_center_split_by_customer_product (
                customer_id, product_id, kpi_center_id, split_percentage,
                valid_from, valid_to, isApproved, approved_by,
                created_date, modified_date, created_by, delete_flag, version
            )
            SELECT 
                customer_id, product_id, kpi_center_id, split_percentage,
                :new_valid_from, :new_valid_to, 0, NULL,
                NOW(), NOW(), :created_by, 0, 0
            FROM kpi_center_split_by_customer_product
            WHERE id IN :rule_ids AND delete_flag = 0
        """
        
        params = {
            'rule_ids': tuple(rule_ids),
            'new_valid_from': new_valid_from,
            'new_valid_to': new_valid_to,
            'created_by': self.user_id
        }
        
        return self._execute_insert(query, params, "copy_splits_to_period")
    
    # =========================================================================
    # KPI CENTER HIERARCHY - READ
    # =========================================================================
    
    def get_kpi_center_hierarchy(
        self,
        kpi_type: str = None,
        include_stats: bool = True
    ) -> pd.DataFrame:
        """
        Get KPI Center hierarchy with parent-child relationships.
        
        Args:
            kpi_type: Filter by KPI type
            include_stats: Include statistics (split count, assignment count)
            
        Returns:
            DataFrame with hierarchy data
        """
        if include_stats:
            query = """
                WITH RECURSIVE kpi_hierarchy AS (
                    -- Base case: root KPI centers (no parent)
                    SELECT 
                        id AS kpi_center_id,
                        name AS kpi_center_name,
                        type AS kpi_type,
                        description,
                        parent_center_id,
                        0 AS level
                    FROM kpi_centers
                    WHERE parent_center_id IS NULL
                      AND delete_flag = 0
                    
                    UNION ALL
                    
                    -- Recursive case: child KPI centers
                    SELECT 
                        kc.id,
                        kc.name,
                        kc.type,
                        kc.description,
                        kc.parent_center_id,
                        kh.level + 1
                    FROM kpi_centers kc
                    INNER JOIN kpi_hierarchy kh ON kc.parent_center_id = kh.kpi_center_id
                    WHERE kc.delete_flag = 0
                ),
                split_counts AS (
                    SELECT 
                        kpi_center_id,
                        COUNT(*) as split_count
                    FROM kpi_center_split_looker_view
                    WHERE effective_to >= CURDATE() OR effective_to IS NULL
                    GROUP BY kpi_center_id
                ),
                assignment_counts AS (
                    SELECT 
                        kpi_center_id,
                        COUNT(*) as assignment_count,
                        MAX(year) as latest_year
                    FROM sales_kpi_center_assignments_view
                    GROUP BY kpi_center_id
                ),
                children_count AS (
                    SELECT 
                        parent_center_id,
                        COUNT(*) as child_count
                    FROM kpi_centers
                    WHERE delete_flag = 0 AND parent_center_id IS NOT NULL
                    GROUP BY parent_center_id
                )
                SELECT 
                    h.kpi_center_id,
                    h.kpi_center_name,
                    h.kpi_type,
                    h.description,
                    h.parent_center_id,
                    h.level,
                    CASE WHEN cc.child_count IS NULL OR cc.child_count = 0 THEN 1 ELSE 0 END as is_leaf,
                    COALESCE(cc.child_count, 0) as children_count,
                    COALESCE(sc.split_count, 0) as split_count,
                    COALESCE(ac.assignment_count, 0) as assignment_count,
                    ac.latest_year
                FROM kpi_hierarchy h
                LEFT JOIN children_count cc ON h.kpi_center_id = cc.parent_center_id
                LEFT JOIN split_counts sc ON h.kpi_center_id = sc.kpi_center_id
                LEFT JOIN assignment_counts ac ON h.kpi_center_id = ac.kpi_center_id
                WHERE 1=1
            """
        else:
            query = """
                WITH RECURSIVE kpi_hierarchy AS (
                    SELECT 
                        id AS kpi_center_id,
                        name AS kpi_center_name,
                        type AS kpi_type,
                        description,
                        parent_center_id,
                        0 AS level
                    FROM kpi_centers
                    WHERE parent_center_id IS NULL
                      AND delete_flag = 0
                    
                    UNION ALL
                    
                    SELECT 
                        kc.id,
                        kc.name,
                        kc.type,
                        kc.description,
                        kc.parent_center_id,
                        kh.level + 1
                    FROM kpi_centers kc
                    INNER JOIN kpi_hierarchy kh ON kc.parent_center_id = kh.kpi_center_id
                    WHERE kc.delete_flag = 0
                ),
                children_count AS (
                    SELECT 
                        parent_center_id,
                        COUNT(*) as child_count
                    FROM kpi_centers
                    WHERE delete_flag = 0 AND parent_center_id IS NOT NULL
                    GROUP BY parent_center_id
                )
                SELECT 
                    h.kpi_center_id,
                    h.kpi_center_name,
                    h.kpi_type,
                    h.description,
                    h.parent_center_id,
                    h.level,
                    CASE WHEN cc.child_count IS NULL OR cc.child_count = 0 THEN 1 ELSE 0 END as is_leaf,
                    COALESCE(cc.child_count, 0) as children_count
                FROM kpi_hierarchy h
                LEFT JOIN children_count cc ON h.kpi_center_id = cc.parent_center_id
                WHERE 1=1
            """
        
        params = {}
        
        if kpi_type:
            query += " AND h.kpi_type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        query += " ORDER BY h.kpi_type, h.level, h.kpi_center_name"
        
        return self._execute_query(query, params, "kpi_center_hierarchy")
    
    def get_all_descendants(
        self,
        kpi_center_id: int,
        include_self: bool = False
    ) -> List[int]:
        """
        Get all descendant KPI Center IDs for a given parent.
        
        NEW v2.4.1: Synced with KPI & Targets tab logic.
        
        Args:
            kpi_center_id: Parent KPI Center ID
            include_self: Whether to include the parent ID in results
            
        Returns:
            List of descendant kpi_center_ids
        """
        query = """
            WITH RECURSIVE descendants AS (
                -- Base case: direct children
                SELECT id as kpi_center_id
                FROM kpi_centers
                WHERE parent_center_id = :parent_id
                  AND delete_flag = 0
                
                UNION ALL
                
                -- Recursive case: children of children
                SELECT kc.id
                FROM kpi_centers kc
                INNER JOIN descendants d ON kc.parent_center_id = d.kpi_center_id
                WHERE kc.delete_flag = 0
            )
            SELECT kpi_center_id FROM descendants
        """
        
        df = self._execute_query(query, {'parent_id': kpi_center_id}, "all_descendants")
        
        result = df['kpi_center_id'].tolist() if not df.empty else []
        
        if include_self:
            result = [kpi_center_id] + result
        
        return result
    
    def get_leaf_descendants(
        self,
        kpi_center_id: int
    ) -> List[int]:
        """
        Get only leaf (no children) descendants for a KPI Center.
        
        NEW v2.4.1: For rollup calculations - only aggregate from leaves.
        
        Args:
            kpi_center_id: Parent KPI Center ID
            
        Returns:
            List of leaf descendant kpi_center_ids
        """
        query = """
            WITH RECURSIVE descendants AS (
                SELECT id as kpi_center_id
                FROM kpi_centers
                WHERE parent_center_id = :parent_id
                  AND delete_flag = 0
                
                UNION ALL
                
                SELECT kc.id
                FROM kpi_centers kc
                INNER JOIN descendants d ON kc.parent_center_id = d.kpi_center_id
                WHERE kc.delete_flag = 0
            ),
            children_count AS (
                SELECT parent_center_id, COUNT(*) as cnt
                FROM kpi_centers
                WHERE delete_flag = 0 AND parent_center_id IS NOT NULL
                GROUP BY parent_center_id
            )
            SELECT d.kpi_center_id
            FROM descendants d
            LEFT JOIN children_count cc ON d.kpi_center_id = cc.parent_center_id
            WHERE cc.cnt IS NULL OR cc.cnt = 0
        """
        
        df = self._execute_query(query, {'parent_id': kpi_center_id}, "leaf_descendants")
        
        return df['kpi_center_id'].tolist() if not df.empty else []
    
    def get_center_info(self, kpi_center_id: int) -> Dict:
        """
        Get basic info for a KPI Center (name, type, is_leaf, children_count).
        
        NEW v2.4.1: Helper for issues summary.
        """
        query = """
            SELECT 
                kc.id,
                kc.name,
                kc.type,
                COALESCE(cc.child_count, 0) as children_count,
                CASE WHEN COALESCE(cc.child_count, 0) = 0 THEN 1 ELSE 0 END as is_leaf
            FROM kpi_centers kc
            LEFT JOIN (
                SELECT parent_center_id, COUNT(*) as child_count
                FROM kpi_centers
                WHERE delete_flag = 0 AND parent_center_id IS NOT NULL
                GROUP BY parent_center_id
            ) cc ON kc.id = cc.parent_center_id
            WHERE kc.id = :kpi_center_id AND kc.delete_flag = 0
        """
        
        df = self._execute_query(query, {'kpi_center_id': kpi_center_id}, "center_info")
        
        if df.empty:
            return None
        
        row = df.iloc[0]
        return {
            'id': row['id'],
            'name': row['name'],
            'type': row['type'],
            'children_count': int(row['children_count']),
            'is_leaf': row['is_leaf'] == 1
        }
    
    def get_kpi_center_detail(self, kpi_center_id: int) -> Dict:
        """
        Get detailed information about a KPI Center.
        
        Args:
            kpi_center_id: KPI Center ID
            
        Returns:
            Dict with center details, stats, and recent activity
        """
        # Basic info
        info_query = """
            SELECT 
                kc.id as kpi_center_id,
                kc.name as kpi_center_name,
                kc.description,
                kc.type as kpi_type,
                kc.parent_center_id,
                p.name as parent_name,
                kc.created_date,
                kc.modified_date
            FROM kpi_centers kc
            LEFT JOIN kpi_centers p ON kc.parent_center_id = p.id
            WHERE kc.id = :kpi_center_id AND kc.delete_flag = 0
        """
        
        info_df = self._execute_query(info_query, {'kpi_center_id': kpi_center_id}, "kpi_center_detail_info")
        
        if info_df.empty:
            return None
        
        info = info_df.iloc[0].to_dict()
        
        # Stats
        stats_query = """
            SELECT 
                (SELECT COUNT(*) FROM kpi_center_split_by_customer_product 
                 WHERE kpi_center_id = :kpi_center_id AND delete_flag = 0
                   AND (valid_to >= CURDATE() OR valid_to IS NULL)) as active_splits,
                (SELECT COUNT(*) FROM sales_kpi_center_assignments 
                 WHERE kpi_center_id = :kpi_center_id AND delete_flag = 0
                   AND year = YEAR(CURDATE())) as current_year_assignments,
                (SELECT COUNT(*) FROM kpi_centers 
                 WHERE parent_center_id = :kpi_center_id AND delete_flag = 0) as children_count
        """
        
        stats_df = self._execute_query(stats_query, {'kpi_center_id': kpi_center_id}, "kpi_center_detail_stats")
        
        if not stats_df.empty:
            info.update(stats_df.iloc[0].to_dict())
        
        return info
    
    def get_kpi_centers_for_dropdown(
        self,
        kpi_type: str = None,
        exclude_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get KPI Centers for dropdown selection.
        
        Args:
            kpi_type: Filter by type
            exclude_ids: IDs to exclude
            
        Returns:
            DataFrame with id, name, type for dropdown options
        """
        query = """
            SELECT 
                id AS kpi_center_id,
                name AS kpi_center_name,
                type AS kpi_type,
                parent_center_id
            FROM kpi_centers
            WHERE delete_flag = 0
        """
        
        params = {}
        
        if kpi_type:
            query += " AND type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        if exclude_ids:
            query += " AND id NOT IN :exclude_ids"
            params['exclude_ids'] = tuple(exclude_ids)
        
        query += " ORDER BY type, name"
        
        return self._execute_query(query, params, "kpi_centers_dropdown")
    
    # =========================================================================
    # KPI CENTER HIERARCHY - CREATE/UPDATE/DELETE
    # =========================================================================
    
    def create_kpi_center(
        self,
        name: str,
        kpi_type: str,
        description: str = None,
        parent_center_id: int = None
    ) -> Dict:
        """
        Create a new KPI Center.
        
        Args:
            name: Center name
            kpi_type: Type (TERRITORY, VERTICAL, BRAND, INTERNAL)
            description: Optional description
            parent_center_id: Parent center ID (null for root)
            
        Returns:
            Dict with 'success': bool, 'id': int, 'message': str
        """
        query = """
            INSERT INTO kpi_centers (
                name, description, type, parent_center_id,
                created_date, modified_date, created_by, delete_flag, version
            ) VALUES (
                :name, :description, :kpi_type, :parent_center_id,
                NOW(), NOW(), :created_by, 0, 0
            )
        """
        
        params = {
            'name': name,
            'description': description,
            'kpi_type': kpi_type,
            'parent_center_id': parent_center_id,
            'created_by': self.user_id
        }
        
        return self._execute_insert(query, params, "create_kpi_center")
    
    def update_kpi_center(
        self,
        kpi_center_id: int,
        name: str = None,
        description: str = None,
        parent_center_id: int = None
    ) -> Dict:
        """
        Update a KPI Center.
        
        Args:
            kpi_center_id: Center ID
            name: New name
            description: New description
            parent_center_id: New parent ID
            
        Returns:
            Dict with 'success': bool, 'message': str
        """
        updates = []
        params = {'kpi_center_id': kpi_center_id}
        
        if name is not None:
            updates.append("name = :name")
            params['name'] = name
        
        if description is not None:
            updates.append("description = :description")
            params['description'] = description
        
        if parent_center_id is not None:
            updates.append("parent_center_id = :parent_center_id")
            params['parent_center_id'] = parent_center_id if parent_center_id > 0 else None
        
        if not updates:
            return {'success': False, 'message': 'No fields to update'}
        
        updates.append("modified_date = NOW()")
        updates.append("version = version + 1")
        
        query = f"""
            UPDATE kpi_centers
            SET {', '.join(updates)}
            WHERE id = :kpi_center_id AND delete_flag = 0
        """
        
        return self._execute_update(query, params, "update_kpi_center")
    
    def check_kpi_center_dependencies(self, kpi_center_id: int) -> Dict:
        """
        Check if a KPI Center can be deleted (has no dependencies).
        
        Args:
            kpi_center_id: Center ID
            
        Returns:
            Dict with 'can_delete': bool, 'dependencies': dict
        """
        deps = {}
        
        # Check for children
        children_query = """
            SELECT COUNT(*) as count FROM kpi_centers
            WHERE parent_center_id = :kpi_center_id AND delete_flag = 0
        """
        children_df = self._execute_query(children_query, {'kpi_center_id': kpi_center_id}, "check_children")
        deps['children'] = int(children_df.iloc[0]['count']) if not children_df.empty else 0
        
        # Check for active splits
        splits_query = """
            SELECT COUNT(*) as count FROM kpi_center_split_by_customer_product
            WHERE kpi_center_id = :kpi_center_id AND delete_flag = 0
              AND (valid_to >= CURDATE() OR valid_to IS NULL)
        """
        splits_df = self._execute_query(splits_query, {'kpi_center_id': kpi_center_id}, "check_splits")
        deps['active_splits'] = int(splits_df.iloc[0]['count']) if not splits_df.empty else 0
        
        # Check for assignments
        assignments_query = """
            SELECT COUNT(*) as count FROM sales_kpi_center_assignments
            WHERE kpi_center_id = :kpi_center_id AND delete_flag = 0
        """
        assignments_df = self._execute_query(assignments_query, {'kpi_center_id': kpi_center_id}, "check_assignments")
        deps['assignments'] = int(assignments_df.iloc[0]['count']) if not assignments_df.empty else 0
        
        can_delete = all(v == 0 for v in deps.values())
        
        return {
            'can_delete': can_delete,
            'dependencies': deps,
            'message': 'No dependencies found' if can_delete else 'Cannot delete: has active dependencies'
        }
    
    def delete_kpi_center(self, kpi_center_id: int, force: bool = False) -> Dict:
        """
        Soft delete a KPI Center.
        
        Args:
            kpi_center_id: Center ID
            force: Force delete even with dependencies (not recommended)
            
        Returns:
            Dict with 'success': bool, 'message': str
        """
        if not force:
            deps = self.check_kpi_center_dependencies(kpi_center_id)
            if not deps['can_delete']:
                return {
                    'success': False,
                    'message': deps['message'],
                    'dependencies': deps['dependencies']
                }
        
        query = """
            UPDATE kpi_centers
            SET delete_flag = 1,
                modified_date = NOW(),
                version = version + 1
            WHERE id = :kpi_center_id
        """
        
        return self._execute_update(query, {'kpi_center_id': kpi_center_id}, "delete_kpi_center")
    
    # =========================================================================
    # KPI ASSIGNMENTS - READ
    # =========================================================================
    
    def get_kpi_assignments(
        self,
        year: int = None,
        kpi_center_ids: List[int] = None,
        kpi_type_id: int = None
    ) -> pd.DataFrame:
        """
        Get KPI assignments for display and editing.
        
        Args:
            year: Filter by year
            kpi_center_ids: Filter by KPI Center IDs
            kpi_type_id: Filter by KPI type ID
            
        Returns:
            DataFrame with assignment details (all columns from view v2.0)
        """
        # Query from view to get all fields including creator/modifier
        query = """
            SELECT 
                -- Primary ID
                assignment_id,
                
                -- KPI Center
                kpi_center_id,
                kpi_center_name,
                kpi_center_description,
                kpi_center_type,
                parent_center_id,
                parent_center_name,
                
                -- Year
                year,
                
                -- KPI Type
                kpi_type_id,
                kpi_name,
                kpi_description,
                unit_of_measure,
                
                -- Targets (formatted)
                annual_target_value,
                weight,
                
                -- Targets (numeric)
                annual_target_value_numeric,
                weight_numeric,
                monthly_target_value,
                quarterly_target_value,
                
                -- Notes
                notes,
                
                -- Creator
                created_by_user_id,
                created_by_username,
                created_by_name,
                created_at,
                
                -- Modifier
                modified_by_user_id,
                modified_by_username,
                modified_by_name,
                updated_at,
                
                -- Version
                version,
                
                -- Flags
                is_current_year,
                year_status
                
            FROM sales_kpi_center_assignments_view
            WHERE 1=1
        """
        
        params = {}
        
        if year:
            query += " AND year = :year"
            params['year'] = year
        
        if kpi_center_ids:
            query += " AND kpi_center_id IN :kpi_center_ids"
            params['kpi_center_ids'] = tuple(kpi_center_ids)
        
        if kpi_type_id:
            query += " AND kpi_type_id = :kpi_type_id"
            params['kpi_type_id'] = kpi_type_id
        
        query += " ORDER BY kpi_center_type, kpi_center_name, kpi_name"
        
        return self._execute_query(query, params, "kpi_assignments")
    
    def get_assignment_summary_by_type(self, year: int) -> pd.DataFrame:
        """
        Get assignment summary by KPI type for a year.
        
        Args:
            year: Target year
            
        Returns:
            DataFrame with kpi_type, center_count, total_target, sum_assigned
        """
        query = """
            SELECT 
                kt.name as kpi_name,
                kt.id as kpi_type_id,
                kt.uom as unit_of_measure,
                COUNT(DISTINCT a.kpi_center_id) as center_count,
                SUM(a.annual_target_value) as total_target
            FROM sales_kpi_center_assignments a
            JOIN kpi_types kt ON a.kpi_type_id = kt.id
            WHERE a.year = :year AND a.delete_flag = 0
            GROUP BY kt.id, kt.name, kt.uom
            ORDER BY kt.name
        """
        
        return self._execute_query(query, {'year': year}, "assignment_summary_by_type")
    
    def get_assignment_weight_summary(self, year: int) -> pd.DataFrame:
        """
        Get weight sum per KPI Center for a year.
        
        Args:
            year: Target year
            
        Returns:
            DataFrame with kpi_center_id, kpi_center_name, total_weight, kpi_count
        """
        query = """
            SELECT 
                kpi_center_id,
                kpi_center_name,
                year,
                SUM(weight_numeric) as total_weight,
                COUNT(*) as kpi_count
            FROM sales_kpi_center_assignments_view
            WHERE year = :year
            GROUP BY kpi_center_id, kpi_center_name, year
            ORDER BY kpi_center_name
        """
        
        return self._execute_query(query, {'year': year}, "assignment_weight_summary")
    
    def validate_assignment_weight(
        self,
        kpi_center_id: int,
        year: int,
        new_weight: int,
        exclude_assignment_id: int = None
    ) -> Dict:
        """
        Validate if adding/updating an assignment weight is valid.
        
        Args:
            kpi_center_id: KPI Center ID
            year: Year
            new_weight: New weight to add/update
            exclude_assignment_id: Assignment ID to exclude (when editing)
            
        Returns:
            Dict with 'valid': bool, 'current_total', 'new_total', 'message'
        """
        query = """
            SELECT COALESCE(SUM(weight), 0) as current_total
            FROM sales_kpi_center_assignments
            WHERE kpi_center_id = :kpi_center_id 
              AND year = :year 
              AND delete_flag = 0
        """
        
        params = {
            'kpi_center_id': kpi_center_id,
            'year': year
        }
        
        if exclude_assignment_id:
            query = query.replace("AND delete_flag = 0", "AND delete_flag = 0 AND id != :exclude_id")
            params['exclude_id'] = exclude_assignment_id
        
        df = self._execute_query(query, params, "validate_weight")
        current_total = int(df.iloc[0]['current_total']) if not df.empty else 0
        new_total = current_total + new_weight
        
        if new_total > 100:
            return {
                'valid': False,
                'current_total': current_total,
                'new_total': new_total,
                'message': f"Adding {new_weight}% will result in {new_total}% (over 100% limit)"
            }
        elif new_total == 100:
            return {
                'valid': True,
                'current_total': current_total,
                'new_total': new_total,
                'message': f"Total weight will be exactly 100% ✓"
            }
        else:
            return {
                'valid': True,
                'current_total': current_total,
                'new_total': new_total,
                'message': f"Total weight will be {new_total}% ({100 - new_total}% remaining)"
            }
    
    def check_duplicate_assignment(
        self,
        kpi_center_id: int,
        kpi_type_id: int,
        year: int,
        exclude_assignment_id: int = None
    ) -> bool:
        """
        Check if a duplicate assignment exists.
        
        Args:
            kpi_center_id: KPI Center ID
            kpi_type_id: KPI Type ID
            year: Year
            exclude_assignment_id: Assignment ID to exclude (when editing)
            
        Returns:
            True if duplicate exists, False otherwise
        """
        query = """
            SELECT COUNT(*) as count
            FROM sales_kpi_center_assignments
            WHERE kpi_center_id = :kpi_center_id
              AND kpi_type_id = :kpi_type_id
              AND year = :year
              AND delete_flag = 0
        """
        
        params = {
            'kpi_center_id': kpi_center_id,
            'kpi_type_id': kpi_type_id,
            'year': year
        }
        
        if exclude_assignment_id:
            query = query.replace("AND delete_flag = 0", "AND delete_flag = 0 AND id != :exclude_id")
            params['exclude_id'] = exclude_assignment_id
        
        df = self._execute_query(query, params, "check_duplicate_assignment")
        return int(df.iloc[0]['count']) > 0 if not df.empty else False
    
    # =========================================================================
    # KPI ASSIGNMENTS - CREATE/UPDATE/DELETE
    # =========================================================================
    
    def create_assignment(
        self,
        kpi_center_id: int,
        kpi_type_id: int,
        year: int,
        annual_target_value: int,
        weight: int,
        notes: str = None
    ) -> Dict:
        """
        Create a new KPI assignment.
        
        Args:
            kpi_center_id: KPI Center ID
            kpi_type_id: KPI Type ID
            year: Year
            annual_target_value: Annual target
            weight: Weight percentage
            notes: Optional notes
            
        Returns:
            Dict with 'success': bool, 'id': int, 'message': str
            
        Note:
            - created_by: uses self.user_id (FK -> users.id)
            - modified_by: same as created_by on creation
        """
        # Check for duplicate
        if self.check_duplicate_assignment(kpi_center_id, kpi_type_id, year):
            return {
                'success': False,
                'message': 'Duplicate assignment: This KPI Center already has this KPI type for this year'
            }
        
        query = """
            INSERT INTO sales_kpi_center_assignments (
                kpi_center_id, kpi_type_id, year, annual_target_value, weight, notes,
                created_at, updated_at, created_by, modified_by, delete_flag, version
            ) VALUES (
                :kpi_center_id, :kpi_type_id, :year, :annual_target_value, :weight, :notes,
                NOW(), NOW(), :created_by, :created_by, 0, 0
            )
        """
        
        params = {
            'kpi_center_id': kpi_center_id,
            'kpi_type_id': kpi_type_id,
            'year': year,
            'annual_target_value': annual_target_value,
            'weight': weight,
            'notes': notes,
            'created_by': self.user_id  # Should be users.id (INT)
        }
        
        return self._execute_insert(query, params, "create_assignment")
    
    def update_assignment(
        self,
        assignment_id: int,
        annual_target_value: int = None,
        weight: int = None,
        notes: str = None
    ) -> Dict:
        """
        Update an existing KPI assignment.
        
        Args:
            assignment_id: Assignment ID
            annual_target_value: New annual target
            weight: New weight
            notes: New notes
            
        Returns:
            Dict with 'success': bool, 'message': str
            
        Note:
            - modified_by: uses self.user_id (FK -> users.id)
        """
        updates = []
        params = {'assignment_id': assignment_id, 'modified_by': self.user_id}
        
        if annual_target_value is not None:
            updates.append("annual_target_value = :annual_target_value")
            params['annual_target_value'] = annual_target_value
        
        if weight is not None:
            updates.append("weight = :weight")
            params['weight'] = weight
        
        if notes is not None:
            updates.append("notes = :notes")
            params['notes'] = notes
        
        if not updates:
            return {'success': False, 'message': 'No fields to update'}
        
        updates.append("updated_at = NOW()")
        updates.append("modified_by = :modified_by")
        updates.append("version = version + 1")
        
        query = f"""
            UPDATE sales_kpi_center_assignments
            SET {', '.join(updates)}
            WHERE id = :assignment_id AND delete_flag = 0
        """
        
        return self._execute_update(query, params, "update_assignment")
    
    def delete_assignment(self, assignment_id: int) -> Dict:
        """
        Soft delete a KPI assignment.
        
        Args:
            assignment_id: Assignment ID
            
        Returns:
            Dict with 'success': bool, 'message': str
        """
        query = """
            UPDATE sales_kpi_center_assignments
            SET delete_flag = 1,
                updated_at = NOW(),
                version = version + 1
            WHERE id = :assignment_id
        """
        
        return self._execute_update(query, {'assignment_id': assignment_id}, "delete_assignment")
    
    # =========================================================================
    # KPI TYPES - LOOKUP
    # =========================================================================
    
    def get_kpi_types(self) -> pd.DataFrame:
        """
        Get all KPI types for dropdown selection.
        
        Returns:
            DataFrame with id, name, description, uom
        """
        query = """
            SELECT 
                id as kpi_type_id,
                name as kpi_name,
                description as kpi_description,
                uom as unit_of_measure
            FROM kpi_types
            WHERE delete_flag = 0
            ORDER BY name
        """
        
        return self._execute_query(query, {}, "kpi_types")
    
    def get_available_years(self) -> List[int]:
        """
        Get list of years with KPI assignments.
        
        Returns:
            List of years
        """
        query = """
            SELECT DISTINCT year
            FROM sales_kpi_center_assignments
            WHERE delete_flag = 0
            ORDER BY year DESC
        """
        
        df = self._execute_query(query, {}, "available_years")
        
        if df.empty:
            return [datetime.now().year]
        
        return df['year'].tolist()
    
    # =========================================================================
    # LOOKUP QUERIES
    # =========================================================================
    
    def get_customers_for_dropdown(self) -> pd.DataFrame:
        """
        Get customers for dropdown selection.
        Customers are companies with company_type = 'Customer' via companies_company_types junction.
        """
        query = """
            SELECT DISTINCT
                c.id as customer_id,
                c.english_name as customer_name,
                c.company_code
            FROM companies c
            INNER JOIN companies_company_types cct ON c.id = cct.companies_id
            INNER JOIN company_types ct ON cct.company_type_id = ct.id
            WHERE c.delete_flag = 0
              AND ct.name = 'Customer'
              AND c.english_name IS NOT NULL
              AND c.english_name != ''
            ORDER BY c.english_name
        """
        
        return self._execute_query(query, {}, "customers_dropdown")
    
    def get_products_for_dropdown(
        self,
        brand_id: int = None
    ) -> pd.DataFrame:
        """
        Get products for dropdown selection.
        """
        query = """
            SELECT 
                p.id as product_id,
                p.name as product_name,
                p.pt_code,
                p.package_size,
                b.brand_name
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            WHERE p.delete_flag = 0
        """
        
        params = {}
        
        if brand_id:
            query += " AND p.brand_id = :brand_id"
            params['brand_id'] = brand_id
        
        query += " ORDER BY p.name"
        
        return self._execute_query(query, params, "products_dropdown")
    
    def get_brands_for_dropdown(self) -> pd.DataFrame:
        """
        Get brands for dropdown selection.
        """
        query = """
            SELECT 
                id as brand_id,
                brand_name
            FROM brands
            WHERE delete_flag = 0
            ORDER BY brand_name
        """
        
        return self._execute_query(query, {}, "brands_dropdown")
    
    def get_users_for_dropdown(self) -> pd.DataFrame:
        """
        Get users who have created or approved split rules.
        
        v2.6.0: NEW - For Created By / Approved By filters.
        NOTE: Users table doesn't have first_name/last_name - must join employees.
        
        Returns:
            DataFrame with user_id, username, full_name
        """
        query = """
            SELECT DISTINCT 
                u.id as user_id,
                u.username,
                TRIM(CONCAT(
                    COALESCE(e.first_name, ''), 
                    ' ', 
                    COALESCE(e.last_name, '')
                )) as full_name
            FROM users u
            LEFT JOIN employees e ON u.employee_id = e.id
            WHERE u.delete_flag = 0
              AND (
                  u.id IN (SELECT DISTINCT created_by FROM kpi_center_split_by_customer_product WHERE created_by IS NOT NULL)
                  OR u.id IN (SELECT DISTINCT approved_by FROM kpi_center_split_by_customer_product WHERE approved_by IS NOT NULL)
                  OR u.id IN (SELECT DISTINCT modified_by FROM kpi_center_split_by_customer_product WHERE modified_by IS NOT NULL)
              )
            ORDER BY full_name
        """
        return self._execute_query(query, {}, "users_for_dropdown")
    
    def get_split_rule_years(self) -> List[int]:
        """
        Get list of years that have split rules.
        
        v2.6.0: NEW - For Period Year dropdown.
        
        Returns:
            List of years sorted descending
        """
        query = """
            SELECT DISTINCT year FROM (
                SELECT YEAR(valid_from) as year
                FROM kpi_center_split_by_customer_product
                WHERE (delete_flag = 0 OR delete_flag IS NULL)
                  AND valid_from IS NOT NULL
                
                UNION
                
                SELECT YEAR(valid_to) as year
                FROM kpi_center_split_by_customer_product
                WHERE (delete_flag = 0 OR delete_flag IS NULL)
                  AND valid_to IS NOT NULL
            ) years
            WHERE year IS NOT NULL
            ORDER BY year DESC
        """
        
        df = self._execute_query(query, {}, "split_rule_years")
        
        if df.empty:
            return [date.today().year]
        
        years = df['year'].dropna().astype(int).tolist()
        
        # Ensure current year is included
        current_year = date.today().year
        if current_year not in years:
            years.append(current_year)
        
        return sorted(set(years), reverse=True)
    
    # =========================================================================
    # VALIDATION DASHBOARD
    # =========================================================================
    
    def get_all_validation_issues(self, year: int = None) -> Dict:
        """
        Get all validation issues for dashboard.
        
        Args:
            year: Year to check (default: current year)
            
        Returns:
            Dict with split_issues, assignment_issues, hierarchy_issues
        """
        year = year or datetime.now().year
        
        issues = {
            'split_issues': [],
            'assignment_issues': [],
            'hierarchy_issues': [],
            'summary': {}
        }
        
        # Split issues
        split_stats = self.get_split_summary_stats()
        issues['summary']['split'] = split_stats
        
        if split_stats['over_100_count'] > 0:
            issues['split_issues'].append({
                'severity': 'critical',
                'type': 'over_100_split',
                'count': split_stats['over_100_count'],
                'message': f"{split_stats['over_100_count']} customer-product combos have over 100% split"
            })
        
        if split_stats['incomplete_count'] > 0:
            issues['split_issues'].append({
                'severity': 'warning',
                'type': 'incomplete_split',
                'count': split_stats['incomplete_count'],
                'message': f"{split_stats['incomplete_count']} customer-product combos have under 100% split"
            })
        
        if split_stats['pending_count'] > 0:
            issues['split_issues'].append({
                'severity': 'info',
                'type': 'pending_approval',
                'count': split_stats['pending_count'],
                'message': f"{split_stats['pending_count']} split rules pending approval"
            })
        
        if split_stats['expiring_soon_count'] > 0:
            issues['split_issues'].append({
                'severity': 'info',
                'type': 'expiring_soon',
                'count': split_stats['expiring_soon_count'],
                'message': f"{split_stats['expiring_soon_count']} split rules expiring within 30 days"
            })
        
        # Assignment issues
        weight_df = self.get_assignment_weight_summary(year)
        if not weight_df.empty:
            # Check for weight != 100%
            invalid_weights = weight_df[weight_df['total_weight'] != 100]
            if not invalid_weights.empty:
                issues['assignment_issues'].append({
                    'severity': 'warning',
                    'type': 'weight_not_100',
                    'count': len(invalid_weights),
                    'message': f"{len(invalid_weights)} KPI Centers have weights not summing to 100%",
                    'details': invalid_weights.to_dict('records')
                })
        
        # Check for centers without assignments
        centers_without_assignment_query = """
            SELECT kc.id, kc.name
            FROM kpi_centers kc
            WHERE kc.delete_flag = 0
              AND kc.id NOT IN (
                  SELECT DISTINCT kpi_center_id 
                  FROM sales_kpi_center_assignments 
                  WHERE year = :year AND delete_flag = 0
              )
              AND kc.id IN (
                  SELECT DISTINCT kpi_center_id 
                  FROM kpi_center_split_by_customer_product 
                  WHERE delete_flag = 0 AND (valid_to >= CURDATE() OR valid_to IS NULL)
              )
        """
        centers_df = self._execute_query(centers_without_assignment_query, {'year': year}, "centers_without_assignment")
        if not centers_df.empty:
            issues['assignment_issues'].append({
                'severity': 'critical',
                'type': 'no_assignment',
                'count': len(centers_df),
                'message': f"{len(centers_df)} active KPI Centers have no {year} assignments",
                'details': centers_df.to_dict('records')
            })
        
        issues['summary']['assignment'] = {
            'weight_issues': len(invalid_weights) if not weight_df.empty else 0,
            'no_assignment': len(centers_df) if not centers_df.empty else 0
        }
        
        # Hierarchy issues (orphan nodes, etc.)
        hierarchy_df = self.get_kpi_center_hierarchy(include_stats=False)
        issues['summary']['hierarchy'] = {
            'total_centers': len(hierarchy_df),
            'issues': 0  # Could add more checks here
        }
        
        return issues
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _execute_query(
        self, 
        query: str, 
        params: dict, 
        query_name: str = "query"
    ) -> pd.DataFrame:
        """Execute SQL query and return DataFrame."""
        try:
            logger.debug(f"Executing {query_name}")
            df = pd.read_sql(text(query), self.engine, params=params)
            logger.debug(f"{query_name} returned {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Error executing {query_name}: {e}")
            return pd.DataFrame()
    
    def _execute_insert(
        self,
        query: str,
        params: dict,
        operation_name: str = "insert"
    ) -> Dict:
        """Execute INSERT and return result with new ID."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                
                # Get last insert ID
                last_id_result = conn.execute(text("SELECT LAST_INSERT_ID() as id"))
                last_id = last_id_result.fetchone()[0]
                
                logger.info(f"{operation_name} successful, id={last_id}")
                return {
                    'success': True,
                    'id': last_id,
                    'message': f'{operation_name} completed successfully'
                }
        except Exception as e:
            logger.error(f"Error in {operation_name}: {e}")
            return {
                'success': False,
                'id': None,
                'message': str(e)
            }
    
    def _execute_update(
        self,
        query: str,
        params: dict,
        operation_name: str = "update"
    ) -> Dict:
        """Execute UPDATE/DELETE and return result."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                
                rows_affected = result.rowcount
                logger.info(f"{operation_name} successful, {rows_affected} rows affected")
                return {
                    'success': True,
                    'count': rows_affected,
                    'message': f'{operation_name} completed successfully'
                }
        except Exception as e:
            logger.error(f"Error in {operation_name}: {e}")
            return {
                'success': False,
                'count': 0,
                'message': str(e)
            }