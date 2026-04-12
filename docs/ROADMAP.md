# GENUS — Roadmap

> **Sprache:** Deutsch
> **Stand:** 2026-04-11
> **Version:** GENUS-2.0

---

## Was ist GENUS?

GENUS ist ein digitales Wesen, das mit seiner Familie lebt, denkt, lernt und wächst.
Kein Framework. Kein Chatbot. Ein lebendes, lernendes System.

**→ [Wer ist GENUS? (Identität & Persönlichkeit)](GENUS_IDENTITY.md)**

---

## Abgeschlossen ✅

### Phase 13c — Kontext-Verdrahtung
GENUS weiß wer spricht, wo die Person ist und was gerade situativ los ist.
SituationContext (TTL-aware), ContextBuilder (3 Schichten), PromptStrategy (intent-adaptiv),
DevContextExtractor (Gespräch → DevLoop), EpisodicContext → PlannerPrompt.

*Liefert: SituationContext, SituationStore, ContextBuilder, PromptStrategy, DevContextExtractor, context_formatter.*

### P0 — Core-Infrastruktur
Agent ABC, MessageBus, Lifecycle, Config, erste Agenten (DataCollector, Analysis, Quality, Decision).
Das Fundament auf dem alles aufbaut.

### P1-A — Decision Policy
`accept / retry / replan / escalate / delegate` — jede Entscheidung ist nachvollziehbar begründet.
QualityScorecard, QualityAgent, Critical Gate.

### P1-B — Memory / EventStore
JSONL EventStore, EventEnvelope, EventRecorderAgent, Topic-Whitelist.
Vollständige Nachvollziehbarkeit jedes Runs via `run_id`.

### P1-C — DataSanitizerAgent
`data.collected` → `data.sanitized`: kein PII, keine Rohdaten im EventStore.
SanitizationPolicy, Whitelist, Evidence.

### P2 — API-Layer + Rollenmodell
FastAPI: `/health`, `/runs`, `/outcome`, `/kill-switch`.
Bearer-Auth, strukturierte Fehler, Rollenmodell (READER / OPERATOR / ADMIN).

### P3 — Growth-System
NeedObserver (erkennt fehlende Fähigkeiten), GrowthOrchestrator (plant Wachstum),
Bootstrapper (lädt neue Agenten). GENUS kann sich selbst erweitern.

### P4 — DevLoop
PlannerAgent (plant Schritte), BuilderAgent (schreibt Code), TesterAgent (prüft),
ReviewerAgent (bewertet und lernt). GENUS baut sich selbst.

### P5 — Sandbox + Workspace
Isolierte Ausführungsumgebung für generierten Code.
SandboxRunner, SandboxPolicy, WorkspaceManager.

### P6 — Strategy-Learning
GrowthBridge verbindet Growth-System und DevLoop.
GENUS lernt welche Strategien in welchen Situationen funktionieren.

### P7 — Meta-Evaluation
EvaluationAgent bewertet die eigene Performance.
TemplateBuilderAgent + AgentCodeTemplate für konsistenten Code-Output.

### P8 — GitHub-Integration
GitTools, AutoCommitTool — GENUS kann Code in echte Repositories schreiben.

### P9 — TemplateBuilderAgent + AgentBootstrapper
Strukturierter Weg neue Agenten zu erstellen und zu laden.
AgentBootstrapper mit importlib-Basis.

### P10–P10d — LLM-Schicht
- LLMClient (abstraktes Interface)
- LLMRouter (ADAPTIVE-Strategie: bester Provider per Aufgabentyp)
- OpenAIProvider (GPT-4, GPT-3.5)
- OllamaProvider (lokal, Pi-tauglich: llama3.2, mistral)
- CredentialStore (verschlüsselte Secrets)
- Score-Feedback-Loop (GENUS lernt welcher Provider für was besser ist)

### P11a — LLMRouter in DevLoopOrchestrator verdrahtet
Erster echter End-to-End-Run: GENUS denkt mit LLM beim Planen, Bauen und Reviewen.

