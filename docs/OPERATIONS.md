# GENUS – Betrieb & Debugging

> **Stand:** 2026-04-05 | Sprache: Deutsch

---

## LLM-Konfiguration

| Variable | Default | Beschreibung |
|---|---|---|
| `GENUS_LLM_OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `GENUS_LLM_OLLAMA_MODEL` | `llama3.2` | Standard-Ollama-Modell |
| `GENUS_OPENAI_API_KEY` | — | OpenAI API Key (optional) |
| `GENUS_LLM_STRATEGY` | `adaptive` | Routing-Strategie: `adaptive`, `quality`, `cost`, `local` |
| `GENUS_LLM_SCORES_PATH` | `var/router_scores.jsonl` | Pfad für Router-Score-Persistenz |

Ohne konfigurierte Provider laufen alle Agenten im **Stub-Modus** (rückwärtskompatibel).

### Schnellstart auf dem Raspberry Pi (nur Ollama)

```bash
# 1. Ollama installieren und starten
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2

# 2. GENUS starten (Ollama wird automatisch erkannt)
uvicorn genus.api:create_app --factory --host 0.0.0.0 --port 8000
```

### Mit OpenAI + Ollama (Hybrid)

```bash
export GENUS_OPENAI_API_KEY="sk-..."
export GENUS_LLM_STRATEGY="adaptive"
uvicorn genus.api:create_app --factory --host 0.0.0.0 --port 8000
```

---

## 1. Konfiguration

### Umgebungsvariablen

| Variable | Default | Beschreibung |
|---|---|---|
| `API_KEY` | – (Pflicht) | API-Schlüssel; fehlt er, startet die Applikation nicht |
| `GENUS_EVENTSTORE_DIR` | `var/events` | Verzeichnis für JSONL-Event-Logs (pro `run_id` eine Datei) |
| `GENUS_ENV` | `development` | Umgebung; `production` deaktiviert Debug-Details in Fehlermeldungen |
| `GENUS_LOG_LEVEL` | `INFO` | Log-Level: `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `GENUS_LLM_OLLAMA_URL` | `http://localhost:11434` | Ollama API URL (siehe LLM-Konfiguration) |
| `GENUS_LLM_OLLAMA_MODEL` | `llama3.2` | Standard-Ollama-Modell |
| `GENUS_OPENAI_API_KEY` | — | OpenAI API Key (optional) |
| `GENUS_LLM_STRATEGY` | `adaptive` | Routing-Strategie (`adaptive`, `quality`, `cost`, `local`) |
| `GENUS_LLM_SCORES_PATH` | `var/router_scores.jsonl` | Pfad für Router-Score-Persistenz |
| `GENUS_NEEDS_DIR` | `var/needs/` | Verzeichnis für NeedObserver-State-Persistenz |
| `GENUS_SANDBOX_ENABLED` | `true` | Sandbox-Probelauf vor Agent-Bootstrap aktivieren (Phase 11c) |
| `GENUS_CONVERSATIONS_DIR` | `var/conversations/` | Gesprächs-Persistenz (Phase 13) |
| `GENUS_SESSION_TIMEOUT_MINUTES` | `30` | Inaktive Konversations-Sessions bereinigen (Phase 13) |
| `GENUS_MAX_CONVERSATION_HISTORY` | `20` | Maximale Nachrichten im LLM-Kontext pro Session (Phase 13) |
| `GENUS_MASTER_KEY` | – (Pflicht) | Superadmin API-Key für `ronny_wolter`; fehlt er, startet GENUS nicht (Phase 14) |
| `GENUS_PROFILES_DIR` | `var/profiles/` | Profil-Dateien (JSON pro User) (Phase 14) |
| `GENUS_GROUPS_DIR` | `var/groups/` | Gruppen-Dateien (JSON pro Gruppe) (Phase 14) |
| `GENUS_VAULT_DIR` | `var/vault/` | Vertrauliche Daten (PrivacyVault) (Phase 14) |
| `GENUS_DEFAULT_GROUP_NAME` | `Meine Familie` | Name der Standard-Familiengruppe (Phase 14) |
| `GENUS_CONFIG_PATH` | — | Optionaler Pfad zu `genus.config.yaml` für Actor/Family/API-Key-Mapping |
### Beispiel: Docker / systemd

```bash
export API_KEY="mein-geheimes-schluessel-mit-mind-32-zeichen"
export GENUS_EVENTSTORE_DIR="/var/lib/genus/events"
export GENUS_ENV="production"
```

### Actor-Identity Konfiguration (`genus.config.yaml`)

```yaml
actors:
  - actor_id: papa-phone
    type: device
    role: OPERATOR
    families: [family-woltlab]
families:
  - family_id: family-woltlab
    name: WoltLab Familie
    members: [papa-phone]
api_keys:
  - key_env: GENUS_KEY_PAPA_PHONE
    actor_id: papa-phone
```

```bash
export GENUS_KEY_PAPA_PHONE="super-secret-token"
# optional, wenn Datei nicht im Projekt-Root liegt:
export GENUS_CONFIG_PATH="/opt/genus/genus.config.yaml"
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

## 5. Outcome per CLI einspeisen

Mit dem CLI-Producer kann ein Operator ein `outcome.recorded`-Event manuell
auf den MessageBus veröffentlichen. Die Persistenz übernimmt der
`EventRecorderAgent` (ist standardmäßig für `outcome.recorded` abonniert).

### Grundaufruf

```bash
python -m genus.cli.outcome \
    --run-id  2026-04-05T15-30-00__analyze__abc123 \
    --outcome good \
    --score-delta 1.0
