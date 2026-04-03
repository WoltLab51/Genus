# GENUS - Generic Agent System with Decision Feedback

GENUS is a modular agent-based system with built-in decision feedback capabilities, enabling agents to learn from their past decisions.

## Features

- **Agent-based Architecture**: Modular agents that communicate via MessageBus
- **Decision Tracking**: Store and retrieve agent decisions in PostgreSQL/SQLite
- **Feedback System**: Submit and track feedback on decisions (👍/👎 or custom scores)
- **Event-driven Observability**: EventBus for tracking all system events
- **RESTful API**: FastAPI-based endpoints for decision and feedback management
- **Interactive Dashboard**: Web UI for monitoring decisions and providing feedback

## Architecture

```
genus/
├── core/               # Base Agent and Message classes
├── communication/      # MessageBus and EventBus
├── storage/           # Database models and stores (MemoryStore, FeedbackStore)
├── agents/            # Sample agent implementations
├── api/               # FastAPI application and schemas
└── ui/                # Dashboard HTML
```

## Installation

```bash
# Clone the repository
git clone https://github.com/WoltLab51/Genus.git
cd Genus

# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

## Quick Start

### 1. Start the API Server

```bash
python -m uvicorn genus.api.app:app --reload
```

The API will be available at `http://localhost:8000`

### 2. Open the Dashboard

Open `genus/ui/dashboard.html` in your browser to view the dashboard.

### 3. Run Example

```python
import asyncio
from genus.communication import MessageBus, EventBus
from genus.storage import MemoryStore, FeedbackStore
from genus.agents import CoordinatorAgent, WorkerAgent

async def main():
    # Initialize components
    message_bus = MessageBus()
    event_bus = EventBus()
    memory_store = MemoryStore()
    feedback_store = FeedbackStore()

    await memory_store.init_db()
    await feedback_store.init_db()

    # Create agents
    coordinator = CoordinatorAgent("coordinator-1", message_bus, memory_store, event_bus)
    worker = WorkerAgent("worker-1", message_bus, memory_store, event_bus)

    # Start agents
    await coordinator.start()
    await worker.start()

    # Send a task request
    await coordinator.publish("task.request", {
        "task_data": {
            "type": "process",
            "input": "sample data"
        }
    })

    # Wait for processing
    await asyncio.sleep(1)

    # Cleanup
    await memory_store.close()
    await feedback_store.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## API Endpoints

### Decisions

- `POST /decisions` - Create a new decision
- `GET /decisions` - List all decisions (with filters)
- `GET /decisions/{id}` - Get a specific decision with feedback

### Feedback

- `POST /feedback` - Submit feedback for a decision
- `GET /feedback` - List all feedback (with filters)
- `GET /feedback/{id}` - Get specific feedback

### Events

- `GET /events` - Get recent system events

## Feedback System

The feedback system allows you to evaluate agent decisions:

### Score Range
- `-1.0` to `1.0` where:
  - `1.0` = Complete success
  - `0.0` = Neutral
  - `-1.0` = Complete failure

### Labels
- `success` - Decision worked well
- `neutral` - Decision was acceptable
- `failure` - Decision needs improvement

### Example: Submitting Feedback

```python
from genus.storage import FeedbackStore

feedback_store = FeedbackStore()
await feedback_store.init_db()

# Submit positive feedback
feedback_id = await feedback_store.store_feedback(
    decision_id="decision-123",
    score=1.0,
    label="success",
    notes="Great decision!",
    source="human_operator"
)
```

## Event Types

The EventBus emits the following events:

- `agent.started` - When an agent starts
- `decision.created` - When a decision is stored
- `decision.made` - When an agent makes a decision
- `decision.feedback` - When feedback is submitted
- `task.completed` - When a task completes

## Testing

Run the test suite:

```bash
# Run all tests
python -m pytest tests/ -v

# Run unit tests only
python -m pytest tests/unit/ -v

# Run integration tests only
python -m pytest tests/integration/ -v

# Run with coverage
python -m pytest tests/ --cov=genus --cov-report=html
```

## Development

### Creating a Custom Agent

```python
from genus.core import Agent, Message

class MyAgent(Agent):
    async def start(self):
        self.subscribe("my.topic")

    async def handle_message(self, message: Message):
        # Handle message
        data = message.payload

        # Store decision if needed
        if self.memory_store:
            await self.memory_store.store_decision(
                agent_id=self.agent_id,
                decision_type="my_decision",
                input_data=data,
                output_data={"result": "processed"}
            )
```

## Architecture Principles

1. **Decoupled Communication**: All agent communication goes through MessageBus
2. **Event-driven**: EventBus provides observability without coupling
3. **Clean Architecture**: Core abstractions are independent of implementation
4. **Modularity**: Each component can be used independently
5. **Async-first**: Built on asyncio for scalability

## Database

GENUS uses SQLAlchemy with async support:

- **Development**: SQLite (`sqlite+aiosqlite:///./genus.db`)
- **Production**: PostgreSQL recommended

### Schema

**Decisions Table**
- `id` - UUID primary key
- `agent_id` - Agent identifier
- `decision_type` - Type of decision
- `input_data` - JSON input
- `output_data` - JSON output
- `timestamp` - When decision was made
- `metadata` - Additional context

**Feedback Table**
- `id` - UUID primary key
- `decision_id` - Foreign key to decisions
- `score` - Float from -1 to 1
- `label` - success/failure/neutral
- `timestamp` - When feedback was given
- `notes` - Optional text
- `source` - Who/what provided feedback

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License