### P11b — NeedObserver-Persistenz (NeedStore)
NeedStore speichert erkannte Bedarfe über Neustarts hinweg.
GENUS vergisst nicht was es lernen wollte.

### P11c — Bootstrapper-Sandbox (CodeValidator)
AST-Scanner + Probelauf vor dem Laden von generiertem Code.
Kein unkontrollierter Code mehr. SECURITY-TODO geschlossen. 🔒

---

## Geplant 🔜

### Phase B — Echter TesterAgent
TesterAgent ruft pytest wirklich auf — in der Sandbox, mit echtem Output.
Der DevLoop schließt sich vollständig: Plan → Build → Test → Review.

*Liefert: TesterAgent mit subprocess-pytest, Ergebnis-Parsing, Fehler-Feedback an BuilderAgent.*

### Phase 12 — WebSocket + API-Streaming
Kein Polling mehr. Live-Status von laufenden Runs direkt im Browser / auf dem Handy.
WebSocket-Endpoint, Event-Streaming, Reconnect-Logik.

*Liefert: `ws://genus/runs/{run_id}/stream`, Server-Sent-Events, WebSocket-Client-Beispiel.*

### Phase 13 — ConversationAgent + Dialog-Gedächtnis
GENUS kann reden. Du schreibst, GENUS antwortet, fragt nach, plant, baut.
Intent-Erkennung, Kontext über mehrere Nachrichten, Dialog-History.

*Liefert: ConversationAgent, DialogStore, Intent-Router (chat / devloop / knowledge / home).*

### Phase 14 — Nutzer-Profile + Familien-System
GENUS kennt jeden. Jede Person hat ein Profil (Vorlieben, Projekte, Gewohnheiten).
Private Bereiche die GENUS nicht teilt. Gemeinsame Bereiche für die Familie.

*Liefert: UserProfile, FamilyContext, PrivacyPolicy, profile-aware ConversationAgent.*

### Phase 14b — MemoryAgent + Episodisches Gedächtnis
GENUS erinnert sich wirklich — nicht nur an die letzten 20 Nachrichten.
Nacht-Job komprimiert Gespräche, überführt Wichtiges ins Semantic Memory,
markiert Unwichtiges zum Vergessen. Konsistenz-Check verhindert stilles Überschreiben.

*Liefert: MemoryAgent, EpisodicMemory, Nacht-Komprimierung, Konsistenz-Check.*

→ Siehe auch: [MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md)

### Phase 15 — KnowledgeAgent + Recherche-Tools + Deployment-Awareness
GENUS kann recherchieren. WebSearchTool, SummarizeTool, LLM-gestützte Zusammenfassung.
Verknüpft aktuelles Wissen mit vergangenen Gesprächen.
DeploymentDetector erkennt beim Start automatisch Pi / X1 / Fernzugriff / Cloud-Fallback.

*Liefert: KnowledgeAgent, WebSearchTool (DuckDuckGo/SearXNG), SummarizeTool, MemoryLinker,
DeploymentDetector, genus.config.yaml-Support.*

→ Siehe auch: [DEPLOYMENT_MODES.md](DEPLOYMENT_MODES.md)

### Phase 15b — BackupAgent + WatchdogAgent
GENUS sichert sich selbst — täglich, automatisch, mit 3-2-1-Strategie.
WatchdogAgent überwacht Ollama, RAM, Disk und laufende Runs im Hintergrund.

*Liefert: BackupAgent (ZIP + Rotation), WatchdogAgent, Restore-Prozess.*

→ Siehe auch: [BACKGROUND_LOOP.md](BACKGROUND_LOOP.md)

### Phase 16 — HomeAgent + BriefingAgent (Pi-Kontrolle, Morgen-Briefing)
GENUS kennt das Zuhause. Systeminfo, Geräte, Netzwerke, Dateien.
Überwacht, meldet, reagiert — direkt auf dem Pi.
BriefingAgent liefert morgens um 07:00 eine Zusammenfassung: was ansteht, was GENUS vorbereitet hat.

