"""Test generator service for creating integration tests based on feature analysis."""

import logging
from pathlib import Path
from typing import List, Optional

from app.core.llm_client import get_llm_client
from app.models.schemas import FeatureAnalysis

logger = logging.getLogger(__name__)


class TestGenerator:
    """Service for generating integration tests based on feature analysis."""

    def __init__(self):
        self.llm_client = get_llm_client()

    async def generate_test_code(
        self,
        feature_analysis: List[FeatureAnalysis],
        execution_plan: str,
        code_structure: str,
        project_path: Optional[str] = None,
    ) -> str:
        """Generate integration test code based on feature analysis.
        
        Args:
            feature_analysis: List of analyzed features with implementation locations
            execution_plan: Suggestion on how to run the project
            code_structure: String representation of code structure
            project_path: Path to the extracted project (for schema extraction)
            
        Returns:
            Generated test code as a string
        """
        # Determine project type from execution_plan
        project_type = self._detect_project_type(execution_plan)
        
        # Format feature analysis for prompt
        features_text = self._format_features(feature_analysis)
        
        # Extract API schema if available
        schema_content = ""
        if project_path:
            schema_content = self._extract_schema(project_path, project_type)
        
        # Generate test code using LLM
        test_code = await self.llm_client.generate_test_code(
            features_text=features_text,
            execution_plan=execution_plan,
            code_structure=code_structure,
            project_type=project_type,
            schema_content=schema_content,
        )
        
        return test_code

    def _detect_project_type(self, execution_plan: str) -> str:
        """Detect project type from execution plan.
        
        Args:
            execution_plan: Execution plan text
            
        Returns:
            "nodejs" or "python"
        """
        plan_lower = execution_plan.lower()
        
        if any(kw in plan_lower for kw in ["npm", "node", "yarn", "graphql", "nest", "express"]):
            return "nodejs"
        elif any(kw in plan_lower for kw in ["pip", "python", "uvicorn", "fastapi", "django", "flask"]):
            return "python"
        else:
            # Default to nodejs as it's more common for the example
            return "nodejs"

    def _extract_schema(self, project_path: str, project_type: str) -> str:
        """Extract API schema from the project.
        
        Args:
            project_path: Path to project root
            project_type: "nodejs" or "python"
            
        Returns:
            Schema content as string, or empty string if not found
        """
        project_dir = Path(project_path)
        schema_files = []
        
        # Look for GraphQL schema files
        graphql_patterns = ["schema.gql", "schema.graphql", "*.graphql", "*.gql"]
        for pattern in graphql_patterns:
            schema_files.extend(project_dir.rglob(pattern))
        
        # Also look for OpenAPI/Swagger specs for REST APIs
        if project_type == "python":
            openapi_patterns = ["openapi.json", "openapi.yaml", "swagger.json", "swagger.yaml"]
            for pattern in openapi_patterns:
                schema_files.extend(project_dir.rglob(pattern))
        
        # Look for TypeScript DTO/Input files that define GraphQL types
        dto_patterns = ["*.input.ts", "*.dto.ts", "*.args.ts"]
        for pattern in dto_patterns:
            schema_files.extend(project_dir.rglob(pattern))
        
        if not schema_files:
            logger.info("No schema files found in project")
            return ""
        
        # Collect schema content
        schema_parts = []
        max_schema_chars = 8000  # Limit to avoid context overflow
        total_chars = 0
        
        for schema_file in schema_files[:10]:  # Limit to 10 files
            try:
                # Skip node_modules and other common ignore dirs
                if any(part in str(schema_file) for part in ['node_modules', '.git', 'dist', 'build']):
                    continue
                    
                content = schema_file.read_text(encoding='utf-8', errors='ignore')
                
                # Skip if too large
                if len(content) > 5000:
                    content = content[:5000] + "\n... (truncated)"
                
                if total_chars + len(content) > max_schema_chars:
                    break
                    
                relative_path = schema_file.relative_to(project_dir)
                schema_parts.append(f"--- {relative_path} ---\n{content}")
                total_chars += len(content)
                
                logger.info(f"Extracted schema from: {relative_path}")
                
            except Exception as e:
                logger.warning(f"Failed to read schema file {schema_file}: {e}")
                continue
        
        if schema_parts:
            return "\n\n".join(schema_parts)
        
        return ""

    def _format_features(self, feature_analysis: List[FeatureAnalysis]) -> str:
        """Format feature analysis into a readable string for LLM prompt.
        
        Args:
            feature_analysis: List of feature analysis results
            
        Returns:
            Formatted string
        """
        lines = []
        for i, feature in enumerate(feature_analysis, 1):
            lines.append(f"{i}. {feature.feature_description}")
            for loc in feature.implementation_location:
                lines.append(f"   - {loc.file}: {loc.function} (lines {loc.lines})")
                if loc.reason:
                    lines.append(f"     Reason: {loc.reason}")
        return "\n".join(lines)


# Singleton instance
_test_generator = None


def get_test_generator() -> TestGenerator:
    """Get the TestGenerator singleton."""
    global _test_generator
    if _test_generator is None:
        _test_generator = TestGenerator()
    return _test_generator
