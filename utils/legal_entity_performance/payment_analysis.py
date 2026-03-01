# utils/legal_entity_performance/payment_analysis.py
"""
Payment & Collection Analysis for Legal Entity Performance.

Uses ACTUAL payment columns from unified_sales_by_legal_entity_view:
  - payment_ratio:          0.0 to 1.0 (invoice-level, applied to each line)
  - payment_status:         'Fully Paid', 'Partially Paid', 'Unpaid', NULL
  - outstanding_amount:     invoice-level local currency (for reference only)
  - total_payment_received: invoice-level local currency (for reference only)
  - due_date:               payment due date (for overdue aging)

USD calculation per line:
  collected_usd  = calculated_invoiced_amount_usd × payment_ratio
  outstanding_usd = calculated_invoiced_amount_usd × (1 - payment_ratio)

This avoids invoice-level deduplication issues since payment_ratio
applies proportionally to each line item.

NOTE: HISTORY data (2014-2024) has payment columns = NULL.
      Analysis only covers rows where payment_status IS NOT NULL.

VERSION: 2.0.0
"""

import logging
from datetime import date
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Aging buckets based on days PAST DUE (due_date), not invoice date
# Negative = not yet due, 0+ = overdue
AGING_BUCKETS_OVERDUE = [
    ('Not Yet Due', -999999, -1),
    ('0-30 days overdue', 0, 30),
    ('31-60 days overdue', 31, 60),
    ('61-90 days overdue', 61, 90),
    ('90+ days overdue', 91, 999999),
]

# Fallback: aging by invoice age (when due_date not available)
AGING_BUCKETS_BY_INV_DATE = [
    ('Current (0-30)', 0, 30),
    ('31-60 days', 31, 60),
    ('61-90 days', 61, 90),
    ('90+ days', 91, 999999),
]

# Alert thresholds
OVERDUE_90_THRESHOLD_USD = 10000     # Alert if 90+ overdue > $10K
COLLECTION_RATE_LOW = 0.70           # Alert if collection rate < 70%
LARGE_UNPAID_THRESHOLD_USD = 50000   # Alert for single customer > $50K outstanding
OVERDUE_SHARE_THRESHOLD = 0.15       # Alert if overdue share > 15%

# Colors for charts
COLORS = {
    'collected': '#28a745',
    'outstanding': '#dc3545',
    'partial': '#ffc107',
    'not_yet_due': '#28a745',
    '0-30': '#ffc107',
    '31-60': '#ff8c00',
    '61-90': '#dc3545',
    '90+': '#8b0000',
}


# =============================================================================
# HELPERS
# =============================================================================

