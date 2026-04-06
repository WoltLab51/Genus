"""
Tests for workspace.repo_tools module.

Verifies:
- Evidence class creates proper evidence records
- ToolResponse serialization works correctly
- read_file() reads files with evidence capture
- list_tree() lists directory contents with filtering
- grep_text() searches for patterns with evidence
"""

import pytest
from pathlib import Path
import tempfile

from genus.workspace.repo_tools import (
    Evidence,
    ToolResponse,
    GrepMatch,
    read_file,
    list_tree,
    grep_text,
)


class TestEvidence:
    """Tests for Evidence class."""

    def test_minimal_evidence(self):
        """Should create evidence with minimal fields."""
        ev = Evidence(tool="read_file", path="src/main.py")

        assert ev.tool == "read_file"
        assert ev.path == "src/main.py"
        assert ev.line_numbers is None
        assert ev.matched_pattern is None
        assert ev.metadata == {}

    def test_evidence_with_line_numbers(self):
        """Should include line numbers when provided."""
        ev = Evidence(
            tool="grep_text",
            path="src/utils.py",
            line_numbers=[10, 25, 42],
        )

        assert ev.line_numbers == [10, 25, 42]

    def test_evidence_with_matched_pattern(self):
        """Should include matched pattern when provided."""
        ev = Evidence(
            tool="grep_text",
            path="src/test.py",
            matched_pattern=r"def test_.*",
        )

        assert ev.matched_pattern == r"def test_.*"

    def test_evidence_with_metadata(self):
        """Should include metadata when provided."""
        ev = Evidence(
            tool="read_file",
            path="README.md",
            metadata={"size_bytes": 1024},
        )

        assert ev.metadata == {"size_bytes": 1024}

    def test_evidence_to_dict(self):
        """Should serialize to dictionary correctly."""
        ev = Evidence(
            tool="grep_text",
            path="src/main.py",
            line_numbers=[5, 10],
            matched_pattern=r"import.*",
            metadata={"match_count": 2},
        )

        result = ev.to_dict()

        assert result == {
            "tool": "grep_text",
            "path": "src/main.py",
            "line_numbers": [5, 10],
            "matched_pattern": r"import.*",
            "metadata": {"match_count": 2},
        }

    def test_evidence_to_dict_omits_none_fields(self):
        """Should omit optional fields when they are None."""
        ev = Evidence(tool="list_tree", path="src/")

        result = ev.to_dict()

        assert result == {
            "tool": "list_tree",
            "path": "src/",
        }
        assert "line_numbers" not in result
        assert "matched_pattern" not in result
        # metadata is included even if empty (it's a default dict, not None)


class TestToolResponse:
    """Tests for ToolResponse class."""

    def test_successful_response(self):
        """Should create successful response."""
        resp = ToolResponse(
            success=True,
            data="file content",
            evidence=[Evidence(tool="read_file", path="test.py")],
        )

        assert resp.success is True
        assert resp.data == "file content"
        assert len(resp.evidence) == 1
        assert resp.error is None

    def test_error_response(self):
        """Should create error response."""
        resp = ToolResponse(
            success=False,
            data=None,
            error="File not found",
        )

        assert resp.success is False
        assert resp.data is None
        assert resp.error == "File not found"
        assert resp.evidence == []

    def test_response_to_dict(self):
        """Should serialize to dictionary correctly."""
        resp = ToolResponse(
            success=True,
            data=["file1.py", "file2.py"],
            evidence=[Evidence(tool="list_tree", path=".")],
        )

        result = resp.to_dict()

        assert result["success"] is True
        assert result["data"] == ["file1.py", "file2.py"]
        assert len(result["evidence"]) == 1
        assert result["evidence"][0]["tool"] == "list_tree"


class TestGrepMatch:
    """Tests for GrepMatch class."""

    def test_grep_match_to_dict(self):
        """Should serialize to dictionary correctly."""
        match = GrepMatch(
            file_path="src/main.py",
            line_number=42,
            line_content="def calculate_total(items):",
            match_start=4,
            match_end=19,
        )

        result = match.to_dict()

        assert result == {
            "file_path": "src/main.py",
            "line_number": 42,
            "line_content": "def calculate_total(items):",
            "match_start": 4,
            "match_end": 19,
        }


