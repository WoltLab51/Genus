"""
Tests for GitHub Client

Tests the GitHubClient REST API wrapper with mocked HTTP layer.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from genus.github.client import GitHubClient, GitHubAPIError
from genus.github.config import GitHubConfig


@pytest.fixture
def github_config():
    """Create a test GitHub configuration."""
    return GitHubConfig(
        owner="test-owner",
        repo="test-repo",
        base_branch="main",
    )


@pytest.fixture
def github_client(github_config):
    """Create a test GitHub client."""
    return GitHubClient(token="test-token", config=github_config)


def test_client_initialization(github_config):
    """Test GitHubClient initialization."""
    client = GitHubClient(token="my-token", config=github_config)

    assert client.token == "my-token"
    assert client.config == github_config


def test_create_pull_request_success(github_client):
    """Test successful PR creation."""
    mock_response = {
        "number": 123,
        "html_url": "https://github.com/test-owner/test-repo/pull/123",
        "title": "Test PR",
    }

    with patch.object(github_client, "_request", return_value=mock_response) as mock_req:
        result = github_client.create_pull_request(
            owner="test-owner",
            repo="test-repo",
            head="feature-branch",
            base="main",
            title="Test PR",
            body="Test body",
        )

        assert result["number"] == 123
        assert result["html_url"] == "https://github.com/test-owner/test-repo/pull/123"

        # Verify _request was called correctly
        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert "/repos/test-owner/test-repo/pulls" in call_args[0][1]


def test_find_open_pull_request_found(github_client):
    """Test finding an existing open PR."""
    mock_response = [
        {
            "number": 456,
            "html_url": "https://github.com/test-owner/test-repo/pull/456",
            "state": "open",
        }
    ]

    with patch.object(github_client, "_request", return_value=mock_response):
        result = github_client.find_open_pull_request(
            owner="test-owner",
            repo="test-repo",
            head="feature-branch",
            base="main",
        )

        assert result is not None
        assert result["number"] == 456


def test_find_open_pull_request_not_found(github_client):
    """Test finding PR when none exists."""
    mock_response = []

    with patch.object(github_client, "_request", return_value=mock_response):
        result = github_client.find_open_pull_request(
            owner="test-owner",
            repo="test-repo",
            head="feature-branch",
            base="main",
        )

        assert result is None


def test_update_pull_request(github_client):
    """Test updating an existing PR."""
    mock_response = {
        "number": 123,
        "title": "Updated Title",
        "body": "Updated Body",
    }

    with patch.object(github_client, "_request", return_value=mock_response) as mock_req:
        result = github_client.update_pull_request(
            owner="test-owner",
            repo="test-repo",
            pr_number=123,
            title="Updated Title",
            body="Updated Body",
        )

        assert result["title"] == "Updated Title"
        assert result["body"] == "Updated Body"

        # Verify PATCH method was used
        call_args = mock_req.call_args
        assert call_args[0][0] == "PATCH"


def test_create_issue_comment(github_client):
    """Test creating a comment on a PR."""
    mock_response = {
        "id": 789,
        "body": "Test comment",
        "html_url": "https://github.com/test-owner/test-repo/pull/123#issuecomment-789",
    }

    with patch.object(github_client, "_request", return_value=mock_response) as mock_req:
        result = github_client.create_issue_comment(
            owner="test-owner",
            repo="test-repo",
            issue_number=123,
            body="Test comment",
        )

        assert result["id"] == 789
        assert result["body"] == "Test comment"

        # Verify POST method was used
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert "/issues/123/comments" in call_args[0][1]


def test_list_pull_request_files(github_client):
    """Test listing files in a PR."""
    mock_response = [
        {"filename": "file1.py", "status": "modified"},
        {"filename": "file2.py", "status": "added"},
    ]

    with patch.object(github_client, "_request", return_value=mock_response):
        result = github_client.list_pull_request_files(
            owner="test-owner",
            repo="test-repo",
            pr_number=123,
        )

        assert len(result) == 2
        assert result[0]["filename"] == "file1.py"
        assert result[1]["status"] == "added"


def test_list_check_runs_for_ref(github_client):
    """Test listing check runs for a commit."""
    mock_response = {
        "check_runs": [
            {"name": "CI", "status": "completed", "conclusion": "success"},
            {"name": "Lint", "status": "completed", "conclusion": "success"},
        ]
    }

    with patch.object(github_client, "_request", return_value=mock_response):
        result = github_client.list_check_runs_for_ref(
            owner="test-owner",
            repo="test-repo",
            ref="abc123",
        )

        assert len(result) == 2
        assert result[0]["name"] == "CI"
        assert result[1]["conclusion"] == "success"


def test_get_combined_status(github_client):
    """Test getting combined status for a commit."""
    mock_response = {
        "state": "success",
        "statuses": [
            {"context": "CI", "state": "success"},
        ],
    }

    with patch.object(github_client, "_request", return_value=mock_response):
        result = github_client.get_combined_status(
            owner="test-owner",
            repo="test-repo",
            ref="abc123",
        )

        assert result["state"] == "success"
        assert len(result["statuses"]) == 1


def test_request_rate_limit_error(github_client):
    """Test handling of rate limit errors."""
    # Mock HTTPError for rate limiting
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_error = Mock()
        mock_error.code = 403
        mock_error.reason = "Forbidden"
        mock_error.read.return_value = b'{"message": "API rate limit exceeded"}'

        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )
        mock_urlopen.side_effect.read = lambda: b'{"message": "API rate limit exceeded"}'

        with pytest.raises(GitHubAPIError) as exc_info:
            github_client._request("GET", "/test")

        assert "rate limit" in str(exc_info.value).lower() or "403" in str(exc_info.value)


def test_request_network_error(github_client):
    """Test handling of network errors."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")

        with pytest.raises(GitHubAPIError) as exc_info:
            github_client._request("GET", "/test")

        assert "network error" in str(exc_info.value).lower()
