"""Unit tests for DecisionStore and FeedbackStore."""

import pytest
from genus.storage.store import DecisionStore, FeedbackStore

DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def decision_store():
    s = DecisionStore(DB_URL)
    await s.init_db()
    yield s
    await s.close()


@pytest.fixture
async def feedback_store():
    s = FeedbackStore(DB_URL)
    await s.init_db()
    yield s
    await s.close()


class TestDecisionStore:

    @pytest.mark.asyncio
    async def test_store_and_get(self, decision_store):
        did = await decision_store.store("agent-1", "test", input_data={"x": 1})
        row = await decision_store.get(did)
        assert row is not None
        assert row.agent_id == "agent-1"

    @pytest.mark.asyncio
    async def test_list_all(self, decision_store):
        await decision_store.store("a", "t1")
        await decision_store.store("b", "t2")
        rows = await decision_store.list()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_list_filter_agent(self, decision_store):
        await decision_store.store("a", "t1")
        await decision_store.store("b", "t2")
        rows = await decision_store.list(agent_id="a")
        assert len(rows) == 1 and rows[0].agent_id == "a"

    @pytest.mark.asyncio
    async def test_list_filter_type(self, decision_store):
        await decision_store.store("a", "t1")
        await decision_store.store("a", "t2")
        rows = await decision_store.list(decision_type="t1")
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_get_missing(self, decision_store):
        row = await decision_store.get("nonexistent")
        assert row is None


class TestFeedbackStore:

    @pytest.mark.asyncio
    async def test_store_and_get(self, decision_store, feedback_store):
        did = await decision_store.store("a", "t")
        fid = await feedback_store.store(did, score=0.8, label="success")
        row = await feedback_store.get(fid)
        assert row is not None
        assert row.score == 0.8
        assert row.label == "success"

    @pytest.mark.asyncio
    async def test_invalid_score(self, decision_store, feedback_store):
        did = await decision_store.store("a", "t")
        with pytest.raises(ValueError):
            await feedback_store.store(did, score=1.5, label="success")
        with pytest.raises(ValueError):
            await feedback_store.store(did, score=-1.5, label="failure")

    @pytest.mark.asyncio
    async def test_invalid_label(self, decision_store, feedback_store):
        did = await decision_store.store("a", "t")
        with pytest.raises(ValueError):
            await feedback_store.store(did, score=0.5, label="bad")

    @pytest.mark.asyncio
    async def test_list_for_decision(self, decision_store, feedback_store):
        did = await decision_store.store("a", "t")
        await feedback_store.store(did, score=1.0, label="success")
        await feedback_store.store(did, score=-0.5, label="failure")
        rows = await feedback_store.list_for_decision(did)
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_list_all(self, decision_store, feedback_store):
        did = await decision_store.store("a", "t")
        await feedback_store.store(did, score=1.0, label="success")
        await feedback_store.store(did, score=0.0, label="neutral")
        rows = await feedback_store.list_all()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_list_all_filter_label(self, decision_store, feedback_store):
        did = await decision_store.store("a", "t")
        await feedback_store.store(did, score=1.0, label="success")
        await feedback_store.store(did, score=0.0, label="neutral")
        rows = await feedback_store.list_all(label="success")
        assert len(rows) == 1
