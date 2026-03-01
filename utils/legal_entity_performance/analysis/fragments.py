# utils/legal_entity_performance/analysis/fragments.py
"""
Analysis Tab Fragments for Legal Entity Performance.
Adapted from kpi_center_performance/analysis/fragments.py v6.2.0

VERSION: 2.0.0
- Top Performers: Pareto chart with dual Y-axis, HHI, CR10
- Growth (YoY): Movers bar, Waterfall, New/Lost, Status Distribution
"""

import logging
from typing import Dict
import pandas as pd
import streamlit as st

from .charts import (
    build_pareto_chart,
    build_growth_comparison_chart,
    build_movers_bar_chart,
    build_waterfall_chart,
    build_new_lost_chart,
    build_status_distribution_chart,
)

logger = logging.getLogger(__name__)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def analysis_tab_fragment(
    sales_df: pd.DataFrame,
    prev_sales_df: pd.DataFrame = None,
    filter_values: Dict = None,
    processor=None,
    fragment_key: str = "le_analysis"
):
    """Main Analysis Tab entry point."""
    if sales_df.empty:
        st.info("📊 No data available for analysis. Please adjust your filters.")
        return
    
    _render_header()
    agg_data = _get_cached_aggregations(sales_df, fragment_key)
    
    tab1, tab2 = st.tabs(["🏆 Top Performers", "📈 Growth (YoY)"])
    
    with tab1:
        _top_performers_tab(agg_data, key_prefix=f"{fragment_key}_top")
    
    with tab2:
        _growth_analysis_tab(
            sales_df=sales_df,
            prev_sales_df=prev_sales_df,
            key_prefix=f"{fragment_key}_growth"
        )


def _render_header():
    col_header, col_help = st.columns([6, 1])
    with col_header:
        st.subheader("📈 Performance Analysis")
    with col_help:
        with st.popover("ℹ️ Help"):
            st.markdown("""
**📈 Analysis Tools**

| Tab | Description |
|-----|-------------|
| **Top Performers** | Pareto analysis by Customer/Brand/Product |
| **Growth (YoY)** | Compare vs previous year |

**Key Metrics:**
- **CR10**: % of total from top 10% of entities
- **HHI**: Concentration index (0-10,000). < 1,500 = Low, > 2,500 = High
- **Threshold**: Cumulative % cutoff (Pareto Principle)
            """)


# =============================================================================
# DATA CACHING
# =============================================================================

def _get_cached_aggregations(sales_df: pd.DataFrame, key_prefix: str) -> Dict:
    cache_key = f"_le_analysis_agg_{key_prefix}"
    data_hash = f"{len(sales_df)}_{sales_df['calculated_invoiced_amount_usd'].sum():.0f}"
    hash_key = f"{cache_key}_hash"
    
    if cache_key in st.session_state and st.session_state.get(hash_key) == data_hash:
        return st.session_state[cache_key]
    
    agg_data = {
        'customer': _aggregate_dimension(sales_df, 'customer'),
        'brand': _aggregate_dimension(sales_df, 'brand'),
        'product_pn': _aggregate_dimension(sales_df, 'product_pn'),
    }
    
    st.session_state[cache_key] = agg_data
    st.session_state[hash_key] = data_hash
    return agg_data


