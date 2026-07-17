import chromadb
from app.core.config import settings, chroma_mode, chroma_path

class VectorStore:
    _client = None
    _embedding_function = None

    @classmethod
    def set_embedding_function(cls, ef):
        cls._embedding_function = ef

    @classmethod
    def get_client(cls):
        if cls._client is None:
            if chroma_mode() == "embedded":
                # Desktop / single-file: no separate ChromaDB server needed.
                path = chroma_path()
                path.mkdir(parents=True, exist_ok=True)
                cls._client = chromadb.PersistentClient(path=str(path))
            else:
                # Server / Docker: connect to a standalone ChromaDB service.
                cls._client = chromadb.HttpClient(
                    host=settings.CHROMADB_HOST,
                    port=settings.CHROMADB_PORT
                )
        return cls._client

    @classmethod
    def get_collection(cls, name: str = "knowledge_points"):
        if cls._embedding_function is None:
            raise ValueError("Embedding function is not initialized. Please configure an AI Embedding Model in System Settings.")
            
        client = cls.get_client()
        # get_or_create_collection handles the existence check
        return client.get_or_create_collection(name=name, embedding_function=cls._embedding_function)

    @classmethod
    def upsert_knowledge_point(cls, id: int, text: str, metadata: dict):
        """
        Upsert a knowledge point into the vector store.
        """
        try:
            collection = cls.get_collection()
            collection.upsert(
                ids=[str(id)],
                documents=[text],
                metadatas=[metadata]
            )
        except Exception as e:
            print(f"Error upserting knowledge point {id} to vector store: {e}")

    @classmethod
    def delete_knowledge_point(cls, id: int):
        """
        Delete a knowledge point from the vector store.
        """
        try:
            collection = cls.get_collection()
            collection.delete(ids=[str(id)])
        except Exception as e:
            print(f"Error deleting knowledge point {id} from vector store: {e}")

    @classmethod
    def search_similar(cls, query: str, subject_id: int = None, limit: int = 10):
        """
        Search for similar knowledge points.
        """
        try:
            collection = cls.get_collection()
            where_filter = {}
            if subject_id:
                where_filter["subject_id"] = subject_id
            
            # If no filter, pass None to avoid ChromaDB error if it expects None
            if not where_filter:
                where_filter = None

            results = collection.query(
                query_texts=[query],
                n_results=limit,
                where=where_filter
            )
            return results
        except Exception as e:
            print(f"Error searching vector store: {e}")
            return None
