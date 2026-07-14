import sys
import os
import asyncio

# Add the backend directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.vector_store import VectorStore
from app.services.embedding import reload_embedding_function
from app.db.session import engine

async def main():
    # Initialize embedding function
    await reload_embedding_function()

    try:
        collection = VectorStore.get_collection()
        count = collection.count()
        print(f"Total records in ChromaDB: {count}")
        
        if count == 0:
            print("No records found.")
            return

        # Fetch all data to sort by ID (since we use DB ID as Chroma ID)
        # For 570 records, fetching all is fast and ensures we see the "latest" by ID.
        result = collection.get(include=['metadatas', 'documents'])
        
        items = []
        ids = result['ids']
        metadatas = result['metadatas']
        documents = result['documents']
        
        for i in range(len(ids)):
            items.append({
                'id': ids[i],
                'metadata': metadatas[i],
                'document': documents[i]
            })
            
        # Sort by ID (convert string ID to int for correct numerical sorting)
        items.sort(key=lambda x: int(x['id']))
        
        print("\n--- Last 5 Records (Ordered by ID) ---")
        for item in items[-5:]:
            print(f"ID: {item['id']}")
            print(f"Metadata: {item['metadata']}")
            print(f"Document: {item['document']}")
            print("-" * 40)
            
    except Exception as e:
        print(f"Error querying ChromaDB: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
