# utils/vendor_invoice/invoice_dialogs.py
# All @st.dialog functions for Vendor Invoice module

import streamlit as st
import pandas as pd
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from utils.auth import AuthManager
from utils.vendor_invoice import (
    get_invoice_details, get_invoice_by_id, get_invoice_line_items,
    create_purchase_invoice, update_invoice, delete_invoice,
    generate_invoice_number, get_payment_terms, calculate_days_from_term_name,
    get_available_currencies, calculate_exchange_rates, validate_exchange_rates,
    format_exchange_rate, get_invoice_amounts_in_currency,
    get_uninvoiced_ans, get_filter_options, validate_invoice_selection,
    validate_uploaded_files, prepare_files_for_upload,
    summarize_files, save_media_records, cleanup_failed_uploads,
    S3Manager, InvoiceService, PaymentTermParser,
)

logger = logging.getLogger(__name__)

# ============================================================================
# PERMISSION HELPERS
# ============================================================================

_MODIFY_ROLES = {"admin", "inbound_manager", "supply_chain"}

def _can_modify() -> bool:
    """Return True if the current user may create/edit/delete invoices."""
    return st.session_state.get("user_role", "") in _MODIFY_ROLES

def _require_modify_permission() -> bool:
    """
    Show an error and return False if the user lacks write permission.
    Call at the top of any write-capable dialog.
    """
    if not _can_modify():
        st.error("🚫 You don't have permission to perform this action. "
                 "Required roles: admin, inbound_manager, supply_chain.")
        if st.button("Close", key="perm_close"):
            st.rerun()
        st.stop()
        return False
    return True


# ============================================================================
# CACHED DB CALLS — avoid hitting DB on every dialog rerun
# ============================================================================

@st.cache_data(ttl=120, show_spinner=False)
def _cached_uninvoiced_ans(filters_json: str) -> pd.DataFrame:
    """Cache uninvoiced ANs 2 min. Key = JSON-serialised active filters."""
    import json
    filters = json.loads(filters_json) if filters_json and filters_json != "{}" else {}
    return get_uninvoiced_ans(filters)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_filter_options() -> dict:
    """Cache filter dropdown options 5 min."""
    return get_filter_options()


# ============================================================================
# STATE  (imported from main page via session_state)
# ============================================================================

def _state():
    """Get InvoiceState from session."""
    return st.session_state.invoice_state


def _invalidate_cache():
    """Signal main page to clear invoice list cache."""
    st.session_state["_invalidate_invoice_cache"] = True


# ============================================================================
# CREATE INVOICE DIALOG — 3-step wizard
# ============================================================================

@st.dialog("📄 Create Purchase Invoice", width="large")
def create_invoice_dialog():
    _require_modify_permission()
    from utils.vendor_invoice import InvoiceService
    state = _state()
    service = InvoiceService()

    # ── Persistent header: progress + Cancel always visible at top ────────────
    prog_col, cancel_col = st.columns([5, 1])
    with prog_col:
        _show_progress(state.wizard_step)
    with cancel_col:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✖ Cancel", use_container_width=True, key="dlg_cancel_top"):
            _reset_wizard()
            st.rerun()
    st.markdown("---")

    if state.wizard_step == "select":
        _step1_select(state, service)
    elif state.wizard_step == "preview":
        _step2_preview(state, service)
    elif state.wizard_step == "confirm":
        _step3_confirm(state, service)


# ─── Progress bar ─────────────────────────────────────────────────────────────

def _show_progress(step: str):
    cur = {"select": 1, "preview": 2, "confirm": 3}.get(step, 1)
    c1, c2, c3 = st.columns(3)
    if cur >= 1:
        c1.success("✅ Step 1: Select ANs")
    else:
        c1.info("⭕ Step 1: Select ANs")
    if cur >= 2:
        c2.success("✅ Step 2: Review")
    else:
        c2.info("⭕ Step 2: Review")
    if cur >= 3:
        c3.success("✅ Step 3: Confirm")
    else:
        c3.info("⭕ Step 3: Confirm")


# ─── Step 1 : Select ANs ──────────────────────────────────────────────────────

