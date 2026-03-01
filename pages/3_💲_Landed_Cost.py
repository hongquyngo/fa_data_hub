"""
Page: Landed Cost Lookup & Analysis
Provides cost lookup, YoY comparison, and trend analysis
based on avg_landed_cost_looker_view.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from utils.auth import AuthManager
from utils.landed_cost.data import (
    get_filter_options,
    get_landed_cost_data,
    get_yoy_comparison,
    get_product_cost_history,
    get_summary_stats,
)
from utils.landed_cost.common import (
    format_usd,
    format_quantity,
    format_pct_change,
    build_cost_trend_chart,
    build_cost_distribution_chart,
    build_source_breakdown_chart,
    build_yoy_comparison_table,
    style_cost_dataframe,
)

# ============================================================
# AUTH
# ============================================================

auth = AuthManager()
auth.require_auth()

# ============================================================
# PAGE CONFIG
# ============================================================

PAGE_ICON = "💲"
PAGE_TITLE = "Landed Cost Lookup"


def render_header():
    st.markdown(f"## {PAGE_ICON} {PAGE_TITLE}")
    st.caption("Weighted average landed cost (USD) per product per entity per year")


# ============================================================
# SIDEBAR FILTERS
# ============================================================

def render_filters():
    """Render sidebar filters and return filter dict."""
    st.sidebar.markdown(f"### {PAGE_ICON} Filters")

    options = get_filter_options()
    current_year = datetime.now().year

    # --- Entity filter ---
    entity_df = options["entities"]
    selected_entities = st.sidebar.multiselect(
        "Legal Entity",
        options=entity_df["entity_id"].tolist(),
        format_func=lambda x: entity_df[entity_df["entity_id"] == x]["legal_entity"].iloc[0],
        default=[],
        key="lc_entity",
    )

    # --- Year filter ---
    available_years = options["years"]
    default_years = [y for y in available_years if y >= current_year - 1][:2]
    selected_years = st.sidebar.multiselect(
        "Cost Year",
        options=available_years,
        default=default_years if default_years else available_years[:2],
        key="lc_year",
    )

    # --- Brand filter ---
    selected_brands = st.sidebar.multiselect(
        "Brand",
        options=options["brands"],
        default=[],
        key="lc_brand",
    )

    # --- Product search ---
    product_search = st.sidebar.text_input(
        "🔍 Search Product (PT Code / Name)",
        value="",
        key="lc_product_search",
        placeholder="e.g. PT-001 or product name...",
    )

    return {
        "entity_ids": selected_entities or None,
        "brand_list": selected_brands or None,
        "year_list": selected_years or None,
        "product_search": product_search.strip() or None,
    }


# ============================================================
# TAB 1: COST LOOKUP (Main Table)
# ============================================================

def render_tab_lookup(df, filters):
    """Main cost lookup table with KPI cards."""
    current_year = datetime.now().year

    # --- KPI Cards ---
    stats = get_summary_stats(
        entity_ids=filters["entity_ids"],
        cost_year=filters["year_list"][0] if filters["year_list"] and len(filters["year_list"]) == 1 else None,
    )

    if stats is not None:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Products", f"{int(stats['total_products']):,}")
        with c2:
            st.metric("Brands", f"{int(stats['total_brands']):,}")
        with c3:
            st.metric("Total Value (USD)", format_usd(stats["total_value_usd"]))
        with c4:
            st.metric("Transactions", f"{int(stats['total_transactions']):,}")

    st.markdown("---")

    # --- Data Table ---
    if df.empty:
        st.info("No data found for the selected filters.")
        return

    st.markdown(f"**{len(df):,} records found**")

    # Prepare display columns
    display_cols = [
        "cost_year", "legal_entity", "pt_code", "product_pn", "brand",
        "standard_uom", "average_landed_cost_usd", "total_quantity",
        "total_landed_value_usd", "min_landed_cost_usd", "max_landed_cost_usd",
        "arrival_quantity", "opening_balance_quantity", "transaction_count",
    ]
    display_df = df[[c for c in display_cols if c in df.columns]].copy()

    # Column config for nice display
    column_config = {
        "cost_year": st.column_config.NumberColumn("Year", format="%d"),
        "legal_entity": "Entity",
        "pt_code": "PT Code",
        "product_pn": "Product",
        "brand": "Brand",
        "standard_uom": "UOM",
        "average_landed_cost_usd": st.column_config.NumberColumn(
            "Avg Cost (USD)", format="$%.4f"
        ),
        "total_quantity": st.column_config.NumberColumn(
            "Total Qty", format="%.2f"
        ),
        "total_landed_value_usd": st.column_config.NumberColumn(
            "Total Value (USD)", format="$%.2f"
        ),
        "min_landed_cost_usd": st.column_config.NumberColumn(
            "Min Cost", format="$%.4f"
        ),
        "max_landed_cost_usd": st.column_config.NumberColumn(
            "Max Cost", format="$%.4f"
        ),
        "arrival_quantity": st.column_config.NumberColumn(
            "Arrival Qty", format="%.2f"
        ),
        "opening_balance_quantity": st.column_config.NumberColumn(
            "OB Qty", format="%.2f"
        ),
        "transaction_count": st.column_config.NumberColumn(
            "Txn Count", format="%d"
        ),
    }

    st.dataframe(
        display_df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=min(len(display_df) * 35 + 40, 600),
    )

    # --- Export ---
    csv = display_df.to_csv(index=False)
    st.download_button(
        "📥 Export to CSV",
        data=csv,
        file_name=f"landed_cost_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        key="lc_export_csv",
    )


# ============================================================
# TAB 2: YoY COMPARISON
# ============================================================

def render_tab_yoy(filters):
    """Year-over-year cost comparison."""
    yoy_df = get_yoy_comparison(
        entity_ids=filters["entity_ids"],
        brand_list=filters["brand_list"],
    )

    if yoy_df.empty:
        st.info("No data available for YoY comparison.")
        return

    comparison = build_yoy_comparison_table(yoy_df)

    if comparison.empty:
        st.info("Need at least 2 years of data for comparison.")
        return

    years = sorted(yoy_df["cost_year"].unique(), reverse=True)
    current_year, prev_year = years[0], years[1]

    # --- Summary metrics ---
    has_increase = comparison["yoy_change_pct"].dropna()
    if not has_increase.empty:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            increased = (has_increase > 0).sum()
            st.metric("🔺 Cost Increased", f"{increased} products")
        with c2:
            decreased = (has_increase < 0).sum()
            st.metric("🔻 Cost Decreased", f"{decreased} products")
        with c3:
            unchanged = (has_increase == 0).sum()
            st.metric("➡️ Unchanged", f"{unchanged} products")
        with c4:
            avg_change = has_increase.mean()
            st.metric("Avg Change", format_pct_change(avg_change))

    st.markdown("---")

    # --- Highlight big changes ---
    significant = comparison[comparison["yoy_change_pct"].abs() > 10].copy()
    if not significant.empty:
        st.markdown(f"**⚠️ Significant changes (>10%) between {prev_year} → {current_year}:**")

        column_config_yoy = {
            f"cost_{current_year}": st.column_config.NumberColumn(
                f"Cost {current_year}", format="$%.4f"
            ),
            f"cost_{prev_year}": st.column_config.NumberColumn(
                f"Cost {prev_year}", format="$%.4f"
            ),
            "yoy_change_pct": st.column_config.NumberColumn(
                "YoY %", format="%.1f%%"
            ),
            "yoy_change_usd": st.column_config.NumberColumn(
                "YoY Δ (USD)", format="$%.4f"
            ),
        }

        st.dataframe(
            significant,
            column_config=column_config_yoy,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No significant cost changes (>10%) detected.")

    # --- Full comparison table ---
    with st.expander(f"📋 Full Comparison Table ({len(comparison)} products)", expanded=False):
        st.dataframe(comparison, use_container_width=True, hide_index=True)


# ============================================================
# TAB 3: ANALYTICS & CHARTS
# ============================================================

def render_tab_analytics(df, filters):
    """Charts and visual analysis."""
    if df.empty:
        st.info("No data for analytics. Adjust filters.")
        return

    # --- Cost Trend ---
    st.subheader("📈 Cost Trend")
    trend_chart = build_cost_trend_chart(df)
    if trend_chart:
        st.plotly_chart(trend_chart, use_container_width=True)

    col_left, col_right = st.columns(2)

    # --- Distribution by Brand ---
    with col_left:
        st.subheader("📊 Cost Distribution")
        year_for_dist = filters["year_list"][0] if filters["year_list"] else None
        dist_chart = build_cost_distribution_chart(df, year=year_for_dist)
        if dist_chart:
            st.plotly_chart(dist_chart, use_container_width=True)
        else:
            st.info("Not enough data for distribution chart.")

    # --- Source Breakdown ---
    with col_right:
        st.subheader("📦 Source Breakdown")
        source_chart = build_source_breakdown_chart(df)
        if source_chart:
            st.plotly_chart(source_chart, use_container_width=True)
        else:
            st.info("Not enough data for source chart.")

    # --- Top Cost Products ---
    st.markdown("---")
    st.subheader("💰 Top 20 Highest Cost Products")

    latest_year = df["cost_year"].max()
    top_df = (
        df[df["cost_year"] == latest_year]
        .nlargest(20, "average_landed_cost_usd")[
            ["pt_code", "product_pn", "brand", "legal_entity",
             "average_landed_cost_usd", "total_quantity", "total_landed_value_usd"]
        ]
    )

    if not top_df.empty:
        st.dataframe(
            top_df,
            column_config={
                "average_landed_cost_usd": st.column_config.NumberColumn("Avg Cost", format="$%.4f"),
                "total_landed_value_usd": st.column_config.NumberColumn("Total Value", format="$%.2f"),
                "total_quantity": st.column_config.NumberColumn("Qty", format="%.2f"),
            },
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# TAB 4: PRODUCT DETAIL
# ============================================================

def render_tab_product_detail(df, filters):
    """Drill-down into a specific product's cost history."""
    if df.empty:
        st.info("No data available. Adjust filters to see products.")
        return

    # Product selector
    product_options = df[["product_id", "pt_code", "product_pn"]].drop_duplicates()
    product_options["display"] = product_options["pt_code"] + " - " + product_options["product_pn"]

    selected_display = st.selectbox(
        "Select Product",
        options=product_options["display"].tolist(),
        key="lc_product_detail",
    )

    if not selected_display:
        return

    selected_row = product_options[product_options["display"] == selected_display].iloc[0]
    product_id = selected_row["product_id"]

    # Fetch full history
    history = get_product_cost_history(
        product_id=int(product_id),
        entity_id=filters["entity_ids"][0] if filters["entity_ids"] and len(filters["entity_ids"]) == 1 else None,
    )

    if history.empty:
        st.warning("No cost history found for this product.")
        return

    # Product info
    st.markdown(f"### {selected_row['pt_code']} - {selected_row['product_pn']}")

    # Cost history table
    st.markdown("**Cost History by Year:**")
    hist_display = history[[
        "cost_year", "legal_entity", "average_landed_cost_usd",
        "min_landed_cost_usd", "max_landed_cost_usd",
        "total_quantity", "total_landed_value_usd",
        "arrival_quantity", "opening_balance_quantity",
        "earliest_source_date", "latest_source_date",
    ]].copy()

    st.dataframe(
        hist_display,
        column_config={
            "cost_year": st.column_config.NumberColumn("Year", format="%d"),
            "average_landed_cost_usd": st.column_config.NumberColumn("Avg Cost", format="$%.4f"),
            "min_landed_cost_usd": st.column_config.NumberColumn("Min", format="$%.4f"),
            "max_landed_cost_usd": st.column_config.NumberColumn("Max", format="$%.4f"),
            "total_quantity": st.column_config.NumberColumn("Qty", format="%.2f"),
            "total_landed_value_usd": st.column_config.NumberColumn("Value", format="$%.2f"),
        },
        use_container_width=True,
        hide_index=True,
    )

    # Mini trend chart for this product
    if len(history) > 1:
        fig = build_cost_trend_chart(history)
        if fig:
            fig.update_layout(title=f"Cost Trend: {selected_row['pt_code']}")
            st.plotly_chart(fig, use_container_width=True)


# ============================================================
# MAIN APPLICATION
# ============================================================

def main():
    """Main entry point."""
    try:
        render_header()
        st.markdown("---")

        # Sidebar filters
        filters = render_filters()

        # Fetch main data
        df = get_landed_cost_data(**filters)

        # === Tabs ===
        tab_lookup, tab_yoy, tab_analytics, tab_detail = st.tabs([
            "📋 Cost Lookup",
            "📊 YoY Comparison",
            "📈 Analytics",
            "🔍 Product Detail",
        ])

        with tab_lookup:
            render_tab_lookup(df, filters)

        with tab_yoy:
            render_tab_yoy(filters)

        with tab_analytics:
            render_tab_analytics(df, filters)

        with tab_detail:
            render_tab_product_detail(df, filters)

    except Exception as e:
        st.error(f"Error loading Landed Cost page: {str(e)}")
        with st.expander("Error Details"):
            st.exception(e)


main()