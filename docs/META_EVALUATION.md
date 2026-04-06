# Meta Layer: Evaluation System

## Overview

The GENUS Meta Layer transforms a dev-automation workflow into a **system with DNA** - the ability to learn from runs and improve strategies over time.

After every run (and optionally after each iteration), an **evaluation** is performed to answer:
- What happened?
- What was inefficient?
- What failure class occurred?
- Which strategy should be preferred next?

The results are stored as **EvaluationArtifacts** in the RunJournal and published as events for downstream consumption.

**Important**: No ML, no external services. Only deterministic heuristics and structured output.

## Architecture

```
Dev Loop Events                 Meta Layer
─────────────────              ──────────────
dev.loop.completed    ─────►   EvaluationAgent
dev.loop.failed       ─────►        │
                                    ├─► RunEvaluator (heuristics)
                                    ├─► Save to RunJournal
                                    └─► Publish meta.evaluation.completed
```

## Components

### 1. Taxonomy (`genus/meta/taxonomy.py`)

Defines stable enums/constants for classification:

#### Failure Classes
- `TEST_FAILURE` - Tests ran but some failed
- `LINT_FAILURE` - Linting checks failed (optional)
- `TIMEOUT` - Execution timed out
- `GITHUB_CHECKS_FAILURE` - GitHub CI/CD checks failed
- `POLICY_BLOCKED` - Sandbox/safety policy blocked execution
- `UNKNOWN` - Could not determine failure type

#### Root Cause Hints
- `ASSERTION_ERROR` - Test assertion failed
- `IMPORT_ERROR` - Import or module not found
- `SYNTAX_ERROR` - Python syntax error
- `FLAKY_TEST_SUSPECTED` - Test appears flaky (optional)
- `ENV_MISSING_DEPENDENCY` - Missing dependency
- `UNKNOWN` - Could not determine root cause

#### Strategy Recommendations
- `TARGET_FAILING_TEST_FIRST` - Focus on specific failing tests
- `MINIMIZE_CHANGESET` - Reduce scope of changes
- `INCREASE_TIMEOUT_ONCE` - Retry with higher timeout
- `REVERT_LAST_COMMIT_AND_RETRY` - Regression suspected (optional)
- `ASK_OPERATOR_WITH_CONTEXT` - Requires human intervention

### 2. Evaluation Models (`genus/meta/evaluation_models.py`)

JSON-serializable dataclasses:

**EvaluationInput**
- `run_id`: Unique run identifier
- `goal`: High-level objective (optional)
- `final_status`: "completed" or "failed"
- `iterations_used`: Number of fix-loop iterations
- `test_reports`: List of test report artifacts
- `github`: GitHub context (PR, checks summary)
- `events`: Subset of journal events for context

**EvaluationArtifact**
- `run_id`: The evaluated run
- `created_at`: ISO-8601 timestamp
- `score`: Quality score (0-100, higher is better)
- `final_status`: "completed" or "failed"
- `failure_class`: Classification of failure (if any)
- `root_cause_hint`: Specific root cause (if detected)
- `highlights`: What went well
- `issues`: What went wrong
- `recommendations`: Human-readable suggestions
- `strategy_recommendations`: Machine-readable strategies
- `evidence`: Links to artifacts/logs/checks

### 3. RunEvaluator (`genus/meta/evaluator.py`)

Deterministic heuristic-based evaluator.

**Scoring Heuristics (v1)**

Base score: 100

Deductions:
- **Iterations**: -10 per iteration (capped at -50)
- **Failed run**: -40
- **Test failure**: -20
- **Timeout**: -25
- **GitHub checks failure**: -20

Score range: 0-100 (capped)

**Failure Classification Logic**

1. Check test reports for timeout → `TIMEOUT`
2. Check test reports for non-zero exit code → `TEST_FAILURE`
3. Check GitHub checks for failures → `GITHUB_CHECKS_FAILURE`
4. Otherwise → `UNKNOWN`

**Root Cause Detection**

Scan stderr/stdout for patterns:
- `AssertionError` → `ASSERTION_ERROR`
- `ImportError` | `ModuleNotFoundError` → `IMPORT_ERROR`
- `SyntaxError` → `SYNTAX_ERROR`

**Strategy Recommendations**

- `TEST_FAILURE` + `ASSERTION_ERROR` → `TARGET_FAILING_TEST_FIRST`, `MINIMIZE_CHANGESET`
- `TIMEOUT` → `INCREASE_TIMEOUT_ONCE`
- Iterations > 3 → `ASK_OPERATOR_WITH_CONTEXT`

### 4. EvaluationAgent (`genus/meta/agents/evaluation_agent.py`)

Meta-layer agent that:

1. **Subscribes** to `dev.loop.completed` and `dev.loop.failed`
2. **Loads** run data from RunJournal
3. **Evaluates** using RunEvaluator
4. **Saves** EvaluationArtifact to RunJournal (artifact_type="evaluation")
5. **Publishes** `meta.evaluation.completed` event

