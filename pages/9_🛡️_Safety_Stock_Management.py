# pages/0_🛡️_Safety_Stock_Management.py
"""
Safety Stock Management Main Page
Version 4.0 - Refactored: @st.fragment + st.form to minimize reruns

Key changes vs v3.4:
- @st.fragment: render_stats(), render_data_section(), demand_fetch_fragment()
- st.form: calculation params (each method), review_dialog, delete confirmation
- st.rerun(scope="fragment") for in-section refreshes
- dialog_data stores calc results so Save reads from state (no stale closures)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import logging
from typing import Dict, Optional

# Import utilities
from utils.auth import AuthManager
from utils.db import get_db_engine
from utils.safety_stock.crud import (
    get_safety_stock_levels,
    get_safety_stock_by_id,
    create_safety_stock,
    update_safety_stock,
    delete_safety_stock,
    create_safety_stock_review,
    get_review_history,
    bulk_create_safety_stock,
    get_review_history_analytics,
    get_coverage_analysis,
)
from utils.safety_stock.calculations import (
    calculate_safety_stock,
    Z_SCORE_MAP,
)
from utils.safety_stock.demand_analysis import (
    fetch_demand_stats,
    get_lead_time_estimate,
)
from utils.safety_stock.validations import (
    validate_safety_stock_data,
    validate_bulk_data,
    get_validation_summary
)
from utils.safety_stock.export import (
    export_to_excel,
    create_upload_template,
    generate_review_report
)
from utils.safety_stock.permissions import (
    get_user_role,
    has_permission,
    filter_data_for_customer,
    get_permission_message,
    get_user_info_display,
    apply_export_limit,
    log_action
)
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Safety Stock Management",
    page_icon="🛡️",
    layout="wide"
)

# ── Auth ───────────────────────────────────────────────────────────────────────
auth_manager = AuthManager()
if not auth_manager.check_session():
    st.warning("Please login to access this page")
    st.stop()

if not has_permission('view'):
    st.error("You don't have permission to access this page")
    st.stop()

# ── Session state ──────────────────────────────────────────────────────────────
if 'dialog_data' not in st.session_state:
    st.session_state.dialog_data = {}


# ══════════════════════════════════════════════════════════════════════════════
# Data Loading (cached)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def load_existing_filter_options():
    """Load filter options only from existing safety stock data"""
    try:
        engine = get_db_engine()

        entity_query = text("""
        SELECT DISTINCT e.id, e.company_code, e.english_name
        FROM safety_stock_levels s
        JOIN companies e ON s.entity_id = e.id
        WHERE s.delete_flag = 0 AND s.is_active = 1
        ORDER BY e.company_code
        """)

        customer_query = text("""
        SELECT DISTINCT c.id, c.company_code, c.english_name
        FROM safety_stock_levels s
        LEFT JOIN companies c ON s.customer_id = c.id
        WHERE s.delete_flag = 0 AND s.is_active = 1 AND s.customer_id IS NOT NULL
        ORDER BY c.company_code
        """)

        product_query = text("""
        SELECT DISTINCT p.id, p.pt_code, p.name, p.package_size, b.brand_name
        FROM safety_stock_levels s
        JOIN products p ON s.product_id = p.id
        LEFT JOIN brands b ON p.brand_id = b.id
        WHERE s.delete_flag = 0 AND s.is_active = 1
        ORDER BY p.pt_code
        """)

        with engine.connect() as conn:
            entities_df  = pd.read_sql(entity_query,   conn)
            customers_df = pd.read_sql(customer_query, conn)
            products_df  = pd.read_sql(product_query,  conn)

        entities   = (entities_df['company_code'] + ' - ' + entities_df['english_name']).tolist()
        entity_ids = entities_df['id'].tolist()

        customers   = []
        customer_ids = []
        if not customers_df.empty:
            customers    = (customers_df['company_code'] + ' - ' + customers_df['english_name']).tolist()
            customer_ids = customers_df['id'].tolist()

        products   = []
        product_ids = []
        if not products_df.empty:
            for _, row in products_df.iterrows():
                display = format_product_display(row)
                products.append(display)
                product_ids.append(row['id'])

        return {
            'entities': entities, 'entity_ids': entity_ids,
            'customers': customers, 'customer_ids': customer_ids,
            'products': products, 'product_ids': product_ids
        }
    except Exception as e:
        logger.error(f"Error loading filter options: {e}")
        return {'entities': [], 'entity_ids': [], 'customers': [], 'customer_ids': [], 'products': [], 'product_ids': []}


@st.cache_data(ttl=300)
def load_entities():
    """Load Internal companies (entities)"""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT DISTINCT c.id, c.company_code, c.english_name,
            COUNT(DISTINCT w.id) as warehouse_count
        FROM companies c
        INNER JOIN companies_company_types cct ON c.id = cct.companies_id
        INNER JOIN company_types ct ON cct.company_type_id = ct.id
        LEFT JOIN warehouses w ON c.id = w.company_id AND w.delete_flag = 0
        WHERE ct.name = 'Internal' AND c.delete_flag = 0 AND c.company_code IS NOT NULL
        GROUP BY c.id, c.company_code, c.english_name
        ORDER BY c.company_code
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn)
    except Exception as e:
        st.error(f"Error loading entities: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_customers():
    """Load customer list"""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT DISTINCT c.id, c.company_code, c.english_name
        FROM companies c
        INNER JOIN companies_company_types cct ON c.id = cct.companies_id
        INNER JOIN company_types ct ON cct.company_type_id = ct.id
        WHERE ct.name = 'Customer' AND c.delete_flag = 0 AND c.company_code IS NOT NULL
        ORDER BY c.company_code
        """)
        with engine.connect() as conn:
            return pd.read_sql(query, conn)
    except Exception as e:
        st.error(f"Error loading customers: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_all_products_for_select():
    """Load all products formatted for selectbox"""
    try:
        engine = get_db_engine()
        query = text("""
        SELECT p.id, p.pt_code, p.name, p.package_size, p.uom, b.brand_name
        FROM products p
        LEFT JOIN brands b ON p.brand_id = b.id
        WHERE p.delete_flag = 0 AND p.pt_code IS NOT NULL
        ORDER BY p.pt_code
        """)
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)

        if df.empty:
            return [], {}

        options = []
        id_map  = {}
        for _, row in df.iterrows():
            display = format_product_display(row)
            options.append(display)
            id_map[display] = row['id']

        return options, id_map
    except Exception as e:
        logger.error(f"Error loading products: {e}")
        return [], {}


def format_product_display(row) -> str:
    pt_code = str(row['pt_code'])
    name    = str(row['name']) if pd.notna(row['name']) else ""
    pkg     = str(row['package_size']) if pd.notna(row['package_size']) else ""
    brand   = str(row['brand_name']) if pd.notna(row['brand_name']) else ""

    display = f"{pt_code} | {name}"
    if pkg and brand:
        display += f" | {pkg} ({brand})"
    elif pkg:
        display += f" | {pkg}"
    elif brand:
        display += f" ({brand})"
    return display


