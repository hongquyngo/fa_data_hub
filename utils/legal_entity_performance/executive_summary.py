# utils/legal_entity_performance/executive_summary.py
"""
Executive Summary Generator for Legal Entity Performance.
Auto-generates text summary + alerts from existing processed data.

Designed for CEO/leadership "5-second test":
- Headline metrics in one line
- Auto-detected alerts requiring attention
- Positive highlights for balance
- No additional SQL queries — pure Pandas on cached data

VERSION: 1.0.0
"""

import logging
from datetime import date
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import streamlit as st

logger = logging.getLogger(__name__)


# =============================================================================
# ALERT THRESHOLDS (tunable)
# =============================================================================
MARGIN_DROP_THRESHOLD_PP = 1.5      # Alert if GP% drops > N percentage points vs LY
CUSTOMER_DECLINE_THRESHOLD = 0.25   # Alert if top customer revenue declines > 25%
CUSTOMER_INACTIVE_DAYS = 45         # Alert if major customer hasn't ordered in N days
CONCENTRATION_THRESHOLD = 0.60      # Alert if top 3 customers > 60% of revenue
EXTERNAL_DECLINE_THRESHOLD = 0.10   # Alert if External revenue declines > 10% vs LY
INTERNAL_SHARE_WARNING = 0.40       # Alert if Internal share exceeds 40% of total


# =============================================================================
# FORMATTING HELPERS
# =============================================================================

def _fmt_currency(value: float) -> str:
    """$1.2M / $850K / $1,234"""
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    elif abs(value) >= 10_000:
        return f"${value / 1_000:,.0f}K"
    else:
        return f"${value:,.0f}"


def _fmt_delta(pct: Optional[float]) -> str:
    if pct is None:
        return ""
    return f"{pct:+.1f}%"


# =============================================================================
# MAIN GENERATOR
# =============================================================================

def generate_executive_summary(
    overview_metrics: Dict,
    yoy_metrics: Optional[Dict],
    pipeline_metrics: Optional[Dict],
    sales_df: pd.DataFrame,
    prev_sales_df: pd.DataFrame = None,
    active_filters: Dict = None,
    complex_kpis: Dict = None,
    payment_data: Dict = None,
    ar_payment_data: Dict = None,
) -> Dict:
    """
    Generate complete executive summary from existing processed data.

    Returns dict with:
        period_label, headline, alerts[], highlights[], has_alerts,
        customer_type_breakdown, payment_data, ar_payment_data
    
    Args:
        payment_data: Payment analysis from period-filtered sales (collection performance)
        ar_payment_data: Payment analysis from ALL outstanding AR (total AR picture)
    """
    filters = active_filters or {}

    period_label = _build_period_label(filters)
    headline = _build_headline(overview_metrics, yoy_metrics, pipeline_metrics, ar_payment_data or payment_data)

    # Collect alerts (ordered by severity)
    alerts = []
    alerts.extend(_check_overdue_alerts(pipeline_metrics))
    alerts.extend(_check_margin_alerts(overview_metrics, yoy_metrics, sales_df, prev_sales_df))
    alerts.extend(_check_external_revenue_alerts(sales_df, prev_sales_df))
    alerts.extend(_check_customer_decline_alerts(sales_df, prev_sales_df))
    alerts.extend(_check_inactive_customer_alerts(sales_df))
    alerts.extend(_check_concentration_alerts(sales_df))

    # Payment/collection alerts — use ALL AR data for more complete alerts
    ar_data_for_alerts = ar_payment_data or payment_data
    if ar_data_for_alerts:
        from .payment_analysis import check_payment_alerts
        alerts.extend(check_payment_alerts(ar_data_for_alerts))

    highlights = _build_highlights(overview_metrics, yoy_metrics, complex_kpis, sales_df, prev_sales_df)

    # Customer type breakdown (External vs Internal)
    customer_type_breakdown = _build_customer_type_breakdown(sales_df, prev_sales_df)

    return {
        'period_label': period_label,
        'headline': headline,
        'alerts': alerts,
        'highlights': highlights,
        'has_alerts': len(alerts) > 0,
        'customer_type_breakdown': customer_type_breakdown,
        'payment_data': payment_data,
        'ar_payment_data': ar_payment_data,
    }


