"""
Unit Tests — CodeValidator (genus.growth.code_validator)

Verifies:
- Valider Agent-Code → passed=True, keine errors
- eval() im Code → passed=False, error enthält "eval"
- exec() im Code → passed=False
- os.system() im Code → passed=False
- import subprocess → passed=False (nicht in Whitelist)
- import genus.communication → passed=True (in Whitelist via "genus")
- Syntax-Fehler → passed=False, error enthält Zeilen-Info
- Keine Agent-Subklasse → warning (nicht error)
- Fehlende Lifecycle-Methoden → warning
"""

from __future__ import annotations

import textwrap

import pytest

from genus.growth.code_validator import CodeValidator, ValidationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_AGENT_CODE = textwrap.dedent(
    """\
    from __future__ import annotations
    from typing import Optional
    from genus.communication.message_bus import Message, MessageBus
    from genus.core.agent import Agent, AgentState

    class SimpleAgent(Agent):
        def __init__(
            self,
            message_bus: MessageBus,
            agent_id: Optional[str] = None,
            name: Optional[str] = None,
        ) -> None:
            super().__init__(agent_id=agent_id, name=name or "SimpleAgent")
            self._bus = message_bus

        async def initialize(self) -> None:
            self._transition_state(AgentState.INITIALIZED)

        async def start(self) -> None:
            self._transition_state(AgentState.RUNNING)

        async def stop(self) -> None:
            self._bus.unsubscribe_all(self.id)
            self._transition_state(AgentState.STOPPED)

        async def process_message(self, message: Message) -> None:
            pass
    """
)


def _validator() -> CodeValidator:
    return CodeValidator()


# ---------------------------------------------------------------------------
# Tests — passing cases
# ---------------------------------------------------------------------------

class TestCodeValidatorPassing:
    def test_valid_agent_code_passes(self) -> None:
        """Valid agent code with all lifecycle methods → passed=True, no errors."""
        result = _validator().validate(_VALID_AGENT_CODE)
        assert result.passed is True
        assert result.errors == []

    def test_valid_agent_no_warnings(self) -> None:
        """Valid complete agent code has no warnings."""
        result = _validator().validate(_VALID_AGENT_CODE)
        assert result.warnings == []

    def test_import_genus_communication_allowed(self) -> None:
        """from genus.communication import ... is allowed (genus in whitelist)."""
        code = textwrap.dedent(
            """\
            from genus.communication.message_bus import Message, MessageBus
            from genus.core.agent import Agent, AgentState

            class MyAgent(Agent):
                async def initialize(self): pass
                async def start(self): pass
                async def stop(self): pass
                async def process_message(self, message): pass
            """
        )
        result = _validator().validate(code)
        assert result.passed is True
        assert not any("genus" in e for e in result.errors)

    def test_import_typing_allowed(self) -> None:
        """from typing import Optional is allowed."""
        code = "from typing import Optional, List\nx: Optional[str] = None"
        result = _validator().validate(code)
        assert result.passed is True

    def test_import_asyncio_allowed(self) -> None:
        """import asyncio is allowed."""
        code = "import asyncio\nasyncio.sleep(0)"
        result = _validator().validate(code)
        assert result.passed is True

    def test_import_future_allowed(self) -> None:
        """from __future__ import annotations is allowed."""
        code = "from __future__ import annotations\nx: int = 1"
        result = _validator().validate(code)
        assert result.passed is True

    def test_import_os_path_allowed(self) -> None:
        """from os.path import join is allowed (os.path in whitelist)."""
        code = "from os.path import join\njoin('a', 'b')"
        result = _validator().validate(code)
        assert result.passed is True

    def test_import_import_os_path_allowed(self) -> None:
        """import os.path is allowed (exact match in whitelist)."""
        code = "import os.path\nos.path.join('a', 'b')"
        result = _validator().validate(code)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Tests — banned calls
# ---------------------------------------------------------------------------