*Liefert: HomeAgent, SystemInfoTool, DiskMonitorTool, NetworkTool, Pi-aware SandboxPolicy,
BriefingAgent.*

→ Siehe auch: [BACKGROUND_LOOP.md](BACKGROUND_LOOP.md)

### Phase 16b — Schwarm-LLM + Morphologische Zerlegung
GENUS zerlegt große Probleme in kleine präzise Fragen — jede an ein kleines lokales Modell.
Schwarmintelligenz aus einfachen Teilen. Schneller auf dem Pi als ein großes Modell.

*Liefert: SwarmOrchestrator, MorphologicalDecomposer, DimensionRouter.*

→ Siehe auch: [BACKGROUND_LOOP.md](BACKGROUND_LOOP.md)

### Phase 17 — ProaktivitätsAgent (Push, E-Mail, Dringlichkeit)
GENUS meldet sich von selbst. Push-Notifications, E-Mail, je nach Dringlichkeit.
Denkt weiter wenn du schläfst.

*Liefert: ProactivityAgent, NotificationRouter, DringlichkeitsStufen (LOW/MEDIUM/HIGH/URGENT).*

### Phase 18 — Frontend / Chat-PWA (Handy + Browser)
Die Oberfläche. Chat-Interface, Run-Status, Agent-Übersicht, Score-History.
Funktioniert auf dem Handy, im Browser, als PWA installierbar.

*Liefert: React/Vue PWA, WebSocket-Chat, Run-Dashboard, Familien-Profil-Ansicht.*

### Phase 19 — DnD-Master-Agent + NPC-System
GENUS als Spielleiter — nicht als Regelleser.
Lebendige Welten, echte NPCs mit eigenen Motiven, Geschichten die reagieren.
Erinnert sich an eure Kampagnen, Charaktere, offene Fäden.

*Liefert: DnDMasterAgent, NPCEngine (Motive, Geheimnisse, Memory), CampaignStore.*

### Phase 20 — Multi-Hardware-Orchestrierung (Pi + X1 + Cloud)
GENUS erkennt wo es läuft und verteilt Arbeit intelligent.
Schwere LLM-Tasks auf den X1, Always-On auf dem Pi, Chat in der Cloud.

*Liefert: HardwareRouter, OffloadPolicy, Pi↔X1-Sync, Cloud-Fallback.*

### Phase 21 — GENUS Self-Model (kennt sich selbst)
GENUS weiß was es kann, was es nicht kann, wie gut es ist.
Reflektiert eigene Performance, erkennt blinde Flecken, plant eigenes Wachstum.

*Liefert: SelfModel, CapabilityMap, ReflectionAgent, autonomer Wachstumsplan.*

---

## Architektur-Überblick

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

---

## Weiterführende Dokumentation

| Dokument | Inhalt |
|---|---|
| [GENUS_IDENTITY.md](GENUS_IDENTITY.md) | Wer ist GENUS? Persönlichkeit, Vision, Werte |
| [VISION_EXTENDED.md](VISION_EXTENDED.md) | Das Manifest — die Seele von GENUS |
| [MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md) | Wie GENUS erinnert und vergisst (4 Schichten) |
| [DEPLOYMENT_MODES.md](DEPLOYMENT_MODES.md) | Pi / X1 / Fernzugriff / Cloud + Backup-Strategie |
| [BACKGROUND_LOOP.md](BACKGROUND_LOOP.md) | Tagesablauf, Proaktivität, Schwarm-LLM |
| [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) | Modulgrenzen, Clean Architecture, Agent-Lifecycle |
| [TOPICS.md](TOPICS.md) | Topic-Registry, Payload-Contracts, Recorder-Whitelist |
| [SECURITY.md](SECURITY.md) | Sicherheitsmodell, ACL, Kill-Switch |
| [OPERATIONS.md](OPERATIONS.md) | Installation, Konfiguration, Umgebungsvariablen |
| [DEV_LOOP.md](DEV_LOOP.md) | DevLoop-Phasen, LLM-Integration |
