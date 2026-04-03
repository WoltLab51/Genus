# GENUS Architecture

## Overview

GENUS follows clean architecture with strict dependency direction: agents depend on core abstractions, communication is decoupled via message bus, and modules are independent.

## Modules

### Core (genus/core/)

**Responsibilities:**
- Agent base class and lifecycle management
- Configuration management
- Core abstractions

**Key Components:**
- `Agent`: Abstract base class with strict lifecycle
- `AgentState`: Enum for agent states (CREATED, INITIALIZED, RUNNING, STOPPED)
- `Config`: Application configuration with environment variable validation

**Lifecycle:**
```
Agent Creation → __init__ (inject dependencies)
              ↓
         initialize() (subscribe to topics)
              ↓
            start() (transition to RUNNING)
              ↓
            stop() (unsubscribe, STOPPED)
```

### Communication (genus/communication/)

**Responsibilities:**
- Pub-sub messaging between agents
- Message history for observability

**Key Components:**
- `MessageBus`: Unified pub-sub bus for all agent communication
- `Message`: Message structure with topic, data, sender, timestamp

**Pattern:**
All agent communication goes through MessageBus. Agents never communicate directly.

### Storage (genus/storage/)

**Responsibilities:**
- Data persistence
- Learning mechanism
- Pattern analysis

**Key Components:**
- `MemoryStore`: Generic key-value store
- `DecisionStore`: Store for decision records
- `FeedbackStore`: Store for feedback records
- `LearningEngine`: Analyzes feedback and adjusts decisions

**ORM Models:**
- `DecisionModel`: Decision records with context, recommendation, confidence
- `FeedbackModel`: Feedback with score, label, comment
- `MemoryModel`: Generic key-value storage

### Agents (genus/agents/)

**Responsibilities:**
- Business logic for data processing, analysis, and decision-making
- Learning integration

**Key Components:**

1. **DataCollectorAgent**
   - Subscribes to: `data.input`
   - Publishes to: `data.processed`
   - Responsibility: Collect and process incoming data

2. **AnalysisAgent**
   - Subscribes to: `data.processed`
   - Publishes to: `analysis.complete`
   - Responsibility: Analyze data and generate insights

3. **DecisionAgent**
   - Subscribes to: `analysis.complete`
   - Publishes to: `decision.made`, `feedback.submitted`
   - Responsibility: Make decisions with learning capability
   - Special: Integrates LearningEngine to improve over time

### API (genus/api/)

**Responsibilities:**
- HTTP API endpoints
- Authentication and error handling
- Lifespan management

**Key Components:**
- `create_app()`: FastAPI application factory
- `AuthenticationMiddleware`: API key authentication
- `ErrorHandlingMiddleware`: Structured error responses

**Endpoints:**
- `GET /health`: Health check (no auth)
- `POST /data`: Submit data for processing
- `POST /feedback`: Submit feedback for learning
- `GET /decisions`: List all decisions
- `GET /decisions/{id}`: Get specific decision
- `GET /feedback`: List all feedback
- `GET /learning/analysis`: Get learning statistics
- `GET /messages`: Get message history

## Data Flow

### Normal Pipeline
```
User → POST /data
  ↓
DataCollectorAgent → publishes "data.input"
  ↓
  → publishes "data.processed"
  ↓
AnalysisAgent → receives "data.processed"
  ↓
  → publishes "analysis.complete"
  ↓
DecisionAgent → receives "analysis.complete"
  ↓
  → queries LearningEngine for similar past decisions
  ↓
  → adjusts confidence based on past learning
  ↓
  → stores decision in DecisionStore
  ↓
  → publishes "decision.made"
  ↓
User ← GET /decisions (retrieve decision)
```

### Feedback & Learning Loop
```
User → POST /feedback
  ↓
DecisionAgent → receives feedback
  ↓
  → stores in FeedbackStore
  ↓
  → invalidates learning cache
  ↓
  → publishes "feedback.submitted"
  ↓
Next Decision → LearningEngine analyzes feedback
  ↓
  → adjusts confidence based on patterns
  ↓
  → improved decision made
```

## Learning Mechanism

### Pattern Extraction
```python
# From context and recommendation
context = "deploy application to production"
recommendation = "proceed with deployment"

# Extract pattern signature (simplified)
pattern = hash(key_terms_from(context, recommendation))
```