# =============================================================================
# HEADLINE BUILDER
# =============================================================================

def _build_period_label(filters: Dict) -> str:
    period_type = filters.get('period_type', 'YTD')
    year = filters.get('year', date.today().year)
    start = filters.get('start_date')
    end = filters.get('end_date')

    if period_type == 'Custom' and start and end:
        return f"{start.strftime('%d %b')} — {end.strftime('%d %b %Y')}"
    elif period_type == 'QTD' and start:
        q = (start.month - 1) // 3 + 1
        return f"Q{q} {year}"
    elif period_type == 'MTD' and start:
        return f"{start.strftime('%B')} {year}"
    elif period_type == 'LY':
        return f"Full Year {year}"
    return f"YTD {year}"


def _build_headline(
    metrics: Dict,
    yoy: Optional[Dict],
    pipeline: Optional[Dict],
    payment_data: Optional[Dict] = None,
) -> str:
    """One-line: Revenue (+YoY%) | GP (margin%) | Backlog (N orders) | AR outstanding"""
    parts = []

    # Revenue
    rev = metrics.get('total_revenue', 0)
    rev_str = f"Revenue: {_fmt_currency(rev)}"
    if yoy and yoy.get('revenue_delta_pct') is not None:
        rev_str += f" ({_fmt_delta(yoy['revenue_delta_pct'])} YoY)"
    parts.append(rev_str)

    # GP + margin
    gp = metrics.get('total_gp', 0)
    gp_pct = metrics.get('gp_percent', 0)
    parts.append(f"GP: {_fmt_currency(gp)} ({gp_pct:.1f}%)")

    # Backlog
    if pipeline:
        summary = pipeline.get('summary', {})
        bl_rev = summary.get('total_backlog_revenue', 0)
        bl_orders = summary.get('backlog_orders', 0)
        if bl_orders > 0:
            parts.append(f"Backlog: {_fmt_currency(bl_rev)} ({bl_orders} orders)")

    # AR (accounts receivable) — show outstanding only, no collection rate
    # because AR dataset excludes fully paid invoices, making rate misleading
    if payment_data:
        ar_summary = payment_data.get('summary', {})
        ar_outstanding = ar_summary.get('total_outstanding', 0)
        if ar_outstanding > 100:
            parts.append(f"AR: {_fmt_currency(ar_outstanding)} outstanding")

    return " | ".join(parts)


# =============================================================================
# ALERT CHECKS
# =============================================================================

def _check_overdue_alerts(pipeline: Optional[Dict]) -> List[Dict]:
    if not pipeline:
        return []
    summary = pipeline.get('summary', {})
    overdue_orders = summary.get('overdue_orders', 0)
    overdue_rev = summary.get('overdue_revenue', 0)
    if overdue_orders > 0:
        return [{
            'severity': 'high',
            'icon': '🔴',
            'message': (
                f"{overdue_orders} orders overdue (past ETD), "
                f"total value {_fmt_currency(overdue_rev)} — cần follow-up delivery"
            ),
        }]
    return []


def _check_margin_alerts(
    metrics: Dict, yoy: Optional[Dict],
    sales_df: pd.DataFrame, prev_sales_df: pd.DataFrame = None,
) -> List[Dict]:
    """Alert if GP margin dropped significantly vs LY; identify source."""
    if not yoy:
        return []

    curr_gp_pct = metrics.get('gp_percent', 0)
    prev_rev = yoy.get('prev_revenue', 0)
    prev_gp = yoy.get('prev_gp', 0)
    if prev_rev <= 0:
        return []
    prev_gp_pct = prev_gp / prev_rev * 100
    margin_change = curr_gp_pct - prev_gp_pct

    if margin_change >= -MARGIN_DROP_THRESHOLD_PP:
        return []

    source = _identify_margin_erosion_source(sales_df, prev_sales_df)
    msg = f"GP margin {margin_change:+.1f}pp vs LY ({curr_gp_pct:.1f}% vs {prev_gp_pct:.1f}%)"
    if source:
        msg += f" — {source}"
    return [{'severity': 'medium', 'icon': '🟡', 'message': msg}]


