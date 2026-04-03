# GENUS

Self-aware agent orchestration system with built-in system state monitoring and health intelligence.

## Features

- **Event-Driven Architecture**: Decoupled agents communicate via publish-subscribe message bus
- **System Health Monitoring**: Real-time tracking of agent states, errors, and system health
- **Self-Awareness**: System monitors its own operational state (healthy/degraded/failing)
- **Modular Design**: Clean architecture with dependency injection
- **REST API**: FastAPI-based API with authentication and health endpoints
- **Comprehensive Testing**: Full unit and integration test coverage

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/WoltLab51/Genus.git
cd Genus

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and set your API_KEY
```

### Running the System

```bash
# Set API key
export API_KEY=your_secret_key_here

# Run the API server
uvicorn genus.api.app:create_app --factory --reload
```

### Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run only unit tests
python -m pytest tests/unit/ -v

# Run only integration tests
python -m pytest tests/integration/ -v
```

## API Endpoints

### Health Check (No Auth)
```bash
curl http://localhost:8000/health
```

### System Health (Auth Required)
```bash
curl -H "Authorization: Bearer your_api_key" \
  http://localhost:8000/system/health
```

Response includes:
- System state (healthy/degraded/failing)
- Agent statuses
- Recent errors
- Last successful runs
- Error counts
- Message bus statistics

### Ingest Data
```bash
curl -X POST \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"sensor": "temperature", "value": 25.5}' \
  http://localhost:8000/data/ingest
```

### List Decisions
```bash
curl -H "Authorization: Bearer your_api_key" \
  http://localhost:8000/decisions
```

### Submit Feedback
```bash
curl -X POST \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"decision_id": "dec-123", "rating": 5, "comment": "Great!"}' \
  http://localhost:8000/feedback
```

## Architecture

GENUS follows clean architecture principles with five core modules:

- **core/**: Agent base class, lifecycle, config, and system state tracking
- **communication/**: Message bus for publish-subscribe patterns
- **storage/**: In-memory stores for data, decisions, and feedback
- **agents/**: Agent implementations (DataCollector, Analysis, Decision)
- **api/**: FastAPI application with authentication and endpoints

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

## System State Monitoring

GENUS monitors its own health based on:
- Agent execution errors
- Missing or stale events
- Failed pipeline executions

**Health States**:
- **HEALTHY**: All systems operational
- **DEGRADED**: Some errors or stale agents detected
- **FAILING**: Critical errors or failed agents

## Agent Lifecycle

All agents follow a strict lifecycle:

1. `__init__` - Constructor with dependency injection
2. `initialize()` - Subscribe to message bus topics
3. `start()` - Begin processing messages
4. `stop()` - Unsubscribe and clean shutdown

## Configuration

Environment variables:
- `API_KEY` (required): API authentication key
- `DEBUG` (optional): Debug mode (default: false)
- `HOST` (optional): Server host (default: 0.0.0.0)
- `PORT` (optional): Server port (default: 8000)

## Development

### Project Structure
```
genus/
├── core/               # Core abstractions
├── communication/      # Message bus
├── storage/           # Data stores
├── agents/            # Agent implementations
└── api/               # REST API

tests/
├── unit/              # Unit tests
└── integration/       # Integration tests

docs/
└── ARCHITECTURE.md    # Detailed architecture docs
```

### Adding a New Agent

1. Extend the `Agent` base class
2. Implement `initialize()` and `stop()` methods
3. Subscribe to topics in `initialize()`
4. Handle messages with error tracking
5. Register in `api/app.py` lifespan

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed examples.

## Testing

GENUS includes comprehensive test coverage:
- Unit tests for all modules
- Integration tests for API and agent coordination
- pytest with async support

## License

MIT License

## Contributing

Contributions welcome! Please read the architecture documentation before submitting PRs.