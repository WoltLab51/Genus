# GENUS – Betrieb & Debugging

> **Stand:** 2026-04-05 | Sprache: Deutsch

---

## 1. Konfiguration

### Umgebungsvariablen

| Variable | Default | Beschreibung |
|---|---|---|
| `API_KEY` | – (Pflicht) | API-Schlüssel; fehlt er, startet die Applikation nicht |
| `GENUS_EVENTSTORE_DIR` | `var/events` | Verzeichnis für JSONL-Event-Logs (pro `run_id` eine Datei) |
| `GENUS_ENV` | `development` | Umgebung; `production` deaktiviert Debug-Details in Fehlermeldungen |
| `GENUS_LOG_LEVEL` | `INFO` | Log-Level: `DEBUG` / `INFO` / `WARNING` / `ERROR` |

### Beispiel: Docker / systemd

```bash
export API_KEY="mein-geheimes-schluessel-mit-mind-32-zeichen"
export GENUS_EVENTSTORE_DIR="/var/lib/genus/events"
export GENUS_ENV="production"
```

### Konfiguration im Code

```python
from genus.memory.jsonl_event_store import JsonlEventStore

# Explizit per Argument (höchste Priorität)
store = JsonlEventStore(base_dir="/opt/genus/events")

# Oder via ENV (automatisch ausgelesen)
# GENUS_EVENTSTORE_DIR=/opt/genus/events
store = JsonlEventStore()
print(store.base_dir)  # → "/opt/genus/events"
```

---

## 2. EventStore – Wo liegen die Logs?

### Verzeichnisstruktur

```
var/events/                                          ← Default-Pfad
├── 2026-04-05T15-30-00__analyze__abc123.jsonl      ← Ein Run
├── 2026-04-05T16-00-00__analyze__xyz789.jsonl      ← Anderer Run
└── unknown.jsonl                                    ← Events ohne run_id (Warnung!)
```

### Dateiformat: JSONL (eine Zeile = ein Event)

```jsonl
{"timestamp": "2026-04-05T15:30:01Z", "run_id": "2026-04-05T15-30-00__analyze__abc123", "topic": "analysis.completed", "sender_id": "AnalysisAgent-1", "payload": {"classification": "high", "confidence": 0.87}, "metadata": {"run_id": "2026-04-05T15-30-00__analyze__abc123"}}
{"timestamp": "2026-04-05T15:30:02Z", "run_id": "2026-04-05T15-30-00__analyze__abc123", "topic": "quality.scored", "sender_id": "QualityAgent-1", "payload": {"quality_score": 0.87, "dimensions": {}, "evidence": []}, "metadata": {"run_id": "2026-04-05T15-30-00__analyze__abc123"}}
{"timestamp": "2026-04-05T15:30:03Z", "run_id": "2026-04-05T15-30-00__analyze__abc123", "topic": "decision.made", "sender_id": "DecisionAgent-1", "payload": {"decision": "accept", "reason": "quality_score >= min_quality", "quality_score": 0.87, "min_quality": 0.8, "attempt": 1, "max_retries": 3, "critical": false}, "metadata": {"run_id": "2026-04-05T15-30-00__analyze__abc123"}}
```

---

## 3. Einen Run inspizieren / Replay

### Via Python-API

```python
from genus.memory.jsonl_event_store import JsonlEventStore

store = JsonlEventStore()  # oder JsonlEventStore(base_dir="var/events")
run_id = "2026-04-05T15-30-00__analyze__abc123"

# Alle Events eines Runs ausgeben
for envelope in store.iter(run_id):
    print(f"[{envelope.timestamp}] {envelope.topic}: {envelope.payload}")

# Letztes Event eines bestimmten Topics
last_decision = store.latest(run_id, topic="decision.made")
if last_decision:
    print("Entscheidung:", last_decision.payload.get("decision"))
```

### Via Kommandozeile

```bash
# Alle Events eines Runs anzeigen (pretty-printed)
cat var/events/2026-04-05T15-30-00__analyze__abc123.jsonl | python3 -m json.tool --no-ensure-ascii

# Nur Entscheidungen anzeigen
grep '"topic": "decision.made"' var/events/*.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    _, data = line.split(':', 1)
    e = json.loads(data)
    print(e['run_id'], '->', e['payload']['decision'], ':', e['payload']['reason'])
"

# Alle Runs mit escalate-Entscheidung finden
grep '"decision": "escalate"' var/events/*.jsonl
```

---

## 4. Debugging-Checkliste

### „Warum wurde `replan` entschieden?"

1. **EventStore öffnen:** `cat var/events/<run_id>.jsonl`
2. **`quality.scored` suchen:**
   - Ist `quality_score` vorhanden und ein float?
   - Falls `quality_score: null` → kein Signal vom QualityAgent → **replan** wegen fehlender Evidenz
3. **`analysis.completed` prüfen:**
   - Hat die Analyse ein auswertbares Signal geliefert (`confidence`, `score`, `quality_score`)?
4. **`decision.made` lesen:** `payload.reason` enthält die genaue Begründung

### „Warum wurde `escalate` entschieden?"

1. **`decision.made` öffnen:** `payload.reason` lesen
   - `"critical/high-risk without explicit requirements"` → Critical Gate ausgelöst
   - `"retry budget exhausted"` → `attempt >= max_retries`
2. **Kontext prüfen:** War `context["critical"] = True` oder `context["risk"] = "high"` in der Nachricht?
3. **Retry-History zählen:** Wie viele `decision.made`-Events mit `decision: "retry"` gibt es für diesen Run?

### „Warum wurde `retry` nicht erneut ausgeführt?"

- `attempt >= max_retries` (Default: 3) → Retry-Budget erschöpft → `escalate`
- `quality_score < min_quality - 0.05` → zu weit unter der Schwelle → direkt `replan`

### „Fehlende `run_id` Warnung im Log"

- Suche in `var/events/unknown.jsonl` nach dem fehlenden Event
- `metadata["run_id_missing"] == true` zeigt, welche Nachrichten betroffen sind
- Ursache: `attach_run_id()` wurde vor `publish()` nicht aufgerufen

### „Der EventStore schreibt nicht"

1. `GENUS_EVENTSTORE_DIR` korrekt gesetzt? `echo $GENUS_EVENTSTORE_DIR`
2. Schreibrechte auf das Verzeichnis? `ls -la var/events/`
3. Ist der `EventRecorderAgent` initialisiert und gestartet? Lifecycle prüfen
4. Ist das Topic in `record_topics`? Standardmäßig nur die Whitelist

---

## 5. Tests ausführen

```bash
# Alle Tests
python -m pytest tests/ -v

# Nur EventStore-Tests
python -m pytest tests/ -v -k "event_store or recorder"

# Mit Coverage
python -m pytest tests/ --cov=genus --cov-report=term-missing
```

---

## 6. Monitoring-Hinweise

| Signal | Bedeutung | Aktion |
|---|---|---|
| `unknown.jsonl` existiert oder wächst | Nachrichten ohne `run_id` | `attach_run_id()` Aufrufe prüfen |
| Viele `escalate`-Entscheidungen | Qualität unter Schwelle, Budget erschöpft | Analyse-Pipeline oder `min_quality` prüfen |
| Viele `replan`-Entscheidungen | Kein Qualitätssignal | QualityAgent-Subscription und Analysis-Output prüfen |
| `var/events/` wächst stark | Viele Runs | EventStore-Archivierungsstrategie planen (manuell, kein Auto-Cleanup) |