class TestCodeValidatorBannedCalls:
    def test_eval_call_is_rejected(self) -> None:
        """eval() in code → passed=False, error mentions 'eval'."""
        code = "result = eval('1 + 1')"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("eval" in e for e in result.errors)

    def test_exec_call_is_rejected(self) -> None:
        """exec() in code → passed=False."""
        code = "exec('x = 1')"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("exec" in e for e in result.errors)

    def test_os_system_is_rejected(self) -> None:
        """os.system() in code → passed=False."""
        code = "import os\nos.system('id')"
        result = _validator().validate(code)
        assert result.passed is False
        # 'os' import is also flagged (not whitelisted); os.system must be present
        call_errors = [e for e in result.errors if "os.system" in e]
        assert call_errors, f"Expected os.system error, got: {result.errors}"

    def test_os_popen_is_rejected(self) -> None:
        """os.popen() in code → passed=False."""
        code = "import os\nos.popen('ls')"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("os.popen" in e for e in result.errors)

    def test_subprocess_call_is_rejected(self) -> None:
        """subprocess.call() in code → passed=False."""
        code = "import subprocess\nsubprocess.call(['ls'])"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("subprocess.call" in e for e in result.errors)

    def test_subprocess_run_is_rejected(self) -> None:
        """subprocess.run() in code → passed=False."""
        code = "import subprocess\nsubprocess.run(['id'], capture_output=True)"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("subprocess.run" in e for e in result.errors)

    def test_compile_is_rejected(self) -> None:
        """compile() in code → passed=False."""
        code = "compile('x = 1', '<string>', 'exec')"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("compile" in e for e in result.errors)

    def test_dunder_import_is_rejected(self) -> None:
        """__import__() in code → passed=False."""
        code = "__import__('os').system('id')"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("__import__" in e for e in result.errors)

    def test_eval_inside_method_is_rejected(self) -> None:
        """eval() nested inside a class method is still caught."""
        code = textwrap.dedent(
            """\
            from genus.core.agent import Agent
            class EvilAgent(Agent):
                async def initialize(self):
                    eval("__import__('os').system('rm -rf /')")
                async def start(self): pass
                async def stop(self): pass
                async def process_message(self, message): pass
            """
        )
        result = _validator().validate(code)
        assert result.passed is False
        assert any("eval" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Tests — import whitelist
# ---------------------------------------------------------------------------

class TestCodeValidatorImportWhitelist:
    def test_import_subprocess_is_rejected(self) -> None:
        """import subprocess → passed=False (not in whitelist)."""
        code = "import subprocess"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("subprocess" in e for e in result.errors)

    def test_import_os_is_rejected(self) -> None:
        """import os → passed=False (only os.path is whitelisted, not bare os)."""
        code = "import os"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("os" in e for e in result.errors)

    def test_from_os_import_getcwd_is_rejected(self) -> None:
        """from os import getcwd → passed=False."""
        code = "from os import getcwd"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("os" in e for e in result.errors)

    def test_import_socket_is_rejected(self) -> None:
        """import socket → passed=False."""
        code = "import socket"
        result = _validator().validate(code)
        assert result.passed is False
        assert any("socket" in e for e in result.errors)

    def test_custom_allowed_imports(self) -> None:
        """Custom allowed_imports set is respected."""
        validator = CodeValidator(allowed_imports={"custom_module"})
        code = "import custom_module"
        result = validator.validate(code)
        assert result.passed is True

    def test_custom_allowed_imports_blocks_default(self) -> None:
        """When custom allowed_imports is given, defaults are NOT merged in."""
        validator = CodeValidator(allowed_imports={"custom_module"})
        code = "import asyncio"  # asyncio is NOT in custom set
        result = validator.validate(code)
        assert result.passed is False


# ---------------------------------------------------------------------------
# Tests — syntax errors
# ---------------------------------------------------------------------------

class TestCodeValidatorSyntaxErrors:
    def test_syntax_error_is_rejected(self) -> None:
        """Syntax error → passed=False."""
        code = "this is not valid python !!!"
        result = _validator().validate(code)
        assert result.passed is False

    def test_syntax_error_contains_line_info(self) -> None:
        """Syntax error message contains line number."""
        code = "x = (\n  1 +\n"  # unclosed paren
        result = _validator().validate(code)
        assert result.passed is False
        assert result.errors
        # Error should mention a line number
        error_text = " ".join(result.errors)
        assert any(char.isdigit() for char in error_text), (
            f"Expected line number in error: {result.errors}"
        )

    def test_syntax_error_no_warnings_on_parse_fail(self) -> None:
        """When syntax fails, no warnings are generated (early return)."""
        code = "def broken(:"
        result = _validator().validate(code)
        assert result.passed is False
        assert result.warnings == []


# ---------------------------------------------------------------------------
# Tests — agent structure (warnings)
# ---------------------------------------------------------------------------

class TestCodeValidatorAgentStructure:
    def test_no_agent_subclass_produces_warning(self) -> None:
        """Code without an Agent subclass → warning (not error)."""
        code = "x = 1\n"
        result = _validator().validate(code)
        # No critical errors, but a warning
        assert result.passed is True
        assert any("Agent" in w for w in result.warnings)

    def test_missing_lifecycle_methods_produces_warning(self) -> None:
        """Agent subclass missing lifecycle methods → warning."""
        code = textwrap.dedent(
            """\
            from genus.core.agent import Agent
            class PartialAgent(Agent):
                async def initialize(self): pass
                # start, stop, process_message missing
            """
        )
        result = _validator().validate(code)
        assert result.passed is True
        assert any("missing lifecycle" in w for w in result.warnings)

    def test_complete_lifecycle_no_warnings(self) -> None:
        """Agent with all lifecycle methods → no structure warnings."""
        code = textwrap.dedent(
            """\
            from genus.core.agent import Agent
            class FullAgent(Agent):
                async def initialize(self): pass
                async def start(self): pass
                async def stop(self): pass
                async def process_message(self, message): pass
            """
        )
        result = _validator().validate(code)
        assert result.passed is True
        assert result.warnings == []

    def test_require_agent_base_false_suppresses_warning(self) -> None:
        """require_agent_base=False: no warning for missing Agent base."""
        validator = CodeValidator(require_agent_base=False, require_lifecycle=False)
        code = "x = 1\n"
        result = validator.validate(code)
        assert result.passed is True
        assert result.warnings == []

    def test_structure_issues_are_warnings_not_errors(self) -> None:
        """Structure issues never appear in errors — only in warnings."""
        code = "class NoBase:\n    pass\n"
        result = _validator().validate(code)
        # The "No class inheriting from Agent" should be a warning
        assert result.passed is True
        assert result.errors == []

    def test_validation_result_fields(self) -> None:
        """ValidationResult has passed, errors, warnings fields."""
        result = ValidationResult(passed=True, errors=[], warnings=["w1"])
        assert result.passed is True
        assert result.errors == []
        assert result.warnings == ["w1"]
