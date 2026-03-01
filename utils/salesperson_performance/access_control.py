# utils/salesperson_performance/access_control.py
"""
Role-based Access Control for Salesperson Performance

Handles data access permissions based on user role:
- admin/GM/MD: Full access to all salespeople
- sales_manager: Access to self + team members (recursive hierarchy)
- sales: Access to own data only

Uses recursive CTE to traverse manager_id hierarchy in employees table.
"""

import logging
from typing import List, Optional
import pandas as pd
from sqlalchemy import text

from utils.db import get_db_engine
from .constants import FULL_ACCESS_ROLES, TEAM_ACCESS_ROLES, SELF_ACCESS_ROLES

logger = logging.getLogger(__name__)


class AccessControl:
    """
    Manage data access based on user role and employee hierarchy.
    
    Usage:
        access = AccessControl(
            user_role=st.session_state.user_role,
            employee_id=st.session_state.employee_id
        )
        
        # Get access level
        level = access.get_access_level()  # 'full', 'team', or 'self'
        
        # Get accessible employee IDs
        ids = access.get_accessible_employee_ids()
        
        # Filter a dataframe
        filtered_df = access.filter_dataframe(df, 'sales_id')
    """
    
    def __init__(self, user_role: str, employee_id: int):
        """
        Initialize access control.
        
        Args:
            user_role: User's role from session (e.g., 'admin', 'sales_manager', 'sales')
            employee_id: User's employee_id from session
        """
        self.user_role = user_role.lower() if user_role else ''
        self.employee_id = employee_id
        self._accessible_ids: Optional[List[int]] = None
        self._team_info: Optional[pd.DataFrame] = None
        
        logger.info(f"AccessControl initialized: role={self.user_role}, employee_id={self.employee_id}")
    
    # =========================================================================
    # ACCESS LEVEL DETERMINATION
    # =========================================================================
    
    def get_access_level(self) -> str:
        """
        Determine access level based on role.
        
        Returns:
            'full' - Can view all salespeople
            'team' - Can view self + team members
            'self' - Can view own data only
        """
        if self.user_role in [r.lower() for r in FULL_ACCESS_ROLES]:
            return 'full'
        elif self.user_role in [r.lower() for r in TEAM_ACCESS_ROLES]:
            return 'team'
        else:
            return 'self'
    
    def can_view_all(self) -> bool:
        """Check if user has full access to all data."""
        return self.get_access_level() == 'full'
    
    def can_select_salesperson(self) -> bool:
        """Check if user can select different salespeople (not self-only)."""
        return self.get_access_level() != 'self'
    
    # =========================================================================
    # ACCESSIBLE EMPLOYEE IDS
    # =========================================================================
    
    def get_accessible_employee_ids(self) -> List[int]:
        """
        Get list of employee IDs that user can access.
        Results are cached after first call.
        
        Returns:
            List of employee IDs
        """
        if self._accessible_ids is not None:
            return self._accessible_ids
        
        level = self.get_access_level()
        
        if level == 'full':
            self._accessible_ids = self._get_all_sales_employee_ids()
        elif level == 'team':
            self._accessible_ids = self._get_team_member_ids()
        else:
            # Self access - only own employee_id
            self._accessible_ids = [self.employee_id] if self.employee_id else []
        
        logger.info(f"Accessible employee IDs ({level}): {len(self._accessible_ids)} employees")
        return self._accessible_ids
    
    def _get_all_sales_employee_ids(self) -> List[int]:
        """
        Get all employee IDs who have sales data.
        Used for full access roles.
        """
        query = """
            SELECT DISTINCT sales_id 
            FROM unified_sales_by_salesperson_view
            WHERE sales_id IS NOT NULL
            ORDER BY sales_id
        """
        
        try:
            engine = get_db_engine()
            with engine.connect() as conn:
                result = conn.execute(text(query))
                ids = [row[0] for row in result]
                logger.debug(f"Found {len(ids)} salespeople with data")
                return ids
        except Exception as e:
            logger.error(f"Error fetching sales employee IDs: {e}")
            return []
    
    def _get_team_member_ids(self) -> List[int]:
        """
        Get team member IDs using recursive CTE.
        Includes the manager themselves + all direct/indirect reports.
        Only returns members who have sales data.
        """
        if not self.employee_id:
            logger.warning("No employee_id provided for team access")
            return []
        
        # Recursive CTE to traverse manager hierarchy
        # Then filter by those who have sales data
        query = """
            WITH RECURSIVE team_hierarchy AS (
                -- Base case: the manager themselves
                SELECT 
                    id,
                    CONCAT(first_name, ' ', last_name) as name,
                    manager_id,
                    0 as level
                FROM employees 
                WHERE id = :manager_id
                  AND delete_flag = 0
                
                UNION ALL
                
                -- Recursive case: all direct/indirect reports
                SELECT 
                    e.id,
                    CONCAT(e.first_name, ' ', e.last_name) as name,
                    e.manager_id,
                    th.level + 1
                FROM employees e
                INNER JOIN team_hierarchy th ON e.manager_id = th.id
                WHERE e.delete_flag = 0 
                  AND e.status = 'ACTIVE'
            ),
            team_with_sales AS (
                SELECT DISTINCT th.id, th.name, th.level
                FROM team_hierarchy th
                INNER JOIN unified_sales_by_salesperson_view usv 
                    ON th.id = usv.sales_id
            )
            SELECT id, name, level
            FROM team_with_sales
            ORDER BY level, name
        """
        
        try:
            engine = get_db_engine()
            with engine.connect() as conn:
                result = conn.execute(text(query), {'manager_id': self.employee_id})
                rows = result.fetchall()
                
                # Cache team info for later use (e.g., displaying team structure)
                self._team_info = pd.DataFrame(rows, columns=['id', 'name', 'level'])
                
                ids = [row[0] for row in rows]
                logger.info(f"Team hierarchy for employee {self.employee_id}: {len(ids)} members with sales data")
                return ids
                
        except Exception as e:
            logger.error(f"Error fetching team member IDs: {e}")
            # Fallback to just self
            return [self.employee_id] if self.employee_id else []
    
    # =========================================================================
    # TEAM INFORMATION
    # =========================================================================
    
    def get_team_size(self) -> int:
        """Get number of team members (including self)."""
        return len(self.get_accessible_employee_ids())
    
    # =========================================================================
    # DATA FILTERING
    # =========================================================================
    
    def filter_dataframe(
        self, 
        df: pd.DataFrame, 
        employee_id_col: str = 'sales_id'
    ) -> pd.DataFrame:
        """
        Filter DataFrame to only include accessible employees.
        
        Args:
            df: DataFrame to filter
            employee_id_col: Column name containing employee IDs
            
        Returns:
            Filtered DataFrame
        """
        if df.empty:
            return df
        
        if employee_id_col not in df.columns:
            logger.warning(f"Column '{employee_id_col}' not found in DataFrame")
            return df
        
        accessible_ids = self.get_accessible_employee_ids()
        
        if not accessible_ids:
            logger.warning("No accessible employee IDs, returning empty DataFrame")
            return df.head(0)
        
        filtered = df[df[employee_id_col].isin(accessible_ids)]
        logger.debug(f"Filtered DataFrame: {len(df)} -> {len(filtered)} rows")
        
        return filtered
    
    # =========================================================================
    # PERMISSION CHECKS
    # =========================================================================
    

    def validate_selected_employees(
        self, 
        selected_ids: List[int]
    ) -> List[int]:
        """
        Validate and filter selected employee IDs against access rights.
        
        Args:
            selected_ids: List of employee IDs user selected
            
        Returns:
            List of valid employee IDs user can actually access
        """
        accessible_ids = set(self.get_accessible_employee_ids())
        valid_ids = [id for id in selected_ids if id in accessible_ids]
        
        if len(valid_ids) < len(selected_ids):
            logger.warning(
                f"Some selected employees were filtered out: "
                f"selected={len(selected_ids)}, valid={len(valid_ids)}"
            )
        
        return valid_ids
    
    # =========================================================================
    # DEBUG / INFO
    # =========================================================================
    

    def __repr__(self) -> str:
        return (
            f"AccessControl(role='{self.user_role}', "
            f"employee_id={self.employee_id}, "
            f"level='{self.get_access_level()}')"
        )