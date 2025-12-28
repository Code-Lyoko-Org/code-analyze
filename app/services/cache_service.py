"""Redis cache service for caching code analysis results."""

import hashlib
import json
from typing import Optional, List, Tuple, Any
import redis

from app.config import get_settings
from app.models.schemas import CodeDefinition


class CacheService:
    """Service for caching code processing results in Redis."""

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[redis.Redis] = None
        # ZIP processing cache TTL: 24 hours
        self.zip_processing_ttl = 86400

    @property
    def client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(self.settings.redis_url)
        return self._client

    @staticmethod
    def calculate_md5(content: bytes) -> str:
        """Calculate MD5 hash of content.
        
        Args:
            content: Binary content to hash
            
        Returns:
            MD5 hex digest string
        """
        return hashlib.md5(content).hexdigest()

    def _get_zip_cache_key(self, zip_md5: str) -> str:
        """Get cache key for ZIP processing result."""
        return f"code_analyze:zip:{zip_md5}"

    def get_cached_definitions(
        self, 
        zip_content: bytes,
    ) -> Tuple[Optional[str], Optional[List[dict]]]:
        """Get cached processing result for a ZIP file.
        
        Args:
            zip_content: Binary content of the ZIP file
            
        Returns:
            Tuple of (session_id, definitions_as_dicts) if cached, (None, None) if not
        """
        zip_md5 = self.calculate_md5(zip_content)
        cache_key = self._get_zip_cache_key(zip_md5)
        
        try:
            cached = self.client.get(cache_key)
            if cached:
                data = json.loads(cached)
                return data.get("session_id"), data.get("definitions")
        except Exception as e:
            print(f"Cache read failed: {e}")
        
        return None, None

    def cache_definitions(
        self,
        zip_content: bytes,
        session_id: str,
        definitions: List[CodeDefinition],
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache processing result for a ZIP file.
        
        Args:
            zip_content: Binary content of the ZIP file
            session_id: Session ID used for this processing
            definitions: List of code definitions extracted
            ttl: Time-to-live in seconds (default: 24 hours)
            
        Returns:
            True if cached successfully
        """
        zip_md5 = self.calculate_md5(zip_content)
        cache_key = self._get_zip_cache_key(zip_md5)
        
        # Convert definitions to dicts
        definitions_data = [d.model_dump() for d in definitions]
        
        data = {
            "session_id": session_id,
            "definitions": definitions_data,
            "zip_md5": zip_md5,
        }
        
        try:
            self.client.setex(
                cache_key,
                ttl or self.zip_processing_ttl,
                json.dumps(data, ensure_ascii=False),
            )
            return True
        except Exception as e:
            print(f"Cache write failed: {e}")
            return False

    def is_zip_processed(self, zip_content: bytes) -> bool:
        """Check if a ZIP file has been processed before.
        
        Args:
            zip_content: Binary content of the ZIP file
            
        Returns:
            True if ZIP was previously processed
        """
        session_id, definitions = self.get_cached_definitions(zip_content)
        return session_id is not None and definitions is not None

    def invalidate_zip_cache(self, zip_content: bytes) -> bool:
        """Invalidate cached processing for a ZIP file.
        
        Args:
            zip_content: Binary content of the ZIP file
            
        Returns:
            True if invalidated successfully
        """
        zip_md5 = self.calculate_md5(zip_content)
        cache_key = self._get_zip_cache_key(zip_md5)
        
        try:
            self.client.delete(cache_key)
            return True
        except Exception as e:
            print(f"Cache invalidate failed: {e}")
            return False


# Singleton instance
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get cache service singleton."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