def _aggregate_dimension(sales_df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    agg_dict = {
        'calculated_invoiced_amount_usd': 'sum',
        'invoiced_gross_profit_usd': 'sum',
        'inv_number': pd.Series.nunique,
    }
    if 'invoiced_gp1_usd' in sales_df.columns:
        agg_dict['invoiced_gp1_usd'] = 'sum'
    
    agg_df = sales_df.groupby(dimension).agg(agg_dict).reset_index()
    agg_df = agg_df.rename(columns={
        'calculated_invoiced_amount_usd': 'revenue',
        'invoiced_gross_profit_usd': 'gross_profit',
        'invoiced_gp1_usd': 'gp1',
        'inv_number': 'orders',
    })
    if 'gp1' not in agg_df.columns:
        agg_df['gp1'] = 0
    return agg_df


# =============================================================================
# TOP PERFORMERS TAB
# =============================================================================

@st.fragment
def _top_performers_tab(agg_data: Dict, key_prefix: str):
    col_tabs, col_slider = st.columns([4, 2])
    with col_slider:
        threshold_pct = st.slider(
            "Threshold %", 50, 100, 80, 5,
            key=f"{key_prefix}_threshold",
            help="Show performers contributing to this % of total"
        )
    threshold = threshold_pct / 100
    
    dim_tab1, dim_tab2, dim_tab3 = st.tabs(["👥 Customer", "🏭 Brand", "📦 Product"])
    
    with dim_tab1:
        _render_dimension_analysis(agg_data['customer'], 'customer', 'Customer', threshold, f"{key_prefix}_cust")
    with dim_tab2:
        _render_dimension_analysis(agg_data['brand'], 'brand', 'Brand', threshold, f"{key_prefix}_brand")
    with dim_tab3:
        _render_dimension_analysis(agg_data['product_pn'], 'product_pn', 'Product', threshold, f"{key_prefix}_prod")


def _render_dimension_analysis(agg_df, dimension, dimension_label, threshold, key_prefix):
    metric_tab1, metric_tab2, metric_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
    with metric_tab1:
        _render_metric_view(agg_df, dimension, dimension_label, 'revenue', 'Revenue', threshold)
    with metric_tab2:
        _render_metric_view(agg_df, dimension, dimension_label, 'gross_profit', 'Gross Profit', threshold)
    with metric_tab3:
        _render_metric_view(agg_df, dimension, dimension_label, 'gp1', 'GP1', threshold)


def _render_metric_view(agg_df, dimension, dimension_label, metric, metric_label, threshold):
    if agg_df.empty or agg_df[metric].sum() == 0:
        st.warning(f"No {metric_label} data available")
        return
    
    top_df, total_value, total_count = _prepare_top_performers(agg_df, dimension, metric, threshold)
    if top_df.empty:
        st.warning("No data to display")
        return
    
    # Metrics cards (4 columns: Top Count, Threshold Value, CR10, HHI)
    _render_metrics_cards(top_df, agg_df, dimension_label, metric, metric_label, threshold, total_value, total_count)
    
    # Chart + Table
    col_chart, col_table = st.columns([3, 2])
    with col_chart:
        chart = build_pareto_chart(
            data_df=top_df, value_col=metric, label_col=dimension,
            title=f"Top {dimension_label}s by {metric_label}", metric_type=metric
        )
        st.altair_chart(chart, width="stretch")
    with col_table:
        _render_detail_table(top_df, dimension, dimension_label, metric, metric_label)
    
    # Insights
    _render_insights(top_df, agg_df, dimension, dimension_label, metric, metric_label, threshold, total_value)


def _prepare_top_performers(agg_df, dimension, metric, threshold):
    sorted_df = agg_df.sort_values(metric, ascending=False).reset_index(drop=True)
    total_value = sorted_df[metric].sum()
    total_count = len(sorted_df)
    
    if total_value == 0:
        return pd.DataFrame(), 0, total_count
    
    sorted_df['cumulative_value'] = sorted_df[metric].cumsum()
    sorted_df['cumulative_percent'] = sorted_df['cumulative_value'] / total_value
    sorted_df['percent_contribution'] = sorted_df[metric] / total_value * 100
    
    exceed_mask = sorted_df['cumulative_percent'] > threshold
    if exceed_mask.any():
        top_df = sorted_df.loc[:exceed_mask.idxmax()].copy()
    else:
        top_df = sorted_df.copy()
    
    return top_df, total_value, total_count


def _render_metrics_cards(top_df, agg_df, dimension_label, metric, metric_label, threshold, total_value, total_count):
    top_count = len(top_df)
    top_value = top_df[metric].sum()
    actual_pct = (top_value / total_value * 100) if total_value > 0 else 0
    
    # CR10
    top_10_count = max(1, int(total_count * 0.1))
    top_10_value = agg_df.sort_values(metric, ascending=False).head(top_10_count)[metric].sum()
    cr_10 = (top_10_value / total_value * 100) if total_value > 0 else 0
    
    # HHI
    shares = agg_df[metric] / total_value if total_value > 0 else 0
    hhi = (shares ** 2).sum() * 10000
    hhi_level = "Low" if hhi < 1500 else "Moderate" if hhi < 2500 else "High"
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(f"Top {dimension_label}s", f"{top_count:,}", f"of {total_count:,} total")
    with c2:
        st.metric(f"{int(threshold*100)}% {metric_label}", f"${top_value:,.0f}", f"{actual_pct:.1f}% of total")
    with c3:
        st.metric("CR10 (Top 10%)", f"{cr_10:.1f}%")
    with c4:
        st.metric("HHI Index", f"{hhi:,.0f}", hhi_level)


def _render_detail_table(top_df, dimension, dimension_label, metric, metric_label):
    st.markdown(f"##### 📋 Top {dimension_label}s Detail")
    
    display_df = pd.DataFrame({
        '#': range(1, len(top_df) + 1),
        dimension_label: top_df[dimension].values,
        metric_label: top_df[metric].apply(lambda x: f"${x:,.0f}").values,
        '% Share': top_df['percent_contribution'].apply(lambda x: f"{x:.1f}%").values,
        'Cumul.%': top_df['cumulative_percent'].apply(lambda x: f"{x:.1%}").values,
    })
    
    if 'revenue' in top_df.columns and 'gross_profit' in top_df.columns and metric in ['revenue', 'gross_profit']:
        display_df['GP%'] = (top_df['gross_profit'] / top_df['revenue'].replace(0, float('nan')) * 100).apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "-"
        ).values
    
    if 'orders' in top_df.columns:
        display_df['Orders'] = top_df['orders'].apply(lambda x: f"{x:,}").values
    
    st.dataframe(display_df, hide_index=True, width="stretch",
                  height=min(400, 35 * len(display_df) + 38))


