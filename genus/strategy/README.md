# Strategy Layer - GENUS DNA v1

The Strategy Layer implements GENUS's "DNA" v1 - a meta-driven approach to playbook selection based on evaluation artifacts, taxonomy, and learning history.

## Overview

The strategy layer provides:

- **Strategy Registry**: Named playbooks with machine-readable descriptions
- **Learning Store**: Persistent preferences for strategy selection
- **Strategy Selector**: Deterministic strategy selection based on context
- **Learning Rules**: Update preferences based on outcomes
- **RunJournal Integration**: Log all decisions for full traceability

## Key Principles

- **No ML, no network calls** - Pure heuristics + persistent rules
- **All decisions logged** in RunJournal for full auditability
- **Fully deterministic** and explainable
- **Simple and stable** - designed for long-term reliability

## Playbooks

The strategy layer defines 5 core playbooks:

1. **`target_failing_test_first`** - Focus on fixing specific failing tests
2. **`minimize_changeset`** - Reduce scope of changes
3. **`increase_timeout_once`** - Increase timeout and retry (for timeout failures)
4. **`ask_operator_with_context`** - Require human intervention
5. **`default`** - Standard approach without special constraints

## Quick Start

```python
from genus.strategy import StrategySelector, StrategyStoreJson

# Initialize
store = StrategyStoreJson(base_dir="var/strategy")
selector = StrategySelector(store=store)

# Select strategy based on evaluation
decision = selector.select_strategy(
    run_id="run_001",
    phase="fix",
    iteration=1,
    evaluation_artifact={
        "failure_class": "test_failure",
        "root_cause_hint": "assertion_error",
        "score": 40,
        "strategy_recommendations": ["target_failing_test_first"],
    },
)

print(f"Selected: {decision.selected_playbook}")
print(f"Reason: {decision.reason}")
```

## Learning from Outcomes

```python
from genus.strategy import apply_learning_rule

# After run completes, apply learning
apply_learning_rule(
    store=store,
    decision=decision,
    outcome_score=85,  # 0-100, higher = better
    failure_class="test_failure",
    root_cause_hint="assertion_error",
)
```

The learning system will:
- **Boost** playbook weights after successful outcomes (score >= 70)
- **Penalize** playbook weights after failed outcomes (score < 50)
- **Record** all outcomes in learning history for analytics

## Integration with RunJournal

```python
from genus.strategy import log_strategy_decision
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore

# Create journal
run_store = JsonlRunStore(base_dir="var/runs")
journal = RunJournal(run_id="run_001", store=run_store)
journal.initialize(goal="Fix failing tests")

# Log strategy decision
log_strategy_decision(journal, decision, phase_id="fix_001")
```

## Strategy Selection Scoring

Playbooks are scored based on multiple factors:

1. **Profile weight** (base score from configuration)
2. **Failure class match** (+20 if playbook recommended for this failure class)
3. **Root cause match** (+15 if playbook recommended for this root cause)
4. **Evaluation recommendations** (+30 if in strategy_recommendations)
5. **Learning history bonus** (up to +10 based on past success)
6. **First iteration bonus** (+5 for DEFAULT on first iteration)

The playbook with the highest total score is selected.

## Custom Profiles

Create custom strategy profiles for different contexts:

```python
from genus.strategy.models import StrategyProfile, PlaybookId

conservative_profile = StrategyProfile(
    name="conservative",
    playbook_weights={
        PlaybookId.MINIMIZE_CHANGESET: 20,
        PlaybookId.ASK_OPERATOR_WITH_CONTEXT: 10,
        PlaybookId.TARGET_FAILING_TEST_FIRST: 5,
        PlaybookId.DEFAULT: 0,
        PlaybookId.INCREASE_TIMEOUT_ONCE: -5,
    }
)

store.save_profile(conservative_profile)
selector = StrategySelector(store=store, profile_name="conservative")
```

## Storage Layout

```
var/strategy/
  strategy_store.json          # Main store file
```

The store contains:
- **profiles**: Named strategy profiles with playbook weights
- **learning_history**: Record of past decisions and outcomes

## Environment Variables

- `GENUS_STRATEGY_STORE_DIR`: Override default storage directory (default: `var/strategy/`)

## Examples

See `examples/strategy_usage.py` for comprehensive usage examples including:

- Basic strategy selection
- Test failure handling
- Learning from outcomes
- RunJournal integration
- Timeout handling
- Custom profiles
- Full DevLoop integration pattern

## Architecture

```
genus/strategy/
├── __init__.py                # Package exports
├── models.py                  # Data models (PlaybookId, StrategyDecision, StrategyProfile)
├── registry.py                # Playbook registry (PLAYBOOKS)
├── store_json.py              # Persistent storage (StrategyStoreJson)
├── selector.py                # Selection logic (StrategySelector)
├── learning.py                # Learning rules (apply_learning_rule)
└── journal_integration.py     # RunJournal helpers
```

## Testing

Run the strategy layer tests:

```bash
pytest tests/unit/test_strategy.py -v
```

All 31 tests should pass.

## Future Enhancements (Post v1)

- More sophisticated learning algorithms
- Strategy composition (combine multiple playbooks)
- A/B testing framework for playbook evaluation
- Analytics dashboard for strategy performance
- Auto-tuning of profile weights based on repository characteristics

## Related Documentation

- [Evaluation Agent](../genus/meta/agents/evaluation_agent.py) - Generates evaluation artifacts
- [Taxonomy](../genus/meta/taxonomy.py) - Defines failure classes and root causes
- [RunJournal](../genus/memory/run_journal.py) - Logging and artifact storage
