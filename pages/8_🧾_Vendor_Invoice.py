# pages/7_🧾_Vendor_Invoice.py
# Main page — layout + invoice list only.
# All dialogs live in utils/vendor_invoice/invoice_dialogs.py

import streamlit as st
import pandas as pd
import io
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Set, Optional, List
from dataclasses import dataclass, field

from utils.auth import AuthManager
from utils.vendor_invoice import (
    get_recent_invoices, InvoiceService,
)
from utils.vendor_invoice.invoice_dialogs import (
    create_invoice_dialog,
    view_invoice_dialog,
    edit_invoice_dialog,
    void_invoice_dialog,
)

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Vendor Invoice", page_icon="📊", layout="wide")

# ============================================================================
# PERMISSION HELPERS
# ============================================================================

_MODIFY_ROLES = {"admin", "inbound_manager", "supply_chain"}

def _can_modify() -> bool:
    """Return True if the current user is allowed to create/edit/delete invoices."""
    return st.session_state.get("user_role", "") in _MODIFY_ROLES


# ============================================================================
# STATE
# ============================================================================

@dataclass
class InvoiceState:
    selected_ans: Set[int]            = field(default_factory=set)
    wizard_step: str                  = "select"
    invoice_data: Optional[Dict]      = None
    details_df: Optional[pd.DataFrame] = None
    selected_df: Optional[pd.DataFrame] = None
    is_advance_payment: bool          = False
    show_po_analysis: bool            = True
    hide_completed_po_lines: bool     = True
    invoice_creating: bool            = False
    last_created_invoice: Optional[Dict] = None
    filters: Dict                     = field(default_factory=dict)
    selected_payment_term: Optional[str] = None
    invoice_date: date                = field(default_factory=date.today)
    invoice_currency_id: Optional[int] = None
    invoice_currency_code: Optional[str] = None
    exchange_rates: Optional[Dict]    = None
    invoice_totals: Optional[Dict]    = None
    commercial_invoice_no: Optional[str] = None
    email_to_accountant: bool         = False
    due_date: Optional[date]          = None
    payment_term_id: Optional[int]    = None
    uploaded_files: List              = field(default_factory=list)
    uploaded_files_metadata: List[Dict] = field(default_factory=list)
    upload_errors: List[str]          = field(default_factory=list)
    s3_upload_success: bool           = False
    s3_keys: List[str]                = field(default_factory=list)
    media_ids: List[int]              = field(default_factory=list)
    _table_key: int                   = 0   # increment to programmatically clear table selection


def _init_state():
    if "invoice_state" not in st.session_state:
        st.session_state.invoice_state = InvoiceState()
    if "show_create_dialog" not in st.session_state:
        st.session_state.show_create_dialog = False


# ============================================================================
# CACHE — load once, filter in pandas
# ============================================================================

@st.cache_data(ttl=60, show_spinner=False)
def _load_invoices(limit: int = 500) -> pd.DataFrame:
    return get_recent_invoices(limit=limit)


def _maybe_invalidate():
    """Called each render — clears cache if a write op signalled it."""
    if st.session_state.pop("_invalidate_invoice_cache", False):
        _load_invoices.clear()


# ============================================================================
# MAIN
# ============================================================================

def main():
    _init_state()
    AuthManager().require_auth()
    _maybe_invalidate()

    _header_fragment()

    tab_list, tab_analytics = st.tabs(["📋 Invoice List", "📈 Analytics"])
    with tab_list:
        show_invoice_list()
    with tab_analytics:
        show_analytics()


# ── Header (own fragment so Create Invoice button doesn't rerun whole page) ──

@st.fragment
def _header_fragment():
    state = st.session_state.invoice_state

    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.title("📊 Vendor Invoice Management")
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if _can_modify():
            if st.button("➕ Create Invoice", type="primary", use_container_width=True):
                st.session_state.show_create_dialog = True
                st.rerun(scope="fragment")
        else:
            st.button("➕ Create Invoice", type="primary",
                      use_container_width=True, disabled=True,
                      help="You don't have permission to create invoices")

    if state.last_created_invoice:
        inv = state.last_created_invoice
        st.success(
            f"✅ **Invoice Created:** {inv['number']} | "
            f"Amount: {inv['amount']:,.2f} {inv['currency']} | "
            f"Attachments: {inv.get('attachments', 0)}"
        )
        state.last_created_invoice = None

    if st.session_state.show_create_dialog:
        create_invoice_dialog()


