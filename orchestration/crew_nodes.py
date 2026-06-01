import os
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

# We need to initialize the LLM for CrewAI
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

def run_comms_crew(user_query: str, agent_context: str) -> str:
    """
    Runs a CrewAI sequential crew to synthesize the agent_context into a polished,
    professional, and empathetic customer response.
    """
    if not agent_context.strip():
        agent_context = "No specific facts were retrieved. Please ask the user to clarify."

    drafter = Agent(
        role="Communications Drafter",
        goal="Draft a clear, professional, and empathetic response to the customer.",
        backstory="You are a seasoned customer support communications specialist at Prodapt AI Operations Center. You excel at turning technical facts and policy rules into easy-to-understand responses for customers.",
        verbose=False,
        allow_delegation=False,
        llm=llm
    )

    reviewer = Agent(
        role="Communications Reviewer",
        goal="Review and polish the drafted response to ensure tone, accuracy, and empathy.",
        backstory="You are the lead editor for customer communications. You ensure every outgoing message is perfectly formatted, polite, empathetic to customer issues, and factually aligned with the provided data.",
        verbose=False,
        allow_delegation=False,
        llm=llm
    )

    draft_task = Task(
        description=f"Review the customer's original query and the raw data retrieved by our specialist systems.\n\nCustomer Query: {user_query}\n\nSystem Data Context:\n{agent_context}\n\nDraft a complete, direct response to the customer. Do not include internal system notes. Be empathetic if they are experiencing an issue.",
        expected_output="A well-written draft response to the customer.",
        agent=drafter
    )

    review_task = Task(
        description="Review the draft response. Ensure it sounds natural, professional, and empathetic. Fix any formatting. The final output must be just the message to the customer, nothing else.",
        expected_output="The final polished message ready to be sent to the customer.",
        agent=reviewer
    )

    crew = Crew(
        agents=[drafter, reviewer],
        tasks=[draft_task, review_task],
        process=Process.sequential,
        verbose=False
    )

    # Crew kickoff
    result = crew.kickoff()
    return str(result)
