# utils/safety_stock/analysis.py
"""
Analysis Section for Safety Stock Management.
Renders a deep-dive analytics panel with 4 tabs:
  📋 Review History | 📈 SS Trend | ⚖️ Coverage Analysis | 🔍 Rule Health

Usage:
    from utils.safety_stock.analysis import render_analysis_section
    render_analysis_section()
"""

import pandas as pd
import altair as alt
import streamlit as st

from .crud import get_review_history_analytics, get_coverage_analysis, get_safety_stock_levels


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _load_entity_options() -> tuple[list, list]:
    """Return (entity_labels, entity_ids) for the entity selectbox."""
    from .crud import get_safety_stock_levels
    try:
        df = get_safety_stock_levels(status='all')
        if df.empty or 'entity_code' not in df.columns:
            return [], []
        pairs = (df[['entity_id', 'entity_code', 'entity_name']]
                 .dropna(subset=['entity_id', 'entity_code'])
                 .drop_duplicates(subset=['entity_id'])
                 .sort_values('entity_code'))
        labels = pairs.apply(
            lambda r: f"{r['entity_code']} | {r['entity_name']}"
                      if pd.notna(r.get('entity_name')) and r['entity_name']
                      else str(r['entity_code']),
            axis=1
        ).tolist()
        return labels, pairs['entity_id'].tolist()
    except Exception:
        return [], []


# ══════════════════════════════════════════════════════════════════════════════
# Tab renderers (each is a plain function so they stay testable independently)
# ══════════════════════════════════════════════════════════════════════════════

def _render_review_history(entity_id, days: int):
    st.markdown("**All review events** within selected window — sortable, filterable.")

    with st.spinner("Loading review history..."):
        hist_df = get_review_history_analytics(entity_id=entity_id, days=days)

    if hist_df.empty:
        st.info("No review events found for the selected period.")
        return

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Reviews",     len(hist_df))
    m2.metric("Products Reviewed", hist_df['pt_code'].nunique())
    m3.metric("📈 Increased",      int((hist_df['action_taken'] == 'INCREASED').sum()))
    m4.metric("📉 Decreased",      int((hist_df['action_taken'] == 'DECREASED').sum()))

    # Action filter
    action_opts = ['All Actions'] + sorted(hist_df['action_taken'].dropna().unique().tolist())
    sel_action  = st.selectbox("Filter by action", action_opts, key="ana_hist_action")
    view_df     = hist_df if sel_action == 'All Actions' else hist_df[hist_df['action_taken'] == sel_action]

    # Bar chart: reviews per day
    if not view_df.empty:
        chart_df = (view_df
                    .assign(date=pd.to_datetime(view_df['review_date']).dt.date)
                    .groupby(['date', 'action_taken'], as_index=False)
                    .size()
                    .rename(columns={'size': 'count'}))
        chart = (alt.Chart(chart_df)
            .mark_bar()
            .encode(
                x=alt.X('date:T', title='Date'),
                y=alt.Y('count:Q', title='Reviews'),
                color=alt.Color('action_taken:N',
                    scale=alt.Scale(
                        domain=['INCREASED', 'DECREASED', 'NO_CHANGE', 'METHOD_CHANGED'],
                        range=['#43a047', '#fb8c00', '#90a4ae', '#1e88e5']
                    )),
                tooltip=['date:T', 'action_taken:N', 'count:Q']
            )
            .properties(height=220, title="Review Events by Day"))
        st.altair_chart(chart, width="stretch")

    # Detail table
    table_cols = ['review_date', 'pt_code', 'product_name', 'brand_name',
                  'entity_code', 'old_safety_stock_qty', 'new_safety_stock_qty',
                  'change_percentage', 'action_taken', 'review_type', 'action_reason', 'reviewed_by']
    table_cols = [c for c in table_cols if c in view_df.columns]
    st.dataframe(
        view_df[table_cols].rename(columns={
            'review_date': 'Date', 'pt_code': 'PT Code', 'product_name': 'Product',
            'brand_name': 'Brand', 'entity_code': 'Entity',
            'old_safety_stock_qty': 'Old SS', 'new_safety_stock_qty': 'New SS',
            'change_percentage': 'Change %', 'action_taken': 'Action',
            'review_type': 'Type', 'action_reason': 'Reason', 'reviewed_by': 'Reviewed By'
        }),
        width="stretch", hide_index=True
    )


