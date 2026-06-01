"""
ADK Remote Client — uses the ADK native RemoteA2aAgent and Runner.
"""
import uuid
import logging
from google.genai import types
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

logger = logging.getLogger(__name__)

NETWORK_ADK_URL = "http://localhost:8001"
BILLING_ADK_URL = "http://localhost:8002"

def _call_a2a_service(base_url: str, agent_name: str, desc: str, message: str) -> str:
    try:
        agent_card = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
        agent = RemoteA2aAgent(
            name=agent_name,
            description=desc,
            agent_card=agent_card,
        )
        runner = Runner(
            agent=agent,
            app_name=f"{agent_name}_app",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )
        
        content = types.Content(role="user", parts=[types.Part.from_text(text=message)])
        session_id = str(uuid.uuid4())
        events = runner.run(
            user_id="supervisor_user",
            session_id=session_id,
            new_message=content
        )
        
        response_text = ""
        for event in events:
            if event.author == agent_name and event.content and event.content.parts:
                texts = [part.text for part in event.content.parts if part.text]
                if texts:
                    response_text = " ".join(texts)
                    
        return response_text or "[No agent response in task history]"
    except Exception as e:
        logger.error(f"Error calling ADK service at {base_url}: {e}")
        return f"[ERROR calling {base_url}]: {type(e).__name__}: {e}"

def call_network_diagnostics(query: str) -> str:
    """Invoke the Network Diagnostics ADK service."""
    return _call_a2a_service(
        NETWORK_ADK_URL, 
        "network_diagnostics", 
        "Remote network diagnostics agent.", 
        query
    )

def call_billing_resolution(query: str) -> str:
    """Invoke the Billing Resolution ADK service."""
    return _call_a2a_service(
        BILLING_ADK_URL, 
        "billing_resolution", 
        "Remote billing resolution agent.", 
        query
    )