def _fmt_currency(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    elif abs(value) >= 10_000:
        return f"${value / 1_000:,.0f}K"
    else:
        return f"${value:,.0f}"


def _normalize_status(val) -> str:
    """Normalize payment_status to standard category."""
    if pd.isna(val):
        return 'unknown'
    s = str(val).strip().lower()
    if 'fully' in s or s == 'paid':
        return 'fully_paid'
    elif 'partial' in s:
        return 'partially_paid'
    elif 'unpaid' in s or 'open' in s or 'pending' in s:
        return 'unpaid'
    return 'unknown'


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

def analyze_payments(
    sales_df: pd.DataFrame,
    as_of_date: date = None,
) -> Optional[Dict]:
    """
    Analyze payment & collection from sales data using actual payment columns.

    Args:
        sales_df: Filtered sales DataFrame (may contain REALTIME + HISTORY)
        as_of_date: Reference date for aging (default: today)

    Returns:
        Dict with payment metrics, or None if no payment data available.
    """
    if sales_df.empty:
        return None

    # Check required columns
    required = ['payment_status', 'payment_ratio', 'calculated_invoiced_amount_usd']
    missing = [c for c in required if c not in sales_df.columns]
    if missing:
        logger.info(f"Payment analysis skipped — missing columns: {missing}")
        return None

    today = as_of_date or date.today()
    rev_col = 'calculated_invoiced_amount_usd'
    gp_col = 'invoiced_gross_profit_usd'

    # Only analyze rows WITH payment data (REALTIME, not HISTORY)
    df = sales_df[sales_df['payment_status'].notna()].copy()
    if df.empty:
        logger.info("Payment analysis skipped — no rows with payment_status")
        return None

    # Ensure types
    df['payment_ratio'] = pd.to_numeric(df['payment_ratio'], errors='coerce').fillna(0).clip(0, 1)
    df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
    if 'due_date' in df.columns:
        df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce')

    # Normalize status
    df['_status'] = df['payment_status'].apply(_normalize_status)

    # =========================================================================
    # LINE-LEVEL USD CALCULATION (using payment_ratio)
    # =========================================================================
    df['_collected_usd'] = df[rev_col] * df['payment_ratio']
    df['_outstanding_usd'] = df[rev_col] * (1 - df['payment_ratio'])
    if gp_col in df.columns:
        df['_outstanding_gp'] = df[gp_col] * (1 - df['payment_ratio'])

    # Raw status values
    raw_statuses = df['payment_status'].dropna().unique().tolist()

    # =========================================================================
    # 1. SUMMARY
    # =========================================================================
    total_invoiced = df[rev_col].sum()
    total_collected = df['_collected_usd'].sum()
    total_outstanding = df['_outstanding_usd'].sum()
    collection_rate = (total_collected / total_invoiced) if total_invoiced > 0 else 0

    # Count by status (invoice-level dedup for counts)
    has_inv_number = 'inv_number' in df.columns
    if has_inv_number:
        inv_status = df.groupby('inv_number')['_status'].first()
        fully_paid_invoices = (inv_status == 'fully_paid').sum()
        partial_invoices = (inv_status == 'partially_paid').sum()
        unpaid_invoices = (inv_status == 'unpaid').sum()
        total_invoices = len(inv_status)
    else:
        fully_paid_invoices = (df['_status'] == 'fully_paid').sum()
        partial_invoices = (df['_status'] == 'partially_paid').sum()
        unpaid_invoices = (df['_status'] == 'unpaid').sum()
        total_invoices = len(df)

    # Revenue breakdown by status category
    status_rev = df.groupby('_status').agg(
        invoiced=(rev_col, 'sum'),
        collected=('_collected_usd', 'sum'),
        outstanding=('_outstanding_usd', 'sum'),
    ).reset_index()

    summary = {
        'total_invoiced': total_invoiced,
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,
        'collection_rate': collection_rate,
        'fully_paid_invoices': int(fully_paid_invoices),
        'partial_invoices': int(partial_invoices),
        'unpaid_invoices': int(unpaid_invoices),
        'total_invoices': int(total_invoices),
        'invoice_paid_rate': (fully_paid_invoices / total_invoices) if total_invoices > 0 else 0,
        'status_breakdown': status_rev,
        'has_outstanding': total_outstanding > 0,
    }

    # =========================================================================
    # 2. AGING ANALYSIS (outstanding only)
    # =========================================================================
    outstanding_df = df[df['_outstanding_usd'] > 0.01].copy()
    aging_data = _calculate_aging(outstanding_df, today, rev_col, gp_col)

    # =========================================================================
    # 3. BY CUSTOMER (outstanding)
    # =========================================================================
    by_customer = _analyze_by_customer(outstanding_df, today)

    # =========================================================================
    # 4. BY ENTITY
    # =========================================================================
    by_entity = _analyze_by_entity(df, rev_col)

    # =========================================================================
    # 5. BY MONTH (collection trend)
    # =========================================================================
    by_month = _analyze_by_month(df, rev_col)

    return {
        'summary': summary,
        'aging_buckets': aging_data,
        'by_customer': by_customer,
        'by_entity': by_entity,
        'by_month': by_month,
        'raw_statuses': raw_statuses,
        'collection_rate': collection_rate,
        'as_of_date': today,
    }


# =============================================================================
# AGING CALCULATION
# =============================================================================

def _calculate_aging(
    outstanding_df: pd.DataFrame,
    today: date,
    rev_col: str,
    gp_col: str,
) -> pd.DataFrame:
    """
    Calculate aging buckets for outstanding amounts.
    Uses due_date (overdue days) if available, else inv_date (invoice age).
    """
    if outstanding_df.empty:
        return pd.DataFrame(columns=['bucket', 'amount', 'gp', 'count', 'share'])

    df = outstanding_df.copy()
    today_ts = pd.Timestamp(today)

    # Determine aging mode
    has_due_date = 'due_date' in df.columns and df['due_date'].notna().any()

    if has_due_date:
        # Days past due (positive = overdue, negative = not yet due)
        df['_aging_days'] = (today_ts - df['due_date']).dt.days
        buckets = AGING_BUCKETS_OVERDUE
        aging_mode = 'overdue'
    else:
        # Days since invoice (always positive)
        df['_aging_days'] = (today_ts - df['inv_date']).dt.days.clip(lower=0)
        buckets = AGING_BUCKETS_BY_INV_DATE
        aging_mode = 'invoice_age'

    total_outstanding = df['_outstanding_usd'].sum()
    rows = []

    for bucket_name, min_d, max_d in buckets:
        mask = (df['_aging_days'] >= min_d) & (df['_aging_days'] <= max_d)
        bucket_df = df[mask]
        amount = bucket_df['_outstanding_usd'].sum()
        gp = bucket_df['_outstanding_gp'].sum() if '_outstanding_gp' in bucket_df.columns else 0
        count = len(bucket_df)
        share = (amount / total_outstanding) if total_outstanding > 0 else 0

        rows.append({
            'bucket': bucket_name,
            'min_days': min_d,
            'max_days': max_d,
            'amount': amount,
            'gp': gp,
            'count': count,
            'share': share,
        })

    result = pd.DataFrame(rows)
    # Remove empty buckets for cleaner display
    result = result[result['amount'] > 0.01].reset_index(drop=True)
    result.attrs['aging_mode'] = aging_mode
    return result


# =============================================================================
# BY CUSTOMER
# =============================================================================

def _analyze_by_customer(
    outstanding_df: pd.DataFrame,
    today: date,
) -> pd.DataFrame:
    """Top customers by outstanding USD amount."""
    if outstanding_df.empty or 'customer' not in outstanding_df.columns:
        return pd.DataFrame()

    today_ts = pd.Timestamp(today)
    df = outstanding_df.copy()

    # Days overdue (use due_date if available, else inv_date)
    if 'due_date' in df.columns and df['due_date'].notna().any():
        df['_days'] = (today_ts - df['due_date']).dt.days
    else:
        df['_days'] = (today_ts - df['inv_date']).dt.days.clip(lower=0)

    # Deduplicate for invoice count
    has_inv = 'inv_number' in df.columns
    agg_dict = {
        'outstanding': ('_outstanding_usd', 'sum'),
        'max_days': ('_days', 'max'),
        'avg_days': ('_days', 'mean'),
    }
    if has_inv:
        agg_dict['invoices'] = ('inv_number', 'nunique')
    else:
        agg_dict['invoices'] = ('_outstanding_usd', 'count')

    result = df.groupby('customer').agg(**agg_dict).reset_index()
    return result.sort_values('outstanding', ascending=False).head(15).reset_index(drop=True)


# =============================================================================
# BY ENTITY
# =============================================================================

def _analyze_by_entity(df: pd.DataFrame, rev_col: str) -> pd.DataFrame:
    """Collection rate by legal entity."""
    if df.empty or 'legal_entity' not in df.columns:
        return pd.DataFrame()

    result = df.groupby('legal_entity').agg(
        total_invoiced=(rev_col, 'sum'),
        collected=('_collected_usd', 'sum'),
        outstanding=('_outstanding_usd', 'sum'),
    ).reset_index()

    result['collection_rate'] = np.where(
        result['total_invoiced'] > 0,
        result['collected'] / result['total_invoiced'],
        0
    )
    return result.sort_values('total_invoiced', ascending=False).reset_index(drop=True)


# =============================================================================
# BY MONTH (collection trend)
# =============================================================================

def _analyze_by_month(df: pd.DataFrame, rev_col: str) -> pd.DataFrame:
    """Monthly collection rate trend."""
    if df.empty or 'inv_date' not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df['_inv_month'] = df['inv_date'].dt.to_period('M').astype(str)

    result = df.groupby('_inv_month').agg(
        invoiced=(rev_col, 'sum'),
        collected=('_collected_usd', 'sum'),
        outstanding=('_outstanding_usd', 'sum'),
    ).reset_index()
    result.rename(columns={'_inv_month': 'inv_month'}, inplace=True)

    result['collection_rate'] = np.where(
        result['invoiced'] > 0,
        result['collected'] / result['invoiced'],
        0
    )
    return result.sort_values('inv_month').reset_index(drop=True)


# =============================================================================
# EXECUTIVE SUMMARY ALERTS
# =============================================================================

def check_payment_alerts(payment_data: Optional[Dict]) -> List[Dict]:
    """Generate payment alerts for Executive Summary."""
    if not payment_data:
        return []

    summary = payment_data['summary']
    aging = payment_data.get('aging_buckets', pd.DataFrame())
    by_customer = payment_data.get('by_customer', pd.DataFrame())
    alerts = []

    total_outstanding = summary.get('total_outstanding', 0)

    # Skip alerts if nothing outstanding
    if total_outstanding < 100:
        return []

    # 1. High overdue share (replaces collection rate alert — rate is misleading
    #    when AR dataset excludes fully paid invoices)
    if not aging.empty:
        overdue_mask = aging['min_days'] >= 0
        total_overdue = aging.loc[overdue_mask, 'amount'].sum()
        overdue_share = total_overdue / total_outstanding if total_outstanding > 0 else 0
        
        if overdue_share >= OVERDUE_SHARE_THRESHOLD and total_overdue > OVERDUE_90_THRESHOLD_USD:
            unpaid_count = summary.get('unpaid_invoices', 0)
            partial_count = summary.get('partial_invoices', 0)
            alerts.append({
                'severity': 'medium',
                'icon': '💰',
                'message': (
                    f"Overdue chiếm {overdue_share:.0%} tổng công nợ — "
                    f"{_fmt_currency(total_overdue)} / {_fmt_currency(total_outstanding)} "
                    f"({unpaid_count} unpaid + {partial_count} partial)"
                ),
            })

    # 2. Heavy overdue 90+ days
    if not aging.empty:
        bucket_90 = aging[aging['min_days'] >= 91]
        if not bucket_90.empty:
            amount_90 = bucket_90['amount'].sum()
            count_90 = int(bucket_90['count'].sum())
            if amount_90 > OVERDUE_90_THRESHOLD_USD:
                share = amount_90 / total_outstanding if total_outstanding > 0 else 0
                alerts.append({
                    'severity': 'high',
                    'icon': '🔴',
                    'message': (
                        f"Công nợ quá hạn 90+ ngày: {_fmt_currency(amount_90)} "
                        f"({share:.0%} of outstanding, {count_90} line items)"
                    ),
                })

    # 3. Large single-customer outstanding
    if not by_customer.empty:
        large = by_customer[by_customer['outstanding'] >= LARGE_UNPAID_THRESHOLD_USD]
        for _, row in large.head(2).iterrows():
            max_days = int(row['max_days'])
            day_label = f"overdue {max_days}d" if max_days > 0 else f"due in {abs(max_days)}d" if max_days < 0 else "due today"
            alerts.append({
                'severity': 'medium',
                'icon': '💰',
                'message': (
                    f"Customer {row['customer']} — outstanding {_fmt_currency(row['outstanding'])} "
                    f"({int(row['invoices'])} invoices, {day_label})"
                ),
            })

    return alerts


def get_payment_headline(payment_data: Optional[Dict]) -> Optional[str]:
    """One-line payment status for Executive Summary headline."""
    if not payment_data:
        return None

    summary = payment_data['summary']
    outstanding = summary.get('total_outstanding', 0)
    rate = summary.get('collection_rate', 0)

    if outstanding < 100:
        return None

    return f"AR: {_fmt_currency(outstanding)} outstanding ({rate:.0%} collected)"


# =============================================================================
# STREAMLIT RENDERER
# =============================================================================

def render_payment_section(payment_data: Optional[Dict]):
    """
    Render payment/collection analysis section.

    Layout:
      Row 1: 4 summary metrics
      Row 2: Aging chart + detail table  (if outstanding > 0)
      Row 3: Collection trend + top unpaid customers
      Row 4: Collection by entity (if multi-entity)
    """
    if not payment_data:
        st.info("📊 Payment data not available for this period. "
                "Payment tracking is available for 2025+ invoices only.")
        return

    summary = payment_data['summary']
    aging = payment_data.get('aging_buckets', pd.DataFrame())
    by_customer = payment_data.get('by_customer', pd.DataFrame())
    by_entity = payment_data.get('by_entity', pd.DataFrame())
    by_month = payment_data.get('by_month', pd.DataFrame())
    has_outstanding = summary.get('has_outstanding', False)

    # Show raw statuses detected
    raw_statuses = payment_data.get('raw_statuses', [])
    if raw_statuses:
        st.caption(f"Payment statuses in data: {', '.join(raw_statuses)}")

    # -----------------------------------------------------------------
    # ROW 1: Summary Metrics (focused on outstanding, not invoiced totals)
    # -----------------------------------------------------------------
    total_outstanding = summary['total_outstanding']
    unpaid_count = summary['unpaid_invoices'] + summary['partial_invoices']
    
    # Parse aging for overdue / not-yet-due split
    not_yet_due_amount = 0
    total_overdue_amount = 0
    overdue_line_count = 0
    nyd_line_count = 0
    weighted_days_sum = 0
    total_outstanding_for_avg = 0
    
    if not aging.empty and 'min_days' in aging.columns:
        nyd_mask = aging['min_days'] < 0
        not_yet_due_amount = aging.loc[nyd_mask, 'amount'].sum()
        nyd_line_count = int(aging.loc[nyd_mask, 'count'].sum())
        
        overdue_mask = aging['min_days'] >= 0
        total_overdue_amount = aging.loc[overdue_mask, 'amount'].sum()
        overdue_line_count = int(aging.loc[overdue_mask, 'count'].sum())
        
        # Weighted avg days outstanding (midpoint of each bucket × amount)
        for _, row in aging.iterrows():
            mid = (row['min_days'] + min(row['max_days'], 365)) / 2
            if mid > 0:  # Only overdue contributes
                weighted_days_sum += mid * row['amount']
                total_outstanding_for_avg += row['amount']
    
    avg_days = int(weighted_days_sum / total_outstanding_for_avg) if total_outstanding_for_avg > 0 else 0
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "💰 Outstanding",
            _fmt_currency(total_outstanding),
            f"{unpaid_count:,} invoices ({summary['unpaid_invoices']} unpaid · {summary['partial_invoices']} partial)",
            delta_color="off",
        )
    with c2:
        if total_overdue_amount > 0:
            overdue_pct = (total_overdue_amount / total_outstanding * 100) if total_outstanding > 0 else 0
            st.metric(
                "🔴 Overdue",
                _fmt_currency(total_overdue_amount),
                f"{overdue_line_count:,} lines · {overdue_pct:.0f}% of total",
                delta_color="inverse",
            )
        else:
            st.metric("🟢 Overdue", "$0", "No overdue", delta_color="off")
    with c3:
        nyd_pct = (not_yet_due_amount / total_outstanding * 100) if total_outstanding > 0 else 0
        st.metric(
            "🟢 Not Yet Due",
            _fmt_currency(not_yet_due_amount),
            f"{nyd_line_count:,} lines · {nyd_pct:.0f}% of total",
            delta_color="off",
        )
    with c4:
        if avg_days > 0:
            severity = "🔴" if avg_days > 90 else "🟠" if avg_days > 45 else "🟢"
            st.metric(
                f"{severity} Avg Days Overdue",
                f"{avg_days} days",
                f"weighted by amount",
                delta_color="off",
            )
        else:
            st.metric("🟢 Avg Days Overdue", "0 days", "All within terms", delta_color="off")

    # If nothing outstanding, show clean status and skip details
    if not has_outstanding:
        st.success("✅ All invoices fully collected — no outstanding balance")
        return

    # -----------------------------------------------------------------
    # ROW 2: Aging Analysis (only if outstanding > 0)
    # -----------------------------------------------------------------
    if not aging.empty:
        col_aging, col_detail = st.columns([3, 2])

        with col_aging:
            aging_mode = getattr(aging, 'attrs', {}).get('aging_mode', 'invoice_age')
            title = "📅 Aging by Due Date" if aging_mode == 'overdue' else "📅 Aging by Invoice Date"
            st.markdown(f"##### {title}")
            chart = _build_aging_chart(aging)
            st.altair_chart(chart, use_container_width=True)

        with col_detail:
            st.markdown("##### 📋 Aging Detail")
            display = aging.copy()
            display['Amount'] = display['amount'].apply(lambda x: f"${x:,.0f}")
            display['Share'] = display['share'].apply(lambda x: f"{x:.0%}")
            display['Lines'] = display['count'].astype(int)
            st.dataframe(
                display[['bucket', 'Amount', 'Share', 'Lines']].rename(
                    columns={'bucket': 'Aging Bucket'}
                ),
                hide_index=True,
                use_container_width=True,
            )

    # -----------------------------------------------------------------
    # ROW 3: Collection Trend + Top Unpaid Customers
    # -----------------------------------------------------------------
    has_trend = not by_month.empty and len(by_month) >= 2
    has_customers = not by_customer.empty

    if has_trend or has_customers:
        col_left, col_right = st.columns([3, 2])

        if has_trend:
            with col_left:
                st.markdown("##### 📈 Monthly Collection Trend")
                chart = _build_collection_trend_chart(by_month)
                st.altair_chart(chart, use_container_width=True)

        if has_customers:
            with col_right:
                st.markdown("##### 👥 Top Outstanding Customers")
                display_cust = by_customer.head(10).copy()
                display_cust['Outstanding'] = display_cust['outstanding'].apply(lambda x: f"${x:,.0f}")
                # Positive days = overdue, negative = not yet due
                def _fmt_days(d):
                    d = int(d)
                    if d > 0:
                        return f"⚠️ {d}d overdue"
                    elif d < 0:
                        return f"due in {abs(d)}d"
                    return "due today"
                display_cust['Status'] = display_cust['max_days'].apply(_fmt_days)
                display_cust['Inv.'] = display_cust['invoices'].astype(int)
                display_cust['#'] = range(1, len(display_cust) + 1)
                st.dataframe(
                    display_cust[['#', 'customer', 'Outstanding', 'Inv.', 'Status']].rename(
                        columns={'customer': 'Customer'}
                    ),
                    hide_index=True,
                    use_container_width=True,
                    height=min(350, 35 * len(display_cust) + 38),
                )
        elif has_trend:
            with col_right:
                st.info("No individual customer outstanding data available")

    # -----------------------------------------------------------------
    # ROW 4: Collection by Entity
    # -----------------------------------------------------------------
    if not by_entity.empty and len(by_entity) > 1:
        st.markdown("##### 🏢 Collection by Entity")
        display_ent = by_entity.copy()
        display_ent['Invoiced'] = display_ent['total_invoiced'].apply(lambda x: f"${x:,.0f}")
        display_ent['Collected'] = display_ent['collected'].apply(lambda x: f"${x:,.0f}")
        display_ent['Outstanding'] = display_ent['outstanding'].apply(lambda x: f"${x:,.0f}")
        display_ent['Rate'] = display_ent['collection_rate'].apply(lambda x: f"{x:.0%}")
        st.dataframe(
            display_ent[['legal_entity', 'Invoiced', 'Collected', 'Outstanding', 'Rate']].rename(
                columns={'legal_entity': 'Legal Entity'}
            ),
            hide_index=True,
            use_container_width=True,
        )


