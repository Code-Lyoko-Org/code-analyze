"""Code parser using Tree-sitter for AST analysis."""

import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from app.config import get_settings
from app.models.schemas import CodeDefinition, CodeBlock

# Tree-sitter imports will be lazy-loaded
_parsers: Dict[str, Any] = {}
_languages_loaded = False


def _get_language_for_extension(ext: str) -> Optional[str]:
    """Map file extension to tree-sitter language name.
    
    Args:
        ext: File extension (with or without dot)
        
    Returns:
        Language name for tree-sitter, or None if not supported
    """
    ext = ext.lstrip(".")
    mapping = {
        "ts": "typescript",
        "tsx": "tsx",
        "js": "javascript",
        "jsx": "javascript",
        "py": "python",
        "java": "java",
        "go": "go",
        "rs": "rust",
        "rb": "ruby",
        "php": "php",
        "c": "c",
        "cpp": "cpp",
        "h": "c",
        "hpp": "cpp",
    }
    return mapping.get(ext)


def _load_parsers():
    """Load tree-sitter parsers for supported languages."""
    global _parsers, _languages_loaded
    
    if _languages_loaded:
        return
    
    try:
        import tree_sitter_typescript as ts_typescript
        import tree_sitter_javascript as ts_javascript
        from tree_sitter import Language, Parser
        
        # Load TypeScript
        ts_lang = Language(ts_typescript.language_typescript())
        tsx_lang = Language(ts_typescript.language_tsx())
        js_lang = Language(ts_javascript.language())
        
        # Create parsers
        for name, lang in [("typescript", ts_lang), ("tsx", tsx_lang), ("javascript", js_lang)]:
            parser = Parser()
            parser.language = lang
            _parsers[name] = {"parser": parser, "language": lang}
        
        _languages_loaded = True
    except Exception as e:
        print(f"Warning: Failed to load tree-sitter parsers: {e}")


def _get_parser(language: str) -> Optional[Any]:
    """Get parser for a language.
    
    Args:
        language: Language name
        
    Returns:
        Parser dict or None
    """
    _load_parsers()
    return _parsers.get(language)


