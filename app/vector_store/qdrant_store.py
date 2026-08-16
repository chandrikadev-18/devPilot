import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.indexer.chunker import CodeChunk

DEFAULT_COLLECTION_NAME = "devpilot_code"
DEFAULT_STORAGE_PATH = "data/qdrant"
DEFAULT_DISTANCE = Distance.COSINE
DEFAULT_BATCH_SIZE = 64


class VectorStoreError(Exception):
    """Base exception for vector store operations."""
    pass


class ConfigurationMismatchError(VectorStoreError):
    """Raised when existing collection configuration does not match current model settings."""
    pass


class ValidationError(VectorStoreError):
    """Raised when input chunks or vectors fail validation checks."""
    pass


def chunk_id_to_point_id(chunk_id: str) -> str:
    """
    Converts a deterministic CodeChunk ID into a standard UUID string for Qdrant point storage.
    
    Qdrant requires point IDs to be valid unsigned 64-bit integers or RFC 4122 UUID strings.
    This function uses UUIDv5 (SHA-1 hashing over a fixed namespace and key) to guarantee that
    identical CodeChunk IDs always produce the exact same point UUID across sessions and platforms.
    """
    if not chunk_id or not isinstance(chunk_id, str):
        raise ValidationError("chunk_id must be a non-empty string.")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"devpilot:{chunk_id}"))


def build_chunk_payload(chunk: CodeChunk) -> Dict[str, Any]:
    """
    Constructs a clean, serializable payload dictionary containing all necessary metadata
    to reconstruct the CodeChunk from the vector store.
    """
    return {
        "chunk_id": chunk.id,
        "file_path": chunk.file_path,
        "language": chunk.language,
        "symbol_name": chunk.symbol_name,
        "symbol_type": chunk.symbol_type,
        "parent_symbol": chunk.parent_symbol,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "code": chunk.code,
        "metadata": chunk.metadata if isinstance(chunk.metadata, dict) else {},
    }