def _identify_margin_erosion_source(
    sales_df: pd.DataFrame, prev_sales_df: pd.DataFrame = None,
) -> str:
    """Find brand/entity contributing most to margin decline."""
    if prev_sales_df is None or prev_sales_df.empty or sales_df.empty:
        return ""

    rev_col = 'calculated_invoiced_amount_usd'
    gp_col = 'invoiced_gross_profit_usd'
    if rev_col not in sales_df.columns or gp_col not in sales_df.columns:
        return ""

    for dim in ['brand', 'legal_entity']:
        if dim not in sales_df.columns or dim not in prev_sales_df.columns:
            continue

        curr = sales_df.groupby(dim).agg({rev_col: 'sum', gp_col: 'sum'}).reset_index()
        curr.columns = [dim, 'curr_rev', 'curr_gp']
        curr['curr_margin'] = np.where(curr['curr_rev'] > 0, curr['curr_gp'] / curr['curr_rev'] * 100, 0)

        prev = prev_sales_df.groupby(dim).agg({rev_col: 'sum', gp_col: 'sum'}).reset_index()
        prev.columns = [dim, 'prev_rev', 'prev_gp']
        prev['prev_margin'] = np.where(prev['prev_rev'] > 0, prev['prev_gp'] / prev['prev_rev'] * 100, 0)

        merged = curr.merge(prev, on=dim, how='inner')
        if merged.empty:
            continue

        total_curr_rev = merged['curr_rev'].sum()
        if total_curr_rev <= 0:
            continue

        merged['rev_share'] = merged['curr_rev'] / total_curr_rev
        merged['margin_drop'] = merged['curr_margin'] - merged['prev_margin']
        merged['weighted_impact'] = merged['margin_drop'] * merged['rev_share']

        worst = merged.nsmallest(1, 'weighted_impact')
        if worst.empty or worst.iloc[0]['margin_drop'] >= 0:
            continue

        row = worst.iloc[0]
        dim_label = "brand" if dim == "brand" else "entity"
        return (
            f"chủ yếu từ {dim_label} {row[dim]} "
            f"(margin {row['curr_margin']:.1f}% vs {row['prev_margin']:.1f}% LY)"
        )
    return ""


def _check_customer_decline_alerts(
    sales_df: pd.DataFrame, prev_sales_df: pd.DataFrame = None,
) -> List[Dict]:
    """Alert if any top-10 customer declined > threshold."""
    if prev_sales_df is None or prev_sales_df.empty or sales_df.empty:
        return []

    rev_col = 'calculated_invoiced_amount_usd'
    if rev_col not in sales_df.columns or 'customer' not in sales_df.columns:
        return []

    curr = sales_df.groupby('customer')[rev_col].sum().reset_index(name='curr_rev')
    prev = prev_sales_df.groupby('customer')[rev_col].sum().reset_index(name='prev_rev')
    merged = curr.merge(prev, on='customer', how='inner')
    if merged.empty:
        return []

    top_prev = merged.nlargest(10, 'prev_rev').copy()
    top_prev['change_pct'] = (top_prev['curr_rev'] - top_prev['prev_rev']) / top_prev['prev_rev']
    top_prev['change_abs'] = top_prev['curr_rev'] - top_prev['prev_rev']

    declining = top_prev[top_prev['change_pct'] < -CUSTOMER_DECLINE_THRESHOLD]
    alerts = []
    for _, row in declining.head(2).iterrows():
        alerts.append({
            'severity': 'medium',
            'icon': '🟠',
            'message': (
                f"Customer {row['customer']} giảm {abs(row['change_pct']):.0%} "
                f"({_fmt_currency(row['change_abs'])} vs LY)"
            ),
        })
    return alerts