def _render_insights(top_df, agg_df, dimension, dimension_label, metric, metric_label, threshold, total_value):
    with st.expander("💡 Key Insights", expanded=False):
        if top_df.empty:
            st.info("No data for insights")
            return
        
        top_count = len(top_df)
        total_count = len(agg_df)
        concentration_pct = (top_count / total_count * 100) if total_count > 0 else 0
        
        top_1 = top_df.iloc[0]
        top_1_name = top_1[dimension]
        top_1_pct = top_1['percent_contribution']
        top_3_share = top_df.head(3)['percent_contribution'].sum()
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
**📊 Concentration:**
- **Top 1**: {top_1_name} = {top_1_pct:.1f}% of {metric_label}
- **Top 3**: {top_3_share:.1f}% of {metric_label}
- **{int(threshold*100)}% threshold**: {top_count:,} {dimension_label}s ({concentration_pct:.1f}% of base)
            """)
        with c2:
            if 'revenue' in top_df.columns and 'gross_profit' in top_df.columns:
                tr = top_df['revenue'].sum()
                tg = top_df['gross_profit'].sum()
                avg_margin = (tg / tr * 100) if tr > 0 else 0
                st.markdown(f"""
**💰 Profitability (Top {top_count}):**
- Average GP Margin: **{avg_margin:.1f}%**
- Total Revenue: ${tr:,.0f}
- Total GP: ${tg:,.0f}
                """)


# =============================================================================
# GROWTH ANALYSIS TAB
# =============================================================================

@st.fragment
def _growth_analysis_tab(
    sales_df: pd.DataFrame,
    prev_sales_df: pd.DataFrame = None,
    key_prefix: str = "le_growth"
):
    st.markdown("#### 📈 Growth Analysis (YoY)")
    
    if prev_sales_df is None or prev_sales_df.empty:
        st.info("📊 No previous period data available for YoY comparison.")
        st.caption("Enable 'Show YoY' in sidebar filters to load comparison data.")
        return
    
    c1, c2 = st.columns(2)
    with c1:
        dimension = st.selectbox("Compare by", ["Customer", "Brand", "Product"], key=f"{key_prefix}_dim")
    with c2:
        metric = st.selectbox("Metric", ["Revenue", "Gross Profit", "GP1"], key=f"{key_prefix}_metric")
    
    dim_col = {"Customer": "customer", "Brand": "brand", "Product": "product_pn"}.get(dimension)
    value_col = {
        "Revenue": "calculated_invoiced_amount_usd",
        "Gross Profit": "invoiced_gross_profit_usd",
        "GP1": "invoiced_gp1_usd",
    }.get(metric)
    
    compare_df = _build_comparison_data(sales_df, prev_sales_df, dim_col, value_col)
    if compare_df.empty:
        st.warning("No comparison data available")
        return
    
    _render_growth_metrics(compare_df, dimension, metric)
    
    view_tab1, view_tab2, view_tab3 = st.tabs(["📊 Top Movers", "🆕 New & Lost", "📋 Full List"])
    with view_tab1:
        _render_top_movers(compare_df, dim_col, dimension, metric)
    with view_tab2:
        _render_new_and_lost(compare_df, dim_col, dimension, metric)
    with view_tab3:
        _render_full_comparison(compare_df, dim_col, dimension, metric)


def _build_comparison_data(sales_df, prev_sales_df, dim_col, value_col) -> pd.DataFrame:
    current = sales_df.groupby(dim_col).agg({value_col: 'sum'}).reset_index()
    current.columns = [dim_col, 'current']
    prev = prev_sales_df.groupby(dim_col).agg({value_col: 'sum'}).reset_index()
    prev.columns = [dim_col, 'previous']
    
    compare = current.merge(prev, on=dim_col, how='outer').fillna(0)
    compare['change'] = compare['current'] - compare['previous']
    compare['growth_pct'] = (
        (compare['current'] - compare['previous']) / compare['previous'] * 100
    ).replace([float('inf'), -float('inf')], 0).fillna(0).round(1)
    
    compare['status'] = compare.apply(
        lambda r: '🆕 New' if r['previous'] == 0 and r['current'] > 0
        else '❌ Lost' if r['current'] == 0 and r['previous'] > 0
        else '📈 Growing' if r['growth_pct'] > 10
        else '📉 Declining' if r['growth_pct'] < -10
        else '➡️ Stable',
        axis=1
    )
    return compare.sort_values('current', ascending=False)


def _render_growth_metrics(compare_df, dimension, metric):
    total_curr = compare_df['current'].sum()
    total_prev = compare_df['previous'].sum()
    total_growth = ((total_curr - total_prev) / total_prev * 100) if total_prev > 0 else 0
    
    new_count = len(compare_df[compare_df['status'] == '🆕 New'])
    lost_count = len(compare_df[compare_df['status'] == '❌ Lost'])
    growing = len(compare_df[compare_df['status'] == '📈 Growing'])
    declining = len(compare_df[compare_df['status'] == '📉 Declining'])
    
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric(f"Total {metric}", f"${total_curr:,.0f}", f"{total_growth:+.1f}%")
    with c2:
        st.metric("🆕 New", f"{new_count:,}")
    with c3:
        st.metric("❌ Lost", f"{lost_count:,}")
    with c4:
        st.metric("📈 Growing", f"{growing:,}")
    with c5:
        st.metric("📉 Declining", f"{declining:,}")


def _render_top_movers(compare_df, dim_col, dimension, metric):
    gainers = compare_df[compare_df['change'] > 0].nlargest(10, 'change')
    losers = compare_df[compare_df['change'] < 0].nsmallest(10, 'change')
    
    col_chart, col_status = st.columns([3, 1])
    with col_chart:
        chart = build_movers_bar_chart(gainers, losers, dim_col, f"Top {dimension} Movers by {metric}")
        st.altair_chart(chart, width="stretch")
    with col_status:
        st.altair_chart(build_status_distribution_chart(compare_df, "Status"), width="stretch")
    
    col_gain, col_lose = st.columns(2)
    with col_gain:
        st.markdown("##### 📈 Top Gainers")
        if not gainers.empty:
            st.dataframe(pd.DataFrame({
                '#': range(1, len(gainers) + 1),
                dimension: gainers[dim_col].values,
                'Previous': gainers['previous'].apply(lambda x: f"${x:,.0f}").values,
                'Current': gainers['current'].apply(lambda x: f"${x:,.0f}").values,
                'Change': gainers['change'].apply(lambda x: f"${x:+,.0f}").values,
                'Growth %': gainers['growth_pct'].apply(lambda x: f"{x:+.1f}%").values,
            }), hide_index=True, width="stretch", height=min(350, 35 * len(gainers) + 38))
        else:
            st.info("No gainers")
    with col_lose:
        st.markdown("##### 📉 Top Decliners")
        if not losers.empty:
            st.dataframe(pd.DataFrame({
                '#': range(1, len(losers) + 1),
                dimension: losers[dim_col].values,
                'Previous': losers['previous'].apply(lambda x: f"${x:,.0f}").values,
                'Current': losers['current'].apply(lambda x: f"${x:,.0f}").values,
                'Change': losers['change'].apply(lambda x: f"${x:+,.0f}").values,
                'Growth %': losers['growth_pct'].apply(lambda x: f"{x:+.1f}%").values,
            }), hide_index=True, width="stretch", height=min(350, 35 * len(losers) + 38))
        else:
            st.info("No decliners")
    
    with st.expander("💡 Growth Insights", expanded=False):
        _render_growth_insights(compare_df, gainers, losers, dim_col, dimension, metric)


def _render_new_and_lost(compare_df, dim_col, dimension, metric):
    new_items = compare_df[compare_df['status'] == '🆕 New'].nlargest(15, 'current')
    lost_items = compare_df[compare_df['status'] == '❌ Lost'].nlargest(15, 'previous')
    
    col_chart, col_waterfall = st.columns([1, 2])
    with col_chart:
        st.altair_chart(build_new_lost_chart(new_items, lost_items, dim_col, f"New vs Lost {metric}"), width="stretch")
    with col_waterfall:
        st.altair_chart(build_waterfall_chart(compare_df, dim_col, f"Top Contributors to {metric} Change", 8), width="stretch")
    
    col_new, col_lost = st.columns(2)
    with col_new:
        st.markdown("##### 🆕 New")
        if not new_items.empty:
            st.dataframe(pd.DataFrame({
                '#': range(1, len(new_items) + 1),
                dimension: new_items[dim_col].values,
                f'Current {metric}': new_items['current'].apply(lambda x: f"${x:,.0f}").values,
            }), hide_index=True, width="stretch", height=min(350, 35 * len(new_items) + 38))
        else:
            st.info(f"No new {dimension}s")
    with col_lost:
        st.markdown("##### ❌ Lost")
        if not lost_items.empty:
            st.dataframe(pd.DataFrame({
                '#': range(1, len(lost_items) + 1),
                dimension: lost_items[dim_col].values,
                f'Previous {metric}': lost_items['previous'].apply(lambda x: f"${x:,.0f}").values,
            }), hide_index=True, width="stretch", height=min(350, 35 * len(lost_items) + 38))
        else:
            st.info(f"No lost {dimension}s")


def _render_full_comparison(compare_df, dim_col, dimension, metric):
    col_chart, col_summary = st.columns([3, 1])
    with col_chart:
        top_15 = compare_df.head(15)
        if not top_15.empty:
            st.altair_chart(build_growth_comparison_chart(
                top_15, 'current', 'previous', dim_col,
                f"Top {dimension}s: Current vs Previous {metric}", 15
            ), width="stretch")
    with col_summary:
        tc = compare_df['current'].sum()
        tp = compare_df['previous'].sum()
        change = tc - tp
        gpct = (change / tp * 100) if tp > 0 else 0
        st.markdown("##### 📊 Summary")
        st.metric("Total Current", f"${tc:,.0f}")
        st.metric("Total Previous", f"${tp:,.0f}")
        st.metric("Net Change", f"${change:+,.0f}", f"{gpct:+.1f}%")
        st.metric("Total Entities", f"{len(compare_df):,}")
    
    st.markdown("##### 📋 Complete Comparison List")
    src = compare_df.head(50)
    st.dataframe(pd.DataFrame({
        '#': range(1, len(src) + 1),
        dimension: src[dim_col].values,
        'Previous': src['previous'].apply(lambda x: f"${x:,.0f}").values,
        'Current': src['current'].apply(lambda x: f"${x:,.0f}").values,
        'Change': src['change'].apply(lambda x: f"${x:+,.0f}").values,
        'Growth %': src['growth_pct'].apply(lambda x: f"{x:+.1f}%").values,
        'Status': src['status'].values,
    }), hide_index=True, width="stretch", height=400)


def _render_growth_insights(compare_df, gainers, losers, dim_col, dimension, metric):
    tc = compare_df['current'].sum()
    tp = compare_df['previous'].sum()
    total_change = tc - tp
    
    new_value = compare_df[compare_df['status'] == '🆕 New']['current'].sum()
    lost_value = compare_df[compare_df['status'] == '❌ Lost']['previous'].sum()
    
    top_g_name = gainers.iloc[0][dim_col] if not gainers.empty else 'N/A'
    top_g_change = gainers.iloc[0]['change'] if not gainers.empty else 0
    top_d_name = losers.iloc[0][dim_col] if not losers.empty else 'N/A'
    top_d_change = losers.iloc[0]['change'] if not losers.empty else 0
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
**📊 Growth Summary:**
- **Total Growth**: ${total_change:+,.0f} ({(total_change/tp*100 if tp > 0 else 0):+.1f}%)
- **Net from New/Lost**: ${new_value - lost_value:+,.0f}

**📈 Top Gainer**: {top_g_name} (${top_g_change:+,.0f})
**📉 Top Decliner**: {top_d_name} (${top_d_change:+,.0f})
        """)
    with c2:
        counts = compare_df['status'].value_counts()
        st.markdown(f"""
**📋 Status Breakdown:**
- 🆕 **New**: {counts.get('🆕 New', 0):,} (${new_value:,.0f})
- ❌ **Lost**: {counts.get('❌ Lost', 0):,} (${lost_value:,.0f})
- 📈 **Growing**: {counts.get('📈 Growing', 0):,}
- 📉 **Declining**: {counts.get('📉 Declining', 0):,}
- ➡️ **Stable**: {counts.get('➡️ Stable', 0):,}

**🎯 Top 10 Gainers**: ${gainers.head(10)['change'].sum():+,.0f}
**🎯 Top 10 Decliners**: ${losers.head(10)['change'].sum():+,.0f}
        """)