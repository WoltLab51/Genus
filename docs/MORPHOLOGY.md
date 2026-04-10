# GENUS Morphologie

## Einleitung

Morphologie beschreibt nicht *was* GENUS tut, sondern *wie es gebaut ist* — die Körperform des Systems. Die Schichtenordnung verhindert unkontrolliertes Wachstum, indem sie klare Grenzen zwischen stabilen Kern-Teilen und dynamisch wachsenden Teilen zieht. Ein Modul, das seine eigene Schicht kennt, kann sich selbst einordnen und entscheiden, welche anderen Module es importieren darf. Diese Struktur macht GENUS langzeitstabil: Veränderungen finden immer nur in den richtigen Schichten statt.

---

## Die 3 Schichten

### KERN-Schicht (`layer: "kernel"`)

- **Beschreibung:** Unveränderlich, nie dynamisch ersetzt, kein Import von höheren Schichten erlaubt
- **Module:** `core`, `communication`, `security`, `memory`, `config`, `sandbox`, `safety`
- **Regel:** Kern-Module dürfen nur andere Kern-Module importieren

### FÄHIGKEITS-Schicht (`layer: "capability"`)

- **Beschreibung:** Stabil, erweiterbar, kann Kern-Module importieren
- **Module:** `orchestration`, `dev`, `strategy`, `meta`, `quality`, `feedback`, `tools`, `run`
- **Regel:** Kann Kern importieren, darf **nicht** Wachstums-Module importieren

### WACHSTUMS-Schicht (`layer: "growth"`)

- **Beschreibung:** Dynamisch, wird teilweise von GENUS selbst gebaut, kann alle anderen importieren
- **Module:** `growth`, `agents`, `workspace`, `github`, `api`, `cli`, `utils`
- **Regel:** Kann alle Schichten importieren

---

## Domains

| Domain | Beschreibung |
|---|---|
| `system` | Interne Systemfunktionen |
| `family` | Familienorganisation, Kalender, Ole-Tagebuch |
| `home` | Heimnetz, Geräte, Pi5-Management |
| `trading` | Trading-App Monry, Strategien, Marktdaten |
| `security_compliance` | Internetsicherheit für die Familie |
| `communication` | Nachrichten, Benachrichtigungen zwischen Agenten |

---

## Geräte-Rollen (Device Morphology)

- **Pi5** — Kern-Schicht läuft hier: immer online, das Gehirn
- **Laptop** — Fähigkeits-Schicht: mobil, manchmal offline, die Hände
- **Handy** — nur Konsument: schwach, sporadisch verbunden, die Sinnesorgane

---

## Import-Regel

```
Von \ Nach  | Kern | Fähigkeit | Wachstum
------------|------|-----------|----------
Kern        |  ✅  |    ❌     |    ❌
Fähigkeit   |  ✅  |    ✅     |    ❌
Wachstum    |  ✅  |    ✅     |    ✅
```

---

## Wachstumsregeln

- Kein neuer Agent ohne mind. 2 Trigger-Beobachtungen
- Kein Build wenn `security_compliance < 0.90` (Wert aus `QualityGate`, Dimension `security_compliance`)
- 24h Wartezeit bevor ein Agent ersetzt werden darf
- 12h Cooldown pro (domain, need) nach einem Build
- Max. 2 neue Agenten pro Tag (Limit aus IdentityProfile)

---

## Was noch kommt (ehrlicher Ausblick)

- `DeviceRegistry` — GENUS weiß welche Komponenten wo laufen
- `MorphologyEngine` — systematische Variantenexploration
- Automatischer Import-Schichten-Test in CI
