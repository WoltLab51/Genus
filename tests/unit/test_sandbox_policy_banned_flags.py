"""Tests for banned_flags enforcement in SandboxPolicy."""
import pytest
from genus.sandbox.policy import SandboxPolicy
from genus.sandbox.models import SandboxCommand, SandboxPolicyError


def make_cmd(argv):
    return SandboxCommand(argv=argv, cwd=".")


class TestBannedFlagsDefault:
    def test_force_flag_blocked(self):
        policy = SandboxPolicy()
        cmd = make_cmd(["git", "push", "origin", "main", "--force"])
        with pytest.raises(SandboxPolicyError, match="Banned flag"):
            policy.validate(cmd)

    def test_no_verify_blocked(self):
        policy = SandboxPolicy()
        cmd = make_cmd(["git", "push", "origin", "main", "--no-verify"])
        with pytest.raises(SandboxPolicyError, match="Banned flag"):
            policy.validate(cmd)

    def test_delete_blocked(self):
        policy = SandboxPolicy()
        cmd = make_cmd(["git", "push", "origin", "--delete", "main"])
        with pytest.raises(SandboxPolicyError, match="Banned flag"):
            policy.validate(cmd)

    def test_short_force_blocked(self):
        policy = SandboxPolicy()
        cmd = make_cmd(["git", "push", "origin", "main", "-f"])
        with pytest.raises(SandboxPolicyError, match="Banned flag"):
            policy.validate(cmd)

    def test_mirror_blocked(self):
        policy = SandboxPolicy()
        cmd = make_cmd(["git", "push", "origin", "--mirror"])
        with pytest.raises(SandboxPolicyError, match="Banned flag"):
            policy.validate(cmd)

    def test_all_blocked(self):
        policy = SandboxPolicy()
        cmd = make_cmd(["git", "push", "origin", "--all"])
        with pytest.raises(SandboxPolicyError, match="Banned flag"):
            policy.validate(cmd)

    def test_force_with_lease_allowed(self):
        """--force-with-lease is the safe alternative and must NOT be banned."""
        policy = SandboxPolicy()
        cmd = make_cmd(["git", "push", "origin", "main", "--force-with-lease"])
        policy.validate(cmd)  # must not raise

    def test_normal_push_allowed(self):
        policy = SandboxPolicy()
        cmd = make_cmd(["git", "push", "origin", "main"])
        policy.validate(cmd)  # must not raise

    def test_default_banned_flags_list(self):
        policy = SandboxPolicy()
        assert "--force" in policy.banned_flags
        assert "-f" in policy.banned_flags
        assert "--no-verify" in policy.banned_flags
        assert "--delete" in policy.banned_flags
        assert "--mirror" in policy.banned_flags
        assert "--all" in policy.banned_flags


class TestBannedFlagsCustom:
    def test_empty_banned_flags_allows_force(self):
        policy = SandboxPolicy(banned_flags=[])
        cmd = make_cmd(["git", "push", "origin", "main", "--force"])
        policy.validate(cmd)  # must not raise with empty banned_flags

    def test_empty_banned_flags_stored(self):
        policy = SandboxPolicy(banned_flags=[])
        assert policy.banned_flags == []

    def test_custom_banned_flag(self):
        policy = SandboxPolicy(banned_flags=["--dry-run"])
        cmd = make_cmd(["git", "push", "origin", "main", "--dry-run"])
        with pytest.raises(SandboxPolicyError, match="Banned flag"):
            policy.validate(cmd)

    def test_custom_banned_flag_stored(self):
        policy = SandboxPolicy(banned_flags=["--dry-run", "--verbose"])
        assert "--dry-run" in policy.banned_flags
        assert "--verbose" in policy.banned_flags
