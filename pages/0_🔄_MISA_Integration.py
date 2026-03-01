# pages/11_🔄_MISA_Integration.py
"""
MISA AMIS Kế Toán - API Integration
======================================
Page trong FA Data Hub để kết nối với MISA AMIS API:
- Tồn kho (Inventory Balance)
- Danh mục (Đối tượng, Vật tư, Kho, Đơn vị tính, Tài khoản)
- Công nợ phải thu / phải trả
- Thông tin công ty

Yêu cầu: app_id từ MISA, access_code từ AMIS Kế toán
"""

import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

from utils.auth import AuthManager

# Load environment variables
load_dotenv()

# ==================== AUTH CHECK ====================

auth = AuthManager()

if not auth.check_session():
    st.warning("⚠️ Vui lòng đăng nhập để sử dụng chức năng này.")
    st.switch_page("app.py")
    st.stop()

# ==================== SIDEBAR (user info + logout) ====================

with st.sidebar:
    st.markdown(f"### 👤 {auth.get_user_display_name()}")
    access_level = st.session_state.get('user_role', 'viewer')
    st.caption(f"Role: {access_level}")
    st.markdown("---")
    if st.button("🚪 Logout", use_container_width=True, key="misa_logout"):
        auth.logout()
        st.rerun()

# ==================== CONFIGURATION ====================

BASE_URL = "https://actapp.misa.vn"

API_ENDPOINTS = {
    "connect": "/api/oauth/actopen/connect",
    "get_dictionary": "/apir/sync/actopen/get_dictionary",
    "get_inventory_balance": "/apir/sync/actopen/get_list_inventory_balance",
    "get_debt": "/apir/sync/actopen/get_list_acc_obj_debt",
    "get_company_info": "/apir/sync/actopen/get_company_info",
    "get_system_option": "/apir/sync/actopen/get_option",
}

DICTIONARY_TYPES = {
    "Khách hàng": 1,
    "Nhà cung cấp": 2,
    "Vật tư hàng hóa": 3,
    "Kho": 4,
    "Đơn vị tính": 5,
    "Hệ thống tài khoản": 6,
    "Cơ cấu tổ chức": 7,
    "Tài khoản ngân hàng": 8,
}

COLORS = px.colors.qualitative.Set2
CHART_TEMPLATE = "plotly_white"

# ==================== STYLING ====================

st.markdown("""
<style>
.metric-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 20px 24px;
    border-radius: 12px;
    color: white;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    margin-bottom: 10px;
}
.metric-card.green {
    background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
}
.metric-card.blue {
    background: linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%);
}
.metric-card.orange {
    background: linear-gradient(135deg, #f2994a 0%, #f2c94c 100%);
}
.metric-card.red {
    background: linear-gradient(135deg, #e44d26 0%, #f09819 100%);
}
.metric-card.purple {
    background: linear-gradient(135deg, #8e2de2 0%, #4a00e0 100%);
}
.metric-card.teal {
    background: linear-gradient(135deg, #0f9b8e 0%, #2dd4bf 100%);
}
.metric-card .metric-label {
    font-size: 13px;
    font-weight: 500;
    opacity: 0.9;
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.metric-card .metric-value {
    font-size: 28px;
    font-weight: 700;
    line-height: 1.2;
}
.metric-card .metric-sub {
    font-size: 12px;
    opacity: 0.8;
    margin-top: 6px;
}
</style>
""", unsafe_allow_html=True)


# ==================== HELPER FUNCTIONS ====================

