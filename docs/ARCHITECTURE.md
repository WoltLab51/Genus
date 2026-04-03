# GENUS Architecture

## Overview

GENUS (self-aware agent orchestration system) is a modular, event-driven architecture for coordinating intelligent agents with built-in system state monitoring and health intelligence.

## Core Principles

1. **Clean Architecture**: Strict dependency direction with core abstractions at the center
2. **Event-Driven Communication**: All agent communication through publish-subscribe message bus
3. **Dependency Injection**: No global singletons; all dependencies injected through constructors
4. **Self-Awareness**: System monitors its own health and operational state
5. **Modularity**: Independent modules with clear boundaries

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         API Layer                            │
│  (FastAPI, Authentication, Error Handling, /system/health)  │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────┴─────────────────────────────────────┐
│                    Agent Layer                               │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐       │
│  │DataCollector │  │  Analysis   │  │   Decision   │       │
│  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘       │
│         │                  │                 │               │
└─────────┼──────────────────┼─────────────────┼───────────────┘
          │                  │                 │
┌─────────┴──────────────────┴─────────────────┴───────────────┐
│                     Message Bus                               │
│          (Publish-Subscribe + State Tracking)                 │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────┴─────────────────────────────────────┐
│                    Core Layer                                │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐       │
│  │ Agent ABC    │  │   Config    │  │ SystemState  │       │
│  │ (Lifecycle)  │  │             │  │  Tracker     │       │
│  └──────────────┘  └─────────────┘  └──────────────┘       │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────┴─────────────────────────────────────┐
│                   Storage Layer                              │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐       │
│  │ MemoryStore  │  │DecisionStore│  │FeedbackStore │       │
│  └──────────────┘  └─────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Module Structure

### Core (`genus/core/`)

**Purpose**: Fundamental abstractions and system state management

**Components**:
- `agent.py`: Agent base class and lifecycle management
- `config.py`: Configuration with environment variable validation
- `system_state.py`: System health monitoring and state tracking

**Agent Lifecycle**:
1. `__init__` - Inject dependencies (NO subscriptions here!)
2. `initialize()` - Subscribe to message bus topics
3. `start()` - Transition to RUNNING state
4. `stop()` - Unsubscribe and transition to STOPPED

**Agent States**:
- CREATED - Initial state after construction
- INITIALIZED - Dependencies set up, subscriptions active
- RUNNING - Actively processing messages
- STOPPED - Cleanly shut down
- FAILED - Multiple errors exceeded threshold

### Communication (`genus/communication/`)

**Purpose**: Decoupled agent communication

**Components**:
- `message_bus.py`: Publish-subscribe message bus