### Pattern Scoring
```python
class PatternScore:
    success_count: int
    failure_count: int
    total_score: float
    decision_count: int

    def get_weight(self) -> float:
        # Weight = f(success_rate, average_score)
        # Range: 0.1 (very bad) to 2.0 (very good)
        return combine(success_rate, average_score)
```

### Decision Adjustment
```python
# Before making decision
original_confidence = 0.75
pattern = extract_pattern(context, recommendation)
pattern_score = get_pattern_score(pattern)
weight = pattern_score.get_weight()

# Adjust
adjusted_confidence = original_confidence * weight
adjusted_confidence = clamp(adjusted_confidence, 0.0, 1.0)
```

## Dependency Injection

No global singletons are used. All dependencies created in FastAPI lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create dependencies
    config = Config()
    message_bus = MessageBus()
    memory_store = MemoryStore(config.database_url)
    decision_store = DecisionStore(config.database_url)
    feedback_store = FeedbackStore(config.database_url)

    # Initialize stores
    await memory_store.initialize()
    await decision_store.initialize()
    await feedback_store.initialize()

    # Create agents with dependency injection
    data_collector = DataCollectorAgent("DataCollector", message_bus)
    analysis_agent = AnalysisAgent("AnalysisAgent", message_bus, memory_store)
    decision_agent = DecisionAgent(
        "DecisionAgent", message_bus, decision_store, feedback_store
    )

    # Initialize and start agents
    for agent in [data_collector, analysis_agent, decision_agent]:
        await agent.initialize()
        await agent.start()

    # Store in app state
    app.state.message_bus = message_bus
    # ... other components

    yield

    # Cleanup
    for agent in [data_collector, analysis_agent, decision_agent]:
        await agent.stop()
```

## Testing Strategy

### Unit Tests
- Test components in isolation
- Mock dependencies
- Focus on logic correctness

### Integration Tests
- Test full agent pipeline
- Test learning feedback loop
- Test API endpoints with real database

### Test Structure
```
tests/
├── unit/
│   ├── test_core.py          # Agent lifecycle, Config
│   ├── test_message_bus.py   # Pub-sub functionality
│   └── test_learning.py      # Learning mechanism
└── integration/
    ├── test_api.py            # API endpoints, auth
    └── test_agents.py         # Agent interactions
```

## Observability

### Logging Levels
- INFO: Normal operations, learning applied, feedback received
- DEBUG: Detailed message flow, subscriptions
- WARNING: Authentication failures
- ERROR: Exception in subscribers, system errors

### Key Logs
```
# Learning applied
🎓 LEARNING APPLIED: Increased confidence based on 5 past decisions
with 100% success rate (confidence: 0.75 -> 0.95)

# Feedback received
📝 Feedback received: success (score: 0.9) for decision abc-123

# Agent lifecycle
DataCollector initialized and subscribed to 'data.input'
DataCollector started
```

### Message History
All messages published through MessageBus are stored:
```python
message_history = [
    {
        "topic": "data.processed",
        "sender": "DataCollector",
        "timestamp": "2024-01-01T12:00:00"
    },
    # ...
]
```

## Security

### Authentication
- API key required for all endpoints except `/health`
- Format: `Authorization: Bearer <API_KEY>`
- Middleware validates on every request

### Error Handling
- All errors caught by ErrorHandlingMiddleware
- Structured JSON responses
- Debug mode adds traceback (disable in production)

### Environment Variables
- API_KEY: Required, no default
- DATABASE_URL: Optional, defaults to SQLite
- DEBUG: Optional, defaults to false

## Performance Considerations

### Async/Await
- All I/O operations are async
- Non-blocking database queries
- Concurrent message processing

### Caching
- Learning engine caches pattern scores
- Cache invalidated on new feedback
- Lazy re-computation on next decision

### Database
- SQLAlchemy async engine
- Connection pooling
- Indexes on decision_id, feedback_id

## Extension Points

### Adding New Agents
1. Inherit from `Agent` base class
2. Implement lifecycle methods
3. Subscribe to topics in `initialize()`
4. Inject dependencies via constructor

### Custom Learning Strategies
- Extend `LearningEngine`
- Override pattern extraction
- Customize weight calculation
- Maintain simple, interpretable logic

### New Storage Backends
- Implement store interface
- Keep async/await pattern
- Maintain ORM compatibility
