"""
Landed Cost - Common Utilities (Refactored)
Formatting, chart builders, heatmap helpers, constants, and Excel export.

Version: 2.0.0
"""

import logging
from io import BytesIO
from typing import Any, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

logger = logging.getLogger(__name__)


# ================================================================
# Constants
# ================================================================

class LandedCostConstants:
    """Module-level constants."""
    MAX_MULTILINE_PRODUCTS = 15
    HEATMAP_TOP_N = 15
    TOP_PRODUCTS_N = 20
    SIGNIFICANT_CHANGE_PCT = 10.0

    COST_COLOR = "#4472C4"
    ACCENT_COLOR = "#ED7D31"
    ARRIVAL_COLOR = "#4472C4"
    OB_COLOR = "#ED7D31"
    TREND_COLORS = px.colors.qualitative.Set2


# ================================================================
# Formatting Helpers
# ================================================================

def format_usd(value: Any, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    try:
        return f"${float(value):,.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


def format_usd4(value: Any) -> str:
    """Format USD with 4 decimal places (for unit cost)."""
    return format_usd(value, decimals=4)


def format_quantity(value: Any, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    try:
        num = float(value)
        if num == int(num):
            return f"{int(num):,}"
        return f"{num:,.{decimals}f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return str(value)


def format_pct_change(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    try:
        v = float(value)
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.1f}%"
    except (ValueError, TypeError):
        return str(value)


def format_rate(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    try:
        return f"{float(value):,.4f}"
    except (ValueError, TypeError):
        return str(value)


def format_date(value: Any) -> str:
    if value is None:
        return "-"
    try:
        if isinstance(value, str):
            return value
        if hasattr(value, "strftime"):
            return value.strftime("%d/%m/%Y")
        return str(value)
    except Exception:
        return str(value)


def safe_get(data: dict, key: str, default: Any = None) -> Any:
    try:
        value = data.get(key, default)
        if pd.isna(value):
            return default
        return value
    except Exception:
        return default


# ================================================================
# Plotly Layout Defaults
# ================================================================

def _plotly_layout_defaults(fig, height: int = 400) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        font=dict(size=11),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        hoverlabel=dict(bgcolor="white"),
    )
    return fig


# ================================================================
# Chart Builders
# ================================================================

def build_cost_trend_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    """Line chart: cost trend over years, multi-product or aggregated."""
    if df.empty or "cost_year" not in df.columns:
        return None

    products = df["pt_code"].nunique() if "pt_code" in df.columns else 0
    C = LandedCostConstants

    if 1 < products <= C.MAX_MULTILINE_PRODUCTS:
        fig = px.line(
            df.sort_values("cost_year"),
            x="cost_year",
            y="average_landed_cost_usd",
            color="pt_code",
            markers=True,
            labels={
                "cost_year": "Year",
                "average_landed_cost_usd": "Avg Cost (USD)",
                "pt_code": "Product",
            },
            color_discrete_sequence=C.TREND_COLORS,
        )
    else:
        # Weighted average across products
        agg = (
            df.groupby("cost_year")
            .agg(total_value=("total_landed_value_usd", "sum"),
                 total_qty=("total_quantity", "sum"))
            .reset_index()
        )
        agg["weighted_avg"] = agg["total_value"] / agg["total_qty"].replace(0, pd.NA)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=agg["cost_year"], y=agg["weighted_avg"],
            mode="lines+markers+text",
            text=[format_usd4(v) for v in agg["weighted_avg"]],
            textposition="top center",
            marker=dict(size=8, color=C.COST_COLOR),
            line=dict(width=2, color=C.COST_COLOR),
            name="Weighted Avg Cost",
            hovertemplate="Year: %{x}<br>Cost: $%{y:.4f}<extra></extra>",
        ))

    fig = _plotly_layout_defaults(fig, height=380)
    fig.update_xaxes(dtick=1, title_text="Year")
    fig.update_yaxes(title_text="USD")
    return fig


def build_cost_distribution_chart(
    df: pd.DataFrame, year: Optional[int] = None
) -> Optional[go.Figure]:
    """Box plot: cost distribution by brand."""
    data = df[df["cost_year"] == year] if year else df
    if data.empty or "brand" not in data.columns:
        return None

    top_brands = data.groupby("brand")["total_landed_value_usd"].sum().nlargest(12).index
    data = data[data["brand"].isin(top_brands)]

    fig = px.box(
        data, x="brand", y="average_landed_cost_usd",
        labels={"brand": "Brand", "average_landed_cost_usd": "Avg Cost (USD)"},
        color_discrete_sequence=[LandedCostConstants.COST_COLOR],
    )
    fig = _plotly_layout_defaults(fig, height=380)
    fig.update_xaxes(title_text="")
    return fig


def build_source_breakdown_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    """Pie chart: Arrival vs Opening Balance quantities."""
    if df.empty:
        return None

    arr = df["arrival_quantity"].sum() if "arrival_quantity" in df.columns else 0
    ob = df["opening_balance_quantity"].sum() if "opening_balance_quantity" in df.columns else 0
    total = arr + ob
    if total == 0:
        return None

    fig = go.Figure(data=[go.Pie(
        labels=["Arrivals", "Opening Balance"],
        values=[arr, ob],
        marker=dict(colors=[LandedCostConstants.ARRIVAL_COLOR,
                            LandedCostConstants.OB_COLOR]),
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:,.0f}<br>(%{percent})<extra></extra>",
        hole=0.4,
    )])
    fig = _plotly_layout_defaults(fig, height=380)
    fig.update_layout(showlegend=True)
    return fig