def _check_inactive_customer_alerts(sales_df: pd.DataFrame) -> List[Dict]:
    """Alert if major customers haven't ordered in N days."""
    if sales_df.empty:
        return []
    rev_col = 'calculated_invoiced_amount_usd'
    if rev_col not in sales_df.columns or 'inv_date' not in sales_df.columns:
        return []

    today = pd.Timestamp(date.today())
    df = sales_df.copy()
    df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')

    cust_rev = df.groupby('customer')[rev_col].sum()
    total_rev = cust_rev.sum()
    if total_rev <= 0:
        return []

    top_customers = cust_rev.nlargest(max(3, int(len(cust_rev) * 0.2)))
    last_order = df.groupby('customer')['inv_date'].max()

    alerts = []
    for cust in top_customers.index:
        if cust not in last_order.index:
            continue
        last_date = last_order[cust]
        if pd.isna(last_date):
            continue
        days_since = (today - last_date).days
        if days_since >= CUSTOMER_INACTIVE_DAYS:
            alerts.append({
                'severity': 'low',
                'icon': '⚪',
                'message': (
                    f"Customer {cust} — last order {days_since} ngày trước "
                    f"(revenue {_fmt_currency(top_customers[cust])})"
                ),
            })
    return alerts[:2]


def _check_concentration_alerts(sales_df: pd.DataFrame) -> List[Dict]:
    """Alert if revenue too concentrated in top 3 customers."""
    if sales_df.empty or 'customer' not in sales_df.columns:
        return []
    rev_col = 'calculated_invoiced_amount_usd'
    if rev_col not in sales_df.columns:
        return []

    cust_rev = sales_df.groupby('customer')[rev_col].sum().sort_values(ascending=False)
    total = cust_rev.sum()
    if total <= 0 or len(cust_rev) < 5:
        return []

    top3_share = cust_rev.head(3).sum() / total
    if top3_share >= CONCENTRATION_THRESHOLD:
        top3_names = ", ".join(cust_rev.head(3).index.tolist())
        return [{
            'severity': 'low',
            'icon': '⚪',
            'message': (
                f"Revenue concentration: top 3 customers chiếm {top3_share:.0%} "
                f"({top3_names})"
            ),
        }]
    return []


# =============================================================================
# CUSTOMER TYPE BREAKDOWN (External vs Internal)
# =============================================================================

def _build_customer_type_breakdown(
    sales_df: pd.DataFrame,
    prev_sales_df: pd.DataFrame = None,
) -> Optional[Dict]:
    """
    Build External vs Internal revenue/GP breakdown.
    Returns None if customer_type column is missing.
    """
    if sales_df.empty or 'customer_type' not in sales_df.columns:
        return None

    rev_col = 'calculated_invoiced_amount_usd'
    gp_col = 'invoiced_gross_profit_usd'
    if rev_col not in sales_df.columns:
        return None

    total_rev = sales_df[rev_col].sum()
    if total_rev <= 0:
        return None

    # Current period by type
    type_agg = sales_df.groupby('customer_type').agg(
        revenue=(rev_col, 'sum'),
        gp=(gp_col, 'sum') if gp_col in sales_df.columns else (rev_col, 'count'),
        customers=('customer_id', 'nunique') if 'customer_id' in sales_df.columns else (rev_col, 'count'),
    ).reset_index()

    breakdown = {}
    for _, row in type_agg.iterrows():
        ctype = str(row['customer_type']).strip()
        rev = row['revenue']
        gp = row.get('gp', 0)
        margin = (gp / rev * 100) if rev > 0 else 0
        share = rev / total_rev

        entry = {
            'revenue': rev,
            'gp': gp,
            'margin': margin,
            'share': share,
            'customers': int(row.get('customers', 0)),
            'yoy_pct': None,
        }

        # YoY by type
        if prev_sales_df is not None and not prev_sales_df.empty and 'customer_type' in prev_sales_df.columns:
            prev_type = prev_sales_df[prev_sales_df['customer_type'] == ctype]
            prev_rev = prev_type[rev_col].sum() if not prev_type.empty else 0
            if prev_rev > 0:
                entry['yoy_pct'] = (rev - prev_rev) / prev_rev * 100
            prev_gp = prev_type[gp_col].sum() if not prev_type.empty and gp_col in prev_type.columns else 0
            entry['prev_revenue'] = prev_rev
            entry['prev_gp'] = prev_gp
            entry['prev_margin'] = (prev_gp / prev_rev * 100) if prev_rev > 0 else 0

        breakdown[ctype] = entry

    return breakdown


