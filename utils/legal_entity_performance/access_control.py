# utils/legal_entity_performance/access_control.py
"""
Access Control for Legal Entity Performance Module
Aligned with kpi_center_performance/access_control.py

VERSION: 2.0.0
- Simplified: No Setup tab, no hierarchy management
- Same role-based pattern as KPI center
"""

import logging
from typing import List, Dict
import streamlit as st

from .constants import ALLOWED_ROLES

logger = logging.getLogger(__name__)


class AccessControl:
    """
    Access control for Legal Entity Performance page.
    
    Simplified vs KPI center:
    - No Setup tab (no KPI assignments for entities)
    - No hierarchy management
    - Same ALLOWED_ROLES for page access
    
    Usage:
        access = AccessControl(user_role)
        if access.can_access_page():
            ...
    """
    
    def __init__(self, user_role: str):
        self.user_role = user_role
    
    # =========================================================================
    # PAGE-LEVEL ACCESS
    # =========================================================================
    
    def can_access_page(self) -> bool:
        """Check if user can access Legal Entity Performance page."""
        return self.user_role in ALLOWED_ROLES
    
    def get_access_level(self) -> str:
        if self.user_role in ALLOWED_ROLES:
            return 'full'
        return 'none'
    
    # =========================================================================
    # FEATURE ACCESS
    # =========================================================================
    
    def can_export(self) -> bool:
        """Check if user can export data."""
        return self.user_role in ALLOWED_ROLES
    
    def can_view_all_entities(self) -> bool:
        """Check if user can view all legal entities."""
        return self.user_role in ALLOWED_ROLES
    
    # =========================================================================
    # ENTITY ACCESS
    # =========================================================================
    
    def get_accessible_entity_ids(self) -> List[int]:
        """
        Get list of legal entity IDs accessible to user.
        For allowed roles, returns empty list (= all entities).
        """
        if not self.can_access_page():
            return []
        return []  # Empty = no restriction
    
    # =========================================================================
    # MESSAGES
    # =========================================================================
    
    def get_denied_message(self) -> str:
        return (
            f"⚠️ Access Denied. Your role ({self.user_role}) does not have "
            f"permission to view Legal Entity Performance. "
            f"Required roles: {', '.join(ALLOWED_ROLES)}"
        )
    
    def __repr__(self) -> str:
        return f"AccessControl(role={self.user_role}, level={self.get_access_level()})"