def build_yoy_comparison_table(yoy_df: pd.DataFrame) -> pd.DataFrame:
    """Build comparison table between 2 most recent years."""
    if yoy_df.empty or yoy_df["cost_year"].nunique() < 2:
        return pd.DataFrame()

    years = sorted(yoy_df["cost_year"].unique(), reverse=True)
    curr, prev = years[0], years[1]

    curr_data = yoy_df[yoy_df["cost_year"] == curr][
        ["pt_code", "product_pn", "brand", "legal_entity",
         "average_landed_cost_usd", "total_quantity"]
    ].copy()
    prev_data = yoy_df[yoy_df["cost_year"] == prev][
        ["pt_code", "legal_entity", "average_landed_cost_usd", "total_quantity"]
    ].copy()

    curr_data.rename(columns={
        "average_landed_cost_usd": f"cost_{curr}",
        "total_quantity": f"qty_{curr}",
    }, inplace=True)
    prev_data.rename(columns={
        "average_landed_cost_usd": f"cost_{prev}",
        "total_quantity": f"qty_{prev}",
    }, inplace=True)

    merged = curr_data.merge(prev_data, on=["pt_code", "legal_entity"], how="outer")
    merged["yoy_change_usd"] = merged[f"cost_{curr}"] - merged[f"cost_{prev}"]
    merged["yoy_change_pct"] = (
        merged["yoy_change_usd"] / merged[f"cost_{prev}"].replace(0, pd.NA) * 100
    )

    return merged.sort_values("yoy_change_pct", ascending=False, na_position="last")


# ================================================================
# Heatmap Builders
# ================================================================

def build_brand_year_heatmap(df: pd.DataFrame) -> Optional[go.Figure]:
    """Heatmap: Brand × Year weighted average cost."""
    if df.empty or df["brand"].nunique() < 2 or df["cost_year"].nunique() < 2:
        return None

    top = df.groupby("brand")["total_landed_value_usd"].sum().nlargest(
        LandedCostConstants.HEATMAP_TOP_N).index
    heat_df = df[df["brand"].isin(top)].copy()

    pivot = heat_df.pivot_table(
        values="total_landed_value_usd", index="brand",
        columns="cost_year", aggfunc="sum", fill_value=0,
    )
    qty_pivot = heat_df.pivot_table(
        values="total_quantity", index="brand",
        columns="cost_year", aggfunc="sum", fill_value=0,
    )
    avg_pivot = (pivot / qty_pivot.replace(0, pd.NA)).round(4)

    avg_pivot = avg_pivot.sort_index()

    fig = go.Figure(data=go.Heatmap(
        z=avg_pivot.values,
        x=[str(c) for c in avg_pivot.columns],
        y=avg_pivot.index.tolist(),
        colorscale="YlOrRd",
        text=[[format_usd4(v) if pd.notna(v) else "" for v in row]
              for row in avg_pivot.values],
        texttemplate="%{text}",
        textfont=dict(size=10),
        hovertemplate="Brand: %{y}<br>Year: %{x}<br>Avg Cost: $%{z:.4f}<extra></extra>",
        colorbar=dict(title="USD"),
    ))
    h = max(400, len(avg_pivot) * 32 + 80)
    fig = _plotly_layout_defaults(fig, height=h)
    fig.update_layout(xaxis_title="Cost Year", yaxis_title="", showlegend=False)
    return fig


def build_entity_year_heatmap(df: pd.DataFrame) -> Optional[go.Figure]:
    """Heatmap: Entity × Year total value."""
    if df.empty or df["legal_entity"].nunique() < 2 or df["cost_year"].nunique() < 2:
        return None

    pivot = df.pivot_table(
        values="total_landed_value_usd", index="legal_entity",
        columns="cost_year", aggfunc="sum", fill_value=0,
    )
    pivot = pivot.sort_index()

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[str(c) for c in pivot.columns],
        y=pivot.index.tolist(),
        colorscale="Blues",
        text=[[format_usd(v) if v > 0 else "" for v in row] for row in pivot.values],
        texttemplate="%{text}",
        textfont=dict(size=10),
        hovertemplate="Entity: %{y}<br>Year: %{x}<br>Value: $%{z:,.2f}<extra></extra>",
        colorbar=dict(title="USD"),
    ))
    h = max(300, len(pivot) * 40 + 80)
    fig = _plotly_layout_defaults(fig, height=h)
    fig.update_layout(xaxis_title="Cost Year", yaxis_title="", showlegend=False)
    return fig


# ================================================================
# Excel Export
# ================================================================

def create_excel_download(df: pd.DataFrame) -> bytes:
    """Create formatted Excel file from export DataFrame."""
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Landed Cost", startrow=2)
        ws = writer.sheets["Landed Cost"]
        ncols = len(df.columns)

        # Title
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
        title_cell = ws.cell(row=1, column=1, value="LANDED COST REPORT")
        title_cell.font = Font(bold=True, size=13)
        title_cell.alignment = Alignment(horizontal="center")

        # Header styling
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=10)
        for col_idx in range(1, ncols + 1):
            cell = ws.cell(row=3, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        # Auto width
        for idx, col in enumerate(df.columns):
            max_len = max(
                df[col].astype(str).map(len).max() if len(df) > 0 else 0,
                len(str(col)),
            ) + 2
            ws.column_dimensions[get_column_letter(idx + 1)].width = min(max_len, 45)

    return output.getvalue()