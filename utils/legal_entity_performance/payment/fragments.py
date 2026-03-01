# utils/legal_entity_performance/payment/fragments.py
"""
Streamlit Fragments for Legal Entity Performance — Payment & Collection Tab.

Pattern follows sales_detail/fragments.py:
- payment_tab_fragment: Tab-level @st.fragment with filters
- Sub-tabs: Payment List | Summary & Aging | Customer Analysis

Only analyzes rows with payment data (REALTIME 2025+, not HISTORY).

VERSION: 1.0.0
"""

import logging
from datetime import date, datetime
from typing import Dict
from io import BytesIO
import pandas as pd
import numpy as np
import streamlit as st

from ..payment_analysis import analyze_payments, render_payment_section, _fmt_currency, _normalize_status
from ..export_utils import LegalEntityExport

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def _format_product_display(row) -> str:
    parts = []
    if pd.notna(row.get('pt_code')) and row.get('pt_code'):
        parts.append(str(row['pt_code']))
    if pd.notna(row.get('product_pn')) and row.get('product_pn'):
        parts.append(str(row['product_pn']))
    if pd.notna(row.get('package_size')) and row.get('package_size'):
        parts.append(str(row['package_size']))
    return ' | '.join(parts) if parts else ''


def _format_oc_po(row) -> str:
    oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
    po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
    if oc and po:
        return f"{oc}\n(PO: {po})"
    return oc or po or ''


# =============================================================================
# TAB-LEVEL FRAGMENT
# =============================================================================

