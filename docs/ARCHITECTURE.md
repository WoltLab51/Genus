# GENUS Architecture

## Overview

GENUS (Generic Agent System) follows clean architecture principles with strict separation of concerns and dependency inversion.

## Core Principles

### 1. Decoupled Communication

All agent communication must go through the MessageBus using the publish-subscribe pattern. Agents never communicate directly with each other.

**Why?**
- Loose coupling between agents
- Easy to add/remove agents
- Better testability
- Event replay capabilities

**Example:**
```python
# Good: Using MessageBus
await agent.publish("task.assigned", {"data": "value"})

# Bad: Direct agent-to-agent communication
await other_agent.handle_task(data)  # Don't do this!
```

### 2. Clean Architecture Layers

```
┌─────────────────────────────────────┐
│           UI / API Layer            │
│    (FastAPI, Dashboard HTML)        │
├─────────────────────────────────────┤
│         Agent Layer                 │
│  (CoordinatorAgent, WorkerAgent)    │
├─────────────────────────────────────┤
│      Communication Layer            │
│   (MessageBus, EventBus)            │
├─────────────────────────────────────┤
│        Storage Layer                │
│  (MemoryStore, FeedbackStore)       │
├─────────────────────────────────────┤
│         Core Layer                  │
│    (Agent, Message abstractions)    │
└─────────────────────────────────────┘
```

Dependencies flow inward: outer layers depend on inner layers, never vice versa.

### 3. Event-Driven Observability

The EventBus provides system-wide observability without creating coupling between components.

**Event Types:**
- `agent.started` - Agent lifecycle
- `decision.created` - Decision tracking
- `decision.made` - Agent decisions
- `decision.feedback` - Feedback submission
- `task.completed` - Task completion

**Benefits:**
- Monitoring without coupling
- Audit trails
- Debugging and diagnostics
- Future analytics

### 4. Modular Design

Each component can be used independently:

```python
# Use just the MessageBus
from genus.communication import MessageBus
bus = MessageBus()

# Use just the storage
from genus.storage import MemoryStore
store = MemoryStore()

# Use agents with or without storage
agent = WorkerAgent("worker-1", bus)  # No storage
agent = WorkerAgent("worker-1", bus, memory_store=store)  # With storage
```

## Component Details

### MessageBus

**Purpose:** Central hub for agent communication

**Key Features:**
- Topic-based pub/sub
- Multiple subscribers per topic
- Async message delivery
- Topic isolation

**Usage Pattern:**
```python
bus = MessageBus()

# Subscribe
async def handler(message):
    print(f"Received: {message.payload}")

bus.subscribe("my.topic", handler)

# Publish
message = Message(topic="my.topic", payload={"key": "value"})
await bus.publish(message)
```

### EventBus

**Purpose:** Observability and event logging

**Key Features:**
- Event persistence
- Event filtering
- Multiple listeners
- Event history

**Usage Pattern:**
```python
event_bus = EventBus()

# Subscribe to events
async def log_event(event):
    print(f"Event: {event.event_type}")

event_bus.subscribe("decision.feedback", log_event)

# Emit events
await event_bus.emit_event(
    "decision.feedback",
    {"decision_id": "123", "score": 1.0},
    source="agent-1"
)

# Query event history
recent_events = event_bus.get_events(event_type="decision.feedback", limit=10)
```

### MemoryStore

**Purpose:** Persistent storage for agent decisions

**Key Features:**
- SQLAlchemy-based
- Async operations
- Filtering and querying
- JSON data storage

**Schema:**
```python
Decision:
  - id: str (UUID)
  - agent_id: str
  - decision_type: str
  - input_data: JSON
  - output_data: JSON
  - timestamp: datetime
  - metadata: JSON
```

### FeedbackStore

**Purpose:** Storage for decision feedback

**Key Features:**
- Linked to decisions (foreign key)
- Score validation (-1 to 1)
- Label validation (success/failure/neutral)
- Query by decision or label

**Schema:**
```python
Feedback:
  - id: str (UUID)
  - decision_id: str (FK)
  - score: float (-1.0 to 1.0)
  - label: str (success/failure/neutral)
  - timestamp: datetime
  - notes: str (optional)
  - source: str (optional)
```

## Agent Communication Flow

```
┌──────────────┐     1. Subscribe      ┌──────────────┐
│  Agent A     │─────to "task.req"────→│  MessageBus  │
└──────────────┘                        └──────────────┘
                                               ▲
                                               │
                                        2. Publish
┌──────────────┐                              │
│  Agent B     │──────────────────────────────┘
└──────────────┘

                        3. MessageBus delivers
┌──────────────┐            to all            ┌──────────────┐
│  Agent A     │◄───────subscribers───────────│  MessageBus  │
└──────────────┘                              └──────────────┘
      │
      └─4. handle_message() called
```

## Decision Feedback Flow

```
1. Agent makes decision
   │
   ├─→ Store in MemoryStore (decision_id returned)
   │
   └─→ Emit "decision.made" event

2. Decision executes (time passes)

3. Feedback submitted (via API or programmatically)
   │
   ├─→ Validate decision exists
   │
   ├─→ Store in FeedbackStore
   │
   └─→ Emit "decision.feedback" event

4. Future agents can query feedback history
   │
   └─→ Learn from past decisions
```

## Extending GENUS

### Adding a New Agent

1. Inherit from `Agent` base class
2. Implement `handle_message()` method
3. Subscribe to relevant topics in `start()`
4. Use MessageBus for all communication

```python
class MyCustomAgent(Agent):
    async def start(self):
        self.subscribe("my.custom.topic")

    async def handle_message(self, message: Message):
        # Process message
        result = self.process(message.payload)

        # Store decision
        if self.memory_store:
            await self.memory_store.store_decision(
                agent_id=self.agent_id,
                decision_type="custom_processing",
                input_data=message.payload,
                output_data=result
            )

        # Publish result
        await self.publish("my.result.topic", result)
```

### Adding a New Event Type

Simply emit with a new event type - no registration needed:

```python
await event_bus.emit_event(
    "my.custom.event",
    {"custom": "data"},
    source="my-agent"
)
```

### Adding API Endpoints

Add to `genus/api/app.py`:

```python
@app.get("/custom-endpoint")
async def custom_endpoint(
    store: MemoryStore = Depends(get_memory_store)
):
    # Your logic here
    return {"result": "data"}
```

## Testing Strategy

### Unit Tests
- Test individual components in isolation
- Mock dependencies
- Fast execution

### Integration Tests
- Test component interactions
- Use in-memory database
- Test API endpoints

### Test Structure
```
tests/
├── unit/
│   ├── test_agent.py
│   ├── test_message_bus.py
│   ├── test_event_bus.py
│   └── test_storage.py
└── integration/
    └── test_api.py
```

## Performance Considerations

1. **Async Operations**: All I/O operations are async
2. **Connection Pooling**: SQLAlchemy manages database connections
3. **Event Log Size**: EventBus stores events in memory (clear periodically)
4. **Message Delivery**: Messages delivered to all subscribers concurrently

## Security Considerations

1. **Input Validation**: Pydantic schemas validate API input
2. **SQL Injection**: SQLAlchemy ORM prevents SQL injection
3. **CORS**: Configured in API (adjust for production)
4. **Database URL**: Use environment variables in production

## Future Enhancements

- [ ] Persistent event log (database-backed)
- [ ] Machine learning on feedback data
- [ ] Agent decision recommendation system
- [ ] Distributed agent deployment
- [ ] Real-time dashboard updates (WebSockets)
- [ ] Advanced feedback analytics
