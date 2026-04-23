"""
DevLoop Artifact Schemas

Lightweight dataclass definitions that document the *shape* of artifacts
produced and consumed during a GENUS dev loop.  Events transport plain
``dict`` payloads; these classes exist to document the expected structure
and enable type-checked construction/access where desired.

All fields are optional to keep deserialization tolerant: callers should
use ``dataclasses.asdict`` to convert to a dict before embedding in a
message payload.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class PlanArtifact:
    """Describes the output of the planning phase.

    Attributes:
        steps:               Ordered list of implementation steps.
        acceptance_criteria: Conditions that must be satisfied for success.
        risks:               Identified risks and their descriptions.
    """

    steps: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)


@dataclass
class TestReportArtifact:
    """Describes the outcome of a test run.

    Attributes:
        passed:        Number of passing tests.
        failed:        Number of failing tests.
        errors:        Number of test errors (e.g. collection errors).
        duration_s:    Total test duration in seconds.
        summary:       Human-readable summary line.
        status:        Overall status: "passed", "failed", "error", or "no_tests".
        failing_tests: List of test identifiers that failed.
        failures:      Detailed failure records, each a dict with "test" and "message".
    """

    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration_s: float = 0.0
    summary: str = ""
    status: str = "passed"
    failing_tests: List[str] = field(default_factory=list)
    failures: List[dict] = field(default_factory=list)


@dataclass
class ReviewArtifact:
    """Describes the outcome of a code review.

    Attributes:
        findings:       List of findings, each a dict with at least
                        ``{"severity": str, "message": str}``.
        severity:       Highest severity level found (e.g. ``"high"``).
        required_fixes: Descriptions of fixes that must be applied.
    """

    findings: List[dict] = field(default_factory=list)
    severity: str = "none"
    required_fixes: List[str] = field(default_factory=list)


@dataclass
class FixArtifact:
    """Describes a set of fixes applied during the fix phase.

    Attributes:
        patch_summary:  Human-readable summary of the changes.
        files_changed:  List of file paths that were modified.
        tests_rerun:    List of test identifiers re-executed after fixing.
    """

    patch_summary: str = ""
    files_changed: List[str] = field(default_factory=list)
    tests_rerun: List[str] = field(default_factory=list)