def get_quick_stats():
    try:
        engine = get_db_engine()
        query = text("""
        SELECT
            COUNT(DISTINCT s.id)                                                          AS total_items,
            COUNT(DISTINCT CASE WHEN s.customer_id IS NOT NULL THEN s.id END)             AS customer_rules,
            COUNT(DISTINCT CASE
                WHEN ssp.last_calculated_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                  OR ssp.last_calculated_date IS NULL
                THEN s.id END)                                                             AS needs_review,
            COUNT(DISTINCT s.product_id)                                                   AS unique_products,
            -- Rules expiring within 30 days
            COUNT(DISTINCT CASE
                WHEN s.effective_to IS NOT NULL
                  AND s.effective_to BETWEEN CURRENT_DATE() AND DATE_ADD(CURRENT_DATE(), INTERVAL 30 DAY)
                THEN s.id END)                                                             AS expiring_soon,
            -- Rules with no reorder point set
            COUNT(DISTINCT CASE
                WHEN s.reorder_point IS NULL OR s.reorder_point = 0
                THEN s.id END)                                                             AS no_reorder_point,
            -- FIXED method count and percentage
            COUNT(DISTINCT CASE WHEN ssp.calculation_method = 'FIXED' OR ssp.calculation_method IS NULL
                THEN s.id END)                                                             AS fixed_method_count
        FROM safety_stock_levels s
        LEFT JOIN safety_stock_parameters ssp ON s.id = ssp.safety_stock_level_id
        WHERE s.delete_flag = 0 AND s.is_active = 1
        """)
        with engine.connect() as conn:
            return conn.execute(query).fetchone()
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return None


def safe_int(value, default=0) -> int:
    try:
        if pd.isna(value):
            return default
        if hasattr(value, 'item'):
            return int(value.item())
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def fetch_and_store_demand_data(product_id, entity_id, customer_id, fetch_days, exclude_pending):
    """Fetch demand data and store results in dialog_data"""
    stats = fetch_demand_stats(
        product_id=product_id,
        entity_id=entity_id,
        customer_id=customer_id,
        days_back=fetch_days,
        exclude_pending=exclude_pending
    )
    lead_time_info = get_lead_time_estimate(
        product_id=product_id,
        entity_id=entity_id,
        customer_id=customer_id
    )

    st.session_state.dialog_data['demand_stats'] = stats
    if lead_time_info['sample_size'] > 0:
        st.session_state.dialog_data['lead_time_days'] = lead_time_info['avg_lead_time_days']
        st.session_state.dialog_data['lead_time_info'] = lead_time_info

    if stats['data_points'] > 0:
        st.session_state.dialog_data['selected_method'] = stats['suggested_method']

    return stats, lead_time_info


# ══════════════════════════════════════════════════════════════════════════════
# Fragment: Stats Dashboard
# ══════════════════════════════════════════════════════════════════════════════

@st.fragment
def render_stats():
    """Renders KPI metrics independently – does not rerun when filters change"""
    stats = get_quick_stats()
    if not stats:
        return

    total = stats.total_items or 0

    # ── Row 1: Core metrics ───────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Active Rules", total)
    with col2:
        st.metric("Customer Rules", stats.customer_rules or 0)
    with col3:
        nr = stats.needs_review or 0
        st.metric("Needs Review", nr, delta=f"⚠️ {nr} overdue" if nr > 0 else None,
                  delta_color="inverse")
    with col4:
        st.metric("Unique Products", stats.unique_products or 0)

    # ── Row 2: Data quality / alerts ─────────────────────────────────────────
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        exp = stats.expiring_soon or 0
        st.metric("Expiring in 30d", exp,
                  delta="⚠️ Action needed" if exp > 0 else None,
                  delta_color="inverse")
    with col6:
        no_rop = stats.no_reorder_point or 0
        st.metric("No Reorder Point", no_rop,
                  delta="Data gap" if no_rop > 0 else "✅ Complete",
                  delta_color="inverse" if no_rop > 0 else "off")
    with col7:
        fixed = stats.fixed_method_count or 0
        fixed_pct = round(fixed / total * 100) if total > 0 else 0
        st.metric("Manual (FIXED)", f"{fixed} ({fixed_pct}%)",
                  delta="Consider auto-calc" if fixed_pct > 70 else None,
                  delta_color="off")
    with col8:
        auto = total - (stats.fixed_method_count or 0)
        auto_pct = round(auto / total * 100) if total > 0 else 0
        st.metric("Auto-Calculated", f"{auto} ({auto_pct}%)")


# ══════════════════════════════════════════════════════════════════════════════
# Fragment: Demand Fetch (called inside safety_stock_form dialog)
# ══════════════════════════════════════════════════════════════════════════════

