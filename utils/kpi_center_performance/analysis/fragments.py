# utils/kpi_center_performance/analysis/fragments.py
"""
Streamlit Fragments for KPI Center Performance - Analysis Tab.

VERSION: 6.2.0

Changes:
- v6.2.0: Added @st.fragment for partial rerun, added detail data table next to chart,
          improved Growth Analysis with charts (movers bar, waterfall, new/lost summary,
          status distribution) and insights expander.
- v6.1.0: Optimized for performance with proper data caching.
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
    build_status_distribution_chart
)

logger = logging.getLogger(__name__)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def analysis_tab_fragment(
    sales_df: pd.DataFrame,
    prev_sales_df: pd.DataFrame = None,
    filter_values: Dict = None,
    metrics_calculator = None,
    fragment_key: str = "analysis"
):
    """
    Main Analysis Tab entry point.
    
    Uses @st.fragment on sub-tabs for partial rerun when widgets change.
    
    Args:
        sales_df: Current period sales data
        prev_sales_df: Previous period sales data (for YoY)
        filter_values: Active filters from sidebar
        metrics_calculator: KPICenterMetrics instance
        fragment_key: Unique key prefix for widgets
    """
    if sales_df.empty:
        st.info("📊 No data available for analysis. Please adjust your filters.")
        return
    
    # Header
    _render_header()
    
    # Pre-aggregate all data once (cached in session)
    agg_data = _get_cached_aggregations(sales_df, fragment_key)
    
    # Two main tabs
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
    """Render analysis tab header."""
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

---

**📊 Key Metrics Explained:**

**1️⃣ Top Count**
- Number of entities (customers/brands/products) that together contribute to the selected threshold % of total value
- Example: "6 of 31 total" means 6 customers make up 80% of revenue

**2️⃣ CR10 (Concentration Ratio - Top 10%)**
- Formula: `CR10 = (Value of Top 10% entities) / (Total Value) × 100`
- Measures how much the top 10% of entities contribute to total
- **Interpretation:**
  - **> 70%**: High concentration - few entities dominate
  - **40-70%**: Moderate concentration
  - **< 40%**: Low concentration - diversified base

**3️⃣ HHI (Herfindahl-Hirschman Index)**
- Formula: `HHI = Σ(market_share²) × 10,000`
- Where market_share = entity_value / total_value
- Range: **0 to 10,000**
- **Interpretation:**
  - **< 1,500**: Low concentration (competitive/diversified)
  - **1,500 - 2,500**: Moderate concentration
  - **> 2,500**: High concentration (dominated by few)
- Used by regulators (FTC, DOJ) to assess market competition

---

**💡 Example:**
If you have 3 customers with 50%, 30%, 20% share:
- HHI = (0.5² + 0.3² + 0.2²) × 10,000
- HHI = (0.25 + 0.09 + 0.04) × 10,000 = **3,800** (High)

---

**🎯 Threshold Slider:**
- Adjusts the cumulative % cutoff (default 80%)
- Shows entities contributing up to that % of total
- Based on Pareto Principle (80/20 rule)
            """)


# =============================================================================
# DATA CACHING
# =============================================================================

def _get_cached_aggregations(sales_df: pd.DataFrame, key_prefix: str) -> Dict:
    """
    Pre-aggregate data for all dimensions. Cache in session state.
    """
    cache_key = f"_analysis_agg_{key_prefix}"
    
    # Check if data changed (simple row count check)
    data_hash = f"{len(sales_df)}_{sales_df['sales_by_kpi_center_usd'].sum():.0f}"
    hash_key = f"{cache_key}_hash"
    
    if cache_key in st.session_state and st.session_state.get(hash_key) == data_hash:
        return st.session_state[cache_key]
    
    # Aggregate for each dimension
    agg_data = {
        'customer': _aggregate_dimension(sales_df, 'customer'),
        'brand': _aggregate_dimension(sales_df, 'brand'),
        'product_pn': _aggregate_dimension(sales_df, 'product_pn'),
    }
    
    st.session_state[cache_key] = agg_data
    st.session_state[hash_key] = data_hash
    
    return agg_data


