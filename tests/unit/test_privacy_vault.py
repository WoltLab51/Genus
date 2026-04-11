"""Unit tests for PrivacyVault — Phase 14."""

import pytest

from genus.identity.models import PrivacyLevel, SystemRole, UserProfile
from genus.identity.privacy_vault import PrivacyVault
from genus.identity.profile_store import ProfileStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def profile_store(tmp_path) -> ProfileStore:
    store = ProfileStore(base_dir=tmp_path / "profiles")
    # Create owner profile
    owner = UserProfile(user_id="vault_owner", display_name="Owner", system_role=SystemRole.ADULT)
    await store.save(owner)
    # Create superadmin
    await store.get_or_create_superadmin()
    # Create other user
    other = UserProfile(user_id="other_user", display_name="Other", system_role=SystemRole.ADULT)
    await store.save(other)
    return store


@pytest.fixture
def vault(tmp_path, profile_store) -> PrivacyVault:
    return PrivacyVault(base_dir=tmp_path / "vault", profile_store=profile_store)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVaultOwnerAccess:
    async def test_owner_can_retrieve_own_data(self, vault):
        await vault.store("vault_owner", "my_secret", "s3cr3t", PrivacyLevel.PERSONAL)
        result = await vault.retrieve("vault_owner", "vault_owner", "my_secret")
        assert result == "s3cr3t"

    async def test_owner_can_retrieve_confidential(self, vault):
        await vault.store("vault_owner", "hidden", "top_secret", PrivacyLevel.CONFIDENTIAL)
        result = await vault.retrieve("vault_owner", "vault_owner", "hidden")
        assert result == "top_secret"

    async def test_retrieve_missing_key_returns_none(self, vault):
        result = await vault.retrieve("vault_owner", "vault_owner", "nonexistent")
        assert result is None


class TestVaultOtherUserBlocked:
    async def test_other_user_cannot_read_personal(self, vault):
        await vault.store("vault_owner", "diary", "private", PrivacyLevel.PERSONAL)
        result = await vault.retrieve("other_user", "vault_owner", "diary")
        assert result is None

    async def test_other_user_cannot_read_confidential(self, vault):
        await vault.store("vault_owner", "secret", "classified", PrivacyLevel.CONFIDENTIAL)
        result = await vault.retrieve("other_user", "vault_owner", "secret")
        assert result is None

    async def test_no_error_on_missing_key_for_other_user(self, vault):
        # Should return None silently, never raise
        result = await vault.retrieve("other_user", "vault_owner", "ghost_key")
        assert result is None


class TestVaultSuperadminAccess:
    async def test_superadmin_can_read_personal(self, vault):
        await vault.store("vault_owner", "health", "some_data", PrivacyLevel.PERSONAL)
        result = await vault.retrieve("ronny_wolter", "vault_owner", "health")
        assert result == "some_data"

    async def test_superadmin_cannot_read_confidential(self, vault):
        """CONFIDENTIAL entries are protected even from superadmin."""
        await vault.store("vault_owner", "confession", "very_private", PrivacyLevel.CONFIDENTIAL)
        result = await vault.retrieve("ronny_wolter", "vault_owner", "confession")
        assert result is None

    async def test_superadmin_can_read_nsfw(self, vault):
        """NSFW entries are accessible to superadmin (but never displayed aloud)."""
        await vault.store("vault_owner", "adult_content", "...", PrivacyLevel.NSFW)
        result = await vault.retrieve("ronny_wolter", "vault_owner", "adult_content")
        assert result == "..."


class TestDenyExistence:
    async def test_deny_existence_true_for_confidential_other_user(self, vault):
        await vault.store("vault_owner", "private_matter", "secret", PrivacyLevel.CONFIDENTIAL)
        should_deny = await vault.deny_existence("other_user", "vault_owner", "private_matter")
        assert should_deny is True

    async def test_deny_existence_false_for_owner(self, vault):
        await vault.store("vault_owner", "private_matter", "secret", PrivacyLevel.CONFIDENTIAL)
        should_deny = await vault.deny_existence("vault_owner", "vault_owner", "private_matter")
        assert should_deny is False

    async def test_deny_existence_false_for_personal_level(self, vault):
        await vault.store("vault_owner", "normal_data", "data", PrivacyLevel.PERSONAL)
        should_deny = await vault.deny_existence("other_user", "vault_owner", "normal_data")
        assert should_deny is False

    async def test_deny_existence_false_for_missing_key(self, vault):
        should_deny = await vault.deny_existence("other_user", "vault_owner", "ghost")
        assert should_deny is False