@st.fragment
def payment_tab_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    key_prefix: str = "le_payment_tab",
    ar_outstanding_df: pd.DataFrame = None,
):
    """
    Fragment wrapper for Payment & Collection tab.
    
    Dual-mode:
      - All Outstanding AR: shows ALL unpaid/partial invoices regardless of date
      - Period Invoices: shows only invoices within the selected period (original behavior)
    
    Includes filters + sub-tabs (Payment List + Summary & Aging + Customer).
    """
    # Check if we have any payment data at all
    has_period_data = (
        not sales_df.empty
        and 'payment_status' in sales_df.columns
        and sales_df['payment_status'].notna().any()
    )
    has_ar_data = ar_outstanding_df is not None and not ar_outstanding_df.empty
    
    if not has_period_data and not has_ar_data:
        st.info("Payment data not available. Payment tracking is available for 2025+ invoices only.")
        return
    
    # =========================================================================
    # VIEW MODE TOGGLE
    # =========================================================================
    ar_mode = st.radio(
        "View mode",
        options=["📋 All Outstanding AR", "📅 Period Invoices"],
        horizontal=True,
        key=f"{key_prefix}_mode",
        help=(
            "**All Outstanding AR**: All unpaid/partially paid invoices regardless of period — "
            "gives complete AR picture.  \n"
            "**Period Invoices**: Only invoices within the selected date range — "
            "shows collection performance for the period."
        ),
    )
    is_ar_mode = (ar_mode == "📋 All Outstanding AR")
    
    # =========================================================================
    # SELECT SOURCE DATA BASED ON MODE
    # =========================================================================
    if is_ar_mode:
        if not has_ar_data:
            st.warning("AR outstanding data not available. Showing period invoices instead.")
            is_ar_mode = False
            source_df = sales_df
        else:
            source_df = ar_outstanding_df
    else:
        if not has_period_data:
            st.info("No payment data in the selected period. "
                    "Switch to 'All Outstanding AR' to see full AR picture.")
            return
        source_df = sales_df
    
    # Filter rows with payment data
    if 'payment_status' not in source_df.columns:
        st.info("Payment data not available for this dataset.")
        return
    
    pay_df = source_df[source_df['payment_status'].notna()].copy()
    
    # Apply sidebar filters (entity, customer_type) to AR mode
    # so the AR view respects the global sidebar selections
    if is_ar_mode and filter_values:
        entity_ids = filter_values.get('entity_ids', [])
        if entity_ids and 'legal_entity_id' in pay_df.columns:
            pay_df = pay_df[pay_df['legal_entity_id'].isin(entity_ids)]
        
        customer_type = filter_values.get('customer_type', 'All')
        if customer_type != 'All' and 'customer_type' in pay_df.columns:
            pay_df = pay_df[pay_df['customer_type'] == customer_type]
    
    if pay_df.empty:
        st.info("No rows with payment data. "
                "HISTORY data (2014-2024) does not include payment tracking.")
        return

    # Ensure computed columns
    pay_df['payment_ratio'] = pd.to_numeric(pay_df.get('payment_ratio', 0), errors='coerce').fillna(0).clip(0, 1)
    rev_col = 'calculated_invoiced_amount_usd'
    pay_df['collected_usd'] = pay_df[rev_col] * pay_df['payment_ratio']
    pay_df['outstanding_usd'] = pay_df[rev_col] * (1 - pay_df['payment_ratio'])

    if 'due_date' in pay_df.columns:
        pay_df['due_date'] = pd.to_datetime(pay_df['due_date'], errors='coerce')
    pay_df['inv_date'] = pd.to_datetime(pay_df['inv_date'], errors='coerce')

    total_count = len(pay_df)

    # =========================================================================
    # AR CONTEXT BANNER (dual-mode awareness)
    # =========================================================================
    if is_ar_mode and filter_values:
        start_date = filter_values.get('start_date')
        end_date = filter_values.get('end_date')
        total_ar_outstanding = pay_df['outstanding_usd'].sum()
        
        if start_date and end_date and total_ar_outstanding > 0:
            period_mask = (
                (pay_df['inv_date'] >= pd.Timestamp(start_date)) &
                (pay_df['inv_date'] <= pd.Timestamp(end_date))
            )
            in_period_outstanding = pay_df.loc[period_mask, 'outstanding_usd'].sum()
            carried_over = total_ar_outstanding - in_period_outstanding
            
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                st.metric(
                    "📋 Total AR Outstanding",
                    f"${total_ar_outstanding:,.0f}",
                    delta=f"{len(pay_df):,} lines",
                    delta_color="off",
                )
            with bc2:
                pct_current = (in_period_outstanding / total_ar_outstanding * 100) if total_ar_outstanding > 0 else 0
                st.metric(
                    "📅 Current Period",
                    f"${in_period_outstanding:,.0f}",
                    delta=f"{pct_current:.0f}% of total",
                    delta_color="off",
                )
            with bc3:
                pct_prior = (carried_over / total_ar_outstanding * 100) if total_ar_outstanding > 0 else 0
                st.metric(
                    "⏪ Carried Over (Prior Periods)",
                    f"${carried_over:,.0f}",
                    delta=f"{pct_prior:.0f}% of total",
                    delta_color="inverse" if carried_over > 0 else "off",
                )
            st.divider()

    # =========================================================================
    # FILTERS ROW
    # =========================================================================
    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)

    with col_f1:
        st.markdown("**Payment Status**")
        status_options = sorted(pay_df['payment_status'].dropna().unique().tolist())
        selected_statuses = st.multiselect(
            "Status", status_options,
            key=f"{key_prefix}_status", placeholder="All statuses",
            label_visibility="collapsed"
        )

    with col_f2:
        _lbl2, _excl2 = st.columns([3, 1])
        with _lbl2:
            st.markdown("**Customer**")
        with _excl2:
            excl_customer = st.checkbox("Excl", key=f"{key_prefix}_excl_customer")
        customer_options = sorted(pay_df['customer'].dropna().unique().tolist())
        selected_customers = st.multiselect(
            "Customer", customer_options,
            key=f"{key_prefix}_customer", placeholder="Choose options",
            label_visibility="collapsed"
        )

    with col_f3:
        st.markdown("**Legal Entity**")
        entity_options = sorted(pay_df['legal_entity'].dropna().unique().tolist()) if 'legal_entity' in pay_df.columns else []
        selected_entities = st.multiselect(
            "Entity", entity_options,
            key=f"{key_prefix}_entity", placeholder="All entities",
            label_visibility="collapsed"
        )

    with col_f4:
        st.markdown("**Min Outstanding ($)**")
        min_outstanding = st.number_input(
            "Min Outstanding",
            min_value=0, value=0, step=1000,
            key=f"{key_prefix}_min_outstanding",
            label_visibility="collapsed"
        )

    with col_f5:
        st.markdown("**Overdue Only**")
        overdue_only = st.checkbox(
            "Show only overdue invoices", key=f"{key_prefix}_overdue_only"
        )

    # =========================================================================
    # APPLY FILTERS
    # =========================================================================
    filtered_df = pay_df.copy()

    if selected_statuses:
        filtered_df = filtered_df[filtered_df['payment_status'].isin(selected_statuses)]

    if selected_customers:
        if excl_customer:
            filtered_df = filtered_df[~filtered_df['customer'].isin(selected_customers)]
        else:
            filtered_df = filtered_df[filtered_df['customer'].isin(selected_customers)]

    if selected_entities and 'legal_entity' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['legal_entity'].isin(selected_entities)]

    if min_outstanding > 0:
        filtered_df = filtered_df[filtered_df['outstanding_usd'] >= min_outstanding]

    if overdue_only and 'due_date' in filtered_df.columns:
        today = pd.Timestamp(date.today())
        filtered_df = filtered_df[
            (filtered_df['due_date'].notna()) &
            (filtered_df['due_date'] < today) &
            (filtered_df['outstanding_usd'] > 0.01)
        ]

    # Filter summary
    active_filters = []
    if selected_statuses:
        active_filters.append(f"Status: {', '.join(selected_statuses)}")
    if selected_customers:
        mode = "excl" if excl_customer else "incl"
        active_filters.append(f"Customer: {len(selected_customers)} ({mode})")
    if selected_entities:
        active_filters.append(f"Entity: {', '.join(selected_entities)}")
    if min_outstanding > 0:
        active_filters.append(f"Outstanding ≥ ${min_outstanding:,.0f}")
    if overdue_only:
        active_filters.append("Overdue only")

    if active_filters:
        st.caption(f"🔍 Active filters: {' | '.join(active_filters)}")

    st.divider()

    # =========================================================================
    # SUB-TABS
    # =========================================================================
    tab_summary, tab_list, tab_customer = st.tabs([
        "📊 Summary & Aging", "📋 Payment List", "👥 Customer Analysis"
    ])

    with tab_summary:
        payment_summary_fragment(
            pay_df=filtered_df,
            fragment_key=f"{key_prefix}_summary",
        )

    with tab_list:
        payment_list_fragment(
            pay_df=filtered_df,
            fragment_key=f"{key_prefix}_list",
            total_count=total_count
        )

    with tab_customer:
        _customer_analysis_section(
            pay_df=filtered_df,
            fragment_key=f"{key_prefix}_cust_analysis",
        )