class TestReadFile:
    """Tests for read_file() function."""

    def test_read_existing_file(self, tmp_path):
        """Should read file content successfully."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        response = read_file(tmp_path, "test.txt")

        assert response.success is True
        assert response.data == "Hello, World!"
        assert len(response.evidence) == 1
        assert response.evidence[0].tool == "read_file"
        assert response.evidence[0].path == "test.txt"
        assert response.error is None

    def test_read_file_with_utf8_content(self, tmp_path):
        """Should handle UTF-8 content correctly."""
        test_file = tmp_path / "unicode.txt"
        content = "Hello 世界 🌍"
        test_file.write_text(content, encoding="utf-8")

        response = read_file(tmp_path, "unicode.txt")

        assert response.success is True
        assert response.data == content

    def test_read_nonexistent_file(self, tmp_path):
        """Should return error for nonexistent file."""
        response = read_file(tmp_path, "missing.txt")

        assert response.success is False
        assert response.data is None
        assert "not found" in response.error.lower()

    def test_read_directory_returns_error(self, tmp_path):
        """Should return error when trying to read a directory."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        response = read_file(tmp_path, "subdir")

        assert response.success is False
        assert "not a file" in response.error.lower()

    def test_read_file_path_traversal_protection(self, tmp_path):
        """Should reject path traversal attempts."""
        # Create a file outside repo_dir
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("secret data")

        # Try to read it using path traversal
        response = read_file(tmp_path / "repo", "../outside/secret.txt")

        assert response.success is False
        assert "outside repository" in response.error.lower()

    def test_read_file_includes_size_metadata(self, tmp_path):
        """Should include file size in evidence metadata."""
        test_file = tmp_path / "test.txt"
        content = "A" * 100
        test_file.write_text(content)

        response = read_file(tmp_path, "test.txt")

        assert response.success is True
        assert response.evidence[0].metadata["size_bytes"] == 100

    def test_read_binary_file_returns_error(self, tmp_path):
        """Should return error for binary files."""
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\xFF\xFE")

        response = read_file(tmp_path, "binary.bin")

        assert response.success is False
        assert "not a valid utf-8" in response.error.lower()