# ============================================================================
# INVOICE LIST — fragment so filter changes don't rerun the whole page
# ============================================================================

@st.fragment
def show_invoice_list():
    state = st.session_state.invoice_state

    # ── Filters — wrapped in a form so the table only reruns on Apply ─────────
    with st.expander("🔍 Search & Filters", expanded=True):
        with st.form("invoice_filter_form", border=False):
            fc1, fc2, fc3, fc4 = st.columns(4)
            with fc1:
                date_filter = st.selectbox(
                    "Date Range",
                    ["Last 7 days", "Last 30 days", "Last 90 days", "This Month", "All Time"],
                    key="f_date"
                )
            with fc2:
                inv_search   = st.text_input("Invoice #",            placeholder="Search...", key="f_inv")
                comm_search  = st.text_input("Commercial Invoice #",  placeholder="Search...", key="f_comm")
            with fc3:
                vendor_search    = st.text_input("Vendor", placeholder="Search...", key="f_vendor")
                inv_type_filter  = st.selectbox("Invoice Type",
                                    ["All", "Commercial Invoice", "Advance Payment"], key="f_type")
            with fc4:
                status_filter = st.selectbox(
                    "Payment Status",
                    ["All", "Unpaid", "Partially Paid", "Fully Paid", "Overdue"],
                    key="f_status"
                )
                limit = st.number_input("Max Records", min_value=50, max_value=1000,
                                        value=500, step=50, key="f_limit")
            fa, _, fb = st.columns([1, 4, 1])
            with fa:
                st.form_submit_button("🔍 Apply", use_container_width=True)
            with fb:
                if st.form_submit_button("🔄 Reset", use_container_width=True):
                    for k in ["f_date", "f_inv", "f_comm", "f_vendor", "f_type", "f_status"]:
                        st.session_state.pop(k, None)
                    st.rerun(scope="fragment")

    # ── Load + filter ─────────────────────────────────────────────────────────
    raw_df = _load_invoices(int(limit))
    df = _filter(raw_df, date_filter, inv_search, comm_search,
                 vendor_search, inv_type_filter, status_filter)

    _show_summary_metrics(df)

    if df.empty:
        st.info("No invoices match the current filters.")
        return

    st.markdown("### 📋 Invoice List")
    disp = _prepare_display(df)

    # ── Native table with single-row selection ────────────────────────────────
    event = st.dataframe(
        disp.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key=f"invoice_table_{state._table_key}",
        column_config={
            "Invoice #":      st.column_config.TextColumn(width="large"),
            "Type":           st.column_config.TextColumn(width="small"),
            "Vendor":         st.column_config.TextColumn(width="large"),
            "Commercial #":   st.column_config.TextColumn(width="large"),
            "Amount":         st.column_config.TextColumn(width="medium"),
            "Invoice Date":   st.column_config.TextColumn(width="small"),
            "Due Date":       st.column_config.TextColumn(width="small"),
            "Payment Status": st.column_config.TextColumn(width="medium"),
            "Days Overdue":   st.column_config.NumberColumn(width="small"),
        }
    )

    # ── Action bar ────────────────────────────────────────────────────────────
    sel_rows = event.selection.rows
    if sel_rows:
        idx        = sel_rows[0]
        sel_id     = int(disp.iloc[idx]["id"])
        sel_num    = disp.iloc[idx]["Invoice #"]
        sel_status = disp.iloc[idx].get("Payment Status", "Unknown")

        info_col, clear_col = st.columns([8, 1])
        with info_col:
            st.markdown(f"**Selected:** `{sel_num}`")
        with clear_col:
            if st.button("✖ Clear", use_container_width=True, key="act_clear",
                         help="Deselect current row"):
                state._table_key += 1
                st.rerun(scope="fragment")

        ac1, ac2, ac3, _ = st.columns([1, 1, 1, 4])
        with ac1:
            if st.button("👁️ View", use_container_width=True, key="act_view"):
                st.session_state["_dlg"] = ("view", sel_id)
                st.rerun(scope="fragment")
        with ac2:
            if _can_modify():
                if st.button("✏️ Edit", use_container_width=True, key="act_edit"):
                    st.session_state["_dlg"] = ("edit", sel_id)
                    st.rerun(scope="fragment")
            else:
                st.button("✏️ Edit", use_container_width=True, key="act_edit",
                          disabled=True, help="You don't have permission to edit invoices")
        with ac3:
            if sel_status != "Fully Paid":
                if _can_modify():
                    if st.button("🚫 Void", use_container_width=True, key="act_void"):
                        st.session_state["_dlg"] = ("void", sel_id)
                        st.rerun(scope="fragment")
                else:
                    st.button("🚫 Void", use_container_width=True, key="act_void",
                              disabled=True, help="You don't have permission to void invoices")

    # ── Open dialogs from INSIDE fragment (no full-page rerun) ───────────────
    dlg = st.session_state.pop("_dlg", None)
    if dlg:
        action, inv_id = dlg
        if action == "view":
            view_invoice_dialog(inv_id)
        elif action == "edit":
            edit_invoice_dialog(inv_id)
        elif action == "void":
            void_invoice_dialog(inv_id)

    _show_export(disp)