```

### Mit optionalen Feldern

```bash
python -m genus.cli.outcome \
    --run-id       2026-04-05T15-30-00__analyze__abc123 \
    --outcome      bad \
    --score-delta  -2.5 \
    --notes        "Ergebnis nicht verwertbar – fehlende Sensordaten" \
    --source       user \
    --timestamp    2026-04-05T17:00:00+00:00
```

### Parameter

| Parameter | Pflicht | Default | Beschreibung |
|---|---|---|---|
| `--run-id` | ✅ Ja | – | Run-ID (in `Message.metadata["run_id"]`) |
| `--outcome` | ✅ Ja | – | `good` \| `bad` \| `unknown` |
| `--score-delta` | ✅ Ja | – | Float; wird auf `[-10.0, 10.0]` geclampt |
| `--notes` | ❌ Nein | – | Optionaler Freitext; max. 256 Zeichen |
| `--source` | ❌ Nein | `user` | Wer das Outcome liefert; max. 64 Zeichen |
| `--timestamp` | ❌ Nein | `now()` UTC | ISO-8601-String; wird automatisch gesetzt wenn nicht angegeben |

> **Hinweis:** Das CLI schreibt keine Dateien direkt. Die Persistenz läuft
> ausschließlich über den `EventRecorderAgent`.

---

## 6. Sicherheits-Features: Topic-ACL und Kill-Switch

### 6.1 Topic-ACL (opt-in)

Die ACL-Enforcement ist **standardmäßig deaktiviert**. Der MessageBus ist im
Default vollständig permissiv – bestehende Pipelines und Tests laufen
unverändert.

Enforcement aktivieren:

```python
from genus.security.topic_acl import TopicAclPolicy, TopicPermissionError
from genus.communication.message_bus import MessageBus

policy = TopicAclPolicy()
policy.allow("QualityAgent-1", "quality.scored")
policy.allow("AnalysisAgent-1", "analysis.completed")
policy.allow("DecisionAgent-1", "decision.made")

bus = MessageBus(acl_policy=policy, acl_enforced=True)
# Jedes publish() prüft nun, ob sender_id das Topic darf.
# Bei Verstoß: TopicPermissionError
```

**QM-Sicherheit:** QualityAgent und DecisionAgent bleiben im Default-Modus
unberührt. Bei aktivem Enforcement jeden publizierenden Agent explizit in der
Policy eintragen.

### 6.2 Kill-Switch

Globaler Notfall-Stop für alle `publish()`-Aufrufe am MessageBus.

```python
from genus.security.kill_switch import KillSwitch, KillSwitchActiveError
from genus.communication.message_bus import MessageBus

ks = KillSwitch(allowed_topics={"health.ping"})  # optionale Allowlist
bus = MessageBus(kill_switch=ks)
```

**Aktivieren (Notfall):**

```python
ks.activate(reason="Sicherheitsvorfall erkannt", actor="ops-team")
# Ab sofort wirft jedes bus.publish() für Topics außerhalb der Allowlist
# eine KillSwitchActiveError.
```

**Deaktivieren (Normalbetrieb wiederherstellen):**

```python
ks.deactivate(actor="ops-team")
# Normaler Betrieb sofort wiederhergestellt – kein Restart nötig.
```

**Reihenfolge:** Der Kill-Switch wird **vor** dem ACL-Check geprüft.

**QM-Auswirkung:** Ein aktiver Kill-Switch blockiert **auch** QualityAgent und
DecisionAgent. Das ist beabsichtigt – ein aktiver Kill-Switch signalisiert den
vollständigen Notfall-Stop des Systems. Nach `deactivate()` laufen alle Agents
sofort wieder normal.

| Zustand | Auswirkung |
|---|---|
| `ks.is_active() == False` | Kein Einfluss auf publish() – Normalbetrieb |
| `ks.is_active() == True` | Alle publish()-Aufrufe außer Allowlist → `KillSwitchActiveError` |
| Nach `ks.deactivate()` | Sofort wieder Normalbetrieb (kein Restart erforderlich) |

---

## 7. Tests ausführen

```bash
# Alle Tests
python -m pytest tests/ -v

# Nur EventStore-Tests
python -m pytest tests/ -v -k "event_store or recorder"

# Nur Security-Tests
python -m pytest tests/ -v -k "security"

# Mit Coverage
python -m pytest tests/ --cov=genus --cov-report=term-missing
```

---

## 8. Monitoring-Hinweise

| Signal | Bedeutung | Aktion |
|---|---|---|
| `unknown.jsonl` existiert oder wächst | Nachrichten ohne `run_id` | `attach_run_id()` Aufrufe prüfen |
| Viele `escalate`-Entscheidungen | Qualität unter Schwelle, Budget erschöpft | Analyse-Pipeline oder `min_quality` prüfen |
| Viele `replan`-Entscheidungen | Kein Qualitätssignal | QualityAgent-Subscription und Analysis-Output prüfen |
| `var/events/` wächst stark | Viele Runs | EventStore-Archivierungsstrategie planen (manuell, kein Auto-Cleanup) |
| `KillSwitchActiveError` im Log | Kill-Switch ist aktiv | `ks.deactivate()` aufrufen wenn Notfall behoben |
| `TopicPermissionError` im Log | ACL-Verstoß (Enforcement aktiv) | Policy prüfen: fehlt ein `allow()`-Eintrag? |
