# Learning Mechanism Documentation

## Overview

The GENUS learning mechanism enables the system to improve decisions based on past feedback without using machine learning libraries. It uses a simple, deterministic, pattern-based approach that is fully interpretable.

## Core Concept

The learning system is built on three key principles:

1. **Pattern Recognition**: Similar decisions are grouped by pattern
2. **Performance Tracking**: Success/failure rates are tracked per pattern
3. **Weight Adjustment**: Confidence is adjusted based on past performance

## Components

### PatternScore

Tracks the performance of a specific decision pattern.

```python
class PatternScore:
    success_count: int      # Number of successful decisions
    failure_count: int      # Number of failed decisions
    total_score: float      # Sum of all feedback scores
    decision_count: int     # Total decisions with this pattern
```

**Key Methods:**
- `get_success_rate()`: Returns ratio of successes to total decisions
- `get_average_score()`: Returns mean feedback score
- `get_weight()`: Calculates adjustment weight (0.1 to 2.0)

### LearningEngine

Main learning component that analyzes feedback and adjusts decisions.

**Constructor:**
```python
LearningEngine(feedback_store, decision_store)
```

**Key Methods:**

#### `analyze_feedback() -> Dict[str, Any]`
Analyzes all stored feedback to identify patterns.

Returns:
```python
{
    "total_feedback": 10,
    "success_count": 8,
    "failure_count": 2,
    "success_rate": 0.8,
    "patterns": {
        "abc123": {
            "weight": 1.5,
            "success_rate": 0.9,
            "decision_count": 5,
            "average_score": 0.85
        }
    }
}
```

#### `adjust_decision(context, recommendation, confidence) -> Tuple`
Adjusts a decision based on past learning.

Args:
- `context`: Decision context (string)
- `recommendation`: Proposed recommendation (string)
- `confidence`: Original confidence score (0.0-1.0)

Returns:
```python
(
    adjusted_recommendation,  # str (unchanged in current implementation)
    adjusted_confidence,      # float (adjusted based on learning)
    learning_info            # dict (metadata about adjustment)
)
```

#### `query_similar_decisions(context, recommendation) -> List[Dict]`
Finds past decisions with similar patterns.

Returns list of decisions with their feedback.

## Pattern Extraction

### Algorithm

1. **Tokenization**: Extract key terms from context and recommendation
2. **Normalization**: Convert to lowercase, take first N words
3. **Hashing**: Create MD5 hash of sorted terms
4. **Signature**: Use first 8 characters as pattern ID

### Example

```python
context = "deploy application to production environment"
recommendation = "proceed with deployment after review"

# Extract terms
context_terms = {"deploy", "application", "production", "environment"}
rec_terms = {"proceed", "deployment", "after", "review"}

# Create signature
pattern = hash(sorted(context_terms) + sorted(rec_terms))[:8]
# Result: "a1b2c3d4"
```

### Why This Works

- Similar contexts produce similar term sets
- Same patterns get grouped together
- Variations in wording still match
- Fast computation with hashing

## Weight Calculation

### Formula

```python
def get_weight(success_rate, average_score):
    base_weight = success_rate * 1.5 + average_score * 0.5
    return clamp(base_weight, 0.1, 2.0)
```

### Weight Ranges

| Success Rate | Avg Score | Weight | Effect |
|-------------|-----------|--------|--------|
| 100% | 0.9 | 2.0 | Maximum confidence boost |
| 80% | 0.7 | 1.55 | Moderate confidence boost |
| 50% | 0.5 | 1.0 | Neutral (no change) |
| 20% | 0.3 | 0.45 | Significant confidence reduction |
| 0% | 0.1 | 0.1 | Minimum confidence |

### Examples

**Successful Pattern:**
```python
pattern = PatternScore()
# Add 5 successful feedbacks
for _ in range(5):
    pattern.add_feedback("success", 0.9)

weight = pattern.get_weight()  # Returns ~2.0
confidence = 0.75 * weight      # 0.75 * 2.0 = 1.5 → clamped to 1.0
```