@st.fragment
def demand_fetch_fragment():
    """
    Independent fragment for demand data analysis.
    Reads product/entity context from st.session_state.dialog_data.
    Clicking 'Fetch Data' reruns only this fragment, NOT the whole dialog.
    """
    ctx        = st.session_state.dialog_data
    product_id = ctx.get('product_id')
    entity_id  = ctx.get('entity_id')
    customer_id = ctx.get('customer_id')

    if not product_id or not entity_id:
        st.info("ℹ️ Select product and entity in Basic Information tab first")
        return

    st.markdown("#### 📊 Historical Demand Analysis")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        fetch_days = st.number_input(
            "Analyze last N days",
            min_value=30, max_value=365, value=180, step=30,
            key="frag_fetch_days"
        )
    with col2:
        exclude_pending = st.checkbox(
            "Exclude pending deliveries", value=True, key="frag_exclude_pending"
        )
    with col3:
        st.write("")  # vertical alignment
        if st.button("Fetch Data", type="primary", width="stretch", key="frag_fetch_btn"):
            with st.spinner("Fetching from delivery_full_view..."):
                fetch_and_store_demand_data(
                    product_id, entity_id, customer_id,
                    int(fetch_days), bool(exclude_pending)
                )
                st.session_state.dialog_data['data_fetched'] = True

    # ── Display results ────────────────────────────────────────────────────────
    if not ctx.get('data_fetched'):
        return

    stats = ctx.get('demand_stats', {})
    if stats.get('data_points', 0) == 0:
        st.warning("No demand data found for this product / entity / period")
        return

    st.success(f"✔ Found {stats['data_points']} delivery dates over {stats.get('days_analyzed', 0)} days")

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Data Points",  f"{stats['data_points']}")
    mc2.metric("Avg/Day",      f"{stats['avg_daily_demand']:.1f}")
    mc3.metric("Std Dev",      f"{stats['demand_std_dev']:.1f}")
    cv    = stats['cv_percent']
    color = "🟢" if cv < 20 else "🟡" if cv < 50 else "🔴"
    mc4.metric("Variability",  f"{color} {cv:.0f}%")

    st.info(
        f"💡 Suggested method: **{stats['suggested_method']}** "
        f"| Range: {stats['min_daily_demand']:.0f} – {stats['max_daily_demand']:.0f} units/day"
    )

    if 'lead_time_info' in ctx:
        lt = ctx['lead_time_info']
        st.success(
            f"📦 Estimated lead time: **{lt['avg_lead_time_days']:.0f} days** "
            f"(from {lt['sample_size']} deliveries)"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Fragment: Main Data Section (filters + actions + table + row actions)
# ══════════════════════════════════════════════════════════════════════════════

@st.fragment
def render_data_section():
    """
    Contains the entire interactive data layer.
    Filter changes rerun only this fragment – header and stats are unaffected.
    Post-save/delete from dialogs triggers a full app rerun (st.rerun()),
    which also refreshes this fragment with fresh data.
    """

    # ── Filters Row 1 ─────────────────────────────────────────────────────────
    with st.container():
        st.subheader("Filters")
        col1, col2, col3, col4 = st.columns([2, 2, 4, 1])
        existing = load_existing_filter_options()

        with col1:
            entity_opts = ['All Entities'] + existing['entities']
            sel_entity  = st.selectbox("Entity", entity_opts, key="flt_entity")
            entity_id   = None
            if sel_entity != 'All Entities' and sel_entity in existing['entities']:
                entity_id = existing['entity_ids'][existing['entities'].index(sel_entity)]

        with col2:
            base_customer_opts = ['All Customers', 'General Rules Only'] + existing['customers']
            if get_user_role() == 'customer':
                session_cid = st.session_state.get('customer_id')
                if session_cid:
                    for i, cid in enumerate(existing['customer_ids']):
                        if cid == session_cid:
                            base_customer_opts = [existing['customers'][i]]
                            break

            sel_customer = st.selectbox("Customer", base_customer_opts, key="flt_customer")
            customer_id  = None
            if sel_customer == 'General Rules Only':
                customer_id = 'general'
            elif sel_customer not in ('All Customers', 'General Rules Only') and sel_customer in existing['customers']:
                customer_id = existing['customer_ids'][existing['customers'].index(sel_customer)]

        with col3:
            product_opts = ['All Products'] + existing['products']
            sel_product  = st.selectbox(
                "Product Search", product_opts, index=0,
                placeholder="Select or type to search...", key="flt_product"
            )
            product_id = None
            if sel_product != 'All Products' and sel_product in existing['products']:
                product_id = existing['product_ids'][existing['products'].index(sel_product)]

        with col4:
            STATUS_MAP  = {'Active': 'active', 'All': 'all', 'Expired': 'expired', 'Future': 'future'}
            sel_status  = st.selectbox("Status", list(STATUS_MAP.keys()), index=0, key="flt_status")
            status      = STATUS_MAP[sel_status]

    # ── Filters Row 2: Advanced ────────────────────────────────────────────────
    with st.container():
        col5, col6, col7, col8, col9 = st.columns(5)

        with col5:
            METHOD_FILTER_MAP = {
                'All Methods': None,
                'FIXED (Manual)': 'FIXED',
                'Days of Supply': 'DAYS_OF_SUPPLY',
                'Lead Time Based': 'LEAD_TIME_BASED'
            }
            sel_method    = st.selectbox("Calculation Method", list(METHOD_FILTER_MAP.keys()), key="flt_method")
            method_filter = METHOD_FILTER_MAP[sel_method]

        with col6:
            needs_review_only = st.checkbox(
                "⚠️ Needs Review Only",
                value=False, key="flt_needs_review",
                help="Show only rules not reviewed in the last 30 days"
            )

        with col7:
            expiring_only = st.checkbox(
                "📅 Expiring in 30 Days",
                value=False, key="flt_expiring",
                help="Show rules whose effective_to is within the next 30 days"
            )

        with col8:
            no_rop_only = st.checkbox(
                "🔴 No Reorder Point",
                value=False, key="flt_no_rop",
                help="Show rules missing a reorder point"
            )

        with col9:
            has_reviews_only = st.checkbox(
                "📋 Has Reviews",
                value=False, key="flt_has_reviews",
                help="Show only rules that have been reviewed at least once"
            )

    # ── Action buttons ─────────────────────────────────────────────────────────
    st.divider()
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        if st.button(
            "➕ Add Safety Stock", type="primary", width="stretch",
            disabled=not has_permission('create')
        ):
            st.session_state.dialog_data = {}
            safety_stock_form('add')

    with col2:
        if st.button(
            "📤 Bulk Upload", width="stretch",
            disabled=not has_permission('bulk_upload')
        ):
            bulk_upload_dialog()

    with col3:
        # Single button that prepares and downloads immediately
        query_cid_exp = None if customer_id == 'general' else customer_id
        exp_kwargs = dict(entity_id=entity_id, customer_id=query_cid_exp, status=status)
        if product_id:
            exp_kwargs['product_id'] = product_id
        export_df = get_safety_stock_levels(**exp_kwargs)
        export_df = filter_data_for_customer(export_df)
        export_df, was_limited = apply_export_limit(export_df)
        if not export_df.empty:
            excel_bytes = export_to_excel(export_df)
            st.download_button(
                "📥 Export Excel",
                excel_bytes,
                f"safety_stock_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch"
            )
            if was_limited:
                st.caption(f"Limited to {len(export_df)} rows")
        else:
            st.button("📥 Export Excel", width="stretch", disabled=True)

    with col4:
        report_bytes = generate_review_report()
        st.download_button(
            "📊 Review Report",
            report_bytes,
            f"review_{datetime.now().strftime('%Y%m%d')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch"
        )

    with col5:
        if st.button("🔄 Refresh", width="stretch"):
            st.cache_data.clear()
            st.rerun(scope="fragment")

    # ── Data table ─────────────────────────────────────────────────────────────
    st.divider()

    query_customer_id = None if customer_id == 'general' else customer_id
    fetch_kwargs = dict(entity_id=entity_id, customer_id=query_customer_id, status=status)
    if product_id:
        fetch_kwargs['product_id'] = product_id

    df = get_safety_stock_levels(**fetch_kwargs)
    df = filter_data_for_customer(df)

    # ── Apply advanced filters client-side ────────────────────────────────────
    if method_filter and 'calculation_method' in df.columns:
        df = df[df['calculation_method'] == method_filter]

    if needs_review_only and 'last_calculated_date' in df.columns:
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=30)
        df = df[df['last_calculated_date'].isna() | (pd.to_datetime(df['last_calculated_date']) < cutoff)]

    if expiring_only and 'effective_to' in df.columns:
        today = pd.Timestamp.now().normalize()
        in_30 = today + pd.Timedelta(days=30)
        df = df[
            df['effective_to'].notna() &
            (pd.to_datetime(df['effective_to']) >= today) &
            (pd.to_datetime(df['effective_to']) <= in_30)
        ]

    if no_rop_only and 'reorder_point' in df.columns:
        df = df[df['reorder_point'].isna() | (df['reorder_point'] == 0)]

    if has_reviews_only and 'review_count' in df.columns:
        df = df[df['review_count'] > 0]

    if df.empty:
        st.info("No records found. Adjust filters or add a new safety stock rule.")
        return

    # ── Expiry alert banner ───────────────────────────────────────────────────
    if 'effective_to' in df.columns:
        today_ts = pd.Timestamp.now().normalize()
        expiring_df = df[
            df['effective_to'].notna() &
            (pd.to_datetime(df['effective_to']) >= today_ts) &
            (pd.to_datetime(df['effective_to']) <= today_ts + pd.Timedelta(days=30))
        ]
        if not expiring_df.empty and not expiring_only:
            st.warning(
                f"📅 **{len(expiring_df)} rule(s) expiring within 30 days** — "
                f"check the *Expiring in 30 Days* filter to review them."
            )

    # ── Build display dataframe ───────────────────────────────────────────────
    METHOD_ABBREV = {
        'FIXED':           'FIXED',
        'DAYS_OF_SUPPLY':  'DOS',
        'LEAD_TIME_BASED': 'LTB',
    }

    display_df = pd.DataFrame()
    display_df['PT Code']          = df['pt_code'] if 'pt_code' in df.columns else ''
    display_df['Product Name']     = df['product_name'] if 'product_name' in df.columns else ''
    display_df['Brand']            = df['brand_name'] if 'brand_name' in df.columns else ''
    display_df['Entity']           = df['entity_code'] if 'entity_code' in df.columns else ''
    display_df['Customer']         = df['customer_code'].fillna('All') if 'customer_code' in df.columns else 'All'
    display_df['SS Qty']           = df['safety_stock_qty'] if 'safety_stock_qty' in df.columns else 0
    display_df['Reorder Point']    = df['reorder_point'].apply(
        lambda x: '—' if pd.isna(x) or x == 0 else f"{x:.0f}"
    ) if 'reorder_point' in df.columns else '—'
    display_df['Method']           = df['calculation_method'].map(
        lambda x: METHOD_ABBREV.get(x, x or 'FIXED')
    ) if 'calculation_method' in df.columns else 'FIXED'
    display_df['Rule Type']        = df['rule_type'] if 'rule_type' in df.columns else ''
    display_df['Status']           = df['status'] if 'status' in df.columns else ''
    display_df['Effective Period'] = df.apply(
        lambda r: f"{r.get('effective_from', '')} → {r.get('effective_to', '') or 'ongoing'}",
        axis=1
    )
    display_df['Priority']         = df['priority_level'] if 'priority_level' in df.columns else 100
    display_df['Last Calculated']  = df['last_calculated_date'].apply(
        lambda x: pd.to_datetime(x).strftime('%Y-%m-%d') if pd.notna(x) else '—'
    ) if 'last_calculated_date' in df.columns else '—'

    # ── Review badge columns ──────────────────────────────────────────────────
    if 'review_count' in df.columns:
        def _review_badge(row):
            cnt = int(row.get('review_count', 0) or 0)
            if cnt == 0:
                return '—'
            action = str(row.get('last_action', '') or '')
            icon = {'INCREASED': '📈', 'DECREASED': '📉', 'NO_CHANGE': '➡️',
                    'METHOD_CHANGED': '🔄'}.get(action, '✅')
            return f"{icon} {cnt}"
        display_df['Reviews'] = df.apply(_review_badge, axis=1)
        display_df['Last Review'] = df['last_review_date'].apply(
            lambda x: pd.to_datetime(x).strftime('%Y-%m-%d') if pd.notna(x) else '—'
        )
    else:
        display_df['Reviews']     = '—'
        display_df['Last Review'] = '—'

    # ── Row highlighting via pandas Styler ───────────────────────────────────
    def _style_rows(row):
        rev = row.get('Reviews', '—')
        if rev == '—':
            return [''] * len(row)
        # Pick color by last action icon prefix
        if '📈' in str(rev):
            bg = 'background-color: #e8f5e9'   # light green — increased
        elif '📉' in str(rev):
            bg = 'background-color: #fff3e0'   # light amber — decreased
        elif '🔄' in str(rev):
            bg = 'background-color: #e3f2fd'   # light blue  — method changed
        else:
            bg = 'background-color: #f3e5f5'   # light purple — reviewed/no change
        return [bg] * len(row)

    styled_df = display_df.style.apply(_style_rows, axis=1)

    st.subheader(f"Safety Stock Rules ({len(df)} records)")

    # Legend for row colors
    st.caption(
        "Row colors — "
        "🟢 **Green**: SS increased &nbsp;|&nbsp; "
        "🟠 **Amber**: SS decreased &nbsp;|&nbsp; "
        "🔵 **Blue**: Method changed &nbsp;|&nbsp; "
        "🟣 **Purple**: Reviewed / no change &nbsp;|&nbsp; "
        "⬜ **White**: Never reviewed"
    )

    selected = st.dataframe(
        styled_df,
        width="stretch",
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun"
    )

    if not (selected and selected.selection.rows):
        return

    idx    = selected.selection.rows[0]
    record = df.iloc[idx]

    # ── Selected record info ──────────────────────────────────────────────────
    st.divider()
    info_cols = st.columns(5)
    info_cols[0].markdown(f"**PT Code:** {record.get('pt_code', '—')}")
    info_cols[1].markdown(f"**Product:** {str(record.get('product_name', '—'))[:40]}")
    info_cols[2].markdown(f"**SS Qty:** {safe_float(record.get('safety_stock_qty')):.0f}")
    rop_val = record.get('reorder_point')
    info_cols[3].markdown(f"**Reorder Point:** {'—' if pd.isna(rop_val) or rop_val == 0 else f'{rop_val:.0f}'}")
    info_cols[4].markdown(f"**Method:** {METHOD_ABBREV.get(record.get('calculation_method'), record.get('calculation_method') or 'FIXED')}")

    # ── Row actions ────────────────────────────────────────────────────────────
    st.subheader("Actions")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("✏️ Edit", width="stretch", disabled=not has_permission('edit')):
            st.session_state.dialog_data = {}
            safety_stock_form('edit', record['id'])

    with col2:
        if st.button("📋 Review", width="stretch", disabled=not has_permission('review')):
            review_dialog(record['id'])

    with col3:
        if st.button("📊 Compare vs Inventory", width="stretch"):
            st.session_state['compare_record_id'] = int(record['id'])

    with col4:
        if st.button("🗑️ Delete", width="stretch",
                     disabled=not has_permission('delete'),
                     type="secondary"):
            st.session_state['pending_delete_id'] = int(record['id'])

    # ── Delete confirmation (popover-style inline) ────────────────────────────
    if st.session_state.get('pending_delete_id') == int(record['id']):
        st.error(
            f"⚠️ Delete safety stock rule for **{record.get('pt_code')}** "
            f"({record.get('customer_code') or 'General Rule'})? This cannot be undone."
        )
        yes_col, no_col, _ = st.columns([1, 1, 4])
        with yes_col:
            if st.button("✅ Yes, Delete", type="primary", width="stretch", key="del_yes"):
                success, msg = delete_safety_stock(int(record['id']), st.session_state.username)
                if success:
                    log_action('DELETE', f"Deleted safety stock ID {record['id']}")
                    st.session_state.pop('pending_delete_id', None)
                    st.cache_data.clear()
                    st.rerun(scope="fragment")
                else:
                    st.error(msg)
        with no_col:
            if st.button("❌ Cancel", width="stretch", key="del_no"):
                st.session_state.pop('pending_delete_id', None)
                st.rerun(scope="fragment")

    # ── Review History expander ───────────────────────────────────────────────
    with st.expander("📜 Review History", expanded=False):
        history = get_review_history(int(record['id']))
        if not history.empty:
            st.dataframe(history, width="stretch", hide_index=True)
        else:
            st.info("No review history found for this rule.")

    # ── Compare vs Inventory panel ────────────────────────────────────────────
    if st.session_state.get('compare_record_id') == int(record['id']):
        _render_compare_panel(record)