class QdrantVectorStore:
    """
    Manages local and remote vector storage operations using Qdrant.
    Handles collection lifecycle, batch upserts, deterministic point ID mapping,
    and metadata retrieval.
    """

    def __init__(
        self,
        storage_path: Optional[str] = DEFAULT_STORAGE_PATH,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        location: Optional[str] = None,
    ):
        """
        Initializes the Qdrant client.

        Args:
            storage_path: Path to local persistent storage folder (used if url/location not given).
            url: URL of a remote or local Qdrant server (e.g. 'http://localhost:6333').
            api_key: Optional API key for remote Qdrant authentication.
            location: Special location string (e.g. ':memory:' for in-memory testing).
        """
        self.storage_path = storage_path
        self.url = url
        self.location = location

        if location is not None:
            self.client = QdrantClient(location=location)
        elif url is not None:
            self.client = QdrantClient(url=url, api_key=api_key)
        elif storage_path is not None:
            path_obj = Path(storage_path)
            path_obj.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(path_obj))
        else:
            self.client = QdrantClient(location=":memory:")

    def collection_exists(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> bool:
        """Checks if a collection exists in the vector database."""
        try:
            return bool(self.client.collection_exists(collection_name=collection_name))
        except Exception as e:
            raise VectorStoreError(f"Failed to check if collection '{collection_name}' exists: {e}") from e

    def create_collection(
        self,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        vector_size: int = 384,
        distance: Union[Distance, str] = DEFAULT_DISTANCE,
        recreate: bool = False,
    ) -> bool:
        """
        Safely creates a Qdrant collection with the specified vector dimension and distance metric.
        If the collection already exists and recreate=False, validates that the existing configuration
        matches the requested vector size and distance metric.

        Args:
            collection_name: Name of the collection.
            vector_size: Dimensionality of embedding vectors (e.g. 384 for bge-small).
            distance: Distance metric (Cosine, Euclidean, Dot).
            recreate: If True, drops any existing collection and recreates it.

        Returns:
            True if a new collection was created, False if existing collection was validated.
        """
        if isinstance(distance, str):
            dist_map = {
                "cosine": Distance.COSINE,
                "euclid": Distance.EUCLID,
                "euclidean": Distance.EUCLID,
                "dot": Distance.DOT,
            }
            distance = dist_map.get(distance.lower(), Distance.COSINE)

        if vector_size <= 0:
            raise ValidationError(f"Vector size must be a positive integer, got {vector_size}")

        try:
            exists = self.collection_exists(collection_name)
        except Exception as e:
            raise VectorStoreError(f"Error checking collection existence: {e}") from e

        if exists:
            if recreate:
                try:
                    self.client.delete_collection(collection_name=collection_name)
                except Exception as e:
                    raise VectorStoreError(f"Failed to delete existing collection '{collection_name}': {e}") from e
            else:
                # Validate existing collection configuration
                info = self.get_collection_info(collection_name)
                existing_dim = info.get("vector_size")
                existing_dist = info.get("distance", "").lower()
                expected_dist = distance.value.lower() if hasattr(distance, "value") else str(distance).lower()

                if existing_dim is not None and existing_dim != vector_size:
                    raise ConfigurationMismatchError(
                        f"Embedding configuration mismatch for collection '{collection_name}'.\n"
                        f"Existing collection dimension: {existing_dim}\n"
                        f"Current model dimension: {vector_size}\n"
                        f"Please create a new collection or reset the existing collection."
                    )
                if existing_dist and existing_dist != expected_dist:
                    raise ConfigurationMismatchError(
                        f"Distance metric mismatch for collection '{collection_name}'.\n"
                        f"Existing collection distance: {existing_dist}\n"
                        f"Requested distance: {expected_dist}\n"
                        f"Please create a new collection or reset the existing collection."
                    )
                return False

        try:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=distance),
            )
            return True
        except Exception as e:
            raise VectorStoreError(f"Failed to create collection '{collection_name}': {e}") from e

    def get_collection_info(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> Dict[str, Any]:
        """
        Retrieves metadata and statistics about the specified collection.

        Args:
            collection_name: Name of the collection.

        Returns:
            Dictionary containing collection details.
        """
        if not self.collection_exists(collection_name):
            raise VectorStoreError(f"Collection '{collection_name}' does not exist.")

        try:
            info = self.client.get_collection(collection_name=collection_name)
        except Exception as e:
            raise VectorStoreError(f"Failed to retrieve collection info for '{collection_name}': {e}") from e

        # Extract vector parameters
        vector_size = None
        distance_name = "Unknown"
        vectors_config = getattr(info.config.params, "vectors", None)
        if isinstance(vectors_config, VectorParams):
            vector_size = vectors_config.size
            distance_name = vectors_config.distance.value if hasattr(vectors_config.distance, "value") else str(vectors_config.distance)
        elif isinstance(vectors_config, dict):
            # If multiple named vectors exist, get default or first
            first_param = next(iter(vectors_config.values()), None)
            if first_param:
                vector_size = first_param.size
                distance_name = first_param.distance.value if hasattr(first_param.distance, "value") else str(first_param.distance)

        status_str = "Ready"
        if hasattr(info, "status"):
            raw_status = str(info.status).lower()
            if "green" in raw_status or "ready" in raw_status:
                status_str = "Ready"
            elif "yellow" in raw_status:
                status_str = "Optimizing"
            elif "grey" in raw_status:
                status_str = "Pending"
            elif "red" in raw_status:
                status_str = "Error"
            else:
                status_str = str(info.status)

        points_count = getattr(info, "points_count", 0) or 0

        return {
            "collection_name": collection_name,
            "vector_size": vector_size,
            "distance": distance_name,
            "points": points_count,
            "status": status_str,
            "vectors_count": getattr(info, "vectors_count", points_count),
        }

    def validate_inputs(
        self,
        chunks: List[CodeChunk],
        vectors: List[List[float]],
        expected_dim: Optional[int] = None,
    ) -> None:
        """
        Validates CodeChunks and vectors before database insertion.

        Raises:
            ValidationError: If any chunk or vector is malformed.
        """
        if len(chunks) != len(vectors):
            raise ValidationError(
                f"Mismatch between number of chunks ({len(chunks)}) and vectors ({len(vectors)})."
            )

        if not chunks:
            return

        dim = expected_dim if expected_dim is not None else len(vectors[0])

        for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
            if not isinstance(chunk, CodeChunk):
                raise ValidationError(f"Item at index {idx} is not an instance of CodeChunk.")
            if not chunk.id or not isinstance(chunk.id, str):
                raise ValidationError(f"Chunk at index {idx} has invalid or missing id.")
            if not chunk.file_path or not isinstance(chunk.file_path, str):
                raise ValidationError(f"Chunk '{chunk.id}' has missing or invalid file_path.")
            if not isinstance(vec, (list, tuple)):
                raise ValidationError(f"Vector for chunk '{chunk.id}' must be a list of numbers.")
            if len(vec) == 0:
                raise ValidationError(f"Vector for chunk '{chunk.id}' is empty.")
            if len(vec) != dim:
                raise ValidationError(
                    f"Vector dimension mismatch for chunk '{chunk.id}': expected {dim}, got {len(vec)}."
                )
            for v_idx, val in enumerate(vec):
                if not isinstance(val, (int, float)):
                    raise ValidationError(
                        f"Non-numeric value at index {v_idx} in vector for chunk '{chunk.id}': {val}"
                    )

    def upsert_chunks(
        self,
        chunks: List[CodeChunk],
        vectors: List[List[float]],
        collection_name: str = DEFAULT_COLLECTION_NAME,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> int:
        """
        Upserts a batch of CodeChunks and their embedding vectors into Qdrant.
        If a point with the same deterministic ID already exists, it is updated.

        Args:
            chunks: List of CodeChunk objects.
            vectors: Corresponding embedding vectors.
            collection_name: Target collection name.
            batch_size: Number of points per upsert request.

        Returns:
            Total number of points upserted.
        """
        if not chunks:
            return 0

        # Ensure collection exists; if not, create it
        first_dim = len(vectors[0]) if vectors and len(vectors) > 0 else 384
        if not self.collection_exists(collection_name):
            self.create_collection(collection_name=collection_name, vector_size=first_dim)
        else:
            info = self.get_collection_info(collection_name)
            first_dim = info.get("vector_size") or first_dim

        # Validate inputs
        self.validate_inputs(chunks, vectors, expected_dim=first_dim)

        points: List[PointStruct] = []
        for chunk, vec in zip(chunks, vectors):
            pt_id = chunk_id_to_point_id(chunk.id)
            payload = build_chunk_payload(chunk)
            points.append(PointStruct(id=pt_id, vector=vec, payload=payload))

        total_points = len(points)
        try:
            for i in range(0, total_points, batch_size):
                batch = points[i : i + batch_size]
                self.client.upsert(
                    collection_name=collection_name,
                    points=batch,
                )
        except Exception as e:
            raise VectorStoreError(f"Failed to upsert points into collection '{collection_name}': {e}") from e

        return total_points

    def get_by_id(
        self,
        chunk_id: str,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves a stored CodeChunk payload by its chunk ID or point ID.

        Args:
            chunk_id: The CodeChunk id (e.g. SHA-256 hash or mock id) or the point UUID.
            collection_name: Target collection name.

        Returns:
            Dictionary containing the point payload, or None if not found.
        """
        if not chunk_id or not isinstance(chunk_id, str):
            return None

        if not self.collection_exists(collection_name):
            return None

        # 1. Try lookup by deterministic UUID
        try:
            pt_id = chunk_id_to_point_id(chunk_id)
            records = self.client.retrieve(
                collection_name=collection_name,
                ids=[pt_id],
                with_payload=True,
                with_vectors=False,
            )
            if records and len(records) > 0:
                return records[0].payload
        except Exception:
            pass

        # 2. Try direct lookup in case chunk_id is already a raw UUID
        try:
            records = self.client.retrieve(
                collection_name=collection_name,
                ids=[chunk_id],
                with_payload=True,
                with_vectors=False,
            )
            if records and len(records) > 0:
                return records[0].payload
        except Exception:
            pass

        # 3. Fallback: scroll filter by payload chunk_id field
        try:
            records, _ = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="chunk_id",
                            match=MatchValue(value=chunk_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if records and len(records) > 0:
                return records[0].payload
        except Exception:
            pass

        return None

    def search(
        self,
        query_vector: List[float],
        collection_name: str = DEFAULT_COLLECTION_NAME,
        limit: int = 5,
        score_threshold: Optional[float] = None,
        query_filter: Optional[Filter] = None,
    ) -> List[Any]:
        """
        Searches collection for points closest/most similar to the query vector.

        Args:
            query_vector: Query embedding vector.
            collection_name: Name of the collection to search.
            limit: Maximum number of points to retrieve.
            score_threshold: Minimum similarity score cutoff.
            query_filter: Optional Qdrant filter condition.

        Returns:
            List of ScoredPoint objects from Qdrant.
        """
        if not self.collection_exists(collection_name):
            raise VectorStoreError(f"Collection '{collection_name}' does not exist.")

        if not query_vector or len(query_vector) == 0:
            raise ValidationError("Query vector cannot be empty.")

        try:
            res = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
                with_payload=True,
                with_vectors=False,
            )
            return res.points
        except Exception as e:
            raise VectorStoreError(f"Failed to execute vector search on '{collection_name}': {e}") from e

    def delete_collection(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> bool:
        """
        Deletes a collection from the vector database.

        Args:
            collection_name: Name of the collection to delete.

        Returns:
            True if collection was deleted, False if it did not exist.
        """
        if not self.collection_exists(collection_name):
            return False

        try:
            self.client.delete_collection(collection_name=collection_name)
            return True
        except Exception as e:
            raise VectorStoreError(f"Failed to delete collection '{collection_name}': {e}") from e

    def close(self) -> None:
        """Closes the underlying client connection if supported."""
        if hasattr(self.client, "close"):
            try:
                self.client.close()
            except Exception:
                pass