**Features**:
- Topic-based routing
- Message history for observability
- Automatic error reporting to SystemStateTracker
- Handler error isolation (one failure doesn't affect others)

**Usage**:
```python
# Subscribe
bus.subscribe("topic", async_handler)

# Publish
await bus.publish("topic", data, source="agent_name")

# Unsubscribe
bus.unsubscribe("topic", handler)
```

### Storage (`genus/storage/`)

**Purpose**: Data persistence and retrieval

**Components**:
- `memory_store.py`: Key-value store for agent data
- `decision_store.py`: Decision tracking and outcomes
- `feedback_store.py`: User feedback collection

### Agents (`genus/agents/`)

**Purpose**: Business logic implementation

**Components**:
- `data_collector.py`: Ingests and preprocesses data
- `analysis.py`: Analyzes processed data
- `decision.py`: Makes decisions based on analysis

**Communication Pattern**:
```
data.raw → [DataCollector] → data.processed → [Analysis] →
analysis.complete → [Decision] → decision.made
```

**Error Handling**:
- All agents use try/except in handlers
- Success: Call `self.record_success()`
- Error: Call `self.record_error(error_msg)` and re-raise
- System automatically tracks agent health

### API (`genus/api/`)

**Purpose**: REST API interface

**Components**:
- `app.py`: FastAPI application factory
- `middleware.py`: Authentication middleware
- `errors.py`: Error handling middleware

**Endpoints**:
- `GET /health` - Basic health check (no auth)
- `GET /system/health` - Detailed health report (auth required)
- `POST /data/ingest` - Ingest raw data
- `GET /decisions` - List agent decisions
- `POST /feedback` - Submit feedback

**Authentication**:
- API key via `Authorization: Bearer <key>` header
- All endpoints except `/health` require authentication

## System State Monitoring

### Health States

**HEALTHY**:
- No failed agents
- Fewer than 3 errors in last 5 minutes
- Less than 50% agents stale (no activity in 10 min)

**DEGRADED**:
- 3-9 errors in last 5 minutes
- OR more than 50% agents stale

**FAILING**:
- Any agent in FAILED state
- OR 10+ errors in last 5 minutes

### State Tracking

The `SystemStateTracker` monitors:
1. **Agent Errors**: Execution failures per agent
2. **Pipeline Failures**: End-to-end pipeline issues
3. **Message Bus Errors**: Handler failures
4. **Event Staleness**: Last successful run timestamps

### Integration Points

**MessageBus → StateTracker**:
- Handler errors automatically reported
- Topic and error message captured

**Agents → StateTracker**:
- Agent states updated via API
- Execution outcomes tracked (success/error)

### Observability Features

1. **Timestamps**: All events timestamped
2. **Error Counts**: Total and per-agent counts
3. **Last Successful Run**: Per-agent timestamps
4. **Message History**: Last 1000 messages retained
5. **Error History**: Last 100 errors per source

## Testing

### Unit Tests (`tests/unit/`)
- Individual component testing
- Mock dependencies
- Fast execution

### Integration Tests (`tests/integration/`)
- End-to-end flows
- API endpoint testing
- Multi-agent coordination

### Test Configuration
- `pytest.ini`: Pytest configuration with asyncio auto mode
- Run tests: `python -m pytest tests/ -v`

## Configuration

### Environment Variables
- `API_KEY` (required): API authentication key
- `DEBUG` (optional): Enable debug mode (default: false)
- `HOST` (optional): Server host (default: 0.0.0.0)
- `PORT` (optional): Server port (default: 8000)
- `DATABASE_URL` (optional): Database connection string

### Example `.env`
```
API_KEY=your_secret_key_here
DEBUG=false
HOST=0.0.0.0
PORT=8000
```

## Design Patterns

### Dependency Injection
```python
# In lifespan (startup)
message_bus = MessageBus(state_tracker)
agent = DataCollectorAgent(message_bus, memory_store)

# No global state, everything passed explicitly
```

### Publish-Subscribe
```python
# Agents never reference each other directly
await bus.publish("data.processed", data)
# Other agents subscribed to "data.processed" receive it
```

### Error Isolation
```python
# One handler failure doesn't stop others
try:
    await handler(message)
except Exception as e:
    state_tracker.record_message_bus_error(topic, str(e))
    # Continue to next handler
```

### Self-Monitoring
```python
# Agents report their own outcomes
try:
    process_data()
    self.record_success()
except Exception as e:
    self.record_error(str(e))
    raise
```

## Extending GENUS

### Adding a New Agent

1. Create class extending `Agent`:
```python
class MyAgent(Agent):
    def __init__(self, message_bus, ...):
        super().__init__("my_agent")
        self.message_bus = message_bus
```

2. Implement lifecycle:
```python
async def initialize(self):
    self.message_bus.subscribe("my_topic", self._handler)
    self.state = AgentState.INITIALIZED

async def stop(self):
    self.message_bus.unsubscribe("my_topic", self._handler)
    await super().stop()
```

3. Add error handling:
```python
async def _handler(self, message):
    try:
        # Process message
        self.record_success()
    except Exception as e:
        self.record_error(str(e))
        raise
```

4. Register in `app.py` lifespan

### Adding a New Endpoint

1. Add route in `app.py`:
```python
@app.get("/my/endpoint")
async def my_endpoint():
    # Access dependencies via app.state
    data = app.state.my_store.get_data()
    return {"data": data}
```

2. Authentication is automatic (all endpoints except `/health`)

## Best Practices

1. **Never create global singletons** - Use dependency injection
2. **Subscribe in `initialize()`, not `__init__`** - Follow lifecycle
3. **Always handle errors in message handlers** - Record outcomes
4. **Use message bus for all agent communication** - No direct calls
5. **Keep agents focused** - Single responsibility principle
6. **Test with realistic flows** - Integration tests matter
7. **Monitor system health** - Use `/system/health` endpoint

## Security Considerations

1. **API Key Management**: Never commit keys to source control
2. **Error Messages**: Don't expose sensitive data in errors
3. **Input Validation**: Validate all API inputs
4. **Rate Limiting**: Consider adding for production
5. **HTTPS**: Always use HTTPS in production

## Performance Considerations

1. **Message History**: Limited to 1000 messages
2. **Error History**: Limited to 100 errors per source
3. **Async Processing**: All message handlers are async
4. **In-Memory Storage**: Not suitable for production scale
5. **Database**: Consider persistent storage for production

## Future Enhancements

1. **Persistent Storage**: Database integration
2. **Metrics Export**: Prometheus/Grafana integration
3. **Alerting**: Webhook notifications for DEGRADED/FAILING states
4. **Agent Discovery**: Dynamic agent registration
5. **Load Balancing**: Multiple instances of same agent type
6. **Circuit Breakers**: Prevent cascade failures
7. **Retry Policies**: Configurable retry strategies

## Troubleshooting

### Agent Not Receiving Messages
- Check subscriptions happen in `initialize()`, not `__init__`
- Verify agent is started (`await agent.start()`)
- Check message bus has subscribers for topic

### System State FAILING
- Check `/system/health` for recent errors
- Review agent status in health report
- Check message bus error log

### Tests Failing
- Ensure `API_KEY` environment variable is set
- Use `with TestClient(app)` context manager
- Check async test configuration in `pytest.ini`

### Authentication Issues
- Verify `Authorization: Bearer <key>` header format
- Check API_KEY matches configuration
- Remember `/health` doesn't require auth, others do
