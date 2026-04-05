# GENUS

**Generative ENvironment for Unified Systems**

A modular agent-based framework built on clean architecture principles.

## Dokumentation / Roter Faden

Einstieg in die GENUS-Dokumentation:

- 📍 **[docs/ROADMAP.md](docs/ROADMAP.md)** – Roter Faden: GENUS-2.0 Überblick, Meilensteine, E2E-Beispiel
- 🏗 [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md) – Modulgrenzen, Clean Architecture, Agent-Lifecycle
- 📋 [docs/TOPICS.md](docs/TOPICS.md) – Topic-Registry, Payload-Contracts, Recorder-Whitelist
- ⚖️ [docs/POLICIES.md](docs/POLICIES.md) – Decision-Semantik (accept/retry/replan/escalate/delegate)
- 🔒 [docs/SECURITY.md](docs/SECURITY.md) – Sicherheitsposture, Threat Model, geplante Maßnahmen
- 🛠 [docs/OPERATIONS.md](docs/OPERATIONS.md) – Konfiguration, EventStore, Debugging-Checkliste

## Overview

GENUS is a lightweight, extensible framework for building multi-agent systems with clear separation of concerns. It provides:

- **Modular Architecture**: Independent, loosely-coupled modules
- **Agent Communication**: Pub-sub message bus for decoupled agent interaction
- **Clean Design**: Follows SOLID principles and clean architecture
- **Extensibility**: Easy to add new agent types and behaviors
- **Type Safety**: Built with Python type hints for better IDE support

## Architecture

```
genus/
├── core/               # Core abstractions and base classes
│   ├── agent.py       # Agent base class and state management
│   └── lifecycle.py   # Agent lifecycle management
├── communication/     # Communication layer
│   └── message_bus.py # Pub-sub message bus implementation
├── config/            # Configuration management
│   └── settings.py    # Centralized configuration
├── utils/             # Utility functions
│   └── logger.py      # Logging utilities
└── agents/            # Concrete agent implementations
    ├── worker_agent.py      # Example worker agent
    └── coordinator_agent.py # Example coordinator agent
```

## Key Features

### 1. Modular Architecture

Each module has a single, well-defined responsibility:

- **Core**: Provides abstract base classes for agents
- **Communication**: Handles all inter-agent messaging
- **Config**: Manages configuration across the system
- **Utils**: Provides common utilities like logging

### 2. Strong Agent Communication

The message bus provides:
- Topic-based publish-subscribe pattern
- Asynchronous message delivery
- Wildcard topic matching
- Message history and monitoring
- Priority-based messaging

### 3. Clean Separation of Concerns

- Agents don't know about each other directly
- All communication goes through the message bus
- Configuration is centralized and environment-aware
- Logging is standardized across all components

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Basic Usage

```python
import asyncio
from genus.core.lifecycle import Lifecycle
from genus.communication.message_bus import MessageBus
from genus.agents import WorkerAgent, CoordinatorAgent
from genus.utils.logger import setup_logging

async def main():
    # Setup
    setup_logging(level="INFO")
    message_bus = MessageBus()

    # Create agents
    coordinator = CoordinatorAgent(name="Coordinator", message_bus=message_bus)
    worker = WorkerAgent(name="Worker-1", message_bus=message_bus)

    # Manage lifecycle
    lifecycle = Lifecycle()
    lifecycle.register_agent(coordinator)
    lifecycle.register_agent(worker)

    # Run
    await lifecycle.start_all()
    await asyncio.sleep(10)  # Run for 10 seconds
    await lifecycle.stop_all()

if __name__ == "__main__":
    asyncio.run(main())
```

## Creating Custom Agents

Extend the `Agent` base class:

```python
from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import Message

class MyAgent(Agent):
    async def initialize(self):
        # Setup resources
        self._transition_state(AgentState.INITIALIZED)

    async def start(self):
        # Start execution
        self._transition_state(AgentState.RUNNING)

    async def stop(self):
        # Cleanup
        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Message):
        # Handle incoming messages
        pass
```

## Design Principles

GENUS follows clean architecture principles:

### 1. Independence
- Modules don't depend on implementation details of other modules
- Agents operate independently and asynchronously
- Communication is always through well-defined interfaces

### 2. Testability
- Each component can be tested in isolation
- Dependency injection allows for easy mocking
- Clear interfaces make unit testing straightforward

### 3. Flexibility
- Easy to add new agent types
- Message bus supports any message structure
- Configuration can be adapted per environment

### 4. Maintainability
- Single Responsibility Principle: Each class has one reason to change
- Open/Closed Principle: Open for extension, closed for modification
- Dependency Inversion: Depend on abstractions, not concretions

## Running Tests

```bash
pytest tests/
```

## Examples

See the `examples/` directory for complete examples:

- `basic_example.py`: Simple coordinator-worker setup

## Configuration

Configure via environment variables:

- `GENUS_ENV`: Environment (development/production)
- `GENUS_LOG_LEVEL`: Logging level (DEBUG/INFO/WARNING/ERROR)
- `GENUS_MAX_QUEUE_SIZE`: Message queue size per agent

Or use a configuration file:

```python
from genus.config import Config

config = Config()
config.load_from_file("config.json")
```

## License

MIT

## Contributing

Contributions welcome! Please ensure:

1. All tests pass
2. Code follows existing style
3. New features include tests
4. Documentation is updated

## Future Enhancements

Potential areas for improvement:

- Add monitoring and metrics collection
- Implement agent discovery and registration
- Add support for persistent message queues
- Create web-based monitoring dashboard
- Add more sophisticated routing patterns
- Implement agent clustering and failover