def _check_external_revenue_alerts(
    sales_df: pd.DataFrame,
    prev_sales_df: pd.DataFrame = None,
) -> List[Dict]:
    """Alert on External revenue concerns: decline vs LY, or Internal share too high."""
    if sales_df.empty or 'customer_type' not in sales_df.columns:
        return []

    rev_col = 'calculated_invoiced_amount_usd'
    gp_col = 'invoiced_gross_profit_usd'
    if rev_col not in sales_df.columns:
        return []

    total_rev = sales_df[rev_col].sum()
    if total_rev <= 0:
        return []

    alerts = []

    # External revenue
    ext_df = sales_df[sales_df['customer_type'].str.lower() == 'external']
    ext_rev = ext_df[rev_col].sum() if not ext_df.empty else 0
    ext_gp = ext_df[gp_col].sum() if not ext_df.empty and gp_col in ext_df.columns else 0
    ext_margin = (ext_gp / ext_rev * 100) if ext_rev > 0 else 0

    # Internal share warning
    int_df = sales_df[sales_df['customer_type'].str.lower() == 'internal']
    int_rev = int_df[rev_col].sum() if not int_df.empty else 0
    int_share = int_rev / total_rev if total_rev > 0 else 0

    if int_share >= INTERNAL_SHARE_WARNING:
        alerts.append({
            'severity': 'low',
            'icon': '⚪',
            'message': (
                f"Internal revenue chiếm {int_share:.0%} tổng "
                f"({_fmt_currency(int_rev)} / {_fmt_currency(total_rev)})"
            ),
        })

    # External YoY decline
    if prev_sales_df is not None and not prev_sales_df.empty and 'customer_type' in prev_sales_df.columns:
        prev_ext = prev_sales_df[prev_sales_df['customer_type'].str.lower() == 'external']
        prev_ext_rev = prev_ext[rev_col].sum() if not prev_ext.empty else 0
        if prev_ext_rev > 0:
            ext_change_pct = (ext_rev - prev_ext_rev) / prev_ext_rev
            if ext_change_pct < -EXTERNAL_DECLINE_THRESHOLD:
                # Also check margin
                prev_ext_gp = prev_ext[gp_col].sum() if gp_col in prev_ext.columns else 0
                prev_ext_margin = (prev_ext_gp / prev_ext_rev * 100) if prev_ext_rev > 0 else 0
                margin_note = ""
                if ext_margin < prev_ext_margin - 1.5:
                    margin_note = f", margin {ext_margin:.1f}% vs {prev_ext_margin:.1f}% LY"

                alerts.append({
                    'severity': 'medium',
                    'icon': '🟠',
                    'message': (
                        f"External revenue giảm {abs(ext_change_pct):.0%} vs LY "
                        f"({_fmt_currency(ext_rev)} vs {_fmt_currency(prev_ext_rev)}{margin_note})"
                    ),
                })

    return alerts


# =============================================================================
# HIGHLIGHTS (positive news)
# =============================================================================

