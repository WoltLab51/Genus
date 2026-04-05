# GENUS – Roter Faden (Einstiegspunkt)

> **Sprache:** Deutsch  
> **Stand:** 2026-04-05  
> **Version:** GENUS-2.0

---

## 1. Was ist GENUS?

**GENUS** (Generative ENvironment for Unified Systems) ist ein modulares, agenten-basiertes Framework für mehrstufige KI-Pipelines. Es stellt sicher, dass Entscheidungen **nachvollziehbar, auditierbar und kontrollierbar** bleiben.

### Ziele
- Klare Trennung von Analyse, Qualitätsbewertung und Entscheidungslogik
- Vollständige Nachvollziehbarkeit jedes Runs via `run_id` + EventStore
- Sichere Persistenz ohne Rohdaten (Whitelist-Recorder + geplanter Sanitizer)
- Erweiterbarkeit durch saubere Modulgrenzen (Clean Architecture)

### Nicht-Ziele
- Kein allgemeiner ML-Trainingsrahmen
- Kein direkter Datenbankersatz (EventStore ist Audit-Log, kein Query-Store)
- Keine proprietäre Plattformbindung

---

## 2. GENUS-2.0 Bausteine

| Baustein | Beschreibung | Status | Ort im Repo |
|---|---|---|---|
| **MessageBus** | Pub-Sub-Kommunikation, Entkopplung aller Agenten | ✅ Implementiert | `genus/communication/message_bus.py` |
| **Agent ABC** | Abstrakte Basisklasse, Lifecycle (init/start/stop) | ✅ Implementiert | `genus/core/agent.py` |
| **run_id / RunContext** | Eindeutige Run-Kennung, Propagation via Message.metadata | ✅ Implementiert | `genus/core/run.py` |
| **DataCollectorAgent** | Sammelt Rohdaten, publiziert `data.collected` | ✅ Implementiert | `genus/agents/data_collector_agent.py` |
| **AnalysisAgent** | Analysiert Rohdaten, publiziert `analysis.completed` | ✅ Implementiert | `genus/agents/analysis_agent.py` |
| **QualityAgent** | Bewertet Analyse, publiziert `quality.scored` | ✅ Implementiert | `genus/agents/quality_agent.py` |
| **DecisionAgent** | Entscheidet (accept/retry/replan/escalate/delegate) | ✅ Implementiert | `genus/agents/decision_agent.py` |
| **EventStore / JSONL** | Append-only Persistenz pro run_id | ✅ Implementiert | `genus/memory/` |
| **EventRecorderAgent** | Subscribt auf Whitelist-Topics, schreibt in EventStore | ✅ Implementiert | `genus/agents/event_recorder_agent.py` |
| **QualityScorecard** | Strukturiertes Bewertungsobjekt | ✅ Implementiert | `genus/quality/scorecard.py` |
| **API-Layer (FastAPI)** | REST-Endpunkte, Auth-Middleware, Fehlerbehandlung | ✅ Implementiert | `genus/api/` |
| **DataSanitizerAgent** | Bereinigt Rohdaten vor Persistenz (Whitelist-Felder) | 🔜 Geplant (P1-C) | – |
| **Orchestrator** | Koordiniert Agenten-Workflows, Fehler-Recovery | 🔜 Geplant | – |
| **Builder** | Erstellt/konfiguriert Agenten dynamisch | 🔜 Geplant | – |
| **Sandbox** | Isolierte Ausführungsumgebung für unsichere Operationen | 🔜 Geplant | – |
| **Permissions / Rollen** | Fein-granulare Zugriffskontrolle | 🔜 Geplant | – |
| **Kill-Switch** | Notfall-Stop für laufende Runs | 🔜 Geplant | – |

---

## 3. Ist-Architektur (heute)

```
┌─────────────────────────────────────────────────────────┐
│                      GENUS Run                          │
│                                                         │
│  DataCollector ──► [data.collected] ──► AnalysisAgent  │
│                                              │          │
│                                    [analysis.completed] │
│                                              │          │
│                                         QualityAgent   │
│                                              │          │
│                                     [quality.scored]   │
│                                              │          │
│                                        DecisionAgent   │
│                                              │          │
│                                      [decision.made]   │
│                                              │          │
│  EventRecorderAgent ◄──────────────── MessageBus       │
│        │                                               │
│        ▼                                               │
│  var/events/<run_id>.jsonl                             │
└─────────────────────────────────────────────────────────┘
```

