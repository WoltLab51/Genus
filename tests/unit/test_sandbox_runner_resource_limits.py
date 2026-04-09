"""Tests for resource limit setup in SandboxRunner."""
import subprocess
import sys
import pytest
from genus.sandbox.runner import (
    _make_preexec_fn,
    _DEFAULT_MAX_MEMORY_BYTES,
    _DEFAULT_MAX_NPROC,
    _DEFAULT_MAX_FSIZE_BYTES,
)


def test_preexec_fn_is_none_on_windows():
    """On Windows, preexec_fn must be None (not supported)."""
    if sys.platform != "win32":
        pytest.skip("Windows-only test")
    fn = _make_preexec_fn()
    assert fn is None


def test_preexec_fn_is_callable_on_unix():
    """On Unix, preexec_fn must be a callable."""
    if sys.platform == "win32":
        pytest.skip("Unix-only test")
    fn = _make_preexec_fn()
    assert callable(fn)


def test_preexec_fn_does_not_raise():
    """The preexec_fn must not raise when called (even if limits can't be set).

    The function is run in a subprocess to avoid permanently lowering the
    test process's resource limits (RLIMIT_NPROC hard limits cannot be raised
    back by unprivileged processes once reduced).
    """
    if sys.platform == "win32":
        pytest.skip("Unix-only test")
    script = (
        "from genus.sandbox.runner import ("
        "_make_preexec_fn, _DEFAULT_MAX_MEMORY_BYTES, _DEFAULT_MAX_NPROC, _DEFAULT_MAX_FSIZE_BYTES"
        "); fn = _make_preexec_fn("
        "max_memory_bytes=_DEFAULT_MAX_MEMORY_BYTES, "
        "max_nproc=_DEFAULT_MAX_NPROC, "
        "max_fsize_bytes=_DEFAULT_MAX_FSIZE_BYTES"
        "); fn()"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


def test_preexec_fn_custom_limits_callable():
    """Custom resource limits should produce a callable that runs without errors.

    Runs fn() in a subprocess to avoid permanently lowering the test process's
    resource limits.
    """
    if sys.platform == "win32":
        pytest.skip("Unix-only test")
    fn = _make_preexec_fn(
        max_memory_bytes=256 * 1024 * 1024,
        max_nproc=32,
        max_fsize_bytes=50 * 1024 * 1024,
    )
    assert callable(fn)
    script = (
        "from genus.sandbox.runner import _make_preexec_fn;"
        "fn = _make_preexec_fn("
        "max_memory_bytes=256*1024*1024, "
        "max_nproc=32, "
        "max_fsize_bytes=50*1024*1024"
        "); fn()"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


def test_default_memory_limit_is_reasonable():
    assert _DEFAULT_MAX_MEMORY_BYTES >= 128 * 1024 * 1024  # at least 128 MB
    assert _DEFAULT_MAX_MEMORY_BYTES <= 2 * 1024 * 1024 * 1024  # at most 2 GB


def test_default_nproc_limit_is_reasonable():
    assert _DEFAULT_MAX_NPROC >= 8
    assert _DEFAULT_MAX_NPROC <= 256


def test_default_fsize_limit_is_reasonable():
    assert _DEFAULT_MAX_FSIZE_BYTES >= 10 * 1024 * 1024   # at least 10 MB
    assert _DEFAULT_MAX_FSIZE_BYTES <= 1024 * 1024 * 1024  # at most 1 GB