def _aggregate_dimension(sales_df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Aggregate sales data by dimension with all metrics."""
    agg_dict = {
        'sales_by_kpi_center_usd': 'sum',
        'gross_profit_by_kpi_center_usd': 'sum',
        'inv_number': pd.Series.nunique
    }
    
    if 'gp1_by_kpi_center_usd' in sales_df.columns:
        agg_dict['gp1_by_kpi_center_usd'] = 'sum'
    
    agg_df = sales_df.groupby(dimension).agg(agg_dict).reset_index()
    
    # Rename columns
    agg_df = agg_df.rename(columns={
        'sales_by_kpi_center_usd': 'revenue',
        'gross_profit_by_kpi_center_usd': 'gross_profit',
        'gp1_by_kpi_center_usd': 'gp1',
        'inv_number': 'orders'
    })
    
    if 'gp1' not in agg_df.columns:
        agg_df['gp1'] = 0
    
    return agg_df


# =============================================================================
# TOP PERFORMERS TAB
# =============================================================================

@st.fragment
def _top_performers_tab(agg_data: Dict, key_prefix: str):
    """Unified Top Performers Analysis with cached data. Uses @st.fragment for partial rerun."""
    
    # Header row with slider
    col_tabs, col_slider = st.columns([4, 2])
    
    with col_slider:
        threshold_pct = st.slider(
            "Threshold %",
            min_value=50, max_value=100, value=80, step=5,
            key=f"{key_prefix}_threshold",
            help="Show performers contributing to this % of total"
        )
    
    threshold = threshold_pct / 100
    
    # Dimension tabs
    dim_tab1, dim_tab2, dim_tab3 = st.tabs(["👥 Customer", "🏭 Brand", "📦 Product"])
    
    with dim_tab1:
        _render_dimension_analysis(
            agg_df=agg_data['customer'],
            dimension='customer',
            dimension_label='Customer',
            threshold=threshold,
            key_prefix=f"{key_prefix}_cust"
        )
    
    with dim_tab2:
        _render_dimension_analysis(
            agg_df=agg_data['brand'],
            dimension='brand',
            dimension_label='Brand',
            threshold=threshold,
            key_prefix=f"{key_prefix}_brand"
        )
    
    with dim_tab3:
        _render_dimension_analysis(
            agg_df=agg_data['product_pn'],
            dimension='product_pn',
            dimension_label='Product',
            threshold=threshold,
            key_prefix=f"{key_prefix}_prod"
        )


def _render_dimension_analysis(
    agg_df: pd.DataFrame,
    dimension: str,
    dimension_label: str,
    threshold: float,
    key_prefix: str
):
    """Render analysis for a dimension with metric sub-tabs."""
    
    metric_tab1, metric_tab2, metric_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
    
    with metric_tab1:
        _render_metric_view(agg_df, dimension, dimension_label, 'revenue', 'Revenue', threshold)
    
    with metric_tab2:
        _render_metric_view(agg_df, dimension, dimension_label, 'gross_profit', 'Gross Profit', threshold)
    
    with metric_tab3:
        _render_metric_view(agg_df, dimension, dimension_label, 'gp1', 'GP1', threshold)


def _render_metric_view(
    agg_df: pd.DataFrame,
    dimension: str,
    dimension_label: str,
    metric: str,
    metric_label: str,
    threshold: float
):
    """Render complete view for dimension + metric with chart and data table."""
    
    if agg_df.empty or agg_df[metric].sum() == 0:
        st.warning(f"No {metric_label} data available")
        return
    
    # Prepare top performers data
    top_df, total_value, total_count = _prepare_top_performers(agg_df, dimension, metric, threshold)
    
    if top_df.empty:
        st.warning("No data to display")
        return
    
    # Metrics cards
    _render_metrics_cards(top_df, agg_df, dimension_label, metric, metric_label, threshold, total_value, total_count)
    
    # Chart (left) + Data Table (right)
    col_chart, col_table = st.columns([3, 2])
    
    with col_chart:
        # Pareto chart
        chart = build_pareto_chart(
            data_df=top_df,
            value_col=metric,
            label_col=dimension,
            title=f"Top {dimension_label}s by {metric_label}",
            metric_type=metric
        )
        st.altair_chart(chart, use_container_width=True)
    
    with col_table:
        # Data table
        _render_detail_table(top_df, dimension, dimension_label, metric, metric_label)
    
    # Insights
    _render_insights(top_df, agg_df, dimension, dimension_label, metric, metric_label, threshold, total_value)


def _prepare_top_performers(
    agg_df: pd.DataFrame,
    dimension: str,
    metric: str,
    threshold: float
) -> tuple:
    """
    Prepare top performers data with cumulative calculations.
    
    Logic: Include first performer that EXCEEDS threshold (> not >=).
    """
    # Sort descending
    sorted_df = agg_df.sort_values(metric, ascending=False).copy()
    sorted_df = sorted_df.reset_index(drop=True)
    
    total_value = sorted_df[metric].sum()
    total_count = len(sorted_df)
    
    if total_value == 0:
        return pd.DataFrame(), 0, total_count
    
    # Calculate cumulative
    sorted_df['cumulative_value'] = sorted_df[metric].cumsum()
    sorted_df['cumulative_percent'] = sorted_df['cumulative_value'] / total_value
    sorted_df['percent_contribution'] = sorted_df[metric] / total_value * 100
    
    # Find cutoff: first row that EXCEEDS threshold
    exceed_mask = sorted_df['cumulative_percent'] > threshold
    
    if exceed_mask.any():
        first_exceed_idx = exceed_mask.idxmax()
        top_df = sorted_df.loc[:first_exceed_idx].copy()
    else:
        top_df = sorted_df.copy()
    
    return top_df, total_value, total_count


def _render_detail_table(
    top_df: pd.DataFrame,
    dimension: str,
    dimension_label: str,
    metric: str,
    metric_label: str
):
    """Render detail data table for top performers."""
    st.markdown(f"##### 📋 Top {dimension_label}s Detail")
    
    # Prepare display DataFrame
    display_df = pd.DataFrame({
        '#': range(1, len(top_df) + 1),
        dimension_label: top_df[dimension].values,
        metric_label: top_df[metric].apply(lambda x: f"${x:,.0f}").values,
        '% Share': top_df['percent_contribution'].apply(lambda x: f"{x:.1f}%").values,
        'Cumul.%': top_df['cumulative_percent'].apply(lambda x: f"{x:.1%}").values,
    })
    
    # Add GP Margin if both revenue and gross_profit available
    if 'revenue' in top_df.columns and 'gross_profit' in top_df.columns and metric in ['revenue', 'gross_profit']:
        display_df['GP%'] = (top_df['gross_profit'] / top_df['revenue'].replace(0, float('nan')) * 100).apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "-"
        ).values
    
    # Add orders if available
    if 'orders' in top_df.columns:
        display_df['Orders'] = top_df['orders'].apply(lambda x: f"{x:,}").values
    
    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        height=min(400, 35 * len(display_df) + 38)  # Dynamic height based on rows
    )


def _render_metrics_cards(
    top_df: pd.DataFrame,
    agg_df: pd.DataFrame,
    dimension_label: str,
    metric: str,
    metric_label: str,
    threshold: float,
    total_value: float,
    total_count: int
):
    """Render 4 metrics cards."""
    top_count = len(top_df)
    top_value = top_df[metric].sum()
    actual_percent = (top_value / total_value * 100) if total_value > 0 else 0
    
    # CR10
    top_10_count = max(1, int(total_count * 0.1))
    sorted_agg = agg_df.sort_values(metric, ascending=False)
    top_10_value = sorted_agg.head(top_10_count)[metric].sum()
    cr_10 = (top_10_value / total_value * 100) if total_value > 0 else 0
    
    # HHI
    shares = agg_df[metric] / total_value if total_value > 0 else 0
    hhi = (shares ** 2).sum() * 10000
    hhi_level = "Low" if hhi < 1500 else "Moderate" if hhi < 2500 else "High"
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(f"Top {dimension_label}s", f"{top_count:,}", f"of {total_count:,} total")
    
    with col2:
        st.metric(f"{int(threshold*100)}% {metric_label}", f"${top_value:,.0f}", f"{actual_percent:.1f}% of total")
    
    with col3:
        st.metric("CR10 (Top 10%)", f"{cr_10:.1f}%")
    
    with col4:
        st.metric("HHI Index", f"{hhi:,.0f}", hhi_level)


def _render_insights(
    top_df: pd.DataFrame,
    agg_df: pd.DataFrame,
    dimension: str,
    dimension_label: str,
    metric: str,
    metric_label: str,
    threshold: float,
    total_value: float
):
    """Render insights expander."""
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
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"""
**📊 Concentration:**
- **Top 1**: {top_1_name} = {top_1_pct:.1f}% of {metric_label}
- **Top 3**: {top_3_share:.1f}% of {metric_label}
- **{int(threshold*100)}% threshold**: {top_count:,} {dimension_label}s ({concentration_pct:.1f}% of base)
            """)
        
        with col2:
            if 'revenue' in top_df.columns and 'gross_profit' in top_df.columns:
                total_revenue = top_df['revenue'].sum()
                total_gp = top_df['gross_profit'].sum()
                avg_margin = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
                
                st.markdown(f"""
**💰 Profitability (Top {top_count}):**
- Average GP Margin: **{avg_margin:.1f}%**
- Total Revenue: ${total_revenue:,.0f}
- Total GP: ${total_gp:,.0f}
                """)


# =============================================================================
# GROWTH ANALYSIS TAB
# =============================================================================

@st.fragment
def _growth_analysis_tab(
    sales_df: pd.DataFrame,
    prev_sales_df: pd.DataFrame = None,
    key_prefix: str = "growth"
):
    """Year-over-Year growth analysis. Uses @st.fragment for partial rerun."""
    
    st.markdown("#### 📈 Growth Analysis (YoY)")
    
    if prev_sales_df is None or prev_sales_df.empty:
        st.info("📊 No previous period data available for YoY comparison.")
        st.caption("Enable 'Show YoY' in sidebar filters to load comparison data.")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        dimension = st.selectbox("Compare by", ["Customer", "Brand", "Product"], key=f"{key_prefix}_dim")
    
    with col2:
        metric = st.selectbox("Metric", ["Revenue", "Gross Profit"], key=f"{key_prefix}_metric")
    
    dim_col = {"Customer": "customer", "Brand": "brand", "Product": "product_pn"}.get(dimension)
    value_col = {"Revenue": "sales_by_kpi_center_usd", "Gross Profit": "gross_profit_by_kpi_center_usd"}.get(metric)
    
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
    """Build comparison DataFrame."""
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
    """Render growth summary metrics."""
    total_current = compare_df['current'].sum()
    total_previous = compare_df['previous'].sum()
    total_growth = ((total_current - total_previous) / total_previous * 100) if total_previous > 0 else 0
    
    new_count = len(compare_df[compare_df['status'] == '🆕 New'])
    lost_count = len(compare_df[compare_df['status'] == '❌ Lost'])
    growing_count = len(compare_df[compare_df['status'] == '📈 Growing'])
    declining_count = len(compare_df[compare_df['status'] == '📉 Declining'])
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(f"Total {metric}", f"${total_current:,.0f}", f"{total_growth:+.1f}%")
    with col2:
        st.metric("🆕 New", f"{new_count:,}")
    with col3:
        st.metric("❌ Lost", f"{lost_count:,}")
    with col4:
        st.metric("📈 Growing", f"{growing_count:,}")
    with col5:
        st.metric("📉 Declining", f"{declining_count:,}")


def _render_top_movers(compare_df, dim_col, dimension, metric):
    """Render top gainers and decliners with chart and tables."""
    gainers = compare_df[compare_df['change'] > 0].nlargest(10, 'change')
    losers = compare_df[compare_df['change'] < 0].nsmallest(10, 'change')
    
    # Chart section
    col_chart, col_status = st.columns([3, 1])
    
    with col_chart:
        # Movers bar chart
        chart = build_movers_bar_chart(
            gainers_df=gainers,
            decliners_df=losers,
            label_col=dim_col,
            title=f"Top {dimension} Movers by {metric}"
        )
        st.altair_chart(chart, use_container_width=True)
    
    with col_status:
        # Status distribution
        status_chart = build_status_distribution_chart(
            compare_df=compare_df,
            title="Status Distribution"
        )
        st.altair_chart(status_chart, use_container_width=True)
    
    # Tables section
    col_gain, col_lose = st.columns(2)
    
    with col_gain:
        st.markdown("##### 📈 Top Gainers")
        if not gainers.empty:
            display_df = pd.DataFrame({
                '#': range(1, len(gainers) + 1),
                dimension: gainers[dim_col].values,
                'Previous': gainers['previous'].apply(lambda x: f"${x:,.0f}").values,
                'Current': gainers['current'].apply(lambda x: f"${x:,.0f}").values,
                'Change': gainers['change'].apply(lambda x: f"${x:+,.0f}").values,
                'Growth %': gainers['growth_pct'].apply(lambda x: f"{x:+.1f}%").values,
            })
            st.dataframe(display_df, hide_index=True, use_container_width=True,
                        height=min(350, 35 * len(display_df) + 38))
        else:
            st.info("No gainers")
    
    with col_lose:
        st.markdown("##### 📉 Top Decliners")
        if not losers.empty:
            display_df = pd.DataFrame({
                '#': range(1, len(losers) + 1),
                dimension: losers[dim_col].values,
                'Previous': losers['previous'].apply(lambda x: f"${x:,.0f}").values,
                'Current': losers['current'].apply(lambda x: f"${x:,.0f}").values,
                'Change': losers['change'].apply(lambda x: f"${x:+,.0f}").values,
                'Growth %': losers['growth_pct'].apply(lambda x: f"{x:+.1f}%").values,
            })
            st.dataframe(display_df, hide_index=True, use_container_width=True,
                        height=min(350, 35 * len(display_df) + 38))
        else:
            st.info("No decliners")
    
    # Insights expander
    with st.expander("💡 Growth Insights", expanded=False):
        _render_growth_insights(compare_df, gainers, losers, dim_col, dimension, metric)


def _render_new_and_lost(compare_df, dim_col, dimension, metric):
    """Render new and lost items with chart and tables."""
    new_items = compare_df[compare_df['status'] == '🆕 New'].nlargest(15, 'current')
    lost_items = compare_df[compare_df['status'] == '❌ Lost'].nlargest(15, 'previous')
    
    # Summary chart
    col_chart, col_waterfall = st.columns([1, 2])
    
    with col_chart:
        chart = build_new_lost_chart(
            new_df=new_items,
            lost_df=lost_items,
            label_col=dim_col,
            title=f"New vs Lost {metric} Impact"
        )
        st.altair_chart(chart, use_container_width=True)
    
    with col_waterfall:
        # Waterfall chart for contribution
        waterfall = build_waterfall_chart(
            compare_df=compare_df,
            label_col=dim_col,
            title=f"Top Contributors to {metric} Change",
            top_n=8
        )
        st.altair_chart(waterfall, use_container_width=True)
    
    # Tables section
    col_new, col_lost = st.columns(2)
    
    with col_new:
        st.markdown("##### 🆕 New")
        if not new_items.empty:
            display_df = pd.DataFrame({
                '#': range(1, len(new_items) + 1),
                dimension: new_items[dim_col].values,
                f'Current {metric}': new_items['current'].apply(lambda x: f"${x:,.0f}").values,
            })
            st.dataframe(display_df, hide_index=True, use_container_width=True,
                        height=min(350, 35 * len(display_df) + 38))
        else:
            st.info(f"No new {dimension}s")
    
    with col_lost:
        st.markdown("##### ❌ Lost")
        if not lost_items.empty:
            display_df = pd.DataFrame({
                '#': range(1, len(lost_items) + 1),
                dimension: lost_items[dim_col].values,
                f'Previous {metric}': lost_items['previous'].apply(lambda x: f"${x:,.0f}").values,
            })
            st.dataframe(display_df, hide_index=True, use_container_width=True,
                        height=min(350, 35 * len(display_df) + 38))
        else:
            st.info(f"No lost {dimension}s")


def _render_full_comparison(compare_df, dim_col, dimension, metric):
    """Render full comparison with comparison chart and table."""
    
    # Comparison bar chart
    col_chart, col_summary = st.columns([3, 1])
    
    with col_chart:
        # Grouped bar chart - Current vs Previous
        top_15 = compare_df.head(15).copy()
        
        if not top_15.empty:
            chart = build_growth_comparison_chart(
                data_df=top_15,
                current_col='current',
                previous_col='previous',
                label_col=dim_col,
                title=f"Top {dimension}s: Current vs Previous {metric}",
                top_n=15
            )
            st.altair_chart(chart, use_container_width=True)
    
    with col_summary:
        # Quick summary stats
        total_current = compare_df['current'].sum()
        total_previous = compare_df['previous'].sum()
        total_change = total_current - total_previous
        growth_pct = (total_change / total_previous * 100) if total_previous > 0 else 0
        
        st.markdown("##### 📊 Summary")
        st.metric("Total Current", f"${total_current:,.0f}")
        st.metric("Total Previous", f"${total_previous:,.0f}")
        st.metric("Net Change", f"${total_change:+,.0f}", f"{growth_pct:+.1f}%")
        st.metric("Total Entities", f"{len(compare_df):,}")
    
    # Full table
    st.markdown("##### 📋 Complete Comparison List")
    source_df = compare_df.head(50)
    display_df = pd.DataFrame({
        '#': range(1, len(source_df) + 1),
        dimension: source_df[dim_col].values,
        'Previous': source_df['previous'].apply(lambda x: f"${x:,.0f}").values,
        'Current': source_df['current'].apply(lambda x: f"${x:,.0f}").values,
        'Change': source_df['change'].apply(lambda x: f"${x:+,.0f}").values,
        'Growth %': source_df['growth_pct'].apply(lambda x: f"{x:+.1f}%").values,
        'Status': source_df['status'].values,
    })
    st.dataframe(display_df, hide_index=True, use_container_width=True, height=400)


def _render_growth_insights(compare_df, gainers, losers, dim_col, dimension, metric):
    """Render growth analysis insights."""
    total_current = compare_df['current'].sum()
    total_previous = compare_df['previous'].sum()
    total_change = total_current - total_previous
    
    # Status counts
    new_count = len(compare_df[compare_df['status'] == '🆕 New'])
    lost_count = len(compare_df[compare_df['status'] == '❌ Lost'])
    growing_count = len(compare_df[compare_df['status'] == '📈 Growing'])
    declining_count = len(compare_df[compare_df['status'] == '📉 Declining'])
    stable_count = len(compare_df[compare_df['status'] == '➡️ Stable'])
    
    # Value metrics
    new_value = compare_df[compare_df['status'] == '🆕 New']['current'].sum()
    lost_value = compare_df[compare_df['status'] == '❌ Lost']['previous'].sum()
    
    col1, col2 = st.columns(2)
    
    with col1:
        top_gainer_name = gainers.iloc[0][dim_col] if not gainers.empty else 'N/A'
        top_gainer_change = gainers.iloc[0]['change'] if not gainers.empty else 0
        top_gainer_pct = gainers.iloc[0]['growth_pct'] if not gainers.empty else 0
        
        top_decliner_name = losers.iloc[0][dim_col] if not losers.empty else 'N/A'
        top_decliner_change = losers.iloc[0]['change'] if not losers.empty else 0
        top_decliner_pct = losers.iloc[0]['growth_pct'] if not losers.empty else 0
        
        st.markdown(f"""
**📊 Growth Summary:**
- **Total Growth**: ${total_change:+,.0f} ({(total_change/total_previous*100 if total_previous > 0 else 0):+.1f}%)
- **Net from New/Lost**: ${new_value - lost_value:+,.0f}

**📈 Top Gainer**: {top_gainer_name}
- Change: ${top_gainer_change:+,.0f} ({top_gainer_pct:+.1f}%)

**📉 Top Decliner**: {top_decliner_name}
- Change: ${top_decliner_change:+,.0f} ({top_decliner_pct:+.1f}%)
        """)
    
    with col2:
        st.markdown(f"""
**📋 Status Breakdown:**
- 🆕 **New**: {new_count:,} {dimension}s (${new_value:,.0f})
- ❌ **Lost**: {lost_count:,} {dimension}s (${lost_value:,.0f})
- 📈 **Growing**: {growing_count:,} {dimension}s (>10% growth)
- 📉 **Declining**: {declining_count:,} {dimension}s (<-10% decline)
- ➡️ **Stable**: {stable_count:,} {dimension}s (±10%)

**🎯 Concentration:**
- Top 10 Gainers contribute: ${gainers.head(10)['change'].sum():+,.0f}
- Top 10 Decliners contribute: ${losers.head(10)['change'].sum():+,.0f}
        """)