# =============================================================================
# CHARTS
# =============================================================================

def _build_aging_chart(aging_df: pd.DataFrame) -> alt.Chart:
    """Horizontal bar chart for aging buckets with color coding."""
    df = aging_df.copy()
    df['bucket_order'] = range(len(df))

    # Color: green for not-yet-due, yellow→red for overdue
    color_list = ['#28a745', '#ffc107', '#ff8c00', '#dc3545', '#8b0000']
    domain = df['bucket'].tolist()
    range_colors = color_list[:len(domain)]

    bars = alt.Chart(df).mark_bar().encode(
        y=alt.Y('bucket:N', sort=alt.EncodingSortField(field='bucket_order'),
                title=None, axis=alt.Axis(labelLimit=150)),
        x=alt.X('amount:Q', title='Outstanding (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('bucket:N', scale=alt.Scale(
            domain=domain, range=range_colors
        ), legend=None),
        tooltip=[
            alt.Tooltip('bucket:N', title='Bucket'),
            alt.Tooltip('amount:Q', title='Amount', format='$,.0f'),
            alt.Tooltip('count:Q', title='Line Items'),
            alt.Tooltip('share:Q', title='Share', format='.0%'),
        ]
    )

    text = alt.Chart(df).mark_text(
        align='left', dx=4, fontSize=11
    ).encode(
        y=alt.Y('bucket:N', sort=alt.EncodingSortField(field='bucket_order')),
        x=alt.X('amount:Q'),
        text=alt.Text('amount:Q', format='$,.0f'),
    )

    return (bars + text).properties(height=35 * max(len(df), 2) + 40, title='Outstanding by Aging')


