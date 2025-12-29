"""Embeddings generation using official OpenAI SDK."""

import logging
from typing import List, Optional

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingsClient:
    """Client for generating text embeddings using OpenAI SDK."""

    def __init__(self):
        self.settings = get_settings()
        self.model = self.settings.embedding_model
        self.dimension = self.settings.embedding_dimension
        
        # Initialize OpenAI client for embeddings
        api_url = self.settings.embedding_api_url.rstrip("/")
        
        if "api.openai.com" in api_url:
            # Official OpenAI - use default
            self.client = AsyncOpenAI(
                api_key=self.settings.embedding_api_key,
            )
        else:
            # Third-party API - set base_url
            if not api_url.endswith("/v1"):
                api_url = f"{api_url}/v1"
            self.client = AsyncOpenAI(
                api_key=self.settings.embedding_api_key,
                base_url=api_url,
            )

    async def create_embedding(self, text: str) -> List[float]:
        """Create an embedding for a single text using OpenAI SDK.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding API error: {e}", exc_info=True)
            raise

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
        all_embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                )
                
                # Extract embeddings in order
                batch_embeddings = [item.embedding for item in response.data]
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
