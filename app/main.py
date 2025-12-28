"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import review
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="AI Code Reviewer",
    description="AI Agent for analyzing codebases and generating feature location reports",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(review.router, prefix="/api", tags=["review"])


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "AI Code Reviewer",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "review": "POST /api/review",
            "health": "GET /api/health",
        },
    }


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    import os
    from pathlib import Path
    
    # Ensure temp directory exists
    temp_dir = Path(settings.temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    if settings.debug:
        print(f"Debug mode enabled")
        print(f"LLM API URL: {settings.llm_api_url}")
        print(f"Qdrant: {settings.qdrant_host}:{settings.qdrant_port}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    pass
