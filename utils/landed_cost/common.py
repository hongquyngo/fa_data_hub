"""
Landed Cost - Common Display Helpers
Formatting, chart builders, and shared UI components.
"""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px


# ============================================================
# Formatting
# ============================================================

def format_usd(value, decimals=2):
    """Format number as USD currency string."""
    if pd.isna(value) or value is None:
        return "N/A"
    return f"${value:,.{decimals}f}"


def format_quantity(value, decimals=2):
    """Format quantity with thousand separators."""
    if pd.isna(value) or value is None:
        return "N/A"
    return f"{value:,.{decimals}f}"


def format_pct_change(value):
    """Format percentage change with color indicator."""
    if pd.isna(value) or value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


# ============================================================
# Plotly Layout Defaults
# ============================================================

def _plotly_layout_defaults(fig, height=400):
    """Apply consistent plotly layout styling."""
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        font=dict(size=11),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.1)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.1)"),
    )
    return fig


# ============================================================
# Chart Builders
# ============================================================

def build_cost_trend_chart(df):
    """
    Line chart showing average landed cost trend by year.
    df should have: cost_year, average_landed_cost_usd, and optionally pt_code/product_pn.
    """
    if df.empty:
        return None

    fig = go.Figure()

    if "pt_code" in df.columns and df["pt_code"].nunique() <= 15:
        # Multi-product view
        for pt_code in df["pt_code"].unique():
            mask = df["pt_code"] == pt_code
            product_df = df[mask].sort_values("cost_year")
            name = product_df["product_pn"].iloc[0] if "product_pn" in product_df.columns else pt_code
            display_name = f"{pt_code} - {name}" if len(str(name)) < 30 else pt_code
            fig.add_trace(go.Scatter(
                x=product_df["cost_year"],
                y=product_df["average_landed_cost_usd"],
                mode="lines+markers",
                name=display_name,
                hovertemplate=(
                    f"<b>{display_name}</b><br>"
                    "Year: %{x}<br>"
                    "Avg Cost: $%{y:,.4f}<br>"
                    "<extra></extra>"
                ),
            ))
    else:
        # Aggregated view
        agg = df.groupby("cost_year").agg(
            total_value=("total_landed_value_usd", "sum"),
            total_qty=("total_quantity", "sum"),
        ).reset_index()
        agg["weighted_avg_cost"] = agg["total_value"] / agg["total_qty"]
        agg = agg.sort_values("cost_year")

        fig.add_trace(go.Scatter(
            x=agg["cost_year"],
            y=agg["weighted_avg_cost"],
            mode="lines+markers",
            name="Weighted Avg Cost",
            line=dict(width=2.5, color="#1f77b4"),
            marker=dict(size=8),
            hovertemplate=(
                "Year: %{x}<br>"
                "Weighted Avg: $%{y:,.4f}<br>"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        title="Average Landed Cost Trend (USD)",
        xaxis_title="Year",
        yaxis_title="Avg Landed Cost (USD)",
        yaxis_tickprefix="$",
        hovermode="x unified",
    )
    fig = _plotly_layout_defaults(fig, height=420)
    return fig


def build_cost_distribution_chart(df, year=None):
    """Box plot of landed cost distribution by brand."""
    if df.empty:
        return None

    title = f"Cost Distribution by Brand"
    if year:
        title += f" ({year})"

    fig = px.box(
        df,
        x="brand",
        y="average_landed_cost_usd",
        color="brand",
        title=title,
        labels={
            "average_landed_cost_usd": "Avg Landed Cost (USD)",
            "brand": "Brand",
        },
        hover_data=["pt_code", "product_pn"],
    )
    fig.update_layout(
        yaxis_tickprefix="$",
        showlegend=False,
    )
    fig = _plotly_layout_defaults(fig, height=400)
    return fig


def build_source_breakdown_chart(df):
    """Stacked bar chart: arrival vs opening balance quantity by year."""
    if df.empty:
        return None

    agg = df.groupby("cost_year").agg(
        arrival_qty=("arrival_quantity", "sum"),
        ob_qty=("opening_balance_quantity", "sum"),
    ).reset_index().sort_values("cost_year")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=agg["cost_year"],
        y=agg["arrival_qty"],
        name="Arrivals",
        marker_color="#2196F3",
        hovertemplate="Year: %{x}<br>Arrival Qty: %{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=agg["cost_year"],
        y=agg["ob_qty"],
        name="Opening Balance",
        marker_color="#FF9800",
        hovertemplate="Year: %{x}<br>OB Qty: %{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        title="Quantity by Source Type",
        barmode="stack",
        xaxis_title="Year",
        yaxis_title="Quantity",
        hovermode="x unified",
    )
    fig = _plotly_layout_defaults(fig, height=380)
    return fig


def build_yoy_comparison_table(df):
    """
    Build a year-over-year comparison DataFrame.
    Input df should have: cost_year, pt_code, product_pn, brand, average_landed_cost_usd, etc.
    Returns a wide-format DataFrame with YoY change columns.
    """
    if df.empty:
        return pd.DataFrame()

    years = sorted(df["cost_year"].unique(), reverse=True)
    if len(years) < 2:
        return df

    current_year = years[0]
    prev_year = years[1]

    current = df[df["cost_year"] == current_year][
        ["pt_code", "product_pn", "brand", "legal_entity", "standard_uom",
         "average_landed_cost_usd", "total_quantity"]
    ].rename(columns={
        "average_landed_cost_usd": f"cost_{current_year}",
        "total_quantity": f"qty_{current_year}",
    })

    prev = df[df["cost_year"] == prev_year][
        ["pt_code", "legal_entity", "average_landed_cost_usd", "total_quantity"]
    ].rename(columns={
        "average_landed_cost_usd": f"cost_{prev_year}",
        "total_quantity": f"qty_{prev_year}",
    })

    merged = current.merge(
        prev, on=["pt_code", "legal_entity"], how="outer"
    )

    # Calculate YoY change
    cost_curr = f"cost_{current_year}"
    cost_prev = f"cost_{prev_year}"
    merged["yoy_change_pct"] = (
        (merged[cost_curr] - merged[cost_prev]) / merged[cost_prev] * 100
    ).round(1)

    merged["yoy_change_usd"] = (
        merged[cost_curr] - merged[cost_prev]
    ).round(4)

    return merged.sort_values("yoy_change_pct", ascending=False, na_position="last")


# ============================================================
# Styled DataFrame for Display
# ============================================================

def style_cost_dataframe(df):
    """Apply conditional formatting to cost DataFrame for st.dataframe."""
    if df.empty:
        return df

    format_dict = {}
    for col in df.columns:
        if "cost" in col.lower() or "value" in col.lower():
            format_dict[col] = "${:,.4f}"
        elif "quantity" in col.lower() or "qty" in col.lower():
            format_dict[col] = "{:,.2f}"
        elif "pct" in col.lower() or "change_pct" in col.lower():
            format_dict[col] = "{:+.1f}%"

    return format_dict