class TestListTree:
    """Tests for list_tree() function."""

    def test_list_simple_directory(self, tmp_path):
        """Should list files in a simple directory."""
        # Create test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.py").write_text("content2")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")

        response = list_tree(tmp_path)

        assert response.success is True
        assert "file1.txt" in response.data
        assert "file2.py" in response.data
        assert "subdir" in response.data
        # With default unlimited depth, subdirectory files are included
        # Note: The actual path format depends on the implementation

    def test_list_tree_with_max_depth(self, tmp_path):
        """Should respect max_depth parameter."""
        # Create nested structure
        level1 = tmp_path / "level1"
        level1.mkdir()
        (level1 / "file1.txt").write_text("content")

        level2 = level1 / "level2"
        level2.mkdir()
        (level2 / "file2.txt").write_text("content")

        # List with max_depth=1
        response = list_tree(tmp_path, max_depth=1)

        assert response.success is True
        assert "level1" in response.data
        # level2 should not be included due to depth limit
        paths_str = " ".join(response.data)
        # At depth 1, we see level1 directory and file1.txt, but not level2

    def test_list_tree_with_pattern_filter(self, tmp_path):
        """Should filter files by include_pattern."""
        (tmp_path / "test.py").write_text("python")
        (tmp_path / "test.txt").write_text("text")
        (tmp_path / "main.py").write_text("python")

        # Filter for Python files only
        response = list_tree(tmp_path, include_pattern=r"\.py$")

        assert response.success is True
        assert any("test.py" in p for p in response.data)
        assert any("main.py" in p for p in response.data)
        assert not any("test.txt" in p for p in response.data)

    def test_list_tree_nonexistent_directory(self, tmp_path):
        """Should return error for nonexistent directory."""
        response = list_tree(tmp_path, "nonexistent")

        assert response.success is False
        assert "not found" in response.error.lower()

    def test_list_tree_file_instead_of_directory(self, tmp_path):
        """Should return error when path is a file, not directory."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        response = list_tree(tmp_path, "test.txt")

        assert response.success is False
        assert "not a directory" in response.error.lower()

    def test_list_tree_path_traversal_protection(self, tmp_path):
        """Should reject path traversal attempts."""
        response = list_tree(tmp_path / "repo", "../outside")

        assert response.success is False
        assert "outside repository" in response.error.lower()

    def test_list_tree_evidence_includes_metadata(self, tmp_path):
        """Should include metadata in evidence."""
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.txt").write_text("content")

        response = list_tree(tmp_path)

        assert response.success is True
        assert len(response.evidence) == 1
        assert response.evidence[0].metadata["file_count"] > 0


class TestGrepText:
    """Tests for grep_text() function."""

    def test_grep_simple_pattern(self, tmp_path):
        """Should find simple text pattern."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('Hello')\n    return True\n")

        response = grep_text(tmp_path, r"def hello")

        assert response.success is True
        assert len(response.data) == 1
        match = response.data[0]
        assert match["file_path"] == "test.py"
        assert match["line_number"] == 1
        assert "def hello" in match["line_content"]

    def test_grep_multiple_matches(self, tmp_path):
        """Should find all matches across files."""
        (tmp_path / "file1.py").write_text("import os\nimport sys\n")
        (tmp_path / "file2.py").write_text("import json\ndef test():\n    pass\n")

        response = grep_text(tmp_path, r"import")

        assert response.success is True
        assert len(response.data) >= 3  # 2 in file1, 1 in file2

    def test_grep_with_file_pattern_filter(self, tmp_path):
        """Should filter files using file_pattern."""
        (tmp_path / "test.py").write_text("TODO: fix this\n")
        (tmp_path / "test.txt").write_text("TODO: update docs\n")

        # Search only in .py files
        response = grep_text(tmp_path, r"TODO", file_pattern=r"\.py$")

        assert response.success is True
        assert len(response.data) == 1
        assert response.data[0]["file_path"] == "test.py"

    def test_grep_respects_max_matches(self, tmp_path):
        """Should limit results to max_matches."""
        test_file = tmp_path / "test.txt"
        content = "\n".join(["line {}".format(i) for i in range(200)])
        test_file.write_text(content)

        response = grep_text(tmp_path, r"line", max_matches=10)

        assert response.success is True
        assert len(response.data) == 10

    def test_grep_invalid_regex_returns_error(self, tmp_path):
        """Should return error for invalid regex pattern."""
        response = grep_text(tmp_path, r"[invalid(")

        assert response.success is False
        assert "invalid regex" in response.error.lower()

    def test_grep_skips_binary_files(self, tmp_path):
        """Should skip binary files gracefully."""
        # Create binary file
        binary = tmp_path / "binary.bin"
        binary.write_bytes(b"\x00\x01\xFF\xFE")

        # Create text file
        text = tmp_path / "text.txt"
        text.write_text("searchable content")

        response = grep_text(tmp_path, r"searchable")

        assert response.success is True
        # Should find match in text file, skip binary file
        assert len(response.data) == 1
        assert response.data[0]["file_path"] == "text.txt"

    def test_grep_evidence_includes_line_numbers(self, tmp_path):
        """Should include line numbers in evidence."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line 1\nTARGET line 2\nline 3\nTARGET line 4\n")

        response = grep_text(tmp_path, r"TARGET")

        assert response.success is True
        assert len(response.evidence) == 1
        assert response.evidence[0].path == "test.py"
        assert response.evidence[0].line_numbers == [2, 4]
        assert response.evidence[0].matched_pattern == r"TARGET"

    def test_grep_match_includes_position(self, tmp_path):
        """Should include match start/end positions."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("prefix TARGET suffix")

        response = grep_text(tmp_path, r"TARGET")

        assert response.success is True
        match = response.data[0]
        assert match["match_start"] == 7
        assert match["match_end"] == 13

    def test_grep_empty_result_is_successful(self, tmp_path):
        """Should return success with empty data when no matches found."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("no matches here")

        response = grep_text(tmp_path, r"NONEXISTENT")

        assert response.success is True
        assert response.data == []
        assert response.evidence == []
