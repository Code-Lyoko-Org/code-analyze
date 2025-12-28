"""Celery tasks for LLM analysis."""

import asyncio
from typing import List, Dict, Any

from celery import group
from celery.result import AsyncResult

from app.celery_app import celery_app


def run_async(coro):
    """Run async coroutine in sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(bind=True, max_retries=2)
def analyze_feature_task(
    self,
    feature_description: str,
    code_structure: str,
    feature_index: int,
) -> Dict[str, Any]:
    """Analyze a single feature using LLM.
    
    Args:
        feature_description: Description of the feature
        code_structure: String representation of code structure
        feature_index: Index for ordering results
        
    Returns:
        Dict with feature analysis result
    """
    from app.core.llm_client import get_llm_client
    
    try:
        client = get_llm_client()
        result = run_async(client.analyze_feature(feature_description, code_structure))
        return {
            "index": feature_index,
            "success": True,
            "result": result,
        }
    except Exception as e:
        return {
            "index": feature_index,
            "success": False,
            "error": str(e),
            "result": {
                "feature_description": feature_description,
                "implementation_location": [],
            },
        }


@celery_app.task(bind=True)
def analyze_all_features_task(
    self,
    features: List[str],
    code_structure: str,
) -> Dict[str, Any]:
    """Analyze all features in parallel using Celery group.
    
    Args:
        features: List of feature descriptions
        code_structure: String representation of code structure
        
    Returns:
        Dict with all feature analysis results
    """
    try:
        # Create a group of tasks
        tasks = group([
            analyze_feature_task.s(feature, code_structure, i)
            for i, feature in enumerate(features)
        ])
        
        # Execute the group and wait for results
        result = tasks.apply_async()
        results = result.get(timeout=300)  # 5 minute timeout
        
        # Sort by index and extract results
        sorted_results = sorted(results, key=lambda x: x["index"])
        feature_analyses = [r["result"] for r in sorted_results]
        
        return {
            "success": True,
            "feature_analysis": feature_analyses,
            "failed_count": sum(1 for r in sorted_results if not r["success"]),
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


@celery_app.task(bind=True)
def generate_execution_plan_task(
    self,
    code_structure: str,
) -> Dict[str, Any]:
    """Generate execution plan for the project.
    
    Args:
        code_structure: String representation of code structure
        
    Returns:
        Dict with execution plan
    """
    from app.core.llm_client import get_llm_client
    
    try:
        client = get_llm_client()
        plan = run_async(client.generate_execution_plan(code_structure))
        return {"success": True, "execution_plan": plan}
    except Exception as e:
        return {"success": False, "error": str(e), "execution_plan": ""}


def submit_analysis_job(
    features: List[str],
    code_structure: str,
) -> str:
    """Submit a feature analysis job to Celery.
    
    Args:
        features: List of feature descriptions
        code_structure: Code structure string
        
    Returns:
        Task ID for tracking
    """
    task = analyze_all_features_task.delay(features, code_structure)
    return task.id


def get_analysis_status(task_id: str) -> Dict[str, Any]:
    """Get status of an analysis job.
    
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
