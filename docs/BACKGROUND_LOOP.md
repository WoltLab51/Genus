# GENUS Background Loop

> *GENUS denkt weiter — auch wenn niemand fragt.*

---

## Das Prinzip

GENUS ist kein Request-Response-System.
Es lebt. Es denkt. Es bereitet vor.

Im Vordergrund: Gespräche, Anfragen, Runs.
Im Hintergrund: Verdauen, Lernen, Planen, Überwachen.

---

## Der Tagesablauf von GENUS

### 🌙 Nachts (02:00 – 05:00 Uhr)
Ruhige Zeit. Pi ist idle. GENUS arbeitet still.

```
02:00  MemoryAgent:
         Gespräche des Tages komprimieren
         Wichtiges in Semantic Memory überführen
         Unwichtiges markieren zum Vergessen

02:30  LearningAgent:
         Was lief heute gut?
         Was ist fehlgeschlagen?
         Strategie-Gewichte anpassen

03:00  BackupAgent:
         ZIP von var/ erstellen
         Auf USB/externes Laufwerk kopieren
         Alte Backups rotieren

03:30  CleanupAgent:
         Disk-Auslastung prüfen
         Alte Logs bereinigen
         Temp-Dateien löschen

04:00  ResearchAgent (optional):
         Offene Recherche-Aufgaben abarbeiten
         Themen vorrecherchieren die oft gefragt werden
         Ergebnisse cachen
```

### ☀️ Morgens (07:00 Uhr)
```
BriefingAgent:
  "Guten Morgen!
   Heute ist Samstag, 12. April.
   
   Du wolltest noch: Solar-Anlage Angebote vergleichen
   Ich habe schon: 3 Anbieter recherchiert (gestern Nacht)
   
   GENUS läuft seit 14 Tagen ohne Neustart.
   Disk: 34% belegt. Alles grün."
```

### ☀️ Tagsüber (kontinuierlich, idle)
```
WatchdogAgent (alle 5 Minuten):
  Ollama noch erreichbar?
  RAM über 85%?
  Disk über 90%?
  Laufende Runs hängen?
  → Bei Problem: sofort melden

PlannerAgent (alle 30 Minuten):
  Offene Tasks prüfen
  Fällige Erinnerungen prüfen
  Proaktiv melden wenn etwas ansteht
```

---

## Proaktivität: Wann meldet sich GENUS von selbst?

### Dringlichkeit → Kanal

```
KRITISCH:   Sofort, alle Kanäle
  Beispiel: Disk voll, Pi überhitzt, Sicherheitsproblem
  Kanal:    Push-Notification + E-Mail

WICHTIG:    Beim nächsten Gespräch + Push
  Beispiel: Run fehlgeschlagen, Backup fehlt 3 Tage
  Kanal:    Push-Notification

NORMAL:     Beim nächsten Gespräch erwähnen
  Beispiel: "Ich habe etwas Interessantes gefunden"
  Kanal:    Nächste Chat-Session

INFO:       Im Morgen-Briefing
  Beispiel: Tages-Zusammenfassung, Statistiken
  Kanal:    Morgen-Briefing (07:00)
```

---

## Schwarm-LLM: Große Probleme klein denken

GENUS nutzt nicht ein großes LLM für alles.
Es zerlegt Probleme morphologisch.

```
Problem: "Plane eine Solar-Anlage für den Pi"

Morphologische Zerlegung:
  Dimension 1: Strombedarf    → "Wie viel Watt braucht ein Pi 5?"
  Dimension 2: Standort       → "Wieviel Sonne hat [Ort] im Jahr?"
  Dimension 3: Speicher       → "Welche Akku-Kapazität für 24h Betrieb?"
  Dimension 4: Budget         → "Was kostet ein 50W Solar-Setup?"
  Dimension 5: Installation   → "Was brauche ich technisch?"

Jede Dimension:
  → Kleine, präzise Frage an lokales 7B Modell
  → Schnell, günstig, oft besser als eine große vage Frage

Orchestrator:
  → Sammelt alle Antworten
  → Synthetisiert Gesamtantwort
  → Prüft Konsistenz zwischen Dimensionen
```

**Warum das funktioniert:**
Ein 7B Modell das eine gut gestellte Einzelfrage beantwortet
schlägt oft ein 70B Modell mit einer vagen Gesamtfrage.
Und es läuft schneller auf dem Pi.

---

## Implementierungsplan

| Phase | Was | Status |
|---|---|---|
| Heute | Dokumentation (diese Datei) | ✅ |
| 14b | MemoryAgent (Nacht-Komprimierung) | 🔜 |
| 15b | BackupAgent | 🔜 |
| 15b | WatchdogAgent | 🔜 |
| 16 | BriefingAgent (Morgen-Zusammenfassung) | 🔜 |
| 17 | Proaktivitäts-Kanäle (Push, E-Mail) | 🔜 |
| 16b | Schwarm-LLM / Morphologische Zerlegung | 🔜 |
