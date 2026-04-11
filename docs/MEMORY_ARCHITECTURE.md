# GENUS Memory-Architektur

> *Gedächtnis heißt auch vergessen — aber kein Chaos dadurch.*

---

## Das Problem

Ein LLM hat ein begrenztes Kontextfenster.
"Immer die letzten 20 Nachrichten" ist naiv.
"Alles für immer speichern" ist Chaos.

GENUS braucht ein Gedächtnis das wie ein echtes Gedächtnis funktioniert:
selektiv, komprimierend, assozierend — und vergessend wo es sinnvoll ist.

---

## Die vier Gedächtnisschichten

### 1. Working Memory (Arbeitsgedächtnis)
**Was:** Die letzten N Nachrichten der aktuellen Session.
**Wie lang:** Solange die Session aktiv ist.
**Wofür:** Unmittelbarer Gesprächskontext.
**Implementiert:** `ConversationMemory` (Phase 12+13 ✅)

```
"Was hast du gerade gesagt?"
→ Working Memory antwortet sofort
```

### 2. Episodic Memory (Episodisches Gedächtnis)
**Was:** Komprimierte Zusammenfassungen vergangener Gespräche.
**Wie lang:** Wochen bis Monate, dann verdichtet.
**Wofür:** "Weißt du noch was wir über Solar besprochen haben?"
**Implementiert:** Phase 14b (geplant)

```
5 Gespräche über Solar-Anlage (roh: 200 Nachrichten)
    ↓ MemoryAgent (nachts)
"April 2026: User plant Solar-Anlage für Pi.
 Budget ~500€. Bevorzugt lokale Installateure.
 Offene Frage: Wechselrichter-Kompatibilität."
(1 Zeile statt 200 Nachrichten)
```

### 3. Semantic Memory (Semantisches Gedächtnis)
**Was:** Fakten, Präferenzen, Entscheidungen — strukturiert.
**Wie lang:** Permanent (bis explizit geändert).
**Wofür:** "Was weiß GENUS über mich?"
**Implementiert:** Phase 14 (geplant)

```json
{
  "user": "WoltLab51",
  "preferences": {
    "antwort_stil": "kurz und direkt",
    "sprache": "deutsch",
    "llm_präferenz": "ollama_lokal"
  },
  "projekte": ["GENUS", "familien-ki-pi5", "Solar"],
  "entscheidungen": [
    {"datum": "2026-04", "entscheidung": "kein Redis", "grund": "Pi zu klein"}
  ],
  "hardware": {
    "pi": "Raspberry Pi 5, 8GB",
    "laptop": "ThinkPad X1 Carbon"
  }
}
```

### 4. Procedural Memory (Prozedurales Gedächtnis)
**Was:** Wie macht GENUS Dinge? Playbooks, Tools, Strategien.
**Wie lang:** Permanent, wächst durch Lernen.
**Wofür:** "Wie baut man einen Agent?" — GENUS weiß es schon.
**Implementiert:** StrategyStore (bereits vorhanden ✅)

---

## Relevanz: Wer entscheidet was in den Kontext kommt?

Nicht eine feste Zahl ("immer 20 Nachrichten").
Das LLM entscheidet — mit Hilfe von GENUS.

```python
async def build_context(user_message: str, user_id: str) -> List[dict]:

    # 1. Immer: letzte 5 Nachrichten (unmittelbarer Kontext)
    recent = working_memory.get_last(5)

    # 2. Immer: Nutzer-Profil (wer spricht?)
    profile = semantic_memory.get_profile(user_id)

    # 3. Thematisch passend: relevante Fakten
    relevant_facts = semantic_memory.search(user_message, top_k=5)

    # 4. Nur bei Memory-Anfragen: vergangene Episoden
    if intent == MEMORY_REQUEST:
        episodes = episodic_memory.search(user_message, top_k=3)
    else:
        episodes = []

    # 5. Zusammenbauen — dynamisch, relevant, nicht "immer alles"
    return build_llm_context(
        system_prompt=GENUS_IDENTITY,
        profile=profile,
        facts=relevant_facts,
        episodes=episodes,
        recent=recent,
    )
```

---

## Vergessen — gezielt, nicht zufällig

### Was GENUS vergisst (nach 7 Tagen):
- Smalltalk ("Hey wie geht's" → "Gut danke")
- Interne Zwischenschritte
- Duplikate

### Was GENUS verdichtet (nach 30 Tagen):
- Gespräche → Zusammenfassungen
- Mehrere Runs zum gleichen Thema → eine Erkenntnis

### Was GENUS nie vergisst:
- Explizite Entscheidungen ("Wir nutzen kein Redis")
- Persönliche Präferenzen
- Fehler und was daraus gelernt wurde
- Familien-Fakten (Geburtstage, Namen, Projekte)

### Konsistenz-Check (kein stilles Überschreiben):
```
Neu: "Ich will Redis nutzen"
Alt: "Wir haben entschieden kein Redis zu nutzen" (April 2026)

GENUS fragt nach:
"Du hattest im April entschieden Redis nicht zu nutzen —
 hat sich das geändert?"
```

---

## Implementierungsplan

| Phase | Was | Status |
|---|---|---|
| 12+13 | Working Memory (ConversationMemory) | ✅ |
| 14 | Semantic Memory (Nutzer-Profile, Fakten) | 🔜 |
| 14b | Episodic Memory (MemoryAgent, Nacht-Job) | 🔜 |
| 14b | Konsistenz-Check | 🔜 |
| 15+ | Vektor-Suche (wenn Volumen groß wird) | 🔮 |