**Failed Pattern:**
```python
pattern = PatternScore()
# Add 5 failed feedbacks
for _ in range(5):
    pattern.add_feedback("failure", 0.2)

weight = pattern.get_weight()  # Returns ~0.1
confidence = 0.75 * weight      # 0.75 * 0.1 = 0.075 → clamped to 0.075
```

## Decision Adjustment Process

### Step-by-Step

1. **Extract Pattern**
   ```python
   pattern = _extract_pattern(context, recommendation)
   ```

2. **Check Cache**
   ```python
   if not cache_valid:
       await analyze_feedback()
   ```

3. **Get Pattern Score**
   ```python
   pattern_score = pattern_cache.get(pattern)
   if pattern_score is None:
       return original_decision  # No learning data
   ```

4. **Calculate Weight**
   ```python
   weight = pattern_score.get_weight()
   ```

5. **Adjust Confidence**
   ```python
   adjusted_confidence = original_confidence * weight
   adjusted_confidence = clamp(adjusted_confidence, 0.0, 1.0)
   ```

6. **Generate Metadata**
   ```python
   learning_info = {
       "pattern": pattern,
       "learning_applied": True,
       "original_confidence": original_confidence,
       "adjusted_confidence": adjusted_confidence,
       "pattern_weight": weight,
       "pattern_success_rate": success_rate,
       "adjustment_reason": "..."
   }
   ```

## Integration with DecisionAgent

### Decision Flow with Learning

```python
async def _handle_analysis(message):
    # 1. Generate initial recommendation
    recommendation = _generate_recommendation(analysis)
    initial_confidence = 0.75

    # 2. Query similar past decisions
    similar = await learning_engine.query_similar_decisions(
        context, recommendation
    )

    # 3. Adjust based on learning
    adjusted_rec, adjusted_conf, info = await learning_engine.adjust_decision(
        context, recommendation, initial_confidence
    )

    # 4. Log learning influence
    if info["learning_applied"]:
        logger.info(f"🎓 LEARNING APPLIED: {info['adjustment_reason']}")

    # 5. Store decision with learning info
    await decision_store.store_decision(
        decision_id, context, adjusted_rec, adjusted_conf, reasoning
    )
```

### Feedback Loop

```python
async def submit_feedback(decision_id, score, label):
    # 1. Store feedback
    await feedback_store.store_feedback(
        feedback_id, decision_id, score, label
    )

    # 2. Invalidate cache
    learning_engine.invalidate_cache()

    # 3. Next decision will use updated learning
```

## Observability

### Logging

**Learning Applied:**
```
🎓 LEARNING APPLIED: Increased confidence based on 5 past decisions
with 100% success rate (confidence: 0.75 -> 0.95)
```

**No Learning Data:**
```
No learning data available for this decision pattern
```

**Feedback Received:**
```
📝 Feedback received: success (score: 0.9) for decision abc-123
```

### Learning Analysis Endpoint

GET `/learning/analysis` returns:
```json
{
  "total_feedback": 25,
  "success_count": 20,
  "failure_count": 5,
  "success_rate": 0.8,
  "patterns": {
    "a1b2c3d4": {
      "weight": 1.75,
      "success_rate": 0.9,
      "decision_count": 10,
      "average_score": 0.88
    },
    "e5f6g7h8": {
      "weight": 0.3,
      "success_rate": 0.2,
      "decision_count": 5,
      "average_score": 0.25
    }
  }
}
```

## Testing the Learning Mechanism

### Unit Tests

**Test Weight Increase:**
```python
async def test_successful_pattern_increases_weight():
    # Create 5 successful decisions
    for i in range(5):
        await decision_store.store_decision(...)
        await feedback_store.store_feedback(..., label="success", score=0.95)

    # Adjust similar decision
    rec, conf, info = await learning_engine.adjust_decision(...)

    assert conf > original_confidence
    assert info["pattern_weight"] > 1.0
```

**Test Weight Decrease:**
```python
async def test_failed_pattern_decreases_weight():
    # Create 5 failed decisions
    for i in range(5):
        await decision_store.store_decision(...)
        await feedback_store.store_feedback(..., label="failure", score=0.2)

    # Adjust similar decision
    rec, conf, info = await learning_engine.adjust_decision(...)

    assert conf < original_confidence
    assert info["pattern_weight"] < 1.0
```

