"""
GitHub Authentication

Provides secure token retrieval from environment.
"""

import os


def get_github_token_from_env(env_key: str = "GITHUB_TOKEN") -> str:
    """Retrieve GitHub token from environment variable.

    Args:
        env_key: Environment variable name (default "GITHUB_TOKEN").

    Returns:
        GitHub token string.

    Raises:
        RuntimeError: If the environment variable is not set or empty.

    Security:
        - Never logs the token value
        - Never stores token in memory journal
        - Token is only used in-memory for API calls

    Example::

        try:
            token = get_github_token_from_env()
            # Use token for API calls
        except RuntimeError as e:
            print(f"Error: {e}")
    """
    token = os.environ.get(env_key, "").strip()

    if not token:
        raise RuntimeError(
            "GitHub token not found. "
            "Please set the {} environment variable.".format(env_key)
        )

    return token
