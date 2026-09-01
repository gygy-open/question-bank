from typing import Any, Dict, List
import shutil
import socket
import chromadb
from app.core.config import settings, chroma_mode, chroma_path, legacy_chroma_path

class VectorStore:
    _client = None
    _embedding_function = None

    # chromadb's HttpClient hardcodes an unbounded httpx timeout internally, so an
    # unreachable server otherwise blocks for the OS-level TCP timeout (~110-130s on
    # Linux) on every single call. Probe first with a short, bounded timeout instead.
    _HTTP_PROBE_TIMEOUT_SECONDS = 2.0

    @classmethod
    def set_embedding_function(cls, ef):
        cls._embedding_function = ef

    @classmethod
    def is_reachable(cls) -> bool:
        """Whether the configured ChromaDB backend can be reached right now."""
        if chroma_mode() == "embedded":
            return True
        try:
            with socket.create_connection(
                (settings.CHROMADB_HOST, settings.CHROMADB_PORT),
                timeout=cls._HTTP_PROBE_TIMEOUT_SECONDS,
            ):
                return True
        except OSError:
            return False

    @classmethod
    def get_client(cls):
        if cls._client is None:
            if chroma_mode() == "embedded":
                # Desktop / single-file: no separate ChromaDB server needed.
                path = chroma_path()
                # One-time move of the pre-consolidation store into data/.
                legacy = legacy_chroma_path()
                if legacy.exists() and not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(legacy), str(path))
                path.mkdir(parents=True, exist_ok=True)
                cls._client = chromadb.PersistentClient(path=str(path))
            else:
                # Server / Docker: connect to a standalone ChromaDB service.
                if not cls.is_reachable():
                    raise ConnectionError(
                        f"ChromaDB HTTP server {settings.CHROMADB_HOST}:{settings.CHROMADB_PORT} unreachable"
                    )
                cls._client = chromadb.HttpClient(
                    host=settings.CHROMADB_HOST,
                    port=settings.CHROMADB_PORT
                )
        return cls._client

    @classmethod
    def is_available(cls) -> bool:
        """
        Whether an embedding function is configured. Write paths use this to
        decide whether to sync (deferred indexing when no embedding model set up).
        """
        return cls._embedding_function is not None

    @classmethod
    def get_collection(cls, name: str = "knowledge_points"):
        if cls._embedding_function is None:
            raise ValueError("Embedding function is not initialized. Please configure an AI Embedding Model in System Settings.")
            
        client = cls.get_client()
        # get_or_create_collection handles the existence check
        return client.get_or_create_collection(name=name, embedding_function=cls._embedding_function)

    @classmethod
    def count(cls, name: str = "knowledge_points") -> int:
        """Number of vectors currently in the collection (for sync-status comparison)."""
        if not cls.is_available():
            return 0
        try:
            return cls.get_collection(name).count()
        except Exception as e:
            print(f"Error counting vector store collection {name}: {e}")
            return 0

    @classmethod
    def count_by_subject(cls, subject_id: int, name: str = "knowledge_points") -> int:
        """Number of vectors for a single subject (subject-scoped sync check)."""
        if not cls.is_available():
            return 0
        try:
            res = cls.get_collection(name).get(where={"subject_id": subject_id}, include=[])
            return len(res.get("ids", []))
        except Exception as e:
            print(f"Error counting vectors for subject {subject_id}: {e}")
            return 0

    @classmethod
    def reset_collection(cls, name: str = "knowledge_points"):
        """Delete the collection so it can be rebuilt from scratch (full reindex)."""
        try:
            client = cls.get_client()
            client.delete_collection(name)
        except Exception as e:
            # Collection may not exist yet; that's fine.
            print(f"Note: could not delete collection {name} (may not exist): {e}")

    @classmethod
    def upsert_knowledge_points_batch(cls, items: List[Dict[str, Any]], raise_on_error: bool = False):
        """
        Batch upsert knowledge points in a single call.
        items: [{"id": int, "text": str, "metadata": dict}, ...]
        """
        if not cls.is_available() or not items:
            return
        try:
            collection = cls.get_collection()
            collection.upsert(
                ids=[str(i["id"]) for i in items],
                documents=[i["text"] for i in items],
                metadatas=[i["metadata"] for i in items],
            )
        except Exception as e:
            print(f"Error batch upserting {len(items)} knowledge points to vector store: {e}")
            if raise_on_error:
                raise

    @classmethod
    def delete_knowledge_points_batch(cls, ids: List[int]):
        """Batch delete knowledge points from the vector store by id."""
        if not cls.is_available() or not ids:
            return
        try:
            collection = cls.get_collection()
            collection.delete(ids=[str(i) for i in ids])
        except Exception as e:
            print(f"Error batch deleting knowledge points from vector store: {e}")

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
