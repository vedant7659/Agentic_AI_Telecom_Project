from typing import TypedDict, Annotated, Literal
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    next: str
    user_query: str
    chat_history_str: str
    agent_context: str
    execution_trace: Annotated[list[dict], operator.add]
    final_response: str
