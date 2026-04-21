"""Sandboxed testing for generated tools."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from genus.sandbox.models import SandboxCommand
from genus.sandbox.policy import SandboxPolicy
from genus.sandbox.runner import SandboxRunner
from genus.workspace.workspace import RunWorkspace


class ToolTester:
    """Tests generated code only inside temporary sandbox workspaces."""

    def __init__(self, timeout_s: float = 30.0) -> None:
        self._timeout_s = timeout_s

    async def test(self, code: str, name: str) -> tuple[bool, str]:
        """Test generated Python code in an isolated sandbox and return status/output."""
        token = uuid4().hex
        module_name = f"{name}_{token}"
        module_filename = f"{module_name}.py"
        test_filename = f"test_{module_name}.py"

        with tempfile.TemporaryDirectory(prefix="genus-builder-test-") as tmp:
            workspace_root = Path(tmp)
            workspace = RunWorkspace.create(
                f"builder-test-{token}",
                workspace_root=workspace_root,
            )
            workspace.ensure_dirs()

            ws_generated = workspace.repo_dir / "genus" / "agents" / "generated"
            ws_generated.mkdir(parents=True, exist_ok=True)
            (ws_generated / module_filename).write_text(code, encoding="utf-8")
            (ws_generated / test_filename).write_text(
                "\n".join(
                    [
                        "import importlib.util",
                        "from pathlib import Path",
                        "",
                        "def test_generated_tool_module_loads() -> None:",
                        f"    target = Path(__file__).with_name('{module_filename}')",
                        f"    spec = importlib.util.spec_from_file_location('{module_name}', target)",
                        "    assert spec is not None",
                        "    assert spec.loader is not None",
                        "    module = importlib.util.module_from_spec(spec)",
                        "    spec.loader.exec_module(module)",
                        f"    assert hasattr(module, '{name}')",
                    ]
                ),
                encoding="utf-8",
            )

            runner = SandboxRunner(workspace=workspace, policy=SandboxPolicy())
            command = SandboxCommand(
                argv=[
                    "python",
                    "-m",
                    "pytest",
                    "-q",
                    f"genus/agents/generated/{test_filename}",
                ],
                cwd=".",
            )
            result = await runner.run(command, timeout_s=self._timeout_s)
            parts = [s for s in [result.stdout.strip(), result.stderr.strip()] if s]
            output = "\n".join(parts)
            return result.exit_code == 0, output
