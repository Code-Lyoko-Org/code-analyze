"""Configuration management using Pydantic Settings."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Configuration
    llm_api_url: str = "https://x666.me"
    llm_api_key: str = ""
    llm_model: str = "gemini-2.5-pro"

    # Qdrant Configuration
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "code_blocks"

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"

    # App Configuration
    debug: bool = False
    temp_dir: str = "/tmp/code-analyze"

    # Embedding Configuration (Ollama)
    embedding_api_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text:latest"
    embedding_dimension: int = 768  # nomic-embed-text dimension

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

    # Embedding settings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # Celery worker settings
    celery_concurrency: int = 4

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
