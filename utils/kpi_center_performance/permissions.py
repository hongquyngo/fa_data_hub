# utils/kpi_center_performance/permissions.py
"""
Permission Definitions for KPI Center Performance Module

Centralized permission configuration - NO DATABASE CHANGES REQUIRED.
Simply define which roles can do what.

VERSION: 1.0.0
"""

from typing import Set, Dict
from dataclasses import dataclass


# =============================================================================
# PERMISSION CONFIGURATION
# =============================================================================

# Roles that can ACCESS the Setup Tab
SETUP_TAB_ACCESS_ROLES: Set[str] = {
    'admin',
    'md',
    'gm',
    'director',
    'sales_manager',
}

# Roles that can VIEW data (implicit if can access)
VIEW_ROLES: Set[str] = SETUP_TAB_ACCESS_ROLES

# Roles that can CREATE split rules / assignments
CREATE_ROLES: Set[str] = {
    'admin',
    'md',
    'gm',
    'director',
    'sales_manager',
}

# Roles that can EDIT split rules / assignments
EDIT_ROLES: Set[str] = {
    'admin',
    'md',
    'gm',
    'director',
    'sales_manager',
}

# Roles that can DELETE split rules / assignments
DELETE_ROLES: Set[str] = {
    'admin',
    'md',
    'gm',
    'sales_manager',
}

# Roles that can APPROVE split rules
APPROVE_ROLES: Set[str] = {
    'admin',
    'md',
    'sales_manager',
}

# Roles that can perform BULK operations
BULK_OPS_ROLES: Set[str] = {
    'admin',
    'md',
    'gm',
    'sales_manager',
}

# Roles that can MANAGE HIERARCHY (add/edit KPI Centers)
MANAGE_HIERARCHY_ROLES: Set[str] = {
    'admin',
}

# Roles that can EXPORT data
EXPORT_ROLES: Set[str] = SETUP_TAB_ACCESS_ROLES


# =============================================================================
# PERMISSION CHECKER CLASS
# =============================================================================

@dataclass
class SetupPermissions:
    """
    Permission checker for Setup Tab.
    
    Usage:
        perms = SetupPermissions(user_role='sales_manager')
        
        if perms.can_edit:
            # show edit button
        
        if perms.can_approve:
            # show approve button
    """
    user_role: str
    
    def __post_init__(self):
        # Normalize role to lowercase for comparison
        self._role = str(self.user_role).lower().strip() if self.user_role else ''
    
    @property
    def can_access_setup_tab(self) -> bool:
        """Check if user can access Setup Tab."""
        return self._role in SETUP_TAB_ACCESS_ROLES
    
    @property
    def can_view(self) -> bool:
        """Check if user can view data."""
        return self._role in VIEW_ROLES
    
    @property
    def can_create(self) -> bool:
        """Check if user can create records."""
        return self._role in CREATE_ROLES
    
    @property
    def can_edit(self) -> bool:
        """Check if user can edit records."""
        return self._role in EDIT_ROLES
    
    @property
    def can_delete(self) -> bool:
        """Check if user can delete records."""
        return self._role in DELETE_ROLES
    
    @property
    def can_approve(self) -> bool:
        """Check if user can approve records."""
        return self._role in APPROVE_ROLES
    
    @property
    def can_bulk_operations(self) -> bool:
        """Check if user can perform bulk operations."""
        return self._role in BULK_OPS_ROLES
    
    @property
    def can_manage_hierarchy(self) -> bool:
        """Check if user can manage KPI Center hierarchy."""
        return self._role in MANAGE_HIERARCHY_ROLES
    
    @property
    def can_export(self) -> bool:
        """Check if user can export data."""
        return self._role in EXPORT_ROLES
    
    def to_dict(self) -> Dict[str, bool]:
        """Get all permissions as dictionary (for UI)."""
        return {
            'can_access': self.can_access_setup_tab,
            'can_view': self.can_view,
            'can_create': self.can_create,
            'can_edit': self.can_edit,
            'can_delete': self.can_delete,
            'can_approve': self.can_approve,
            'can_bulk': self.can_bulk_operations,
            'can_manage_hierarchy': self.can_manage_hierarchy,
            'can_export': self.can_export,
        }
    
    def get_denied_message(self) -> str:
        """Get message when access is denied."""
        return (
            f"⚠️ Access Denied. Your role '{self.user_role}' does not have permission "
            f"to access Setup. Required roles: {', '.join(sorted(SETUP_TAB_ACCESS_ROLES))}"
        )
    
    def __repr__(self) -> str:
        perms = []
        if self.can_view: perms.append('V')
        if self.can_create: perms.append('C')
        if self.can_edit: perms.append('E')
        if self.can_delete: perms.append('D')
        if self.can_approve: perms.append('A')
        if self.can_bulk_operations: perms.append('B')
        return f"SetupPermissions(role='{self._role}', perms=[{','.join(perms)}])"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_permissions(user_role: str) -> SetupPermissions:
    """
    Factory function to get permissions for a role.
    
    Args:
        user_role: User's role from session
        
    Returns:
        SetupPermissions instance
    """
    return SetupPermissions(user_role=user_role)


def check_permission(user_role: str, action: str) -> bool:
    """
    Quick permission check.
    
    Args:
        user_role: User's role
        action: One of 'access', 'view', 'create', 'edit', 'delete', 'approve', 'bulk'
        
    Returns:
        True if permitted
    """
    perms = SetupPermissions(user_role)
    
    action_map = {
        'access': perms.can_access_setup_tab,
        'view': perms.can_view,
        'create': perms.can_create,
        'edit': perms.can_edit,
        'delete': perms.can_delete,
        'approve': perms.can_approve,
        'bulk': perms.can_bulk_operations,
        'hierarchy': perms.can_manage_hierarchy,
        'export': perms.can_export,
    }
    
    return action_map.get(action.lower(), False)
