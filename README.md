# GENUS

Generic Engineering System for Universal Solutions

## Overview

GENUS is a modular multi-agent system built with FastAPI that enables coordinated data collection, analysis, and decision-making through a clean architecture with message-based communication.

## Architecture

### Core Components

- **Core Module** (`genus/core/`): Base abstractions for agents, configuration, and lifecycle management
- **Communication** (`genus/communication/`): MessageBus for publish-subscribe agent communication
- **Storage** (`genus/storage/`): In-memory stores for memories, decisions, and feedback
- **Agents** (`genus/agents/`): Specialized agents for data collection, analysis, and decision-making
- **API** (`genus/api/`): FastAPI application with authentication and error handling

### Key Design Principles

1. **No Global Singletons**: All dependencies are injected via constructors
2. **Message-Based Communication**: Agents never communicate directly; all communication goes through MessageBus
3. **Strict Agent Lifecycle**: Agents follow IDLE → INITIALIZING → RUNNING → STOPPED lifecycle
4. **Clean Architecture**: Clear separation of concerns with dependency injection

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Required environment variables:

- `API_KEY`: API key for authentication (required)
- `LOG_LEVEL`: Logging level (default: INFO)
- `DEBUG`: Enable debug mode (default: false)
- `DATABASE_URL`: Database connection string (default: sqlite:///./genus.db)

## Running the System

### Start the API Server

```bash
export API_KEY=your-secret-key
python main.py
```

The API will be available at `http://localhost:8000`

### API Endpoints

#### Public Endpoints (No Authentication Required)

- `GET /` - Root endpoint with version info
- `GET /health` - Health check

#### Protected Endpoints (Require Authentication)

All other endpoints require the `Authorization: Bearer <api_key>` header.

- `POST /data/collect` - Submit data for collection and processing
- `GET /memory` - Retrieve stored memories
- `GET /decisions` - Retrieve agent decisions
- `GET /feedback` - Retrieve feedback entries
- `POST /feedback` - Submit feedback

### Example Usage

```bash
# Health check (no auth required)
curl http://localhost:8000/health

# Collect data (requires auth)
curl -X POST http://localhost:8000/data/collect \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"source": "sensor", "type": "observation", "value": 42}'

# Get memories
curl http://localhost:8000/memory?limit=10 \
  -H "Authorization: Bearer your-secret-key"

# Get decisions
curl http://localhost:8000/decisions?limit=10 \
  -H "Authorization: Bearer your-secret-key"
```

## Testing

Run the complete test suite:

```bash
export API_KEY=test-key
python -m pytest tests/ -v
```

The test suite includes:
- Unit tests for all core components
- Integration tests for the API
- End-to-end workflow tests

### Test Coverage

- 39 tests covering:
  - Configuration management
  - Agent lifecycle and communication
  - MessageBus publish-subscribe
  - Storage operations (Memory, Decision, Feedback)
  - API authentication and endpoints
  - Complete agent pipeline integration

## Development

### Project Structure

```
genus/
├── genus/
│   ├── core/          # Base classes and configuration
│   ├── communication/ # MessageBus implementation
│   ├── storage/       # Data stores
│   ├── agents/        # Agent implementations
│   └── api/           # FastAPI application
├── tests/
│   ├── unit/          # Unit tests
│   └── integration/   # Integration tests
├── main.py            # Application entry point
├── requirements.txt   # Python dependencies
└── pytest.ini         # Test configuration
```

### Agent Lifecycle

Agents follow a strict lifecycle:

1. **`__init__`**: Inject dependencies (MessageBus, stores)
2. **`initialize()`**: Subscribe to topics
3. **`start()`**: Transition to RUNNING state
4. **`stop()`**: Unsubscribe and transition to STOPPED

**Important**: Subscriptions must happen in `initialize()`, never in `__init__`.

### Adding New Agents

1. Inherit from `genus.core.agent.Agent`
2. Implement `initialize()`, `handle_message()`, and `stop()`
3. Subscribe to relevant topics in `initialize()`
4. Add agent to the application lifespan in `genus/api/app.py`

## Features

### Implemented

✅ Multi-agent architecture with lifecycle management
✅ Message-based agent communication
✅ In-memory storage for memories, decisions, and feedback
✅ RESTful API with authentication
✅ Comprehensive error handling and logging
✅ Full test coverage
✅ Timezone-aware timestamp handling

### System Capabilities

- **Data Collection**: Automated data ingestion and storage
- **Analysis**: Real-time analysis of collected data
- **Decision Making**: Automated decision-making based on analysis
- **Feedback Loop**: User and system feedback collection
- **Observability**: Message history tracking for debugging

## License

Copyright © 2026
