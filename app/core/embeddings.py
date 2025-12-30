"""Embeddings generation using OpenAI-compatible API format."""

import httpx
import logging
from typing import List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingsClient:
    """Client for generating text embeddings using OpenAI-compatible API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.embedding_api_url.rstrip("/")
        self.api_key = self.settings.embedding_api_key
        self.model = self.settings.embedding_model
        self.dimension = self.settings.embedding_dimension

    async def create_embedding(self, text: str) -> List[float]:
        """Create an embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        embeddings = await self.create_embeddings_batch([text])
        return embeddings[0]

    async def create_embeddings_batch(
        self, 
        texts: List[str],
        batch_size: int = 32,
    ) -> List[List[float]]:
        """Create embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call
            
        Returns:
            List of embedding vectors (same order as input texts)
        """
        # Build URL
        if self.base_url.endswith("/v1"):
            url = f"{self.base_url}/embeddings"
        else:
            url = f"{self.base_url}/v1/embeddings"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        all_embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            payload = {
                "model": self.model,
                "input": batch,
            }
            
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    
                    if response.status_code != 200:
                        logger.error(f"Embedding API error: {response.status_code} - {response.text[:500]}")
                        response.raise_for_status()
                    
                    data = response.json()
                
                if "data" not in data:
                    raise ValueError("Embedding API 响应缺少 data 字段")
                
                # Extract embeddings in order
                batch_embeddings = [item["embedding"] for item in data["data"]]
                all_embeddings.extend(batch_embeddings)
                
                logger.info(f"Embedded batch {i//batch_size + 1}, total: {len(all_embeddings)}/{len(texts)}")
                
            except Exception as e:
                logger.error(f"Embedding batch failed: {e}", exc_info=True)
                raise
        
        return all_embeddings


# Singleton instance
_embeddings_client: Optional[EmbeddingsClient] = None


def get_embeddings_client() -> EmbeddingsClient:
    """Get the embeddings client singleton."""
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = EmbeddingsClient()
    return _embeddings_client
