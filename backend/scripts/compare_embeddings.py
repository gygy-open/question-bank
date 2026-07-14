import os
import sys
import asyncio
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from typing import List
import openai
from dotenv import load_dotenv

# Add backend directory to path to import app modules if needed
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import SessionLocal, engine
from app.crud.crud_system_setting import system_setting
from app.crud.crud_ai_config import ai_model, ai_provider
from app.services.embedding import AIProviderEmbeddingFunction
from app.models.ai_config import AIModel, AIProvider
from sqlalchemy import select

load_dotenv()

# Test Data: High school math concepts (Chinese)
DOCUMENTS = [
    "函数 f(x) = x^2 的单调递增区间是 [0, +∞)。",
    "集合 A={1, 2}，集合 B={2, 3}，则 A ∪ B = {1, 2, 3}。",
    "若向量 a = (1, 2)，b = (3, 4)，则 a·b = 1*3 + 2*4 = 11。",
    "秦始皇是中国历史上第一个皇帝，统一了六国。",  # Distractor
    "勾股定理：直角三角形的两条直角边的平方和等于斜边的平方。",
    "光合作用是植物利用光能将二氧化碳和水转化为有机物的过程。", # Distractor
]

IDS = [str(i) for i in range(len(DOCUMENTS))]

QUERIES = [
    "二次函数的性质",
    "集合的并集怎么算",
    "向量的数量积公式",
    "直角三角形边长关系",
]

async def get_active_embedding_config():
    """
    Returns (api_key, base_url, interface_type, model_name)
    """
    async with SessionLocal() as db:
        # 1. Try to get active embedding model ID
        setting = await system_setting.get_by_key(db, "AI_EMBEDDING_MODEL_ID")
        model_id = int(setting.value) if setting and setting.value else None
        
        target_model = None
        if model_id:
            target_model = await ai_model.get(db, id=model_id)
        
        # 2. If no active model, try to find first available embedding model
        if not target_model:
            query = select(AIModel).where(AIModel.is_embedding_model == True).limit(1)
            result = await db.execute(query)
            target_model = result.scalar_one_or_none()
            
        if not target_model:
            print("[INFO] No embedding model found in database.")
            return None
            
        # 3. Get Provider
        provider = await ai_provider.get(db, id=target_model.provider_id)
        if not provider:
            print(f"[ERROR] Provider not found for model {target_model.name}")
            return None
            
        return (provider.api_key, provider.base_url, provider.interface_type, target_model.name)

async def run_comparison():
    print("=== Embedding Model Comparison Script ===\n")

    # 1. Setup Default ChromaDB (uses all-MiniLM-L6-v2)
    print("Initializing ChromaDB with DEFAULT embedding (all-MiniLM-L6-v2)...")
    client = chromadb.Client() # Ephemeral in-memory client
    
    try:
        default_collection = client.create_collection(name="default_test")
        default_collection.add(documents=DOCUMENTS, ids=IDS)
    except Exception as e:
        print(f"Error setting up default collection: {e}")
        return

    # 2. Setup Custom ChromaDB (uses Provider from DB)
    print("\nFetching configuration from Database...")
    config = await get_active_embedding_config()
    
    if not config:
        print("\n[WARNING] No active embedding configuration found in database.")
        print("Skipping Custom Embedding test. Please configure an embedding model in the UI.")
        custom_collection = None
    else:
        api_key, base_url, provider_type, model_name = config
        print(f"\nInitializing ChromaDB with CUSTOM embedding (Provider: {provider_type}, Model: {model_name})...")
        try:
            ef = AIProviderEmbeddingFunction(
                provider_type=provider_type, 
                api_key=api_key, 
                base_url=base_url, 
                model_name=model_name
            )
            custom_collection = client.create_collection(name="custom_test", embedding_function=ef)
            custom_collection.add(documents=DOCUMENTS, ids=IDS)
        except Exception as e:
            print(f"Error setting up custom collection: {e}")
            custom_collection = None

    # 3. Run Comparison
    print("\n=== Comparison Results ===\n")
    
    for query in QUERIES:
        print(f"Query: [{query}]")
        
        # Default Results
        print("  [Default Model Results]:")
        results_default = default_collection.query(query_texts=[query], n_results=3)
        for i, doc in enumerate(results_default['documents'][0]):
            dist = results_default['distances'][0][i]
            print(f"    {i+1}. (Dist: {dist:.4f}) {doc}")

        # Custom Results
        if custom_collection:
            print("  [Custom Model Results]:")
            try:
                results_custom = custom_collection.query(query_texts=[query], n_results=3)
                for i, doc in enumerate(results_custom['documents'][0]):
                    dist = results_custom['distances'][0][i]
                    print(f"    {i+1}. (Dist: {dist:.4f}) {doc}")
            except Exception as e:
                print(f"    Error querying custom collection: {e}")
        
        print("-" * 50)
    
    # Cleanup
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_comparison())
