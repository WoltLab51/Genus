# GENUS Deployment-Modes

> *GENUS bootet und fragt sich zuerst: "Wo bin ich? Was habe ich? Was kann ich hier?"*

---

## Das Prinzip: Situations-Awareness

GENUS passt sich seiner Umgebung an — automatisch.
Keine manuelle Konfiguration für jeden Startmodus.
GENUS erkennt wo es läuft und wählt den passenden Modus.

---

## Die vier Deployment-Szenarien

### Modus 1: Pi — Always-On zuhause
```
Hardware:    Raspberry Pi 5, 8GB RAM
LLM:         Ollama llama3.2 (3B, schnell, Pi-optimiert)
Verfügbar:   24/7, niedriger Verbrauch
Stärken:     Monitoring, Notifications, Hintergrund-Denken,
             Gedächtnis-Verwaltung, Backup
Grenzen:     Langsam bei komplexen Aufgaben,
             kleine Modelle, wenig RAM

Automatische Anpassungen:
  - Kompakte LLM-Antworten (max_tokens reduziert)
  - Kein paralleles Bauen mehrerer Agents
  - Hintergrund-Jobs nachts (02:00-05:00 Uhr)
  - Aggressive Kontext-Komprimierung
```

### Modus 2: X1 — Volle Kraft zuhause
```
Hardware:    ThinkPad X1 Carbon, 16GB+ RAM
LLM:         Ollama llama3.3 70B oder Mistral Large
Verfügbar:   Wenn eingeschaltet
Stärken:     Komplexe DevLoop-Runs, große Modelle,
             schnelle Antworten, parallele Aufgaben
Grenzen:     Nicht always-on, höherer Verbrauch

Automatische Anpassungen:
  - Größere LLM-Modelle bevorzugt
  - Parallele Runs erlaubt
  - Volle Kontext-Fenster
  - Komplexe Analysen und Recherchen
```

### Modus 3: Fernzugriff — Unterwegs auf Pi
```
Verbindung:  Tunnel (Tailscale/WireGuard) oder direkter Port
Client:      Handy oder Laptop von unterwegs
LLM:         Pi's Ollama (mit Latenz)
Verfügbar:   Wenn Pi online und Tunnel aktiv

Automatische Anpassungen:
  - Noch kompaktere Antworten (Bandbreite schonen)
  - Kein Streaming (Verbindung zu instabil)
  - Längere Timeouts
  - "Pi ist ausgelastet" — ehrlich kommunizieren
```

### Modus 4: Cloud-Fallback
```
Trigger:     Lokales LLM zu langsam / nicht verfügbar
             Komplexe Aufgabe übersteigt lokale Kapazität
LLM:         OpenAI GPT-4o oder Anthropic Claude
Kosten:      Bewusst eingesetzt, nicht Standard

Automatische Anpassungen:
  - Nur aktiviert wenn GENUS_LLM_OPENAI_KEY gesetzt
  - LLMRouter wählt automatisch (Score-basiert)
  - Kosten-Logging
  - User wird informiert wenn Cloud genutzt wird
```

---

## Wie GENUS seinen Modus erkennt

```python
class DeploymentDetector:
    """GENUS erkennt beim Start wo es läuft."""

    def detect(self) -> DeploymentMode:
        hardware = self._detect_hardware()
        # Raspberry Pi: /proc/cpuinfo enthält "Raspberry Pi"
        # ThinkPad: DMI-Daten oder Hostname

        network = self._detect_network()
        # Lokaler Zugriff: Client-IP ist LAN
        # Fernzugriff: Client-IP ist extern / VPN

        resources = self._detect_resources()
        # RAM, CPU-Kerne, verfügbarer Speicher

        llm = self._detect_llm_availability()
        # Ollama erreichbar? Welches Modell? Wie schnell?

        return DeploymentMode(
            hardware=hardware,
            network=network,
            resources=resources,
            llm=llm,
        )
```

---

## Umgebungsvariablen pro Modus

Statt alles manuell zu setzen: `genus.config.yaml` mit Profilen:

```yaml
# genus.config.yaml
profiles:
  pi:
    llm_model: "llama3.2"
    max_tokens: 256
    parallel_runs: 1
    background_jobs: true
    backup_enabled: true

  x1:
    llm_model: "llama3.3:70b"
    max_tokens: 2048
    parallel_runs: 3
    background_jobs: false

  remote:
    llm_model: "llama3.2"
    max_tokens: 128
    streaming: false
    timeout_multiplier: 3.0

active_profile: auto  # GENUS erkennt selbst
```

---

## Backup-Strategie

```
Strategie: 3-2-1

3 Kopien:
  1. Live:       var/ auf dem Pi (immer aktuell)
  2. Lokal:      USB-Stick oder externe SSD (täglich)
  3. Remote:     NAS, zweiter Pi, oder Cloud (wöchentlich)

2 verschiedene Medien:
  Pi-SSD + USB ← physisch getrennt

1 externer Ort:
  Mindestens eine Kopie nicht am gleichen Ort

Rotation:
  Täglich:    letzte 7 Tage
  Wöchentlich: letzte 4 Wochen
  Monatlich:  letzte 12 Monate
  Älter:      weg (außer explizit markiert)

Format: ZIP mit Timestamp
  genus_backup_2026-04-11_0200.zip
    var/conversations/
    var/runs/
    var/events/
    var/needs/
    var/strategy/
    genus.config.yaml
```

---

## Implementierungsplan

| Phase | Was | Status |
|---|---|---|
| Heute | Dokumentation (diese Datei) | ✅ |
| 15 | DeploymentDetector | 🔜 |
| 15 | genus.config.yaml Support | 🔜 |
| 15b | BackupAgent (ZIP + Rotation) | 🔜 |
| 15b | Restore-Prozess | 🔜 |
