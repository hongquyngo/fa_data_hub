# utils/kpi_center_performance/access_control.py
"""
Access Control for KPI Center Performance Module

Handles role-based access control for KPI Center data.

VERSION: 2.1.0 - Integrated with permissions.py for granular CRUD control
"""

import logging
from typing import List, Optional, Dict
import streamlit as st

from .constants import ALLOWED_ROLES
from .permissions import SetupPermissions, get_permissions

logger = logging.getLogger(__name__)


class AccessControl:
    """
    Access control for KPI Center Performance page.
    
    v2.1.0: Integrated with SetupPermissions for granular CRUD control
    
    Usage:
        access = AccessControl(user_role)
        
        # Page-level access
        if access.can_access_page():
            ...
        
        # Setup tab access
        if access.can_access_setup_tab():
            ...
        
        # CRUD permissions
        if access.can_edit():
            st.button("Edit")
    """
    
    def __init__(self, user_role: str):
        """
        Initialize access control.
        
        Args:
            user_role: Current user's role
        """
        self.user_role = user_role
        self._perms = get_permissions(user_role)
        self._kpi_center_ids = None
    
    # =========================================================================
    # PAGE-LEVEL ACCESS (for main KPI Center Performance page)
    # =========================================================================
    
    def can_access_page(self) -> bool:
        """Check if user can access KPI Center Performance page."""
        return self.user_role in ALLOWED_ROLES
    
    def get_access_level(self) -> str:
        """
        Get access level for current user.
        
        Returns:
            'full' for allowed roles, 'none' otherwise
        """
        if self.user_role in ALLOWED_ROLES:
            return 'full'
        return 'none'
    
    # =========================================================================
    # SETUP TAB ACCESS
    # =========================================================================
    
    def can_access_setup_tab(self) -> bool:
        """Check if user can access Setup Tab."""
        return self._perms.can_access_setup_tab
    
    # =========================================================================
    # CRUD PERMISSIONS
    # =========================================================================
    
    def can_view(self) -> bool:
        """Check if user can view data in Setup Tab."""
        return self._perms.can_view
    
    def can_create(self) -> bool:
        """Check if user can create split rules / assignments."""
        return self._perms.can_create
    
    def can_edit(self) -> bool:
        """Check if user can edit split rules / assignments."""
        return self._perms.can_edit
    
    def can_delete(self) -> bool:
        """Check if user can delete split rules / assignments."""
        return self._perms.can_delete
    
    def can_approve(self) -> bool:
        """Check if user can approve split rules."""
        return self._perms.can_approve
    
    def can_bulk_operations(self) -> bool:
        """Check if user can perform bulk operations."""
        return self._perms.can_bulk_operations
    
    def can_manage_hierarchy(self) -> bool:
        """Check if user can manage KPI Center hierarchy."""
        return self._perms.can_manage_hierarchy
    
    def can_export(self) -> bool:
        """Check if user can export data."""
        return self._perms.can_export
    
    # =========================================================================
    # KPI CENTER ACCESS
    # =========================================================================
    
    def get_accessible_kpi_center_ids(self) -> List[int]:
        """
        Get list of KPI Center IDs accessible to user.
        
        For allowed roles, returns all KPI Centers.
        
        Returns:
            List of kpi_center_id values
        """
        if not self.can_access_page():
            return []
        
        if self._kpi_center_ids is not None:
            return self._kpi_center_ids
        
        # Get all KPI Centers
        try:
            from utils.db import get_db_engine
            from sqlalchemy import text
            
            engine = get_db_engine()
            query = """
                SELECT DISTINCT id 
                FROM kpi_centers 
                WHERE delete_flag = 0
                ORDER BY id
            """
            
            with engine.connect() as conn:
                result = conn.execute(text(query))
                self._kpi_center_ids = [row[0] for row in result]
            
            return self._kpi_center_ids
            
        except Exception as e:
            logger.error(f"Error fetching KPI Center IDs: {e}")
            return []
    
    def validate_selected_kpi_centers(self, selected_ids: List[int]) -> List[int]:
        """
        Validate that selected KPI Centers are accessible.
        
        Args:
            selected_ids: List of selected KPI Center IDs
            
        Returns:
            List of valid KPI Center IDs
        """
        if not self.can_access_page():
            return []
        
        # For full access, all selections are valid
        return selected_ids
    
    # =========================================================================
    # MESSAGES
    # =========================================================================
    
    def get_denied_message(self) -> str:
        """Get message to show when page access is denied."""
        return f"⚠️ Access Denied. Your role ({self.user_role}) does not have permission to view KPI Center Performance. Required roles: {', '.join(ALLOWED_ROLES)}"
    
    def get_setup_denied_message(self) -> str:
        """Get message to show when Setup Tab access is denied."""
        return self._perms.get_denied_message()
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    
    def get_permission_summary(self) -> Dict[str, bool]:
        """
        Get all permissions as dictionary for UI rendering.
        
        Returns:
            Dict with all permission flags
        """
        return self._perms.to_dict()
    
    def __repr__(self) -> str:
        return f"AccessControl(role={self.user_role}, level={self.get_access_level()}, perms={self._perms})"