### Integration Tests

**Test Learning Loop:**
```python
async def test_learning_feedback_loop():
    # Submit data
    await data_collector.collect_data("deploy to production")
    await asyncio.sleep(0.5)

    # Get decision
    decisions = await decision_store.get_all_decisions()
    decision_id = decisions[0]["decision_id"]
    original_conf = decisions[0]["confidence"]

    # Submit positive feedback
    await decision_agent.submit_feedback(decision_id, 0.95, "success")

    # Submit similar data
    await data_collector.collect_data("deploy to production")
    await asyncio.sleep(0.5)

    # Verify learning applied
    new_decisions = await decision_store.get_all_decisions()
    new_conf = new_decisions[0]["confidence"]

    # Confidence should increase
    assert new_conf > original_conf
```

## Limitations

### Current Limitations

1. **Pattern Granularity**: Simple hash-based patterns may group dissimilar decisions
2. **No Context Awareness**: Doesn't consider temporal or environmental context
3. **Equal Weighting**: All feedback weighted equally regardless of age
4. **No Decay**: Old patterns never expire
5. **Binary Labels**: Only "success" or "failure", no nuance

### Mitigations

1. **Pattern Granularity**: Can be improved with better tokenization
2. **Context Awareness**: Can add metadata to patterns
3. **Equal Weighting**: Can implement time-based decay
4. **No Decay**: Can add pattern expiry logic
5. **Binary Labels**: Score provides some nuance

## Future Enhancements

### Short Term
- More sophisticated pattern matching
- Configurable learning rates
- Pattern confidence thresholds

### Medium Term
- Time-based pattern decay
- Context-aware patterns
- Hierarchical pattern matching

### Long Term
- Pattern clustering
- Anomaly detection
- Learning snapshots and rollback

## Best Practices

### For Operators

1. **Provide Diverse Feedback**: Cover various scenarios
2. **Be Consistent**: Use labels consistently
3. **Use Score Range**: Leverage 0.0-1.0 score range fully
4. **Monitor Analysis**: Regularly check `/learning/analysis`
5. **Watch Logs**: Monitor learning application logs

### For Developers

1. **Keep Patterns Simple**: Don't over-complicate extraction
2. **Test Edge Cases**: Zero feedback, all success, all failure
3. **Document Changes**: Pattern changes affect grouping
4. **Validate Weights**: Ensure weights stay in valid range
5. **Cache Wisely**: Balance freshness vs. performance

## Troubleshooting

### Learning Not Applied

**Symptom**: Confidence never changes

**Causes:**
- No feedback submitted
- Pattern mismatch (check pattern extraction)
- Cache not invalidated

**Solution:**
```python
# Check feedback exists
feedback_count = await feedback_store.get_all_feedback()
print(f"Total feedback: {len(feedback_count)}")

# Force cache invalidation
learning_engine.invalidate_cache()

# Manually analyze
analysis = await learning_engine.analyze_feedback()
print(analysis)
```

### Unexpected Adjustments

**Symptom**: Confidence changes unexpectedly

**Causes:**
- Pattern collision (different decisions, same pattern)
- Incorrect feedback labels
- Score calculation error

**Solution:**
```python
# Check pattern extraction
pattern = learning_engine._extract_pattern(context, rec)
print(f"Pattern: {pattern}")

# Check pattern score
await learning_engine.analyze_feedback()
pattern_info = learning_engine._pattern_cache.get(pattern)
if pattern_info:
    print(f"Weight: {pattern_info.get_weight()}")
    print(f"Success rate: {pattern_info.get_success_rate()}")
```

### Cache Issues

**Symptom**: New feedback not reflected

**Cause:** Cache not invalidated

**Solution:**
```python
# Always invalidate after feedback
await decision_agent.submit_feedback(...)
decision_agent.learning_engine.invalidate_cache()

# Or manually
learning_engine.invalidate_cache()
```
