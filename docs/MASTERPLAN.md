GENUS - Masterplan
Stand: 2026-04-24 | Sprache: Deutsch

1. Zielbild
GENUS ist vollendet, wenn es nicht mehr nur ein ambitioniertes System ist, sondern ein verlasslicher personlicher digitaler Begleiter mit drei stabilen Ebenen:

Kommunikation: GENUS kann sprechen, zuhoren, erinnern und im Kontext handeln.
Handlung: GENUS kann Aufgaben planen, ausfuhren, prufen, dokumentieren und weiterverfolgen.
Betrieb: GENUS ist sicher, nachvollziehbar, erweiterbar und uber langere Zeit stabil betreibbar.
Im Endzustand ist GENUS kein reines Chat-System und kein loses Agenten-Experiment mehr, sondern ein personliches Betriebssystem fur Wissen, Alltag, Entwicklung und Familienkontext.

2. Was GENUS dann kann
Kernfahigkeiten
Naturliche Gesprache mit Kurzzeit- und Langzeitkontext fuhren
Personen, Rollen, Familienkontext und private Bereiche sauber unterscheiden
Aufgaben annehmen, strukturieren, ausfuhren, prufen und mit Run-Historie dokumentieren
Recherchieren, Quellen zusammenfassen und neues Wissen mit bestehendem Kontext verknupfen
Proaktiv reagieren: erinnern, briefen, warnen, priorisieren und verdichten
Auf lokaler Hardware laufen und Aufgaben intelligent zwischen Pi, starkerer Maschine und optionaler Cloud verteilen
Neue Fahigkeiten kontrolliert nachladen, ohne die Grundstabilitat zu gefahrden
Spezifische Nutzungsmodi
Personlicher Assistent: Termine, Erinnerungen, Briefings, Nachverfolgung
Familien-Gedachtnis: gemeinsame Informationen, Profile, Gewohnheiten, Schutz privater Raume
Developer-Assistent: planen, bauen, testen, reviewen, dokumentieren
Knowledge-System: recherchieren, verdichten, historisieren, verknupfen
Home-Knoten: Zustande beobachten, melden, bewerten
DnD-Master: Kampagnen, NPCs, Verlauf, Weltenwissen
3. Produktstrategie
GENUS sollte nicht feature-first, sondern in klaren Reifestufen gebaut werden:

Erst die Plattform stabilisieren
Dann ein echtes Kernprodukt fertigstellen
Danach den personlichen Alltag und Familienkontext aufbauen
Erst anschliessend Wachstum, Spezialagenten und komplexe Selbst-Erweiterung vertiefen
Leitentscheidung
GENUS wird zuerst eine stabile personliche Assistenz mit harter Plattformbasis und erst danach eine allgemeine Agentenplattform.

Warum:

Das schafft fruher echten Nutzen
Es halt den Scope kontrollierbar
Es verhindert Architektur ohne Alltagstauglichkeit
Es macht spatere Spezialisierung robuster
4. Phasenplan
Phase 1 - Plattform harten
Ziel
GENUS startet reproduzierbar, lauft stabil, fallt kontrolliert aus und ist technisch nachvollziehbar.

Schwerpunkte
Lifespan, Startup und Shutdown vereinfachen
Konfiguration vereinheitlichen und dokumentieren
Modulgrenzen scharfen
Logging, Fehlermeldungen und Zustandsdiagnostik verbessern
Sicherheitsmodell durchgangig verdrahten
Testfundament fur Kernmodule, API und Integrationen ausbauen
Lokalen Betrieb und Deployment sauber reproduzierbar machen
Meilensteine
Ein klarer Startpfad fur API und Hintergrundkomponenten
Ein einheitliches Konfigurationsmodell fur lokale und produktive Nutzung
Vollstandige Run-Nachvollziehbarkeit fur Kernablaufe
Sicherheitskritische Pfade mit Rollen, Kill-Switch und Guards abgesichert
Kernmodule mit belastbaren Unit- und Integrationstests abgedeckt
Definition of Done
GENUS startet mit dokumentierter Konfiguration ohne manuelle Sondergriffe
Kritische Komponenten besitzen Health- und Fehlerdiagnostik
Kernpfade sind automatisiert testbar
Ein Fehler in Teilkomponenten zieht nicht unkontrolliert das Gesamtsystem mit
Die Betriebsdokumentation reicht aus, um GENUS auf einer Zielmaschine reproduzierbar hochzufahren
Phase 2 - Kernprodukt fertig machen
Ziel
GENUS ist als taglich nutzbarer personlicher Assistent verwendbar.

