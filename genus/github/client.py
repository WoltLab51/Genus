"""
GitHub API Client

Provides a minimal REST client for GitHub operations.
Uses urllib for HTTP requests to avoid external dependencies.

Security:
- Never logs tokens or sensitive data
- Respects rate limits
- Clean error handling
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from genus.github.config import GitHubConfig

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Raised when GitHub API returns an error."""

    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GitHubClient:
    """Minimal GitHub REST API client.

    Provides basic operations for PR management and check runs polling.
    Uses synchronous urllib requests for simplicity.

    Args:
        token: GitHub personal access token.
        config: GitHubConfig instance.

    Example::

        from genus.github.auth import get_github_token_from_env
        from genus.github.config import GitHubConfig
        from genus.github.client import GitHubClient

        token = get_github_token_from_env()
        config = GitHubConfig()
        client = GitHubClient(token, config)

        # Create a PR
        pr = client.create_pull_request(
            owner="WoltLab51",
            repo="Genus",
            head="feature-branch",
            base="main",
            title="Add new feature",
            body="Description of changes",
        )
        print(f"Created PR #{pr['number']}")
    """

    def __init__(self, token: str, config: GitHubConfig):
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token.
            config: GitHubConfig instance.
        """
        self.token = token
        self.config = config

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make a GitHub API request.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.).
            path: API path (e.g., "/repos/owner/repo/pulls").
            json_data: Optional JSON payload.
            params: Optional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            GitHubAPIError: If the request fails.
        """
        # Build URL
        url = self.config.api_base + path

        # Add query parameters
        if params:
            query_string = "&".join("{}={}".format(k, v) for k, v in params.items())
            url = url + "?" + query_string

        # Prepare request
        headers = {
            "Authorization": "token {}".format(self.token),
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": self.config.user_agent,
        }

        # Prepare body
        body = None
        if json_data is not None:
            body = json.dumps(json_data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        # Create request
        req = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        # Make request
        try:
            with urllib.request.urlopen(req) as response:
                response_body = response.read().decode("utf-8")
                if response_body:
                    return json.loads(response_body)
                return {}

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            error_msg = "GitHub API request failed: {} {}".format(e.code, e.reason)

            # Check for rate limiting
            if e.code in (403, 429):
                error_msg += " (Rate limit exceeded or forbidden)"

            # Try to parse error details
            try:
                error_data = json.loads(error_body)
                if "message" in error_data:
                    error_msg += " - {}".format(error_data["message"])
            except (json.JSONDecodeError, ValueError) as _exc:
                logger.debug(
                    "GitHubClient: could not parse error response body: %s", _exc
                )

            raise GitHubAPIError(error_msg, status_code=e.code, response_body=error_body)

        except urllib.error.URLError as e:
            raise GitHubAPIError("Network error: {}".format(e.reason))

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> Dict[str, Any]:
        """Create a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            head: Branch to merge from.
            base: Branch to merge into.
            title: PR title.
            body: PR description.

        Returns:
            PR data dict with 'number', 'html_url', etc.

        Raises:
            GitHubAPIError: If the request fails.
        """
        path = "/repos/{}/{}/pulls".format(owner, repo)
        data = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
        }

        return self._request("POST", path, json_data=data)

    def find_open_pull_request(
        self,
        owner: str,
        repo: str,
        head: str,
        base: str,
    ) -> Optional[Dict[str, Any]]:
        """Find an open pull request for the given head and base.

        Args:
            owner: Repository owner.
            repo: Repository name.
            head: Branch to search for.
            base: Base branch.

        Returns:
            PR data dict if found, None otherwise.

        Raises:
            GitHubAPIError: If the request fails.
        """
        path = "/repos/{}/{}/pulls".format(owner, repo)
        params = {
            "state": "open",
            "head": "{}:{}".format(owner, head),
            "base": base,
        }

        prs = self._request("GET", path, params=params)

        if prs and len(prs) > 0:
            return prs[0]
        return None

    def update_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        *,
        title: Optional[str] = None,
        body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: PR number.
            title: Optional new title.
            body: Optional new body.

        Returns:
            Updated PR data dict.

        Raises:
            GitHubAPIError: If the request fails.
        """
        path = "/repos/{}/{}/pulls/{}".format(owner, repo, pr_number)
        data = {}

        if title is not None:
            data["title"] = title
        if body is not None:
            data["body"] = body

        return self._request("PATCH", path, json_data=data)

    def create_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> Dict[str, Any]:
        """Create a comment on an issue or PR.

        Args:
            owner: Repository owner.
            repo: Repository name.
            issue_number: Issue or PR number.
            body: Comment text.

        Returns:
            Comment data dict.

        Raises:
            GitHubAPIError: If the request fails.
        """
        path = "/repos/{}/{}/issues/{}/comments".format(owner, repo, issue_number)
        data = {"body": body}

        return self._request("POST", path, json_data=data)

    def list_pull_request_files(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> List[Dict[str, Any]]:
        """List files changed in a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: PR number.

        Returns:
            List of file dicts with 'filename', 'status', etc.

        Raises:
            GitHubAPIError: If the request fails.
        """
        path = "/repos/{}/{}/pulls/{}/files".format(owner, repo, pr_number)

        return self._request("GET", path)

    def list_check_runs_for_ref(
        self,
        owner: str,
        repo: str,
        ref: str,
    ) -> List[Dict[str, Any]]:
        """List check runs for a commit reference.

        Args:
            owner: Repository owner.
            repo: Repository name.
            ref: Commit SHA or branch name.

        Returns:
            List of check run dicts.

        Raises:
            GitHubAPIError: If the request fails.
        """
        path = "/repos/{}/{}/commits/{}/check-runs".format(owner, repo, ref)

        result = self._request("GET", path)
        return result.get("check_runs", [])

    def get_combined_status(
        self,
        owner: str,
        repo: str,
        ref: str,
    ) -> Dict[str, Any]:
        """Get combined status for a commit reference.

        Args:
            owner: Repository owner.
            repo: Repository name.
            ref: Commit SHA or branch name.

        Returns:
            Combined status dict with 'state', 'statuses', etc.

        Raises:
            GitHubAPIError: If the request fails.
        """
        path = "/repos/{}/{}/commits/{}/status".format(owner, repo, ref)

        return self._request("GET", path)
