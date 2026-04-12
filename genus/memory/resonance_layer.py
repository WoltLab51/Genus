"""
ResonanceLayer — Phase 15a

Baut den Memory-Kontext-Block der bei JEDER LLM-Anfrage injiziert wird.
Kein Keyword-Matching. Kein expliziter Trigger.

Das LLM bekommt immer:
- Die letzten N Episodes des Users (komprimierte Wochenerinnerungen)
- Alle SemanticFacts des Users (permanente Fakten)
- Die aktuelle InnerMonologue-Note (wenn vorhanden)

Das LLM entscheidet selbst ob und wie es diese Information einbringt.

Design:
- Graceful degradation: wenn EpisodeStore/FactStore nicht verfügbar → leerer Block
- Token-budget aware: episodes werden gekürzt wenn zu viele
- Kein externes Dependency
- Synchron (keine async) — nur Lese-Operationen auf lokalen JSONL-Dateien
"""

from __future__ import annotations

from typing import Optional

from genus.memory.episode_store import EpisodeStore
from genus.memory.fact_store import SemanticFactStore
from genus.memory.inner_monologue import InnerMonologue


_MAX_EPISODE_SUMMARY_CHARS = 300  # pro Episode im Kontext
_RESONANCE_HEADER = "=== GENUS Gedächtnis ==="


def build_resonance_block(
    user_id: str,
    *,
    episode_store: Optional[EpisodeStore] = None,
    fact_store: Optional[SemanticFactStore] = None,
    inner_monologue: Optional[InnerMonologue] = None,
    max_episodes: int = 3,
) -> str:
    """Baut den Memory-Kontext-Block für den LLM-Prompt.

    Args:
        user_id:         Der User für den der Kontext gebaut wird.
        episode_store:   Optional. Wenn None → keine Episodes.
        fact_store:      Optional. Wenn None → keine Facts.
        inner_monologue: Optional. Wenn None → keine innere Notiz.
        max_episodes:    Maximale Anzahl Episodes im Block. Default: 3.

    Returns:
        Formatierter Kontext-Block als String.
        Leerer String wenn keine Daten vorhanden.
    """
    from datetime import datetime

    parts: list[str] = []

    # ── Episodes ─────────────────────────────────────────────────────────────
    if episode_store is not None:
        try:
            episodes = episode_store.get_recent(user_id, limit=max_episodes)
            if episodes:
                ep_lines = []
                for ep in reversed(episodes):  # älteste zuerst
                    summary = ep.summary[:_MAX_EPISODE_SUMMARY_CHARS]
                    if len(ep.summary) > _MAX_EPISODE_SUMMARY_CHARS:
                        summary += "..."
                    # created_at is stored as ISO string in Episode
                    try:
                        created_at = datetime.fromisoformat(ep.created_at)
                        date_str = created_at.strftime("%d.%m.%Y")
                    except (ValueError, TypeError):
                        date_str = str(ep.created_at)[:10]
                    topics_str = (
                        f" [{', '.join(ep.topics[:3])}]" if ep.topics else ""
                    )
                    ep_lines.append(f"• {date_str}{topics_str}: {summary}")
                parts.append("Erinnerungen:\n" + "\n".join(ep_lines))
        except Exception:  # noqa: BLE001
            pass  # graceful degradation

    # ── SemanticFacts ─────────────────────────────────────────────────────────
    if fact_store is not None:
        try:
            facts = fact_store.get_all(user_id)
            if facts:
                fact_lines = [
                    f"• {f.key}: {f.value}"
                    for f in facts.values()
                    if f.value
                ]
                if fact_lines:
                    parts.append("Bekannte Fakten:\n" + "\n".join(fact_lines))
        except Exception:  # noqa: BLE001
            pass

    # ── InnerMonologue ────────────────────────────────────────────────────────
    if inner_monologue is not None:
        try:
            note = inner_monologue.get_current(user_id)
            if note:
                parts.append(f"Innere Notiz: {note}")
        except Exception:  # noqa: BLE001
            pass

    if not parts:
        return ""

    return _RESONANCE_HEADER + "\n" + "\n\n".join(parts)
