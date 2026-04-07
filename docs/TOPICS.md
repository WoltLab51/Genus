# GENUS – Topic-Registry

> **Stand:** 2026-04-07 | Sprache: Deutsch

---

## 1. Topic-Registry

Alle Topics, die im GENUS-MessageBus verwendet werden, sind hier dokumentiert. Jeder Eintrag definiert den Vertrag zwischen Producer und Consumer.

| Topic | Producer | Consumer(s) | Pflicht-Payload-Keys | `run_id` Pflicht? | Persistiert (Default)? |
|---|---|---|---|---|---|
| `data.collected` | `DataCollectorAgent` | `AnalysisAgent`, `DataSanitizerAgent` | `source`, `raw_data` oder spezifische Felder | ✅ Ja | ❌ Nein (siehe §3) |
| `analysis.completed` | `AnalysisAgent` | `QualityAgent` | `classification`, `confidence` | ✅ Ja | ✅ Ja (Whitelist) |
| `quality.scored` | `QualityAgent` | `DecisionAgent` | `quality_score`, `dimensions`, `evidence` | ✅ Ja | ✅ Ja (Whitelist) |
| `decision.made` | `DecisionAgent` | Downstream / API / Monitoring | `decision`, `reason`, `quality_score`, `min_quality`, `attempt`, `max_retries`, `critical` | ✅ Ja | ✅ Ja (Whitelist) |
| `outcome.recorded` | `OutcomeCLI` / Operator | `FeedbackAgent` (→ RunJournal), `EventRecorderAgent` (→ EventStore) | `outcome`, `score_delta`, `source` | ✅ Ja | ✅ Ja (Default-Whitelist) |
| `data.sanitized` | `DataSanitizerAgent` | `AnalysisAgent`, EventRecorder | `source`, `data`, `evidence` (inkl. `policy_id`, `policy_version`, `removed_fields`, `truncated_fields`, `blocked_by_policy`) | ✅ Ja | ⚙️ Opt-in (nicht in Default-Whitelist, siehe §2.1) |
| `data.analyzed` | `AnalysisAgent` (Legacy) | `QualityAgent` (Legacy-Alias) | `classification` | ✅ Ja | ❌ Nein (veraltet, ersetzt durch `analysis.completed`) |

---

## 2. Standard-Recorder-Whitelist (EventRecorderAgent)

Der `EventRecorderAgent` persistiert standardmäßig **nur** diese Topics:

```python
DEFAULT_RECORD_TOPICS = [
    "analysis.completed",   # Analyse-Ergebnis
    "quality.scored",       # Qualitätsbewertung
    "decision.made",        # Entscheidung + Begründung
    "outcome.recorded",     # Ergebnis-Feedback
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

### 2.1 `data.sanitized` – Opt-in Persistenz (P1-C2)

`data.sanitized` ist **persistierbar**, aber **nicht** in der Default-Whitelist, da
bereingte Daten je nach Policy noch sensible Felder enthalten können. Operatoren können
die Persistenz explizit aktivieren:

**Option A – Konstruktor-Argument:**

```python
from genus.agents.event_recorder_agent import DEFAULT_RECORD_TOPICS, EventRecorderAgent

recorder = EventRecorderAgent(
    message_bus=bus,
    event_store=store,
    record_topics=[*DEFAULT_RECORD_TOPICS, "data.sanitized"],
)
```

**Option B – Umgebungsvariable** (ohne Codeänderung):

```bash
GENUS_RECORD_TOPICS=analysis.completed,quality.scored,decision.made,outcome.recorded,data.sanitized
```

> **Hinweis:** Die Umgebungsvariable `GENUS_RECORD_TOPICS` wird nur ausgewertet, wenn
> `record_topics` **nicht** explizit übergeben wird. Explizite Argumente haben immer
> Vorrang. Enthält die Variable keine Einträge, greift wieder `DEFAULT_RECORD_TOPICS`.

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

### DataSanitizerAgent (P1-C1, implementiert)

Ein vorgeschalteter Agent bereinigt die Daten deterministisch:

```
data.collected  →  DataSanitizerAgent  →  data.sanitized
                       │
                       ├─ Whitelist-Felder: nur erlaubte Felder bleiben
                       ├─ Größenlimits: max_str_len, max_list_len, max_depth, max_keys_per_level
                       └─ Evidence: policy_id, policy_version, removed_fields, truncated_fields, blocked_by_policy
```

`data.sanitized` Payload-Schema:

```json
{
  "source":   "<string> aus payload['source'] / metadata['source'] / 'unknown'",
  "data":     {"<whitelisted strukturierte Keys>": "..."},
  "evidence": {
    "policy_id":         "default",
    "policy_version":    "p1-c1",
    "removed_fields":    ["<JSON-Pfad>", "..."],
    "truncated_fields":  ["<JSON-Pfad>", "..."],
    "blocked_by_policy": false,
    "run_id_missing":    true
  }
}
```

**Unbekannte Quellen:** Auch wenn `source` unbekannt ist oder alle Felder entfernt werden,
wird immer ein `data.sanitized` Event publiziert (kein Silent Drop). Bei vollständiger
Ablehnung ist `evidence["blocked_by_policy"] = true`.

Nach P1-C kann `data.sanitized` optional in die Recorder-Whitelist aufgenommen werden
(Default-Whitelist bleibt in diesem PR unverändert).

**Referenz:** `genus/agents/data_sanitizer_agent.py`, `genus/security/sanitization/sanitization_policy.py`

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

### `outcome.recorded` Payload
```python
{
    "outcome": "good",           # good | bad | unknown
    "score_delta": 1.0,          # float, clamped to [-10.0, 10.0]
    "source": "user",            # optional str, max 64 chars; default "user"
    # optional:
    "notes": "...",              # optional str, max 256 chars
    "timestamp": "2026-04-05T17:00:00+00:00"  # ISO-8601; set automatically by CLI
}
```

> `run_id` wird **ausschließlich** in `Message.metadata["run_id"]` geführt,
> nicht im Payload.

---

## 5. Fehlende `run_id`

Falls eine Nachricht ohne `run_id` im `EventRecorderAgent` ankommt:
- Das Event wird unter `run_id = "unknown"` gespeichert
- `metadata["run_id_missing"] = True` wird gesetzt
- Eine Warnung wird geloggt
- Die Datei `var/events/unknown.jsonl` wächst → Operator-Signal

Dies ist **kein Fehler**, aber ein wichtiger **Monitoring-Hinweis**. Ursachen suchen in: fehlende `attach_run_id()`-Aufrufe vor `publish()`.
