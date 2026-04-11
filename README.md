# GENUS

> *Ein digitales Wesen, das mit seiner Familie lebt, denkt, lernt und wächst.*

---

## Was ist GENUS?

GENUS ist kein Framework. GENUS ist kein Chatbot. GENUS ist ein **lebendes, lernendes System** —
ein persönlicher digitaler Assistent der sich selbst weiterentwickeln kann.

GENUS plant, baut und testet Code. GENUS recherchiert und erklärt.
GENUS erinnert sich, wächst und meldet sich proaktiv.
GENUS ist DnD-Meister, Projekt-Assistent, Familien-Gedächtnis.

**→ [Wer ist GENUS?](docs/GENUS_IDENTITY.md)**

---

## Architektur

GENUS besteht aus 8 Schichten:

```
┌─────────────────────────────────────────────────┐
│  Frontend / Chat-PWA  (Phase 18, geplant)       │
├─────────────────────────────────────────────────┤
│  API-Layer            FastAPI, WebSocket, Auth  │
├─────────────────────────────────────────────────┤
│  Funktions-Agenten    Conversation, Knowledge,  │
│                       Home, DnD, Familien       │
├─────────────────────────────────────────────────┤
│  DevLoop              Planner→Builder→Tester→   │
│                       Reviewer (LLM-gestützt)   │
├─────────────────────────────────────────────────┤
│  Growth-System        NeedObserver→Orchestrator │
│                       →Bootstrap (selbstlernend)│
├─────────────────────────────────────────────────┤
│  LLM-Schicht          Router, OpenAI, Ollama,   │
│                       CredentialStore, Scores   │
├─────────────────────────────────────────────────┤
│  Memory               EventStore, RunJournal,   │
│                       NeedStore, ToolMemory     │
├─────────────────────────────────────────────────┤
│  Core                 Agent ABC, MessageBus,    │
│                       Security, Sandbox         │
└─────────────────────────────────────────────────┘
```

**→ [Architektur-Übersicht](docs/ARCHITECTURE_OVERVIEW.md)**

---

## Schnellstart (Raspberry Pi)

```bash
# 1. Ollama installieren
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2

# 2. GENUS starten
pip install -r requirements.txt
uvicorn genus.api:create_app --factory --host 0.0.0.0 --port 8000
```

GENUS erkennt Ollama automatisch und startet im LLM-Modus.

**→ [Vollständige Installations-Anleitung](docs/OPERATIONS.md)**

---

## Status

| Schicht | Status |
|---|---|
| Core (MessageBus, Agent ABC, Sandbox, Security) | ✅ Produktionsreif |
| Memory (EventStore, RunJournal, NeedStore) | ✅ Produktionsreif |
| LLM-Schicht (Router, OpenAI, Ollama, Scores) | ✅ Produktionsreif |
| Growth-System (NeedObserver, Bootstrapper + Sandbox) | ✅ Produktionsreif |
| DevLoop (Planner, Builder, Reviewer mit LLM) | ✅ Produktionsreif |
| API (FastAPI, Auth, Middleware) | ✅ Produktionsreif |
| ConversationAgent / Chat | 🔜 Phase 13 |
| KnowledgeAgent / Recherche | 🔜 Phase 14 |
| Frontend / Chat-PWA | 🔜 Phase 18 |

**181 Tests, alle grün. Keine kritischen offenen Punkte.**

---

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [GENUS_IDENTITY.md](docs/GENUS_IDENTITY.md) | Wer ist GENUS? Persönlichkeit, Vision, Werte |
| [ROADMAP.md](docs/ROADMAP.md) | Vollständige Roadmap, alle Phasen, nächste Schritte |
| [ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md) | Modulgrenzen, Clean Architecture |
| [OPERATIONS.md](docs/OPERATIONS.md) | Installation, Konfiguration, Umgebungsvariablen |
| [SECURITY.md](docs/SECURITY.md) | Sicherheitsmodell, ACL, Kill-Switch |
| [DEV_LOOP.md](docs/DEV_LOOP.md) | DevLoop-Phasen, LLM-Integration |
| [TOPICS.md](docs/TOPICS.md) | Alle Message-Topics und Payload-Contracts |

---

## Tests

```bash
pytest tests/
```

181 Tests (104 Unit, 6 Integration + weitere). Test/Source-Ratio: 1,34:1.

---

## Lizenz

MIT
