"""Code indexer service for vector storage and semantic search."""

import hashlib
import uuid
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from app.config import get_settings
from app.models.schemas import CodeDefinition, CodeBlock


class CodeIndexer:
    """Service for indexing code blocks in vector storage."""

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[QdrantClient] = None
        self._collection_initialized = False

    @property
    def client(self) -> QdrantClient:
        """Get or create Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(
                host=self.settings.qdrant_host,
                port=self.settings.qdrant_port,
            )
        return self._client

    def _ensure_collection(self) -> None:
        """Ensure the collection exists."""
        if self._collection_initialized:
            return
        
        collection_name = self.settings.qdrant_collection
        
        try:
            self.client.get_collection(collection_name)
        except Exception:
            # Create collection if it doesn't exist
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=self.settings.embedding_dimension,
                    distance=qdrant_models.Distance.COSINE,
                ),
            )
        
        self._collection_initialized = True

    def _generate_point_id(self, file_path: str, start_line: int, name: str) -> str:
        """Generate a deterministic point ID.
        
        Args:
            file_path: Path to the file
            start_line: Start line of the code block
            name: Name of the definition
            
        Returns:
            UUID string
        """
        content = f"{file_path}:{start_line}:{name}"
        hash_bytes = hashlib.sha256(content.encode()).digest()[:16]
        return str(uuid.UUID(bytes=hash_bytes))

    def index_definitions(
        self,
        definitions: List[CodeDefinition],
        embeddings: List[List[float]],
        session_id: str,
    ) -> int:
        """Index code definitions with their embeddings.
        
        Args:
            definitions: List of code definitions
            embeddings: List of embedding vectors (same order as definitions)
            session_id: Session ID for grouping
            
        Returns:
            Number of points indexed
        """
        self._ensure_collection()
        
        if len(definitions) != len(embeddings):
            raise ValueError("Number of definitions must match number of embeddings")
        
        points = []
        for definition, embedding in zip(definitions, embeddings):
            point_id = self._generate_point_id(
                definition.file_path,
                definition.start_line,
                definition.name,
            )
            
            payload = {
                "session_id": session_id,
                "file_path": definition.file_path,
                "name": definition.name,
                "definition_type": definition.definition_type,
                "start_line": definition.start_line,
                "end_line": definition.end_line,
                "signature": definition.signature or "",
                "content": definition.content[:2000],  # Limit content size
            }
            
            points.append(qdrant_models.PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload,
            ))
        
        # Batch upsert
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self.client.upsert(
                collection_name=self.settings.qdrant_collection,
                points=batch,
            )
        
        return len(points)

    def search(
        self,
        query_vector: List[float],
        session_id: str,
        limit: int = 10,
        min_score: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Search for similar code blocks.
        
        Args:
            query_vector: Query embedding vector
            session_id: Session ID to filter by
            limit: Maximum number of results
            min_score: Minimum similarity score
            
        Returns:
            List of matching code blocks with scores
        """
        self._ensure_collection()
        
        results = self.client.search(
            collection_name=self.settings.qdrant_collection,
            query_vector=query_vector,
            limit=limit,
            score_threshold=min_score,
            query_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="session_id",
                        match=qdrant_models.MatchValue(value=session_id),
                    ),
                ]
            ),
        )
        
        return [
            {
                "score": result.score,
                "file_path": result.payload.get("file_path"),
                "name": result.payload.get("name"),
                "definition_type": result.payload.get("definition_type"),
                "start_line": result.payload.get("start_line"),
                "end_line": result.payload.get("end_line"),
                "signature": result.payload.get("signature"),
                "content": result.payload.get("content"),
            }
            for result in results
        ]

    def delete_session(self, session_id: str) -> None:
        """Delete all points for a session.
        
        Args:
            session_id: Session ID to delete
        """
        self._ensure_collection()
        
        self.client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="session_id",
                            match=qdrant_models.MatchValue(value=session_id),
                        ),
                    ]
                )
            ),
        )

    def get_all_definitions(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all indexed definitions for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            List of all code definitions
        """
        self._ensure_collection()
        
        results = []
        offset = None
        
        while True:
            records, offset = self.client.scroll(
                collection_name=self.settings.qdrant_collection,
                scroll_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="session_id",
                            match=qdrant_models.MatchValue(value=session_id),
                        ),
                    ]
                ),
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            
            for record in records:
                results.append(record.payload)
            
            if offset is None:
                break
        
        return results