def _render_compare_panel(record):
    """Inline compare panel: Safety Stock vs actual inventory"""
    st.divider()
    st.markdown("#### 📊 Compare: Safety Stock vs Current Inventory")

    try:
        engine = get_db_engine()
        inv_query = text("""
        SELECT
            w.name                     AS warehouse,
            SUM(ih.remain)             AS qty_on_hand,
            COUNT(DISTINCT ih.id)      AS lot_count
        FROM inventory_histories ih
        JOIN warehouses w ON ih.warehouse_id = w.id
        WHERE ih.product_id = :product_id
          AND ih.delete_flag = 0
          AND ih.remain > 0
        GROUP BY w.id, w.name
        ORDER BY qty_on_hand DESC
        """)
        with engine.connect() as conn:
            inv_df = pd.read_sql(inv_query, conn, params={'product_id': int(record['product_id'])})

        ss_qty  = safe_float(record.get('safety_stock_qty'))
        rop_val = safe_float(record.get('reorder_point'))
        total_inventory = inv_df['qty_on_hand'].sum() if not inv_df.empty else 0

        # Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Safety Stock Target", f"{ss_qty:.0f}")
        m2.metric("Total On Hand",       f"{total_inventory:.0f}",
                  delta=f"{total_inventory - ss_qty:+.0f} vs SS",
                  delta_color="normal")
        m3.metric("Reorder Point",       f"{rop_val:.0f}" if rop_val else "—")
        if rop_val and total_inventory > 0:
            rop_status = "✅ Above ROP" if total_inventory >= rop_val else "🔴 Below ROP — Reorder Now!"
            m4.metric("ROP Status", rop_status)
        else:
            m4.metric("ROP Status", "—")

        if not inv_df.empty:
            st.dataframe(inv_df, width="stretch", hide_index=True)
        else:
            st.info("No inventory found for this product across all warehouses.")

        if st.button("Close Compare", key="close_compare"):
            st.session_state.pop('compare_record_id', None)
            st.rerun(scope="fragment")

    except Exception as e:
        st.error(f"Could not load inventory data: {e}")
        logger.error(f"Compare panel error: {e}")



