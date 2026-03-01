# utils/net_gap/constants.py - VERSION 4.5

"""
Constants for GAP Analysis System - IMPROVED VERSION 4.5
KEY CHANGE: Status classification based on Net GAP SIGN first, then coverage severity
- net_gap < 0 → SHORTAGE group (always!)
- net_gap = 0 → BALANCED
- net_gap > 0 → SURPLUS group
"""

# =============================================================================
# GAP STATUS CATEGORIES - Updated for Option A (Net GAP sign primary)
# =============================================================================
GAP_CATEGORIES = {
    'SHORTAGE': {
        'statuses': [
            'CRITICAL_SHORTAGE',   # coverage < 25%
            'SEVERE_SHORTAGE',     # coverage < 50%
            'HIGH_SHORTAGE',       # coverage < 75%
            'MODERATE_SHORTAGE',   # coverage < 90%
            'LIGHT_SHORTAGE'       # coverage < 100%
        ],
        'color': '#DC2626',
        'label': 'Shortage',
        'icon': '🔴'
    },
    'OPTIMAL': {
        'statuses': ['BALANCED'],  # Only when net_gap = 0
        'color': '#10B981',
        'label': 'Optimal',
        'icon': '✅'
    },
    'SURPLUS': {
        'statuses': [
            'LIGHT_SURPLUS',       # coverage ≤ 125%
            'MODERATE_SURPLUS',    # coverage ≤ 175%
            'HIGH_SURPLUS',        # coverage ≤ 250%
            'SEVERE_SURPLUS'       # coverage > 250%
        ],
        'color': '#3B82F6',
        'label': 'Surplus',
        'icon': '📦'
    },
    'INACTIVE': {
        'statuses': ['NO_DEMAND', 'NO_ACTIVITY'],
        'color': '#9CA3AF',
        'label': 'Inactive',
        'icon': '⭕'
    }
}

# =============================================================================
# THRESHOLDS - Updated for Option A logic
# =============================================================================
THRESHOLDS = {
    # Coverage thresholds for SHORTAGE severity (when net_gap < 0)
    'shortage': {
        'critical': 0.25,    # < 25% coverage → CRITICAL_SHORTAGE
        'severe': 0.50,      # < 50% coverage → SEVERE_SHORTAGE
        'high': 0.75,        # < 75% coverage → HIGH_SHORTAGE
        'moderate': 0.90,    # < 90% coverage → MODERATE_SHORTAGE
        'light': 1.00        # < 100% coverage → LIGHT_SHORTAGE
    },
    
    # Coverage thresholds for SURPLUS severity (when net_gap > 0)
    'surplus': {
        'light': 1.25,       # ≤ 125% coverage → LIGHT_SURPLUS
        'moderate': 1.75,    # ≤ 175% coverage → MODERATE_SURPLUS
        'high': 2.50,        # ≤ 250% coverage → HIGH_SURPLUS
        'severe': 2.50       # > 250% coverage → SEVERE_SURPLUS
    },
    
    # Safety stock thresholds
    'safety': {
        'critical_breach': 0.5,  # inventory < 50% of safety stock
        'below_safety': 1.0,     # inventory < 100% of safety stock
        'at_reorder': 1.0
    },
    
    # Priority levels
    'priority': {
        'critical': 1,
        'high': 2,
        'medium': 3,
        'low': 4,
        'ok': 99
    },
    
    # Legacy coverage thresholds (for backward compatibility)
    'coverage': {
        'critical_shortage': 0.25,
        'severe_shortage': 0.50,
        'high_shortage': 0.75,
        'moderate_shortage': 0.90,
        'light_shortage': 1.00,
        'balanced': 1.00,
        'light_surplus': 1.25,
        'moderate_surplus': 1.75,
        'high_surplus': 2.50
    }
}

