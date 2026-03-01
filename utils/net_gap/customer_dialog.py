# utils/net_gap/customer_dialog.py

"""
Simplified Customer Impact Dialog
"""

import streamlit as st
import pandas as pd
from typing import Optional
import logging
from datetime import datetime
import io

from .state import get_state
from .formatters import GAPFormatter
from .components import render_pagination

logger = logging.getLogger(__name__)


@st.dialog("Customer Impact Analysis", width="large")
def show_customer_dialog():
    """Display customer impact analysis in dialog"""
    
    state = get_state()
    formatter = GAPFormatter()
    
    # Get result from state
    result = state.get_result()
    
    if not result or not result.customer_impact or result.customer_impact.is_empty():
        st.warning("No customer impact data available")
        st.info("This occurs when:\n- No shortage items found\n- No demand data available")
        if st.button("Close", use_container_width=True):
            if 'show_customer_dialog' in st.session_state:
                del st.session_state['show_customer_dialog']
            st.rerun()
        return
    
    # Get customer data
    customer_data = result.customer_impact.customer_df
    
    if customer_data.empty:
        st.warning("No affected customers found")
        if st.button("Close", use_container_width=True):
            if 'show_customer_dialog' in st.session_state:
                del st.session_state['show_customer_dialog']
            st.rerun()
        return
    
    # Header metrics
    st.markdown("### 👥 Customer Impact Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Customers", f"{result.customer_impact.affected_count:,}")
    
    with col2:
        st.metric("At Risk", formatter.format_currency(
            result.customer_impact.at_risk_value, abbreviate=True
        ))
    
    with col3:
        st.metric("Shortage Qty", formatter.format_number(
            result.customer_impact.shortage_qty
        ))
    
    with col4:
        # Export button
        excel_data = export_customer_data(customer_data, formatter)
        if excel_data:
            st.download_button(
                "📥 Export",
                excel_data,
                f"customers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    
    st.divider()
    
    # Search and filter
    search = st.text_input("Search customers", placeholder="Name or code...", key="cust_search")
    
    # Filter data
    if search:
        filtered = customer_data[
            customer_data['customer'].str.contains(search, case=False, na=False) |
            customer_data['customer_code'].astype(str).str.contains(search, case=False, na=False)
        ]
    else:
        filtered = customer_data
    
    if filtered.empty:
        st.info("No customers match search")
    else:
        # Display customers
        st.caption(f"Showing {len(filtered)} customers")
        display_customer_list(filtered, formatter, state)
    
    st.divider()
    
    # Close button
    if st.button("✅ Close", type="primary", use_container_width=True):
        # Clear the dialog flag before rerun
        if 'show_customer_dialog' in st.session_state:
            del st.session_state['show_customer_dialog']
        st.rerun()


def display_customer_list(df: pd.DataFrame, formatter: GAPFormatter, state):
    """Display paginated customer list"""
    
    # Pagination settings
    items_per_page = 10
    current_page = state.get_dialog_page()
    total_pages = max(1, (len(df) + items_per_page - 1) // items_per_page)
    
    # Ensure valid page
    page = min(current_page, total_pages)
    
    # Get page data
    start = (page - 1) * items_per_page
    end = min(start + items_per_page, len(df))
    page_data = df.iloc[start:end]
    
    # Urgency indicators
    urgency_icons = {
        'OVERDUE': '🔴',
        'URGENT': '🟠',
        'UPCOMING': '🟡',
        'FUTURE': '🟢'
    }
    
    # Display each customer
    for _, row in page_data.iterrows():
        icon = urgency_icons.get(row.get('urgency', ''), '⚪')
        
        with st.expander(
            f"{icon} **{row['customer']}** ({row['customer_code']}) - "
            f"{row['product_count']} products affected",
            expanded=False
        ):
            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Required", formatter.format_number(row['total_required']))
            with col2:
                st.metric("Shortage", formatter.format_number(row['total_shortage']))
            with col3:
                st.metric("At Risk", formatter.format_currency(row['at_risk_value']))
            with col4:
                st.metric("Urgency", row.get('urgency', 'N/A'))
            
            # Product details (if available)
            if 'products' in row and row['products']:
                st.divider()
                st.caption("**Affected Products:**")
                
                products = row['products'][:10]  # Show max 10
                
                for i, prod in enumerate(products, 1):
                    cols = st.columns([0.5, 3, 1.5, 1.5, 1.5])
                    
                    with cols[0]:
                        st.text(str(i))
                    with cols[1]:
                        st.text(f"{prod.get('pt_code', '')} - {prod.get('product_name', '')[:30]}")
                    with cols[2]:
                        st.text(f"Qty: {prod.get('shortage_quantity', 0):.0f}")
                    with cols[3]:
                        st.text(formatter.format_currency(prod.get('at_risk_value', 0), abbreviate=True))
                    with cols[4]:
                        coverage = prod.get('coverage', 0)
                        color = "🔴" if coverage < 50 else "🟡" if coverage < 80 else "🟢"
                        st.text(f"{color} {coverage:.0f}%")
                
                if len(row['products']) > 10:
                    st.caption(f"... and {len(row['products']) - 10} more products")
    
    # Pagination
    if total_pages > 1:
        new_page = render_pagination(page, total_pages, key_prefix="dlg")
        if new_page != page:
            state.set_dialog_page(new_page, total_pages)
            st.rerun()


def export_customer_data(df: pd.DataFrame, formatter: GAPFormatter) -> Optional[bytes]:
    """Export customer data to Excel"""
    
    try:
        output = io.BytesIO()
        
        # Prepare export data
        export_df = df[[
            'customer', 'customer_code', 'product_count',
            'total_required', 'total_shortage',
            'total_demand_value', 'at_risk_value',
            'urgency'
        ]].copy()
        
        # Format columns
        export_df.columns = [
            'Customer', 'Code', 'Products',
            'Required Qty', 'Shortage Qty',
            'Demand Value', 'At Risk Value',
            'Urgency'
        ]
        
        # Write to Excel
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='Customer Impact', index=False)
            
            # Auto-adjust columns
            worksheet = writer.sheets['Customer Impact']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                worksheet.column_dimensions[column_letter].width = min(max_length + 2, 40)
        
        output.seek(0)
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return None