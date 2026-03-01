# app.py
"""
FA Data Hub - Finance & Accounting Data Management
Main Entry Point

"""

import streamlit as st
from utils.auth import AuthManager
from utils.db import check_db_connection
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== PAGE CONFIGURATION ====================

APP_NAME = "FA Data Hub"
APP_ICON = "💰"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Finance & Accounting Data Management Platform"

st.set_page_config(
    page_title=f"{APP_NAME} - iSCM",
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CUSTOM CSS ====================

st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
        color: #2e7d32;
    }
    
    .sub-header {
        font-size: 1.1rem;
        color: #666;
        margin-bottom: 2rem;
    }
    
    .welcome-box {
        background: linear-gradient(135deg, #2e7d32 0%, #43a047 100%);
        color: white;
        padding: 2rem;
        border-radius: 0.75rem;
        margin-bottom: 2rem;
    }
    
    .welcome-title {
        font-size: 1.75rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    
    .welcome-subtitle {
        opacity: 0.9;
        font-size: 1rem;
    }
    
    .info-card {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #2e7d32;
        margin-bottom: 1rem;
    }
    
    .footer {
        text-align: center;
        color: #888;
        padding: 1rem;
        margin-top: 3rem;
        border-top: 1px solid #eee;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# ==================== INITIALIZATION ====================

auth = AuthManager()

# ==================== HELPER FUNCTIONS ====================

def show_login_page():
    """Display the login page"""
    st.markdown(f'<p class="main-header">{APP_ICON} {APP_NAME}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="sub-header">{APP_DESCRIPTION}</p>', unsafe_allow_html=True)
    
    # Check database connection
    db_ok, db_error = check_db_connection()
    if not db_ok:
        st.error(f"⚠️ {db_error}")
        st.info("Please check your network connection or contact IT support.")
        return
    
    # Center the login form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form", clear_on_submit=False):
            st.markdown("#### 🔐 Login")
            
            username = st.text_input(
                "Username",
                placeholder="Enter your username",
                key="login_username"
            )
            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter your password",
                key="login_password"
            )
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submit = st.form_submit_button(
                    "🔑 Login",
                    type="primary",
                    use_container_width=True
                )
            with col_btn2:
                st.form_submit_button(
                    "🔄 Clear",
                    use_container_width=True
                )
            
            if submit:
                if not username or not password:
                    st.warning("Please enter both username and password")
                else:
                    with st.spinner("Authenticating..."):
                        success, result = auth.authenticate(username, password)
                    
                    if success:
                        auth.login(result)
                        st.success("✅ Login successful!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(result.get("error", "Authentication failed"))
        
        with st.expander("ℹ️ Need Help?"):
            st.info("""
            - Use your iSCM credentials to login
            - Contact IT support if you forgot your password
            - Session expires after 8 hours of inactivity
            """)


def show_main_app():
    """Display the main application after login"""
    
    # Sidebar
    with st.sidebar:
        st.markdown(f"### 👤 {auth.get_user_display_name()}")
        
        # Access level indicator
        access_level = st.session_state.get('user_role', 'viewer')
        if access_level in ['admin', 'GM', 'MD']:
            st.success("🔓 Full Access")
        elif access_level in ['fa_manager', 'accountant']:
            st.info("📋 FA Access")
        else:
            st.warning("👤 Limited Access")
        
        st.caption(f"Role: {access_level}")
        st.markdown("---")
        
        # Logout
        if st.button("🚪 Logout", use_container_width=True):
            auth.logout()
            st.rerun()
    
    # Main content - Welcome
    st.markdown(f"""
    <div class="welcome-box">
        <div class="welcome-title">Welcome, {auth.get_user_display_name()}! 👋</div>
        <div class="welcome-subtitle">Select a module from the sidebar menu to get started.</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Available modules info
    st.markdown("### 📊 Available Modules")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="info-card">
            <strong>📋 ERP Data Verification</strong><br>
            <span style="color: #666;">Review and verify financial data from ERP system — AR/AP balances, journal entries, and transaction records.</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="info-card">
            <strong>🔄 MISA Data Interaction</strong><br>
            <span style="color: #666;">Sync, compare, and reconcile data between ERP and MISA accounting software.</span>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="info-card">
            <strong>📊 Financial Reports</strong><br>
            <span style="color: #666;">Generate and review financial statements, trial balances, and management reports.</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="info-card">
            <strong>✅ Data Reconciliation</strong><br>
            <span style="color: #666;">Cross-check ERP vs MISA entries, identify discrepancies, and track resolution status.</span>
        </div>
        """, unsafe_allow_html=True)
    
    # Coming soon note
    st.markdown("#### 🔜 Coming Soon")
    st.caption("Tax report automation, bank reconciliation, inter-company elimination, audit trail dashboard...")
    
    # System Status (Admin only)
    if auth.is_admin():
        st.markdown("---")
        with st.expander("🔧 System Status (Admin Only)"):
            from utils.db import get_connection_pool_status
            pool_status = get_connection_pool_status()
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("DB Status", pool_status.get("status", "OK"))
            with col2:
                st.metric("Connections Used", pool_status.get("checked_out", 0))
            with col3:
                st.metric("Available", pool_status.get("checked_in", 0))
    
    # Footer
    st.markdown(f"""
    <div class="footer">
        <strong>{APP_NAME}</strong> v{APP_VERSION} | Part of iSCM System | © 2025 ProsTech
    </div>
    """, unsafe_allow_html=True)


# ==================== MAIN ====================

def main():
    """Main application entry point"""
    if not auth.check_session():
        show_login_page()
    else:
        show_main_app()


if __name__ == "__main__":
    main()