"""
Tests for genus.growth.identity_profile (StabilityRules)

Verifies:
- Default values are correct
- cooldown_same_domain_per_need=True: same domain, different needs → no cooldown implied
- cooldown_same_domain_per_need=False: same domain → cooldown applies regardless of need
"""

import pytest

from genus.growth.identity_profile import IdentityProfile, StabilityRules


class TestStabilityRulesDefaults:
    def test_default_min_agent_runtime(self):
        """Default min_agent_runtime_before_replace_s must be 86400 (24h)."""
        rules = StabilityRules()
        assert rules.min_agent_runtime_before_replace_s == 86_400

    def test_default_cooldown_same_domain(self):
        """Default cooldown_same_domain_s must be 43200 (12h)."""
        rules = StabilityRules()
        assert rules.cooldown_same_domain_s == 43_200

    def test_default_cooldown_after_failed_build(self):
        """Default cooldown_after_failed_build_s must be 3600 (1h)."""
        rules = StabilityRules()
        assert rules.cooldown_after_failed_build_s == 3_600

    def test_default_cooldown_same_domain_per_need_is_true(self):
        """Default cooldown_same_domain_per_need must be True."""
        rules = StabilityRules()
        assert rules.cooldown_same_domain_per_need is True

    def test_default_min_trigger_count(self):
        """Default min_trigger_count_before_build must be 2."""
        rules = StabilityRules()
        assert rules.min_trigger_count_before_build == 2

    def test_default_min_observations(self):
        """Default min_observations_before_upgrade must be 5."""
        rules = StabilityRules()
        assert rules.min_observations_before_upgrade == 5

    def test_default_min_score_to_keep(self):
        """Default min_score_to_keep_agent must be 0.40."""
        rules = StabilityRules()
        assert rules.min_score_to_keep_agent == pytest.approx(0.40)

    def test_default_min_score_to_replace(self):
        """Default min_score_to_replace_agent must be 0.65."""
        rules = StabilityRules()
        assert rules.min_score_to_replace_agent == pytest.approx(0.65)


class TestStabilityRulesCooldownPerNeed:
    """Verify the semantics of cooldown_same_domain_per_need."""

    def _is_cooldown_active(
        self,
        rules: StabilityRules,
        domain: str,
        need: str,
        active_keys: set,
    ) -> bool:
        """Simulate whether a cooldown is active for a (domain, need) pair.

        When cooldown_same_domain_per_need=True the key is (domain, need).
        When cooldown_same_domain_per_need=False the key is just domain.
        """
        if rules.cooldown_same_domain_per_need:
            key = (domain, need)
        else:
            key = domain  # type: ignore[assignment]
        return key in active_keys

    def test_per_need_true_same_domain_different_needs_no_cooldown(self):
        """With per_need=True, same domain but different needs must NOT share cooldown."""
        rules = StabilityRules(cooldown_same_domain_per_need=True)
        # Imagine FamilyCalendarAgent was just built:
        active_cooldowns = {("family", "Familienkalender verwalten")}

        # A different need in the same domain must NOT be in cooldown
        in_cooldown = self._is_cooldown_active(
            rules, "family", "Familiensicherheit verbessern", active_cooldowns
        )
        assert in_cooldown is False

    def test_per_need_true_same_domain_same_need_has_cooldown(self):
        """With per_need=True, same domain and same need must share cooldown."""
        rules = StabilityRules(cooldown_same_domain_per_need=True)
        active_cooldowns = {("family", "Familienkalender verwalten")}

        in_cooldown = self._is_cooldown_active(
            rules, "family", "Familienkalender verwalten", active_cooldowns
        )
        assert in_cooldown is True

    def test_per_need_false_same_domain_any_need_has_cooldown(self):
        """With per_need=False, same domain must be in cooldown regardless of need."""
        rules = StabilityRules(cooldown_same_domain_per_need=False)
        active_cooldowns = {"family"}  # domain-only key

        in_cooldown_1 = self._is_cooldown_active(
            rules, "family", "Familienkalender verwalten", active_cooldowns
        )
        in_cooldown_2 = self._is_cooldown_active(
            rules, "family", "Familiensicherheit verbessern", active_cooldowns
        )
        assert in_cooldown_1 is True
        assert in_cooldown_2 is True

    def test_per_need_false_different_domain_no_cooldown(self):
        """With per_need=False, different domain must not be in cooldown."""
        rules = StabilityRules(cooldown_same_domain_per_need=False)
        active_cooldowns = {"family"}

        in_cooldown = self._is_cooldown_active(
            rules, "trading", "Trading-Strategie optimieren", active_cooldowns
        )
        assert in_cooldown is False


class TestIdentityProfile:
    def test_default_stability_rules(self):
        """IdentityProfile must create default StabilityRules if not provided."""
        profile = IdentityProfile(system_name="GENUS", owner="Tester")
        assert isinstance(profile.stability_rules, StabilityRules)

    def test_custom_stability_rules(self):
        """IdentityProfile must accept custom StabilityRules."""
        rules = StabilityRules(min_trigger_count_before_build=5)
        profile = IdentityProfile(
            system_name="GENUS", owner="Tester", stability_rules=rules
        )
        assert profile.stability_rules.min_trigger_count_before_build == 5

    def test_description_defaults_to_empty_string(self):
        """IdentityProfile.description must default to empty string."""
        profile = IdentityProfile(system_name="GENUS", owner="Tester")
        assert profile.description == ""
