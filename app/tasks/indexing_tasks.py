"""Celery tasks for code indexing."""

import asyncio
from typing import List, Dict, Any

from celery import group, chord
from celery.result import AsyncResult

from app.celery_app import celery_app
from app.services.code_indexer import CodeIndexer
from app.models.schemas import CodeDefinition


def run_async(coro):
    """Run async coroutine in sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(bind=True, max_retries=3)
def generate_embedding_task(
    self,
    text: str,
    index: int,
) -> Dict[str, Any]:
    """Generate embedding for a single text.
    
    Args:
        text: Text to embed
        index: Index in the original list (for ordering)
        
    Returns:
        Dict with index and embedding
    """
    from app.core.embeddings import get_embeddings_client
    
    try:
        client = get_embeddings_client()
        embedding = run_async(client.create_embedding(text))
        return {"index": index, "embedding": embedding, "success": True}
    except Exception as e:
        return {"index": index, "embedding": None, "success": False, "error": str(e)}


@celery_app.task(bind=True)
def index_batch_task(
    self,
    definitions_data: List[Dict[str, Any]],
    embeddings: List[List[float]],
    session_id: str,
) -> Dict[str, Any]:
    """Index a batch of definitions into vector store.
    
    Args:
        definitions_data: List of definition dicts
        embeddings: Corresponding embeddings
        session_id: Session ID
        
    Returns:
        Result dict with count
    """
    try:
        indexer = CodeIndexer()
        
        # Convert dicts back to CodeDefinition objects
        definitions = [CodeDefinition(**d) for d in definitions_data]
        
        count = indexer.index_definitions(definitions, embeddings, session_id)
        return {"success": True, "indexed_count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@celery_app.task(bind=True)
def process_and_index_definitions(
    self,
    definitions_data: List[Dict[str, Any]],
    session_id: str,
    batch_size: int = 10,
) -> Dict[str, Any]:
    """Process definitions: generate embeddings and index them.
    
    This is the main task that coordinates embedding generation and indexing.
    
    Args:
        definitions_data: List of definition dicts
        session_id: Session ID
        batch_size: Batch size for embedding generation
        
    Returns:
        Result dict with total indexed count
    """
    from app.core.embeddings import get_embeddings_client
    
    try:
        # Generate text for each definition
        texts = []
        for d in definitions_data:
            text = f"{d['definition_type']} {d['name']}\n{d.get('signature', '')}\n{d.get('content', '')[:500]}"
            texts.append(text)
        
        # Generate embeddings in batches
        client = get_embeddings_client()
        
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            embeddings = run_async(client.create_embeddings_batch(batch_texts))
            all_embeddings.extend(embeddings)
        
        # Convert dicts to CodeDefinition objects
        definitions = [CodeDefinition(**d) for d in definitions_data]
        
        # Index into vector store
        indexer = CodeIndexer()
        count = indexer.index_definitions(definitions, all_embeddings, session_id)
        
        return {"success": True, "indexed_count": count}
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


def submit_indexing_job(
    definitions: List[CodeDefinition],
    session_id: str,
) -> str:
    """Submit an indexing job to Celery.
    
    Args:
        definitions: List of code definitions
        session_id: Session ID
        
    Returns:
        Task ID for tracking
    """
    definitions_data = [d.model_dump() for d in definitions]
    task = process_and_index_definitions.delay(definitions_data, session_id)
    return task.id


def get_indexing_status(task_id: str) -> Dict[str, Any]:
    """Get status of an indexing job.
    
    Args:
        task_id: Celery task ID
        
    Returns:
        Status dict
    """
    result = AsyncResult(task_id, app=celery_app)
    
    if result.ready():
        if result.successful():
            return {"status": "completed", "result": result.get()}
        else:
            return {"status": "failed", "error": str(result.result)}
    elif result.state == "PENDING":
        return {"status": "pending"}
    else:
        return {"status": result.state}
