"""
Cross-Run Query

Provides filtered access to historical RunHeaders without loading
full journal data. All filtering is done on RunHeader fields only.
"""

from typing import List, Optional

from genus.memory.models import RunHeader
from genus.memory.store_jsonl import JsonlRunStore


def query_runs(
    store: JsonlRunStore,
    *,
    repo_id: Optional[str] = None,
    goal_contains: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[RunHeader]:
    """Query run headers with optional filters.

    All filters are applied on RunHeader fields. Runs without a header
    (e.g. created but never initialized) are silently skipped.

    Args:
        store: The JsonlRunStore to query.
        repo_id: If given, only return runs where header.repo_id == repo_id.
        goal_contains: If given, only return runs where goal contains this
                       substring (case-insensitive).
        since: ISO-8601 UTC string. Only return runs created at or after
               this timestamp (compared lexicographically — valid for ISO-8601).
        until: ISO-8601 UTC string. Only return runs created before or at
               this timestamp (compared lexicographically).
        limit: If given, return only the N most recent matching runs.
               Applied after all other filters.

    Returns:
        List of RunHeader objects, ordered by created_at descending
        (most recent first).

    Example::

        from genus.memory.store_jsonl import JsonlRunStore
        from genus.memory.query import query_runs

        store = JsonlRunStore()
        recent_failures = query_runs(
            store,
            repo_id="WoltLab51/Genus",
            since="2024-01-01T00:00:00+00:00",
            limit=10,
        )
    """
    # list_run_summaries returns most-recent-first
    summaries = store.list_run_summaries()

    results: List[RunHeader] = []
    for header in summaries:
        # Filter: repo_id exact match
        if repo_id is not None and header.repo_id != repo_id:
            continue

        # Filter: goal_contains case-insensitive substring
        if goal_contains is not None:
            if goal_contains.lower() not in (header.goal or "").lower():
                continue

        # Filter: since (created_at >= since, lexicographic ISO-8601 compare)
        if since is not None and header.created_at < since:
            continue

        # Filter: until (created_at <= until)
        if until is not None and header.created_at > until:
            continue

        results.append(header)

    # Apply limit after filtering
    if limit is not None:
        results = results[:limit]

    return results
