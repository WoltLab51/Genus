"""
Unit tests for genus.safety.sanitization_policy

Covers:
- Allowlist: non-allowed top-level keys are removed
- Allowed keys pass through unchanged when within limits
- String truncation
- List truncation
- Dict key limit per level
- Depth limit
- Deterministic output (same input → same output)
- Non-dict input → blocked_by_policy=True, empty data
- Evidence structure: policy_id, policy_version, removed_fields, truncated_fields, blocked_by_policy
- blocked_by_policy is True only when all keys were removed from a non-empty input
- Empty dict input → empty data, blocked_by_policy=False
- Custom policy allowlist
"""

import pytest

from genus.security.sanitization.sanitization_policy import (
    DEFAULT_POLICY,
    SanitizationPolicy,
    sanitize_payload,
)


# ---------------------------------------------------------------------------
# Allowlist / whitelist
# ---------------------------------------------------------------------------

class TestAllowlist:
    def test_allowed_key_passes_through(self):
        data, ev = sanitize_payload({"source": "test-agent"})
        assert data == {"source": "test-agent"}
        assert "source" not in ev["removed_fields"]

    def test_non_allowed_key_is_removed(self):
        data, ev = sanitize_payload({"secret_token": "abc123"})
        assert "secret_token" not in data
        assert "secret_token" in ev["removed_fields"]

    def test_mixed_keys_only_allowed_survive(self):
        payload = {
            "source": "ha",
            "timestamp": "2026-04-05T10:00:00Z",
            "raw_text": "personal data",
            "auth_token": "Bearer xyz",
        }
        data, ev = sanitize_payload(payload)
        assert set(data.keys()) == {"source", "timestamp"}
        assert "raw_text" in ev["removed_fields"]
        assert "auth_token" in ev["removed_fields"]

    def test_all_non_allowed_keys_blocked(self):
        data, ev = sanitize_payload({"unknown_a": 1, "unknown_b": 2})
        assert data == {}
        assert ev["blocked_by_policy"] is True

    def test_empty_dict_not_blocked(self):
        data, ev = sanitize_payload({})
        assert data == {}
        assert ev["blocked_by_policy"] is False

    def test_custom_allowlist(self):
        policy = SanitizationPolicy(allowed_keys=["custom_field"])
        data, ev = sanitize_payload({"custom_field": "hello", "source": "ignored"}, policy)
        assert "custom_field" in data
        assert "source" not in data
        assert "source" in ev["removed_fields"]

    def test_metrics_allowed_dict(self):
        payload = {"metrics": {"temp": 31.5, "humidity": 60}}
        data, ev = sanitize_payload(payload)
        assert "metrics" in data
        assert data["metrics"] == {"temp": 31.5, "humidity": 60}

    def test_all_default_allowed_keys_pass(self):
        payload = {
            "source": "s",
            "timestamp": "t",
            "type": "x",
            "event_type": "y",
            "metrics": {},
        }
        data, ev = sanitize_payload(payload)
        assert set(data.keys()) == set(payload.keys())


# ---------------------------------------------------------------------------
# String truncation
# ---------------------------------------------------------------------------

class TestStringTruncation:
    def test_short_string_unchanged(self):
        payload = {"source": "short"}
        data, ev = sanitize_payload(payload)
        assert data["source"] == "short"
        assert "source" not in ev["truncated_fields"]

    def test_long_string_truncated(self):
        policy = SanitizationPolicy(max_str_len=10)
        long_val = "a" * 20
        data, ev = sanitize_payload({"source": long_val}, policy)
        assert data["source"] == "a" * 10
        assert "source" in ev["truncated_fields"]

    def test_string_at_exact_limit_not_truncated(self):
        policy = SanitizationPolicy(max_str_len=5)
        data, ev = sanitize_payload({"source": "hello"}, policy)
        assert data["source"] == "hello"
        assert "source" not in ev["truncated_fields"]

    def test_nested_string_truncated(self):
        policy = SanitizationPolicy(max_str_len=3)
        data, ev = sanitize_payload({"metrics": {"label": "toolong"}}, policy)
        assert data["metrics"]["label"] == "too"
        assert any("label" in f for f in ev["truncated_fields"])


# ---------------------------------------------------------------------------
# List truncation
# ---------------------------------------------------------------------------

class TestListTruncation:
    def test_short_list_unchanged(self):
        policy = SanitizationPolicy(max_list_len=5, allowed_keys=["items"])
        data, ev = sanitize_payload({"items": [1, 2, 3]}, policy)
        assert data["items"] == [1, 2, 3]
        assert "items" not in ev["truncated_fields"]

    def test_long_list_truncated(self):
        policy = SanitizationPolicy(max_list_len=3, allowed_keys=["items"])
        data, ev = sanitize_payload({"items": list(range(10))}, policy)
        assert data["items"] == [0, 1, 2]
        assert "items" in ev["truncated_fields"]

    def test_list_at_exact_limit_not_truncated(self):
        policy = SanitizationPolicy(max_list_len=3, allowed_keys=["items"])
        data, ev = sanitize_payload({"items": [1, 2, 3]}, policy)
        assert data["items"] == [1, 2, 3]
        assert "items" not in ev["truncated_fields"]


