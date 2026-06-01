from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from guardrails.input_guard import check_input
from guardrails.output_guard import scrub_output

from .state import AgentState
from llamaindex_rag.document_rag import query_policy
from llamaindex_rag.sql_semantic_search import query_network_data
from .adk_remote_client import call_network_diagnostics, call_billing_resolution
from .crew_nodes import run_comms_crew

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

# --- Routing Logic ---
class RouterOutput(BaseModel):
    next: Literal[
        "policy_rag",
        "network_analytics",
        "network_diagnostics_adk",
        "billing_resolution_adk",
        "customer_comms_crew",
        "FINISH"
    ]

routing_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are the Prodapt AI Operations Center supervisor.
You route customer inquiries to specialist workers based on the current context.

Decision Matrix:
- Policy / FAQ (policy, roaming, SLA, 5G FAQ) -> policy_rag -> customer_comms_crew
- Analytics (outage trends, packet loss, top N) -> network_analytics -> customer_comms_crew
- Connectivity (signal drops, tower ID, diagnose) -> network_diagnostics_adk -> customer_comms_crew
- Billing (charged twice, credit, CUST- prefix) -> billing_resolution_adk -> customer_comms_crew
- Combined (e.g. outage + policy) -> Data/ADK worker first -> Policy worker -> customer_comms_crew

Available workers:
- policy_rag: policy questions, FAQ, roaming, SLA rules, device upgrades
- network_analytics: outage data, tower performance, regional analytics (SQL)
- network_diagnostics_adk: live tower diagnosis, 5G issues, incident lookup
- billing_resolution_adk: billing disputes, duplicate charges, credit application
- customer_comms_crew: ALWAYS run this last before FINISH to polish the response
- FINISH: only after customer_comms_crew has run

