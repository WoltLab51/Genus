# Simple Pipeline Example

This example demonstrates a minimal working pipeline using the GENUS architecture.

## Overview

The pipeline consists of three agents that communicate via the MessageBus:

1. **DataCollectorAgent** - Generates and publishes mock sensor data
2. **AnalysisAgent** - Analyzes the collected data
3. **DecisionAgent** - Makes decisions based on the analysis

## Message Flow

```
DataCollector → [data.collected] → Analysis → [data.analyzed] → Decision → [decision.made]
```

### Message Types

- **data.collected** - Raw sensor data (temperature, humidity, pressure)
- **data.analyzed** - Analysis results with status classifications
- **decision.made** - Action decisions based on analysis

## Running the Pipeline

```bash
# Install the package
pip install -e .

# Run the pipeline
python examples/simple_pipeline.py
```

## Expected Output

The pipeline will:
1. Initialize all three agents
2. DataCollector publishes mock sensor data
3. AnalysisAgent receives and analyzes the data
4. DecisionAgent receives analysis and makes a decision
5. Display statistics showing:
   - Number of data points collected
   - Number of analyses performed
   - Number of decisions made
   - Message flow history

## Architecture Highlights

This example demonstrates:

- **Clean separation of concerns** - Each agent has a single responsibility
- **MessageBus communication** - Agents communicate only via the message bus
- **Lifecycle management** - Coordinated agent initialization and shutdown
- **Observable system** - Message history provides full traceability
- **Extensibility** - Easy to add new agents or message types

## Code Structure

```
genus/agents/
  ├── data_collector.py   # Collects and publishes data
  ├── analysis.py         # Analyzes collected data
  └── decision.py         # Makes decisions from analysis

examples/
  └── simple_pipeline.py  # Pipeline runner script
```

## Key Concepts

### Agent Lifecycle

1. **__init__** - Inject dependencies (MessageBus)
2. **initialize()** - Subscribe to topics
3. **start()** - Begin execution
4. **stop()** - Clean up and unsubscribe

### Message Publishing

```python
message = Message(
    topic="data.collected",
    payload={"temperature": 23.5},
    sender_id=self.id,
    priority=MessagePriority.NORMAL
)
await self._message_bus.publish(message)
```

### Topic Subscription

```python
self._message_bus.subscribe(
    "data.collected",
    self.id,
    self.process_message
)
```

## Extending the Pipeline

To add a new agent to the pipeline:

1. Create a new agent class inheriting from `Agent`
2. Implement required methods: `initialize()`, `start()`, `stop()`, `process_message()`
3. Subscribe to relevant topics in `initialize()`
4. Publish messages to communicate results
5. Register the agent with the Lifecycle manager

Example:

```python
class AlertAgent(Agent):
    async def initialize(self):
        self._message_bus.subscribe("decision.made", self.id, self.process_message)

    async def process_message(self, message: Message):
        # Handle decision and send alerts
        pass
```
