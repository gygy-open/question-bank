import sys
import os
import asyncio
import chromadb
from dotenv import load_dotenv

# Add backend directory to path to import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.config import settings

def clear_chroma():
    print("=== Clearing ChromaDB ===")
    print(f"Connecting to ChromaDB at {settings.CHROMADB_HOST}:{settings.CHROMADB_PORT}...")
    
    try:
        client = chromadb.HttpClient(
            host=settings.CHROMADB_HOST,
            port=settings.CHROMADB_PORT
        )
        
        collections = client.list_collections()
        if not collections:
            print("No collections found.")
            return

        print(f"Found {len(collections)} collections: {[c.name for c in collections]}")
        
        confirm = input("Are you sure you want to delete ALL collections? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            return

        for collection in collections:
            print(f"Deleting collection: {collection.name}...")
            client.delete_collection(collection.name)
            
        print("All collections deleted successfully.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    clear_chroma()