# ══════════════════════════════════════════════════════════════════════════════
# Dialog: Safety Stock Configuration (Add / Edit)
# ══════════════════════════════════════════════════════════════════════════════

@st.dialog("Safety Stock Configuration", width="large")
def safety_stock_form(mode: str = 'add', record_id=None):
    """
    Add / Edit safety stock.

    Structure:
      Tab 1 – Basic Information  (plain widgets, low rerun cost)
      Tab 2 – Demand Analysis    (demand_fetch_fragment – isolated rerun)
             – Calculation       (st.form per method – Calculate batches inputs)
             – Results + Save    (reads from dialog_data)
    """
    required_perm = 'create' if mode == 'add' else 'edit'
    if not has_permission(required_perm):
        st.error(get_permission_message(required_perm))
        return

    # ── Init dialog state ──────────────────────────────────────────────────────
    if 'initialized' not in st.session_state.dialog_data:
        st.session_state.dialog_data = {'initialized': True, 'mode': mode, 'record_id': record_id}

    existing = {}
    if mode == 'edit' and record_id:
        existing = get_safety_stock_by_id(record_id) or {}

    entities  = load_entities()
    customers = load_customers()

    if entities.empty:
        st.error("Unable to load entity data")
        return

    st.markdown(f"### {'✏️ Edit' if mode == 'edit' else '➕ Add New'} Safety Stock")

    tab1, tab2 = st.tabs(["Basic Information", "Stock Levels & Calculation"])

    # ── Tab 1: Basic Information ───────────────────────────────────────────────
    with tab1:
        col1, col2 = st.columns(2)

        with col1:
            if mode == 'add':
                product_options, product_id_map = load_all_products_for_select()
                if not product_options:
                    st.error("No products available")
                    product_id = None
                else:
                    sel_option = st.selectbox(
                        "Product * (type to search)",
                        options=product_options,
                        index=None,
                        placeholder="Type PT code or name to search...",
                        key="dlg_product_selectbox",
                        help=f"Total {len(product_options)} products available"
                    )
                    product_id = product_id_map.get(sel_option) if sel_option else None
                    if product_id:
                        st.success(f"✓ Selected: {sel_option.split(' | ')[0]}")
                    else:
                        st.warning("Please select a product")
            else:
                st.text_input(
                    "Product",
                    value=f"{existing.get('pt_code', '')} | {existing.get('product_name', '')}",
                    disabled=True
                )
                product_id = existing['product_id']

            # Entity
            entity_options = entities['company_code'] + ' - ' + entities['english_name']
            entity_idx = 0
            if mode == 'edit' and existing.get('entity_id'):
                matches = entities[entities['id'] == existing['entity_id']]
                if not matches.empty:
                    entity_idx = safe_int(matches.index[0])

            sel_entity = st.selectbox(
                "Entity *",
                options=range(len(entities)),
                format_func=lambda x: entity_options.iloc[x],
                index=entity_idx,
                key="dlg_entity",
                disabled=(mode == 'edit')
            )
            entity_id = entities.iloc[sel_entity]['id']

        with col2:
            # Customer
            customer_options = ['General Rule (All Customers)'] + \
                               (customers['company_code'] + ' - ' + customers['english_name']).tolist()
            customer_idx = 0
            if mode == 'edit' and existing.get('customer_id'):
                matches = customers[customers['id'] == existing['customer_id']]
                if not matches.empty:
                    customer_idx = safe_int(matches.index[0]) + 1

            sel_customer = st.selectbox(
                "Customer (Optional)",
                options=range(len(customer_options)),
                format_func=lambda x: customer_options[x],
                index=customer_idx,
                key="dlg_customer"
            )
            customer_id = None if sel_customer == 0 else customers.iloc[sel_customer - 1]['id']

            default_priority = 100 if customer_id is None else 50
            priority_level = st.number_input(
                "Priority Level",
                min_value=1, max_value=9999,
                value=safe_int(existing.get('priority_level', default_priority)),
                help="Lower = higher priority. Customer rules ≤ 500",
                key="dlg_priority"
            )

        col1, col2 = st.columns(2)
        with col1:
            effective_from = st.date_input(
                "Effective From *",
                value=existing.get('effective_from', datetime.now().date()),
                key="dlg_eff_from"
            )
        with col2:
            effective_to = st.date_input(
                "Effective To (Optional)",
                value=existing.get('effective_to'),
                key="dlg_eff_to"
            )

        business_notes = st.text_area(
            "Business Notes",
            value=existing.get('business_notes', ''),
            height=100,
            key="dlg_notes"
        )

    # ── Propagate context to fragment BEFORE Tab 2 renders ────────────────────
    # Fragments read product/entity from dialog_data
    st.session_state.dialog_data['product_id']  = product_id
    st.session_state.dialog_data['entity_id']   = entity_id
    st.session_state.dialog_data['customer_id'] = customer_id

    # ── Tab 2: Demand + Calculation ────────────────────────────────────────────
    with tab2:
        if mode == 'add' and not product_id:
            st.warning("Please select a product in the Basic Information tab first")
            st.stop()

        # Demand analysis – independent fragment (Fetch Data won't rerun whole dialog)
        demand_fetch_fragment()

        st.divider()
        st.markdown("#### Calculation Method")

        # Auto-select method from demand analysis if available
        ctx            = st.session_state.dialog_data
        current_method = ctx.get('selected_method', existing.get('calculation_method', 'FIXED'))

        if ctx.get('data_fetched'):
            st.info(f"✅ Method auto-selected from demand analysis: **{current_method}**")

        methods = ['FIXED', 'DAYS_OF_SUPPLY', 'LEAD_TIME_BASED']
        calculation_method = st.selectbox(
            "Select Calculation Method",
            options=methods,
            index=methods.index(current_method),
            key="dlg_calc_method"
        )
        # Persist selected method so it survives fragment reruns
        st.session_state.dialog_data['selected_method'] = calculation_method

        # Clear stale calculation results if user switched to a different method
        if ctx.get('calc_method') and ctx['calc_method'] != calculation_method:
            for stale_key in ('calculated_ss', 'calculated_rop', 'formula_used',
                              'calc_safety_days', 'calc_avg_demand', 'calc_lead_time',
                              'calc_std_dev', 'calc_sl'):
                ctx.pop(stale_key, None)
            st.info(f"ℹ️ Switched to **{calculation_method}** — previous results cleared. Please recalculate.")

        demand_stats  = ctx.get('demand_stats', {})
        has_auto_data = bool(demand_stats and demand_stats.get('data_points', 0) > 0)

        st.markdown("#### Parameters")

        # ── FIXED ──────────────────────────────────────────────────────────────
        if calculation_method == 'FIXED':
            with st.form("calc_form_fixed", border=True):
                st.caption("Enter safety stock and reorder point directly")
                col1, col2 = st.columns(2)
                with col1:
                    fixed_ss  = st.number_input(
                        "Safety Stock Quantity *", min_value=0.0, step=1.0,
                        value=safe_float(existing.get('safety_stock_qty', 0)),
                        key="form_fixed_ss"
                    )
                with col2:
                    fixed_rop = st.number_input(
                        "Reorder Point", min_value=0.0, step=1.0,
                        value=safe_float(existing.get('reorder_point', 0)),
                        key="form_fixed_rop"
                    )
                if st.form_submit_button("✔ Apply Values", type="primary"):
                    st.session_state.dialog_data.update({
                        'calculated_ss':  fixed_ss,
                        'calculated_rop': fixed_rop,
                        'calc_method':    'FIXED',
                        'formula_used':   'Manual Input'
                    })
                    st.success(f"Set → SS: **{fixed_ss:.0f}** | ROP: **{fixed_rop:.0f}**")

        # ── DAYS_OF_SUPPLY ─────────────────────────────────────────────────────
        elif calculation_method == 'DAYS_OF_SUPPLY':
            if has_auto_data:
                st.caption("📊 Fields auto-filled from historical demand analysis")

            with st.form("calc_form_dos", border=True):
                col1, col2 = st.columns(2)
                with col1:
                    dos_safety_days = st.number_input(
                        "Safety Days *", min_value=1, max_value=365,
                        value=safe_int(existing.get('safety_days', 14)),
                        help="Number of days of average demand to hold as buffer",
                        key="form_dos_safety_days"
                    )
                    dos_avg_demand = st.number_input(
                        "Avg Daily Demand" + (" ✔" if has_auto_data else ""),
                        min_value=0.0, step=0.1,
                        value=safe_float(
                            demand_stats.get('avg_daily_demand', 0) if has_auto_data
                            else existing.get('avg_daily_demand', 0)
                        ),
                        key="form_dos_avg_demand"
                    )
                with col2:
                    dos_lead_time = st.number_input(
                        "Lead Time (days)" + (" ✔" if has_auto_data and 'lead_time_days' in ctx else ""),
                        min_value=1, max_value=365,
                        value=safe_int(
                            ctx.get('lead_time_days', 7) if has_auto_data
                            else existing.get('lead_time_days', 7)
                        ),
                        key="form_dos_lead_time"
                    )

                if st.form_submit_button("🔢 Calculate Safety Stock & Reorder Point", type="primary"):
                    result = calculate_safety_stock(
                        method='DAYS_OF_SUPPLY',
                        safety_days=dos_safety_days,
                        avg_daily_demand=dos_avg_demand,
                        lead_time_days=dos_lead_time
                    )
                    if 'error' not in result:
                        st.session_state.dialog_data.update({
                            'calculated_ss':     result['safety_stock_qty'],
                            'calculated_rop':    result['reorder_point'],
                            'formula_used':      result['formula_used'],
                            'calc_method':       'DAYS_OF_SUPPLY',
                            'calc_safety_days':  dos_safety_days,
                            'calc_avg_demand':   dos_avg_demand,
                            'calc_lead_time':    dos_lead_time
                        })
                    else:
                        st.error(result['error'])

        # ── LEAD_TIME_BASED ────────────────────────────────────────────────────
        elif calculation_method == 'LEAD_TIME_BASED':
            if has_auto_data:
                st.caption("📊 Fields auto-filled from historical demand analysis")

            service_level_options = list(Z_SCORE_MAP.keys())
            current_sl = existing.get('service_level_percent', 95.0)
            sl_default_idx = service_level_options.index(current_sl) if current_sl in service_level_options else 4

            with st.form("calc_form_ltb", border=True):
                col1, col2 = st.columns(2)
                with col1:
                    ltb_lead_time = st.number_input(
                        "Lead Time (days) *" + (" ✔" if has_auto_data and 'lead_time_days' in ctx else ""),
                        min_value=1, max_value=365,
                        value=safe_int(
                            ctx.get('lead_time_days', 7) if has_auto_data
                            else existing.get('lead_time_days', 7)
                        ),
                        key="form_ltb_lead_time"
                    )
                    ltb_service_level = st.selectbox(
                        "Service Level % *",
                        options=service_level_options,
                        index=sl_default_idx,
                        key="form_ltb_sl"
                    )
                with col2:
                    ltb_std_dev = st.number_input(
                        "Demand Std Deviation" + (" ✔" if has_auto_data else ""),
                        min_value=0.0, step=0.1,
                        value=safe_float(
                            demand_stats.get('demand_std_dev', 0) if has_auto_data
                            else existing.get('demand_std_deviation', 0)
                        ),
                        key="form_ltb_std_dev"
                    )
                    ltb_avg_demand = st.number_input(
                        "Avg Daily Demand" + (" ✔" if has_auto_data else ""),
                        min_value=0.0, step=0.1,
                        value=safe_float(
                            demand_stats.get('avg_daily_demand', 0) if has_auto_data
                            else existing.get('avg_daily_demand', 0)
                        ),
                        key="form_ltb_avg_demand"
                    )

                if st.form_submit_button("🔢 Calculate Safety Stock & Reorder Point", type="primary"):
                    result = calculate_safety_stock(
                        method='LEAD_TIME_BASED',
                        lead_time_days=ltb_lead_time,
                        service_level_percent=ltb_service_level,
                        demand_std_deviation=ltb_std_dev,
                        avg_daily_demand=ltb_avg_demand
                    )
                    if 'error' not in result:
                        st.session_state.dialog_data.update({
                            'calculated_ss':      result['safety_stock_qty'],
                            'calculated_rop':     result['reorder_point'],
                            'formula_used':       result['formula_used'],
                            'calc_method':        'LEAD_TIME_BASED',
                            'calc_lead_time':     ltb_lead_time,
                            'calc_sl':            ltb_service_level,
                            'calc_std_dev':       ltb_std_dev,
                            'calc_avg_demand':    ltb_avg_demand
                        })
                    else:
                        st.error(result['error'])

        # ── Calculation results display ────────────────────────────────────────
        if 'calculated_ss' in ctx:
            st.divider()
            st.markdown("**Calculation Results**")
            rc1, rc2 = st.columns(2)
            with rc1:
                st.success(f"✔ Safety Stock: **{ctx['calculated_ss']:.2f}** units")
            with rc2:
                st.success(f"✔ Reorder Point: **{ctx['calculated_rop']:.2f}** units")
            if 'formula_used' in ctx:
                st.caption(f"Formula: {ctx['formula_used']}")

    # ── Save / Cancel (outside tabs, at dialog level) ─────────────────────────
    st.divider()

    # Calculation result summary always visible near Save
    ctx = st.session_state.dialog_data
    if 'calculated_ss' in ctx:
        saved_m = ctx.get('calc_method', '—')
        abbrev  = {'FIXED': 'FIXED', 'DAYS_OF_SUPPLY': 'DOS', 'LEAD_TIME_BASED': 'LTB'}.get(saved_m, saved_m)
        sum_cols = st.columns(4)
        sum_cols[0].metric("Calculated SS",    f"{ctx['calculated_ss']:.2f}")
        sum_cols[1].metric("Reorder Point",    f"{ctx['calculated_rop']:.2f}")
        sum_cols[2].metric("Method Used",      abbrev)
        if 'formula_used' in ctx:
            sum_cols[3].caption(f"Formula: {ctx['formula_used']}")

        # Warn if dropdown method doesn't match calculated method
        if ctx.get('calc_method') and ctx['calc_method'] != calculation_method:
            st.warning(
                f"⚠️ Method mismatch: results are from **{ctx['calc_method']}** "
                f"but dropdown is set to **{calculation_method}**. "
                f"Please recalculate before saving."
            )
    else:
        st.info("ℹ️ Use the Calculate / Apply Values button in the *Stock Levels & Calculation* tab, then save.")

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("💾 Save", type="primary", width="stretch", key="dlg_save"):
            _save_safety_stock(
                mode=mode,
                record_id=record_id,
                product_id=product_id,
                entity_id=entity_id,
                customer_id=customer_id,
                calculation_method=calculation_method,
                effective_from=effective_from,
                effective_to=effective_to,
                priority_level=priority_level,
                business_notes=business_notes
            )

    with col2:
        if st.button("✖ Cancel", width="stretch", key="dlg_cancel"):
            st.session_state.dialog_data = {}
            st.rerun()

    with col3:
        if mode == 'edit' and has_permission('review'):
            if st.button("📋 Create Review", width="stretch", key="dlg_review"):
                review_dialog(record_id)


