import os
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings, StorageContext, load_index_from_storage
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Configure global settings
Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
Settings.llm = OpenAI(model="gpt-4o-mini", temperature=0.1)

DOCUMENTS_DIR = "data/documents"
PERSIST_DIR = "data/vector_index"

def build_or_load_index():
    """Builds the vector index from policy documents or loads it if it exists."""
    if not os.path.exists(PERSIST_DIR) or not os.listdir(PERSIST_DIR):
        print(f"Building vector index from {DOCUMENTS_DIR}...")
        documents = SimpleDirectoryReader(DOCUMENTS_DIR).load_data()
        index = VectorStoreIndex.from_documents(documents)
        index.storage_context.persist(persist_dir=PERSIST_DIR)
        print("Vector index built and persisted.")
        return index
    else:
        print(f"Loading existing vector index from {PERSIST_DIR}...")
        storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
        index = load_index_from_storage(storage_context)
        print("Vector index loaded.")
        return index

# Initialize index globally so it's loaded once
index = build_or_load_index()
query_engine = index.as_query_engine()

def query_policy(question: str) -> str:
    """Queries the policy documents using LlamaIndex Vector RAG."""
    response = query_engine.query(question)
    return str(response)

if __name__ == "__main__":
    # Test
    print("Testing Policy RAG...")
    res = query_policy("What is the roaming policy for Europe?")
    print(res)
