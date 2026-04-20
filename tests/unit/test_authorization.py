import pytest

from genus.identity.actor_registry import Actor, ActorRole, ActorType
from genus.identity.authorization import AuthorizationError, authorize


ADMIN = Actor(
    actor_id="admin",
    type=ActorType.SYSTEM,
    role=ActorRole.ADMIN,
    families=frozenset(),
)
OWNER = Actor(
    actor_id="papa",
    type=ActorType.HUMAN,
    role=ActorRole.OPERATOR,
    user_id="papa",
    families=frozenset({"family-1"}),
)
READER_MEMBER = Actor(
    actor_id="reader-member",
    type=ActorType.DEVICE,
    role=ActorRole.READER,
    families=frozenset({"family-1"}),
)
STRANGER = Actor(
    actor_id="stranger",
    type=ActorType.HUMAN,
    role=ActorRole.OPERATOR,
    user_id="other",
    families=frozenset(),
)


@pytest.mark.parametrize(
    ("actor", "operation", "scope", "allowed"),
    [
        (ADMIN, "admin", "system", True),
        (OWNER, "admin", "system", False),
        (OWNER, "read", "private:papa", True),
        (STRANGER, "read", "private:papa", False),
        (ADMIN, "write", "private:papa", True),
        (READER_MEMBER, "read", "family:family-1", True),
        (READER_MEMBER, "write", "family:family-1", False),
        (OWNER, "write", "family:family-1", True),
        (STRANGER, "read", "family:family-1", False),
    ],
)
def test_authorize_policy_matrix(actor, operation, scope, allowed):
    if allowed:
        authorize(actor, operation, scope)
        return
    with pytest.raises(AuthorizationError):
        authorize(actor, operation, scope)