def _step1_select(state, service):
    _filters_expander(state)

    # Convert filters to stable JSON key for cache lookup
    import json
    # Make filters JSON-serialisable (dates → str)
    def _serialisable(v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        if isinstance(v, (list, tuple)):
            return [_serialisable(i) for i in v]
        return v
    safe_filters = {k: _serialisable(v) for k, v in (state.filters or {}).items()}
    filters_key = json.dumps(safe_filters, sort_keys=True)

    with st.spinner("Loading ANs..."):
        raw_df = _cached_uninvoiced_ans(filters_key)

    if state.hide_completed_po_lines and "po_line_pending_invoiced_qty" in raw_df.columns:
        df = raw_df[raw_df["po_line_pending_invoiced_qty"] > 0].copy()
        hidden = len(raw_df) - len(df)
        if hidden > 0:
            st.info(f"ℹ️ Hiding {hidden} line(s) from completed PO lines")
    else:
        df = raw_df.copy()

    total = len(df)

    ctrl1, ctrl2, ctrl3 = st.columns([2, 1, 1])
    with ctrl1:
        st.markdown(f"**📊 Available ANs ({total})**  —  "
                    f"**{len(state.selected_ans)} selected**")
    with ctrl2:
        state.show_po_analysis = st.checkbox("PO Analysis", value=state.show_po_analysis,
                                             key="dlg_po_analysis")
    with ctrl3:
        state.hide_completed_po_lines = st.checkbox("Hide Completed",
                                                    value=state.hide_completed_po_lines,
                                                    key="dlg_hide_comp")

    if df.empty:
        st.info("No uninvoiced ANs found.")
        st.markdown("---")
        if st.button("✖ Cancel", use_container_width=True, key="s1_cancel_empty"):
            _reset_wizard()
            st.rerun()
    else:
        st.session_state["_dlg_an_df"] = df
        st.session_state["_dlg_an_service"] = service
        _an_table_fragment()


@st.fragment
def _an_table_fragment():
    """
    Isolated fragment — row selection, metrics, and validation feedback only.
    Navigation buttons (Cancel / Review Invoice) live OUTSIDE this fragment
    in _step1_select to avoid scope="app" reruns from within the fragment.
    """
    df      = st.session_state.get("_dlg_an_df", pd.DataFrame())
    service = st.session_state.get("_dlg_an_service")
    state   = _state()

    if df.empty:
        return

    disp     = _build_display_df(df, state.show_po_analysis)
    page_ids = df["can_line_id"].tolist()

    # Key-counter lets us clear selection programmatically without a full rerun
    tbl_key = f"dlg_an_table_{st.session_state.get('_an_tbl_key', 0)}"

    event = st.dataframe(
        disp,
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key=tbl_key,
    )

    # Sync selection → state.selected_ans
    sel_indices = event.selection.rows
    state.selected_ans -= set(page_ids)
    for i in sel_indices:
        state.selected_ans.add(page_ids[i])

    # ── Bottom bar ────────────────────────────────────────────────────────────
    st.markdown("---")

    # Always show Deselect All when there is a selection
    if state.selected_ans:
        _, desel_col = st.columns([5, 1])
        with desel_col:
            if st.button("✖ Deselect All", use_container_width=True, key="dlg_deselect"):
                state.selected_ans.clear()
                st.session_state["_an_tbl_key"] = st.session_state.get("_an_tbl_key", 0) + 1
                # Reset nav validation so outer buttons update
                st.session_state["_an_nav_valid"] = False
                st.rerun(scope="fragment")

    # Compute metrics + validation; signal _step1_select whether Review Invoice is allowed
    if state.selected_ans and service:
        selected_df = df[df["can_line_id"].isin(state.selected_ans)].copy()
        selected_df = selected_df.drop_duplicates(subset=["can_line_id"])

        if not selected_df.empty:
            totals = service.calculate_invoice_totals(selected_df)
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Selected ANs", totals["an_count"])
            mc2.metric("Lines",        totals["total_lines"])
            mc3.metric("Total Qty",    f"{totals['total_quantity']:,.2f}")
            mc4.metric("Est. Value",   f"{totals['total_value']:,.2f} {totals['currency']}")

            is_valid, err = validate_invoice_selection(selected_df)
            if not is_valid:
                st.error(f"❌ {err}")
                can_proceed = False
            else:
                val_result, val_msgs = service.validate_invoice_with_po_level(selected_df)
                if not val_result["can_invoice"]:
                    st.error(f"❌ {val_msgs['error']}")
                    can_proceed = False
                else:
                    for w in val_msgs.get("warnings", []):
                        st.warning(f"⚠️ {w}")
                    can_proceed = True
        else:
            can_proceed = False
    else:
        selected_df = None
        can_proceed = False

    # ── Nav buttons inside fragment so they re-render on every row click ──────
    # Dynamic key forces Streamlit to re-evaluate disabled state (avoids cache bug)
    st.markdown("---")
    nb1, _, nb3 = st.columns([1, 2, 1])
    with nb1:
        if st.button("✖ Cancel", use_container_width=True,
                     key=f"s1_cancel_{can_proceed}"):
            _reset_wizard()
            st.rerun(scope="app")
    with nb3:
        if st.button("➡️ Review Invoice", type="primary", use_container_width=True,
                     key=f"s1_next_{can_proceed}",
                     disabled=not can_proceed):
            state.selected_df = selected_df
            state.wizard_step = "preview"
            st.rerun(scope="app")


def _build_display_df(df: pd.DataFrame, show_po: bool) -> pd.DataFrame:
    """Build display-only DataFrame for the AN table — pure pandas, no DB."""
    disp = pd.DataFrame()
    disp["AN#"]     = df["arrival_note_number"].apply(
        lambda an: f"{an.split('-')[0]}-{an.split('-')[-1]}" if "-" in an else an)
    disp["PO#"]     = df["po_number"].str[:12]
    disp["Vendor"]  = df.apply(lambda r: f"{r['vendor_code'][:4]}-{r['vendor'][:14]}", axis=1)
    disp["Product"] = df.apply(lambda r: f"{r['pt_code'][:6]}-{r['product_name'][:14]}", axis=1)

    if show_po:
        _s = lambda col, fill=0: df[col] if col in df.columns else pd.Series([fill]*len(df), index=df.index)
        disp["PO Qty"]   = _s("po_buying_quantity").apply(lambda x: f"{x:,.0f}")
        disp["PO Pend"]  = _s("po_line_pending_invoiced_qty").apply(lambda x: f"{x:,.0f}")
        disp["AN Uninv"] = df["uninvoiced_quantity"].apply(lambda x: f"{x:,.0f}")
        leg = _s("legacy_invoice_qty")
        disp["Legacy"]   = leg.apply(lambda x: f"{x:,.0f}" if x > 0 else "-")
        disp["True Qty"] = df.apply(
            lambda r: f"{r.get('true_remaining_qty', r['uninvoiced_quantity']):,.0f}", axis=1)
        disp["Unit Cost"] = df["buying_unit_cost"].apply(
            lambda x: f"{float(str(x).split()[0]):,.0f}" if " " in str(x) else f"{float(x):,.0f}")
        disp["VAT"]      = _s("vat_percent").apply(lambda x: f"{x:.0f}%")
        disp["Est.Val"]  = df["estimated_invoice_value"].apply(lambda x: f"{x:,.0f}")

        def _risk(row):
            r, leg_v = [], row.get("legacy_invoice_qty", 0)
            if row.get("po_line_is_over_invoiced") == "Y": r.append("🔴OI")
            if row.get("po_line_is_over_delivered") == "Y": r.append("🔴OD")
            if leg_v > 0: r.append("⚠️LEG")
            if row.get("true_remaining_qty", row["uninvoiced_quantity"]) < row["uninvoiced_quantity"]:
                r.append("⚠️ADJ")
            return " ".join(r) if r else "✅OK"
        disp["Status"] = df.apply(_risk, axis=1)
    else:
        disp["Uninv Qty"] = df.apply(
            lambda r: f"{r['uninvoiced_quantity']:,.2f} {r['buying_uom']}", axis=1)
        disp["Unit Cost"] = df["buying_unit_cost"].astype(str)
        disp["VAT"]       = df.get("vat_percent", 0).apply(lambda x: f"{x:.0f}%")
        disp["Est.Val"]   = df["estimated_invoice_value"].apply(lambda x: f"{x:,.2f}")
        disp["Payment"]   = df.get("payment_term", pd.Series(["N/A"]*len(df), index=df.index)).fillna("N/A")

    return disp


def _filters_expander(state):
    with st.expander("🔍 Filters", expanded=False):
        filter_options = _cached_filter_options()   # cached — no DB hit
        c1, c2 = st.columns(2)
        with c1:
            vendor_opts = [f"{code} - {name}" for code, name in filter_options["vendors"]]
            sel = st.multiselect("Vendor", vendor_opts, key="dlg_f_vendor")
            if sel: state.filters["vendors"] = [v.split(" - ")[0] for v in sel]
            else: state.filters.pop("vendors", None)
        with c2:
            entity_opts = [f"{code} - {name}" for code, name in filter_options["entities"]]
            sel = st.multiselect("Legal Entity", entity_opts, key="dlg_f_entity")
            if sel: state.filters["entities"] = [e.split(" - ")[0] for e in sel]
            else: state.filters.pop("entities", None)

        c3, c4, c5, c6 = st.columns(4)
        _ms_filter(c3, "AN Number",  filter_options["an_numbers"],  "an_numbers",  state, "dlg_f_an")
        _ms_filter(c4, "PO Number",  filter_options["po_numbers"],  "po_numbers",  state, "dlg_f_po")
        _ms_filter(c5, "Creator",    filter_options["creators"],    "creators",    state, "dlg_f_creator")
        _ms_filter(c6, "Brand",      filter_options["brands"],      "brands",      state, "dlg_f_brand")

        d1, d2, d3, d4, d5 = st.columns([1, 1, 1, 1, 0.5])
        _date_filter(d1, "Arrival From",  "arrival_date_from",  state, "dlg_f_arr_from")
        _date_filter(d2, "Arrival To",    "arrival_date_to",    state, "dlg_f_arr_to")
        _date_filter(d3, "Created From",  "created_date_from",  state, "dlg_f_cr_from")
        _date_filter(d4, "Created To",    "created_date_to",    state, "dlg_f_cr_to")
        with d5:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Reset", use_container_width=True, key="dlg_f_reset"):
                state.filters = {}
                _cached_uninvoiced_ans.clear()
                st.rerun()


def _ms_filter(col, label, options, key, state, widget_key):
    with col:
        sel = st.multiselect(label, options, key=widget_key)
        if sel: state.filters[key] = sel
        else: state.filters.pop(key, None)


def _date_filter(col, label, key, state, widget_key):
    with col:
        d = st.date_input(label, value=None, key=widget_key)
        if d: state.filters[key] = d
        else: state.filters.pop(key, None)


# ─── Step 2 : Review ──────────────────────────────────────────────────────────

def _step2_preview(state, service):
    if state.selected_df is None or state.selected_df.empty:
        st.error("No data. Please go back.")
        if st.button("⬅ Back", key="s2_back_err"):
            state.wizard_step = "select"; st.rerun()
        return

    with st.spinner("Loading invoice details..."):
        details_df = get_invoice_details(list(state.selected_ans))

    if details_df.empty:
        st.error("Could not load invoice details.")
        if st.button("⬅ Back", key="s2_back_err2"):
            state.wizard_step = "select"; st.rerun()
        return

    details_df = details_df.drop_duplicates(subset=["arrival_detail_id"])
    state.details_df = details_df
    po_currency_code = details_df["po_currency_code"].iloc[0]

    # Invoice type toggle
    c1, c2 = st.columns(2)
    with c1:
        adv = st.checkbox("Advance Payment Invoice", value=state.is_advance_payment, key="dlg_adv")
        if adv != state.is_advance_payment:
            state.is_advance_payment = adv; st.rerun()
    with c2:
        if state.is_advance_payment:
            st.info("🔵 **Advance Payment (PI)**")
        else:
            st.success("🟢 **Commercial Invoice (CI)**")

    vendor_id = details_df["vendor_id"].iloc[0]
    buyer_id  = details_df["entity_id"].iloc[0]
    invoice_number = generate_invoice_number(vendor_id, buyer_id, state.is_advance_payment)

    # Currency
    st.markdown("**💱 Currency**")
    currencies_df = get_available_currencies()
    curr_c1, curr_c2, curr_c3 = st.columns(3)
    with curr_c1:
        st.info(f"PO Currency: **{po_currency_code}**")
    with curr_c2:
        if currencies_df.empty:
            st.error("⚠️ Could not load currencies. Please refresh.")
            return
        curr_opts = currencies_df["code"].tolist()
        curr_disp = [f"{r['code']} - {r['name']}" for _, r in currencies_df.iterrows()]
        def_idx = curr_opts.index(po_currency_code) if po_currency_code in curr_opts else 0
        sel_curr = st.selectbox("Invoice Currency", curr_disp, index=def_idx, key="dlg_curr")
        inv_curr_code = sel_curr.split(" - ")[0]
        inv_curr_id = int(currencies_df[currencies_df["code"] == inv_curr_code]["id"].iloc[0])
        state.invoice_currency_code = inv_curr_code
        state.invoice_currency_id   = inv_curr_id
    with curr_c3:
        with st.spinner("Fetching rates..."):
            rates = calculate_exchange_rates(po_currency_code, inv_curr_code)
        validate_exchange_rates(rates, po_currency_code, inv_curr_code)
        if po_currency_code != inv_curr_code:
            if rates.get("po_to_invoice_rate"):
                st.text(f"1 {po_currency_code} = {format_exchange_rate(rates['po_to_invoice_rate'])} {inv_curr_code}")
            else:
                st.error(f"⚠️ Rate {po_currency_code}/{inv_curr_code} unavailable")
        else:
            st.success("✅ Same currency")
        if inv_curr_code != "USD" and rates.get("usd_exchange_rate"):
            st.text(f"1 USD = {format_exchange_rate(rates['usd_exchange_rate'])} {inv_curr_code}")
        state.exchange_rates = rates

    # Payment terms
    st.markdown("**📅 Payment Terms & Dates**")
    _payment_terms_section(state)

    # Invoice form
    st.markdown("---")
    with st.form("dlg_invoice_form"):
        fc1, fc2 = st.columns(2)
        with fc1:
            st.text_input("Invoice Number", value=invoice_number, disabled=True)
            st.text_input("Invoice Date", value=str(state.invoice_date), disabled=True)
            st.text_input("Payment Terms", value=state.selected_payment_term or "", disabled=True)
        with fc2:
            state.commercial_invoice_no = st.text_input(
                "Commercial Invoice No.",
                value=state.commercial_invoice_no or "",
                disabled=state.is_advance_payment,
                placeholder="Required" if not state.is_advance_payment else "N/A for Advance"
            )
            st.text_input("Due Date", value=str(state.due_date or ""), disabled=True)
            state.email_to_accountant = st.checkbox("Email to Accountant",
                                                    value=state.email_to_accountant)

        st.markdown("**📊 Invoice Summary**")
        if po_currency_code != state.invoice_currency_code:
            converted = get_invoice_amounts_in_currency(
                state.selected_df, po_currency_code, state.invoice_currency_code)
            totals = converted if converted else service.calculate_invoice_totals_with_vat(state.selected_df)
        else:
            totals = service.calculate_invoice_totals_with_vat(state.selected_df)
            totals["currency"] = state.invoice_currency_code

        summary_df = service.prepare_invoice_summary(state.selected_df)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        _, _, tc = st.columns([2, 1, 1])
        with tc:
            st.markdown("**Totals**")
            st.text(f"Subtotal: {totals['subtotal']:,.2f} {totals['currency']}")
            st.text(f"VAT:      {totals['total_vat']:,.2f} {totals['currency']}")
            st.text(f"Total:    {totals['total_with_vat']:,.2f} {totals['currency']}")
        state.invoice_totals = totals

        fb1, _, fb3 = st.columns([1, 1, 1])
        with fb1:
            back_btn = st.form_submit_button("⬅ Back", use_container_width=True)
        with fb3:
            next_btn = st.form_submit_button("✅ Review & Confirm", type="primary",
                                             use_container_width=True)

    if back_btn:
        state.wizard_step = "select"; st.rerun()

    if next_btn:
        if not state.is_advance_payment and not state.commercial_invoice_no:
            st.error("❌ Commercial Invoice No. required"); return
        if not state.due_date:
            st.error("❌ Due date required"); return
        if state.due_date < state.invoice_date:
            st.error("❌ Due date cannot be before invoice date"); return

        usd_rate = 1.0 if state.invoice_currency_code == "USD" \
            else (state.exchange_rates or {}).get("usd_exchange_rate")
        state.invoice_data = {
            "invoice_number":        invoice_number,
            "commercial_invoice_no": state.commercial_invoice_no if not state.is_advance_payment else "",
            "invoiced_date":         state.invoice_date,
            "due_date":              state.due_date,
            "total_invoiced_amount": totals["total_with_vat"],
            "currency_id":           state.invoice_currency_id,
            "usd_exchange_rate":     usd_rate if usd_rate is not None else 1.0,
            "seller_id":             details_df["vendor_id"].iloc[0],
            "buyer_id":              details_df["entity_id"].iloc[0],
            "payment_term_id":       state.payment_term_id,
            "email_to_accountant":   1 if state.email_to_accountant else 0,
            "created_by":            st.session_state.username,
            "invoice_type":          "PROFORMA_INVOICE" if state.is_advance_payment else "COMMERCIAL_INVOICE",
            "advance_payment":       1 if state.is_advance_payment else 0,
            "po_currency_code":      po_currency_code,
            "invoice_currency_code": state.invoice_currency_code,
            "po_to_invoice_rate":    (state.exchange_rates or {}).get("po_to_invoice_rate", 1.0),
        }
        state.wizard_step = "confirm"; st.rerun()


def _payment_terms_section(state):
    unique_terms = state.selected_df["payment_term"].dropna().unique().tolist()
    all_terms_df = get_payment_terms()
    term_options = {}

    for tname in (unique_terms or ["Net 30"]):
        db_match = all_terms_df[all_terms_df["name"] == tname]
        if not db_match.empty:
            row = db_match.iloc[0]
            term_options[tname] = {"id": int(row["id"]), "days": int(row["days"]),
                                   "description": row.get("description", "")}
        else:
            days = calculate_days_from_term_name(tname)
            term_options[tname] = {"id": 1, "days": days, "description": f"{tname} ({days} days)"}

    if not term_options:
        term_options = {"Net 30": {"id": 1, "days": 30, "description": "Payment due in 30 days"}}

    tc1, tc2 = st.columns(2)
    with tc1:
        term_names = list(term_options.keys())
        def_idx = term_names.index(state.selected_payment_term) \
            if state.selected_payment_term in term_names else 0
        sel_term = st.selectbox("Payment Terms", term_names, index=def_idx, key="dlg_pt")
        state.selected_payment_term = sel_term
        state.payment_term_id = term_options[sel_term]["id"]
        if term_options[sel_term].get("description"):
            st.caption(term_options[sel_term]["description"])
    with tc2:
        inv_date = st.date_input("Invoice Date", value=state.invoice_date, key="dlg_inv_date")
        if inv_date != state.invoice_date:
            state.invoice_date = inv_date
            state.due_date = None

    parser = PaymentTermParser()
    calc_due, explanation, needs_review = parser.calculate_due_date(
        state.selected_payment_term, state.invoice_date,
        term_options[state.selected_payment_term].get("description", "")
    )
    if state.due_date is None:
        state.due_date = calc_due or (state.invoice_date + timedelta(days=30))

    dd1, dd2 = st.columns([2, 1])
    with dd1:
        new_due = st.date_input("Due Date", value=state.due_date,
                                min_value=state.invoice_date, key="dlg_due_date",
                                help=f"Auto-calculated: {explanation}")
        if new_due != state.due_date:
            state.due_date = new_due
        if needs_review:
            st.warning(f"⚠️ {explanation}")
        else:
            st.info(f"ℹ️ {explanation}")
    with dd2:
        if state.due_date and state.invoice_date:
            st.metric("Days", f"{(state.due_date - state.invoice_date).days}d")
        if st.button("🔄 Recalculate", key="dlg_recalc"):
            state.due_date = calc_due or (state.invoice_date + timedelta(days=30))
            st.rerun()


# ─── Step 3 : Confirm & Create ────────────────────────────────────────────────

def _step3_confirm(state, service):
    auth = AuthManager()

    if not state.invoice_data or state.details_df is None:
        st.error("Missing data. Please go back.")
        if st.button("⬅ Back", key="s3_back_err"):
            state.wizard_step = "preview"; st.rerun()
        return

    inv        = state.invoice_data
    details_df = state.details_df

    ic1, ic2 = st.columns(2)
    with ic1:
        st.markdown("**📋 Invoice Details**")
        inv_type = "Advance Payment (PI)" if inv.get("invoice_type") == "PROFORMA_INVOICE" \
            else "Commercial Invoice (CI)"
        st.text(f"Type:     {inv_type}")
        st.text(f"Number:   {inv['invoice_number']}")
        st.text(f"Date:     {inv['invoiced_date']}")
        st.text(f"Due:      {inv['due_date']}")
        if inv.get("commercial_invoice_no"):
            st.text(f"Comm. #:  {inv['commercial_invoice_no']}")
    with ic2:
        st.markdown("**💰 Financial**")
        st.text(f"Total:    {inv['total_invoiced_amount']:,.2f}")
        st.text(f"Currency: {inv['invoice_currency_code']}")
        if inv["po_currency_code"] != inv["invoice_currency_code"]:
            st.text(f"Rate:     {format_exchange_rate(inv['po_to_invoice_rate'])}")
        st.text(f"Lines:    {len(details_df)}")
        st.text(f"Email:    {'Yes' if inv['email_to_accountant'] else 'No'}")

    st.markdown("**📋 Line Items**")
    df_disp = details_df[["arrival_note_number", "po_number", "product_name",
                           "uninvoiced_quantity", "buying_unit_cost"]].copy()
    df_disp.insert(0, "#", range(1, len(df_disp) + 1))
    st.dataframe(df_disp, use_container_width=True, hide_index=True)

    if state.invoice_totals:
        t = state.invoice_totals
        _, _, tc = st.columns(3)
        with tc:
            st.text(f"Subtotal: {t['subtotal']:,.2f} {t['currency']}")
            st.text(f"VAT:      {t['total_vat']:,.2f} {t['currency']}")
            st.text(f"Total:    {t['total_with_vat']:,.2f} {t['currency']}")

    st.markdown("---")
    st.markdown("**📎 Attachments (Optional)**")
    uploaded = st.file_uploader(
        "Upload invoice files (PDF/PNG/JPG)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="dlg_file_upload"
    )
    if uploaded:
        is_valid, errors, metadata = validate_uploaded_files(uploaded)
        if not is_valid:
            for e in errors: st.error(f"❌ {e}")
            state.uploaded_files = []
        else:
            state.uploaded_files = uploaded
            state.uploaded_files_metadata = metadata
            summary = summarize_files(metadata)
            st.success(f"✅ {summary['count']} file(s) ready ({summary['total_size_formatted']})")
    else:
        state.uploaded_files = []

    st.markdown("---")
    st.warning("⚠️ Review carefully. This cannot be undone.")
    cb1, _, cb3 = st.columns([1, 1, 1])
    with cb1:
        if st.button("⬅ Back", use_container_width=True, key="s3_back"):
            state.wizard_step = "preview"; st.rerun()
    with cb3:
        label = "💾 Create & Upload Files" if state.uploaded_files else "💾 Create Invoice"
        if st.button(label, type="primary", use_container_width=True, key="s3_create"):
            _do_create_invoice(inv, details_df, auth, state)


def _do_create_invoice(invoice_data, details_df, auth, state):
    if state.invoice_creating:
        st.warning("⏳ Creating invoice, please wait..."); return

    state.invoice_creating = True
    s3_keys_uploaded = []
    media_ids_created = []

    try:
        keycloak_id = auth.get_user_keycloak_id()
        if not keycloak_id:
            st.error("❌ Could not retrieve user info."); return

        if state.uploaded_files:
            with st.spinner(f"📤 Uploading {len(state.uploaded_files)} file(s)..."):
                s3_mgr = S3Manager()
                prepared = prepare_files_for_upload(state.uploaded_files,
                                                    invoice_data["invoice_number"])
                results = s3_mgr.batch_upload_invoice_files(
                    [(f["content"], f["sanitized_name"]) for f in prepared])
                if not results["success"]:
                    for f in results["failed"]:
                        st.error(f"❌ Upload failed: {f['filename']} — {f['error']}")
                    return
                s3_keys_uploaded = results["uploaded"]
                st.success(f"✅ Uploaded {len(s3_keys_uploaded)} file(s)")

        if s3_keys_uploaded:
            with st.spinner("💾 Saving media records..."):
                ok, media_ids, err = save_media_records(s3_keys_uploaded, keycloak_id)
                if not ok:
                    st.error(f"❌ Media record error: {err}")
                    cleanup_failed_uploads(s3_keys_uploaded, S3Manager()); return
                media_ids_created = media_ids

        with st.spinner("📝 Creating invoice..."):
            ok, msg, invoice_id = create_purchase_invoice(
                invoice_data, details_df, keycloak_id,
                media_ids=media_ids_created or None)

        if ok:
            st.success(f"✅ {msg}")
            st.balloons()
            _invalidate_cache()
            state.last_created_invoice = {
                "id": invoice_id,
                "number": invoice_data["invoice_number"],
                "amount": invoice_data["total_invoiced_amount"],
                "currency": invoice_data["invoice_currency_code"],
                "attachments": len(media_ids_created),
            }
            _reset_wizard()
            st.rerun()
        else:
            st.error(f"❌ {msg}")
            if s3_keys_uploaded:
                cleanup_failed_uploads(s3_keys_uploaded, S3Manager())

    except Exception as e:
        logger.error(f"Invoice creation error: {e}")
        st.error(f"❌ Error: {str(e)}")
        if s3_keys_uploaded:
            try: cleanup_failed_uploads(s3_keys_uploaded, S3Manager())
            except Exception: pass
    finally:
        state.invoice_creating = False


def _reset_wizard():
    state = _state()
    state.wizard_step = "select"
    state.selected_ans = set()
    state.invoice_data = None
    state.details_df = None
    state.selected_df = None
    state.is_advance_payment = False
    state.invoice_creating = False
    state.selected_payment_term = None
    state.invoice_date = date.today()
    state.invoice_currency_id = None
    state.invoice_currency_code = None
    state.exchange_rates = None
    state.invoice_totals = None
    state.commercial_invoice_no = None
    state.email_to_accountant = False
    state.due_date = None
    state.payment_term_id = None
    state.uploaded_files = []
    state.uploaded_files_metadata = []
    state.upload_errors = []
    state.s3_upload_success = False
    state.s3_keys = []
    state.media_ids = []
    # Clean up fragment-level nav state
    st.session_state.pop("_an_can_proceed", None)
    st.session_state.pop("_an_selected_df", None)
    st.session_state.pop("_an_tbl_key", None)
    st.session_state.pop("_an_can_proceed", None)
    st.session_state.pop("_an_selected_df", None)
    st.session_state.show_create_dialog = False


# ============================================================================
# VIEW DIALOG
# ============================================================================

@st.dialog("👁️ Invoice Details", width="large")
def view_invoice_dialog(invoice_id: int):
    inv = get_invoice_by_id(invoice_id)
    if not inv:
        st.error("Invoice not found.")
        if st.button("Close"): st.rerun()
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("#### 📄 Invoice Info")
        st.text(f"Number:  {inv['invoice_number']}")
        st.text(f"Type:    {inv.get('invoice_type', 'Commercial Invoice')}")
        st.text(f"Comm #:  {inv.get('commercial_invoice_no', 'N/A')}")
        ps = inv.get("payment_status", "Unknown")
        if ps == "Fully Paid": st.success(f"Status: {ps}")
        elif ps == "Partially Paid": st.warning(f"Status: {ps}")
        else: st.error(f"Status: {ps}")
    with c2:
        st.markdown("#### 📅 Dates")
        st.text(f"Invoice:  {inv['invoiced_date']}")
        st.text(f"Due:      {inv['due_date']}")
        od = inv.get("days_overdue", 0)
        if od and od > 0:
            st.error(f"Overdue: {od} days")
        st.text(f"Created:  {inv.get('created_by', 'N/A')}")
    with c3:
        st.markdown("#### 💰 Financial")
        st.text(f"Amount:   {inv['total_invoiced_amount']:,.2f}")
        st.text(f"Currency: {inv.get('currency_code', 'USD')}")
        st.text(f"Terms:    {inv.get('payment_term_name', 'N/A')}")
        if inv.get("total_outstanding_amount"):
            st.warning(f"Outstanding: {inv['total_outstanding_amount']:,.2f}")

    st.markdown("---")
    vc1, vc2 = st.columns(2)
    with vc1:
        st.markdown("#### 🏢 Vendor")
        st.text(f"Name: {inv.get('vendor_name', 'N/A')}")
        st.text(f"Code: {inv.get('vendor_code', 'N/A')}")
    with vc2:
        st.markdown("#### 🏢 Buyer")
        st.text(f"Name: {inv.get('buyer_name', 'N/A')}")
        st.text(f"Code: {inv.get('buyer_code', 'N/A')}")

    st.markdown("---")
    st.markdown("#### 📋 Line Items")
    line_items = get_invoice_line_items(invoice_id)
    if not line_items.empty:
        avail = [c for c in ["po_number", "product_name", "purchased_invoice_quantity",
                              "amount", "vat_gst", "arrival_note_number"]
                 if c in line_items.columns]
        st.dataframe(line_items[avail].rename(columns={
            "po_number": "PO", "product_name": "Product",
            "purchased_invoice_quantity": "Qty", "amount": "Amount",
            "vat_gst": "VAT%", "arrival_note_number": "AN#",
        }), use_container_width=True, hide_index=True)
    else:
        st.info("No line items found.")

    st.markdown("---")
    if st.button("Close", use_container_width=True):
        st.rerun()


# ============================================================================
# EDIT DIALOG
# ============================================================================

@st.dialog("✏️ Edit Invoice", width="large")
def edit_invoice_dialog(invoice_id: int):
    _require_modify_permission()
    inv = get_invoice_by_id(invoice_id)
    if not inv:
        st.error("Invoice not found.")
        if st.button("Close"): st.rerun()
        return

    if inv.get("payment_status") == "Fully Paid":
        st.error("❌ Cannot edit a fully paid invoice.")
        if st.button("Close"): st.rerun()
        return

    st.markdown(f"**Invoice:** `{inv['invoice_number']}`")
    st.markdown("---")

    with st.form("edit_invoice_form"):
        ec1, ec2 = st.columns(2)
        with ec1:
            commercial = st.text_input("Commercial Invoice #",
                                       value=inv.get("commercial_invoice_no", "") or "")
            inv_date = st.date_input("Invoice Date",
                                     value=pd.to_datetime(inv["invoiced_date"]).date())
        with ec2:
            st.text_input("Total Amount", value=f"{inv['total_invoiced_amount']:,.2f}",
                          disabled=True)
            due_date = st.date_input("Due Date",
                                     value=pd.to_datetime(inv["due_date"]).date())
        email_acc = st.checkbox("Email to Accountant",
                                value=bool(inv.get("email_to_accountant", 0)))
        st.markdown("---")
        sb1, _, sb3 = st.columns([1, 2, 1])
        with sb1:
            cancel_btn = st.form_submit_button("Cancel", use_container_width=True)
        with sb3:
            save_btn = st.form_submit_button("💾 Save", type="primary", use_container_width=True)

    if cancel_btn:
        st.rerun()

    if save_btn:
        if due_date < inv_date:
            st.error("❌ Due date cannot be before invoice date")
        else:
            ok, msg = update_invoice(invoice_id, {
                "commercial_invoice_no": commercial,
                "invoiced_date": inv_date,
                "due_date": due_date,
                "email_to_accountant": 1 if email_acc else 0,
            })
            if ok:
                _invalidate_cache()
                st.success("✅ Invoice updated!")
                st.rerun()
            else:
                st.error(f"❌ {msg}")


# ============================================================================
# VOID DIALOG
# ============================================================================

@st.dialog("🚫 Void Invoice")
def void_invoice_dialog(invoice_id: int):
    _require_modify_permission()
    inv = get_invoice_by_id(invoice_id)
    inv_num = inv["invoice_number"] if inv else f"#{invoice_id}"
    st.warning(f"⚠️ Void **{inv_num}**? This cannot be undone.")
    if inv:
        st.text(f"Amount: {inv['total_invoiced_amount']:,.2f} {inv.get('currency_code', '')}")
        st.text(f"Vendor: {inv.get('vendor_name', 'N/A')}")
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Cancel", use_container_width=True):
            st.rerun()
    with c2:
        if st.button("🚫 Confirm Void", type="primary", use_container_width=True):
            ok, msg = delete_invoice(invoice_id, hard_delete=False)
            if ok:
                _invalidate_cache()
                st.rerun()
            else:
                st.error(f"❌ {msg}")