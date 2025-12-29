"""Review API endpoint for code analysis."""

import uuid
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, UploadFile, BackgroundTasks

# Configure logger
logger = logging.getLogger(__name__)

from app.services.file_extractor import FileExtractor
from app.services.code_parser import CodeParser
from app.services.code_indexer import CodeIndexer
from app.services.feature_analyzer import FeatureAnalyzer
from app.services.cache_service import get_cache_service
from app.core.embeddings import get_embeddings_client
from app.models.schemas import AnalysisReport, ReviewResponse, CodeDefinition


router = APIRouter()


@router.post("/review", response_model=ReviewResponse)
async def review_code(
    background_tasks: BackgroundTasks,
    problem_description: str = Form(..., description="Description of required features"),
    code_zip: UploadFile = File(..., description="ZIP file containing the code"),
) -> ReviewResponse:
    """Analyze a codebase and generate a feature location report.
    
    This endpoint accepts a ZIP file containing source code and a problem
    description, then returns a JSON report mapping features to code locations.
    
    Includes functional verification: generates integration tests and executes them.
    """
    # Always skip cache and enable verification
    skip_cache = True
    enable_verification = True
    # Read ZIP content first
    zip_content = await code_zip.read()
    cache_service = get_cache_service()
    
    session_id: Optional[str] = None
    definitions: list = []
    cache_hit = False
    
    # Check if ZIP was already processed
    if not skip_cache:
        try:
            cached_session_id, cached_definitions = cache_service.get_cached_definitions(zip_content)
            if cached_session_id and cached_definitions:
                session_id = cached_session_id
                definitions = [CodeDefinition(**d) for d in cached_definitions]
                cache_hit = True
                print(f"Cache hit! Reusing {len(definitions)} definitions from session {session_id}")
        except Exception as e:
            print(f"Cache check failed: {e}")
    
    file_extractor = FileExtractor()
    project_root: Optional[str] = None
    
    try:
        # Process ZIP if not cached
        if not cache_hit:
            session_id = str(uuid.uuid4())
            
            # 1. Extract ZIP file
            project_root, file_paths = file_extractor.extract_zip(zip_content, session_id)
            
            if not file_paths:
                return ReviewResponse(
                    success=False,
                    error="No supported files found in the uploaded ZIP",
                )
            
            # 2. Parse code to extract definitions
            code_parser = CodeParser()
            definitions = code_parser.parse_files(project_root, file_paths)
            
            if not definitions:
                return ReviewResponse(
                    success=False,
                    error="No code definitions (functions, classes) found in the codebase",
                )
            
            # 3. Generate embeddings and index code (for semantic search)
            try:
                embeddings_client = get_embeddings_client()
                code_indexer = CodeIndexer()
                
                # Generate texts for embedding
                texts = [
                    f"{d.definition_type} {d.name}\n{d.signature or ''}\n{d.content[:500]}"
                    for d in definitions
                ]
                
                # Generate embeddings in batches
                embeddings = await embeddings_client.create_embeddings_batch(texts)
                
                # Index into vector store
                code_indexer.index_definitions(definitions, embeddings, session_id)
            except Exception as e:
                # Continue without vector search if embedding/indexing fails
                print(f"Indexing failed (continuing without semantic search): {e}")
            
            # 4. Cache the processing result
            try:
                cache_service.cache_definitions(zip_content, session_id, definitions)
                print(f"Cached {len(definitions)} definitions for session {session_id}")
            except Exception as e:
                print(f"Failed to cache processing result: {e}")
            
            # Clean up extracted files only if verification is not enabled
            # (verification needs the project files to run tests)
            if not enable_verification:
                file_extractor.cleanup(session_id)
            else:
                # Keep project_root for verification
                project_root = project_root
        
        # 5. Analyze features using LLM (always run, as query may differ)
        feature_analyzer = FeatureAnalyzer()
        report = await feature_analyzer.generate_report(
            problem_description=problem_description,
            definitions=definitions,
            session_id=session_id,
            enable_verification=enable_verification,
            project_path=project_root,
        )
        
        # Clean up after verification if it was enabled
        if enable_verification and project_root:
            background_tasks.add_task(file_extractor.cleanup, session_id)
        
        return ReviewResponse(
            success=True,
            report=report,
        )
        
    except httpx.TimeoutException:
        # LLM API timeout
        logger.error("LLM API timeout during analysis", exc_info=True)
        return ReviewResponse(
            success=False,
            error="分析超时，请稍后重试。LLM API 响应时间过长。",
        )
    except httpx.HTTPStatusError as e:
        # LLM API error
        logger.error(f"LLM API error: {e.response.status_code}", exc_info=True)
        return ReviewResponse(
            success=False,
            error=f"LLM API 请求失败 (HTTP {e.response.status_code})，请检查配置。",
        )
    except Exception as e:
        # Clean up on error
        if not cache_hit:
            try:
                file_extractor.cleanup(session_id)
                code_indexer = CodeIndexer()
                code_indexer.delete_session(session_id)
            except:
                pass
        
        # Log the full traceback, return friendly message
        logger.error(f"Analysis failed: {e}", exc_info=True)
        
        # Return user-friendly error message
        error_msg = "分析过程中发生错误，请稍后重试。"
        if "timeout" in str(e).lower():
            error_msg = "分析超时，请稍后重试。"
        elif "connection" in str(e).lower():
            error_msg = "无法连接到 LLM 服务，请检查配置。"
        
        return ReviewResponse(
            success=False,
            error=error_msg,
        )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
