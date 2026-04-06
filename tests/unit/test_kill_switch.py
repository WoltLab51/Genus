"""
Tests for KillSwitch v1 API

Tests the sandbox-specific KillSwitch API:
- enable() / disable()
- assert_enabled()
- enabled property
- DEFAULT_KILL_SWITCH
"""

import pytest

from genus.security.kill_switch import KillSwitch, DEFAULT_KILL_SWITCH


class TestKillSwitchV1Api:
    """Tests for the v1 sandbox API methods."""

    def test_initially_enabled(self):
        """KillSwitch should start enabled (execution allowed)."""
        ks = KillSwitch()
        assert ks.enabled is True

    def test_disable_blocks_execution(self):
        """disable() should block sandbox execution."""
        ks = KillSwitch()
        ks.disable()
        assert ks.enabled is False

    def test_enable_allows_execution(self):
        """enable() should allow sandbox execution."""
        ks = KillSwitch()
        ks.disable()
        ks.enable()
        assert ks.enabled is True

    def test_assert_enabled_passes_when_enabled(self):
        """assert_enabled() should not raise when enabled."""
        ks = KillSwitch()
        # Should not raise
        ks.assert_enabled()

    def test_assert_enabled_raises_when_disabled(self):
        """assert_enabled() should raise RuntimeError when disabled."""
        ks = KillSwitch()
        ks.disable()
        with pytest.raises(RuntimeError) as exc_info:
            ks.assert_enabled()
        assert "Sandbox execution disabled" in str(exc_info.value)

    def test_enable_disable_cycle(self):
        """Multiple enable/disable cycles should work correctly."""
        ks = KillSwitch()

        # Start enabled
        assert ks.enabled is True
        ks.assert_enabled()

        # Disable
        ks.disable()
        assert ks.enabled is False
        with pytest.raises(RuntimeError):
            ks.assert_enabled()

        # Re-enable
        ks.enable()
        assert ks.enabled is True
        ks.assert_enabled()

    def test_default_kill_switch_exists(self):
        """DEFAULT_KILL_SWITCH should be available."""
        assert DEFAULT_KILL_SWITCH is not None
        assert isinstance(DEFAULT_KILL_SWITCH, KillSwitch)

    def test_default_kill_switch_initially_enabled(self):
        """DEFAULT_KILL_SWITCH should start enabled."""
        # Reset to ensure test isolation
        DEFAULT_KILL_SWITCH.enable()
        assert DEFAULT_KILL_SWITCH.enabled is True

    def test_enabled_property_reflects_active_state(self):
        """enabled property should be inverse of is_active()."""
        ks = KillSwitch()

        # Initially not active -> enabled
        assert ks.is_active() is False
        assert ks.enabled is True

        # Activate -> disabled
        ks.activate(reason="test")
        assert ks.is_active() is True
        assert ks.enabled is False

        # Deactivate -> enabled
        ks.deactivate()
        assert ks.is_active() is False
        assert ks.enabled is True

    def test_disable_is_same_as_activate(self):
        """disable() should activate the kill-switch."""
        ks = KillSwitch()
        ks.disable()
        assert ks.is_active() is True
        assert "Sandbox execution disabled" in ks.reason

    def test_enable_is_same_as_deactivate(self):
        """enable() should deactivate the kill-switch."""
        ks = KillSwitch()
        ks.activate(reason="test")
        ks.enable()
        assert ks.is_active() is False
