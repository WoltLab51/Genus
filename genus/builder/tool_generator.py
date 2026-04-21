"""LLM-backed tool code generation."""

from __future__ import annotations

from genus.builder.models import BuildRequest
from genus.llm.exceptions import LLMProviderUnavailableError
from genus.llm.models import LLMMessage, LLMRole
from genus.llm.router import LLMRouter, TaskType


def _strip_code_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


class ToolGenerator:
    """Generates Python tool code using the configured LLM router."""

    def __init__(self, llm_router: LLMRouter | None) -> None:
        self._llm_router = llm_router

    async def generate(self, request: BuildRequest) -> str:
        """Generate Python tool code for the given build request."""
        if self._llm_router is None:
            raise LLMProviderUnavailableError("LLM unavailable")

        messages = [
            LLMMessage(
                role=LLMRole.SYSTEM,
                content=(
                    "You generate secure, testable Python tools. "
                    "Return only Python code with type hints and a docstring."
                ),
            ),
            LLMMessage(
                role=LLMRole.USER,
                content=(
                    f"Create a Python tool named '{request.name}'.\n"
                    f"Description: {request.description}\n"
                    f"Signature: {request.signature}\n"
                    f"Domain: {request.domain}\n"
                    "Requirements:\n"
                    "- include a module docstring and function docstring\n"
                    "- include full type hints\n"
                    "- avoid unsafe operations and external side effects\n"
                    "- keep implementation deterministic and testable"
                ),
            ),
        ]
        response = await self._llm_router.complete(
            messages=messages,
            task_type=TaskType.CODE_GEN,
            temperature=0.1,
            max_tokens=2000,
        )
        return _strip_code_fences(response.content)
