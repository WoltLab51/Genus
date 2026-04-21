"""Unit tests for genus/functional_agents/ (base, registry, home_agent, family_agent)."""

import pytest

from genus.functional_agents.base import AgentContext, AgentResponse, FunctionalAgent
from genus.functional_agents.registry import FunctionalAgentRegistry
from genus.functional_agents.home_agent import HomeAgent
from genus.functional_agents.family_agent import FamilyAgent
from genus.functional_agents import (
    AgentContext,
    AgentResponse,
    FunctionalAgent,
    FunctionalAgentRegistry,
    HomeAgent,
    FamilyAgent,
)


# ---------------------------------------------------------------------------
# AgentContext
# ---------------------------------------------------------------------------


class TestAgentContext:
    def test_required_fields(self):
        ctx = AgentContext(user_id="alice")
        assert ctx.user_id == "alice"

    def test_defaults(self):
        ctx = AgentContext(user_id="bob")
        assert ctx.session_id == "default"
        assert ctx.actor_id is None
        assert ctx.metadata == {}

    def test_all_fields(self):
        ctx = AgentContext(
            user_id="carol",
            session_id="sess-1",
            actor_id="device-phone",
            metadata={"lang": "de"},
        )
        assert ctx.session_id == "sess-1"
        assert ctx.actor_id == "device-phone"
        assert ctx.metadata["lang"] == "de"


# ---------------------------------------------------------------------------
# AgentResponse
# ---------------------------------------------------------------------------


class TestAgentResponse:
    def test_required_fields(self):
        r = AgentResponse(agent_id="home", text="ok")
        assert r.agent_id == "home"
        assert r.text == "ok"

    def test_defaults(self):
        r = AgentResponse(agent_id="x", text="y")
        assert r.success is True
        assert r.data is None
        assert r.metadata == {}

    def test_to_dict(self):
        r = AgentResponse(agent_id="home", text="hello", data={"k": "v"})
        d = r.to_dict()
        assert d["agent_id"] == "home"
        assert d["text"] == "hello"
        assert d["success"] is True
        assert d["data"] == {"k": "v"}
        assert "metadata" in d


# ---------------------------------------------------------------------------
# FunctionalAgentRegistry
# ---------------------------------------------------------------------------


class TestFunctionalAgentRegistry:
    def test_register_and_get(self):
        reg = FunctionalAgentRegistry()
        agent = HomeAgent()
        reg.register(agent)
        assert reg.get("home") is agent

    def test_get_missing_returns_none(self):
        reg = FunctionalAgentRegistry()
        assert reg.get("nonexistent") is None

    def test_list_all_empty(self):
        reg = FunctionalAgentRegistry()
        assert reg.list_all() == []

    def test_list_all_returns_registered(self):
        reg = FunctionalAgentRegistry()
        reg.register(HomeAgent())
        reg.register(FamilyAgent())
        ids = {a.agent_id for a in reg.list_all()}
        assert ids == {"home", "family"}

    def test_agent_ids_sorted(self):
        reg = FunctionalAgentRegistry()
        reg.register(FamilyAgent())
        reg.register(HomeAgent())
        assert reg.agent_ids() == ["family", "home"]

    def test_len(self):
        reg = FunctionalAgentRegistry()
        reg.register(HomeAgent())
        assert len(reg) == 1

    def test_contains(self):
        reg = FunctionalAgentRegistry()
        reg.register(HomeAgent())
        assert "home" in reg
        assert "unknown" not in reg

    def test_register_raises_on_empty_agent_id(self):
        class BadAgent(FunctionalAgent):
            agent_id = ""
            role = "r"
            description = "d"

            async def handle(self, intent, context):
                ...

        reg = FunctionalAgentRegistry()
        with pytest.raises(ValueError, match="agent_id"):
            reg.register(BadAgent())

    def test_duplicate_registration_overwrites(self):
        reg = FunctionalAgentRegistry()
        a1 = HomeAgent()
        a2 = HomeAgent()
        reg.register(a1)
        reg.register(a2)
        assert reg.get("home") is a2
        assert len(reg) == 1


# ---------------------------------------------------------------------------
# HomeAgent
# ---------------------------------------------------------------------------


class TestHomeAgent:
    def test_class_attributes(self):
        agent = HomeAgent()
        assert agent.agent_id == "home"
        assert agent.role == "smart_home"
        assert "Steuerung" in agent.description

    def test_status_dict(self):
        agent = HomeAgent()
        s = agent.status()
        assert s["agent_id"] == "home"
        assert s["role"] == "smart_home"
        assert s["ready"] is True
        assert "allowed_tools" in s

    async def test_handle_returns_response(self):
        agent = HomeAgent()
        ctx = AgentContext(user_id="papa")
        resp = await agent.handle("Licht an", ctx)
        assert isinstance(resp, AgentResponse)
        assert resp.agent_id == "home"
        assert resp.success is True
        assert "Licht an" in resp.text
        assert resp.data is not None

    async def test_can_handle_home_keywords(self):
        agent = HomeAgent()
        assert await agent.can_handle("Licht im Wohnzimmer einschalten") is True
        assert await agent.can_handle("Heizung auf 22 Grad") is True
        assert await agent.can_handle("Smart Home einrichten") is True

    async def test_can_handle_returns_false_for_unrelated(self):
        agent = HomeAgent()
        assert await agent.can_handle("Was ist das Wetter?") is False
        assert await agent.can_handle("Schreib einen Brief") is False

    async def test_handle_includes_user_id_in_data(self):
        agent = HomeAgent()
        ctx = AgentContext(user_id="mama", session_id="s42")
        resp = await agent.handle("Rollos schließen", ctx)
        assert resp.data["user_id"] == "mama"
        assert resp.data["session_id"] == "s42"


# ---------------------------------------------------------------------------
# FamilyAgent
# ---------------------------------------------------------------------------


class TestFamilyAgent:
    def test_class_attributes(self):
        agent = FamilyAgent()
        assert agent.agent_id == "family"
        assert agent.role == "family_management"
        assert "Management" in agent.description

    def test_status_dict(self):
        agent = FamilyAgent()
        s = agent.status()
        assert s["agent_id"] == "family"
        assert s["required_scope"] == "family"

    async def test_handle_returns_response(self):
        agent = FamilyAgent()
        ctx = AgentContext(user_id="mama")
        resp = await agent.handle("Termin morgen 14 Uhr beim Arzt", ctx)
        assert isinstance(resp, AgentResponse)
        assert resp.agent_id == "family"
        assert resp.success is True

    async def test_can_handle_family_keywords(self):
        agent = FamilyAgent()
        assert await agent.can_handle("Termin beim Arzt eintragen") is True
        assert await agent.can_handle("Aufgabe: Einkaufen") is True
        assert await agent.can_handle("Erinnerung für Kind") is True

    async def test_can_handle_returns_false_for_unrelated(self):
        agent = FamilyAgent()
        assert await agent.can_handle("Licht einschalten") is False
        assert await agent.can_handle("Code generieren") is False

    async def test_handle_includes_intent_in_data(self):
        agent = FamilyAgent()
        ctx = AgentContext(user_id="papa")
        resp = await agent.handle("Einkaufsliste erstellen", ctx)
        assert resp.data["intent"] == "Einkaufsliste erstellen"
        assert resp.data["user_id"] == "papa"