# ============================================================================
# ANALYTICS — fragment
# ============================================================================

@st.fragment
def show_analytics():
    raw_df = _load_invoices(1000)
    if raw_df.empty:
        st.info("No data for analytics.")
        return

    col_sel, _ = st.columns([1, 3])
    with col_sel:
        period = st.selectbox("Period",
            ["Last 30 days", "Last 90 days", "Last 6 months", "Last Year"],
            key="analytics_period")

    thresholds = {"Last 30 days": 30, "Last 90 days": 90,
                  "Last 6 months": 180, "Last Year": 365}
    df = raw_df.copy()
    df["invoiced_date"] = pd.to_datetime(df["invoiced_date"])
    df = df[df["invoiced_date"] >= pd.Timestamp.now() - timedelta(days=thresholds[period])]

    st.markdown("### 📊 Key Metrics")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Invoices", f"{len(df):,}")
    m2.metric("Vendors", f"{df['vendor'].nunique():,}")
    if not df.empty and "currency" in df.columns:
        main_curr = df.groupby("currency")["total_invoiced_amount"].sum().idxmax()
        m3.metric(f"Total ({main_curr})",
                  f"{df[df['currency']==main_curr]['total_invoiced_amount'].sum():,.0f}")
    m4.metric("Avg Invoice", f"{df['total_invoiced_amount'].mean():,.0f}")

    st.markdown("### 💳 Payment Status")
    pa1, pa2 = st.columns(2)
    with pa1:
        if "payment_status" in df.columns:
            ps_df = df.groupby("payment_status")["total_invoiced_amount"].agg(["sum", "count"])
            ps_df.columns = ["Total Amount", "Count"]
            st.dataframe(ps_df, use_container_width=True)
    with pa2:
        if "aging_status" in df.columns:
            ag = df.groupby("aging_status")["total_outstanding_amount"].sum().reset_index()
            ag.columns = ["Aging", "Outstanding"]
            st.dataframe(ag, use_container_width=True, hide_index=True)

    st.markdown("### 📈 Trends")
    tr1, tr2 = st.columns(2)
    with tr1:
        st.markdown("#### Volume Over Time")
        df["month"] = df["invoiced_date"].dt.to_period("M")
        monthly = df.groupby("month").size().reset_index(name="count")
        monthly["month"] = monthly["month"].astype(str)
        if not monthly.empty:
            st.line_chart(monthly.set_index("month")["count"])
    with tr2:
        st.markdown("#### Top 10 Vendors")
        top_v = df.groupby("vendor")["total_invoiced_amount"].agg(["sum", "count"]).round(2)
        top_v.columns = ["Total Amount", "Count"]
        st.dataframe(top_v.sort_values("Total Amount", ascending=False).head(10),
                     use_container_width=True)


