"""
Tests for genus.growth.agent_spec

Verifies:
- AgentSpec can be instantiated with minimal arguments
- created_at is set automatically when empty
- max_instances < 1 raises ValueError
- KERNEL + replaceable=True raises ValueError
- CAPABILITY + replaceable=True does not raise
- is_kernel_safe() returns True for KERNEL agents (replaceable=False)
- is_kernel_safe() returns False for CAPABILITY agents
- morphology_tags accepts free key-value pairs
- AgentDomain has all 6 domains
- AgentLayer has all 3 layers
- status defaults to "planned"
"""

import pytest

from genus.growth.agent_spec import (
    AgentDomain,
    AgentLayer,
    AgentMorphology,
    AgentSpec,
)


def _make_morphology(
    layer: AgentLayer = AgentLayer.GROWTH,
    domain: AgentDomain = AgentDomain.SYSTEM,
    replaceable: bool = True,
    max_instances: int = 1,
) -> AgentMorphology:
    return AgentMorphology(
        layer=layer,
        domain=domain,
        replaceable=replaceable,
        max_instances=max_instances,
    )


def _make_spec(**kwargs) -> AgentSpec:
    defaults = dict(
        name="TestAgent",
        description="A test agent",
        morphology=_make_morphology(),
    )
    defaults.update(kwargs)
    return AgentSpec(**defaults)


class TestAgentLayer:
    def test_has_kernel(self):
        assert AgentLayer.KERNEL.value == "kernel"

    def test_has_capability(self):
        assert AgentLayer.CAPABILITY.value == "capability"

    def test_has_growth(self):
        assert AgentLayer.GROWTH.value == "growth"

    def test_exactly_three_layers(self):
        assert len(AgentLayer) == 3


class TestAgentDomain:
    def test_has_system(self):
        assert AgentDomain.SYSTEM.value == "system"

    def test_has_family(self):
        assert AgentDomain.FAMILY.value == "family"

    def test_has_home(self):
        assert AgentDomain.HOME.value == "home"

    def test_has_trading(self):
        assert AgentDomain.TRADING.value == "trading"

    def test_has_security(self):
        assert AgentDomain.SECURITY.value == "security"

    def test_has_communication(self):
        assert AgentDomain.COMMUNICATION.value == "communication"

    def test_exactly_six_domains(self):
        assert len(AgentDomain) == 6


class TestAgentSpecInstantiation:
    def test_minimal_instantiation(self):
        """AgentSpec can be created with only the required fields."""
        spec = _make_spec()
        assert spec.name == "TestAgent"
        assert spec.description == "A test agent"
        assert isinstance(spec.morphology, AgentMorphology)

    def test_status_defaults_to_planned(self):
        spec = _make_spec()
        assert spec.status == "planned"

    def test_version_defaults_to_one(self):
        spec = _make_spec()
        assert spec.version == 1

    def test_morphology_tags_defaults_to_empty_dict(self):
        spec = _make_spec()
        assert spec.morphology_tags == {}

    def test_depends_on_defaults_to_empty_list(self):
        spec = _make_spec()
        assert spec.morphology.depends_on == []


class TestCreatedAt:
    def test_created_at_set_automatically(self):
        """created_at must be populated with a non-empty string after init."""
        spec = _make_spec()
        assert spec.created_at != ""

    def test_created_at_is_iso8601(self):
        """created_at must be a valid ISO 8601 timestamp."""
        from datetime import datetime, timezone

        spec = _make_spec()
        # Should parse without error
        dt = datetime.fromisoformat(spec.created_at)
        assert dt.tzinfo is not None

    def test_created_at_not_overwritten_when_provided(self):
        """If created_at is already set, it must not be overwritten."""
        fixed_ts = "2025-01-01T00:00:00+00:00"
        spec = _make_spec(created_at=fixed_ts)
        assert spec.created_at == fixed_ts


