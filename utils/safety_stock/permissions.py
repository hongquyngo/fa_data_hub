# utils/safety_stock/permissions.py
"""
Role-Based Access Control for Safety Stock Management
Simple permission system based on user roles
"""

import streamlit as st
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ── Permission matrix ─────────────────────────────────────────────────────────
# Columns: view | create | edit | delete | review | bulk_upload | approve
#
# create / edit : admin, supply_chain_manager, inbound_manager only
# delete        : admin, supply_chain_manager only
# approve       : admin, supply_chain_manager only
# review        : all operational roles (not sales, fa, accountant, viewer, customer, vendor)
# MD / GM       : strategic oversight — view + review + bulk_upload, NO create/edit/delete/approve

_P = lambda v, c, e, d, r, b, a: {
    'view': v, 'create': c, 'edit': e, 'delete': d,
    'review': r, 'bulk_upload': b, 'approve': a
}

ROLE_PERMISSIONS = {
    # ── Full control ──────────────────────────────────────────────────────────
    'admin':                   _P(True,  True,  True,  True,  True,  True,  True),
    'supply_chain_manager':    _P(True,  True,  True,  True,  True,  True,  True),

    # ── Executive — view / review / bulk only (no create/edit/delete/approve) ─
    'MD':                      _P(True,  False, False, False, True,  True,  False),
    'GM':                      _P(True,  False, False, False, True,  True,  False),

    # ── Operational — create + edit (no delete/approve) ──────────────────────
    'inbound_manager':         _P(True,  True,  True,  False, True,  False, False),

    # ── Operational — view + review only ─────────────────────────────────────
    'supply_chain':            _P(True,  False, False, False, True,  False, False),
    'buyer':                   _P(True,  False, False, False, True,  False, False),
    'allocator':               _P(True,  False, False, False, True,  False, False),
    'outbound_manager':        _P(True,  False, False, False, True,  False, False),
    'warehouse_manager':       _P(True,  False, False, False, True,  False, False),
    'sales_manager':           _P(True,  False, False, False, True,  False, False),

    # ── View only ─────────────────────────────────────────────────────────────
    'sales':                   _P(True,  False, False, False, False, False, False),
    'fa_manager':              _P(True,  False, False, False, False, False, False),
    'accountant':              _P(True,  False, False, False, False, False, False),
    'viewer':                  _P(True,  False, False, False, False, False, False),

    # ── Customer — limited to own data ────────────────────────────────────────
    'customer':                _P(True,  False, False, False, False, False, False),

    # ── No access ─────────────────────────────────────────────────────────────
    'vendor':                  _P(False, False, False, False, False, False, False),
}

# Export row limits by role (None = unlimited)
EXPORT_ROW_LIMITS = {
    'customer':             1_000,
    'sales':                5_000,
    'viewer':               5_000,
    'fa_manager':           5_000,
    'accountant':           5_000,
    'sales_manager':        10_000,
    'outbound_manager':     10_000,
    'warehouse_manager':    10_000,
    'allocator':            10_000,
    'buyer':                10_000,
    # Unlimited
    'supply_chain':         None,
    'supply_chain_manager': None,
    'inbound_manager':      None,
    'MD':                   None,
    'GM':                   None,
    'admin':                None,
}


def get_user_role() -> str:
    """Get current user's role from session"""
    return st.session_state.get('user_role', 'viewer')


def has_permission(permission: str) -> bool:
    """
    Check if current user has specific permission
    
    Args:
        permission: Permission name (view, create, edit, delete, review, bulk_upload, approve)
    
    Returns:
        bool: True if user has permission
    """
    role = get_user_role()
    
    # Handle vendor role (not in table, no permissions)
    if role == 'vendor':
        return False
    
    permissions = ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS['viewer'])
    return permissions.get(permission, False)


def filter_data_for_customer(df: pd.DataFrame, customer_col: str = 'customer_id') -> pd.DataFrame:
    """
    Filter dataframe for customer role (only their data)
    
    Args:
        df: DataFrame to filter
        customer_col: Column name containing customer ID
    
    Returns:
        Filtered DataFrame
    """
    role = get_user_role()
    
    # Only filter for customer role
    if role == 'customer' and customer_col in df.columns:
        # Get customer ID from session (set during login)
        customer_id = st.session_state.get('customer_id')
        if customer_id:
            # Customer can only see their own data
            df = df[df[customer_col] == customer_id]
            logger.info(f"Filtered data for customer ID: {customer_id}")
        else:
            # No customer ID found, return empty
            logger.warning("Customer role but no customer_id in session")
            return pd.DataFrame()
    
    return df


def get_permission_message(permission: str) -> str:
    """
    Get user-friendly message for permission denial
    
    Args:
        permission: Permission that was denied
    
    Returns:
        User-friendly error message
    """
    messages = {
        'view': "Bạn không có quyền xem dữ liệu này",
        'create': "Bạn không có quyền tạo safety stock",
        'edit': "Bạn không có quyền chỉnh sửa safety stock",
        'delete': "Bạn không có quyền xóa safety stock",
        'review': "Bạn không có quyền review safety stock",
        'bulk_upload': "Bạn không có quyền upload hàng loạt",
        'approve': "Bạn không có quyền phê duyệt review"
    }
    return messages.get(permission, f"Bạn không có quyền {permission}")


def get_export_row_limit() -> int:
    """
    Get maximum number of rows user can export
    
    Returns:
        Maximum row count for export (None = no limit)
    """
    role = get_user_role()
    return EXPORT_ROW_LIMITS.get(role, 1000)


def get_user_info_display() -> str:
    """
    Get formatted user info for display
    
    Returns:
        Formatted string with username and role
    """
    username = st.session_state.get('user_fullname') or st.session_state.get('username', 'User')
    role = get_user_role()
    
    # Map role to Vietnamese if needed
    role_display = {
        'admin':                'Quản trị',
        'MD':                   'Tổng giám đốc',
        'GM':                   'Giám đốc',
        'supply_chain_manager': 'Quản lý chuỗi cung ứng',
        'supply_chain':         'Chuỗi cung ứng',
        'inbound_manager':      'Quản lý nhập kho',
        'outbound_manager':     'Quản lý xuất kho',
        'warehouse_manager':    'Quản lý kho',
        'buyer':                'Mua hàng',
        'allocator':            'Phân bổ',
        'sales_manager':        'Quản lý bán hàng',
        'sales':                'Bán hàng',
        'fa_manager':           'Quản lý tài chính',
        'accountant':           'Kế toán',
        'viewer':               'Xem',
        'customer':             'Khách hàng',
        'vendor':               'Nhà cung cấp',
    }.get(role, role)
    
    return f"👤 {username} ({role_display})"


def apply_export_limit(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """
    Apply export row limit based on user role
    
    Args:
        df: DataFrame to limit
    
    Returns:
        Tuple of (limited DataFrame, was_limited boolean)
    """
    limit = get_export_row_limit()
    
    if limit is None or len(df) <= limit:
        return df, False
    
    # Apply limit
    limited_df = df.head(limit)
    return limited_df, True


def log_action(action: str, details: str = None):
    """
    Log user action for audit
    
    Args:
        action: Action performed
        details: Optional details about the action
    """
    username = st.session_state.get('username', 'unknown')
    role = get_user_role()
    
    log_msg = f"Action: {action} by {username} (role: {role})"
    if details:
        log_msg += f" - {details}"
    
    logger.info(log_msg)