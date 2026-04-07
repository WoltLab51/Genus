"""
Unit tests for GENUS Role Model (P2)

Covers:
- Role enum: READER, OPERATOR, ADMIN exist
- topics_for_role(Role.READER) returns frozenset (may be empty)
- topics_for_role(Role.OPERATOR) contains run.started, outcome.recorded, data.collected
- topics_for_role(Role.ADMIN) is superset of OPERATOR
- ADMIN contains system.kill_switch.activated, system.acl.updated
- all_roles() returns all three roles
- build_policy_from_roles: OPERATOR actor can publish on run.started
- build_policy_from_roles: READER actor cannot publish on run.started
- build_policy_from_roles: ADMIN actor can publish on system.kill_switch.activated
- build_policy_from_roles: empty assignments → empty policy
- build_policy_from_roles: multiple actors with different roles
- default_pipeline_policy: DataCollectorAgent can publish data.collected
- default_pipeline_policy: AnalysisAgent cannot publish data.collected
- default_pipeline_policy: EventRecorderAgent cannot publish anything
"""

import pytest

from genus.security.roles import Role, topics_for_role, all_roles
from genus.security.role_acl import build_policy_from_roles
from genus.security.acl_presets import default_pipeline_policy


# ---------------------------------------------------------------------------
# Role enum
# ---------------------------------------------------------------------------

def test_role_enum_members_exist():
    assert Role.READER is not None
    assert Role.OPERATOR is not None
    assert Role.ADMIN is not None


# ---------------------------------------------------------------------------
# topics_for_role
# ---------------------------------------------------------------------------

def test_reader_topics_is_frozenset():
    result = topics_for_role(Role.READER)
    assert isinstance(result, frozenset)


def test_reader_topics_may_be_empty():
    # READER has no publish permissions by design
    result = topics_for_role(Role.READER)
    assert len(result) == 0


def test_operator_contains_run_started():
    assert "run.started" in topics_for_role(Role.OPERATOR)


def test_operator_contains_outcome_recorded():
    assert "outcome.recorded" in topics_for_role(Role.OPERATOR)


def test_operator_contains_data_collected():
    assert "data.collected" in topics_for_role(Role.OPERATOR)


def test_admin_is_superset_of_operator():
    operator_topics = topics_for_role(Role.OPERATOR)
    admin_topics = topics_for_role(Role.ADMIN)
    assert operator_topics.issubset(admin_topics)


def test_admin_contains_kill_switch_activated():
    assert "system.kill_switch.activated" in topics_for_role(Role.ADMIN)


def test_admin_contains_acl_updated():
    assert "system.acl.updated" in topics_for_role(Role.ADMIN)


# ---------------------------------------------------------------------------
# all_roles
# ---------------------------------------------------------------------------

def test_all_roles_returns_all_three():
    roles = all_roles()
    assert Role.READER in roles
    assert Role.OPERATOR in roles
    assert Role.ADMIN in roles


def test_all_roles_order():
    roles = all_roles()
    assert roles == (Role.READER, Role.OPERATOR, Role.ADMIN)


# ---------------------------------------------------------------------------
# build_policy_from_roles
# ---------------------------------------------------------------------------

def test_operator_can_publish_run_started():
    policy = build_policy_from_roles({"agent-1": Role.OPERATOR})
    assert policy.is_allowed("agent-1", "run.started")


def test_reader_cannot_publish_run_started():
    policy = build_policy_from_roles({"agent-2": Role.READER})
    assert not policy.is_allowed("agent-2", "run.started")


def test_admin_can_publish_kill_switch_activated():
    policy = build_policy_from_roles({"admin-1": Role.ADMIN})
    assert policy.is_allowed("admin-1", "system.kill_switch.activated")


def test_empty_assignments_empty_policy():
    policy = build_policy_from_roles({})
    assert not policy.is_allowed("anyone", "run.started")


def test_multiple_actors_different_roles():
    policy = build_policy_from_roles({
        "op": Role.OPERATOR,
        "rd": Role.READER,
        "adm": Role.ADMIN,
    })
    assert policy.is_allowed("op", "run.started")
    assert not policy.is_allowed("rd", "run.started")
    assert policy.is_allowed("adm", "system.acl.updated")
    # cross-check: op cannot trigger kill switch
    assert not policy.is_allowed("op", "system.kill_switch.activated")


# ---------------------------------------------------------------------------
# default_pipeline_policy
# ---------------------------------------------------------------------------

def test_pipeline_data_collector_can_publish_data_collected():
    policy = default_pipeline_policy()
    assert policy.is_allowed("DataCollectorAgent", "data.collected")


def test_pipeline_analysis_agent_cannot_publish_data_collected():
    policy = default_pipeline_policy()
    assert not policy.is_allowed("AnalysisAgent", "data.collected")


def test_pipeline_event_recorder_cannot_publish_anything():
    policy = default_pipeline_policy()
    # EventRecorderAgent is deliberately excluded from all grants
    assert not policy.is_allowed("EventRecorderAgent", "data.collected")
    assert not policy.is_allowed("EventRecorderAgent", "analysis.completed")
    assert not policy.is_allowed("EventRecorderAgent", "feedback.received")