def _build_highlights(
    metrics: Dict, yoy: Optional[Dict], complex_kpis: Optional[Dict],
    sales_df: pd.DataFrame, prev_sales_df: pd.DataFrame = None,
) -> List[str]:
    highlights = []

    # 1. Revenue growth (total)
    if yoy and yoy.get('revenue_delta_pct') is not None and yoy['revenue_delta_pct'] > 5:
        highlights.append(f"Revenue tăng {yoy['revenue_delta_pct']:.1f}% YoY")

    # 2. External revenue growth (follows revenue naturally)
    if prev_sales_df is not None and not prev_sales_df.empty and not sales_df.empty:
        rev_col = 'calculated_invoiced_amount_usd'
        if 'customer_type' in sales_df.columns and rev_col in sales_df.columns:
            ext_curr = sales_df[sales_df['customer_type'].str.lower() == 'external'][rev_col].sum()
            ext_prev_df = prev_sales_df[prev_sales_df['customer_type'].str.lower() == 'external'] if 'customer_type' in prev_sales_df.columns else pd.DataFrame()
            ext_prev = ext_prev_df[rev_col].sum() if not ext_prev_df.empty else 0
            if ext_prev > 0:
                ext_growth = (ext_curr - ext_prev) / ext_prev * 100
                if ext_growth > 5:
                    highlights.append(f"External revenue tăng {ext_growth:.1f}% YoY")

    # 3. GP margin improvement
    if yoy:
        prev_rev = yoy.get('prev_revenue', 0)
        prev_gp = yoy.get('prev_gp', 0)
        curr_gp_pct = metrics.get('gp_percent', 0)
        if prev_rev > 0:
            prev_gp_pct = prev_gp / prev_rev * 100
            margin_change = curr_gp_pct - prev_gp_pct
            if margin_change > 1.0:
                highlights.append(f"GP margin cải thiện {margin_change:+.1f}pp vs LY")

    # 4. New business
    if complex_kpis:
        new_cust = complex_kpis.get('num_new_customers', 0)
        new_biz_rev = complex_kpis.get('new_business_revenue', 0)
        if new_cust > 0 and new_biz_rev > 0:
            highlights.append(
                f"{new_cust} khách hàng mới, new business {_fmt_currency(new_biz_rev)}"
            )

    # 5. Top growing customer
    if prev_sales_df is not None and not prev_sales_df.empty and not sales_df.empty:
        rev_col = 'calculated_invoiced_amount_usd'
        if rev_col in sales_df.columns and 'customer' in sales_df.columns:
            curr = sales_df.groupby('customer')[rev_col].sum()
            prev = prev_sales_df.groupby('customer')[rev_col].sum()
            growth = (curr - prev.reindex(curr.index, fill_value=0)).dropna()
            if not growth.empty:
                best = growth.idxmax()
                best_val = growth[best]
                if best_val > 0:
                    highlights.append(f"Top gainer: {best} ({_fmt_currency(best_val)})")

    return highlights[:4]


# =============================================================================
# STREAMLIT RENDERER
# =============================================================================

def render_executive_summary(summary: Dict):
    """
    Render executive summary box in Streamlit.
    CEO glances at this first — must convey status in 5 seconds.
    
    Layout:
      Line 1: Headline (Revenue | GP | Backlog | AR)
      Line 2: 4 metric cards (External Rev | Internal Rev | Total Outstanding | Overdue)
      Line 3: Alerts (if any)
      Line 4: Highlights (if any)
    """
    period = summary.get('period_label', '')
    headline = summary.get('headline', '')
    alerts = summary.get('alerts', [])
    highlights = summary.get('highlights', [])
    breakdown = summary.get('customer_type_breakdown')
    ar_payment_data = summary.get('ar_payment_data')

    with st.container(border=True):
        st.markdown(f"#### 📊 Executive Summary — {period}")
        st.markdown(f"**{headline}**")

        # Single row: External | Internal | Total Outstanding | Overdue
        _render_summary_metrics_row(breakdown, ar_payment_data)

        if alerts:
            severity_order = {'high': 0, 'medium': 1, 'low': 2}
            sorted_alerts = sorted(alerts, key=lambda a: severity_order.get(a['severity'], 9))

            high_alerts = [a for a in sorted_alerts if a['severity'] == 'high']
            other_alerts = [a for a in sorted_alerts if a['severity'] != 'high']

            if high_alerts:
                lines = "\n".join(f"- {a['icon']} {a['message']}" for a in high_alerts)
                st.error(f"**⚡ Cần xử lý ngay:**\n{lines}")

            if other_alerts:
                lines = "\n".join(f"- {a['icon']} {a['message']}" for a in other_alerts)
                st.warning(f"**👀 Cần theo dõi:**\n{lines}")

        if highlights:
            text = " · ".join(f"✅ {h}" for h in highlights)
            st.success(text)

        if not alerts and not highlights:
            st.success("✅ Hoạt động bình thường — không có vấn đề cần chú ý")


