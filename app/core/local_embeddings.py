"""Local embeddings generation using HuggingFace Transformers.

Supports local models like Qwen/Qwen3-Embedding-0.6B.
Falls back to API-based embeddings if local model is not configured.
"""

import logging
from typing import List, Optional

import torch
from transformers import AutoModel, AutoTokenizer

from app.config import get_settings

logger = logging.getLogger(__name__)


class LocalEmbeddingsClient:
    """Client for generating text embeddings using local HuggingFace models."""

    def __init__(self):
        self.settings = get_settings()
        self.model_name = self.settings.embedding_model
        self.dimension = self.settings.embedding_dimension
        
        # Load model and tokenizer
        logger.info(f"Loading local embedding model: {self.model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(self.model_name, trust_remote_code=True)
        
        # Move to GPU if available
        self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = self.model.to(self.device)
        self.model.eval()
        
        logger.info(f"Embedding model loaded on {self.device}")

    def _mean_pooling(self, model_output, attention_mask):
        """Mean pooling - take average of all tokens."""
        token_embeddings = model_output[0]  # First element of model_output contains all token embeddings
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

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
            batch_size: Number of texts per batch
            
        Returns:
            List of embedding vectors
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            # Tokenize
            encoded_input = self.tokenizer(
                batch, 
                padding=True, 
                truncation=True, 
                max_length=512,
                return_tensors='pt'
            ).to(self.device)
            
            # Generate embeddings
            with torch.no_grad():
                model_output = self.model(**encoded_input)
            
            # Mean pooling
            embeddings = self._mean_pooling(model_output, encoded_input['attention_mask'])
            
            # Normalize
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            
            # Convert to list
            batch_embeddings = embeddings.cpu().numpy().tolist()
            all_embeddings.extend(batch_embeddings)
            
            logger.info(f"Embedded batch {i//batch_size + 1}, total: {len(all_embeddings)}/{len(texts)}")
        
        return all_embeddings


# Singleton instance
_local_embeddings_client: Optional[LocalEmbeddingsClient] = None


def get_local_embeddings_client() -> LocalEmbeddingsClient:
    """Get the local embeddings client singleton."""
    global _local_embeddings_client
    if _local_embeddings_client is None:
        _local_embeddings_client = LocalEmbeddingsClient()
    return _local_embeddings_client
