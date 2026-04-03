# GENUS - Learning Decision System

A learning system that improves decisions based on feedback without machine learning libraries.

## Overview

GENUS (Generic Expert Network with Universal Synthesis) is a decision-making system that learns from past feedback to improve future decisions. It uses a simple, deterministic learning mechanism based on pattern recognition and success/failure tracking.

## Key Features

### 1. **Learning from Feedback**
   - Analyzes stored feedback (score, label)
   - Identifies patterns of successful vs failed decisions
   - Adjusts confidence based on past performance

### 2. **Decision Scoring**
   - Tracks performance of past decisions
   - Assigns weights to decision patterns
   - Increases weight for successful patterns
   - Decreases weight for failed patterns

### 3. **Agent-Based Architecture**
   - **DataCollectorAgent**: Collects and processes incoming data
   - **AnalysisAgent**: Analyzes data and generates insights
   - **DecisionAgent**: Makes decisions with learning capability

### 4. **Observability**
   - Logs when past feedback influences decisions
   - Message history tracking via MessageBus
   - Learning analysis endpoint showing patterns and performance

### 5. **No External ML Libraries**
   - Simple, interpretable logic
   - Deterministic behavior
   - Pattern-based scoring system

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI Application                   │
├─────────────────────────────────────────────────────────────┤
│  Authentication Middleware  │  Error Handling Middleware    │
├─────────────────────────────────────────────────────────────┤
│                           Agents                             │
│  ┌───────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ DataCollector │→ │ AnalysisAgent│→ │ DecisionAgent   │ │
│  │               │  │              │  │ + Learning      │ │
│  └───────────────┘  └──────────────┘  └─────────────────┘ │
│                             ↕                                │
│                       MessageBus                             │
├─────────────────────────────────────────────────────────────┤
│                    Storage Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ MemoryStore  │  │DecisionStore │  │ FeedbackStore    │ │
│  └──────────────┘  └──────────────┘  └──────────────────┘ │
│                    + LearningEngine                         │
└─────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites
- Python 3.8+
- pip

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file or set environment variables:

```bash
export API_KEY="your-secret-api-key"
export DATABASE_URL="sqlite+aiosqlite:///./genus.db"  # Optional
export DEBUG="false"  # Optional
export LOG_LEVEL="INFO"  # Optional
```

## Usage

### Running the API Server

```bash
# Set API key
export API_KEY="your-secret-key"

# Run with uvicorn
uvicorn genus.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

### API Endpoints

#### Health Check
```bash
curl http://localhost:8000/health
```

#### Submit Data (triggers decision pipeline)
```bash
curl -X POST http://localhost:8000/data \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"data": "deploy application to production"}'
```

#### Get Decisions
```bash
curl http://localhost:8000/decisions \
  -H "Authorization: Bearer your-secret-key"
```

#### Submit Feedback (enables learning)
```bash
curl -X POST http://localhost:8000/feedback \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "decision_id": "decision-uuid-here",
    "score": 0.9,
    "label": "success",
    "comment": "Excellent decision!"
  }'
```

#### Get Learning Analysis
```bash
curl http://localhost:8000/learning/analysis \
  -H "Authorization: Bearer your-secret-key"
```

### Example Learning Workflow

1. **Submit initial data**:
```bash
curl -X POST http://localhost:8000/data \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"data": "review security patch"}'
```

2. **Get the decision ID**:
```bash
curl http://localhost:8000/decisions \
  -H "Authorization: Bearer your-secret-key" | jq '.[0].decision_id'
```

3. **Submit positive feedback**:
```bash
curl -X POST http://localhost:8000/feedback \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "decision_id": "YOUR_DECISION_ID",
    "score": 0.95,
    "label": "success"
  }'
```

4. **Submit similar data again** - the system will adjust confidence based on past success:
```bash
curl -X POST http://localhost:8000/data \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"data": "review security patch"}'
```

5. **Check learning analysis**:
```bash
curl http://localhost:8000/learning/analysis \
  -H "Authorization: Bearer your-secret-key"