**Invarianten (dürfen nie gebrochen werden):**
- `run_id` ist in jedem Message.metadata Pflicht
- Recorder schreibt nur Topics aus der Whitelist (keine Rohdaten)
- EventStore ist append-only (keine Mutation bestehender Einträge)
- Agenten kommunizieren **ausschließlich** über den MessageBus

---

## 4. End-to-End Beispiel

### Szenario: Datenanalyse mit Qualitätsbewertung

**run_id:** `2026-04-05T15-30-00__analyze__abc123`

#### Schritt 1 – Analyse abgeschlossen
```jsonl
{
  "timestamp": "2026-04-05T15:30:01Z",
  "run_id": "2026-04-05T15-30-00__analyze__abc123",
  "topic": "analysis.completed",
  "sender_id": "AnalysisAgent-1",
  "payload": {
    "classification": "high",
    "confidence": 0.87,
    "features": {"temperature": 31, "anomaly_score": 0.12}
  },
  "metadata": {"run_id": "2026-04-05T15-30-00__analyze__abc123"}
}
```

#### Schritt 2 – Qualität bewertet
```jsonl
{
  "timestamp": "2026-04-05T15:30:02Z",
  "run_id": "2026-04-05T15-30-00__analyze__abc123",
  "topic": "quality.scored",
  "sender_id": "QualityAgent-1",
  "payload": {
    "quality_score": 0.87,
    "dimensions": {"completeness": 0.9, "accuracy": 0.85},
    "evidence": [{"source": "confidence", "note": "Wert aus analysis.completed.confidence"}]
  },
  "metadata": {"run_id": "2026-04-05T15-30-00__analyze__abc123"}
}
```

#### Schritt 3 – Entscheidung getroffen
```jsonl
{
  "timestamp": "2026-04-05T15:30:03Z",
  "run_id": "2026-04-05T15-30-00__analyze__abc123",
  "topic": "decision.made",
  "sender_id": "DecisionAgent-1",
  "payload": {
    "decision": "accept",
    "reason": "quality_score >= min_quality",
    "quality_score": 0.87,
    "min_quality": 0.8,
    "attempt": 1,
    "max_retries": 3,
    "critical": false
  },
  "metadata": {"run_id": "2026-04-05T15-30-00__analyze__abc123"}
}
```

Alle drei Zeilen landen in **`var/events/2026-04-05T15-30-00__analyze__abc123.jsonl`**.

---

## 5. Meilensteine

| Milestone | Status | PRs | Inhalt |
|---|---|---|---|
| **P0** | ✅ Done | #5 | Core-Infrastruktur: Agent ABC, MessageBus, Lifecycle, Config, erste Agenten |
| **P1-A** | ✅ Done | #6 | Decision Policy 2.0: accept/retry/replan/escalate/delegate, QualityScorecard, QualityAgent |
| **P1-B** | ✅ Done | #7 | Memory 2.0: JSONL EventStore, EventEnvelope, EventRecorderAgent, Topic-Whitelist |
| **P1-C** | 🔜 Geplant | – | DataSanitizerAgent (Whitelist-Felder, Redaction, `data.sanitized` Topic) |
| **P2** | 🔜 Geplant | – | `outcome.recorded`, Lernen/Calibration, Permissions/Rollen, Kill-Switch |
| **P3** | 🔜 Geplant | – | Orchestrator, Builder, Sandbox, verteilter MessageBus |

---

## 6. Weiterführende Dokumentation

| Dokument | Inhalt |
|---|---|
| [`docs/ARCHITECTURE_OVERVIEW.md`](./ARCHITECTURE_OVERVIEW.md) | Modulgrenzen, Dependency-Richtung, Agent-Lifecycle |
| [`docs/TOPICS.md`](./TOPICS.md) | Topic-Registry, Payload-Contracts, Recorder-Whitelist |
| [`docs/POLICIES.md`](./POLICIES.md) | Decision-Semantik, min_quality, Critical Gate, QM-preferred |
| [`docs/SECURITY.md`](./SECURITY.md) | Sicherheitsposture, Threat Model, geplante Maßnahmen |
| [`docs/OPERATIONS.md`](./OPERATIONS.md) | Konfiguration, EventStore-Pfad, Debugging-Checkliste |
| [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md) | Technische Architektur-Referenz (Englisch) |
