"""Ignore rules for filtering files during code scanning."""

import os
from pathlib import Path
from typing import List, Set

from app.config import get_settings


class IgnoreRules:
    """Handle file/directory ignore rules."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.settings = get_settings()
        self._ignore_dirs: Set[str] = set(self.settings.ignore_dirs)
        self._supported_extensions: Set[str] = set(self.settings.supported_extensions)

    def should_ignore_dir(self, dir_name: str) -> bool:
        """Check if a directory should be ignored.
        
        Args:
            dir_name: Name of the directory (not full path)
            
        Returns:
            True if directory should be ignored
        """
        # Ignore hidden directories
        if dir_name.startswith("."):
            return True
        return dir_name in self._ignore_dirs

    def should_ignore_file(self, file_path: str) -> bool:
        """Check if a file should be ignored.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if file should be ignored
        """
        path = Path(file_path)
        
        # Ignore hidden files
        if path.name.startswith("."):
            return True
        
        # Check extension
        return path.suffix.lower() not in self._supported_extensions

    def filter_files(self, file_paths: List[str]) -> List[str]:
        """Filter a list of file paths, removing ignored files.
        
        Args:
            file_paths: List of file paths to filter
            
        Returns:
            Filtered list of file paths
        """
        return [f for f in file_paths if not self.should_ignore_file(f)]

    def scan_directory(self, directory: str = None) -> List[str]:
        """Scan a directory and return list of supported files.
        
        Args:
            directory: Directory to scan, defaults to project root
            
        Returns:
            List of file paths relative to project root
        """
        if directory is None:
            directory = str(self.project_root)
        
        files = []
        
        for root, dirs, filenames in os.walk(directory):
            # Filter out ignored directories (in-place modification)
            dirs[:] = [d for d in dirs if not self.should_ignore_dir(d)]
            
            for filename in filenames:
                file_path = os.path.join(root, filename)
                if not self.should_ignore_file(file_path):
                    # Make path relative to project root
                    rel_path = os.path.relpath(file_path, self.project_root)
                    files.append(rel_path)
        
        return files
