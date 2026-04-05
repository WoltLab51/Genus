# GENUS – Topic-Registry

> **Stand:** 2026-04-05 | Sprache: Deutsch

---

## 1. Topic-Registry

Alle Topics, die im GENUS-MessageBus verwendet werden, sind hier dokumentiert. Jeder Eintrag definiert den Vertrag zwischen Producer und Consumer.

| Topic | Producer | Consumer(s) | Pflicht-Payload-Keys | `run_id` Pflicht? | Persistiert (Default)? |
|---|---|---|---|---|---|
| `data.collected` | `DataCollectorAgent` | `AnalysisAgent`, `DataSanitizerAgent` (geplant) | `source`, `raw_data` oder spezifische Felder | ✅ Ja | ❌ Nein (siehe §3) |
| `analysis.completed` | `AnalysisAgent` | `QualityAgent` | `classification`, `confidence` | ✅ Ja | ✅ Ja (Whitelist) |
| `quality.scored` | `QualityAgent` | `DecisionAgent` | `quality_score`, `dimensions`, `evidence` | ✅ Ja | ✅ Ja (Whitelist) |
| `decision.made` | `DecisionAgent` | Downstream / API / Monitoring | `decision`, `reason`, `quality_score`, `min_quality`, `attempt`, `max_retries`, `critical` | ✅ Ja | ✅ Ja (Whitelist) |
| `outcome.recorded` | *Geplant* | `DecisionAgent` (Feedback-Loop) | `outcome`, `run_id`, `score_delta` | ✅ Ja | ✅ Ja (Whitelist) – *wenn vorhanden* |
| `data.sanitized` | `DataSanitizerAgent` (geplant) | `AnalysisAgent`, EventRecorder | `sanitized_fields`, `redaction_applied`, `pii_detected`, `removed_fields` | ✅ Ja | ✅ Ja (nach P1-C) |
| `data.analyzed` | `AnalysisAgent` (Legacy) | `QualityAgent` (Legacy-Alias) | `classification` | ✅ Ja | ❌ Nein (veraltet, ersetzt durch `analysis.completed`) |

---

## 2. Standard-Recorder-Whitelist (EventRecorderAgent)

Der `EventRecorderAgent` persistiert standardmäßig **nur** diese Topics:

```python
DEFAULT_RECORD_TOPICS = [
    "analysis.completed",   # Analyse-Ergebnis
    "quality.scored",       # Qualitätsbewertung
    "decision.made",        # Entscheidung + Begründung
    "outcome.recorded",     # (optional) Ergebnis-Feedback (sobald vorhanden)
]
```

**Konfigurierbar:** Die Whitelist kann bei der Instanziierung überschrieben werden:

```python
recorder = EventRecorderAgent(
    message_bus=bus,
    event_store=store,
    record_topics=["analysis.completed", "quality.scored", "decision.made"]
)
```

---

## 3. `data.collected` wird nicht persistiert – Begründung

`data.collected` enthält Rohdaten und ist aus folgenden Gründen **explizit nicht** in der Standard-Whitelist:

| Grund | Erklärung |
|---|---|
| **Datenschutz / PII** | Rohdaten können personenbezogene Informationen (Adressen, Tokens, Familieninfos) enthalten |
| **Sensitivität** | Mögliche Secrets/Credentials in Rohdaten |
| **Größe** | Rohdaten-Payloads können groß und unhandlich sein |
| **Intentionskonformität** | GENUS braucht auditierbare *Signale*, nicht rohe Inputs |
| **Sicherheitsrisiko** | Path-Traversal- oder Injection-Angriffe über Payload-Inhalte |

### Geplante Lösung: DataSanitizerAgent (P1-C)

Statt `data.collected` direkt zu persistieren, wird ein vorgeschalteter Agent die Daten bereinigen:

```
data.collected  →  DataSanitizerAgent  →  data.sanitized
                       │
                       ├─ Whitelist-Felder: nur erlaubte Felder bleiben
                       ├─ Redaction: PII-Patterns entfernen
                       └─ Evidence: redaction_applied, removed_fields, pii_detected
```

Nach P1-C kann `data.sanitized` optional in die Recorder-Whitelist aufgenommen werden.

**Referenz:** `genus/agents/data_collector_agent.py`, geplant: `genus/agents/data_sanitizer_agent.py`

---

## 4. Payload-Konventionen

### Alle Topics: Pflichtfelder in `Message.metadata`

```python
{
    "run_id": "2026-04-05T15-30-00__analyze__abc123"  # Immer Pflicht
}
```

### `analysis.completed` Payload
```python
{
    "classification": "high" | "normal" | "low",
    "confidence": 0.87,          # float [0.0, 1.0]
    # optional:
    "quality_score": 0.87,       # direkte Weitergabe an QualityAgent
    "score": 87,                 # Alternative (wird normalisiert)
    "features": {...}            # beliebige weitere Signale
}
```

### `quality.scored` Payload
```python
{
    "quality_score": 0.87,       # float [0.0, 1.0] oder None
    "dimensions": {
        "completeness": 0.9,
        "accuracy": 0.85
    },
    "evidence": [
        {"source": "confidence", "note": "Wert aus analysis.completed.confidence"}
    ]
}
```

### `decision.made` Payload
```python
{
    "decision": "accept",        # accept | retry | replan | escalate | delegate
    "reason": "quality_score >= min_quality",
    "quality_score": 0.87,
    "min_quality": 0.8,
    "attempt": 1,
    "max_retries": 3,
    "critical": false
}
```

---

## 5. Fehlende `run_id`

Falls eine Nachricht ohne `run_id` im `EventRecorderAgent` ankommt:
- Das Event wird unter `run_id = "unknown"` gespeichert
- `metadata["run_id_missing"] = True` wird gesetzt
- Eine Warnung wird geloggt
- Die Datei `var/events/unknown.jsonl` wächst → Operator-Signal

Dies ist **kein Fehler**, aber ein wichtiger **Monitoring-Hinweis**. Ursachen suchen in: fehlende `attach_run_id()`-Aufrufe vor `publish()`.
