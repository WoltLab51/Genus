"""
GitHub Configuration

Provides configuration dataclass for GitHub operations.
"""

from dataclasses import dataclass


@dataclass
class GitHubConfig:
    """Configuration for GitHub API operations.

    Attributes:
        owner: Repository owner (default "WoltLab51").
        repo: Repository name (default "Genus").
        base_branch: Default base branch for PRs (default "main").
        remote_name: Git remote name (default "origin").
        api_base: GitHub API base URL (default "https://api.github.com").
        user_agent: User agent string for API requests (default "GENUS/1.0").
    """

    owner: str = "WoltLab51"
    repo: str = "Genus"
    base_branch: str = "main"
    remote_name: str = "origin"
    api_base: str = "https://api.github.com"
    user_agent: str = "GENUS/1.0"
