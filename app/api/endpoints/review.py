"""Review API endpoint for code analysis."""

import uuid
import asyncio
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile, HTTPException, BackgroundTasks

from app.services.file_extractor import FileExtractor
from app.services.code_parser import CodeParser
from app.services.code_indexer import CodeIndexer
from app.services.feature_analyzer import FeatureAnalyzer
from app.core.embeddings import get_embeddings_client
from app.models.schemas import AnalysisReport, ReviewResponse


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
    """
    session_id = str(uuid.uuid4())
    file_extractor = FileExtractor()
    
    try:
        # 1. Extract ZIP file
        zip_content = await code_zip.read()
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
        
        # 4. Analyze features using LLM
        feature_analyzer = FeatureAnalyzer()
        report = await feature_analyzer.generate_report(
            problem_description=problem_description,
            definitions=definitions,
            session_id=session_id,
        )
        
        # 5. Schedule cleanup in background
        background_tasks.add_task(cleanup_session, session_id, file_extractor)
        
        return ReviewResponse(
            success=True,
            report=report,
        )
        
    except Exception as e:
        # Clean up on error
        try:
            file_extractor.cleanup(session_id)
            code_indexer = CodeIndexer()
            code_indexer.delete_session(session_id)
        except:
            pass
        
        import traceback
        return ReviewResponse(
            success=False,
            error=f"Analysis failed: {str(e)}\n{traceback.format_exc()}",
        )


async def cleanup_session(session_id: str, file_extractor: FileExtractor):
    """Clean up session resources."""
    try:
        file_extractor.cleanup(session_id)
        code_indexer = CodeIndexer()
        code_indexer.delete_session(session_id)
    except Exception as e:
        print(f"Cleanup failed for session {session_id}: {e}")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
