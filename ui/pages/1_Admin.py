"""
Admin HITL Panel — Pending Credit Approvals.

Accessible via the Streamlit sidebar navigation as a second page.
Protected by a simple password gate.

Approve:  sets status='APPROVED' and deducts amount from billing_accounts.current_balance
Reject:   sets status='REJECTED', balance unchanged
"""
import os
import sys
import sqlite3
import streamlit as st
from datetime import datetime
import io
import csv
import json

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'telecom_ops.db')
ADMIN_PASSWORD = "admin123"  # Replace with env var in production

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Admin — Prodapt AI Ops",
    page_icon="🔐",
    layout="wide"
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .admin-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border: 1px solid rgba(255,100,100,0.3);
        border-radius: 12px;
        padding: 24px 32px;
        margin-bottom: 28px;
    }
    .admin-header h1 { color: #ff6b6b; margin: 0; font-size: 1.8rem; }
    .admin-header p  { color: #a0a0b0; margin: 6px 0 0; font-size: 0.95rem; }

    .badge-pending  { background:#ff6b6b22; color:#ff6b6b; border:1px solid #ff6b6b55;
                      padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
    .badge-approved { background:#51cf6622; color:#51cf66; border:1px solid #51cf6655;
                      padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
    .badge-rejected { background:#adb5bd22; color:#adb5bd; border:1px solid #adb5bd55;
                      padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }

    .credit-card {
        background: linear-gradient(135deg, #1e1e2e, #16213e);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 14px;
        transition: border-color 0.2s;
    }
    .credit-card:hover { border-color: rgba(255,107,107,0.4); }

    .credit-amount { font-size: 1.6rem; font-weight:700; color:#ff6b6b; }
    .credit-meta   { font-size: 0.85rem; color:#8888aa; margin-top:4px; }
    .credit-reason { color:#c8c8e0; font-size:0.95rem; margin:8px 0; }
    .credit-ref    { font-family:monospace; font-size:0.8rem; color:#6666aa;
                     background:#ffffff08; padding:2px 8px; border-radius:4px; }

    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(135deg, #37b24d, #2f9e44);
        border: none; border-radius: 8px; font-weight: 600;
    }
    div[data-testid="stButton"] button[kind="secondary"] {
        border-radius: 8px; font-weight: 600;
    }

    .empty-state {
        text-align: center; padding: 60px 20px;
        color: #555577;
    }
    .empty-state .icon { font-size: 3rem; }
    .empty-state h3    { color: #7777aa; margin-top:12px; }

    .stat-box {
        background: #1e1e2e; border:1px solid rgba(255,255,255,0.07);
        border-radius:10px; padding:16px 20px; text-align:center;
    }
    .stat-num  { font-size:2rem; font-weight:700; }
    .stat-label{ font-size:0.8rem; color:#8888aa; margin-top:2px; }
</style>
""", unsafe_allow_html=True)

# ── DB Helpers ────────────────────────────────────────────────────────────────
def get_pending_credits():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT credit_id, customer_id, amount, reason, reference_number, applied_at "
        "FROM billing_credits WHERE status = 'PENDING_APPROVAL' ORDER BY applied_at ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    stats = {}
    stats["pending"]  = conn.execute("SELECT COUNT(*) FROM billing_credits WHERE status='PENDING_APPROVAL'").fetchone()[0]
    stats["approved"] = conn.execute("SELECT COUNT(*) FROM billing_credits WHERE status='APPROVED'").fetchone()[0]
    stats["rejected"] = conn.execute("SELECT COUNT(*) FROM billing_credits WHERE status='REJECTED'").fetchone()[0]
    stats["total_pending_value"] = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM billing_credits WHERE status='PENDING_APPROVAL'"
    ).fetchone()[0]
    conn.close()
    return stats

def approve_credit(credit_id: int, customer_id: str, amount: float):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE billing_credits SET status='APPROVED' WHERE credit_id=?", (credit_id,)
    )
    conn.execute(
        "UPDATE billing_accounts SET current_balance = current_balance - ? WHERE customer_id=?",
        (amount, customer_id)
    )
    # Change the description to show it was refunded and clear the flag
    conn.execute(
        "UPDATE billing_charges "
        "SET is_duplicate_flag = 0, "
        "    description = REPLACE(description, '(duplicate)', '(REFUNDED)') "
        "WHERE customer_id=? AND amount=? AND (is_duplicate_flag=1 OR description LIKE '%(duplicate)%')",
        (customer_id, amount)
    )
    conn.commit()
    conn.close()

def reject_credit(credit_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE billing_credits SET status='REJECTED' WHERE credit_id=?", (credit_id,)
    )
    conn.commit()
    conn.close()

# ── Session state ─────────────────────────────────────────────────────────────
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

# ── Password Gate ─────────────────────────────────────────────────────────────
if not st.session_state.admin_authenticated:
    st.markdown("""
    <div class="admin-header">
        <h1>🔐 Admin Portal</h1>
        <p>Prodapt AI Operations Center — Restricted Access</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("#### Enter Admin Password")
        pwd = st.text_input("Password", type="password", placeholder="••••••••", label_visibility="collapsed")
        if st.button("Sign In", type="primary", use_container_width=True):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password. Access denied.")
    st.stop()

# ── Authenticated Admin View ──────────────────────────────────────────────────
st.markdown("""
<div class="admin-header">
    <h1>🔐 Admin — Pending Credit Approvals</h1>
    <p>Review and action billing credits flagged for manual approval (credits over $50).</p>
</div>
""", unsafe_allow_html=True)

# Logout
if st.button("Sign Out", type="secondary"):
    st.session_state.admin_authenticated = False
    st.rerun()

# --- Sidebar admin actions: refresh, export, clear filters ---
with st.sidebar.expander("Admin Actions", expanded=True):
    if st.button("Refresh data", use_container_width=True):
        st.experimental_rerun()

    # Prepare CSV for download
    _rows_for_export = get_pending_credits()
    sio = io.StringIO()
    writer = csv.writer(sio)
    writer.writerow(["credit_id", "customer_id", "amount", "reason", "reference_number", "applied_at"])
    for r in _rows_for_export:
        writer.writerow([r.get("credit_id"), r.get("customer_id"), r.get("amount"), r.get("reason"), r.get("reference_number"), r.get("applied_at")])

    st.download_button("Export pending (CSV)", data=sio.getvalue(), file_name="pending_credits.csv", mime="text/csv")

    if st.button("Clear saved filters", use_container_width=True):
        for k in ("filter_customer", "filter_min"):
            if k in st.session_state:
                del st.session_state[k]
        st.experimental_rerun()

    st.markdown("---")
    st.caption("Use filters on the main page to narrow the pending queue.")

st.divider()

# ── Stats Row ─────────────────────────────────────────────────────────────────
stats = get_stats()
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(f"""
    <div class="stat-box">
        <div class="stat-num" style="color:#ff6b6b">{stats['pending']}</div>
        <div class="stat-label">Pending Review</div>
    </div>""", unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="stat-box">
        <div class="stat-num" style="color:#ff6b6b">${stats['total_pending_value']:.2f}</div>
        <div class="stat-label">Total Pending Value</div>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="stat-box">
        <div class="stat-num" style="color:#51cf66">{stats['approved']}</div>
        <div class="stat-label">Approved (All Time)</div>
    </div>""", unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="stat-box">
        <div class="stat-num" style="color:#adb5bd">{stats['rejected']}</div>
        <div class="stat-label">Rejected (All Time)</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Pending Credits Queue ─────────────────────────────────────────────────────
# Filters
filter_col, amt_col, _ = st.columns([2, 1, 7])
with filter_col:
    filter_customer = st.text_input("Filter by customer ID", key="filter_customer")
with amt_col:
    filter_min = st.number_input("Minimum amount", min_value=0.0, value=st.session_state.get("filter_min", 0.0), key="filter_min", format="%.2f")

pending = get_pending_credits()
filtered = [p for p in pending if (filter_customer.lower() in p["customer_id"].lower() if filter_customer else True) and p["amount"] >= filter_min]

if not filtered:
    st.markdown("""
    <div class="empty-state">
        <div class="icon">✅</div>
        <h3>No matching items</h3>
        <p>No pending credits match your filters.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"### Pending Queue &nbsp; <span class='badge-pending'>{len(filtered)} items</span>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    for credit in filtered:
        credit_id   = credit["credit_id"]
        customer_id = credit["customer_id"]
        amount      = credit["amount"]
        reason      = credit["reason"]
        ref         = credit["reference_number"] or "—"
        submitted   = credit["applied_at"]

        # Format date nicely
        try:
            dt = datetime.strptime(submitted, "%Y-%m-%d %H:%M:%S")
            submitted_fmt = dt.strftime("%d %b %Y, %I:%M %p")
        except Exception:
            submitted_fmt = submitted

        with st.container():
            st.markdown(f"""
            <div class="credit-card">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                        <span style="color:#8888cc; font-size:0.85rem; font-weight:600;">CUSTOMER</span>
                        <div style="font-size:1.1rem; font-weight:700; color:#e0e0ff; margin-top:2px;">{customer_id}</div>
                    </div>
                    <div class="credit-amount">${amount:.2f}</div>
                </div>
                <div class="credit-reason">📝 {reason}</div>
                <div class="credit-meta">
                    <span class="credit-ref">{ref}</span>
                    &nbsp;·&nbsp; Submitted: {submitted_fmt}
                    &nbsp;·&nbsp; ID: #{credit_id}
                </div>
            </div>
            """, unsafe_allow_html=True)

            btn_col1, btn_col2, spacer = st.columns([1, 1, 5])
            with btn_col1:
                if st.button(f"✅  Approve", key=f"approve_{credit_id}", type="primary", use_container_width=True):
                    approve_credit(credit_id, customer_id, amount)
                    st.toast(f"✅ Credit ${amount:.2f} approved for {customer_id}. Balance updated.", icon="✅")
                    st.rerun()
            with btn_col2:
                if st.button(f"❌  Reject", key=f"reject_{credit_id}", type="secondary", use_container_width=True):
                    reject_credit(credit_id)
                    st.toast(f"❌ Credit #{credit_id} rejected.", icon="❌")
                    st.rerun()

            # Details for power users
            with st.expander("Details (JSON)"):
                st.code(json.dumps(credit, indent=2), language="json")

        st.markdown("")  # spacing