# =============================================================================
# PAYMENT LIST FRAGMENT
# =============================================================================

def payment_list_fragment(
    pay_df: pd.DataFrame,
    fragment_key: str = "le_pay_list",
    total_count: int = None,
):
    """Payment transaction list with payment-focused columns."""
    if pay_df.empty:
        st.info("No payment data for selected filters")
        return

    original_count = total_count if total_count is not None else len(pay_df)
    rev_col = 'calculated_invoiced_amount_usd'

    # =========================================================================
    # SUMMARY METRICS (focused on outstanding breakdown, not misleading totals)
    # =========================================================================
    total_outstanding = pay_df['outstanding_usd'].sum()
    inv_count = pay_df['inv_number'].nunique() if 'inv_number' in pay_df.columns else len(pay_df)

    # Count by status
    status_counts = pay_df['payment_status'].value_counts()
    unpaid_lines = status_counts.get('Unpaid', 0)
    partial_lines = status_counts.get('Partially Paid', 0)
    paid_lines = status_counts.get('Fully Paid', 0)

    # Overdue vs Not Yet Due
    today_ts = pd.Timestamp(date.today())
    overdue_amount = 0
    nyd_amount = 0
    overdue_lines = 0
    if 'due_date' in pay_df.columns:
        overdue_mask = (
            (pay_df['due_date'].notna()) &
            (pay_df['due_date'] < today_ts) &
            (pay_df['outstanding_usd'] > 0.01)
        )
        overdue_amount = pay_df.loc[overdue_mask, 'outstanding_usd'].sum()
        overdue_lines = int(overdue_mask.sum())
        nyd_amount = total_outstanding - overdue_amount

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("💰 Outstanding", f"${total_outstanding:,.0f}",
                  delta=f"{inv_count:,} invoices", delta_color="off")
    with c2:
        if overdue_amount > 0:
            overdue_pct = (overdue_amount / total_outstanding * 100) if total_outstanding > 0 else 0
            st.metric("🔴 Overdue", f"${overdue_amount:,.0f}",
                      delta=f"{overdue_lines:,} lines · {overdue_pct:.0f}%",
                      delta_color="inverse")
        else:
            st.metric("🟢 Overdue", "$0", delta="None", delta_color="off")
    with c3:
        nyd_pct = (nyd_amount / total_outstanding * 100) if total_outstanding > 0 else 0
        st.metric("🟢 Not Yet Due", f"${nyd_amount:,.0f}",
                  delta=f"{nyd_pct:.0f}% of total", delta_color="off")
    with c4:
        st.metric("🟡 Partial", f"{partial_lines:,} lines", delta_color="off")
    with c5:
        st.metric("🔴 Unpaid", f"{unpaid_lines:,} lines", delta_color="off")

    st.divider()

    # =========================================================================
    # SORT OPTIONS
    # =========================================================================
    col_sort, col_order, col_limit = st.columns([2, 1, 1])
    with col_sort:
        sort_options = {
            'Outstanding (high→low)': ('outstanding_usd', False),
            'Invoice Date (newest)': ('inv_date', False),
            'Invoice Date (oldest)': ('inv_date', True),
            'Revenue (high→low)': (rev_col, False),
            'Due Date (oldest)': ('due_date', True),
        }
        sort_label = st.selectbox(
            "Sort by", list(sort_options.keys()),
            key=f"{fragment_key}_sort", label_visibility="collapsed"
        )
    with col_order:
        st.markdown("")  # spacer
    with col_limit:
        row_limit = st.selectbox(
            "Show rows", [100, 250, 500, 1000],
            key=f"{fragment_key}_limit", label_visibility="collapsed"
        )

    sort_col, sort_asc = sort_options[sort_label]

    # =========================================================================
    # PREPARE DISPLAY DATA
    # =========================================================================
    display_df = pay_df.copy()

    # Sort
    if sort_col in display_df.columns:
        display_df = display_df.sort_values(sort_col, ascending=sort_asc, na_position='last')

    # Format product/OC display
    display_df['product_display'] = display_df.apply(_format_product_display, axis=1)
    if 'oc_number' in display_df.columns:
        display_df['oc_po_display'] = display_df.apply(_format_oc_po, axis=1)

    # Overdue days calculation
    today = pd.Timestamp(date.today())
    if 'due_date' in display_df.columns:
        display_df['days_overdue'] = (today - display_df['due_date']).dt.days
    else:
        display_df['days_overdue'] = (today - display_df['inv_date']).dt.days

    # =========================================================================
    # DISPLAY COLUMNS
    # =========================================================================
    display_columns = [
        'inv_date', 'inv_number', 'oc_po_display',
        'legal_entity', 'customer', 'customer_type',
        'product_display', 'brand',
        rev_col,
        'payment_status', 'payment_ratio',
        'collected_usd', 'outstanding_usd',
        'due_date', 'days_overdue',
    ]
    available_cols = [c for c in display_columns if c in display_df.columns]

    st.markdown(f"**Showing {min(row_limit, len(display_df)):,} of {len(display_df):,} lines** "
                f"({original_count:,} total before filters)")

    detail = display_df[available_cols].head(row_limit).copy()

    # Pre-format currency columns
    for col in [rev_col, 'collected_usd', 'outstanding_usd']:
        if col in detail.columns:
            detail[col] = detail[col].apply(
                lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
            )
    if 'payment_ratio' in detail.columns:
        detail['payment_ratio'] = detail['payment_ratio'].apply(
            lambda x: f"{x:.0%}" if pd.notna(x) else "0%"
        )

    column_config = {
        'inv_date': st.column_config.DateColumn("Inv Date", help="Invoice date"),
        'inv_number': st.column_config.TextColumn("Invoice#", help="Invoice number"),
        'oc_po_display': st.column_config.TextColumn("OC / PO", width="medium"),
        'legal_entity': st.column_config.TextColumn("Entity"),
        'customer': st.column_config.TextColumn("Customer", width="medium"),
        'customer_type': st.column_config.TextColumn("Type"),
        'product_display': st.column_config.TextColumn("Product", width="large"),
        'brand': st.column_config.TextColumn("Brand"),
        rev_col: st.column_config.TextColumn("Revenue", help="Invoiced amount (USD)"),
        'payment_status': st.column_config.TextColumn("Status", help="Payment status"),
        'payment_ratio': st.column_config.TextColumn("Paid%", help="Payment ratio"),
        'collected_usd': st.column_config.TextColumn("Collected", help="Collected amount (USD)"),
        'outstanding_usd': st.column_config.TextColumn("Outstanding", help="Outstanding (USD)"),
        'due_date': st.column_config.DateColumn("Due Date", help="Payment due date"),
        'days_overdue': st.column_config.NumberColumn(
            "Days O/D", help="Days overdue (negative = not yet due)",
            format="%d",
        ),
    }

    st.dataframe(
        detail,
        column_config=column_config,
        width="stretch",
        hide_index=True,
        height=500,
    )

    # Legend
    with st.expander("📖 Column Legend"):
        st.markdown("""
| Column | Description |
|--------|-------------|
| **Revenue** | Line item invoiced amount (USD) |
| **Status** | Fully Paid / Partially Paid / Unpaid |
| **Paid%** | `payment_ratio` from invoice (0% → 100%) |
| **Collected** | `Revenue × Paid%` |
| **Outstanding** | `Revenue × (1 - Paid%)` |
| **Due Date** | Payment due date (from invoice terms) |
| **Days O/D** | Days overdue. Positive = past due. Negative = not yet due. |
        """)

    # Export
    _render_export_button(pay_df, fragment_key)


