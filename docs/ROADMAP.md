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
| **API-Layer (FastAPI)** | REST-Endpunkte, Auth-Middleware, Fehlerbehandlung | 🔜 Geplant | – (kein `genus/api/`-Modul vorhanden) |
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

### ✅ Done

- **P0** (#5) – Core-Infrastruktur: Agent ABC, MessageBus, Lifecycle, Config, erste Agenten
- **P1-A** (#6) – Decision Policy 2.0: accept/retry/replan/escalate/delegate, QualityScorecard, QualityAgent
- **P1-B** (#7) – Memory 2.0: JSONL EventStore, EventEnvelope, EventRecorderAgent, Topic-Whitelist
- **Docs** (#8) – Deutsche Dokumentation: Roter Faden, Topics, Policies, Security, Operations

### ⏳ Next

- **P1-C** – DataSanitizerAgent (Whitelist-Felder, Redaction) + neues Topic `data.sanitized`
- `outcome.recorded` Feedback-Loop (**Contract + Persistenz ✅ ready**, **Producer/Publisher 🔜 geplant**):
  - ✅ Topic-Contract definiert (`docs/TOPICS.md`)
  - ✅ `EventRecorderAgent` persistiert `outcome.recorded` (Default-Whitelist + Tests vorhanden)
  - 🔜 Offen: Producer/Publisher (wer publiziert Outcome-Events) + Calibration/Policy-Nutzung
- Permissions/Rollen/Kill-Switch (P2)
- Orchestrator / Builder / Sandbox (P3)

### 🔒 Security-Gates

- `data.collected` **nicht persistieren** – erst wenn `DataSanitizerAgent` (P1-C) existiert und `data.sanitized` erzeugt
- Recorder ist **Whitelist-only** – neue Topics müssen explizit freigeschaltet werden
- `run_id` ist **Pflichtfeld** in jeder Nachricht – kein Silent Drop
- Ein Meilenstein gilt erst als ✅ Done, wenn Tests + Dokumentation + Topic-Registry aktualisiert sind

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

---

## 7. Glossar

| Begriff | Definition |
|---|---|
| **run_id** | Eindeutige Kennung eines GENUS-Runs. Format: `<timestamp>__<slug>__<suffix>` (z. B. `2026-04-05T15-30-00__analyze__abc123`). Pflichtfeld in jedem `Message.metadata`. Wird als Dateiname für den EventStore verwendet (nach Sanitierung). |
| **Message** | Einheitliches Kommunikationsobjekt im MessageBus. Felder: `topic`, `payload`, `metadata` (enthält mindestens `run_id`), `sender_id`, `priority`. |
| **payload** | Fachlicher Inhalt einer Nachricht (dict). Struktur ist topic-spezifisch und in `docs/TOPICS.md` dokumentiert. |
| **metadata** | Technische Metadaten einer Nachricht (dict). Enthält immer `run_id`; kann weitere Felder wie `timestamp` oder `attempt` enthalten. |
| **topic** | Benannter Kanal im MessageBus (z. B. `analysis.completed`). Namenskonvention: `<domäne>.<ereignis>` (Kleinbuchstaben, Punkte als Trenner). Alle aktiven Topics sind in `docs/TOPICS.md` registriert. |
| **EventEnvelope** | Persistiertes Objekt im JSONL EventStore. Felder: `timestamp`, `run_id`, `topic`, `sender_id`, `payload`, `metadata`. Wird von `EventRecorderAgent` erzeugt. |
| **EventStore (JSONL)** | Append-only Persistenzschicht. Speichert Events als JSON-Zeilen in `<GENUS_EVENTSTORE_DIR>/<run_id>.jsonl`. Eine Datei pro run_id. Keine Mutation bestehender Einträge. |
| **Recorder-Whitelist** | Liste der Topics, die der `EventRecorderAgent` persistiert. Standard: `analysis.completed`, `quality.scored`, `decision.made`. `data.collected` ist bewusst **nicht** enthalten. |
| **quality_score** | Numerischer Gesamtwert der Qualitätsbewertung (0.0–1.0). Wird von `QualityAgent` berechnet und in `QualityScorecard.overall` gespeichert. |
| **QualityScorecard** | Strukturiertes Bewertungsobjekt (`genus/quality/scorecard.py`). Felder: `overall` (float), `dimensions` (dict), `evidence` (list). Wird im Payload von `quality.scored` übertragen. |
| **Decision-Semantik** | Mögliche Entscheidungen des `DecisionAgent`: `accept` (Qualität ausreichend), `retry` (Qualität knapp unter Schwelle, Wiederholung sinnvoll), `replan` (Qualität zu niedrig, neuer Plan nötig), `escalate` (kritischer Fall, manuelles Eingreifen), `delegate` (an anderen Agenten übergeben). |
| **Critical Gate** | Regel: Wenn `risk=high` oder `critical=True` im Payload und keine expliziten `requirements` definiert sind, erzwingt `DecisionAgent` die Entscheidung `escalate`. Verhindert automatische Akzeptanz bei risikobehafteten Fällen. |
| **requirements / min_quality** | Konfigurierbare Qualitätsschwelle (Standard: `0.8`). `DecisionAgent` vergleicht `quality_score >= min_quality` für die `accept`-Entscheidung. Kann per Payload oder Konfiguration überschrieben werden. |
| **Sanitizer (geplant)** | `DataSanitizerAgent` (P1-C): Empfängt `data.collected`, entfernt PII/Secrets per Whitelist-Felder und Regex-Redaction, publiziert bereinigtes `data.sanitized`. Erst danach darf `data.sanitized` in den EventStore aufgenommen werden. |

---

## 8. Anti-Patterns (No-Gos)

| Anti-Pattern | Warum verboten |
|---|---|
| **Silent Drop bei fehlender run_id** | Nachrichten ohne `run_id` einfach ignorieren verhindert Debugging und Audit-Nachvollziehbarkeit. Korrekt: unter `"unknown"` speichern **und** Warnung loggen. |
| **Rohdaten persistieren ohne Sanitizer** | `data.collected` direkt in den EventStore schreiben riskiert PII/Secrets in Audit-Logs. Erst nach `DataSanitizerAgent` (P1-C) darf `data.sanitized` persistiert werden. |
| **God-Agent / God-Tool** | Ein Agent, der Orchestrierung, Business Logic und I/O gleichzeitig übernimmt, ist untestbar, unsicher und verletzt das Single-Responsibility-Prinzip. |
| **Topic-Sprawl ohne Registry** | Neue Topics einführen, ohne sie in `docs/TOPICS.md` zu registrieren, führt zu Inkonsistenzen, fehlender Dokumentation und unklaren Persistenz-Regeln. |
| **Pfad-Injection via run_id** | `run_id` ungefiltert als Dateinamen verwenden ermöglicht Path Traversal (`../../../etc/passwd`). Immer `sanitize_run_id()` aus `genus/memory/jsonl_event_store.py` verwenden. |
| **Entscheidung ohne Evidence/Reason** | `decision.made` ohne `reason` und `evidence` im Payload ist nicht auditierbar. Jede Entscheidung muss nachvollziehbar begründet sein. |
