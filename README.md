# GENUS

**Generative ENvironment for Unified Systems** — a modular multi-agent system
where independent AI agents collaborate via a publish-subscribe message bus.

## Quick Start

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
uvicorn genus.api.app:app --factory --reload
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

```
genus/
├── core/           # Agent ABC, AgentState, Lifecycle, Config
├── communication/  # Unified MessageBus (pub-sub + observability)
├── storage/        # MemoryStore (KV) + DecisionStore / FeedbackStore (DB)
├── agents/         # DataCollector, Analysis, Decision
└── api/            # FastAPI app factory + Pydantic schemas
```

## Migration

This branch unifies the best parts of three prior branches.
See [docs/MIGRATION.md](docs/MIGRATION.md) for what changed and why.