Schwerpunkte
Chat als primare Oberflache fertigstellen
Session- und Dialogmanagement verlasslich machen
REST- und WebSocket-Pfade konsistent halten
Run-Status, Antworten und Ergebnisdarstellung fur Nutzer lesbar machen
Erste echte End-to-End-Flows abschliessen: fragen, planen, handeln, antworten
Meilensteine
Stabile Chat-Sitzungen mit sauberem Verbindungs- und Fallback-Verhalten
Einheitlicher Antwortpfad fur Konversation, Tool-Nutzung und Task-Runs
Nutzbare Oberflache fur Desktop und Handy
Nachvollziehbare Run-Ansicht fur langere Aktionen
Definition of Done
Ein Nutzer kann GENUS taglich uber Chat nutzen
Antworten sind kontextstabil und fur den Nutzer nachvollziehbar
Verbindungsabbruche oder API-Fehler fuhren nicht zu unklaren Zustanden
Einfache Alltags- und Wissensanfragen funktionieren Ende-zu-Ende
Phase 3 - Memory und Wissen verankern
Ziel
GENUS merkt sich Relevantes verlasslich und kann Wissen sinnvoll wiederverwenden.

Schwerpunkte
Episodisches Gedachtnis, Faktenwissen und Gesprachskontext sauber trennen
Verdichtung, Kompression und spateres Wiederfinden verbessern
Wissensquellen, Rechercheergebnisse und personliche Informationen verknupfen
Konflikte zwischen neuem und altem Wissen sichtbar behandeln
Meilensteine
Stabiler Speicher fur Gesprachsepisoden
Persistenter Faktenstore fur belastbare Aussagen
Kontextaufbau fur Antworten aus Verlauf, Profilen und Wissen
Qualitatsregeln fur Gedachtnis: Relevanz, Sichtbarkeit, Korrigierbarkeit
Definition of Done
GENUS kann sich uber langere Zeitraume an relevante Dinge erinnern
Nutzer konnen wichtige Informationen wiederfinden und korrigieren
Wissenskonflikte verschwinden nicht still im Hintergrund
Recherchiertes Wissen ist vom personlichen Gedachtnis unterscheidbar
Phase 4 - Task Engine und DevLoop produktiv machen
Ziel
GENUS kann komplexere Aufgaben kontrolliert abarbeiten statt nur zu antworten.

Schwerpunkte
Planner, Builder, Tester, Reviewer und Orchestrierung stabilisieren
Aufgaben in strukturierte Runs ubersetzen
Ergebnisse, Risiken und offene Fragen klar zuruckmelden
Workspace-, Tool- und Sandbox-Verhalten absichern
Git-, Build- und Testablaufe verlasslich in das System einbinden
Meilensteine
Verlasslicher Plan -> Implement -> Test -> Review-Flow
Run-Journaling mit verstandlichen Zwischenschritten und Ergebnissen
Klare Eskalationslogik bei Unsicherheit, Fehlern oder Sicherheitsrisiken
Reproduzierbare Tool-Ausfuhrung im kontrollierten Rahmen
Definition of Done
GENUS kann klar umrissene Aufgaben eigenstandig ausfuhren
Jeder Task-Run ist nachvollziehbar und auswertbar
Fehler, Timeouts und Review-Bedenken fuhren zu kontrollierter Eskalation
Die Aufgabe endet entweder mit Ergebnis, Ruckfrage oder sauberem Abbruch
Phase 5 - Identitat, Familie und Privatsphare abschliessen
Ziel
GENUS versteht, fur wen es arbeitet, was geteilt werden darf und was privat bleiben muss.

