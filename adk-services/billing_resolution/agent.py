import sqlite3
import uvicorn
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.tools import FunctionTool

load_dotenv()

DB_PATH = "data/telecom_ops.db"

def lookup_billing_account(customer_id: str) -> str:
    """Retrieves current balance and recent charges for a customer account."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT current_balance FROM billing_accounts WHERE customer_id = ?", (customer_id,))
    account = cursor.fetchone()
    
    if not account:
         return f"Customer account {customer_id} not found."
         
    cursor.execute("SELECT charge_id, description, amount, is_duplicate_flag FROM billing_charges WHERE customer_id = ?", (customer_id,))
    charges = cursor.fetchall()
    conn.close()
    
    res = f"Account {customer_id} - Current Balance: ${account['current_balance']:.2f}. "
    if charges:
         res += "Recent charges: "
         for c in charges:
             duplicate_str = " (FLAGGED DUPLICATE)" if c['is_duplicate_flag'] else ""
             res += f"[ID: {c['charge_id']}] {c['description']}: ${c['amount']:.2f}{duplicate_str}. "
    else:
         res += "No recent charges."
         
    return res

def check_duplicate_charges(customer_id: str) -> str:
    """Checks for charges flagged as duplicates for a customer."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT charge_id, description, amount FROM billing_charges WHERE customer_id = ? AND is_duplicate_flag = 1", (customer_id,))
    duplicates = cursor.fetchall()
    conn.close()
    
    if not duplicates:
        return f"No duplicate charges found for {customer_id}."
        
    res = f"Found {len(duplicates)} duplicate charge(s) for {customer_id}: "
    for d in duplicates:
         res += f"[ID: {d['charge_id']}] {d['description']} for ${d['amount']:.2f}. "
    return res

def apply_billing_credit(customer_id: str, amount: float, reason: str) -> str:
    """Applies a credit to a customer's account. Credits over $50 require manual approval."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if account exists
    cursor.execute("SELECT current_balance FROM billing_accounts WHERE customer_id = ?", (customer_id,))
    account = cursor.fetchone()
    if not account:
        return f"Customer account {customer_id} not found."
        
    current_balance = account[0]
    status = 'PENDING_APPROVAL' if amount > 50.0 else 'APPLIED'
    
    cursor.execute(
        "INSERT INTO billing_credits (customer_id, amount, reason, status, reference_number, applied_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (customer_id, amount, reason, status, f"REF-{customer_id[-4:]}")
    )
    
    res = f"Credit of ${amount:.2f} recorded. Status: {status} "
    if amount > 50.0:
        res += "(exceeds $50 auto-approval limit). "
        
    if status == 'APPLIED':
        new_balance = current_balance - amount
        cursor.execute("UPDATE billing_accounts SET current_balance = ? WHERE customer_id = ?", (new_balance, customer_id))
        res += f"Account balance updated from ${current_balance:.2f} to ${new_balance:.2f}."
    else:
        res += f"Current balance remains ${current_balance:.2f} until credit is approved."
        
    conn.commit()
    conn.close()
    
    return res

# Register tools with the agent
agent = Agent(
    name="billing_resolution",
    model="openai/gpt-4o-mini",
    tools=[
        FunctionTool(lookup_billing_account),
        FunctionTool(check_duplicate_charges),
        FunctionTool(apply_billing_credit)
    ],
    instruction="You are a Billing Resolution specialist. Use your SQL tools to lookup accounts, identify duplicates, and apply credits for customer disputes."
)

# Create A2A application
app = to_a2a(agent, port=8002)

if __name__ == "__main__":
    print("Starting Billing Resolution ADK Service on port 8002...")
    uvicorn.run(app, host="0.0.0.0", port=8002)
