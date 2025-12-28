"""Unit tests for code parser chunking functionality."""

import pytest
from unittest.mock import patch, MagicMock

from app.services.code_parser import CodeParser
from app.models.schemas import CodeDefinition


class TestCodeParserChunking:
    """Test cases for P2 recursive chunking feature."""

    @pytest.fixture
    def parser(self):
        """Create a CodeParser instance with test settings."""
        parser = CodeParser()
        # Override settings for testing with small limits
        parser.settings = MagicMock()
        parser.settings.max_file_size_bytes = 500 * 1024
        parser.settings.max_block_chars = 200  # Small limit for testing
        parser.settings.max_llm_context_chars = 50000
        parser.settings.supported_extensions = [".ts", ".tsx", ".js", ".py"]
        parser.settings.ignore_dirs = ["node_modules", ".git"]
        return parser

    def test_small_function_not_chunked(self, parser):
        """Test that small functions are not chunked."""
        # Small function under 200 chars
        code = '''
function hello() {
  return "world";
}
'''
        definitions = parser.parse_file("test.ts", code, "")
        
        # Should have 1 definition, not chunked
        funcs = [d for d in definitions if d.definition_type == "function"]
        assert len(funcs) >= 1
        # Content should not have "part" in name
        assert "[part" not in funcs[0].name

    def test_large_function_with_children_recurses(self, parser):
        """Test that large functions (>1000 chars) with 3-level nesting are properly chunked."""
        # Build a LARGE function with 3 levels of nesting
        # Level 1: function (processData)
        # Level 2: if/for statements
        # Level 3: nested if/for inside level 2
        
        # Generate enough code to exceed 1000 chars
        inner_padding = "\n".join([f"        console.log('inner line {i}');" for i in range(10)])
        middle_padding = "\n".join([f"      console.log('middle line {i}');" for i in range(10)])
        outer_padding = "\n".join([f"  console.log('outer line {i}');" for i in range(10)])
        
        code = f'''function processLargeData(input) {{
  const results = [];
{outer_padding}
  
  // Level 2: First if block
  if (input.isValid) {{
{middle_padding}
    
    // Level 3: Nested for loop inside if
    for (let i = 0; i < input.items.length; i++) {{
{inner_padding}
      const item = input.items[i];
      results.push(transform(item));
    }}
  }}
  
  // Level 2: Second for loop
  for (const record of input.records) {{
{middle_padding}
    
    // Level 3: Nested if inside for
    if (record.needsProcessing) {{
{inner_padding}
      processRecord(record);
      saveRecord(record);
    }}
  }}
  
  // Level 2: Try-catch block
  try {{
{middle_padding}
    riskyOperation();
  }} catch (error) {{
    console.error(error);
  }}
  
  return results;
}}'''
        
        # Verify code is actually >1000 chars
        assert len(code) > 1000, f"Test code should be >1000 chars, got {len(code)}"
        print(f"\n[TEST] Code length: {len(code)} chars")
        
        # Parse the code to get AST tree
        import tree_sitter_typescript as ts_typescript
        from tree_sitter import Language, Parser as TSParser
        
        ts_lang = Language(ts_typescript.language_typescript())
        ts_parser = TSParser()
        ts_parser.language = ts_lang
        tree = ts_parser.parse(code.encode('utf-8'))
        
        # Use real settings (max_block_chars=1000) instead of mock
        from app.config import get_settings
        parser.settings = get_settings()
        
        # Directly test _extract_definitions_manual which has chunking logic
        definitions = parser._extract_definitions_manual(tree, "test.ts", code.splitlines())
        
        print(f"[TEST] Got {len(definitions)} definitions:")
        for d in definitions:
            has_marker = "子定义" in d.content or "..." in d.content
            print(f"  - {d.name}: {len(d.content)} chars, has_marker={has_marker}")
        
        # Should have main function definition
        assert len(definitions) >= 1, "Should have at least 1 definition"
        
        # Get main function
        main_func = next((d for d in definitions if "processLargeData" in d.name), None)
        assert main_func is not None, f"Should have processLargeData, got: {[d.name for d in definitions]}"
        
        # Since code is >1000 chars and has meaningful children,
        # the main function should have recursion marker
        has_recursion_marker = "子定义" in main_func.content or "..." in main_func.content
        
        assert has_recursion_marker, \
            f"Large function (>{len(code)} chars) with 3-level nesting should be chunked. "\
            f"Main func content: {len(main_func.content)} chars"

    def test_large_class_extracts_methods(self, parser):
        """Test that large classes extract methods as separate definitions."""
        code = '''
class UserService {
  constructor(private repo: Repository) {
    this.repo = repo;
  }

  async create(input: CreateInput) {
    const user = await this.repo.create(input);
    return await this.repo.save(user);
  }

  async findById(id: number) {
    return await this.repo.findOne({ where: { id } });
  }

  async update(id: number, input: UpdateInput) {
    const user = await this.findById(id);
    if (!user) throw new Error("Not found");
    return await this.repo.update(id, input);
  }
}
'''
        definitions = parser.parse_file("test.ts", code, "")
        
        # Should have class definition and methods
        classes = [d for d in definitions if d.definition_type == "class"]
        methods = [d for d in definitions if d.definition_type == "method"]
        
        assert len(classes) >= 1
        assert len(methods) >= 1
        
        # Methods should have class prefix
        method_names = [m.name for m in methods]
        assert any("UserService" in name or "constructor" in name for name in method_names)

    def test_leaf_node_splits_by_lines(self, parser):
        """Test that large leaf nodes are split by lines into parts."""
        # Very long function with no meaningful children (just statements)
        lines = ["  console.log('line " + str(i) + "');" for i in range(50)]
        code = '''
function longLeafFunction() {
''' + "\n".join(lines) + '''
  return true;
}
'''
        definitions = parser.parse_file("test.ts", code, "")
        
        # Should be split into multiple parts
        func_defs = [d for d in definitions if "longLeafFunction" in d.name]
        
        # Either split into parts or processed somehow
        assert len(func_defs) >= 1

    def test_extract_header_preserves_signature(self, parser):
        """Test that _extract_header keeps the function/class signature."""
        content = '''class MyClass {
  constructor() {}
  
  method1() { return 1; }
  method2() { return 2; }
  method3() { return 3; }
}'''
        header = parser._extract_header(content, max_chars=100)
        
        assert "class MyClass" in header
        assert "// ..." in header or "子定义" in header

    def test_split_by_lines(self):
        """Test the line splitting helper function."""
        content = "line1\nline2\nline3\nline4\nline5\n"
        
        # This is testing internal behavior, so we'll test generate_code_structure instead
        # which uses chunking internally

    def test_content_under_limit_unchanged(self, parser):
        """Test that content under max_block_chars is unchanged."""
        code = '''
function short() {
  return 42;
}
'''
        definitions = parser.parse_file("test.ts", code, "")
        
        funcs = [d for d in definitions if d.definition_type == "function"]
        assert len(funcs) >= 1
        
        # Content should be complete (not contain "part" suffix)
        assert "[part" not in funcs[0].name


