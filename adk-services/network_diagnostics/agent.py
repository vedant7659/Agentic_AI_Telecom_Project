import sqlite3
import uvicorn
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.tools import FunctionTool

load_dotenv()

DB_PATH = "data/telecom_ops.db"

def check_tower_status(tower_id: str) -> str:
    """Gets the operational status, performance metrics, and any open incidents for a specific tower."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # JOIN across towers, performance, and incidents
    query = """
        SELECT t.city, t.technology, t.status, p.latency_ms, p.packet_loss_pct, p.throughput_mbps, p.signal_strength_dbm, i.incident_id, i.description as incident_desc
        FROM network_towers t
        LEFT JOIN tower_performance p ON t.tower_id = p.tower_id
        LEFT JOIN open_incidents i ON t.tower_id = i.tower_id
        WHERE t.tower_id = ?
    """
    cursor.execute(query, (tower_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return f"Tower {tower_id} not found."
    
    res = f"Tower {tower_id} ({row['city']}, {row['technology']}): {row['status']}. "
    if row['latency_ms'] is not None:
        res += f"Signal: {row['signal_strength_dbm']} dBm, Latency: {row['latency_ms']}ms, Packet Loss: {row['packet_loss_pct']}%, Throughput: {row['throughput_mbps']} Mbps. "
    
    if row['incident_id']:
        res += f"Open Incident {row['incident_id']}: {row['incident_desc']}. "
    else:
        res += "No open incidents. "
        
    return res

def run_connectivity_diagnostics(tower_id: str, symptom: str) -> str:
    """Diagnoses connectivity issues (like 5G drops) based on tower metrics and provides a recommendation."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT status FROM network_towers WHERE tower_id = ?", (tower_id,))
    tower = cursor.fetchone()
    
    if not tower:
         return f"Tower {tower_id} not found."
         
    cursor.execute("SELECT * FROM tower_performance WHERE tower_id = ?", (tower_id,))
    perf = cursor.fetchone()
    
    cursor.execute("SELECT incident_id FROM open_incidents WHERE tower_id = ?", (tower_id,))
    inc = cursor.fetchone()
    conn.close()

    if tower['status'] == 'MAINTENANCE' or inc:
         return "Diagnostics: Tower is currently undergoing maintenance or has an active incident. Connectivity issues are expected."
    
    if perf:
        if perf['signal_strength_dbm'] > -80 and perf['packet_loss_pct'] < 1.0:
            return f"Diagnostics: Tower is performing well (Signal: {perf['signal_strength_dbm']} dBm). Recommendation: Issue may be device-side or indoor penetration limitation. Try disabling/re-enabling {symptom.split()[0] if symptom else 'connection'} on the device."
        else:
             return f"Diagnostics: Tower is showing degraded performance. Recommendation: Escalate to Level 2 support for network investigation."
             
    return "Diagnostics: Not enough performance data to conclude."

def get_regional_network_summary(region: str) -> str:
    """Aggregates tower counts and operational statuses by region."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT status, count(*) FROM network_towers WHERE region = ? GROUP BY status", (region,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return f"No network towers found in region {region}."
        
    summary = f"Regional Network Summary for {region}: "
    for status, count in rows:
        summary += f"{count} tower(s) {status}. "
    return summary

# Register tools with the agent
agent = Agent(
    name="network_diagnostics",
    model="openai/gpt-4o-mini",
    tools=[
        FunctionTool(check_tower_status),
        FunctionTool(run_connectivity_diagnostics),
        FunctionTool(get_regional_network_summary)
    ],
    instruction="You are a Network Diagnostics specialist. Use your SQL tools to query tower status, performance, and incidents to answer user inquiries."
)

# Create A2A application
if __name__ == "__main__":
    import uvicorn
    app = to_a2a(agent, port=8001)
    print("Starting Network Diagnostics ADK Service on port 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