```

## Learning Mechanism

### How It Works

1. **Pattern Extraction**:
   - Each decision is analyzed to extract a pattern signature based on context and recommendation
   - Similar decisions are grouped by pattern

2. **Feedback Analysis**:
   - System tracks success/failure for each pattern
   - Calculates success rate and average score
   - Updates pattern weights

3. **Weight Calculation**:
   - Successful patterns: weight > 1.0 (increases confidence)
   - Failed patterns: weight < 1.0 (decreases confidence)
   - New patterns: weight = 1.0 (neutral)

4. **Decision Adjustment**:
   - Before making a decision, query past similar decisions
   - Adjust confidence based on pattern weight
   - Log learning influence for observability

### Example

```python
# Initial decision
Context: "deploy database migration"
Recommendation: "proceed with deployment"
Confidence: 0.75

# After 5 successful similar decisions
Adjusted Confidence: 0.95  # Increased by learning
Learning Info: "Increased confidence based on 5 past decisions with 100% success rate"
```

## Testing

### Run All Tests
```bash
pytest tests/ -v
```

### Run Unit Tests Only
```bash
pytest tests/unit/ -v
```

### Run Integration Tests Only
```bash
pytest tests/integration/ -v
```

### Run Learning Tests
```bash
pytest tests/unit/test_learning.py -v
```

## Development

### Project Structure
```
genus/
├── core/              # Agent ABC, Config, Lifecycle
├── communication/     # MessageBus
├── storage/          # Stores and Learning Engine
│   ├── models.py     # SQLAlchemy ORM models
│   ├── stores.py     # MemoryStore, DecisionStore, FeedbackStore
│   └── learning.py   # LearningEngine
├── agents/           # DataCollector, Analysis, Decision
└── api/              # FastAPI application

tests/
├── unit/             # Unit tests
└── integration/      # Integration tests
```

### Key Components

#### LearningEngine (genus/storage/learning.py)
- `analyze_feedback()`: Analyzes all feedback and identifies patterns
- `adjust_decision()`: Adjusts decisions based on past learning
- `query_similar_decisions()`: Finds similar past decisions

#### DecisionAgent (genus/agents/decision.py)
- Integrates LearningEngine
- Queries past similar decisions before making new ones
- Logs when learning influences decisions
- Handles feedback submission

### Design Principles

1. **No Global Singletons**: All dependencies injected via constructor
2. **Agent Lifecycle**: `__init__` → `initialize()` → `start()` → `stop()`
3. **Pub-Sub Communication**: All agents communicate via MessageBus
4. **Simple Learning**: No ML libraries, deterministic logic
5. **Observability**: All learning actions are logged

## Constraints

- ✅ No external ML libraries
- ✅ Simple and deterministic logic
- ✅ Does not break existing pipeline
- ✅ Uses FeedbackStore and DecisionStore (no duplicate storage)
- ✅ Learning behavior is visible and logged

## Observability

### Learning Logs
When decisions are influenced by past feedback, the system logs:
```
🎓 LEARNING APPLIED: Increased confidence based on 5 past decisions
with 100% success rate (confidence: 0.75 -> 0.95)
```

### Feedback Logs
When feedback is submitted:
```
📝 Feedback received: success (score: 0.9) for decision abc-123
```

### Message History
All agent communication is tracked:
```bash
curl http://localhost:8000/messages \
  -H "Authorization: Bearer your-secret-key"
```

## Documentation

- [README.md](README.md) - This file, getting started guide
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture and design
- [docs/LEARNING.md](docs/LEARNING.md) - Detailed learning mechanism documentation

## Future Enhancements

- Pattern similarity using more sophisticated matching
- Configurable learning rates
- Pattern decay for outdated feedback
- Context-aware pattern extraction
- Learning snapshots and rollback

## License

MIT

## Contributing

Contributions are welcome! Please ensure:
1. All tests pass
2. Code follows existing patterns
3. Learning mechanism remains simple and interpretable
4. No external ML libraries are added