"""
Agent Code Template — Phase 7

Provides :class:`AgentCodeTemplate` for rendering a complete, importable
Python agent class from a simple specification dict, plus helper functions
used by :class:`~genus.dev.agents.template_builder_agent.TemplateBuilderAgent`.

Design rules:
- No external dependencies — stdlib only (``textwrap``, ``re``, ``dataclasses``).
- ``render()`` always returns syntactically valid Python (verifiable via
  ``ast.parse()``).
- Template is built with ``textwrap.dedent`` + f-strings; no Jinja2.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def class_name_to_filename(class_name: str) -> str:
    """Convert a CamelCase class name to a snake_case filename (no extension).

    Examples::

        class_name_to_filename("FamilyCalendarAgent") -> "family_calendar_agent"
        class_name_to_filename("SystemAgent")          -> "system_agent"

    Args:
        class_name: A CamelCase identifier, e.g. ``"FamilyCalendarAgent"``.

    Returns:
        A lowercase snake_case string suitable for use as a Python module name.
    """
    # Insert underscore before uppercase letters that follow a lowercase letter
    # or before a sequence of uppercase letters followed by a lowercase letter.
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", class_name)
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s1)
    return s2.lower()


def extract_class_name(agent_spec_template: dict, domain: str) -> str:
    """Extract or derive a class name from an agent spec template dict.

    Uses ``template["name"]`` when present and non-empty, otherwise derives
    the name from *domain*:  ``domain.title() + "Agent"``.

    Examples::

        extract_class_name({"name": "FooAgent"}, "family") -> "FooAgent"
        extract_class_name({}, "family")                   -> "FamilyAgent"

    Args:
        agent_spec_template: Dict that may contain a ``"name"`` key.
        domain:              Fallback domain string (e.g. ``"family"``).

    Returns:
        A valid Python class name string.
    """
    name = agent_spec_template.get("name", "")
    if name and isinstance(name, str):
        return name.strip()
    return domain.strip().title() + "Agent"


def extract_subscribe_topics(agent_spec_template: dict) -> List[str]:
    """Extract the list of topics to subscribe to from an agent spec template.

    Looks for ``template["topics"]`` (a list of strings).  Falls back to an
    empty list when the key is absent or the value is not a list.

    Args:
        agent_spec_template: Dict that may contain a ``"topics"`` key.

    Returns:
        A list of topic strings (may be empty).
    """
    topics = agent_spec_template.get("topics", [])
    if isinstance(topics, list):
        return [t for t in topics if isinstance(t, str)]
    return []


# ---------------------------------------------------------------------------
# AgentCodeTemplate
# ---------------------------------------------------------------------------

@dataclass
class AgentCodeTemplate:
    """Renders a complete, importable Python agent class from a specification.

    Args:
        class_name:        CamelCase class name, e.g. ``"FamilyCalendarAgent"``.
        domain:            Domain string, e.g. ``"family"``.
        need_description:  Short description of the need, e.g.
                           ``"missing_calendar_reminders"``.
        subscribe_topics:  List of topic strings to subscribe in
                           ``initialize()``.  May be empty.
        version:           Agent version integer.  Defaults to ``1``.
        generated_by:      Generator label.  Defaults to
                           ``"GENUS-BuilderAgent"``.
    """

    class_name: str
    domain: str
    need_description: str
    subscribe_topics: List[str] = field(default_factory=list)
    version: int = 1
    generated_by: str = "GENUS-BuilderAgent"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self) -> str:
        """Render the agent class as a Python source code string.

        Returns:
            A complete, importable Python module string.  Always
            syntactically valid (``ast.parse()``-safe).
        """
        subscribe_lines = self._render_subscribe_lines()
        return self._render_module(subscribe_lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _render_subscribe_lines(self) -> str:
        """Render the ``self._bus.subscribe(...)`` calls for ``initialize()``.

        Returns:
            A string containing zero or more subscribe calls (no leading
            indentation — callers are responsible for indenting).  Returns
            an empty string when ``subscribe_topics`` is empty.
        """
        if not self.subscribe_topics:
            return ""
        lines = [
            f'self._bus.subscribe("{topic}", self.id, self.process_message)'
            for topic in self.subscribe_topics
        ]
        return "\n".join(lines) + "\n"

    def _render_module(self, subscribe_lines: str) -> str:
        """Render the complete Python module string.

        The template is written at column 0 to avoid issues with
        ``textwrap.dedent`` and multi-line string substitution.

        Args:
            subscribe_lines: Pre-rendered subscribe call lines without
                leading indentation (may be empty).

        Returns:
            Full Python source code as a string.
        """
        cn = self.class_name
        domain = self.domain
        need = self.need_description
        version = self.version
        gen = self.generated_by

        # Indent subscribe calls to method-body level (8 spaces).
        if subscribe_lines:
            indented = textwrap.indent(subscribe_lines, "        ")
            init_stmts = indented + "        self._transition_state(AgentState.INITIALIZED)"
        else:
            init_stmts = "        self._transition_state(AgentState.INITIALIZED)"

        # The template uses 0-based indentation so that string substitution
        # does not produce incorrect indentation after dedent processing.
        return (
            f'"""\n'
            f'Auto-generated agent: {cn}\n'
            f'Domain: {domain}\n'
            f'Need: {need}\n'
            f'Generated by: {gen} v{version}\n'
            f'"""\n'
            f'\n'
            f'from __future__ import annotations\n'
            f'\n'
            f'import logging\n'
            f'from typing import Optional\n'
            f'\n'
            f'from genus.communication.message_bus import Message, MessageBus\n'
            f'from genus.core.agent import Agent, AgentState\n'
            f'\n'
            f'logger = logging.getLogger(__name__)\n'
            f'\n'
            f'\n'
            f'class {cn}(Agent):\n'
            f'    """Auto-generated agent for domain \'{domain}\'.\n'
            f'\n'
            f'    Need: {need}\n'
            f'\n'
            f'    This agent was generated by GENUS to address an identified need.\n'
            f'    Implement process_message() to add real behaviour.\n'
            f'    """\n'
            f'\n'
            f'    DOMAIN = "{domain}"\n'
            f'    NEED = "{need}"\n'
            f'    VERSION = {version}\n'
            f'\n'
            f'    def __init__(\n'
            f'        self,\n'
            f'        message_bus: MessageBus,\n'
            f'        agent_id: Optional[str] = None,\n'
            f'        name: Optional[str] = None,\n'
            f'    ) -> None:\n'
            f'        super().__init__(agent_id=agent_id, name=name or "{cn}")\n'
            f'        self._bus = message_bus\n'
            f'\n'
            f'    async def initialize(self) -> None:\n'
            f'        """Subscribe to relevant topics."""\n'
            f'{init_stmts}\n'
            f'\n'
            f'    async def start(self) -> None:\n'
            f'        """Transition to RUNNING state."""\n'
            f'        self._transition_state(AgentState.RUNNING)\n'
            f'\n'
            f'    async def stop(self) -> None:\n'
            f'        """Unsubscribe and transition to STOPPED state."""\n'
            f'        self._bus.unsubscribe_all(self.id)\n'
            f'        self._transition_state(AgentState.STOPPED)\n'
            f'\n'
            f'    async def process_message(self, message: Message) -> None:\n'
            f'        """Handle incoming messages.\n'
            f'\n'
            f'        TODO: Implement domain logic for \'{need}\'.\n'
            f'        """\n'
            f'        logger.info(\n'
            f'            "%s received message on topic %r",\n'
            f'            self.__class__.__name__,\n'
            f'            message.topic,\n'
            f'        )\n'
        )
