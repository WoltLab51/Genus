# GENUS – Entscheidungs-Policies

> **Stand:** 2026-04-05 | Sprache: Deutsch

---

## 1. Decision-Semantik: Die fünf Entscheidungen

Der `DecisionAgent` trifft eine von fünf möglichen Entscheidungen basierend auf Qualitätsbewertung, Konfiguration und Kontext:

| Entscheidung | Bedeutung | Typische Bedingung |
|---|---|---|
| `accept` | Ergebnis ist akzeptabel, weiter | `quality_score >= min_quality` |
| `retry` | Qualität knapp unter Schwelle, nochmal versuchen | `quality_score >= min_quality - retry_margin` UND `attempt < max_retries` |
| `replan` | Qualität zu niedrig und kein Retry mehr / kein Signal | `quality_score < min_quality - retry_margin` ODER kein `quality_score` vorhanden |
| `escalate` | Critical-Gate ausgelöst ODER Retry-Budget erschöpft | `is_critical` ohne explizite Requirements ODER `attempt >= max_retries` |
| `delegate` | Explizit delegiert (z. B. via `context["delegate"] = True`) | `context.delegate == True` |

---

## 2. Entscheidungs-Ablauf (Prioritäten)

Der `DecisionAgent` prüft die Bedingungen in dieser Reihenfolge:

```
1. context["delegate"] == True           →  delegate
2. quality_score fehlt (kein Signal)     →  replan
3. Critical Gate:
   is_critical == True
   UND kein explizites min_quality       →  escalate
4. quality_score >= min_quality          →  accept
5. quality_score >= min_quality - 0.05
   UND attempt < max_retries             →  retry
6. attempt >= max_retries                →  escalate  (Budget erschöpft)
7. Sonst                                 →  replan
```

---

## 3. Konfigurierbare Parameter

### Standardwerte (aus `genus/agents/decision_agent.py`)

| Parameter | Default | Beschreibung |
|---|---|---|
| `default_min_quality` | `0.8` | Mindest-Qualitätsschwelle für `accept` |
| `default_max_retries` | `3` | Maximale Retry-Versuche |
| `retry_margin` | `0.05` | Toleranzband unterhalb `min_quality` für `retry` |

### Overrides via `context.requirements`

Die Standardwerte können pro-Request überschrieben werden:

```python
# In der Nachricht mitschicken:
message.payload["context"] = {
    "requirements": {
        "min_quality": 0.9,   # Strenger für diesen Run
        "max_retries": 5,
    },
    "critical": True          # Oder: risk = "high"
}
```

---

## 4. Critical Gate

Das **Critical Gate** greift, wenn:
- `context["critical"] == True` **ODER** `context["risk"] == "high"`
- **UND** kein explizites `min_quality` in `context.requirements`

**Ergebnis:** `escalate` mit Begründung `"critical/high-risk without explicit requirements"`

**Rationale:** Bei kritischen Operationen ohne klare Qualitätsanforderungen soll GENUS nicht autonom entscheiden – ein Mensch oder höheres System muss explizit Anforderungen setzen oder eskalieren.

---

## 5. QM-Preferred Evidence Rule

Der `QualityAgent` leitet den `quality_score` aus dem `analysis.completed`-Payload ab, in dieser Priorität:

| Priorität | Payload-Feld | Verarbeitungsschritt |
|---|---|---|
| 1 | `quality_score` | Direkt verwenden (float) |
| 2 | `score` | Normalisierung: `(1, 100] → /100`, `[0, 1] → unverändert` |
| 3 | `confidence` | Direkt verwenden (float [0, 1]) |
| 4 | – | `quality_score = None`, source = `no_signal` |

**Wichtig:** `quality.scored`-Events haben immer Vorrang vor direkten Analysis-Fallbacks im `DecisionAgent`. Wenn `quality.scored` veröffentlicht wurde, arbeitet der `DecisionAgent` mit diesem Score.

---

## 6. Out-of-Order Handling

**Aktuell (P1-B):** Der `DecisionAgent` subscribt auf `quality.scored`. Falls Nachrichten außer der Reihe ankommen:
- Der `DecisionAgent` verarbeitet jede `quality.scored`-Nachricht unabhängig
- Es gibt keine implizite Reihenfolge-Garantie (MessageBus ist async)
- `run_id` muss immer vorhanden sein, damit Events korrekt dem richtigen Run zugeordnet werden

**Geplant (P2):** Ein Orchestrator wird die Reihenfolge explizit koordinieren und out-of-order Szenarien handhaben.

---

## 7. Beispiel: Decision-Outcome-Tabelle

| Szenario | `quality_score` | `min_quality` | `critical` | `attempt` | `max_retries` | **Entscheidung** |
|---|---|---|---|---|---|---|
| Normale Analyse, gut | 0.90 | 0.80 | false | 1 | 3 | **accept** |
| Knapp drunter, Retry möglich | 0.77 | 0.80 | false | 1 | 3 | **retry** |
| Retry-Budget erschöpft | 0.77 | 0.80 | false | 3 | 3 | **escalate** |
| Kein Signal (kein Score) | None | 0.80 | false | 1 | 3 | **replan** |
| Critical Gate (kein explicit req.) | 0.75 | 0.80 | true | 1 | 3 | **escalate** |
| Critical, explicit req., gut | 0.90 | 0.85 | true | 1 | 3 | **accept** |
| Delegate-Flag gesetzt | 0.90 | 0.80 | false | 1 | 3 | **delegate** |
| Zu weit unter Schwelle | 0.60 | 0.80 | false | 1 | 3 | **replan** |
