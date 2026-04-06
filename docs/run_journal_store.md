# Run Journal Store v1

The Run Journal Store provides persistent, auditable storage for GENUS runs. It tracks:

- **Run metadata** (goal, repository, workspace)
- **Journal events** (phases, decisions, tool usage, errors)
- **Artifacts** (plans, test reports, patches, etc.)

## Key Features

- **Append-only journal**: All events are preserved in insertion order
- **Structured artifacts**: Versioned artifacts stored as individual JSON files
- **Evidence tracking**: Link events and artifacts to source evidence
- **Filesystem-safe**: Automatic sanitization of run IDs for safe storage
- **Decoupled design**: No dependencies on other GENUS modules

## Storage Layout

```
<base_dir>/
    <run_id>/
        header.json          # RunHeader metadata
        journal.jsonl        # Append-only journal events
        artifacts/
            <artifact_id>.json  # Individual artifact records
```

## Data Models

### RunHeader
Stores run metadata:
- `run_id`: Unique identifier
- `created_at`: ISO-8601 UTC timestamp
- `goal`: High-level objective
- `repo_id`: Optional repository (e.g., "WoltLab51/Genus")
- `workspace_root`: Optional workspace path
- `meta`: Arbitrary JSON metadata

### JournalEvent
Records a single event:
- `ts`: ISO-8601 UTC timestamp
- `run_id`: Run identifier
- `phase`: Current phase (e.g., "plan", "implement", "test")
- `event_type`: Event type (e.g., "started", "decision", "tool_used", "error")
- `summary`: Human-readable description
- `phase_id`: Optional phase instance ID
- `data`: Event-specific payload
- `evidence`: Supporting evidence references

### ArtifactRecord
Stores a versioned artifact:
- `run_id`: Run identifier
- `phase`: Phase that created the artifact
- `artifact_type`: Type (e.g., "plan", "test_report", "review")
- `payload`: Artifact content
- `saved_at`: ISO-8601 UTC timestamp
- `phase_id`: Optional phase instance ID
- `evidence`: Supporting evidence

## Usage

### Basic Usage

```python
from genus.core.run import new_run_id
from genus.memory import JsonlRunStore, RunJournal

# Create store and journal
store = JsonlRunStore(base_dir="var/runs")
run_id = new_run_id(slug="my-task")
journal = RunJournal(run_id, store)

# Initialize run
header = journal.initialize(
    goal="Implement feature X",
    repo_id="WoltLab51/Genus",
    workspace_root="/tmp/workspace",
)

# Log events
journal.log_phase_start("plan")
journal.log_decision(
    phase="plan",
    decision="Use pattern Y",
    evidence=[{"file": "docs/patterns.md", "line": 42}],
)

# Save artifacts
artifact_id = journal.save_artifact(
    phase="plan",
    artifact_type="plan",
    payload={"steps": ["1. Do X", "2. Do Y"]},
)

# Query journal
events = journal.get_events(phase="plan")
decisions = journal.get_events(event_type="decision")

# Query artifacts
plans = journal.list_artifacts(artifact_type="plan")
plan = journal.load_artifact(plans[0])
```

### Low-Level Store API

```python
from genus.memory import JsonlRunStore, RunHeader, JournalEvent, ArtifactRecord
from datetime import datetime, timezone

store = JsonlRunStore(base_dir="var/runs")

# Save header
header = RunHeader(
    run_id="my-run-id",
    created_at=datetime.now(timezone.utc).isoformat(),
    goal="My goal",
)
store.save_header(header)

# Append events
event = JournalEvent(
    ts=datetime.now(timezone.utc).isoformat(),
    run_id="my-run-id",
    phase="plan",
    event_type="started",
    summary="Started planning",
)
store.append_event(event)

# Save artifacts
artifact = ArtifactRecord(
    run_id="my-run-id",
    phase="plan",
    artifact_type="plan",
    payload={"content": "..."},
    saved_at=datetime.now(timezone.utc).isoformat(),
)
artifact_id = store.save_artifact(artifact)

# Query
events = store.list_events("my-run-id")
artifacts = store.list_artifacts("my-run-id")
```

## Configuration

The storage directory can be configured via:

1. Constructor argument (highest priority):
   ```python
   store = JsonlRunStore(base_dir="/custom/path")
   ```

2. Environment variable:
   ```bash
   export GENUS_RUNSTORE_DIR=/custom/path
   ```

3. Default: `var/runs/`

## Design Principles

1. **JSON-serializable**: All data uses primitive types (no complex objects)
2. **No import cycles**: Memory module has zero dependencies on DevLoop/Tools
3. **Append-only**: Journal events are never modified after creation
4. **Evidence-driven**: Events and artifacts link to supporting evidence
5. **Filesystem-safe**: Automatic sanitization prevents path traversal attacks

## Testing

Run the comprehensive test suite:

```bash
pytest tests/unit/test_run_journal_store.py -v
```

Or run the demonstration script:

```bash
python examples/run_journal_demo.py
```

## Future Enhancements (Post-v1)

- Query API for complex filters
- Event streaming/subscriptions
- Compressed storage for large artifacts
- Integration with DevLoop phases
- Automatic evidence collection from tool outputs