def metric_card(label: str, value: str, sub: str = "", color: str = ""):
    """Render a styled metric card"""
    cls = f"metric-card {color}" if color else "metric-card"
    sub_html = f'<div class="metric-sub">{sub}</div>' if sub else ""
    st.markdown(f"""
    <div class="{cls}">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def format_vnd(amount):
    """Format number as VND"""
    if pd.isna(amount) or amount == 0:
        return "0 ₫"
    if abs(amount) >= 1_000_000_000:
        return f"{amount/1_000_000_000:,.1f} tỷ ₫"
    elif abs(amount) >= 1_000_000:
        return f"{amount/1_000_000:,.1f} triệu ₫"
    else:
        return f"{amount:,.0f} ₫"


def parse_api_data(result: dict) -> list:
    """Parse API response data into list of dicts"""
    if not result.get("Success"):
        return []
    data = result.get("Data", "[]")
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return []
    elif isinstance(data, list):
        return data
    return []


# ==================== MISA AMIS API CLIENT ====================

class MisaAmisAPI:
    """MISA AMIS API Client"""

    def __init__(self, app_id: str, access_code: str, org_company_code: str):
        self.app_id = app_id
        self.access_code = access_code
        self.org_company_code = org_company_code
        self.access_token = None
        self.token_expiry = None

    def connect(self) -> dict:
        """Kết nối và lấy access_token"""
        url = f"{BASE_URL}{API_ENDPOINTS['connect']}"
        payload = {
            "app_id": self.app_id,
            "access_code": self.access_code,
            "org_company_code": self.org_company_code
        }
        try:
            response = requests.post(url, json=payload, timeout=30)
            result = response.json()
            if result.get("Success"):
                data = result.get("Data", "")
                if isinstance(data, str):
                    try:
                        token_data = json.loads(data)
                        self.access_token = token_data.get("access_token")
                        self.token_expiry = datetime.now() + timedelta(hours=12)
                    except json.JSONDecodeError:
                        self.access_token = data
                        self.token_expiry = datetime.now() + timedelta(hours=12)
                return result
            else:
                return result
        except requests.exceptions.RequestException as e:
            return {"Success": False, "ErrorMessage": str(e)}

    def _get_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "X-MISA-AccessToken": self.access_token or ""
        }

    def _check_token(self) -> bool:
        if not self.access_token:
            return False
        if self.token_expiry and datetime.now() > self.token_expiry:
            return False
        return True

    def get_dictionary(self, data_type: int, skip: int = 0, take: int = 100,
                       last_sync_time: str = None) -> dict:
        url = f"{BASE_URL}{API_ENDPOINTS['get_dictionary']}"
        payload = {
            "app_id": self.app_id,
            "data_type": data_type,
            "skip": skip,
            "take": take,
            "last_sync_time": last_sync_time
        }
        try:
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=60)
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"Success": False, "ErrorMessage": str(e)}

    def get_inventory_balance(self, branch_id: str = None, skip: int = 0,
                               take: int = 100, last_sync_time: str = None) -> dict:
        url = f"{BASE_URL}{API_ENDPOINTS['get_inventory_balance']}"
        payload = {
            "app_id": self.app_id,
            "org_company_code": self.org_company_code,
            "branch_id": branch_id,
            "skip": str(skip),
            "take": str(take),
            "last_sync_time": last_sync_time
        }
        try:
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=60)
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"Success": False, "ErrorMessage": str(e)}

    def get_debt(self, data_type: int = 0, skip: int = 0, take: int = 100,
                 last_sync_time: str = None, branch_id: str = None) -> dict:
        url = f"{BASE_URL}{API_ENDPOINTS['get_debt']}"
        payload = {
            "app_id": self.app_id,
            "org_company_code": self.org_company_code,
            "data_type": str(data_type),
            "skip": str(skip),
            "take": str(take),
            "branch_id": branch_id,
            "last_sync_time": last_sync_time,
        }
        try:
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=60)
            if not response.text or response.text.strip() == "":
                return {
                    "Success": False,
                    "ErrorMessage": f"API trả về response rỗng. Status: {response.status_code}",
                    "_debug": {"status_code": response.status_code, "headers": dict(response.headers)}
                }
            try:
                return response.json()
            except json.JSONDecodeError:
                return {
                    "Success": False,
                    "ErrorMessage": f"Response không phải JSON. Status: {response.status_code}",
                    "_debug": {"status_code": response.status_code, "raw_text": response.text[:500]}
                }
        except requests.exceptions.RequestException as e:
            return {"Success": False, "ErrorMessage": str(e)}

    def get_company_info(self) -> dict:
        url = f"{BASE_URL}{API_ENDPOINTS['get_company_info']}"
        payload = {"app_id": self.app_id}
        try:
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"Success": False, "ErrorMessage": str(e)}

    def get_all_inventory(self, branch_id: str = None, batch_size: int = 100) -> list:
        all_items = []
        skip = 0
        while True:
            result = self.get_inventory_balance(branch_id=branch_id, skip=skip, take=batch_size)
            if not result.get("Success"):
                break
            data = result.get("Data", "[]")
            if isinstance(data, str):
                try:
                    items = json.loads(data)
                except json.JSONDecodeError:
                    break
            elif isinstance(data, list):
                items = data
            else:
                break
            if not items:
                break
            all_items.extend(items)
            if len(items) < batch_size:
                break
            skip += batch_size
        return all_items

    def get_all_dictionary(self, data_type: int, batch_size: int = 100) -> list:
        all_items = []
        skip = 0
        while True:
            result = self.get_dictionary(data_type=data_type, skip=skip, take=batch_size)
            if not result.get("Success"):
                break
            data = result.get("Data", "[]")
            if isinstance(data, str):
                try:
                    items = json.loads(data)
                except json.JSONDecodeError:
                    break
            elif isinstance(data, list):
                items = data
            else:
                break
            if not items:
                break
            all_items.extend(items)
            if len(items) < batch_size:
                break
            skip += batch_size
        return all_items


# ==================== VISUALIZATION FUNCTIONS ====================

def render_inventory_analytics(df_display: pd.DataFrame):
    """Render charts for Inventory tab"""
    st.divider()
    st.subheader("📊 Phân tích tồn kho")

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        if "Tên kho" in df_display.columns and "Giá trị tồn" in df_display.columns:
            wh_summary = df_display.groupby("Tên kho")["Giá trị tồn"].sum().reset_index()
            wh_summary = wh_summary.sort_values("Giá trị tồn", ascending=False)
            fig_pie = px.pie(
                wh_summary, values="Giá trị tồn", names="Tên kho",
                title="Phân bổ giá trị tồn kho theo kho",
                color_discrete_sequence=COLORS, hole=0.4,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(
                template=CHART_TEMPLATE, height=400,
                showlegend=False, margin=dict(t=40, b=20, l=20, r=20)
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with chart_col2:
        if "Tên kho" in df_display.columns and "Mã vật tư" in df_display.columns:
            wh_count = df_display.groupby("Tên kho").agg(
                SKU=("Mã vật tư", "nunique"),
                SL=("SL tồn", "sum") if "SL tồn" in df_display.columns else ("Mã vật tư", "count")
            ).reset_index().sort_values("SKU", ascending=True)
            fig_bar = px.bar(
                wh_count, x="SKU", y="Tên kho", orientation="h",
                title="Số lượng SKU theo kho",
                color="SKU", color_continuous_scale="Teal", text="SKU",
            )
            fig_bar.update_traces(textposition="outside")
            fig_bar.update_layout(
                template=CHART_TEMPLATE, height=400, showlegend=False,
                coloraxis_showscale=False, margin=dict(t=40, b=20, l=20, r=20),
                xaxis_title="Số SKU", yaxis_title="",
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    chart_col3, chart_col4 = st.columns(2)

    with chart_col3:
        if "Tên vật tư" in df_display.columns and "Giá trị tồn" in df_display.columns:
            top_items = df_display.nlargest(15, "Giá trị tồn")[["Tên vật tư", "Giá trị tồn", "SL tồn"]].copy()
            top_items["Tên vật tư (ngắn)"] = top_items["Tên vật tư"].str[:40]
            fig_top = px.bar(
                top_items, x="Giá trị tồn", y="Tên vật tư (ngắn)", orientation="h",
                title="Top 15 vật tư có giá trị tồn cao nhất",
                color="Giá trị tồn", color_continuous_scale="Oryel",
                text=top_items["Giá trị tồn"].apply(lambda x: format_vnd(x)),
            )
            fig_top.update_traces(textposition="outside")
            fig_top.update_layout(
                template=CHART_TEMPLATE, height=500, showlegend=False,
                coloraxis_showscale=False, margin=dict(t=40, b=20, l=20, r=20),
                xaxis_title="Giá trị tồn (VNĐ)", yaxis_title="",
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig_top, use_container_width=True)

    with chart_col4:
        if "Tên vật tư" in df_display.columns and "SL tồn" in df_display.columns:
            top_qty = df_display.nlargest(15, "SL tồn")[["Tên vật tư", "SL tồn"]].copy()
            top_qty["Tên vật tư (ngắn)"] = top_qty["Tên vật tư"].str[:40]
            fig_qty = px.bar(
                top_qty, x="SL tồn", y="Tên vật tư (ngắn)", orientation="h",
                title="Top 15 vật tư có số lượng tồn cao nhất",
                color="SL tồn", color_continuous_scale="Emrld",
                text=top_qty["SL tồn"].apply(lambda x: f"{x:,.0f}"),
            )
            fig_qty.update_traces(textposition="outside")
            fig_qty.update_layout(
                template=CHART_TEMPLATE, height=500, showlegend=False,
                coloraxis_showscale=False, margin=dict(t=40, b=20, l=20, r=20),
                xaxis_title="Số lượng tồn", yaxis_title="",
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig_qty, use_container_width=True)

    if "Tên kho" in df_display.columns and "SL tồn" in df_display.columns:
        st.divider()
        st.subheader("📋 Tổng hợp theo kho")
        summary = df_display.groupby("Tên kho").agg(
            **{"Số mặt hàng": ("Mã vật tư", "count"),
               "Tổng SL": ("SL tồn", "sum"),
               "Tổng giá trị": ("Giá trị tồn", "sum")}
        ).reset_index().sort_values("Tổng giá trị", ascending=False)
        summary["Tổng giá trị (format)"] = summary["Tổng giá trị"].apply(lambda x: f"{x:,.0f} ₫")
        summary["Tỷ trọng"] = (summary["Tổng giá trị"] / summary["Tổng giá trị"].sum() * 100).apply(lambda x: f"{x:.1f}%")
        st.dataframe(
            summary[["Tên kho", "Số mặt hàng", "Tổng SL", "Tổng giá trị (format)", "Tỷ trọng"]],
            use_container_width=True, hide_index=True,
        )


def render_debt_analytics(df: pd.DataFrame, debt_label: str):
    """Render charts for Debt tab"""
    st.divider()
    st.subheader(f"📊 Phân tích {debt_label}")

    debt_col = None
    invoice_col = None
    name_col = None
    for c in df.columns:
        cl = c.lower()
        if "debt_amount" in cl and "invoice" not in cl:
            debt_col = c
        if "invoice_debt_amount" in cl:
            invoice_col = c
        if "account_object_name" in cl:
            name_col = c

    amount_col = invoice_col or debt_col
    if not amount_col or not name_col:
        st.info("Không đủ dữ liệu để tạo biểu đồ phân tích.")
        return

    df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce").fillna(0)
    if debt_col and debt_col != amount_col:
        df[debt_col] = pd.to_numeric(df[debt_col], errors="coerce").fillna(0)

    df_nonzero = df[df[amount_col] > 0].copy()
    if df_nonzero.empty:
        st.info("Tất cả đối tượng đều có công nợ = 0.")
        return

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        top_debt = df_nonzero.nlargest(15, amount_col)[[name_col, amount_col]].copy()
        top_debt["Tên (ngắn)"] = top_debt[name_col].str[:45]
        fig_bar = px.bar(
            top_debt, x=amount_col, y="Tên (ngắn)", orientation="h",
            title=f"Top 15 {debt_label} lớn nhất",
            color=amount_col, color_continuous_scale="OrRd",
            text=top_debt[amount_col].apply(lambda x: format_vnd(x)),
        )
        fig_bar.update_traces(textposition="outside")
        fig_bar.update_layout(
            template=CHART_TEMPLATE, height=500, showlegend=False,
            coloraxis_showscale=False, margin=dict(t=40, b=20, l=20, r=20),
            xaxis_title="Số tiền (VNĐ)", yaxis_title="",
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with chart_col2:
        top10 = df_nonzero.nlargest(10, amount_col)[[name_col, amount_col]].copy()
        others_sum = df_nonzero[~df_nonzero.index.isin(top10.index)][amount_col].sum()
        if others_sum > 0:
            others_row = pd.DataFrame([{name_col: "Còn lại", amount_col: others_sum}])
            pie_data = pd.concat([top10, others_row], ignore_index=True)
        else:
            pie_data = top10
        pie_data["Tên (ngắn)"] = pie_data[name_col].str[:30]
        fig_pie = px.pie(
            pie_data, values=amount_col, names="Tên (ngắn)",
            title=f"Phân bổ {debt_label} (Top 10 + còn lại)",
            color_discrete_sequence=COLORS, hole=0.4,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(
            template=CHART_TEMPLATE, height=500,
            showlegend=False, margin=dict(t=40, b=20, l=20, r=20)
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("#### 📏 Phân bổ theo mức công nợ")
    bins = [0, 1_000_000, 10_000_000, 50_000_000, 100_000_000, 500_000_000, 1_000_000_000, float("inf")]
    labels = ["< 1tr", "1-10tr", "10-50tr", "50-100tr", "100-500tr", "500tr-1tỷ", "> 1 tỷ"]
    df_nonzero["Mức nợ"] = pd.cut(df_nonzero[amount_col], bins=bins, labels=labels, right=False)
    range_dist = df_nonzero["Mức nợ"].value_counts().reset_index()
    range_dist.columns = ["Mức nợ", "Số đối tượng"]
    range_dist["Mức nợ"] = pd.Categorical(range_dist["Mức nợ"], categories=labels, ordered=True)
    range_dist = range_dist.sort_values("Mức nợ")
    fig_hist = px.bar(
        range_dist, x="Mức nợ", y="Số đối tượng",
        title="Phân bổ số đối tượng theo mức công nợ",
        color="Số đối tượng", color_continuous_scale="Teal", text="Số đối tượng",
    )
    fig_hist.update_traces(textposition="outside")
    fig_hist.update_layout(
        template=CHART_TEMPLATE, height=350, showlegend=False,
        coloraxis_showscale=False, margin=dict(t=40, b=20, l=20, r=20),
    )
    st.plotly_chart(fig_hist, use_container_width=True)


def render_dictionary_analytics(df: pd.DataFrame, dict_type_name: str):
    """Render analytics for Dictionary tab"""
    st.divider()
    st.subheader(f"📊 Phân tích danh mục: {dict_type_name}")

    if dict_type_name in ("Khách hàng", "Nhà cung cấp"):
        _render_object_analytics(df, dict_type_name)
    elif dict_type_name == "Vật tư hàng hóa":
        _render_inventory_item_analytics(df)
    elif dict_type_name == "Hệ thống tài khoản":
        _render_account_analytics(df)
    elif dict_type_name == "Kho":
        _render_stock_analytics(df)
    else:
        _render_generic_analytics(df, dict_type_name)


def _render_object_analytics(df: pd.DataFrame, label: str):
    """Analytics for Khách hàng / NCC"""
    group_col = None
    for c in df.columns:
        cl = c.lower()
        if "category" in cl or "group" in cl or "loai" in cl or "nhom" in cl:
            group_col = c
            break

    col1, col2 = st.columns(2)

    with col1:
        if group_col and df[group_col].nunique() > 1 and df[group_col].nunique() < 50:
            grp = df[group_col].fillna("Không phân loại").value_counts().reset_index()
            grp.columns = [group_col, "Số lượng"]
            fig = px.pie(
                grp, values="Số lượng", names=group_col,
                title=f"Phân loại {label}",
                color_discrete_sequence=COLORS, hole=0.4,
            )
            fig.update_layout(template=CHART_TEMPLATE, height=400, margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            for c in df.columns:
                if "inactive" in c.lower() or "is_active" in c.lower():
                    active_counts = df[c].value_counts().reset_index()
                    active_counts.columns = ["Trạng thái", "Số lượng"]
                    active_counts["Trạng thái"] = active_counts["Trạng thái"].map(
                        {True: "Ngưng hoạt động", False: "Đang hoạt động", 1: "Ngưng hoạt động", 0: "Đang hoạt động"}
                    ).fillna(active_counts["Trạng thái"].astype(str))
                    fig = px.pie(
                        active_counts, values="Số lượng", names="Trạng thái",
                        title=f"Trạng thái {label}",
                        color_discrete_sequence=["#38ef7d", "#e44d26"], hole=0.4,
                    )
                    fig.update_layout(template=CHART_TEMPLATE, height=400, margin=dict(t=40, b=20))
                    st.plotly_chart(fig, use_container_width=True)
                    break

    with col2:
        completeness = ((df.notna() & (df != "")).sum() / len(df) * 100).sort_values()
        comp_df = completeness.reset_index()
        comp_df.columns = ["Trường", "% Có dữ liệu"]
        fig = px.bar(
            comp_df.tail(20), x="% Có dữ liệu", y="Trường", orientation="h",
            title="Mức độ đầy đủ dữ liệu (top 20 trường)",
            color="% Có dữ liệu", color_continuous_scale="RdYlGn",
            text=comp_df.tail(20)["% Có dữ liệu"].apply(lambda x: f"{x:.0f}%"),
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            template=CHART_TEMPLATE, height=400, showlegend=False,
            coloraxis_showscale=False, margin=dict(t=40, b=20, l=20, r=20),
        )
        st.plotly_chart(fig, use_container_width=True)


def _render_inventory_item_analytics(df: pd.DataFrame):
    """Analytics for Vật tư hàng hóa"""
    col1, col2 = st.columns(2)

    with col1:
        cat_col = None
        for c in df.columns:
            cl = c.lower()
            if "category" in cl or "inventory_category" in cl or "nhom" in cl or "group" in cl:
                cat_col = c
                break
        if cat_col and df[cat_col].nunique() > 1:
            grp = df[cat_col].fillna("Chưa phân loại").value_counts().head(15).reset_index()
            grp.columns = [cat_col, "Số lượng"]
            fig = px.bar(
                grp, x="Số lượng", y=cat_col, orientation="h",
                title="Phân loại vật tư hàng hóa",
                color="Số lượng", color_continuous_scale="Teal", text="Số lượng",
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(
                template=CHART_TEMPLATE, height=400, showlegend=False,
                coloraxis_showscale=False, margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        unit_col = None
        for c in df.columns:
            if "unit" in c.lower() and "name" in c.lower():
                unit_col = c
                break
        if unit_col and df[unit_col].nunique() > 1:
            unit_dist = df[unit_col].fillna("N/A").value_counts().head(10).reset_index()
            unit_dist.columns = [unit_col, "Số lượng"]
            fig = px.pie(
                unit_dist, values="Số lượng", names=unit_col,
                title="Phân bổ theo đơn vị tính",
                color_discrete_sequence=COLORS, hole=0.4,
            )
            fig.update_layout(template=CHART_TEMPLATE, height=400, margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)


def _render_account_analytics(df: pd.DataFrame):
    """Analytics for Hệ thống tài khoản"""
    grade_col = None
    for c in df.columns:
        cl = c.lower()
        if "grade" in cl or "level" in cl or "cap" in cl or "bac" in cl:
            grade_col = c
            break

    col1, col2 = st.columns(2)
    with col1:
        if grade_col:
            grp = df[grade_col].value_counts().sort_index().reset_index()
            grp.columns = [grade_col, "Số tài khoản"]
            fig = px.bar(
                grp, x=grade_col, y="Số tài khoản",
                title="Số tài khoản theo cấp",
                color="Số tài khoản", color_continuous_scale="Blues", text="Số tài khoản",
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(
                template=CHART_TEMPLATE, height=400, showlegend=False,
                coloraxis_showscale=False, margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        acct_col = None
        for c in df.columns:
            cl = c.lower()
            if "account_number" in cl or "so_tai_khoan" in cl:
                acct_col = c
                break
        if acct_col:
            df_temp = df.copy()
            df_temp["Nhóm TK"] = df_temp[acct_col].astype(str).str[:1]
            acct_grp = df_temp["Nhóm TK"].value_counts().sort_index().reset_index()
            acct_grp.columns = ["Nhóm TK", "Số lượng"]
            tk_labels = {
                "1": "1xx - Tài sản", "2": "2xx - Tài sản", "3": "3xx - Nợ phải trả",
                "4": "4xx - Vốn CSH", "5": "5xx - Doanh thu", "6": "6xx - Chi phí",
                "7": "7xx - Thu nhập khác", "8": "8xx - Chi phí khác", "9": "9xx - XĐ KQKD",
                "0": "0xx - Ngoài bảng"
            }
            acct_grp["Mô tả"] = acct_grp["Nhóm TK"].map(tk_labels).fillna(acct_grp["Nhóm TK"])
            fig = px.bar(
                acct_grp, x="Mô tả", y="Số lượng",
                title="Phân bổ theo nhóm tài khoản",
                color="Số lượng", color_continuous_scale="Sunset", text="Số lượng",
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(
                template=CHART_TEMPLATE, height=400, showlegend=False,
                coloraxis_showscale=False, margin=dict(t=40, b=20),
                xaxis_tickangle=-45,
            )
            st.plotly_chart(fig, use_container_width=True)


def _render_stock_analytics(df: pd.DataFrame):
    """Analytics for Kho"""
    st.info(f"Hệ thống có **{len(df)}** kho được thiết lập.")
    for c in df.columns:
        if "inactive" in c.lower():
            counts = df[c].value_counts().reset_index()
            counts.columns = ["Trạng thái", "Số kho"]
            counts["Trạng thái"] = counts["Trạng thái"].map(
                {True: "Ngưng sử dụng", False: "Đang hoạt động", 1: "Ngưng sử dụng", 0: "Đang hoạt động"}
            ).fillna(counts["Trạng thái"].astype(str))
            fig = px.pie(
                counts, values="Số kho", names="Trạng thái",
                title="Trạng thái kho",
                color_discrete_sequence=["#38ef7d", "#e44d26"], hole=0.4,
            )
            fig.update_layout(template=CHART_TEMPLATE, height=350, margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
            break


def _render_generic_analytics(df: pd.DataFrame, label: str):
    """Generic analytics for any dictionary type"""
    st.info(f"Danh mục **{label}** có **{len(df)}** bản ghi, **{len(df.columns)}** trường dữ liệu.")
    completeness = ((df.notna() & (df != "")).sum() / len(df) * 100).sort_values()
    comp_df = completeness.reset_index()
    comp_df.columns = ["Trường", "% Có dữ liệu"]
    fig = px.bar(
        comp_df.tail(15), x="% Có dữ liệu", y="Trường", orientation="h",
        title="Mức độ đầy đủ dữ liệu",
        color="% Có dữ liệu", color_continuous_scale="RdYlGn",
        text=comp_df.tail(15)["% Có dữ liệu"].apply(lambda x: f"{x:.0f}%"),
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        template=CHART_TEMPLATE, height=400, showlegend=False,
        coloraxis_showscale=False, margin=dict(t=40, b=20, l=20, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)


# ==================== MAIN PAGE CONTENT ====================

st.title("🔄 MISA AMIS Kế Toán - API Integration")
st.caption("Kết nối API lấy dữ liệu từ MISA AMIS Kế toán")

# ---- Sidebar: MISA Connection Settings ----
with st.sidebar:
    st.markdown("---")
    st.header("🔐 Kết nối MISA AMIS")

    env_app_id = os.getenv("MISA_APP_ID", "")
    env_access_code = os.getenv("MISA_ACCESS_CODE", "")
    env_org_code = os.getenv("MISA_ORG_COMPANY_CODE", "prostech")

    app_id = st.text_input(
        "App ID",
        value=st.session_state.get("misa_app_id", env_app_id),
        type="password",
        help="Mã ứng dụng do MISA cấp"
    )
    access_code = st.text_input(
        "Access Code (Mã kết nối)",
        value=st.session_state.get("misa_access_code", env_access_code),
        type="password",
        help="Lấy từ AMIS Kế toán > Thiết lập > Kết nối ứng dụng > API kết nối"
    )
    org_company_code = st.text_input(
        "Org Company Code",
        value=st.session_state.get("misa_org_company_code", env_org_code),
        help="Mã định danh công ty/đối tác của bạn"
    )

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        btn_connect = st.button("🔗 Kết nối", use_container_width=True, key="misa_connect_btn")
    with col_c2:
        btn_disconnect = st.button("🔌 Ngắt", use_container_width=True, key="misa_disconnect_btn")

    if btn_disconnect:
        for key in ["misa_api_client", "misa_access_token", "misa_connected"]:
            st.session_state.pop(key, None)
        st.success("Đã ngắt kết nối")
        st.rerun()

    auto_connect = (
        not st.session_state.get("misa_connected")
        and env_app_id
        and env_access_code
        and not st.session_state.get("misa_auto_connect_tried")
    )

    if btn_connect or auto_connect:
        if auto_connect:
            st.session_state["misa_auto_connect_tried"] = True

        if not all([app_id, access_code, org_company_code]):
            st.error("Vui lòng điền đầy đủ thông tin kết nối")
        else:
            with st.spinner("Đang kết nối MISA AMIS..."):
                client = MisaAmisAPI(app_id, access_code, org_company_code)
                result = client.connect()

                if result.get("Success"):
                    st.session_state["misa_api_client"] = client
                    st.session_state["misa_connected"] = True
                    st.session_state["misa_app_id"] = app_id
                    st.session_state["misa_access_code"] = access_code
                    st.session_state["misa_org_company_code"] = org_company_code
                    st.success("✅ Kết nối thành công!")
                    st.info(f"Token hết hạn: {client.token_expiry.strftime('%H:%M:%S %d/%m/%Y')}")
                else:
                    error_msg = result.get("ErrorMessage", "Lỗi không xác định")
                    error_code = result.get("ErrorCode", "")
                    st.error(f"❌ Kết nối thất bại!\n\nError: {error_code}\n{error_msg}")

    st.divider()
    if st.session_state.get("misa_connected"):
        st.success("🟢 MISA: Đã kết nối")
    else:
        st.warning("🔴 MISA: Chưa kết nối")


# ---- Main Content: Not Connected ----
if not st.session_state.get("misa_connected"):
    st.info("""
    ### 📋 Hướng dẫn sử dụng
    
    **Bước 1:** Liên hệ MISA để được cấp `App ID`
    
    **Bước 2:** Vào AMIS Kế toán → Thiết lập → Kết nối ứng dụng → API kết nối → Sao chép `Mã kết nối`
    
    **Bước 3:** Điền thông tin vào sidebar bên trái và nhấn **Kết nối**
    
    **Bước 4:** Chọn các tab bên dưới để lấy dữ liệu
    
    ---
    
    **Các API hỗ trợ:**
    - 📦 Tồn kho vật tư hàng hóa theo kho
    - 📋 Danh mục: Khách hàng, NCC, Vật tư, Kho, Tài khoản...
    - 💰 Công nợ phải thu / phải trả
    - 🏢 Thông tin công ty
    """)

    # Demo mode
    st.divider()
    st.subheader("🎯 Demo Mode (Dữ liệu mẫu)")

    demo_data = [
        {"inventory_item_code": "SP001", "inventory_item_name": "Robot AMRF7-1000",
         "stock_code": "KHO01", "stock_name": "Kho thành phẩm",
         "quantity_balance": 15, "amount_balance": 750000000, "unit_price": 50000000,
         "lot_no": "LOT2026-001", "expiry_date": None},
        {"inventory_item_code": "SP002", "inventory_item_name": "Cảm biến Hikrobot MV-CS060",
         "stock_code": "KHO02", "stock_name": "Kho linh kiện",
         "quantity_balance": 120, "amount_balance": 360000000, "unit_price": 3000000,
         "lot_no": "LOT2026-002", "expiry_date": "2027-06-15"},
        {"inventory_item_code": "SP003", "inventory_item_name": "Board mạch điều khiển PLC",
         "stock_code": "KHO02", "stock_name": "Kho linh kiện",
         "quantity_balance": 45, "amount_balance": 225000000, "unit_price": 5000000,
         "lot_no": "LOT2026-003", "expiry_date": None},
        {"inventory_item_code": "NL001", "inventory_item_name": "Keo dán công nghiệp Gluditec",
         "stock_code": "KHO03", "stock_name": "Kho nguyên liệu",
         "quantity_balance": 500, "amount_balance": 150000000, "unit_price": 300000,
         "lot_no": "LOT2026-004", "expiry_date": "2026-12-31"},
        {"inventory_item_code": "NL002", "inventory_item_name": "Silicon sealant",
         "stock_code": "KHO03", "stock_name": "Kho nguyên liệu",
         "quantity_balance": 200, "amount_balance": 100000000, "unit_price": 500000,
         "lot_no": "LOT2026-005", "expiry_date": "2027-03-15"},
    ]

    df_demo = pd.DataFrame(demo_data)
    df_demo.columns = [
        "Mã vật tư", "Tên vật tư", "Mã kho", "Tên kho",
        "SL tồn", "Giá trị tồn", "Đơn giá", "Số lô", "Hạn dùng"
    ]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Tổng SKU", str(len(df_demo)), "mặt hàng trong kho", "blue")
    with c2:
        metric_card("Tổng SL tồn", f"{df_demo['SL tồn'].sum():,.0f}", "đơn vị", "green")
    with c3:
        metric_card("Tổng giá trị", format_vnd(df_demo['Giá trị tồn'].sum()), "tổng giá trị tồn kho", "orange")
    with c4:
        metric_card("Số kho", str(df_demo['Mã kho'].nunique()), "kho lưu trữ", "purple")

    st.dataframe(df_demo, use_container_width=True, hide_index=True)
    render_inventory_analytics(df_demo)

    st.stop()


# ==================== CONNECTED: DATA TABS ====================

client: MisaAmisAPI = st.session_state["misa_api_client"]

tab1, tab2, tab3, tab4 = st.tabs([
    "📦 Tồn kho",
    "📋 Danh mục",
    "💰 Công nợ",
    "🏢 Thông tin công ty"
])

# ======================================================================
# Tab 1: Inventory Balance
# ======================================================================
with tab1:
    st.subheader("📦 Tồn kho vật tư hàng hóa")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        branch_id = st.text_input(
            "Branch ID (để trống = tất cả)", value="",
            help="ID chi nhánh, để trống để lấy tất cả", key="inv_branch"
        )
    with col2:
        last_sync = st.text_input(
            "Last Sync Time (optional)", value="",
            placeholder="2025-01-01",
            help="Lấy dữ liệu thay đổi từ thời điểm này", key="inv_sync"
        )
    with col3:
        batch_size = st.selectbox("Số bản ghi/lần", [50, 100, 200, 500], index=1, key="inv_batch")

    if st.button("🔍 Lấy dữ liệu tồn kho", type="primary", use_container_width=True, key="inv_fetch"):
        with st.spinner("Đang tải dữ liệu tồn kho..."):
            items = client.get_all_inventory(branch_id=branch_id or None, batch_size=batch_size)
            if items:
                st.session_state["misa_inventory_data"] = items
                st.success(f"✅ Đã lấy {len(items)} bản ghi tồn kho")
            else:
                result = client.get_inventory_balance(
                    branch_id=branch_id or None, skip=0, take=batch_size,
                    last_sync_time=last_sync or None
                )
                if not result.get("Success"):
                    st.error(f"❌ Lỗi: {result.get('ErrorMessage', 'Unknown')}")
                else:
                    st.warning("Không có dữ liệu tồn kho")

    if "misa_inventory_data" in st.session_state and st.session_state["misa_inventory_data"]:
        items = st.session_state["misa_inventory_data"]
        df = pd.DataFrame(items)

        column_map = {
            "inventory_item_code": "Mã vật tư",
            "inventory_item_name": "Tên vật tư",
            "stock_code": "Mã kho",
            "stock_name": "Tên kho",
            "organization_unit_code": "Mã chi nhánh",
            "organization_unit_name": "Chi nhánh",
            "quantity_balance": "SL tồn",
            "amount_balance": "Giá trị tồn",
            "unit_price": "Đơn giá",
            "lot_no": "Số lô",
            "expiry_date": "Hạn dùng",
        }

        display_cols = [c for c in column_map.keys() if c in df.columns]
        df_display = df[display_cols].rename(columns=column_map)

        for nc in ["SL tồn", "Giá trị tồn", "Đơn giá"]:
            if nc in df_display.columns:
                df_display[nc] = pd.to_numeric(df_display[nc], errors="coerce").fillna(0)

        total_value = df_display["Giá trị tồn"].sum() if "Giá trị tồn" in df_display.columns else 0
        total_qty = df_display["SL tồn"].sum() if "SL tồn" in df_display.columns else 0
        num_sku = df_display["Mã vật tư"].nunique() if "Mã vật tư" in df_display.columns else len(df_display)
        num_wh = df_display["Mã kho"].nunique() if "Mã kho" in df_display.columns else 0
        avg_price = total_value / total_qty if total_qty > 0 else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            metric_card("Tổng bản ghi", f"{len(df_display):,}", f"{num_sku} SKU duy nhất", "blue")
        with c2:
            metric_card("Tổng SL tồn", f"{total_qty:,.0f}", "đơn vị", "green")
        with c3:
            metric_card("Tổng giá trị", format_vnd(total_value), "giá trị tồn kho", "orange")
        with c4:
            metric_card("Đơn giá TB", format_vnd(avg_price), "trung bình / đơn vị", "purple")
        with c5:
            metric_card("Số kho", str(num_wh), "kho lưu trữ", "teal")

        st.divider()
        filter_col1, filter_col2 = st.columns(2)

        with filter_col1:
            if "Tên kho" in df_display.columns:
                warehouses = ["Tất cả"] + sorted(df_display["Tên kho"].dropna().unique().tolist())
                selected_wh = st.selectbox("Lọc theo kho", warehouses, key="inv_wh_filter")
                if selected_wh != "Tất cả":
                    df_display = df_display[df_display["Tên kho"] == selected_wh]

        with filter_col2:
            search_text = st.text_input("🔍 Tìm kiếm vật tư", "", key="inv_search")
            if search_text:
                mask = df_display.apply(lambda row: search_text.lower() in str(row).lower(), axis=1)
                df_display = df_display[mask]

        st.dataframe(df_display, use_container_width=True, height=500, hide_index=True)

        csv = df_display.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "📥 Tải xuống CSV", data=csv,
            file_name=f"ton_kho_amis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv", key="inv_download"
        )

        render_inventory_analytics(df_display)


# ======================================================================
# Tab 2: Dictionary
# ======================================================================
with tab2:
    st.subheader("📋 Danh mục")

    col1, col2 = st.columns([2, 1])
    with col1:
        dict_type_name = st.selectbox("Loại danh mục", list(DICTIONARY_TYPES.keys()), key="dict_type")
    with col2:
        dict_batch = st.selectbox("Số bản ghi/lần", [50, 100, 200], index=1, key="dict_batch")

    if st.button("🔍 Lấy danh mục", type="primary", use_container_width=True, key="dict_fetch"):
        data_type = DICTIONARY_TYPES[dict_type_name]
        with st.spinner(f"Đang tải danh mục {dict_type_name}..."):
            items = client.get_all_dictionary(data_type, batch_size=dict_batch)
            if items:
                st.session_state["misa_dict_data"] = items
                st.session_state["misa_dict_type_name"] = dict_type_name
                st.success(f"✅ Đã lấy {len(items)} bản ghi {dict_type_name}")
            else:
                result = client.get_dictionary(data_type, skip=0, take=dict_batch)
                if not result.get("Success"):
                    st.error(f"❌ Lỗi: {result.get('ErrorMessage', 'Unknown')}")
                else:
                    st.warning(f"Không có dữ liệu {dict_type_name}")

    if "misa_dict_data" in st.session_state and st.session_state["misa_dict_data"]:
        items = st.session_state["misa_dict_data"]
        df = pd.DataFrame(items)
        current_dict_name = st.session_state.get("misa_dict_type_name", "Danh mục")

        num_records = len(df)
        num_cols = len(df.columns)
        data_quality = (df.notna().sum().sum() / (num_records * num_cols) * 100) if num_records > 0 else 0

        c1, c2, c3 = st.columns(3)
        with c1:
            metric_card("Tổng bản ghi", f"{num_records:,}", f"danh mục {current_dict_name}", "blue")
        with c2:
            metric_card("Số trường dữ liệu", str(num_cols), "columns", "green")
        with c3:
            metric_card("Chất lượng dữ liệu", f"{data_quality:.1f}%", "tỷ lệ có dữ liệu", "orange")

        search = st.text_input("🔍 Tìm kiếm", "", key="dict_search")
        if search:
            mask = df.apply(lambda row: search.lower() in str(row).lower(), axis=1)
            df = df[mask]

        st.dataframe(df, use_container_width=True, height=500, hide_index=True)

        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "📥 Tải xuống CSV", data=csv,
            file_name=f"danhmuc_{current_dict_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv", key="dict_download"
        )

        render_dictionary_analytics(df, current_dict_name)


# ======================================================================
# Tab 3: Debt
# ======================================================================
with tab3:
    st.subheader("💰 Công nợ phải thu / phải trả")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        debt_type = st.selectbox(
            "Loại công nợ",
            ["Công nợ phải thu (data_type=0)", "Công nợ phải trả (data_type=1)"],
            key="debt_type_sel"
        )
        debt_data_type = 0 if "phải thu" in debt_type else 1
    with col2:
        debt_branch_id = st.text_input(
            "Branch ID (để trống = tất cả)", value="", key="debt_branch",
        )
    with col3:
        debt_take = st.selectbox("Số bản ghi/lần", [50, 100], index=1, key="debt_take")

    if st.button("🔍 Lấy dữ liệu công nợ", type="primary", use_container_width=True, key="debt_fetch"):
        with st.spinner("Đang tải dữ liệu công nợ..."):
            all_debt = []
            skip = 0
            while True:
                result = client.get_debt(
                    data_type=debt_data_type, skip=skip, take=debt_take,
                    branch_id=debt_branch_id or None
                )
                if not result.get("Success"):
                    error_msg = result.get("ErrorMessage", "Unknown error")
                    st.error(f"❌ Lỗi: {error_msg}")
                    debug = result.get("_debug", {})
                    if debug:
                        with st.expander("🔍 Debug info"):
                            st.json(debug)
                    break
                items = parse_api_data(result)
                if not items:
                    break
                all_debt.extend(items)
                if len(items) < debt_take:
                    break
                skip += debt_take

            if all_debt:
                st.session_state["misa_debt_data"] = all_debt
                st.session_state["misa_debt_type_label"] = "Công nợ phải thu" if debt_data_type == 0 else "Công nợ phải trả"
                st.success(f"✅ Đã lấy {len(all_debt)} bản ghi công nợ {'phải thu' if debt_data_type == 0 else 'phải trả'}")

    if "misa_debt_data" in st.session_state and st.session_state["misa_debt_data"]:
        df = pd.DataFrame(st.session_state["misa_debt_data"])
        debt_label = st.session_state.get("misa_debt_type_label", "Công nợ")

        debt_col = None
        invoice_col = None
        name_col = None
        for c in df.columns:
            cl = c.lower()
            if "debt_amount" in cl and "invoice" not in cl:
                debt_col = c
            if "invoice_debt_amount" in cl:
                invoice_col = c
            if "account_object_name" in cl:
                name_col = c

        amount_col = invoice_col or debt_col

        if amount_col:
            df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce").fillna(0)
        if debt_col and debt_col != amount_col:
            df[debt_col] = pd.to_numeric(df[debt_col], errors="coerce").fillna(0)

        total_debt = df[amount_col].sum() if amount_col else 0
        num_objects = len(df)
        num_with_debt = int((df[amount_col] > 0).sum()) if amount_col else 0
        max_debt = df[amount_col].max() if amount_col else 0
        top_debtor = df.loc[df[amount_col].idxmax(), name_col] if amount_col and name_col and len(df) > 0 else "N/A"
        avg_debt = total_debt / num_with_debt if num_with_debt > 0 else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            metric_card("Tổng công nợ", format_vnd(total_debt), debt_label, "red")
        with c2:
            metric_card("Số đối tượng", f"{num_objects:,}", f"{num_with_debt:,} có nợ > 0", "blue")
        with c3:
            metric_card("Nợ lớn nhất", format_vnd(max_debt), top_debtor[:30] if top_debtor != "N/A" else "", "orange")
        with c4:
            metric_card("Nợ trung bình", format_vnd(avg_debt), "trên đối tượng có nợ", "purple")
        with c5:
            pct_with_debt = (num_with_debt / num_objects * 100) if num_objects > 0 else 0
            metric_card("Tỷ lệ có nợ", f"{pct_with_debt:.1f}%", f"{num_with_debt}/{num_objects} đối tượng", "teal")

        st.divider()
        debt_search = st.text_input("🔍 Tìm kiếm đối tượng", "", key="debt_search")
        df_filtered = df.copy()
        if debt_search:
            mask = df_filtered.apply(lambda row: debt_search.lower() in str(row).lower(), axis=1)
            df_filtered = df_filtered[mask]

        st.dataframe(df_filtered, use_container_width=True, height=500, hide_index=True)

        csv = df_filtered.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "📥 Tải xuống CSV", data=csv,
            file_name=f"congno_amis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv", key="debt_download"
        )

        render_debt_analytics(df.copy(), debt_label)


# ======================================================================
# Tab 4: Company Info
# ======================================================================
with tab4:
    st.subheader("🏢 Thông tin công ty")

    if st.button("🔍 Lấy thông tin công ty", type="primary", use_container_width=True, key="company_fetch"):
        with st.spinner("Đang tải..."):
            result = client.get_company_info()
            if result.get("Success"):
                data = result.get("Data", {})
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except json.JSONDecodeError:
                        pass
                st.session_state["misa_company_info"] = data
                st.success("✅ Đã lấy thông tin công ty")
            else:
                st.error(f"❌ Lỗi: {result.get('ErrorMessage', 'Unknown')}")

    if "misa_company_info" in st.session_state and st.session_state["misa_company_info"]:
        data = st.session_state["misa_company_info"]

        if isinstance(data, dict):
            important_fields = {
                "org_company_name": "🏢 Tên công ty",
                "org_company_code": "🔑 Mã công ty",
                "tax_code": "📋 Mã số thuế",
                "address": "📍 Địa chỉ",
                "tel": "📞 Điện thoại",
                "email": "📧 Email",
                "website": "🌐 Website",
                "director_name": "👤 Giám đốc",
                "chief_of_accounting": "👤 Kế toán trưởng",
                "bank_account": "🏦 Tài khoản NH",
                "bank_name": "🏦 Tên ngân hàng",
            }

            company_name = data.get("org_company_name") or data.get("company_name", "N/A")
            tax_code = data.get("tax_code", "N/A")

            c1, c2 = st.columns(2)
            with c1:
                metric_card("Tên công ty", company_name, "", "blue")
            with c2:
                metric_card("Mã số thuế", str(tax_code), "", "green")

            st.divider()

            displayed = set()
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Thông tin chính")
                for api_key, label in important_fields.items():
                    if api_key in data and data[api_key]:
                        st.markdown(f"**{label}:** {data[api_key]}")
                        displayed.add(api_key)

            with col2:
                st.markdown("#### Thông tin khác")
                remaining = {k: v for k, v in data.items() if k not in displayed and v}
                for key, value in list(remaining.items())[:15]:
                    st.markdown(f"**{key}:** {value}")

            with st.expander("📋 Xem toàn bộ dữ liệu JSON"):
                st.json(data)

        elif isinstance(data, list):
            st.json(data)
        else:
            st.json(data)


# ---- Footer ----
st.divider()
st.caption(f"""
🔗 Base URL: {BASE_URL} | 
⏰ Token hết hạn: {client.token_expiry.strftime('%H:%M:%S %d/%m/%Y') if client.token_expiry else 'N/A'} |
📖 [Tài liệu API MISA AMIS](https://www.misa.vn/154745/tai-lieu-open-api-tich-hop-amis-ke-toan-doanh-nghiep/)
""")