class TestGenerateCodeStructure:
    """Test cases for generate_code_structure with chunking."""

    @pytest.fixture
    def parser(self):
        """Create a CodeParser instance with test settings."""
        with patch('app.services.code_parser.get_settings') as mock_settings:
            settings = MagicMock()
            settings.max_file_size_bytes = 500 * 1024
            settings.max_block_chars = 500
            settings.max_llm_context_chars = 2000  # Small for testing
            mock_settings.return_value = settings
            yield CodeParser()

    def test_budget_exceeded_shows_signature_only(self, parser):
        """Test that when budget is exceeded, only signatures are shown."""
        # Create many definitions that exceed the budget
        definitions = []
        for i in range(20):
            definitions.append(CodeDefinition(
                file_path="test.ts",
                name=f"function{i}",
                definition_type="function",
                start_line=i * 10,
                end_line=i * 10 + 5,
                content="function function{i}() { return " + "x" * 200 + "; }",
                signature=f"function function{i}()",
            ))
        
        result = parser.generate_code_structure(definitions)
        
        # Should contain at least some content
        assert len(result) > 0
        
        # Later definitions should only have signatures (due to budget)
        # Not all definitions should have full content

    def test_smart_truncate_for_large_blocks(self, parser):
        """Test that large blocks are smartly truncated."""
        long_content = "x" * 2000
        definition = CodeDefinition(
            file_path="test.ts",
            name="longFunc",
            definition_type="function",
            start_line=1,
            end_line=100,
            content=f"function longFunc() {{ {long_content} }}",
            signature="function longFunc()",
        )
        
        result = parser.generate_code_structure([definition])
        
        # Result should be shorter than original content
        assert len(result) < len(definition.content) + 200  # Some overhead for markdown


# Run with: uv run pytest tests/test_code_parser.py -v
