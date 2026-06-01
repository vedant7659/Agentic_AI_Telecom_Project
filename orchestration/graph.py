from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

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
If 'customer_comms_crew' has already run (it's in the context), route to 'FINISH'."""),
    ("user", "User Query: {user_query}\n\nCurrent Context:\n{agent_context}\n\nWho should act next?")
])

supervisor_chain = routing_prompt | llm.with_structured_output(RouterOutput)

def supervisor_node(state: AgentState) -> dict:
    decision = supervisor_chain.invoke({
        "user_query": state["user_query"],
        "agent_context": state["agent_context"]
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
    result = call_network_diagnostics(state["user_query"])
    return {
        "agent_context": f"\n[NetworkDiagnosticsADK]: {result}",
        "execution_trace": [{"worker": "NetworkDiagnosticsADK", "output": result}],
        "messages": [AIMessage(content=result)]
    }

def billing_resolution_node(state: AgentState) -> dict:
    result = call_billing_resolution(state["user_query"])
    return {
        "agent_context": f"\n[BillingResolutionADK]: {result}",
        "execution_trace": [{"worker": "BillingResolutionADK", "output": result}],
        "messages": [AIMessage(content=result)]
    }

def customer_comms_node(state: AgentState) -> dict:
    result = run_comms_crew(state["user_query"], state["agent_context"])
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
def run_telecom_assistant(user_query: str) -> dict:
    """Invokes the LangGraph and returns the result dict."""
    initial_state = {
        "messages": [HumanMessage(content=user_query)],
        "user_query": user_query,
        "agent_context": "",
        "execution_trace": [],
        "final_response": "",
        "next": ""
    }
    final_state = compiled_graph.invoke(initial_state)
    return {
        "final_response": final_state["final_response"],
        "execution_trace": final_state["execution_trace"],
        "agent_context": final_state["agent_context"]
    }
