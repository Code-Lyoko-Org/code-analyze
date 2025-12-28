"""File extraction service for handling ZIP uploads."""

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List, Tuple

from app.config import get_settings
from app.utils.ignore_rules import IgnoreRules


class FileExtractor:
    """Service for extracting and processing uploaded code archives."""

    def __init__(self):
        self.settings = get_settings()
        self.temp_dir = Path(self.settings.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def extract_zip(self, zip_content: bytes, session_id: str) -> Tuple[str, List[str]]:
        """Extract a ZIP file to a temporary directory.
        
        Args:
            zip_content: Binary content of the ZIP file
            session_id: Unique session ID for this extraction
            
        Returns:
            Tuple of (extraction directory path, list of extracted file paths)
        """
        # Create session-specific directory
        extract_dir = self.temp_dir / session_id
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)

        # Write ZIP to temp file
        zip_path = extract_dir / "upload.zip"
        with open(zip_path, "wb") as f:
            f.write(zip_content)

        # Extract ZIP
        project_dir = extract_dir / "project"
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(project_dir)

        # Remove the ZIP file
        zip_path.unlink()

        # Find the actual project root (handle nested directories)
        project_root = self._find_project_root(project_dir)

        # Get list of files
        ignore_rules = IgnoreRules(str(project_root))
        files = ignore_rules.scan_directory()

        return str(project_root), files

    def _find_project_root(self, extract_dir: Path) -> Path:
        """Find the actual project root directory.
        
        Some ZIP files have a single root folder containing the project.
        This method handles that case.
        
        Args:
            extract_dir: The directory where ZIP was extracted
            
        Returns:
            Path to the actual project root
        """
        contents = list(extract_dir.iterdir())
        
        # If there's only one directory and no files, go deeper
        if len(contents) == 1 and contents[0].is_dir():
            return contents[0]
        
        return extract_dir

    def read_file(self, project_root: str, file_path: str) -> str:
        """Read the content of a file.
        
        Args:
            project_root: Root directory of the project
            file_path: Relative path to the file
            
        Returns:
            File content as string
        """
        full_path = Path(project_root) / file_path
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            # Try with different encoding
            with open(full_path, "r", encoding="latin-1") as f:
                return f.read()

    def read_file_lines(self, project_root: str, file_path: str) -> List[str]:
        """Read the content of a file as lines.
        
        Args:
            project_root: Root directory of the project
            file_path: Relative path to the file
            
        Returns:
            List of lines
        """
        content = self.read_file(project_root, file_path)
        return content.splitlines()

    def cleanup(self, session_id: str) -> None:
        """Clean up temporary files for a session.
        
        Args:
            session_id: Session ID to clean up
        """
        session_dir = self.temp_dir / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)

    def detect_project_type(self, project_root: str) -> dict:
        """Detect the type of project based on marker files.
        
        Args:
            project_root: Root directory of the project
            
        Returns:
            Dict with project type information
        """
        root = Path(project_root)
        
        markers = {
            "package.json": {"type": "node", "language": "javascript/typescript"},
            "tsconfig.json": {"type": "node", "language": "typescript"},
            "requirements.txt": {"type": "python", "language": "python"},
            "pyproject.toml": {"type": "python", "language": "python"},
            "Cargo.toml": {"type": "rust", "language": "rust"},
            "go.mod": {"type": "go", "language": "go"},
            "pom.xml": {"type": "maven", "language": "java"},
            "build.gradle": {"type": "gradle", "language": "java/kotlin"},
        }

        result = {"type": "unknown", "language": "unknown", "markers": []}
        
        for marker, info in markers.items():
            if (root / marker).exists():
                result["type"] = info["type"]
                result["language"] = info["language"]
                result["markers"].append(marker)

        return result