# ---------------------------------------------------------------------------
# Dict key limit per level
# ---------------------------------------------------------------------------

class TestDictKeyLimit:
    def test_keys_within_limit_unchanged(self):
        policy = SanitizationPolicy(
            max_keys_per_level=10,
            allowed_keys=["metrics"],
        )
        payload = {"metrics": {f"k{i}": i for i in range(5)}}
        data, ev = sanitize_payload(payload, policy)
        assert len(data["metrics"]) == 5

    def test_excess_keys_removed(self):
        policy = SanitizationPolicy(
            max_keys_per_level=3,
            allowed_keys=["metrics"],
        )
        payload = {"metrics": {f"k{i}": i for i in range(6)}}
        data, ev = sanitize_payload(payload, policy)
        assert len(data["metrics"]) == 3
        # At least some removed fields recorded
        assert len(ev["removed_fields"]) >= 3


# ---------------------------------------------------------------------------
# Depth limit
# ---------------------------------------------------------------------------

class TestDepthLimit:
    def test_shallow_struct_unchanged(self):
        # _enforce_limits starts at depth=1 for the top-level dict, so a
        # 3-level nested value (metrics → a → b → value) sits at depth=4.
        # max_depth=4 means "4 levels deep is allowed".
        policy = SanitizationPolicy(max_depth=4, allowed_keys=["metrics"])
        payload = {"metrics": {"a": {"b": 1}}}
        data, ev = sanitize_payload(payload, policy)
        assert data["metrics"]["a"]["b"] == 1

    def test_deep_struct_pruned(self):
        policy = SanitizationPolicy(max_depth=2, allowed_keys=["metrics"])
        # metrics=depth1, a=depth2, b would be depth3 → pruned
        payload = {"metrics": {"a": {"b": 99}}}
        data, ev = sanitize_payload(payload, policy)
        # At depth=2 we have {"a": <value_at_depth3>}
        # The sub-dict {"b": 99} is at depth=3 which exceeds max_depth=2 → None
        assert data["metrics"]["a"] is None


# ---------------------------------------------------------------------------
# Non-dict input
# ---------------------------------------------------------------------------

class TestNonDictInput:
    def test_string_input_blocked(self):
        data, ev = sanitize_payload("raw text string")
        assert data == {}
        assert ev["blocked_by_policy"] is True

    def test_none_input_blocked(self):
        data, ev = sanitize_payload(None)
        assert data == {}
        assert ev["blocked_by_policy"] is True

    def test_list_input_blocked(self):
        data, ev = sanitize_payload([1, 2, 3])
        assert data == {}
        assert ev["blocked_by_policy"] is True

    def test_int_input_blocked(self):
        data, ev = sanitize_payload(42)
        assert data == {}
        assert ev["blocked_by_policy"] is True


# ---------------------------------------------------------------------------
# Evidence structure
# ---------------------------------------------------------------------------

class TestEvidenceStructure:
    def test_evidence_contains_required_keys(self):
        _, ev = sanitize_payload({"source": "test"})
        assert "policy_id" in ev
        assert "policy_version" in ev
        assert "removed_fields" in ev
        assert "truncated_fields" in ev
        assert "blocked_by_policy" in ev

    def test_evidence_policy_id_from_policy(self):
        policy = SanitizationPolicy(policy_id="custom-policy", policy_version="v99")
        _, ev = sanitize_payload({"source": "x"}, policy)
        assert ev["policy_id"] == "custom-policy"
        assert ev["policy_version"] == "v99"

    def test_evidence_default_policy_id(self):
        _, ev = sanitize_payload({})
        assert ev["policy_id"] == "default"
        assert ev["policy_version"] == "p1-c1"

    def test_evidence_removed_fields_is_list(self):
        _, ev = sanitize_payload({"bad": "field"})
        assert isinstance(ev["removed_fields"], list)

    def test_evidence_truncated_fields_is_list(self):
        _, ev = sanitize_payload({"source": "x"})
        assert isinstance(ev["truncated_fields"], list)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        payload = {
            "source": "device-a",
            "timestamp": "2026-04-05T12:00:00Z",
            "secret": "drop-me",
            "metrics": {"temp": 22.5},
        }
        result1 = sanitize_payload(payload)
        result2 = sanitize_payload(payload)
        assert result1 == result2

    def test_independent_calls_do_not_share_evidence(self):
        # Ensure evidence lists are not shared across calls
        _, ev1 = sanitize_payload({"source": "a", "bad1": 1})
        _, ev2 = sanitize_payload({"source": "b", "bad2": 2})
        assert "bad1" in ev1["removed_fields"]
        assert "bad1" not in ev2["removed_fields"]
        assert "bad2" in ev2["removed_fields"]
        assert "bad2" not in ev1["removed_fields"]
