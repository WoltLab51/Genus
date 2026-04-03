# GENUS — Modular AI Multi-Agent System

## Overview

GENUS is a modular, event-driven AI system built with a multi-agent architecture. Three autonomous agents — Data Collector, Analysis, and Decision — communicate via an async event bus, enabling a fully reactive pipeline from raw data ingestion to actionable decisions.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                     GENUS Backend                     │
│                                                      │
│  ┌──────────────┐    event     ┌──────────────────┐  │
│  │ DataCollector│─────bus─────▶│  AnalysisAgent   │  │
│  │    Agent     │              └────────┬─────────┘  │
│  └──────────────┘                       │ event bus  │
│                                         ▼            │
│                               ┌──────────────────┐   │
│                               │  DecisionAgent   │   │
│                               └──────────────────┘   │
│                                                      │
│  Core: MemoryStore · EventBus · Logger · Database    │
└──────────────────────────────────────────────────────┘
         ▲ REST API (FastAPI)
         │
┌────────┴───────┐
│  Next.js 14    │  ← Dashboard (real-time polling)
│  Frontend      │
└────────────────┘
```

## Modules

| Module | Description |
|---|---|
| `core/logger.py` | Centralized `GenusLogger` wrapping Python's `logging` |
| `core/memory.py` | In-memory namespaced key-value store with history |
| `core/messaging.py` | Async `EventBus` for inter-agent pub/sub communication |
| `core/database.py` | SQLAlchemy async engine + session factory |
| `agents/base_agent.py` | Abstract `BaseAgent` with lifecycle management |
| `agents/data_collector/` | Fetches/mocks external data, publishes `data.collected` |
| `agents/analysis/` | Processes data items, publishes `data.analyzed` |
| `agents/decision/` | Produces recommendations from analysis, publishes `decision.made` |
| `models/schemas.py` | Pydantic schemas for all data contracts |
| `frontend/` | Next.js 14 dashboard with Tailwind CSS |

## Tech Stack

**Backend**
- Python 3.12, FastAPI 0.111, Uvicorn
- SQLAlchemy 2 (async) + asyncpg + PostgreSQL 15
- Pydantic v2, httpx, pytest + pytest-asyncio

**Frontend**
- Next.js 14 (App Router), React 18, TypeScript 5
- Tailwind CSS 3

**Infrastructure**
- Docker + Docker Compose

## Getting Started

### With Docker Compose (recommended)

```bash
docker compose up --build
```

- Backend API: http://localhost:8000
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

### Local Development

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Run tests:**
```bash
cd backend
pytest tests/ -v
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | System info |
| GET | `/health` | Health check |
| GET | `/system/status` | All agent statuses |
| GET | `/system/events` | Recent event log |
| GET | `/system/memory` | Memory store contents |
| POST | `/system/pipeline/run` | Trigger full pipeline |
| GET | `/agents/data-collector/status` | DataCollector status |
| POST | `/agents/data-collector/run` | Run DataCollector |
| GET | `/agents/data-collector/data` | Collected data |
| GET | `/agents/analysis/status` | Analysis agent status |
| POST | `/agents/analysis/run` | Run Analysis agent |
| GET | `/agents/analysis/results` | Analysis results |
| GET | `/agents/decision/status` | Decision agent status |
| POST | `/agents/decision/run` | Run Decision agent |
| GET | `/agents/decision/decisions` | Decision history |