class CodeParser:
    """Parse source code using Tree-sitter to extract definitions."""

    def __init__(self):
        self.settings = get_settings()
        _load_parsers()

    def _get_query_for_language(self, language: str) -> str:
        """Get tree-sitter query for a language.
        
        Args:
            language: Language name
            
        Returns:
            Query string in S-expression format
        """
        # TypeScript/JavaScript query
        if language in ("typescript", "tsx", "javascript"):
            return """
            ; Capture class declarations
            (class_declaration
                name: (type_identifier) @class.name) @class.definition

            ; Capture function declarations
            (function_declaration
                name: (identifier) @function.name) @function.definition

            ; Capture arrow functions assigned to variables
            (lexical_declaration
                (variable_declarator
                    name: (identifier) @function.name
                    value: (arrow_function))) @function.definition

            ; Capture method definitions
            (method_definition
                name: (property_identifier) @method.name) @method.definition

            ; Capture interface declarations (TypeScript)
            (interface_declaration
                name: (type_identifier) @interface.name) @interface.definition
            """
        
        # Python query
        if language == "python":
            return """
            (class_definition
                name: (identifier) @class.name) @class.definition
            
            (function_definition
                name: (identifier) @function.name) @function.definition
            """
        
        return ""

    def parse_file(
        self,
        file_path: str,
        content: str,
        project_root: str = "",
    ) -> List[CodeDefinition]:
        """Parse a file and extract code definitions.
        
        Args:
            file_path: Path to the file (relative or absolute)
            content: File content
            project_root: Project root for relative paths
            
        Returns:
            List of CodeDefinition objects
        """
        ext = Path(file_path).suffix.lower()
        language = _get_language_for_extension(ext)
        
        if not language:
            return []
        
        parser_info = _get_parser(language)
        if not parser_info:
            return []
        
        parser = parser_info["parser"]
        lang = parser_info["language"]
        
        # Parse the code (use encode to handle multi-byte chars correctly)
        content_bytes = content.encode("utf-8")
        try:
            tree = parser.parse(content_bytes)
        except Exception as e:
            print(f"Failed to parse {file_path}: {e}")
            return []
        
        lines = content.splitlines()
        
        # Try Query API first, fallback to manual traversal
        query_str = self._get_query_for_language(language)
        if query_str:
            try:
                from tree_sitter import Query, QueryCursor
                
                query = Query(lang, query_str)
                cursor = QueryCursor(query)
                captures = cursor.captures(tree.root_node)
                
                # captures is a dict: {capture_name: [nodes]}
                return self._process_query_captures(captures, file_path, content, lines)
            except Exception as e:
                print(f"Query failed for {file_path}: {e}")
        
        # Fallback: manual AST traversal
        return self._extract_definitions_manual(tree, file_path, lines)

    def _process_query_captures(
        self,
        captures: Dict[str, List[Any]],
        file_path: str,
        content: str,
        lines: List[str],
    ) -> List[CodeDefinition]:
        """Process captures from QueryCursor.
        
        Args:
            captures: Dict of {capture_name: [nodes]}
            file_path: Path to the file
            content: File content
            lines: File lines
            
        Returns:
            List of CodeDefinition objects
        """
        definitions = []
        processed = set()  # Avoid duplicates
        
        # Find definition captures (e.g., 'function.definition', 'class.definition')
        for capture_name, nodes in captures.items():
            if ".definition" not in capture_name:
                continue
            
            def_type = capture_name.split(".")[0]  # function, class, method, interface
            
            for node in nodes:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                
                # Get the name from the corresponding .name capture
                name_capture_key = f"{def_type}.name"
                name = None
                
                if name_capture_key in captures:
                    # Find the name node that is a child of this definition node
                    for name_node in captures[name_capture_key]:
                        if (name_node.start_byte >= node.start_byte and 
                            name_node.end_byte <= node.end_byte):
                            # Use node.text for correct byte handling
                            name = name_node.text.decode("utf-8")
                            break
                
                if not name:
                    # Fallback: try to find identifier in children
                    for child in node.children:
                        if child.type in ("identifier", "type_identifier", "property_identifier"):
                            name = child.text.decode("utf-8")
                            break
                
                if not name:
                    continue
                
                # Deduplicate
                key = (file_path, name, start_line)
                if key in processed:
                    continue
                processed.add(key)
                
                node_content = node.text.decode("utf-8")
                signature = lines[start_line - 1].strip() if start_line <= len(lines) else ""
                
                definitions.append(CodeDefinition(
                    file_path=file_path,
                    name=name,
                    definition_type=def_type,
                    start_line=start_line,
                    end_line=end_line,
                    content=node_content,
                    signature=signature,
                ))
        
        return definitions

    def _extract_definitions_manual(
        self,
        tree: Any,
        file_path: str,
        lines: List[str],
    ) -> List[CodeDefinition]:
        """Manually extract definitions by traversing AST.
        
        Args:
            tree: Parsed AST tree
            file_path: Path to the file
            lines: File lines
            
        Returns:
            List of CodeDefinition objects
        """
        definitions = []
        content_bytes = "\n".join(lines).encode("utf-8")
        
        def traverse(node):
            # Check node types that indicate definitions
            definition_types = {
                "function_declaration": "function",
                "function_definition": "function",
                "class_declaration": "class",
                "class_definition": "class",
                "method_definition": "method",
                "interface_declaration": "interface",
            }
            
            if node.type in definition_types:
                def_type = definition_types[node.type]
                
                # Find name child - use node.text for correct byte handling
                name = None
                for child in node.children:
                    if child.type in ("identifier", "type_identifier", "property_identifier"):
                        name = child.text.decode("utf-8")
                        break
                    if child.type == "name":
                        name = child.text.decode("utf-8")
                        break
                
                if name:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    node_content = node.text.decode("utf-8")
                    signature = lines[start_line - 1].strip() if start_line <= len(lines) else ""
                    
                    definitions.append(CodeDefinition(
                        file_path=file_path,
                        name=name,
                        definition_type=def_type,
                        start_line=start_line,
                        end_line=end_line,
                        content=node_content,
                        signature=signature,
                    ))
            
            # Recurse into children
            for child in node.children:
                traverse(child)
        
        traverse(tree.root_node)
        return definitions

    def parse_files(
        self,
        project_root: str,
        file_paths: List[str],
    ) -> List[CodeDefinition]:
        """Parse multiple files and extract all definitions.
        
        Args:
            project_root: Project root directory
            file_paths: List of relative file paths
            
        Returns:
            List of all CodeDefinition objects
        """
        all_definitions = []
        
        for file_path in file_paths:
            full_path = os.path.join(project_root, file_path)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, IOError):
                continue
            
            definitions = self.parse_file(file_path, content, project_root)
            all_definitions.extend(definitions)
        
        return all_definitions

    def generate_code_structure(
        self,
        definitions: List[CodeDefinition],
        include_content: bool = True,
        max_content_lines: int = 30,
    ) -> str:
        """Generate a structured text representation of code definitions.
        
        Args:
            definitions: List of CodeDefinition objects
            include_content: Whether to include full method/class bodies
            max_content_lines: Maximum lines of content to include per definition
            
        Returns:
            Formatted string representation with code bodies
        """
        if not definitions:
            return "No code definitions found."
        
        # Group by file
        by_file: Dict[str, List[CodeDefinition]] = {}
        for d in definitions:
            if d.file_path not in by_file:
                by_file[d.file_path] = []
            by_file[d.file_path].append(d)
        
        output_lines = []
        for file_path in sorted(by_file.keys()):
            output_lines.append(f"\n## {file_path}")
            
            for d in sorted(by_file[file_path], key=lambda x: x.start_line):
                output_lines.append(
                    f"\n### [{d.definition_type}] {d.name} (lines {d.start_line}-{d.end_line})"
                )
                
                if include_content and d.content:
                    # Include the actual code content
                    content_lines = d.content.splitlines()
                    if len(content_lines) > max_content_lines:
                        # Truncate long content
                        truncated = content_lines[:max_content_lines]
                        truncated.append(f"    // ... ({len(content_lines) - max_content_lines} more lines)")
                        code_block = "\n".join(truncated)
                    else:
                        code_block = d.content
                    
                    output_lines.append("```")
                    output_lines.append(code_block)
                    output_lines.append("```")
                else:
                    # Fallback to signature only
                    if d.signature:
                        output_lines.append(f"Signature: {d.signature}")
        
        return "\n".join(output_lines)