def _save_safety_stock(mode, record_id, product_id, entity_id, customer_id,
                       calculation_method, effective_from, effective_to,
                       priority_level, business_notes):
    """
    Builds data dict from dialog_data + current widget values, validates, saves.
    Separated to keep safety_stock_form readable.
    """
    if mode == 'add' and not product_id:
        st.error("Please select a product before saving")
        return

    ctx = st.session_state.dialog_data

    # SS qty and ROP come from the calculation result stored in dialog_data
    safety_stock_qty = safe_float(ctx.get('calculated_ss'))
    reorder_point    = safe_float(ctx.get('calculated_rop')) or None

    if safety_stock_qty == 0 and 'calculated_ss' not in ctx:
        st.error("Please use the Calculate / Apply Values button before saving")
        return

    # Guard: method selected in widget must match what was actually calculated.
    # Prevents saving LEAD_TIME_BASED method with FIXED calculation results
    # (e.g. user changed method dropdown without recalculating).
    saved_method = ctx.get('calc_method', calculation_method)
    if saved_method != calculation_method:
        st.error(
            f"⚠️ Method mismatch: you selected **{calculation_method}** but the last "
            f"calculation used **{saved_method}**. "
            f"Please recalculate with the selected method before saving."
        )
        return
    calc_params  = {'calculation_method': saved_method}

    if saved_method == 'DAYS_OF_SUPPLY':
        calc_params.update({
            'safety_days':     ctx.get('calc_safety_days'),
            'avg_daily_demand': ctx.get('calc_avg_demand'),
            'lead_time_days':  ctx.get('calc_lead_time'),
            'formula_used':    ctx.get('formula_used'),
        })
    elif saved_method == 'LEAD_TIME_BASED':
        calc_params.update({
            'lead_time_days':        ctx.get('calc_lead_time'),
            'service_level_percent': ctx.get('calc_sl'),
            'demand_std_deviation':  ctx.get('calc_std_dev'),
            'avg_daily_demand':      ctx.get('calc_avg_demand'),
            'formula_used':          ctx.get('formula_used'),
        })

    data = {
        'product_id':       product_id,
        'entity_id':        entity_id,
        'customer_id':      customer_id,
        'safety_stock_qty': safety_stock_qty,
        'reorder_point':    reorder_point,
        'effective_from':   effective_from,
        'effective_to':     effective_to if effective_to else None,
        'priority_level':   priority_level,
        'business_notes':   business_notes if business_notes else None,
        'is_active':        1,
        **calc_params
    }

    is_valid, errors = validate_safety_stock_data(
        data, mode=mode,
        exclude_id=record_id if mode == 'edit' else None
    )

    if not is_valid:
        st.error("**Validation failed — please fix the following issues:**")
        for err in errors:
            st.markdown(f"- {err}")
        return

    if mode == 'add':
        success, result = create_safety_stock(data, st.session_state.username)
        log_action('CREATE', f"Created safety stock for product {product_id}")
    else:
        success, result = update_safety_stock(record_id, data, st.session_state.username)
        log_action('UPDATE', f"Updated safety stock ID {record_id}")

    if success:
        st.session_state.dialog_data = {}
        st.success(f"{'Created' if mode == 'add' else 'Updated'} successfully!")
        st.cache_data.clear()
        st.rerun()   # full app rerun so table refreshes
    else:
        st.error(f"Error: {result}")


