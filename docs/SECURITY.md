# GENUS – Sicherheitsposture

> **Stand:** 2026-04-05 | Sprache: Deutsch

---

## 1. Sicherheitsposture (heute)

### Implementierte Maßnahmen (Stand: P2)

| Maßnahme | Beschreibung | Implementierung |
|---|---|---|
| **run_id Governance** | Jede Nachricht muss eine `run_id` tragen; fehlt sie, wird das Event unter `"unknown"` gespeichert und eine Warnung geloggt | `genus/core/run.py`, `genus/agents/event_recorder_agent.py` |
| **Recorder-Whitelist** | Nur explizit freigegebene Topics werden persistiert (kein Opt-out vergessen) | `genus/agents/event_recorder_agent.py`: `DEFAULT_RECORD_TOPICS` |
| **Keine Rohdaten-Persistenz** | `data.collected` ist nicht in der Standard-Whitelist – Rohdaten werden nie automatisch gespeichert | Explizite Entscheidung in `DEFAULT_RECORD_TOPICS` |
| **Filename-Sanitierung** | `run_id` wird vor Dateizugriff sanitiert; Path-Traversal-Sequenzen (`..`) werfen `ValueError` | `genus/memory/jsonl_event_store.py`: `sanitize_run_id()` |
| **Topic-ACL (opt-in)** | Exact-match Whitelist, welche Sender auf welchen Topics publishen dürfen. Standardmäßig permissiv; Enforcement nur bei `acl_enforced=True` | `genus/security/topic_acl.py`, `genus/communication/message_bus.py` |
| **Kill-Switch (opt-in)** | Globaler Notfall-Stop; blockiert alle `publish()`-Aufrufe außer einer konfigurierbaren Allowlist | `genus/security/kill_switch.py`, `genus/communication/message_bus.py` |
| **API-Key-Authentifizierung** | Alle Endpunkte außer `/health` verlangen `Authorization: Bearer <key>` | 🔜 Geplant – `genus/api/middleware.py` (noch nicht implementiert) |
| **Strukturierte Fehlerantworten** | Keine internen Details in Fehlerantworten (außer Debug-Mode) | 🔜 Geplant – `genus/api/errors.py` (noch nicht implementiert) |
| **Append-only EventStore** | Events können nicht mutiert oder gelöscht werden – manipulationssicheres Audit-Log | `genus/memory/jsonl_event_store.py` |

---

## 2. Threat Model (vereinfacht)

### In-Scope-Bedrohungen

| Bedrohung | Beschreibung | Aktueller Schutz | Status |
|---|---|---|---|
| **PII / Secrets in Rohdaten** | `data.collected` kann personenbezogene Daten enthalten | Nicht persistiert by default | ✅ Heute |
| **Path Traversal via run_id** | Angreifer schleust `../../../etc/passwd` als run_id ein | `sanitize_run_id()` wirft `ValueError` bei `..` | ✅ Heute |
| **Event Poisoning** | Manipulierte Payload-Daten, die downstream falsche Entscheidungen auslösen | Payload-Validierung in `QualityAgent`/`DecisionAgent` | ⚠️ Partiell |
| **Topic Spoofing** | Unberechtigter Agent publiziert auf gesichertem Topic | Kein Sender-Whitelist für Topics (MessageBus-Ebene) | ✅ Heute (opt-in) |
| **Replay-Angriffe** | Alte Events werden erneut eingespielt | Kein Replay-Schutz (Event-Timestamps vorhanden) | 🔜 Geplant |
| **Unbefugter API-Zugriff** | Zugriff ohne gültigen API-Key | API-Key-Auth auf allen Endpunkten | ✅ Heute |
| **Credential-Leak im EventStore** | Secrets landen versehentlich in JSONL-Logs | Keine Rohdaten-Persistenz; Sanitizer geplant | ✅/🔜 Teilweise |

### Out-of-Scope (bewusst nicht berücksichtigt)
- Netzwerk-Sicherheit (TLS, Firewall) – Betreiber-Verantwortung
- Host-Level-Sicherheit (Dateisystem-Berechtigungen)
- Multi-Tenant-Isolation

---

## 3. Geplante Sicherheitsmaßnahmen

### P1-C: DataSanitizerAgent (Whitelist-basiert)

