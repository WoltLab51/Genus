"""Automatic repair loop for failed generated tools."""

from __future__ import annotations

from genus.builder.models import BuildRequest, RepairAttempt
from genus.builder.tool_generator import _strip_code_fences
from genus.builder.tool_tester import ToolTester
from genus.llm.exceptions import LLMProviderUnavailableError
from genus.llm.models import LLMMessage, LLMRole
from genus.llm.router import LLMRouter, TaskType


class RepairLoop:
    """Repairs generated code from test failures using the LLM."""

    def __init__(self, llm_router: LLMRouter | None, tester: ToolTester) -> None:
        self._llm_router = llm_router
        self._tester = tester

    async def run(
        self,
        code: str,
        error: str,
        request: BuildRequest,
        attempt: int,
    ) -> RepairAttempt:
        """Repair failed code using LLM feedback and re-test the result."""
        if self._llm_router is None:
            return RepairAttempt(
                attempt=attempt,
                error=error,
                repaired_code=code,
                test_output="LLM unavailable",
                success=False,
            )

        repaired_code = code
        success = False
        test_output = error
        try:
            response = await self._llm_router.complete(
                messages=[
                    LLMMessage(
                        role=LLMRole.SYSTEM,
                        content=(
                            "You are a Python repair assistant. "
                            "Fix the provided code based on the sandbox error. "
                            "Return only corrected Python code."
                        ),
                    ),
                    LLMMessage(
                        role=LLMRole.USER,
                        content=(
                            f"Tool name: {request.name}\n"
                            f"Signature: {request.signature}\n"
                            f"Attempt: {attempt}/{request.max_repair_attempts}\n\n"
                            f"Current code:\n{code}\n\n"
                            f"Sandbox error output:\n{error}\n"
                        ),
                    ),
                ],
                task_type=TaskType.CODE_GEN,
                temperature=0.1,
                max_tokens=2200,
            )
            repaired_code = _strip_code_fences(response.content)
        except LLMProviderUnavailableError:
            test_output = "LLM unavailable"
        else:
            success, test_output = await self._tester.test(repaired_code, request.name)
        return RepairAttempt(
            attempt=attempt,
            error=error,
            repaired_code=repaired_code,
            test_output=test_output,
            success=success,
        )