# ============================================================================
# HELPERS
# ============================================================================

def _filter(df, date_filter, inv_search, comm_search,
            vendor_search, inv_type_filter, status_filter) -> pd.DataFrame:
    if df.empty:
        return df
    if inv_search:
        df = df[df["invoice_number"].str.contains(inv_search, case=False, na=False)]
    if comm_search and "commercial_invoice_no" in df.columns:
        df = df[df["commercial_invoice_no"].str.contains(comm_search, case=False, na=False)]
    if vendor_search:
        df = df[df["vendor"].str.contains(vendor_search, case=False, na=False)]
    if inv_type_filter == "Commercial Invoice":
        df = df[df["invoice_number"].str.endswith("-P")]
    elif inv_type_filter == "Advance Payment":
        df = df[df["invoice_number"].str.endswith("-A")]
    if status_filter != "All":
        if status_filter == "Overdue":
            if "days_overdue" in df.columns:
                df = df[df["days_overdue"] > 0]
        elif "payment_status" in df.columns:
            df = df[df["payment_status"] == status_filter]
    if date_filter != "All Time" and "invoiced_date" in df.columns:
        df = df.copy()
        df["invoiced_date"] = pd.to_datetime(df["invoiced_date"])
        today = pd.Timestamp.now()
        date_map = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}
        if date_filter in date_map:
            df = df[df["invoiced_date"] >= today - timedelta(days=date_map[date_filter])]
        elif date_filter == "This Month":
            df = df[df["invoiced_date"] >= today.replace(day=1)]
    return df


def _prepare_display(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["invoice_type"] = d["invoice_number"].apply(
        lambda x: "AP" if str(x).endswith("-A") else "CI")
    for col in ["invoiced_date", "due_date"]:
        if col in d.columns:
            d[col] = pd.to_datetime(d[col]).dt.strftime("%Y-%m-%d")
    d["amount_display"] = d.apply(
        lambda r: f"{r['total_invoiced_amount']:,.0f} {r.get('currency','USD')}", axis=1)
    if "payment_status" not in d.columns:
        d["payment_status"] = "Unknown"
    if "days_overdue" not in d.columns:
        d["days_overdue"] = 0
    col_map = {
        "id": "id", "invoice_number": "Invoice #", "invoice_type": "Type",
        "vendor": "Vendor", "commercial_invoice_no": "Commercial #",
        "amount_display": "Amount", "invoiced_date": "Invoice Date",
        "due_date": "Due Date", "payment_status": "Payment Status",
        "days_overdue": "Days Overdue",
    }
    existing = {k: v for k, v in col_map.items() if k in d.columns}
    return d[list(existing.keys())].rename(columns=existing)


def _show_summary_metrics(df: pd.DataFrame):
    st.markdown("### 📈 Summary")
    if df.empty or "currency" not in df.columns:
        st.metric("Total Invoices", 0)
        return
    curr_grp = df.groupby("currency")["total_invoiced_amount"].agg(["sum", "count"])
    cols = st.columns(min(len(curr_grp) + 1, 5))
    cols[0].metric("Total Invoices", len(df))
    for idx, (curr, stats) in enumerate(curr_grp.iterrows()):
        if idx + 1 < 5:
            cols[idx + 1].metric(curr, f"{stats['sum']:,.0f}", f"{stats['count']} invoices")


def _show_export(df: pd.DataFrame):
    st.markdown("---")
    st.markdown("### 📥 Export")
    ec1, ec2, _ = st.columns(3)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with ec1:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, sheet_name="Invoices", index=False)
        st.download_button("📊 Excel", data=buf.getvalue(),
                           file_name=f"invoices_{ts}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
    with ec2:
        st.download_button("📄 CSV", data=df.to_csv(index=False),
                           file_name=f"invoices_{ts}.csv",
                           mime="text/csv", use_container_width=True)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()