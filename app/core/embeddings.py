"""Embeddings generation using OpenAI-compatible API."""

import httpx
import logging
from typing import List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingsClient:
    """Client for generating text embeddings using OpenAI API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.embedding_api_url.rstrip("/")
        self.model = self.settings.embedding_model
        self.dimension = self.settings.embedding_dimension
        self.api_key = self.settings.embedding_api_key

    async def create_embedding(self, text: str) -> List[float]:
        """Create an embedding for a single text using OpenAI API.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        # Build URL - handle both base URLs with and without /v1
        if self.base_url.endswith("/v1"):
            url = f"{self.base_url}/embeddings"
        else:
            url = f"{self.base_url}/v1/embeddings"
        
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        payload = {
            "model": self.model,
            "input": text,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        # OpenAI API returns: {"data": [{"embedding": [...]}]}
        return data["data"][0]["embedding"]

    async def create_embeddings_batch(
        self, 
        texts: List[str],
        batch_size: int = 100,
    ) -> List[List[float]]:
        """Create embeddings for multiple texts using OpenAI batch API.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call (OpenAI supports up to 2048)
            
        Returns:
            List of embedding vectors (same order as input texts)
        """
        # Build URL - handle both base URLs with and without /v1
        if self.base_url.endswith("/v1"):
            url = f"{self.base_url}/embeddings"
        else:
            url = f"{self.base_url}/v1/embeddings"
        
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        all_embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            payload = {
                "model": self.model,
                "input": batch,
            }
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            
            # Extract embeddings in order
            batch_embeddings = [item["embedding"] for item in data["data"]]
            all_embeddings.extend(batch_embeddings)
            
            logger.info(f"Embedded batch {i//batch_size + 1}, total: {len(all_embeddings)}/{len(texts)}")
        
        return all_embeddings


# Singleton instance
_embeddings_client: Optional[EmbeddingsClient] = None


def get_embeddings_client() -> EmbeddingsClient:
    """Get the embeddings client singleton."""
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = EmbeddingsClient()
    return _embeddings_client
