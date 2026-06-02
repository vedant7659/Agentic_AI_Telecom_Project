# Agentic Capstone

Prodapt AI Operations Center is a proof-of-concept telecom operations assistant that combines RAG, semantic SQL, ADK tooling, and CrewAI communication synthesis.

## What it does

- Routes customer inquiries through a supervisor graph (`orchestration/graph.py`) using LangGraph.
- Answers policy and FAQ questions using LlamaIndex RAG over business documents.
- Runs semantic SQL analytics against the telecom database for outage and network queries.
- Calls remote ADK services for live-style network diagnostics and billing resolution.
- Uses CrewAI to draft and polish customer-facing replies.
- Provides a Streamlit UI for conversation handling and an admin page for manual billing credit approvals.

## Key components

- `ui/app.py` — main Streamlit chat UI and system health sidebar.
- `ui/pages/1_Admin.py` — admin approval dashboard for pending billing credits.
- `orchestration/graph.py` — supervisor + worker graph orchestrating the multi-agent workflow.
- `orchestration/adk_remote_client.py` — ADK client for remote A2A agent calls.
- `orchestration/crew_nodes.py` — CrewAI communication drafting and reviewing.
- `llamaindex_rag/document_rag.py` — policy document RAG index and query engine.
- `llamaindex_rag/sql_semantic_search.py` — semantic SQL query engine for network analytics.
- `adk-services/network_diagnostics/agent.py` — Network Diagnostics ADK service.
- `adk-services/billing_resolution/agent.py` — Billing Resolution ADK service.
- `sql/01_schema.sql`, `sql/02_seed_data.sql` — database schema and seed dataset.
- `data/documents/` — policy, SLA, roaming, billing, and 5G reference documents.

## Requirements

- Python 3.11+ recommended
- `requirements.txt` contains the required Python libraries
- OpenAI API credentials and Google ADK credentials must be available via environment variables or `.env`

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
.\.venv\Scripts\activate
```

2. Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3. Create a `.env` file in the repository root with your API credentials. Example:

```bash
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key
GOOGLE_API_PROJECT=your_project_id
```

4. Initialize the SQLite database and seed data:

```bash
python init_db.py
```

5. Build the document vector index automatically by running the UI or manually by importing `llamaindex_rag.document_rag`.

## Running the system

### Start ADK services

Open two terminals and run:

```bash
python adk-services/network_diagnostics/agent.py
```

```bash
python adk-services/billing_resolution/agent.py
```

These services expose remote A2A endpoints on:

- `http://localhost:8001` — Network Diagnostics
- `http://localhost:8002` — Billing Resolution

### Run the Streamlit UI

```bash
streamlit run ui/app.py
```

Then open the URL shown in the terminal.

### Admin page

The admin approval page is available as a Streamlit page at:

- `ui/pages/1_Admin.py`

Use the password `admin123` to sign in, review pending credit approvals, and export or filter pending items.

## How the workflow works

1. User sends a query through the Streamlit chat interface.
2. `orchestration/graph.py` uses a LangGraph supervisor to choose the next specialist worker.
3. The selected worker can be:
   - `policy_rag` for policy/FAQ answers
   - `network_analytics` for semantic SQL queries
   - `network_diagnostics_adk` for remote diagnostics
   - `billing_resolution_adk` for billing issues
4. Once relevant facts are gathered, `customer_comms_crew` uses CrewAI to draft the final customer response.
5. Input and output guardrails are applied through `guardrails/input_guard.py` and `guardrails/output_guard.py`.

## Data sources

- Policy documents: `data/documents/*.txt`
- Telecom database: `data/telecom_ops.db`
- SQL schema: `sql/01_schema.sql`
- Seed data: `sql/02_seed_data.sql`

## Notes

- The UI checks service health and reports if the ADK services are offline.
- Credits over $50 are marked `PENDING_APPROVAL` and require manual action on the admin page.
- The admin panel includes filtering, CSV export, and JSON detail expanders for each credit entry.

## Troubleshooting

- If the UI reports `DB: Not found`, rerun `python init_db.py` and ensure `data/telecom_ops.db` exists.
- If vector search is not ready, it will be built automatically on the first RAG query.
- Ensure both ADK services are running before submitting network or billing queries.

## Development

- Modify `orchestration/graph.py` to change routing behavior.
- Update `llamaindex_rag/document_rag.py` to add or replace policy documents.
- Extend ADK tools in `adk-services/*/agent.py` with new functions for additional diagnostics or billing operations.

---
