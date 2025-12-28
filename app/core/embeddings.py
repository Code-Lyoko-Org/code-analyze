"""Embeddings generation using Ollama API."""

import httpx
from typing import List, Optional

from app.config import get_settings


class EmbeddingsClient:
    """Client for generating text embeddings using Ollama."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.embedding_api_url.rstrip("/")
        self.model = self.settings.embedding_model
        self.dimension = self.settings.embedding_dimension

    async def create_embedding(self, text: str) -> List[float]:
        """Create an embedding for a single text using Ollama.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        url = f"{self.base_url}/api/embeddings"
        
        payload = {
            "model": self.model,
            "prompt": text,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
        return data["embedding"]

    async def create_embeddings_batch(
        self, 
        texts: List[str],
        batch_size: int = 10,
    ) -> List[List[float]]:
        """Create embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per batch (Ollama processes one at a time)
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for text in texts:
            embedding = await self.create_embedding(text)
            embeddings.append(embedding)
            
        return embeddings


# Singleton instance
_embeddings_client: Optional[EmbeddingsClient] = None


def get_embeddings_client() -> EmbeddingsClient:
    """Get the embeddings client singleton."""
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = EmbeddingsClient()
    return _embeddings_client