class TestMaxInstancesValidation:
    def test_max_instances_zero_raises(self):
        morphology = _make_morphology(max_instances=0)
        with pytest.raises(ValueError, match="max_instances"):
            AgentSpec(name="X", description="y", morphology=morphology)

    def test_max_instances_negative_raises(self):
        morphology = _make_morphology(max_instances=-1)
        with pytest.raises(ValueError, match="max_instances"):
            AgentSpec(name="X", description="y", morphology=morphology)

    def test_max_instances_one_is_valid(self):
        spec = _make_spec(morphology=_make_morphology(max_instances=1))
        assert spec.morphology.max_instances == 1

    def test_max_instances_greater_than_one_is_valid(self):
        spec = _make_spec(morphology=_make_morphology(max_instances=5))
        assert spec.morphology.max_instances == 5


class TestKernelReplaceableConstraint:
    def test_kernel_replaceable_true_raises(self):
        """KERNEL + replaceable=True must raise ValueError."""
        morphology = _make_morphology(
            layer=AgentLayer.KERNEL, replaceable=True
        )
        with pytest.raises(ValueError, match="[Kk]ernel"):
            AgentSpec(name="KernelAgent", description="x", morphology=morphology)

    def test_kernel_replaceable_false_is_valid(self):
        """KERNEL + replaceable=False must not raise."""
        morphology = _make_morphology(
            layer=AgentLayer.KERNEL, replaceable=False
        )
        spec = AgentSpec(name="KernelAgent", description="x", morphology=morphology)
        assert spec.morphology.layer == AgentLayer.KERNEL

    def test_capability_replaceable_true_is_valid(self):
        """CAPABILITY + replaceable=True must not raise."""
        morphology = _make_morphology(
            layer=AgentLayer.CAPABILITY, replaceable=True
        )
        spec = AgentSpec(name="CapAgent", description="x", morphology=morphology)
        assert spec.morphology.replaceable is True

    def test_growth_replaceable_true_is_valid(self):
        """GROWTH + replaceable=True must not raise."""
        spec = _make_spec(
            morphology=_make_morphology(layer=AgentLayer.GROWTH, replaceable=True)
        )
        assert spec.morphology.replaceable is True


class TestIsKernelSafe:
    def test_kernel_not_replaceable_returns_true(self):
        morphology = _make_morphology(
            layer=AgentLayer.KERNEL, replaceable=False
        )
        spec = AgentSpec(name="KernelAgent", description="x", morphology=morphology)
        assert spec.is_kernel_safe() is True

    def test_capability_returns_false(self):
        spec = _make_spec(
            morphology=_make_morphology(layer=AgentLayer.CAPABILITY, replaceable=False)
        )
        assert spec.is_kernel_safe() is False

    def test_growth_returns_false(self):
        spec = _make_spec(
            morphology=_make_morphology(layer=AgentLayer.GROWTH, replaceable=True)
        )
        assert spec.is_kernel_safe() is False


class TestMorphologyTags:
    def test_tags_can_store_free_key_value_pairs(self):
        spec = _make_spec(
            morphology_tags={"variant": "alpha", "fitness": "0.82", "source": "MorphologyEngine"}
        )
        assert spec.morphology_tags["variant"] == "alpha"
        assert spec.morphology_tags["fitness"] == "0.82"
        assert spec.morphology_tags["source"] == "MorphologyEngine"

    def test_tags_are_independent_between_instances(self):
        """Each AgentSpec must have its own morphology_tags dict."""
        spec_a = _make_spec()
        spec_b = _make_spec()
        spec_a.morphology_tags["key"] = "value"
        assert "key" not in spec_b.morphology_tags


class TestAgentMorphologyDefaults:
    def test_singleton_defaults_to_false(self):
        m = AgentMorphology(layer=AgentLayer.GROWTH, domain=AgentDomain.SYSTEM)
        assert m.singleton is False

    def test_replaceable_defaults_to_true(self):
        m = AgentMorphology(layer=AgentLayer.GROWTH, domain=AgentDomain.SYSTEM)
        assert m.replaceable is True

    def test_max_instances_defaults_to_one(self):
        m = AgentMorphology(layer=AgentLayer.GROWTH, domain=AgentDomain.SYSTEM)
        assert m.max_instances == 1

    def test_depends_on_defaults_to_empty_list(self):
        m = AgentMorphology(layer=AgentLayer.GROWTH, domain=AgentDomain.SYSTEM)
        assert m.depends_on == []