If a worker has already provided the necessary facts in the context, DO NOT route to them again.
If all necessary facts are gathered, route to 'customer_comms_crew'.
If 'customer_comms_crew' has already run (it's in the context), route to 'FINISH'.

Workers already executed in this turn:
{executed_workers}
CRITICAL RULES:
1. NEVER route to a worker that has already been executed in this turn.
2. If all necessary facts are gathered OR if the required worker has already been executed, route to 'customer_comms_crew'.
3. If 'customer_comms_crew' has already been executed, route to 'FINISH'."""),
    ("user", "Prior Conversation History:\n{chat_history_str}\n\nLatest User Query: {user_query}\n\nCurrent Context:\n{agent_context}\n\nWho should act next?")
])

supervisor_chain = routing_prompt | llm.with_structured_output(RouterOutput)

def supervisor_node(state: AgentState) -> dict:
    executed_workers = ", ".join([step["worker"] for step in state.get("execution_trace", [])]) if state.get("execution_trace") else "None"
    decision = supervisor_chain.invoke({
        "chat_history_str": state.get("chat_history_str", ""),
        "user_query": state["user_query"],
        "agent_context": state["agent_context"],
        "executed_workers": executed_workers
    })
    return {"next": decision.next}

# --- Worker Nodes ---
def policy_rag_node(state: AgentState) -> dict:
    result = query_policy(state["user_query"])
    return {
        "agent_context": f"\n[PolicyRAG]: {result}",
        "execution_trace": [{"worker": "PolicyRAG", "output": result}],
        "messages": [AIMessage(content=result)]
    }

def network_analytics_node(state: AgentState) -> dict:
    result = query_network_data(state["user_query"])
    return {
        "agent_context": f"\n[NetworkAnalytics]: {result}",
        "execution_trace": [{"worker": "NetworkAnalytics", "output": result}],
        "messages": [AIMessage(content=result)]
    }

def network_diagnostics_node(state: AgentState) -> dict:
    result = call_network_diagnostics(state["user_query"], state.get("chat_history_str", ""))
    return {
        "agent_context": f"\n[NetworkDiagnosticsADK]: {result}",
        "execution_trace": [{"worker": "NetworkDiagnosticsADK", "output": result}],
        "messages": [AIMessage(content=result)]
    }

def billing_resolution_node(state: AgentState) -> dict:
    result = call_billing_resolution(state["user_query"], state.get("chat_history_str", ""))
    return {
        "agent_context": f"\n[BillingResolutionADK]: {result}",
        "execution_trace": [{"worker": "BillingResolutionADK", "output": result}],
        "messages": [AIMessage(content=result)]
    }

def customer_comms_node(state: AgentState) -> dict:
    result = run_comms_crew(state["user_query"], state["agent_context"], state.get("chat_history_str", ""))
    return {
        "agent_context": f"\n[CustomerCommsCrew]: {result}",
        "execution_trace": [{"worker": "CustomerCommsCrew", "output": result}],
        "final_response": result,
        "messages": [AIMessage(content=result)]
    }

# --- Build Graph ---
graph_builder = StateGraph(AgentState)

graph_builder.add_node("supervisor", supervisor_node)
graph_builder.add_node("policy_rag", policy_rag_node)
graph_builder.add_node("network_analytics", network_analytics_node)
graph_builder.add_node("network_diagnostics_adk", network_diagnostics_node)
graph_builder.add_node("billing_resolution_adk", billing_resolution_node)
graph_builder.add_node("customer_comms_crew", customer_comms_node)

graph_builder.set_entry_point("supervisor")

graph_builder.add_conditional_edges(
    "supervisor",
    lambda state: state["next"],
    {
        "policy_rag": "policy_rag",
        "network_analytics": "network_analytics",
        "network_diagnostics_adk": "network_diagnostics_adk",
        "billing_resolution_adk": "billing_resolution_adk",
        "customer_comms_crew": "customer_comms_crew",
        "FINISH": END
    }
)

for worker in ["policy_rag", "network_analytics", "network_diagnostics_adk", "billing_resolution_adk"]:
    graph_builder.add_edge(worker, "supervisor")

graph_builder.add_edge("customer_comms_crew", END)

compiled_graph = graph_builder.compile()

# --- Entry Point ---
def run_telecom_assistant(chat_history: list) -> dict:
    """
    Invokes the LangGraph and returns the result dict.
    Applies input guardrail before the graph, and output guardrail after.
    Expects chat_history as a list of dicts: [{"role": "user", "content": "..."}, ...]
    """
    latest_query = chat_history[-1]["content"] if chat_history else ""

    history_lines = []
    for msg in chat_history[:-1]:
        role = "Customer" if msg["role"] == "user" else "Agent"
        history_lines.append(f"{role}: {msg['content']}")
    chat_history_str = "\n".join(history_lines)

    # ── Layer 1: Input Guardrail ──────────────────────────────────────────────
    guard_result = check_input(latest_query, history=chat_history_str)
    if not guard_result["allowed"]:
        return {
            "final_response": guard_result["safe_response"],
            "execution_trace": [{"worker": "InputGuardrail", "output": f"BLOCKED [{guard_result['stage']}]: {guard_result['reason']}"}],
            "agent_context": f"[GUARDRAIL BLOCKED] {guard_result['reason']}"
        }

    # ── LangGraph Execution ───────────────────────────────────────────────────
    messages = []
    for msg in chat_history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    initial_state = {
        "messages": messages,
        "user_query": latest_query,
        "chat_history_str": chat_history_str,
        "agent_context": "",
        "execution_trace": [],
        "final_response": "",
        "next": ""
    }
    final_state = compiled_graph.invoke(initial_state, {"recursion_limit": 10})

    raw_response = final_state["final_response"]

    # ── Layer 2: Output Guardrail ─────────────────────────────────────────────
    safe_response = scrub_output(raw_response)

    return {
        "final_response": safe_response,
        "execution_trace": final_state["execution_trace"],
        "agent_context": final_state["agent_context"]
    }
