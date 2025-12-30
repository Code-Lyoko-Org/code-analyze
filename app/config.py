"""Configuration management using Pydantic Settings."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Configuration (supports OpenAI-compatible APIs)
    llm_api_url: str = "https://api.openai.com/v1"  # Base URL for LLM API
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Qdrant Configuration
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "code_blocks"

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"

    # App Configuration
    debug: bool = False
    temp_dir: str = "/tmp/code-analyze"

    # Embedding Configuration (supports OpenAI-compatible APIs)
    embedding_api_url: str = "https://api.openai.com/v1"  # Base URL for Embedding API
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # Supported file extensions for code analysis
    supported_extensions: List[str] = [
        ".ts", ".tsx", ".js", ".jsx",  # TypeScript/JavaScript
        ".py",  # Python
        ".java",  # Java
        ".go",  # Go
        ".rs",  # Rust
        ".rb",  # Ruby
        ".php",  # PHP
        ".cs",  # C#
        ".cpp", ".c", ".h", ".hpp",  # C/C++
    ]

    # Directories to ignore during code scanning
    ignore_dirs: List[str] = [
        "node_modules",
        ".git",
        "__pycache__",
        "venv",
        "env",
        ".venv",
        "dist",
        "build",
        ".next",
        "coverage",
        ".cache",
        "target",  # Rust/Java
    ]

    # Code Size Limits
    max_file_size_bytes: int = 500 * 1024  # 500KB, skip larger files
    max_block_chars: int = 1000            # Max chars per code block
    max_llm_context_chars: int = 50000     # Max chars for LLM prompt

    # Celery worker settings
    celery_concurrency: int = 4

    # Langfuse Configuration (optional, for LLM observability)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra env vars without error


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
