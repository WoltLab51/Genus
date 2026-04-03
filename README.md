# GENUS - Multi-Agent System with Production Safeguards

GENUS is a production-ready multi-agent system with built-in authentication and comprehensive error handling.

## Features

### Production-Critical Safeguards

#### 1. API Key Authentication
- All API endpoints (except `/health`) require authentication
- Uses Bearer token authentication via `Authorization` header
- Detailed error messages for authentication failures

#### 2. Error Visibility
- Comprehensive error handling middleware
- Detailed error responses with context
- Debug mode for additional troubleshooting information
- Proper HTTP status codes for different error types

#### 3. Clean Architecture
- No global singletons
- Dependency injection via FastAPI lifespan context
- Strict agent lifecycle management
- Publish-subscribe communication pattern

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install development dependencies (for testing)
pip install -r requirements-dev.txt
```

### Configuration

Set the required environment variable:

```bash
export API_KEY="your-secret-api-key-here"
```

Optional environment variables:
- `ENVIRONMENT` - Deployment environment (default: "production")
- `DEBUG` - Enable debug mode (default: "false")
- `HOST` - Server host (default: "0.0.0.0")
- `PORT` - Server port (default: "8000")

### Running the Application

```bash
# Start the server
python main.py
```

Or with uvicorn directly:

```bash
uvicorn genus.api:create_app_with_auth --factory --host 0.0.0.0 --port 8000
```

## API Endpoints

### Public Endpoints

#### Health Check
```bash
GET /health
```

No authentication required. Returns service health status.

**Response:**
```json
{
  "status": "healthy",
  "service": "GENUS"
}
```

### Protected Endpoints

All protected endpoints require the `Authorization` header:

```bash
Authorization: Bearer <your-api-key>
```

#### Root / System Information
```bash
GET /
```

Returns system information and configuration.

**Response:**
```json
{
  "service": "GENUS",
  "version": "1.0.0",
  "environment": "production",
  "authentication": "API key required"
}
```

#### System Status
```bash
GET /status
```

Returns system status and message bus statistics.

**Response:**
```json
{
  "status": "running",
  "message_bus": {
    "total_messages": 0,
    "recent_messages": 0
  }
}
```

#### Message History
```bash
GET /messages?topic=<optional>&limit=<optional>
```

Returns message bus history for observability.

**Query Parameters:**
- `topic` (optional) - Filter by topic
- `limit` (optional) - Maximum messages to return (default: 100, max: 1000)

**Response:**
```json
{
  "total": 0,
  "messages": []
}
```

## Authentication

### Using curl

```bash
# Without authentication (will fail for protected endpoints)
curl http://localhost:8000/

# With authentication
curl -H "Authorization: Bearer your-api-key-here" http://localhost:8000/
```

### Authentication Errors

#### Missing API Key
```json
{
  "error": "Unauthorized",
  "message": "Invalid or missing API key. Please provide a valid API key in the Authorization header as 'Bearer <API_KEY>'.",
  "details": {
    "expected_header": "Authorization: Bearer <API_KEY>",
    "received_header": "None"
  }
}
```

#### Invalid API Key
```json
{
  "error": "Unauthorized",
  "message": "Invalid or missing API key. Please provide a valid API key in the Authorization header as 'Bearer <API_KEY>'.",
  "details": {
    "expected_header": "Authorization: Bearer <API_KEY>",
    "received_header": "Authorization: Bearer ***"
  }
}
```

## Error Handling

### Error Response Format

All errors follow a consistent format:

```json
{
  "error": "ErrorType",
  "message": "Human-readable error message",
  "path": "/endpoint/path",
  "method": "GET"
}
```

### Debug Mode

When `DEBUG=true`, error responses include additional details:

```json
{
  "error": "ErrorType",
  "message": "Human-readable error message",
  "path": "/endpoint/path",
  "method": "GET",
  "details": {
    "traceback": [...],
    "exception_module": "module.name"
  }
}
```

## Architecture

### Core Components

1. **Config** (`genus/core/config.py`)
   - Environment variable management
   - API key validation
   - Configuration validation

2. **Agent** (`genus/core/agent.py`)
   - Abstract base class for all agents
   - Strict lifecycle management (CREATED → INITIALIZED → RUNNING → STOPPED)
   - State tracking

3. **MessageBus** (`genus/communication/message_bus.py`)
   - Publish-subscribe communication
   - Message history for observability
   - No direct agent-to-agent communication

4. **Authentication Middleware** (`genus/api/middleware.py`)
   - Bearer token validation
   - Detailed error messages
   - Health check exemption

5. **Error Handling Middleware** (`genus/api/errors.py`)
   - Comprehensive error catching
   - Detailed error responses
   - Debug mode support

### Dependency Injection

No global singletons. All dependencies are:
1. Created in FastAPI lifespan context
2. Stored in `app.state`
3. Injected into agents via constructors
4. Accessible in endpoints via `request.app.state`

## Testing

Run the test suite:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/unit/ -v
python -m pytest tests/integration/ -v

# Run with coverage
python -m pytest tests/ -v --cov=genus --cov-report=html
```

## Development

### Project Structure

```
genus/
├── core/              # Core abstractions (Agent, Config)
├── communication/     # MessageBus for agent communication
├── storage/          # Data persistence (future)
├── agents/           # Agent implementations (future)
└── api/              # FastAPI application and middleware

tests/
├── unit/             # Unit tests
└── integration/      # Integration tests
```

### Adding New Agents

1. Inherit from `Agent` base class
2. Implement `initialize()` and `_cleanup()` methods
3. Subscribe to topics in `initialize()` (never in `__init__`)
4. Follow lifecycle: __init__ → initialize() → start() → stop()

### Message Bus Usage

```python
# Publishing messages
await message_bus.publish("topic.name", {"data": "value"}, sender="agent-id")

# Subscribing to topics
async def handler(message: Message):
    print(f"Received: {message.data}")

message_bus.subscribe("topic.name", handler)

# Unsubscribing
message_bus.unsubscribe("topic.name", handler)
```

## Security Considerations

1. **API Key Storage**: Store API keys securely (environment variables, secrets manager)
2. **Key Rotation**: Change API keys regularly
3. **HTTPS**: Always use HTTPS in production
4. **Debug Mode**: Never enable debug mode in production
5. **Error Messages**: Debug mode exposes stack traces - only use in development

## Deployment

### Using Docker (Example)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY genus/ ./genus/
COPY main.py .

ENV API_KEY=""
ENV ENVIRONMENT="production"
ENV DEBUG="false"

CMD ["python", "main.py"]
```

### Environment Variables in Production

Use a secure secrets management solution:
- AWS Secrets Manager
- Azure Key Vault
- HashiCorp Vault
- Kubernetes Secrets

Never commit API keys to source control.

## License

[Your License Here]