# =============================================================================
# STATUS CONFIGURATION - Detailed info for each status
# =============================================================================
STATUS_CONFIG = {
    # SHORTAGE statuses (net_gap < 0)
    'CRITICAL_SHORTAGE': {
        'icon': '🚨',
        'color': '#7F1D1D',
        'priority': 1,
        'category': 'SHORTAGE',
        'description': 'Critical shortage - coverage below 25%'
    },
    'SEVERE_SHORTAGE': {
        'icon': '🔴',
        'color': '#DC2626',
        'priority': 1,
        'category': 'SHORTAGE',
        'description': 'Severe shortage - coverage below 50%'
    },
    'HIGH_SHORTAGE': {
        'icon': '🟠',
        'color': '#EA580C',
        'priority': 2,
        'category': 'SHORTAGE',
        'description': 'High shortage - coverage below 75%'
    },
    'MODERATE_SHORTAGE': {
        'icon': '🟡',
        'color': '#CA8A04',
        'priority': 3,
        'category': 'SHORTAGE',
        'description': 'Moderate shortage - coverage below 90%'
    },
    'LIGHT_SHORTAGE': {
        'icon': '⚠️',
        'color': '#EAB308',
        'priority': 4,
        'category': 'SHORTAGE',
        'description': 'Light shortage - coverage below 100%'
    },
    
    # BALANCED status (net_gap = 0)
    'BALANCED': {
        'icon': '✅',
        'color': '#10B981',
        'priority': 99,
        'category': 'OPTIMAL',
        'description': 'Supply exactly matches demand'
    },
    
    # SURPLUS statuses (net_gap > 0)
    'LIGHT_SURPLUS': {
        'icon': '🔵',
        'color': '#3B82F6',
        'priority': 4,
        'category': 'SURPLUS',
        'description': 'Light surplus - coverage up to 125%'
    },
    'MODERATE_SURPLUS': {
        'icon': '🟣',
        'color': '#8B5CF6',
        'priority': 3,
        'category': 'SURPLUS',
        'description': 'Moderate surplus - coverage up to 175%'
    },
    'HIGH_SURPLUS': {
        'icon': '🟠',
        'color': '#F97316',
        'priority': 2,
        'category': 'SURPLUS',
        'description': 'High surplus - coverage up to 250%'
    },
    'SEVERE_SURPLUS': {
        'icon': '🔴',
        'color': '#DC2626',
        'priority': 1,
        'category': 'SURPLUS',
        'description': 'Severe surplus - coverage above 250%'
    },
    
    # INACTIVE statuses
    'NO_DEMAND': {
        'icon': '⚪',
        'color': '#9CA3AF',
        'priority': 99,
        'category': 'INACTIVE',
        'description': 'Has supply but no demand'
    },
    'NO_ACTIVITY': {
        'icon': '⚪',
        'color': '#D1D5DB',
        'priority': 99,
        'category': 'INACTIVE',
        'description': 'No supply and no demand'
    }
}

# =============================================================================
# SUPPLY & DEMAND SOURCES
# =============================================================================
SUPPLY_SOURCES = {
    'INVENTORY': {
        'name': 'Inventory',
        'icon': '📦',
        'priority': 1,
        'lead_days': '0'
    },
    'CAN_PENDING': {
        'name': 'CAN Pending',
        'icon': '📋',
        'priority': 2,
        'lead_days': '1-3'
    },
    'WAREHOUSE_TRANSFER': {
        'name': 'Transfer',
        'icon': '🚛',
        'priority': 3,
        'lead_days': '2-5'
    },
    'PURCHASE_ORDER': {
        'name': 'Purchase Order',
        'icon': '📝',
        'priority': 4,
        'lead_days': '7-30'
    }
}

DEMAND_SOURCES = {
    'OC_PENDING': {
        'name': 'Confirmed Orders',
        'icon': '✔',
        'priority': 1
    },
    'FORECAST': {
        'name': 'Forecast',
        'icon': '📊',
        'priority': 2
    }
}

# =============================================================================
# FIELD TOOLTIPS
# =============================================================================
FIELD_TOOLTIPS = {
    'pt_code': 'Product code identifier',
    'Total Supply': 'Total Supply = Inventory + Pending + Transfer + PO',
    'Total Demand': 'Total Demand = Orders + Forecast',
    'Net GAP': 'Available Supply - Demand (considers safety stock if enabled)',
    'True GAP': 'Total Supply - Demand (ignores safety stock)',
    'Coverage %': '(Available Supply ÷ Demand) × 100%',
    'Safety Stock': 'Minimum required inventory level',
    'Safety Gap': 'Total Supply - Safety Stock (can be negative)',
    'Available Supply': 'MAX(0, Total Supply - Safety Stock)',
    'At Risk Value': 'Revenue at risk from shortage = Shortage × Selling Price',
    'GAP Value': 'Inventory value of gap = GAP × Unit Cost',
    'Reorder Point': 'Stock level that triggers reorder',
    'Below Reorder': 'Indicates if stock is below reorder point',
    'Safety Coverage': 'Current Inventory ÷ Safety Stock requirement',
    'Unit Cost': 'Average landed cost per unit',
    'Sell Price': 'Average selling price per unit',
    'Customers': 'Number of unique customers affected',
    'Shortage Cause': 'Explains why shortage exists (Real/Safety-induced)'
}

# =============================================================================
# EXPORT & UI CONFIGURATION
# =============================================================================
EXPORT_CONFIG = {
    'max_rows': 10000,
    'include_formulas': True,
    'include_cost_breakdown': True,
    'sheets': ['Summary', 'GAP Details', 'Cost Analysis', 'Calculation Guide']
}

UI_CONFIG = {
    'items_per_page_options': [10, 25, 50, 100],
    'default_items_per_page': 25,
    'max_chart_items': 20,
    'chart_height': 400,
    'chart_height_compact': 300,
    'chart_height_min': 250,
    'chart_height_max': 400,
    'chart_margin_compact': 30,
    'table_row_height': 35
}

# Status Icons (simplified)
STATUS_ICONS = {
    'SHORTAGE': '🔴',
    'OPTIMAL': '✅',
    'SURPLUS': '📦',
    'INACTIVE': '⭕',
    'WARNING': '⚠️',
    'CRITICAL': '🚨'
}

# =============================================================================
# FORMULA INFO
# =============================================================================
FORMULA_INFO = {
    'net_gap': {
        'formula': 'Available Supply - Total Demand',
        'description': 'When safety enabled: Available = MAX(0, Supply - Safety Stock)'
    },
    'true_gap': {
        'formula': 'Total Supply - Total Demand',
        'description': 'Always ignores safety stock'
    },
    'safety_gap': {
        'formula': 'Total Supply - Safety Stock',
        'description': 'Can be negative when supply is below safety requirement'
    },
    'coverage_ratio': {
        'formula': '(Available Supply ÷ Demand) × 100%',
        'description': 'Supply as percentage of demand'
    },
    'at_risk_value': {
        'formula': '|Shortage Qty| × Selling Price',
        'description': 'Potential revenue loss'
    },
    'gap_value': {
        'formula': 'Net GAP × Unit Cost',
        'description': 'Inventory value of the gap'
    },
    'safety_impact': {
        'formula': 'Net GAP - True GAP',
        'description': 'How safety stock affects the gap'
    }
}

# =============================================================================
# STATUS CLASSIFICATION LOGIC DOCUMENTATION
# =============================================================================
"""
VERSION 4.5 - STATUS CLASSIFICATION LOGIC

PRINCIPLE: Net GAP sign determines GROUP, Coverage determines SEVERITY

┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: Check for NO DEMAND cases                              │
├─────────────────────────────────────────────────────────────────┤
│  demand == 0 AND supply == 0  →  NO_ACTIVITY                    │
│  demand == 0 AND supply > 0   →  NO_DEMAND                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: Check SAFETY STOCK (if enabled, highest priority)      │
├─────────────────────────────────────────────────────────────────┤
│  inventory < safety_stock × 50%  →  CRITICAL_BREACH             │
│  inventory < safety_stock        →  BELOW_SAFETY                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Classify by NET GAP SIGN (PRIMARY)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  IF net_gap < 0:  ────────────────  SHORTAGE GROUP              │
│      │                                                           │
│      ├── coverage < 25%   →  🚨 CRITICAL_SHORTAGE               │
│      ├── coverage < 50%   →  🔴 SEVERE_SHORTAGE                 │
│      ├── coverage < 75%   →  🟠 HIGH_SHORTAGE                   │
│      ├── coverage < 90%   →  🟡 MODERATE_SHORTAGE               │
│      └── coverage < 100%  →  ⚠️ LIGHT_SHORTAGE                  │
│                                                                  │
│  ELIF net_gap == 0:  ─────────────  BALANCED                    │
│      └──  ✅ BALANCED                                           │
│                                                                  │
│  ELSE (net_gap > 0):  ────────────  SURPLUS GROUP               │
│      │                                                           │
│      ├── coverage ≤ 125%  →  🔵 LIGHT_SURPLUS                   │
│      ├── coverage ≤ 175%  →  🟣 MODERATE_SURPLUS                │
│      ├── coverage ≤ 250%  →  🟠 HIGH_SURPLUS                    │
│      └── coverage > 250%  →  🔴 SEVERE_SURPLUS                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

EXAMPLE with Option A logic:
┌─────────┬────────┬──────────┬──────────┬─────────────────────┐
│ Supply  │ Demand │ Net GAP  │ Coverage │ Status (v4.5)       │
├─────────┼────────┼──────────┼──────────┼─────────────────────┤
│ 240     │ 260    │ -20      │ 92%      │ ⚠️ LIGHT_SHORTAGE   │
│ 80      │ 100    │ -20      │ 80%      │ 🟡 MODERATE_SHORTAGE│
│ 50      │ 100    │ -50      │ 50%      │ 🔴 SEVERE_SHORTAGE  │
│ 100     │ 100    │ 0        │ 100%     │ ✅ BALANCED         │
│ 110     │ 100    │ +10      │ 110%     │ 🔵 LIGHT_SURPLUS    │
│ 200     │ 100    │ +100     │ 200%     │ 🟣 MODERATE_SURPLUS │
└─────────┴────────┴──────────┴──────────┴─────────────────────┘
"""