def _render_ss_trend(entity_id, days: int):
    st.markdown("**How SS quantity evolved over time** for a selected product.")

    with st.spinner("Loading..."):
        trend_src = get_review_history_analytics(entity_id=entity_id, days=days)

    if trend_src.empty:
        st.info("No review data available for trend analysis.")
        return

    product_opts = sorted(trend_src['pt_code'].dropna().unique().tolist())
    if not product_opts:
        st.info("No products with review history.")
        return

    sel_pt  = st.selectbox("Select Product", product_opts, key="ana_trend_pt")
    prod_df = trend_src[trend_src['pt_code'] == sel_pt].sort_values('review_date')

    if prod_df.empty:
        st.info("No history for selected product.")
        return

    first     = prod_df.iloc[0]
    start_val = float(first['old_safety_stock_qty'] or 0)
    end_val   = float(prod_df.iloc[-1]['new_safety_stock_qty'] or 0)
    delta_pct = ((end_val - start_val) / start_val * 100) if start_val else 0

    m1, m2, m3 = st.columns(3)
    m1.metric("Reviews",     len(prod_df))
    m2.metric("Starting SS", f"{start_val:,.0f}")
    m3.metric("Current SS",  f"{end_val:,.0f}", delta=f"{delta_pct:+.1f}%")

    line = (alt.Chart(prod_df)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X('review_date:T', title='Review Date'),
            y=alt.Y('new_safety_stock_qty:Q', title='SS Quantity'),
            color=alt.Color('action_taken:N',
                scale=alt.Scale(
                    domain=['INCREASED', 'DECREASED', 'NO_CHANGE', 'METHOD_CHANGED'],
                    range=['#43a047', '#fb8c00', '#90a4ae', '#1e88e5']
                )),
            tooltip=['review_date:T', 'old_safety_stock_qty:Q',
                     'new_safety_stock_qty:Q', 'change_percentage:Q', 'action_taken:N']
        )
        .properties(height=280, title=f"SS Qty Timeline — {sel_pt}"))
    st.altair_chart(line, width="stretch")

    detail_cols = ['review_date', 'old_safety_stock_qty', 'new_safety_stock_qty',
                   'change_percentage', 'action_taken', 'review_type', 'action_reason']
    detail_cols = [c for c in detail_cols if c in prod_df.columns]
    st.dataframe(
        prod_df[detail_cols].sort_values('review_date', ascending=False),
        width="stretch", hide_index=True
    )