def _render_summary_metrics_row(
    breakdown: Optional[Dict],
    ar_payment_data: Optional[Dict],
):
    """
    Single row: External Revenue | Internal Revenue | Total Outstanding | Overdue
    Combines customer type breakdown + AR into one scannable row.
    """
    # --- Extract External / Internal ---
    ext_data = None
    int_data = None
    if breakdown:
        for ctype, data in breakdown.items():
            if ctype.lower() == 'external':
                ext_data = data
            elif ctype.lower() == 'internal':
                int_data = data
    
    # --- Extract AR ---
    total_outstanding = 0
    total_overdue = 0
    overdue_90_amount = 0
    overdue_line_count = 0
    ar_inv_count = 0
    
    if ar_payment_data:
        ar_summary = ar_payment_data.get('summary', {})
        ar_aging = ar_payment_data.get('aging_buckets', pd.DataFrame())
        
        total_outstanding = ar_summary.get('total_outstanding', 0)
        ar_inv_count = ar_summary.get('unpaid_invoices', 0) + ar_summary.get('partial_invoices', 0)
        
        if not ar_aging.empty and 'min_days' in ar_aging.columns:
            overdue_mask = ar_aging['min_days'] >= 0
            total_overdue = ar_aging.loc[overdue_mask, 'amount'].sum()
            overdue_line_count = int(ar_aging.loc[overdue_mask, 'count'].sum())
            
            bucket_90 = ar_aging[ar_aging['min_days'] >= 91]
            overdue_90_amount = bucket_90['amount'].sum() if not bucket_90.empty else 0
    
    # --- Render 4 columns ---
    c1, c2, c3, c4 = st.columns(4)
    
    # Col 1: External Revenue
    with c1:
        if ext_data:
            share = ext_data.get('share', 0)
            yoy = ext_data.get('yoy_pct')
            margin = ext_data.get('margin', 0)
            customers = ext_data.get('customers', 0)
            
            delta_parts = []
            if yoy is not None:
                delta_parts.append(f"{yoy:+.1f}% YoY")
            delta_parts.append(f"GP {margin:.1f}%")
            
            st.metric(
                f"🌐 External ({share:.0%})",
                _fmt_currency(ext_data['revenue']),
                " · ".join(delta_parts),
                delta_color="normal" if (yoy is None or yoy >= 0) else "inverse",
            )
            if customers > 0:
                st.caption(f"{customers} customers")
        else:
            st.metric("🌐 External", "—", "No data", delta_color="off")
    
    # Col 2: Internal Revenue
    with c2:
        if int_data:
            share = int_data.get('share', 0)
            yoy = int_data.get('yoy_pct')
            margin = int_data.get('margin', 0)
            customers = int_data.get('customers', 0)
            
            delta_parts = []
            if yoy is not None:
                delta_parts.append(f"{yoy:+.1f}% YoY")
            delta_parts.append(f"GP {margin:.1f}%")
            
            st.metric(
                f"🏠 Internal ({share:.0%})",
                _fmt_currency(int_data['revenue']),
                " · ".join(delta_parts),
                delta_color="normal",
            )
            if customers > 0:
                st.caption(f"{customers} customers")
        else:
            st.metric("🏠 Internal", "—", "No data", delta_color="off")
    
    # Col 3: Total AR Outstanding
    with c3:
        if total_outstanding > 100:
            st.metric(
                "💰 Total Outstanding",
                _fmt_currency(total_outstanding),
                f"{ar_inv_count:,} invoices",
                delta_color="off",
            )
        else:
            st.metric("💰 Total Outstanding", "$0", "All collected", delta_color="off")
    
    # Col 4: Overdue
    with c4:
        if total_overdue > 0:
            detail = f"{overdue_line_count:,} lines"
            if overdue_90_amount > 0:
                detail += f" · {_fmt_currency(overdue_90_amount)} is 90+d"
            st.metric(
                "🔴 Overdue",
                _fmt_currency(total_overdue),
                detail,
                delta_color="inverse",
            )
        else:
            st.metric("🟢 Overdue", "$0", "No overdue", delta_color="off")