```
data.collected  →  DataSanitizerAgent  →  data.sanitized
```

- **Whitelist-Felder**: Nur explizit erlaubte Felder werden in `data.sanitized` aufgenommen
- **Regex-Redaction**: PII-Patterns (E-Mail, Telefon, IP) werden vor Weitergabe entfernt
- **Evidence**: `redaction_applied`, `pii_detected`, `removed_fields` im Payload dokumentiert
- **Größenlimit**: Payloads über einem konfigurierbaren Limit werden abgelehnt

### P2: Berechtigungen / Rollen ✅ (opt-in implementiert)

| Feature | Beschreibung | Status |
|---|---|---|
| **Topic-ACL (opt-in)** | `TopicAclPolicy`: exact-match Mapping `sender_id → set[topic]`; Enforcement via `acl_enforced=True` am MessageBus | ✅ Heute |
| **Rollen** | Unterscheidung: Operator / Reader / Admin | 🔜 Geplant |
| **Audit-Log für Rollen-Zugriffe** | Wer hat wann welches Topic publisht? | 🔜 Geplant |

#### Topic-ACL: opt-in Enforcement

ACL-Enforcement ist **standardmäßig deaktiviert**. Der MessageBus ist im Default-Modus vollständig permissiv – bestehende Tests und Pipelines laufen unverändert.

```python
from genus.security.topic_acl import TopicAclPolicy, TopicPermissionError
from genus.communication.message_bus import MessageBus

policy = TopicAclPolicy()
policy.allow("QualityAgent-1", "quality.scored")
policy.allow("AnalysisAgent-1", "analysis.completed")

# Enforcement aktivieren:
bus = MessageBus(acl_policy=policy, acl_enforced=True)
# bus.publish() wirft jetzt TopicPermissionError für unbekannte Sender/Topics
```

**QM-Hinweis:** QualityAgent und DecisionAgent laufen im Default-Modus (`acl_enforced=False`) unverändert. Bei Enforcement: jeden publizierenden Agent explizit in der Policy eintragen.

### P2: Kill-Switch ✅ (implementiert)

```python
from genus.security.kill_switch import KillSwitch, KillSwitchActiveError
from genus.communication.message_bus import MessageBus

ks = KillSwitch(allowed_topics={"health.ping"})  # optional allowlist
bus = MessageBus(kill_switch=ks)

# Notfall-Aktivierung:
ks.activate(reason="Sicherheitsvorfall", actor="ops-team")
# Alle bus.publish()-Aufrufe außer "health.ping" werfen KillSwitchActiveError

# Normalbetrieb wiederherstellen:
ks.deactivate(actor="ops-team")
```

**Wichtig:** Ein aktiver Kill-Switch blockiert **auch** QualityAgent und DecisionAgent. Das ist beabsichtigt – ein aktiver Kill-Switch signalisiert den vollständigen Notfall-Stop des Systems.

---

## 4. Betrieb: Sicherheitsrelevante Konfiguration

| ENV-Variable | Bedeutung | Empfehlung |
|---|---|---|
| `API_KEY` | API-Schlüssel für alle Endpunkte (Pflicht) | Mindestens 32 Zeichen, zufällig generiert |
| `GENUS_EVENTSTORE_DIR` | Pfad für JSONL-Event-Logs | Außerhalb des Web-Roots, Zugriff einschränken |
| `GENUS_ENV` | `development` oder `production` | In Production: `production` setzen (deaktiviert Debug-Details in Fehlern) |

---

## 5. Sicherheits-Checkliste für Operator

Vor dem produktiven Einsatz prüfen:

- [ ] `API_KEY` ist gesetzt und ausreichend zufällig
- [ ] `GENUS_EVENTSTORE_DIR` ist außerhalb des Web-Roots
- [ ] Dateisystem-Berechtigungen für EventStore-Verzeichnis eingeschränkt (nur GENUS-Prozess)
- [ ] `GENUS_ENV=production` gesetzt
- [ ] `data.collected` ist **nicht** in der `record_topics`-Konfiguration
- [ ] Logs regelmäßig auf `run_id_missing=True` Warnungen prüfen
- [ ] EventStore-Dateien regelmäßig auf unerwartete Größe prüfen