**Agent is read-only except**:
- Writing evaluation artifacts to RunJournal (allowed)
- Publishing messages (allowed)

### 5. Events and Topics

**New Topic**: `meta.evaluation.completed`

**Event Factory**: `meta_evaluation_completed_message(run_id, sender_id, score, failure_class, summary)`

Published after evaluation is complete with summary payload.

## Usage

### Standalone Evaluation

```python
from genus.meta import RunEvaluator, EvaluationInput

evaluator = RunEvaluator()

eval_input = EvaluationInput(
    run_id="2026-04-06T12-00-00Z__fix-bug__abc123",
    final_status="failed",
    iterations_used=2,
    test_reports=[
        {
            "exit_code": 1,
            "timed_out": False,
            "stderr_summary": "AssertionError: expected 5, got 3",
        }
    ],
)

artifact = evaluator.evaluate(eval_input)

print(f"Score: {artifact.score}/100")
print(f"Failure: {artifact.failure_class}")
print(f"Root cause: {artifact.root_cause_hint}")
print(f"Recommendations: {artifact.recommendations}")
print(f"Strategy: {artifact.strategy_recommendations}")
```

### Agent Integration

```python
from genus.communication.message_bus import InMemoryMessageBus
from genus.memory.store_jsonl import JsonlRunStore
from genus.meta.agents import EvaluationAgent

bus = InMemoryMessageBus()
store = JsonlRunStore()

# Start evaluation agent
agent = EvaluationAgent(bus, "evaluator-1", store)
agent.start()

# Agent now listens for dev.loop.completed/failed events
# and automatically evaluates runs
```

## Score Interpretation

| Score Range | Interpretation |
|------------|----------------|
| 90-100     | Excellent - Completed quickly with minimal iterations |
| 70-89      | Good - Completed with some iterations or minor issues |
| 50-69      | Acceptable - Multiple iterations or moderate issues |
| 30-49      | Poor - Failed run or significant issues |
| 0-29       | Critical - Failed with multiple severe issues |

## Storage

Evaluation artifacts are stored in RunJournal:

```
var/runs/<run_id>/
├── artifacts/
│   └── evaluation_<timestamp>.json    # EvaluationArtifact
└── journal.jsonl                      # Includes evaluation_completed event
```

## Future Extensions (Post-PR #32)

The evaluation layer provides the foundation for:

1. **Strategy Selection**: Use `strategy_recommendations` to choose next approach
2. **Learning**: Aggregate evaluations to identify patterns
3. **Adaptive Behavior**: Adjust timeouts, retry logic based on history
4. **Operator Dashboards**: Visualize scores, trends, common failure classes
5. **Run Comparison**: Compare evaluations across runs to measure improvement

## Design Principles

1. **Deterministic**: Same input → same evaluation (no randomness, no ML)
2. **Explainable**: Every score deduction and recommendation has clear reasoning
3. **Stable**: Taxonomy is versioned and backward-compatible
4. **Fast**: No network calls, no heavy computation
5. **Decoupled**: Meta layer reads from journal but doesn't modify dev-loop behavior

## Testing

Run unit tests:

```bash
pytest tests/unit/test_run_evaluator.py -v
pytest tests/unit/test_evaluation_agent.py -v
```

Tests cover:
- Score calculation for various scenarios
- Failure classification from test reports
- Root cause detection from stderr patterns
- Strategy recommendation logic
- Agent subscription and event handling
- Edge cases (missing run_id, non-existent runs)

## Constraints

- **No ML**: Pure heuristics only
- **No network**: All data from RunJournal
- **No secrets**: Evaluation artifacts contain no sensitive data
- **Read-only**: Agent doesn't modify workspace or git repo
- **Deterministic**: Same run data produces same evaluation
- **Fast**: Evaluation completes in milliseconds

## Example Evaluation Artifact

```json
{
  "run_id": "2026-04-06T12-00-00Z__fix-tests__abc123",
  "created_at": "2026-04-06T12:05:00+00:00",
  "score": 60,
  "final_status": "failed",
  "failure_class": "test_failure",
  "root_cause_hint": "assertion_error",
  "highlights": [],
  "issues": [
    "Used 2 iteration(s) to complete",
    "Run failed to complete successfully",
    "Tests failed"
  ],
  "recommendations": [
    "Focus on fixing the specific failing assertion(s)."
  ],
  "strategy_recommendations": [
    "target_failing_test_first",
    "minimize_changeset"
  ],
  "evidence": [
    {
      "type": "test_report",
      "index": 0,
      "exit_code": 1,
      "timed_out": false,
      "stderr_summary": "AssertionError: expected 5, got 3"
    }
  ]
}
```

## Contributing

When extending the evaluation system:

1. Keep heuristics simple and explainable
2. Document score deductions in code comments
3. Add test cases for new failure patterns
4. Version taxonomy changes carefully
5. Maintain backward compatibility
