"""Feature analyzer service for LLM-based code analysis."""

import asyncio
import logging
from typing import List, Dict, Any, Optional

from app.core.llm_client import get_llm_client
from app.core.embeddings import get_embeddings_client
from app.services.code_indexer import CodeIndexer
from app.services.code_parser import CodeParser
from app.models.schemas import (
    CodeDefinition,
    FeatureAnalysis,
    AnalysisReport,
    ImplementationLocation,
    FunctionalVerification,
)

logger = logging.getLogger(__name__)


class FeatureAnalyzer:
    """Service for analyzing features and mapping them to code."""

    def __init__(self):
        self.llm_client = get_llm_client()
        self.embeddings_client = get_embeddings_client()
        self.code_indexer = CodeIndexer()
        self.code_parser = CodeParser()

    async def extract_features(self, problem_description: str) -> List[str]:
        """Extract individual features from problem description.
        
        Args:
            problem_description: Full requirement description
            
        Returns:
            List of individual feature descriptions
        """
        return await self.llm_client.extract_features(problem_description)

    async def analyze_single_feature(
        self,
        feature: str,
        code_structure: str,
        session_id: str,
    ) -> FeatureAnalysis:
        """Analyze where a single feature is implemented.
        
        Args:
            feature: Feature description
            code_structure: Code structure string
            session_id: Session ID for vector search
            
        Returns:
            FeatureAnalysis object
        """
        # First, try semantic search to find relevant code
        try:
            query_embedding = await self.embeddings_client.create_embedding(feature)
            search_results = self.code_indexer.search(
                query_vector=query_embedding,
                session_id=session_id,
                limit=5,
                min_score=0.3,
            )
            
            # Add search results to code structure
            if search_results:
                relevant_code = "\n\n### Relevant Code (by semantic search):\n"
                for result in search_results:
                    relevant_code += f"\n- {result['file_path']}: {result['name']} ({result['definition_type']}) lines {result['start_line']}-{result['end_line']}\n"
                    relevant_code += f"  ```\n  {result['content'][:300]}...\n  ```\n"
                code_structure = code_structure + relevant_code
        except Exception as e:
            # If semantic search fails, continue with just code structure
            print(f"Semantic search failed: {e}")

        # Use LLM to analyze
        result = await self.llm_client.analyze_feature(feature, code_structure)
        
        # Convert to FeatureAnalysis
        locations = []
        for loc in result.get("implementation_location", []):
            locations.append(ImplementationLocation(
                file=loc.get("file", ""),
                function=loc.get("function", ""),
                lines=loc.get("lines", ""),
                reason=loc.get("reason"),
            ))
        
        return FeatureAnalysis(
            feature_description=result.get("feature_description", feature),
            implementation_location=locations,
        )

    async def analyze_all_features(
        self,
        features: List[str],
        code_structure: str,
        session_id: str,
    ) -> List[FeatureAnalysis]:
        """Analyze all features in parallel.
        
        Args:
            features: List of feature descriptions
            code_structure: Code structure string
            session_id: Session ID
            
        Returns:
            List of FeatureAnalysis objects
        """
        # Create tasks for parallel execution
        tasks = [
            self.analyze_single_feature(feature, code_structure, session_id)
            for feature in features
        ]
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results
        analyses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Create empty analysis for failed ones
                analyses.append(FeatureAnalysis(
                    feature_description=features[i],
                    implementation_location=[],
                ))
            else:
                analyses.append(result)
        
        return analyses

    async def generate_report(
        self,
        problem_description: str,
        definitions: List[CodeDefinition],
        session_id: str,
        enable_verification: bool = False,
        project_path: Optional[str] = None,
    ) -> AnalysisReport:
        """Generate complete analysis report.
        
        Args:
            problem_description: Original requirement description
            definitions: List of code definitions
            session_id: Session ID
            enable_verification: Whether to generate and run tests
            project_path: Path to extracted project (required if enable_verification=True)
            
        Returns:
            Complete AnalysisReport
        """
        # Generate code structure
        code_structure = self.code_parser.generate_code_structure(definitions)
        
        # Extract features first (needed for analysis)
        features = await self.extract_features(problem_description)
        
        # Run feature analysis AND execution plan generation in parallel
        feature_analyses, execution_plan = await asyncio.gather(
            self.analyze_all_features(
                features=features,
                code_structure=code_structure,
                session_id=session_id,
            ),
            self.llm_client.generate_execution_plan(code_structure),
        )
        
        # Generate functional verification if requested
        functional_verification = None
        if enable_verification:
            functional_verification = await self._generate_verification(
                feature_analyses=feature_analyses,
                execution_plan=execution_plan,
                code_structure=code_structure,
                project_path=project_path,
            )
        
        return AnalysisReport(
            feature_analysis=feature_analyses,
            execution_plan_suggestion=execution_plan,
            functional_verification=functional_verification,
        )

    async def _generate_verification(
        self,
        feature_analyses: List[FeatureAnalysis],
        execution_plan: str,
        code_structure: str,
        project_path: Optional[str],
    ) -> Optional[FunctionalVerification]:
        """Generate and optionally execute tests for verification.
        
        Args:
            feature_analyses: List of analyzed features
            execution_plan: How to run the project
            code_structure: Code structure string
            project_path: Path to extracted project
            
        Returns:
            FunctionalVerification with generated tests and results
        """
        from app.services.test_generator import get_test_generator
        from app.services.docker_executor import get_docker_executor
        
        try:
            # Generate test code (with project_path for schema extraction)
            test_generator = get_test_generator()
            test_code = await test_generator.generate_test_code(
                feature_analysis=feature_analyses,
                execution_plan=execution_plan,
                code_structure=code_structure,
                project_path=project_path,
            )
            
            # Try to execute tests if project path is provided
            execution_result = None
            if project_path:
                try:
                    docker_executor = get_docker_executor()
                    project_type = test_generator._detect_project_type(execution_plan)
                    execution_result = await docker_executor.execute_tests(
                        project_path=project_path,
                        test_code=test_code,
                        project_type=project_type,
                    )
                except Exception as e:
                    logger.warning(f"Test execution failed: {e}")
                    # Still return verification with just generated code
            
            return FunctionalVerification(
                generated_test_code=test_code,
                execution_result=execution_result,
            )
            
        except Exception as e:
            logger.error(f"Verification generation failed: {e}", exc_info=True)
            return None

    async def generate_report_sync(
        self,
        problem_description: str,
        definitions: List[CodeDefinition],
        session_id: str,
    ) -> AnalysisReport:
        """Synchronous wrapper for generate_report.
        
        For use with Celery or other sync contexts.
        """
        return await self.generate_report(problem_description, definitions, session_id)
