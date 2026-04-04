# Architecture Documentation

## Overview

GENUS (Generative ENvironment for Unified Systems) is designed with clean architecture principles to ensure modularity, testability, and maintainability.

## Core Principles

### 1. Separation of Concerns

Each module has a single, well-defined responsibility:

- **Core Module**: Defines abstract interfaces and base behaviors for agents
- **Communication Module**: Handles all message passing between agents
- **Config Module**: Manages system-wide configuration
- **Utils Module**: Provides shared utilities (logging, etc.)
- **Agents Module**: Contains concrete agent implementations

### 2. Dependency Direction

Dependencies always point inward toward abstractions:

```
Agents → Core (abstractions)
Agents → Communication (interface)
Communication → (no dependencies on agents)
Core → (no dependencies on anything)
```

This ensures:
- Core logic is independent of implementation details
- Modules can be tested in isolation
- Easy to swap implementations without affecting other modules

### 3. Interface Segregation

Agent interface is minimal and focused:

```python
class Agent(ABC):
    async def initialize() -> None
    async def start() -> None
    async def stop() -> None
    async def process_message(message) -> None
```

Agents only need to implement what they need, nothing more.

## Module Details

### Core Module

**Purpose**: Define agent abstractions and lifecycle management

**Key Components**:
- `Agent`: Abstract base class defining agent interface
- `AgentState`: Enumeration of possible agent states
- `Lifecycle`: Manages multiple agent lifecycles

**Design Decisions**:
- Abstract base class enforces contract without implementation
- State machine pattern for clear state transitions
- Lifecycle manager follows Single Responsibility Principle

### Communication Module

**Purpose**: Enable decoupled agent communication

**Key Components**:
- `MessageBus`: Publish-subscribe message broker
- `Message`: Data structure for messages
- `MessagePriority`: Priority levels for message handling

**Design Decisions**:
- Pub-sub pattern for loose coupling
- Async message delivery for non-blocking communication
- Topic-based routing with wildcard support
- Message history for debugging and monitoring

**Communication Flow**:
```
Agent A → publish(Message) → MessageBus → deliver → Agent B
                                        ↓
                                     Agent C
```

### Config Module

**Purpose**: Centralize configuration management

**Key Components**:
- `Config`: Singleton configuration manager

**Design Decisions**:
- Singleton pattern ensures single source of truth
- Layered configuration: defaults → file → environment
- Dot notation for hierarchical access
- Environment-specific overrides

### Agents Module

**Purpose**: Provide example implementations

**Key Components**:
- `WorkerAgent`: Task processor agent
- `CoordinatorAgent`: Task distributor agent

**Design Decisions**:
- Demonstrates proper use of base classes
- Shows message bus integration
- Implements complete lifecycle

## Communication Patterns

### 1. Request-Response Pattern

```python
# Coordinator sends task
coordinator.publish(Message(topic="tasks.work", payload=task))

# Worker processes and responds
worker.publish(Message(topic="tasks.results", payload=result))
```

### 2. Broadcast Pattern

```python
# One message to multiple subscribers
bus.subscribe("system.shutdown", worker1.id, worker1.process_message)
bus.subscribe("system.shutdown", worker2.id, worker2.process_message)
bus.publish(Message(topic="system.shutdown"))
```

### 3. Topic Filtering Pattern

```python
# Subscribe to specific topics
bus.subscribe("tasks.work", worker.id, handler)

# Or use wildcards
bus.subscribe("tasks.*", monitor.id, monitor_handler)
```

## State Management

### Agent States

```
INITIALIZED → RUNNING → PAUSED → RUNNING
                ↓
            STOPPED / ERROR
```

**State Transitions**:
- `initialize()`: → INITIALIZED
- `start()`: INITIALIZED → RUNNING
- `stop()`: * → STOPPED

## Extension Points

### Adding New Agent Types

1. Subclass `Agent`
2. Implement required methods
3. Add agent-specific logic
4. Register with lifecycle manager

Example:
```python
class MonitorAgent(Agent):
    async def initialize(self):
        # Subscribe to all topics for monitoring
        self._bus.subscribe("*", self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def process_message(self, message):
        # Log all messages
        self._logger.info(f"Monitored: {message.topic}")
```

### Adding New Communication Patterns

The message bus can be extended with:
- Priority queues
- Message persistence
- Replay capabilities
- Dead letter queues

## Testing Strategy

### Unit Tests
- Test each module in isolation
- Mock dependencies
- Test edge cases and error conditions

### Integration Tests
- Test agent communication
- Test lifecycle management
- Test multi-agent scenarios

### Example Test Structure
```python
def test_agent_communication():
    bus = MessageBus()
    agent1 = WorkerAgent(message_bus=bus)
    agent2 = WorkerAgent(message_bus=bus)

    # Test communication between agents
    # ...
```

## Performance Considerations

### Scalability
- Async I/O for non-blocking operations
- Message queues prevent overwhelming agents
- Independent agent execution

### Resource Management
- Graceful shutdown ensures cleanup
- Queue size limits prevent memory issues
- Message history limited to prevent unbounded growth

## Future Enhancements

### Short-term
- Add metrics collection
- Implement message persistence
- Add health checks

### Long-term
- Distributed message bus
- Agent clustering
- Web-based monitoring UI
- Service mesh integration
