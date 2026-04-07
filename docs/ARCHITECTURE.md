# GENUS-2.0 — Verfassung

> Stand: 2026-04-07 | Anti-Drift-Dokument | Verbindlich für alle Agents und Menschen

---

## 1. Orchestratoren — Rollen und Grenzen

GENUS hat zwei Orchestratoren mit klar getrennten Verantwortlichkeiten:

| Orchestrator | Modul | Verantwortung |
|---|---|---|
| `DevLoopOrchestrator` | `genus/dev/` | **Einziges System das Tasks plant und ausführt.** Koordiniert Plan → Implement → Test → Fix → Review. |
| `Orchestrator` (Tool-Ebene) | `genus/orchestration/` | Führt einzelne Tool-Calls aus (Step-Ebene). Untergeordnet dem DevLoop. |

**Harte Regeln:**

```
DevLoopOrchestrator  → darf ToolOrchestrator nutzen
ToolOrchestrator     → darf DevLoopOrchestrator NICHT kennen
Strategy             → darf Tools NICHT direkt ausführen
Agents               → dürfen sich NICHT gegenseitig direkt aufrufen (nur via MessageBus)
```

---

## 2. Journal — Single Source of Truth

> **If it is not in the RunJournal, it does not exist.**

- Jeder Run **muss** ein `RunJournal` haben. Kein optionales Journal, keine Silent Runs.
- Jede Phase schreibt ins Journal: `log_event` + `save_artifact` wo sinnvoll.
- Journal-Fehler werden geloggt (`logger.warning`), aber **unterbrechen nie den Run**.
- Das Journal ist SSOT — nicht der MessageBus, nicht der EventStore.

---

## 3. Feedback — Signal, kein Befehl

> **Feedback is a signal, not a command. It must NEVER directly change strategy.**

```
outcome.recorded  →  FeedbackAgent
                          ↓ journal.log_event + save_artifact  (best-effort)
                          ↓ feedback.received                  (immer, auch ohne Journal)
                               ↓
                          [zukünftig: LearningAgent interpretiert]
```

- `feedback.received` wird **immer** publiziert, solange `run_id` und Payload valide sind.
- Routing-Entscheidungen liegen beim **Orchestrator**, nicht beim FeedbackAgent.
- `FeedbackAgent` trifft keine Policy-Entscheidungen.

---

## 4. Decision Flow — Herzschlag von GENUS

```
Strategy → DevLoop → Execution → Evaluation → Learning → Strategy
```

Dieser Kreislauf ist **geschlossen**. Kein Agent bricht ihn auf. Kein Agent überspringt eine Stufe.

- **Strategy** wählt Playbook
- **DevLoop** führt aus
- **Execution** (Builder, Tests) liefert Ergebnis
- **Evaluation** bewertet (Score, FailureClass)
- **Learning** liest Evaluation + Feedback → passt Strategy an

---

## 5. Dependency-Regeln

```
genus/core/          → keine Abhängigkeiten
genus/communication/ → nur genus/core/
genus/memory/        → genus/core/, genus/communication/
genus/feedback/      → genus/core/, genus/communication/, genus/memory/
genus/dev/           → genus/core/, genus/communication/, genus/memory/, genus/strategy/
genus/strategy/      → genus/core/, genus/memory/
genus/agents/        → genus/core/, genus/communication/, genus/memory/
```

**Regel:** Abhängigkeiten zeigen **immer nach innen**. Nie nach außen. Nie zirkulär.

---

## 6. Unveränderliche Prinzipien

Diese Prinzipien gelten immer, für jeden Agent, jeden PR, jeden Refactor:

1. **Journal first** — kein Run ohne RunJournal
2. **Signal vor Entscheidung** — Feedback wird erfasst, nicht direkt umgesetzt
3. **Bus-only Kommunikation** — Agents sprechen via MessageBus, nie direkt
4. **Fail-safe Logging** — Infrastruktur-Fehler (Journal, Bus) crashen nie den Run
5. **run_id Pflicht** — jede Nachricht trägt eine run_id in metadata
6. **Orchestrator entscheidet** — kein Agent macht Routing-Entscheidungen für andere

---

## 7. Weiterführende Dokumente

| Dokument | Inhalt |
|---|---|
| `docs/ARCHITECTURE_OVERVIEW.md` | Technische Modulgrenzen, Agent-Lifecycle, Dependency-Details |
| `docs/TOPICS.md` | Topic-Registry, Payload-Contracts, Recorder-Whitelist |
| `docs/DEV_LOOP.md` | DevLoop-Phasen, Phase-IDs, Timeout-Handling |
| `docs/POLICIES.md` | Decision-Semantik, Quality-Thresholds |
| `docs/SECURITY.md` | Sicherheitsposture, Threat Model |