Schwerpunkte
Actor-, Rollen- und Familienmodell vervollstandigen
Personliche Profile und gemeinsame Familienbereiche trennen
Privacy-Vault und Berechtigungspfade ausbauen
Onboarding fur neue Personen und Gerate vereinfachen
Meilensteine
Vollstandige Zuordnung von API-Zugriffen zu Personen oder Geraten
Trennung zwischen privat, geteilt und systemweit
Sichtbare Berechtigungsregeln fur Daten und Fahigkeiten
Nutzbares Onboarding fur Familienmitglieder
Definition of Done
GENUS weiss, wer gerade mit ihm spricht
Private und gemeinsame Informationen werden nicht vermischt
Berechtigungen sind technisch und im Verhalten durchgesetzt
Neue Nutzer konnen ohne Entwicklerwissen aufgenommen werden
Phase 6 - Proaktivitat und Alltagsbetrieb
Ziel
GENUS handelt nicht nur auf Anfrage, sondern begleitet den Alltag sinnvoll.

Schwerpunkte
Briefings, Erinnerungen, Watchdogs und Hintergrundprozesse einbauen
Prioritaten, Dringlichkeit und Benachrichtigungskanale definieren
Tageskontext, Routinen und wiederkehrende Aufgaben modellieren
Home- und Systemzustand als Signale integrieren
Meilensteine
Morgen- oder Tagesbriefing
Hintergrunduberwachung fur Dienste, Ressourcen und wichtige Zustande
Erinnerungs- und Hinweislogik mit Dringlichkeitsstufen
Erste Home- und Gerateintegration
Definition of Done
GENUS liefert sinnvolle proaktive Hinweise mit erkennbarer Prioritat
Hintergrunddienste laufen stabil und transparent
Nutzer erleben Mehrwert auch ohne aktive Chat-Anfrage
Phase 7 - Multi-Hardware und Spezialisierung
Ziel
GENUS verteilt Last intelligent und bekommt tiefere Spezialfahigkeiten.

Schwerpunkte
Pi, starkere Workstation und optionaler Cloud-Fallback koordinieren
Modellrouting je nach Kosten, Geschwindigkeit und Qualitat verbessern
Spezialagenten fur Home, DnD, Developer-Workflows und Recherche vertiefen
Wachstum und Capability-Modell kontrolliert ausbauen
Meilensteine
Hardware-Routing fur unterschiedliche Aufgabenklassen
Sichtbarer Provider- und Modellentscheid pro Task
Produktive Spezialmodi mit echten Nutzerflussen
Selbstmodell fur Grenzen, Starken und Ausbaupfade
Definition of Done
GENUS kann Aufgaben passend auf verfugbare Systeme verteilen
Spezialisierte Fahigkeiten sind echte Produkte, keine Demos
Wachstum und Erweiterung bleiben kontrollierbar und auditierbar
5. Releases
V1 - Personlicher Kernassistent
Stabiler Chat
Grundlegendes Memory
Recherche
Einfache Task-Runs
Solider lokaler Betrieb
V2 - Familien- und Alltagsbetrieb
Familienprofile
Rollen und Privatsphare
Briefings und Proaktivitat
Home- und Systemkontext
V3 - Vollwertige Agentenplattform
Multi-Hardware-Orchestrierung
Spezialagenten
Kontrolliertes Wachstum
Erweitertes Self-Model
6. Definition von "vollendet"
GENUS ist aus Projektsicht vollendet, wenn folgende Bedingungen gleichzeitig erfullt sind:

Es ist taglich uber Chat nutzbar
Es erinnert sich verlasslich und korrigierbar
Es kann Wissen recherchieren, speichern und in Kontext bringen
Es kann Aufgaben Ende-zu-Ende ausfuhren und dokumentieren
Es kennt Personen, Rollen und Privatspharen
Es begleitet proaktiv den Alltag
Es lauft uber langere Zeitraume stabil
Es ist sicher genug fur personliche Nutzung
Neue Fahigkeiten konnen erganzt werden, ohne das System neu zu erfinden
7. Nachste konkrete Schritte
Die nachsten praktischen Schritte sollten sein:

Ein belastbares Ziel fur V1 verbindlich festschreiben
Alle bereits vorhandenen Module auf dieses V1-Ziel ausrichten
Alles pausieren, was nicht direkt auf V1 einzahlt
Fur jede Phase die offenen Architektur-, Produkt- und Betriebsrisiken dokumentieren
Einen operativen Backlog mit priorisierten Meilensteinen aus diesem Masterplan ableiten
