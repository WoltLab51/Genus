# Simple Pipeline Example

This example demonstrates a minimal working pipeline using the GENUS architecture with a feedback loop.

## Overview

The pipeline consists of four agents that communicate via the MessageBus:

1. **DataCollectorAgent** - Generates and publishes mock sensor data
2. **AnalysisAgent** - Analyzes the collected data
3. **DecisionAgent** - Makes decisions based on the analysis and tracks feedback
4. **FeedbackAgent** - Simulates feedback for decisions (success/failure)

## Message Flow

```
DataCollector → [data.collected] → Analysis → [data.analyzed] → Decision → [decision.made]
                                                                      ↓
                                            Feedback ← [decision.feedback]
```

### Message Types

- **data.collected** - Raw sensor data (temperature, humidity, pressure)
- **data.analyzed** - Analysis results with status classifications
- **decision.made** - Action decisions based on analysis (includes decision_id)
- **decision.feedback** - Feedback on decision outcomes (success/failure)

## Running the Pipeline

```bash
# Install the package
pip install -e .

# Run the pipeline
python examples/simple_pipeline.py
```

## Expected Output

The pipeline will:
1. Initialize all four agents
2. DataCollector publishes mock sensor data
3. AnalysisAgent receives and analyzes the data
4. DecisionAgent receives analysis and makes a decision
5. FeedbackAgent simulates feedback for the decision
6. DecisionAgent receives and logs the feedback
7. Display statistics showing:
   - Number of data points collected
   - Number of analyses performed
   - Number of decisions made
   - Number of feedback messages received
   - Message flow history
   - Decisions with their feedback outcomes

## Architecture Highlights

This example demonstrates:

- **Clean separation of concerns** - Each agent has a single responsibility
- **MessageBus communication** - Agents communicate only via the message bus
- **Lifecycle management** - Coordinated agent initialization and shutdown
- **Observable system** - Message history provides full traceability
- **Feedback loop** - Decisions are tracked and linked to feedback
- **Extensibility** - Easy to add new agents or message types

## Code Structure

```
genus/agents/
  ├── data_collector.py   # Collects and publishes data
  ├── analysis.py         # Analyzes collected data
  ├── decision.py         # Makes decisions from analysis, tracks feedback
  └── feedback.py         # Simulates feedback for decisions

examples/
  └── simple_pipeline.py  # Pipeline runner script
```

## Feedback Loop

The feedback loop demonstrates adaptive decision-making through learning:

1. **Decision Tracking**: Each decision gets a unique ID and is stored in memory
2. **Feedback Simulation**: FeedbackAgent simulates outcomes (success/failure) based on:
   - Random probability (70% success rate by default)
   - Action type (e.g., "maintain_current_settings" has 90% success)
3. **Feedback Storage**: DecisionAgent links feedback to decisions using decision_id
4. **Success Rate Tracking**: Statistics are maintained for each action type:
   - Number of successes
   - Number of failures
   - Overall success rate
5. **Adaptive Decision-Making**: DecisionAgent adjusts its behavior based on feedback:
   - When multiple actions are viable, it selects the one with the highest success rate
   - Actions with poor feedback history are avoided
   - Logs show when decisions are "influenced by feedback"
6. **Observability**: Decisions, feedback, and success rates are available for inspection

### Adaptive Behavior Example

```
Iteration 1: No feedback history → Uses default logic
Iteration 2: Has feedback → "Decision influenced by feedback: selected 'maintain_current_settings' (rates: maintain_current_settings=100.00%)"
Iteration 3+: Continues to adapt based on accumulating feedback
```

### Running the Adaptive Pipeline

To see the adaptive behavior over multiple iterations:

```bash
python examples/adaptive_pipeline.py
```

This will run 5 iterations and show how the DecisionAgent learns to prefer actions with higher success rates.

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