def _render_coverage_analysis(entity_id):
    st.markdown("""
**Current on-hand inventory vs Safety Stock target** — identifies products at risk.
Coverage % = On Hand ÷ SS Target × 100. Below 100% means stock is under the safety buffer.
""")
    with st.spinner("Loading coverage data..."):
        cov_df = get_coverage_analysis(entity_id=entity_id)

    if cov_df.empty:
        st.info("No data available.")
        return

    total     = len(cov_df)
    below_rop = int((cov_df['coverage_status'] == 'Below ROP').sum())
    below_ss  = int((cov_df['coverage_status'] == 'Below SS').sum())
    above_ss  = int((cov_df['coverage_status'] == 'Above SS').sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Rules",  total)
    m2.metric("🔴 Below ROP", below_rop,
              delta=f"{below_rop/total*100:.0f}%" if total else None,
              delta_color="inverse")
    m3.metric("🟠 Below SS",  below_ss,
              delta=f"{below_ss/total*100:.0f}%" if total else None,
              delta_color="inverse")
    m4.metric("🟢 Above SS",  above_ss)

    cov_status_opts = ['All'] + sorted(cov_df['coverage_status'].unique().tolist())
    sel_cov_status  = st.selectbox("Filter by status", cov_status_opts, key="ana_cov_status")
    chart_df = cov_df if sel_cov_status == 'All' else cov_df[cov_df['coverage_status'] == sel_cov_status]
    chart_df = chart_df.dropna(subset=['coverage_pct']).sort_values('coverage_pct').head(40)

    if not chart_df.empty:
        bar = (alt.Chart(chart_df)
            .mark_bar()
            .encode(
                x=alt.X('coverage_pct:Q', title='Coverage %', scale=alt.Scale(domainMin=0)),
                y=alt.Y('pt_code:N', sort='-x', title='Product'),
                color=alt.Color('coverage_status:N',
                    scale=alt.Scale(
                        domain=['Below ROP', 'Below SS', 'Above SS', 'No Data'],
                        range=['#e53935', '#fb8c00', '#43a047', '#bdbdbd']
                    )),
                tooltip=['pt_code:N', 'product_name:N', 'on_hand:Q',
                         'safety_stock_qty:Q', 'reorder_point:Q',
                         'coverage_pct:Q', 'coverage_status:N']
            )
            .properties(height=max(300, len(chart_df) * 18),
                        title="Inventory Coverage vs Safety Stock (Top 40 lowest)"))

        rule_100 = (alt.Chart(pd.DataFrame({'x': [100]}))
                    .mark_rule(color='red', strokeDash=[4, 4])
                    .encode(x='x:Q'))

        st.altair_chart(bar + rule_100, width="stretch")
        st.caption("Dashed red line = 100% coverage threshold (on-hand = SS target)")

    tbl_cols = ['pt_code', 'product_name', 'brand_name', 'customer_code',
                'safety_stock_qty', 'reorder_point', 'on_hand',
                'coverage_pct', 'coverage_status', 'calculation_method']
    tbl_cols = [c for c in tbl_cols if c in cov_df.columns]
    st.dataframe(
        cov_df[tbl_cols].rename(columns={
            'pt_code': 'PT Code', 'product_name': 'Product', 'brand_name': 'Brand',
            'customer_code': 'Customer', 'safety_stock_qty': 'SS Target',
            'reorder_point': 'ROP', 'on_hand': 'On Hand',
            'coverage_pct': 'Coverage %', 'coverage_status': 'Status',
            'calculation_method': 'Method'
        }),
        width="stretch", hide_index=True
    )


def _render_rule_health(entity_id):
    st.markdown("**Rule quality scorecard** — identify stale, incomplete, or improvable rules.")

    with st.spinner("Loading..."):
        health_df = get_safety_stock_levels(entity_id=entity_id, status='active')

    if health_df.empty:
        st.info("No active rules found.")
        return

    today = pd.Timestamp.now()

    # Classify
    health_df['_never_reviewed'] = (
        health_df.get('review_count', pd.Series(0, index=health_df.index))
        .fillna(0) == 0
    )
    health_df['_no_rop']   = health_df['reorder_point'].isna() | (health_df['reorder_point'] == 0)
    health_df['_is_fixed'] = (
        health_df.get('calculation_method', pd.Series('FIXED', index=health_df.index))
        .fillna('FIXED') == 'FIXED'
    )
    if 'last_calculated_date' in health_df.columns:
        health_df['_stale_60d'] = health_df['last_calculated_date'].apply(
            lambda x: pd.notna(x) and (today - pd.to_datetime(x)).days > 60
        )
        health_df['_stale_90d'] = health_df['last_calculated_date'].apply(
            lambda x: pd.notna(x) and (today - pd.to_datetime(x)).days > 90
        )
    else:
        health_df['_stale_60d'] = False
        health_df['_stale_90d'] = False

    total          = len(health_df)
    never_reviewed = int(health_df['_never_reviewed'].sum())
    no_rop         = int(health_df['_no_rop'].sum())
    manual_fixed   = int(health_df['_is_fixed'].sum())
    stale_60       = int(health_df['_stale_60d'].sum())
    stale_90       = int(health_df['_stale_90d'].sum())

    # Scorecard
    st.markdown("#### Scorecard")
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric("Active Rules",   total)
    sc2.metric("Never Reviewed", never_reviewed,
               delta=f"{never_reviewed/total*100:.0f}%" if total else None,
               delta_color="inverse" if never_reviewed > 0 else "off")
    sc3.metric("Missing ROP",    no_rop,
               delta=f"{no_rop/total*100:.0f}%" if total else None,
               delta_color="inverse" if no_rop > 0 else "off")
    sc4.metric("Manual (FIXED)", manual_fixed,
               delta=f"{manual_fixed/total*100:.0f}%" if total else None,
               delta_color="inverse" if manual_fixed / max(total, 1) > 0.5 else "off")
    sc5.metric("Stale >60d",     stale_60,
               delta=f"{stale_90} >90d" if stale_90 else None,
               delta_color="inverse" if stale_60 > 0 else "off")

    # Method donut
    st.markdown("#### Method Distribution")
    method_counts = (
        health_df.get('calculation_method', pd.Series(dtype=str))
        .fillna('FIXED')
        .map({'FIXED': 'FIXED', 'DAYS_OF_SUPPLY': 'DOS', 'LEAD_TIME_BASED': 'LTB'})
        .value_counts()
        .reset_index()
    )
    method_counts.columns = ['Method', 'Count']
    donut = (alt.Chart(method_counts)
        .mark_arc(innerRadius=50)
        .encode(
            theta=alt.Theta('Count:Q'),
            color=alt.Color('Method:N',
                scale=alt.Scale(
                    domain=['FIXED', 'DOS', 'LTB'],
                    range=['#ef5350', '#42a5f5', '#66bb6a']
                )),
            tooltip=['Method:N', 'Count:Q']
        )
        .properties(width=260, height=220))
    st.altair_chart(donut)

    # Issue drill-downs
    issue_tabs = st.tabs(["🕰️ Never Reviewed", "❓ Missing ROP", "📋 Stale >60d"])
    base_cols  = ['pt_code', 'product_name', 'brand_name', 'entity_code',
                  'customer_code', 'safety_stock_qty', 'calculation_method',
                  'last_calculated_date', 'review_count']

    def _show_issue_table(mask_col: str, label: str):
        sub = health_df[health_df[mask_col]][[c for c in base_cols if c in health_df.columns]]
        if sub.empty:
            st.success(f"✅ No {label} rules found.")
        else:
            st.dataframe(sub.rename(columns={
                'pt_code': 'PT Code', 'product_name': 'Product',
                'brand_name': 'Brand', 'entity_code': 'Entity',
                'customer_code': 'Customer', 'safety_stock_qty': 'SS Qty',
                'calculation_method': 'Method', 'last_calculated_date': 'Last Calc',
                'review_count': 'Reviews'
            }), width="stretch", hide_index=True)

    with issue_tabs[0]:
        _show_issue_table('_never_reviewed', 'never-reviewed')
    with issue_tabs[1]:
        _show_issue_table('_no_rop', 'missing-ROP')
    with issue_tabs[2]:
        _show_issue_table('_stale_60d', 'stale >60d')


# ══════════════════════════════════════════════════════════════════════════════
# Public entry point — called from main page as a @st.fragment
# ══════════════════════════════════════════════════════════════════════════════

def render_analysis_section():
    """
    Deep-dive analytics panel — 4 tabs.
    Decorated with @st.fragment in the main page wrapper so it reruns
    independently from the data table section.
    """
    st.divider()
    st.subheader("📊 Analysis")

    # ── Shared controls ────────────────────────────────────────────────────────
    ctrl_col1, ctrl_col2, _ = st.columns([2, 2, 4])

    with ctrl_col1:
        labels, ids = _load_entity_options()
        entity_opts = ['All Entities'] + labels
        sel_entity  = st.selectbox("Entity", entity_opts, key="ana_entity")
        ana_entity_id = None
        if sel_entity != 'All Entities' and sel_entity in labels:
            ana_entity_id = ids[labels.index(sel_entity)]

    with ctrl_col2:
        days_opts  = {30: '30 days', 60: '60 days', 90: '90 days', 180: '6 months', 365: '1 year'}
        ana_days   = st.selectbox("History window", list(days_opts.values()),
                                  index=2, key="ana_days")
        ana_days_val = next(k for k, v in days_opts.items() if v == ana_days)

    # ── Tabs ───────────────────────────────────────────────────────────────────
    tab_hist, tab_trend, tab_coverage, tab_health = st.tabs([
        "📋 Review History", "📈 SS Trend", "⚖️ Coverage Analysis", "🔍 Rule Health"
    ])

    with tab_hist:
        _render_review_history(ana_entity_id, ana_days_val)

    with tab_trend:
        _render_ss_trend(ana_entity_id, ana_days_val)

    with tab_coverage:
        _render_coverage_analysis(ana_entity_id)

    with tab_health:
        _render_rule_health(ana_entity_id)