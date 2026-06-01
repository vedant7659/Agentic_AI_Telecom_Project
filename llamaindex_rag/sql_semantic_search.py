from llama_index.core import SQLDatabase
from llama_index.core.query_engine import SQLTableRetrieverQueryEngine
from llama_index.core.objects import SQLTableNodeMapping, ObjectIndex, SQLTableSchema
from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai import OpenAI
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

# Configure global settings
Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
Settings.llm = OpenAI(model="gpt-4o-mini", temperature=0.1) # Using gpt-4o-mini

DB_URI = "sqlite:///data/telecom_ops.db"

def get_sql_query_engine():
    """Builds and returns the SQLTableRetrieverQueryEngine."""
    engine = create_engine(DB_URI)
    sql_database = SQLDatabase(engine)

    # Define table schemas with context strings
    table_node_mapping = SQLTableNodeMapping(sql_database)
    table_schema_objs = [
        SQLTableSchema(
            table_name="network_towers",
            context_str="Tower inventory. Describes tower locations (region, city), technology (e.g., 5G), and general operational status."
        ),
        SQLTableSchema(
            table_name="network_outages",
            context_str="Historical outage records. Describes outage severity (e.g., CRITICAL), start and end times, affected customers, incident IDs, root causes, and region."
        ),
        SQLTableSchema(
            table_name="tower_performance",
            context_str="Live tower metrics. Describes latency, packet loss, throughput, and signal strength for active towers."
        ),
        SQLTableSchema(
            table_name="customer_subscriptions",
            context_str="Customer plans. Describes subscription plan names, monthly fees, and account types by region."
        )
    ]

    # Build object index for semantic table retrieval
    obj_index = ObjectIndex.from_objects(
        table_schema_objs,
        table_node_mapping,
        VectorStoreIndex,
    )

    # Create the query engine
    query_engine = SQLTableRetrieverQueryEngine(
        sql_database,
        obj_index.as_retriever(similarity_top_k=2),
    )
    
    return query_engine

# Initialize query engine globally
query_engine = get_sql_query_engine()

def query_network_data(question: str) -> str:
    """Queries the SQL database using Semantic SQL."""
    response = query_engine.query(question)
    return str(response)

if __name__ == "__main__":
    # Test
    print("Testing Semantic SQL...")
    res = query_network_data("Which region had the most CRITICAL outages?")
    print(res)
