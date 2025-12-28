"""Embeddings generation using OpenAI-compatible API."""

import httpx
from typing import List, Optional

from app.config import get_settings


class EmbeddingsClient:
    """Client for generating text embeddings."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.llm_api_url.rstrip("/")
        self.api_key = self.settings.llm_api_key
        self.model = self.settings.embedding_model
        self.dimension = self.settings.embedding_dimension

    async def create_embedding(self, text: str) -> List[float]:
        """Create an embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        url = f"{self.base_url}/v1/embeddings"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        payload = {
            "model": self.model,
            "input": text,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
        return data["data"][0]["embedding"]

    async def create_embeddings_batch(
        self, 
        texts: List[str],
        batch_size: int = 10,
    ) -> List[List[float]]:
        """Create embeddings for multiple texts in batches.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per batch request
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            url = f"{self.base_url}/v1/embeddings"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            
            payload = {
                "model": self.model,
                "input": batch,
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            
            # Sort by index to maintain order
            batch_embeddings = sorted(data["data"], key=lambda x: x["index"])
            embeddings.extend([e["embedding"] for e in batch_embeddings])
            
        return embeddings


# Singleton instance
_embeddings_client: Optional[EmbeddingsClient] = None


def get_embeddings_client() -> EmbeddingsClient:
    """Get the embeddings client singleton."""
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = EmbeddingsClient()
    return _embeddings_client