# ══════════════════════════════════════════════════════════════════════════════
# Dialog: Review Safety Stock
# ══════════════════════════════════════════════════════════════════════════════

@st.dialog("Review Safety Stock", width="large")
def review_dialog(safety_stock_id):
    """
    Review dialog – quantity input is outside the form so auto_action
    can react to it before form submission.
    """
    if not has_permission('review'):
        st.error(get_permission_message('review'))
        return

    current_data = get_safety_stock_by_id(safety_stock_id)
    if not current_data:
        st.error("Record not found")
        return

    st.markdown("### 📋 Safety Stock Review")

    # ── Current info ──────────────────────────────────────────────────────────
    ci1, ci2, ci3, ci4 = st.columns(4)
    with ci1:
        st.metric("Product",     current_data.get('pt_code', 'N/A'))
    with ci2:
        st.metric("Entity",      current_data.get('entity_name', 'N/A')[:20])
    with ci3:
        st.metric("Current SS",  f"{safe_float(current_data.get('safety_stock_qty')):.0f}")
    with ci4:
        st.metric("Method",      current_data.get('calculation_method', 'FIXED'))

    with st.expander("View Full Settings", expanded=False):
        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.write(f"**Reorder Point:** {safe_float(current_data.get('reorder_point', 0)):.0f}")
            st.write(f"**Effective From:** {current_data.get('effective_from')}")
            st.write(f"**Priority:** {current_data.get('priority_level')}")
            if current_data.get('formula_used'):
                st.write(f"**Formula:** {current_data['formula_used']}")
        with info_col2:
            st.write(f"**Effective To:** {current_data.get('effective_to') or 'Ongoing'}")
            st.write(f"**Customer:** {current_data.get('customer_name') or 'General Rule'}")
            if current_data.get('last_calculated_date'):
                st.write(f"**Last Calculated:** {current_data['last_calculated_date']}")

    st.info(
        "ℹ️ If you need to recalculate safety stock with a new method, "
        "close this dialog and use **Edit** instead."
    )

    st.divider()
    st.subheader("Review Decision")

    old_qty = safe_float(current_data.get('safety_stock_qty'))

    # ── New quantity OUTSIDE form so auto_action updates reactively ───────────
    new_qty = st.number_input(
        "New Safety Stock Quantity *",
        min_value=0.0, step=1.0, value=old_qty,
        help="Adjust quantity based on performance review",
        key="rv_new_qty"
    )

    # Auto-detect action from current widget value (updates live, before submit)
    if new_qty > old_qty:
        auto_action = 'INCREASED'
        change_val  = new_qty - old_qty
        pct         = (change_val / old_qty * 100) if old_qty > 0 else 0
        st.success(f"↑ Increase: +{change_val:.0f} units (+{pct:.1f}%)")
    elif new_qty < old_qty:
        auto_action = 'DECREASED'
        change_val  = new_qty - old_qty
        pct         = (change_val / old_qty * 100) if old_qty > 0 else 0
        st.warning(f"↓ Decrease: {change_val:.0f} units ({pct:.1f}%)")
    else:
        auto_action = 'NO_CHANGE'
        st.info("No quantity change — documenting review only.")

    # ── Rest of inputs in form ────────────────────────────────────────────────
    with st.form("review_form", border=True):
        col1, col2 = st.columns(2)

        with col1:
            action_options = ['NO_CHANGE', 'INCREASED', 'DECREASED', 'METHOD_CHANGED']
            action_taken = st.selectbox(
                "Action *",
                options=action_options,
                index=action_options.index(auto_action),
                help="Auto-detected from quantity change above — adjust if needed",
                key="rv_action"
            )
            review_type = st.selectbox(
                "Review Type",
                options=['PERIODIC', 'EXCEPTION', 'EMERGENCY', 'ANNUAL'],
                help="What triggered this review?",
                key="rv_type"
            )

        with col2:
            action_reason = st.text_area(
                "Reason for Change *",
                height=130,
                placeholder="Example: Had 3 stockouts last month due to increased demand...",
                help="⚠️ REQUIRED – minimum 10 characters",
                key="rv_reason"
            )

        review_notes = st.text_area(
            "Additional Notes (Optional)",
            height=70,
            key="rv_notes"
        )

        approve_review = False
        if has_permission('approve'):
            approve_review = st.checkbox("✅ Approve this review", key="rv_approve")

        sub_col1, sub_col2 = st.columns([3, 1])
        with sub_col1:
            submitted = st.form_submit_button(
                "✅ Submit Review", type="primary", width="stretch"
            )
        with sub_col2:
            cancelled = st.form_submit_button("✖ Cancel", width="stretch")

    if cancelled:
        st.rerun()

    # Process submit
    if submitted:
        if not action_reason or len(action_reason.strip()) < 10:
            st.error("⚠️ Please provide a meaningful reason (at least 10 characters)")
            return

        if action_taken == 'INCREASED' and new_qty <= old_qty:
            st.error("Action is INCREASED but new quantity is not greater than current quantity.")
            return
        elif action_taken == 'DECREASED' and new_qty >= old_qty:
            st.error("Action is DECREASED but new quantity is not less than current quantity.")
            return

        review_data = {
            'review_date':          datetime.now().date(),
            'review_type':          review_type,
            'old_safety_stock_qty': old_qty,
            'new_safety_stock_qty': new_qty,
            'action_taken':         action_taken,
            'action_reason':        action_reason.strip(),
            'review_notes':         review_notes.strip() if review_notes else None,
            'approved_by':          st.session_state.username if approve_review else None
        }

        success, message = create_safety_stock_review(
            safety_stock_id, review_data, st.session_state.username
        )

        if success:
            if new_qty != old_qty:
                update_safety_stock(
                    safety_stock_id,
                    {'safety_stock_qty': new_qty},
                    st.session_state.username
                )
            log_action('REVIEW', f"Reviewed safety stock ID {safety_stock_id}")
            st.success("✅ Review submitted successfully!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(f"⚠️ Error: {message}")


# ══════════════════════════════════════════════════════════════════════════════
# Dialog: Bulk Upload
# ══════════════════════════════════════════════════════════════════════════════

@st.dialog("Bulk Upload", width="large")
def bulk_upload_dialog():
    if not has_permission('bulk_upload'):
        st.error(get_permission_message('bulk_upload'))
        return

    st.markdown("### Bulk Upload Safety Stock")

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Download Template", width="stretch"):
            template = create_upload_template(include_sample_data=True)
            st.download_button(
                label="Save Template",
                data=template,
                file_name=f"safety_stock_template_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch"
            )

    st.divider()

    uploaded_file = st.file_uploader("Choose Excel file", type=['xlsx', 'xls'])

    if not uploaded_file:
        return

    try:
        with st.spinner("Reading file..."):
            df = pd.read_excel(uploaded_file)

        # Skip header row if it contains field descriptions
        if df.iloc[0].astype(str).str.contains('Required|Optional').any():
            df = df.iloc[1:].reset_index(drop=True)

        st.info(f"Found {len(df)} rows")
        st.dataframe(df.head(10), width="stretch")

        with st.spinner("Validating..."):
            is_valid, validated_df, errors = validate_bulk_data(df)

        if not is_valid:
            st.error("Validation failed:")
            for error in errors[:10]:
                st.write(f"• {error}")
            return

        st.success(f"✔ Validation passed – {len(validated_df)} valid rows ready to import")

        with st.form("bulk_import_form", border=False):
            st.write("Review the data above, then confirm import:")
            if st.form_submit_button("Import Data", type="primary", width="stretch"):
                with st.spinner("Importing..."):
                    data_list = validated_df.to_dict('records')
                    success, message, results = bulk_create_safety_stock(
                        data_list, st.session_state.username
                    )

                if success:
                    log_action('BULK_UPLOAD', f"Uploaded {results['created']} records")
                    st.success(message)
                    if results['failed'] > 0:
                        with st.expander(f"⚠️ {results['failed']} errors"):
                            for err in results['errors']:
                                st.write(f"• {err}")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Failed: {message}")

    except Exception as e:
        st.error(f"Error reading file: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

@st.fragment
def render_analysis_section():
    """Proxy — delegates to utils.safety_stock.analysis (separated for maintainability)"""
    from utils.safety_stock.analysis import render_analysis_section as _render
    _render()


def render_help_popover():
    """Proxy — delegates to utils.safety_stock.help (separated for maintainability)"""
    from utils.safety_stock.help import render_help_popover as _render
    _render()


def main():
    # ── Header ─────────────────────────────────────────────────────────────────
    col_title, col_help, col_user = st.columns([3, 1, 1])
    with col_title:
        st.title("🛡️ Safety Stock Management")
    with col_help:
        render_help_popover()
    with col_user:
        st.caption(get_user_info_display())

    # ── Stats (independent fragment – filter changes don't rerun this) ─────────
    render_stats()

    st.divider()

    # ── Data section (fragment – filter changes rerun only this block) ─────────
    render_data_section()

    # ── Analysis section (independent fragment) ────────────────────────────────
    render_analysis_section()


if __name__ == "__main__":
    main()