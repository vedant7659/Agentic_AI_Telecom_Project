import os
import sys
import httpx
import streamlit as st
import io
import json
from datetime import datetime

# Add the project root to sys.path so we can import from orchestration
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from orchestration.graph import run_telecom_assistant

# --- Page Configuration ---
st.set_page_config(
    page_title="Prodapt AI Operations Center",
    page_icon="📡",
    layout="wide"
)

# --- Sidebar Functions ---
def check_db_status():
    if os.path.exists("data/telecom_ops.db"):
        st.sidebar.success("DB: Ready")
    else:
        st.sidebar.error("DB: Not found — run init_db.py")

def check_vector_index():
    if os.path.exists("data/vector_index") and os.listdir("data/vector_index"):
        st.sidebar.success("Vector Index: Ready")
    else:
        st.sidebar.info("Vector Index: Will be built on first RAG query")

def check_adk_service(port: int) -> bool:
    try:
        # A simple HTTP GET to check if the port is responding
        resp = httpx.get(f"http://localhost:{port}/", timeout=2.0)
        # Even if it returns 404 for root, the server is up. 
        # For A2A, we might check a specific endpoint, but catching any response is usually enough to know it's alive.
        return True
    except httpx.RequestError:
        return False

# --- Render Sidebar ---
st.sidebar.title("System Status")
check_db_status()
check_vector_index()

st.sidebar.markdown("---")
network_ok = check_adk_service(8001)
billing_ok = check_adk_service(8002)

st.sidebar.write("Network Diagnostics ADK:", "🟢 Running" if network_ok else "🔴 Not running")
st.sidebar.write("Billing Resolution ADK: ", "🟢 Running" if billing_ok else "🔴 Not running")

if not network_ok or not billing_ok:
    st.sidebar.warning(
        "One or more ADK services are offline.\n\n"
        "Start them in separate terminals:\n\n"
        "`python adk-services/network_diagnostics/agent.py`\n\n"
        "`python adk-services/billing_resolution/agent.py`"
    )

st.sidebar.markdown("---")
st.sidebar.markdown("### Framework Map")
st.sidebar.markdown("""
| Capability | Framework |
|---|---|
| Policy FAQ | LlamaIndex RAG |
| SQL Analytics | LlamaIndex Semantic SQL |
| Diagnostics | Google ADK |
| Billing | Google ADK |
| Comms Draft | CrewAI |
| Routing | LangGraph |
""")

# --- Main Content Area ---
st.title("Prodapt AI Operations Center")
st.caption("Powered by LangGraph · LlamaIndex · Google ADK · CrewAI")

# --- Session State ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_prompt" not in st.session_state:
    st.session_state.last_prompt = None

# --- Chat History Display ---
for msg in st.session_state.messages:
    ts = msg.get("timestamp")
    label = f"{msg['role']}" + (f" • {ts}" if ts else "")
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # Display trace if it exists
        if msg.get("trace"):
            with st.expander("🔍 View Agent Execution Trace"):
                for i, step in enumerate(msg["trace"], 1):
                    st.markdown(f"**Step {i} | {step.get('worker', 'UnknownWorker')}**")
                    output = step.get('output', '')
                    truncated = output[:200] + "..." if len(output) > 200 else output
                    st.code(truncated, language=None)
                    st.divider()

# --- Chat Input & Logic ---
def _timestamp():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

def process_prompt(prompt: str):
    if not prompt:
        return
    st.session_state.last_prompt = prompt

    # Append user message
    st.session_state.messages.append({"role": "user", "content": prompt, "timestamp": _timestamp()})

    # Render assistant response
    with st.chat_message("assistant"):
        with st.spinner("Multi-agent system processing your inquiry..."):
            try:
                result = run_telecom_assistant(st.session_state.messages)
                st.session_state.last_result = result
                final_response = result.get("final_response", "No response generated.")
            except Exception:
                final_response = "An unexpected error occurred while processing your request. Please try again or contact support if the problem persists."
                st.error(final_response)
                st.session_state.last_result = None

        st.markdown(final_response)

    trace = st.session_state.last_result.get("execution_trace", []) if st.session_state.last_result else []
    st.session_state.messages.append({
        "role": "assistant",
        "content": final_response,
        "trace": trace,
        "timestamp": _timestamp()
    })


# Quick actions: Examples, Clear, Download
with st.sidebar.expander("Quick Actions", expanded=True):
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.session_state.last_result = None
        st.experimental_rerun()

    # Build transcript for download
    transcript = "".join([
        f"[{m.get('timestamp','')}] {m['role'].upper()}: {m['content']}\n\n" for m in st.session_state.messages
    ])
    st.download_button("Download transcript", data=transcript, file_name="transcript.txt")

    st.markdown("---")
    st.markdown("### Examples")
    ex1, ex2, ex3 = st.columns(3)
    with ex1:
        if st.button("Network outage — area 415"):
            process_prompt("There is a network outage reported in area code 415 — what could cause this and how to troubleshoot?")
    with ex2:
        if st.button("Billing dispute — duplicate charge"):
            process_prompt("Customer 12345 disputes a duplicate charge of $75 on their last bill. Suggest next steps and required evidence.")
    with ex3:
        if st.button("5G performance degrade"):
            process_prompt("Users report degraded 5G performance in downtown during peak hours. What diagnostics should we run?")

# Chat input (kept at bottom of main column)
if prompt := st.chat_input("Ask anything — network issues, billing disputes, roaming costs, 5G troubleshooting..."):
    process_prompt(prompt)

# Show last result details for power users
if st.session_state.last_result:
    with st.expander("Show last result details (JSON)"):
        pretty = json.dumps(st.session_state.last_result, indent=2)
        st.code(pretty, language="json")

