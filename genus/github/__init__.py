"""
GitHub Integration

Provides controlled GitHub operations including:
- Authentication and configuration
- REST API client
- PR creation/update/comment
- Check runs polling

All operations follow GENUS security principles:
- Deny-by-default policy enforcement
- Kill-switch integration
- Memory journal logging
- No secrets in logs
"""

from genus.github.config import GitHubConfig
from genus.github.auth import get_github_token_from_env

__all__ = [
    "GitHubConfig",
    "get_github_token_from_env",
]
