"""Tests for branch and remote name validation in git_tools."""
import pytest
from genus.tools.git_tools import _validate_branch_name, _validate_remote_name


class TestValidateBranchName:
    def test_valid_simple(self):
        assert _validate_branch_name("main") == "main"

    def test_valid_feature_slash(self):
        assert _validate_branch_name("feature/my-branch") == "feature/my-branch"

    def test_valid_with_dots(self):
        assert _validate_branch_name("fix/issue-123.patch") == "fix/issue-123.patch"

    def test_strips_whitespace(self):
        assert _validate_branch_name("  main  ") == "main"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _validate_branch_name("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _validate_branch_name("   ")

    def test_starts_with_dash_raises(self):
        with pytest.raises(ValueError, match="'-'"):
            _validate_branch_name("--upload-pack=evil")

    def test_double_dot_raises(self):
        with pytest.raises(ValueError, match=r"'\.\.'"):
            _validate_branch_name("feature/../main")

    def test_at_brace_raises(self):
        with pytest.raises(ValueError):
            _validate_branch_name("feature@{yesterday}")

    def test_ends_with_lock_raises(self):
        with pytest.raises(ValueError, match=".lock"):
            _validate_branch_name("feature.lock")

    def test_ends_with_dot_raises(self):
        with pytest.raises(ValueError):
            _validate_branch_name("feature.")

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="too long"):
            _validate_branch_name("a" * 201)

    def test_exactly_max_length_ok(self):
        assert _validate_branch_name("a" * 200) == "a" * 200

    def test_invalid_chars_raises(self):
        with pytest.raises(ValueError, match="invalid characters"):
            _validate_branch_name("feature branch")  # space not allowed

    def test_valid_with_underscores(self):
        assert _validate_branch_name("fix_issue_123") == "fix_issue_123"

    def test_valid_with_numbers(self):
        assert _validate_branch_name("release-2.0.1") == "release-2.0.1"


class TestValidateRemoteName:
    def test_valid_origin(self):
        assert _validate_remote_name("origin") == "origin"

    def test_valid_upstream(self):
        assert _validate_remote_name("upstream") == "upstream"

    def test_starts_with_dash_raises(self):
        with pytest.raises(ValueError):
            _validate_remote_name("--evil")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _validate_remote_name("")

    def test_slash_not_allowed(self):
        with pytest.raises(ValueError):
            _validate_remote_name("origin/bad")

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="too long"):
            _validate_remote_name("r" * 101)

    def test_valid_with_dots(self):
        assert _validate_remote_name("my.remote") == "my.remote"

    def test_valid_with_hyphens(self):
        assert _validate_remote_name("my-remote") == "my-remote"

    def test_spaces_not_allowed(self):
        with pytest.raises(ValueError):
            _validate_remote_name("bad remote")
