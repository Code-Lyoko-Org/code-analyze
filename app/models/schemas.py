"""Pydantic schemas for API request/response models."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ImplementationLocation(BaseModel):
    """Location of a feature implementation in code."""
    
    file: str = Field(..., description="File path relative to project root")
    function: str = Field(..., description="Function or method name")
    lines: str = Field(..., description="Line range, e.g. '13-16'")
    reason: Optional[str] = Field(None, description="Explanation of why this implements the feature")


class FeatureAnalysis(BaseModel):
    """Analysis result for a single feature."""
    
    feature_description: str = Field(..., description="Description of the feature")
    implementation_location: List[ImplementationLocation] = Field(
        default_factory=list,
        description="Locations where this feature is implemented"
    )


class AnalysisReport(BaseModel):
    """Complete analysis report for a codebase."""
    
    feature_analysis: List[FeatureAnalysis] = Field(
        default_factory=list,
        description="Analysis of each feature"
    )
    execution_plan_suggestion: str = Field(
        "",
        description="Suggestion for how to run the project"
    )


class CodeBlock(BaseModel):
    """A block of code extracted from a file."""
    
    file_path: str = Field(..., description="Path to the source file")
    content: str = Field(..., description="Code content")
    start_line: int = Field(..., description="Starting line number (1-indexed)")
    end_line: int = Field(..., description="Ending line number (1-indexed)")
    block_type: str = Field(..., description="Type of block: function, class, method")
    name: str = Field(..., description="Name of the function/class/method")


class CodeDefinition(BaseModel):
    """A code definition (function, class, method) with location info."""
    
    file_path: str = Field(..., description="Path to the source file")
    name: str = Field(..., description="Name of the definition")
    definition_type: str = Field(..., description="Type: function, class, method")
    start_line: int = Field(..., description="Starting line number")
    end_line: int = Field(..., description="Ending line number")
    content: str = Field(..., description="Full content of the definition")
    signature: Optional[str] = Field(None, description="Function/method signature")


class ReviewRequest(BaseModel):
    """Request model for code review (for validation)."""
    
    problem_description: str = Field(..., description="Description of required features")


class ReviewResponse(BaseModel):
    """Response model for code review."""
    
    success: bool = Field(..., description="Whether the analysis was successful")
    report: Optional[AnalysisReport] = Field(None, description="Analysis report if successful")
    error: Optional[str] = Field(None, description="Error message if failed")
