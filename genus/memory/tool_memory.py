"""
Tool Memory Index

Aggregates tool usage statistics across runs from the RunJournal.
Answers questions like:
- Which tools were used most in 'implement' phase?
- How many times was 'sandbox_run' called across all runs?

Note: Tool events do not contain success/failure/duration fields.
The index can only aggregate frequency and phase co-occurrence.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from genus.memory.models import JournalEvent
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore


@dataclass
class ToolUsageStat:
    """Aggregated statistics for a single tool.

    Attributes:
        tool_name: The name of the tool.
        total_calls: Total number of times this tool was called across
                     all indexed runs and phases.
        calls_by_phase: Number of calls broken down by phase name.
        run_ids: Set of run IDs in which this tool was used.
    """

    tool_name: str
    total_calls: int = 0
    calls_by_phase: Dict[str, int] = field(default_factory=dict)
    run_ids: set = field(default_factory=set)

    def record_call(self, phase: str, run_id: str) -> None:
        """Record a single tool call."""
        self.total_calls += 1
        self.calls_by_phase[phase] = self.calls_by_phase.get(phase, 0) + 1
        self.run_ids.add(run_id)

    @property
    def run_count(self) -> int:
        """Number of distinct runs this tool was used in."""
        return len(self.run_ids)


class ToolMemoryIndex:
    """Aggregates tool usage statistics across runs.

    Builds an in-memory index from journal events of type 'tool_used'.
    The index is built lazily when first queried, or explicitly via build().

    Args:
        store: The JsonlRunStore to read journals from.

    Example::

        from genus.memory.store_jsonl import JsonlRunStore
        from genus.memory.tool_memory import ToolMemoryIndex

        store = JsonlRunStore()
        index = ToolMemoryIndex(store)
        index.build(run_ids=store.list_runs()[-20:])  # last 20 runs

        stats = index.get_stats("sandbox_run")
        print(f"sandbox_run called {stats.total_calls} times")
        print(f"by phase: {stats.calls_by_phase}")

        top = index.top_tools(phase="implement", n=5)
        for stat in top:
            print(f"{stat.tool_name}: {stat.total_calls} calls in {stat.run_count} runs")
    """

    def __init__(self, store: JsonlRunStore) -> None:
        self._store = store
        self._stats: Dict[str, ToolUsageStat] = {}
        self._indexed_run_ids: List[str] = []
        self._built = False

    def build(self, run_ids: Optional[List[str]] = None) -> None:
        """Build or rebuild the index from journal events.

        Args:
            run_ids: List of run IDs to index. If None, indexes all runs
                     in the store. Runs that don't exist are silently skipped.
        """
        self._stats = {}
        self._indexed_run_ids = []

        if run_ids is None:
            run_ids = self._store.list_runs()

        for run_id in run_ids:
            if not self._store.run_exists(run_id):
                continue

            journal = RunJournal(run_id, self._store)
            tool_events = journal.get_events(event_type="tool_used")

            for event in tool_events:
                tool_name = event.data.get("tool_name")
                if not tool_name or not isinstance(tool_name, str):
                    continue

                if tool_name not in self._stats:
                    self._stats[tool_name] = ToolUsageStat(tool_name=tool_name)

                self._stats[tool_name].record_call(
                    phase=event.phase,
                    run_id=run_id,
                )

            self._indexed_run_ids.append(run_id)

        self._built = True

    def get_stats(self, tool_name: str) -> Optional[ToolUsageStat]:
        """Get usage statistics for a specific tool.

        Args:
            tool_name: The tool name to look up.

        Returns:
            ToolUsageStat if the tool was found in any indexed run, else None.
        """
        return self._stats.get(tool_name)

    def all_stats(self) -> List[ToolUsageStat]:
        """Return usage stats for all indexed tools, sorted by total_calls descending.

        Returns:
            List of ToolUsageStat objects.
        """
        return sorted(self._stats.values(), key=lambda s: s.total_calls, reverse=True)

    def top_tools(
        self,
        phase: Optional[str] = None,
        n: int = 10,
    ) -> List[ToolUsageStat]:
        """Return the N most-called tools, optionally filtered by phase.

        Args:
            phase: If given, rank by calls in this phase only.
            n: Number of top tools to return.

        Returns:
            List of ToolUsageStat objects, ranked by call count.
        """
        stats = list(self._stats.values())

        if phase is not None:
            # Filter to tools used in this phase; sort by phase-specific count
            stats = [s for s in stats if phase in s.calls_by_phase]
            stats.sort(key=lambda s: s.calls_by_phase.get(phase, 0), reverse=True)
        else:
            stats.sort(key=lambda s: s.total_calls, reverse=True)

        return stats[:n]

    @property
    def indexed_run_count(self) -> int:
        """Number of runs currently indexed."""
        return len(self._indexed_run_ids)

    @property
    def is_built(self) -> bool:
        """Whether the index has been built at least once."""
        return self._built


class ToolBuildMemory:
    """Simple in-memory store for builder results."""

    def __init__(self) -> None:
        self._builds: Dict[str, dict] = {}

    def record_build_result(self, result) -> None:
        self._builds[result.request_id] = result.model_dump(mode="json")

    def get(self, request_id: str) -> Optional[dict]:
        return self._builds.get(request_id)

    def list_all(self) -> List[dict]:
        return list(self._builds.values())

    def delete(self, request_id: str) -> bool:
        return self._builds.pop(request_id, None) is not None