# =============================================================================
# PAYMENT SUMMARY FRAGMENT (reuses payment_analysis.render_payment_section)
# =============================================================================

def payment_summary_fragment(
    pay_df: pd.DataFrame,
    fragment_key: str = "le_pay_summary",
):
    """Summary & Aging view — delegates to payment_analysis.render_payment_section."""
    if pay_df.empty:
        st.info("No payment data for selected filters")
        return

    payment_data = analyze_payments(pay_df)
    render_payment_section(payment_data)


# =============================================================================
# CUSTOMER ANALYSIS SECTION
# =============================================================================

def _customer_analysis_section(
    pay_df: pd.DataFrame,
    fragment_key: str = "le_pay_cust",
):
    """
    Customer-level payment analysis.
    Shows: collection rate by customer, outstanding breakdown, payment behavior.
    """
    if pay_df.empty:
        st.info("No data for customer analysis")
        return

    rev_col = 'calculated_invoiced_amount_usd'

    # =========================================================================
    # CUSTOMER SUMMARY TABLE
    # =========================================================================
    st.subheader("👥 Customer Payment Summary")

    has_inv = 'inv_number' in pay_df.columns

    agg_dict = {
        'invoiced': (rev_col, 'sum'),
        'collected': ('collected_usd', 'sum'),
        'outstanding': ('outstanding_usd', 'sum'),
    }
    if has_inv:
        agg_dict['invoices'] = ('inv_number', 'nunique')
    else:
        agg_dict['invoices'] = (rev_col, 'count')

    cust_df = pay_df.groupby('customer').agg(**agg_dict).reset_index()
    cust_df['rate'] = np.where(
        cust_df['invoiced'] > 0,
        cust_df['collected'] / cust_df['invoiced'],
        0
    )

    # Add overdue info
    today = pd.Timestamp(date.today())
    if 'due_date' in pay_df.columns:
        overdue_df = pay_df[
            (pay_df['outstanding_usd'] > 0.01) &
            (pay_df['due_date'].notna()) &
            (pay_df['due_date'] < today)
        ]
    else:
        overdue_df = pd.DataFrame()

    if not overdue_df.empty:
        overdue_by_cust = overdue_df.groupby('customer').agg(
            overdue_amount=('outstanding_usd', 'sum'),
            overdue_lines=('outstanding_usd', 'count'),
        ).reset_index()
        cust_df = cust_df.merge(overdue_by_cust, on='customer', how='left')
        cust_df['overdue_amount'] = cust_df['overdue_amount'].fillna(0)
        cust_df['overdue_lines'] = cust_df['overdue_lines'].fillna(0).astype(int)
    else:
        cust_df['overdue_amount'] = 0
        cust_df['overdue_lines'] = 0

    # Sort
    sort_by = st.selectbox(
        "Sort by",
        ['Outstanding (high→low)', 'Invoiced (high→low)', 'Collection Rate (low→high)', 'Overdue (high→low)'],
        key=f"{fragment_key}_sort",
    )
    sort_map = {
        'Outstanding (high→low)': ('outstanding', False),
        'Invoiced (high→low)': ('invoiced', False),
        'Collection Rate (low→high)': ('rate', True),
        'Overdue (high→low)': ('overdue_amount', False),
    }
    s_col, s_asc = sort_map[sort_by]
    cust_df = cust_df.sort_values(s_col, ascending=s_asc).reset_index(drop=True)

    # Format for display
    display = cust_df.copy()
    display['#'] = range(1, len(display) + 1)
    display['Invoiced'] = display['invoiced'].apply(lambda x: f"${x:,.0f}")
    display['Collected'] = display['collected'].apply(lambda x: f"${x:,.0f}")
    display['Outstanding'] = display['outstanding'].apply(lambda x: f"${x:,.0f}")
    display['Rate'] = display['rate'].apply(lambda x: f"{x:.0%}")
    display['Overdue'] = display.apply(
        lambda r: f"${r['overdue_amount']:,.0f} ({int(r['overdue_lines'])} lines)" if r['overdue_amount'] > 0 else "—",
        axis=1
    )
    display['Inv.'] = display['invoices'].astype(int)

    st.dataframe(
        display[['#', 'customer', 'Inv.', 'Invoiced', 'Collected', 'Outstanding', 'Rate', 'Overdue']].rename(
            columns={'customer': 'Customer'}
        ),
        hide_index=True,
        use_container_width=True,
        height=min(600, 35 * len(display) + 38),
    )

    # =========================================================================
    # STATUS DISTRIBUTION BY CUSTOMER (top 10)
    # =========================================================================
    if len(cust_df) > 1:
        st.subheader("📊 Payment Status Distribution")
        st.caption("Top 10 customers by revenue — stacked bar: Collected vs Outstanding")

        import altair as alt

        top10 = cust_df.nlargest(10, 'invoiced').copy()
        melted = top10.melt(
            id_vars=['customer'],
            value_vars=['collected', 'outstanding'],
            var_name='type', value_name='amount'
        )
        melted['type'] = melted['type'].map({'collected': 'Collected', 'outstanding': 'Outstanding'})

        chart = alt.Chart(melted).mark_bar().encode(
            y=alt.Y('customer:N', sort='-x', title=None, axis=alt.Axis(labelLimit=200)),
            x=alt.X('amount:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
            color=alt.Color('type:N', scale=alt.Scale(
                domain=['Collected', 'Outstanding'],
                range=['#28a745', '#dc3545']
            ), legend=alt.Legend(orient='top', title=None)),
            order=alt.Order('type:N', sort='ascending'),
            tooltip=[
                alt.Tooltip('customer:N', title='Customer'),
                alt.Tooltip('type:N', title='Type'),
                alt.Tooltip('amount:Q', title='Amount', format='$,.0f'),
            ]
        ).properties(height=350)

        st.altair_chart(chart, use_container_width=True)

    # Export
    _render_export_button(pay_df, fragment_key)


# =============================================================================
# SHARED EXPORT
# =============================================================================

def _render_export_button(pay_df: pd.DataFrame, fragment_key: str):
    """Export payment data to Excel."""
    if st.button("📥 Export Payment Data", key=f"{fragment_key}_export"):
        export_columns = {
            'inv_date': 'Invoice Date',
            'inv_number': 'Invoice#',
            'oc_number': 'OC#',
            'customer_po_number': 'Customer PO',
            'legal_entity': 'Legal Entity',
            'customer': 'Customer',
            'customer_type': 'Type',
            'product_pn': 'Product',
            'brand': 'Brand',
            'calculated_invoiced_amount_usd': 'Revenue (USD)',
            'invoiced_gross_profit_usd': 'GP (USD)',
            'payment_status': 'Payment Status',
            'payment_ratio': 'Payment Ratio',
            'collected_usd': 'Collected (USD)',
            'outstanding_usd': 'Outstanding (USD)',
            'due_date': 'Due Date',
            'payment_term': 'Payment Term',
        }

        export_df = pay_df.copy()
        available = {k: v for k, v in export_columns.items() if k in export_df.columns}
        export_df = export_df[list(available.keys())].rename(columns=available)

        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='Payment Collection', index=False)

        st.download_button(
            label="⬇️ Download Payment Data",
            data=buffer.getvalue(),
            file_name=f"le_payment_collection_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )