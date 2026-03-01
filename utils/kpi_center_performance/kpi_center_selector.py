# utils/kpi_center_performance/kpi_center_selector.py
"""
KPI Center Tree Selector Component

VERSION: 1.0.0

Single-selection tree component for KPI Center selection.
Prevents parent-child double counting by enforcing single selection.

Features:
- Single selection (radio-style)
- Visual hierarchy with indentation
- "Include sub-centers" toggle
- Search/filter functionality
- Clear indicator of selection scope
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set
import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class KPICenterNode:
    """Represents a node in the KPI Center hierarchy tree."""
    id: int
    name: str
    description: str
    kpi_type: str
    parent_id: Optional[int]
    level: int
    is_leaf: bool
    children_count: int
    path: str  # Full path for sorting


@dataclass
class KPICenterSelection:
    """Result of KPI Center selection."""
    selected_id: int
    selected_name: str
    include_children: bool
    expanded_ids: List[int]  # All IDs to query (selected + children if toggled)
    children_count: int
    
    def __repr__(self) -> str:
        if self.include_children and self.children_count > 0:
            return f"KPICenterSelection({self.selected_name} + {self.children_count} sub-centers)"
        return f"KPICenterSelection({self.selected_name})"


# =============================================================================
# TREE BUILDER
# =============================================================================

class KPICenterTreeBuilder:
    """
    Build tree structure from hierarchy DataFrame.
    
    Input DataFrame expected columns:
    - kpi_center_id
    - kpi_center_name
    - kpi_type
    - parent_center_id
    - level (optional, will be calculated if missing)
    - is_leaf (optional)
    - has_children (optional)
    - description (optional)
    """
    
    def __init__(self, hierarchy_df: pd.DataFrame):
        """Initialize with hierarchy data."""
        self.df = hierarchy_df.copy() if not hierarchy_df.empty else pd.DataFrame()
        self._nodes: Dict[int, KPICenterNode] = {}
        self._children_map: Dict[int, List[int]] = {}
        self._build_tree()
    
    def _build_tree(self):
        """Build internal tree structure."""
        if self.df.empty:
            return
        
        # Build nodes
        for _, row in self.df.iterrows():
            node_id = int(row['kpi_center_id'])
            parent_id = row.get('parent_center_id')
            if pd.notna(parent_id):
                parent_id = int(parent_id)
            else:
                parent_id = None
            
            self._nodes[node_id] = KPICenterNode(
                id=node_id,
                name=row.get('kpi_center_name', str(node_id)),
                description=row.get('description', ''),
                kpi_type=row.get('kpi_type', ''),
                parent_id=parent_id,
                level=int(row.get('level', 0)),
                is_leaf=bool(row.get('is_leaf', True)),
                children_count=int(row.get('has_children', 0)) if 'has_children' in row else 0,
                path=row.get('path', row.get('kpi_center_name', ''))
            )
        
        # Build children map
        for node_id, node in self._nodes.items():
            if node.parent_id is not None:
                if node.parent_id not in self._children_map:
                    self._children_map[node.parent_id] = []
                self._children_map[node.parent_id].append(node_id)
        
        # Update children_count if not provided
        for node_id in self._nodes:
            children = self._children_map.get(node_id, [])
            if children:
                self._nodes[node_id].children_count = len(children)
                self._nodes[node_id].is_leaf = False
    
    def get_all_descendants(self, node_id: int, include_self: bool = True) -> List[int]:
        """Get all descendant IDs using BFS."""
        if node_id not in self._nodes:
            return [node_id] if include_self else []
        
        descendants = []
        if include_self:
            descendants.append(node_id)
        
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            children = self._children_map.get(current, [])
            descendants.extend(children)
            queue.extend(children)
        
        return descendants
    
    def count_descendants(self, node_id: int) -> int:
        """Count total descendants (not including self)."""
        return len(self.get_all_descendants(node_id, include_self=False))
    
    def get_node(self, node_id: int) -> Optional[KPICenterNode]:
        """Get node by ID."""
        return self._nodes.get(node_id)
    
    def get_roots(self, kpi_type: str = None) -> List[KPICenterNode]:
        """Get root nodes (no parent), optionally filtered by type."""
        roots = []
        filtered_ids = set(self._nodes.keys())
        
        for node_id, node in self._nodes.items():
            if kpi_type and node.kpi_type != kpi_type:
                continue
            if node.parent_id is None or node.parent_id not in filtered_ids:
                roots.append(node)
        
        return sorted(roots, key=lambda n: n.path)
    
    def filter_by_type(self, kpi_type: str) -> 'KPICenterTreeBuilder':
        """Return new tree filtered by KPI type."""
        if self.df.empty or not kpi_type:
            return self
        
        filtered_df = self.df[self.df['kpi_type'] == kpi_type]
        return KPICenterTreeBuilder(filtered_df)
    
    def filter_by_ids(self, allowed_ids: Set[int]) -> 'KPICenterTreeBuilder':
        """Return new tree filtered by allowed IDs."""
        if self.df.empty or not allowed_ids:
            return self
        
        filtered_df = self.df[self.df['kpi_center_id'].isin(allowed_ids)]
        return KPICenterTreeBuilder(filtered_df)


# =============================================================================
# DISPLAY BUILDER
# =============================================================================

def build_tree_display_options(
    tree: KPICenterTreeBuilder,
    kpi_type: str = None
) -> Tuple[List[str], Dict[str, int], Dict[int, str]]:
    """
    Build display options for selectbox with hierarchy visualization.
    
    Returns:
        - options: List of formatted display strings
        - display_to_id: Dict mapping display string → kpi_center_id
        - id_to_display: Dict mapping kpi_center_id → display string
    """
    options = []
    display_to_id = {}
    id_to_display = {}
    
    # Icons for different node types
    ICON_ROOT = "🏢"      # Root/Company level
    ICON_REGION = "🌏"    # Region level  
    ICON_BRANCH = "📍"    # Branch/Leaf level
    ICON_FOLDER = "📁"    # Has children
    
    def get_icon(node: KPICenterNode) -> str:
        """Get appropriate icon for node."""
        if node.level == 0:
            return ICON_ROOT if not node.is_leaf else ICON_BRANCH
        elif node.level == 1:
            return ICON_REGION if not node.is_leaf else ICON_BRANCH
        else:
            return ICON_FOLDER if not node.is_leaf else ICON_BRANCH
    
    def build_display_name(node: KPICenterNode, indent: str = "") -> str:
        """Build formatted display name with indent and icon."""
        icon = get_icon(node)
        
        # Add children count indicator for non-leaf nodes
        if not node.is_leaf:
            children_count = tree.count_descendants(node.id)
            suffix = f" ({children_count})" if children_count > 0 else ""
        else:
            suffix = ""
        
        return f"{indent}{icon} {node.name}{suffix}"
    
    def traverse(node_id: int, indent_level: int = 0):
        """Recursively traverse tree to build options."""
        node = tree.get_node(node_id)
        if not node:
            return
        
        # Build indent (2 spaces per level)
        indent = "    " * indent_level
        
        display_name = build_display_name(node, indent)
        options.append(display_name)
        display_to_id[display_name] = node.id
        id_to_display[node.id] = display_name
        
        # Process children (sorted by name)
        children_ids = tree._children_map.get(node_id, [])
        children_nodes = [tree.get_node(cid) for cid in children_ids if tree.get_node(cid)]
        children_nodes = sorted(children_nodes, key=lambda n: n.name)
        
        for child_node in children_nodes:
            traverse(child_node.id, indent_level + 1)
    
    # Start from roots
    roots = tree.get_roots(kpi_type)
    for root in roots:
        traverse(root.id, 0)
    
    return options, display_to_id, id_to_display


# =============================================================================
# MAIN SELECTOR COMPONENT
# =============================================================================

def render_kpi_center_selector(
    hierarchy_df: pd.DataFrame,
    kpi_type_filter: str = None,
    allowed_ids: Set[int] = None,
    key_prefix: str = "kpc_sel",
    show_search: bool = True,
) -> KPICenterSelection:
    """
    Render KPI Center tree selector component.
    
    Features:
    - Single selection (prevents parent-child double counting)
    - Visual hierarchy with indentation
    - "Include sub-centers" toggle
    - Optional search filter
    
    Args:
        hierarchy_df: DataFrame with KPI Center hierarchy
        kpi_type_filter: Filter by KPI type (TERRITORY, VERTICAL, etc.)
        allowed_ids: Set of allowed KPI Center IDs (e.g., those with KPI assignments)
        key_prefix: Prefix for session state keys
        show_search: Whether to show search box
        
    Returns:
        KPICenterSelection with selected ID and expanded IDs
    """
    
    # Build tree
    tree = KPICenterTreeBuilder(hierarchy_df)
    
    # Apply filters
    if kpi_type_filter:
        tree = tree.filter_by_type(kpi_type_filter)
    
    if allowed_ids:
        tree = tree.filter_by_ids(allowed_ids)
    
    # Build display options
    options, display_to_id, id_to_display = build_tree_display_options(tree, kpi_type_filter)
    
    if not options:
        st.warning("No KPI Centers available for selection")
        return KPICenterSelection(
            selected_id=0,
            selected_name="",
            include_children=False,
            expanded_ids=[],
            children_count=0
        )
    
    # =========================================================================
    # SEARCH FILTER (optional)
    # =========================================================================
    filtered_options = options
    
    if show_search and len(options) > 10:
        search_key = f"{key_prefix}_search"
        search_term = st.text_input(
            "🔍 Search",
            key=search_key,
            placeholder="Type to filter...",
            label_visibility="collapsed"
        )
        
        if search_term:
            search_lower = search_term.lower()
            # Filter options but keep hierarchy (include parents of matches)
            matching_ids = set()
            for display_name, node_id in display_to_id.items():
                node = tree.get_node(node_id)
                if node and search_lower in node.name.lower():
                    matching_ids.add(node_id)
                    # Also include parents
                    current = node
                    while current.parent_id:
                        matching_ids.add(current.parent_id)
                        current = tree.get_node(current.parent_id)
                        if not current:
                            break
            
            filtered_options = [
                opt for opt in options 
                if display_to_id.get(opt) in matching_ids
            ]
            
            if not filtered_options:
                st.caption(f"No matches for '{search_term}'")
                filtered_options = options  # Fall back to all
    
    # =========================================================================
    # MAIN SELECTOR
    # =========================================================================
    st.markdown("**🎯 KPI Center**")
    
    # Initialize session state
    select_key = f"{key_prefix}_select"
    if select_key not in st.session_state:
        # Default to first option
        st.session_state[select_key] = filtered_options[0] if filtered_options else None
    
    # Validate current selection
    current_selection = st.session_state.get(select_key)
    if current_selection not in filtered_options:
        st.session_state[select_key] = filtered_options[0] if filtered_options else None
    
    selected_display = st.selectbox(
        "Select KPI Center",
        options=filtered_options,
        key=select_key,
        label_visibility="collapsed",
        help="Select a single KPI Center. Use 'Include sub-centers' to add children."
    )
    
    # Get selected ID
    selected_id = display_to_id.get(selected_display, 0)
    selected_node = tree.get_node(selected_id)
    
    if not selected_node:
        return KPICenterSelection(
            selected_id=0,
            selected_name="",
            include_children=False,
            expanded_ids=[],
            children_count=0
        )
    
    # =========================================================================
    # INCLUDE SUB-CENTERS TOGGLE
    # =========================================================================
    children_count = tree.count_descendants(selected_id)
    
    # Only show toggle if node has children
    include_children = False
    toggle_key = f"{key_prefix}_include_children"
    
    if children_count > 0:
        # Initialize session state
        if toggle_key not in st.session_state:
            st.session_state[toggle_key] = True  # Default to include children
        
        include_children = st.checkbox(
            f"Include sub-centers ({children_count})",
            key=toggle_key,
            help=f"Include all {children_count} sub-centers under {selected_node.name}"
        )
    
    # =========================================================================
    # SELECTION SUMMARY
    # =========================================================================
    if include_children and children_count > 0:
        expanded_ids = tree.get_all_descendants(selected_id, include_self=True)
        st.caption(f"✅ **{selected_node.name}** + {children_count} sub-centers = {len(expanded_ids)} total")
    else:
        expanded_ids = [selected_id]
        if children_count > 0:
            st.caption(f"📍 **{selected_node.name}** only (excluding {children_count} sub-centers)")
        else:
            st.caption(f"📍 **{selected_node.name}**")
    
    return KPICenterSelection(
        selected_id=selected_id,
        selected_name=selected_node.name,
        include_children=include_children,
        expanded_ids=expanded_ids,
        children_count=children_count
    )


# =============================================================================
# INTEGRATION HELPER
# =============================================================================

def get_kpi_center_selection_ids(
    hierarchy_df: pd.DataFrame,
    kpi_type_filter: str = None,
    allowed_ids: Set[int] = None,
    key_prefix: str = "kpc_sel",
    show_search: bool = True,
) -> Tuple[List[int], List[int], bool]:
    """
    Convenience wrapper that returns IDs in format compatible with existing code.
    
    Returns:
        Tuple of:
        - selected_ids: List with single selected ID
        - expanded_ids: List of all IDs (selected + children if toggled)
        - include_children: Whether children are included
    """
    selection = render_kpi_center_selector(
        hierarchy_df=hierarchy_df,
        kpi_type_filter=kpi_type_filter,
        allowed_ids=allowed_ids,
        key_prefix=key_prefix,
        show_search=show_search
    )
    
    return (
        [selection.selected_id] if selection.selected_id else [],
        selection.expanded_ids,
        selection.include_children
    )