def _build_collection_trend_chart(by_month: pd.DataFrame) -> alt.Chart:
    """Dual-axis: invoiced/collected bars + collection rate line."""
    df = by_month.copy()

    melted = df.melt(
        id_vars=['inv_month', 'collection_rate'],
        value_vars=['invoiced', 'collected'],
        var_name='type', value_name='amount'
    )
    melted['type'] = melted['type'].map({'invoiced': 'Invoiced', 'collected': 'Collected'})

    bars = alt.Chart(melted).mark_bar().encode(
        x=alt.X('inv_month:N', title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('amount:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('type:N', scale=alt.Scale(
            domain=['Invoiced', 'Collected'],
            range=['#aec7e8', '#28a745']
        ), legend=alt.Legend(orient='top', title=None)),
        xOffset='type:N',
        tooltip=[
            alt.Tooltip('inv_month:N', title='Month'),
            alt.Tooltip('type:N', title='Type'),
            alt.Tooltip('amount:Q', title='Amount', format='$,.0f'),
        ]
    )

    line = alt.Chart(df).mark_line(
        color='#800080', strokeWidth=2, point=True
    ).encode(
        x=alt.X('inv_month:N'),
        y=alt.Y('collection_rate:Q', title='Collection Rate',
                axis=alt.Axis(format='.0%')),
        tooltip=[
            alt.Tooltip('inv_month:N', title='Month'),
            alt.Tooltip('collection_rate:Q', title='Rate', format='.0%'),
        ]
    )

    return alt.layer(bars, line).resolve_scale(
        y='independent'
    ).properties(height=280, title='Monthly Collection Trend')