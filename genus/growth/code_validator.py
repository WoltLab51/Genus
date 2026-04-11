"""
Code Validator

Statische Validierung von generiertem Agent-Code vor dem Import.

Stufe 1: AST-basierter Security-Scan (verbotene Calls)
Stufe 2: Import-Whitelist (nur erlaubte Top-Level-Module)
Stufe 3: Struktur-Check (Agent-Subklasse + Lifecycle-Methoden)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass
class ValidationResult:
    """Ergebnis einer Code-Validierung.

    Attributes:
        passed:   ``True`` wenn keine kritischen Fehler gefunden wurden.
        errors:   Kritische Fehler — führen zur Ablehnung des Codes.
        warnings: Nicht-kritische Hinweise (z. B. fehlende Lifecycle-Methoden).
    """

    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class CodeValidator:
    """Statische + strukturelle Validierung von generiertem Agent-Code.

    Stufe 1: AST-basierter Security-Scan (verbotene Calls)
    Stufe 2: Import-Whitelist (nur erlaubte Top-Level-Module)
    Stufe 3: Struktur-Check (Agent-Subklasse, Lifecycle-Methoden)

    Args:
        allowed_imports:    Set erlaubter Top-Level-Module.
                            Default enthält genus, typing, asyncio, logging, u.a.
        require_agent_base: Ob die Klasse von ``Agent`` erben muss. Default: ``True``.
        require_lifecycle:  Ob initialize/start/stop/process_message vorhanden
                            sein müssen. Default: ``True``.
    """

    BANNED_CALLS: Set[str] = {
        "eval",
        "exec",
        "compile",
        "__import__",
        "os.system",
        "os.popen",
        "os.execv",
        "os.execve",
        "subprocess.call",
        "subprocess.run",
        "subprocess.Popen",
        "socket.socket",
        "socket.connect",
    }

    _DEFAULT_ALLOWED_IMPORTS: frozenset = frozenset(
        {
            "__future__",
            "genus",
            "typing",
            "asyncio",
            "logging",
            "dataclasses",
            "datetime",
            "json",
            "pathlib",
            "collections",
            "functools",
            "itertools",
            "re",
            "enum",
            "abc",
            "copy",
            "math",
            "os.path",
        }
    )

    def __init__(
        self,
        allowed_imports: Optional[Set[str]] = None,
        require_agent_base: bool = True,
        require_lifecycle: bool = True,
    ) -> None:
        self.allowed_imports: Set[str] = (
            set(allowed_imports)
            if allowed_imports is not None
            else set(self._DEFAULT_ALLOWED_IMPORTS)
        )
        self.require_agent_base = require_agent_base
        self.require_lifecycle = require_lifecycle

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, code: str, filename: str = "<generated>") -> ValidationResult:
        """Führt alle Validierungsstufen durch.

        1. Syntax-Check via ``ast.parse()``.
        2. AST-Walk: verbotene Calls, verbotene Imports.
        3. Struktur-Check: Agent-Subklasse, Lifecycle-Methoden.

        Gibt :class:`ValidationResult` zurück — wirft **keine** Exceptions.

        Args:
            code:     Python-Quellcode als String.
            filename: Dateiname für Fehlermeldungen (Standard: ``"<generated>"``).

        Returns:
            :class:`ValidationResult` mit ``passed``, ``errors`` und ``warnings``.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Stage 1: Syntax check
        syntax_error = self._check_syntax(code, filename)
        if syntax_error:
            return ValidationResult(passed=False, errors=[syntax_error])

        # Parse AST (safe — syntax already verified)
        tree = ast.parse(code, filename=filename)

        # Stage 2: Banned calls
        errors.extend(self._check_banned_calls(tree))

        # Stage 3: Import whitelist
        errors.extend(self._check_imports(tree))

        # Stage 4: Agent structure (warnings only)
        warnings.extend(self._check_agent_structure(tree))

        passed = len(errors) == 0
        return ValidationResult(passed=passed, errors=errors, warnings=warnings)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_syntax(self, code: str, filename: str = "<generated>") -> Optional[str]:
        """Gibt Fehlermeldung zurück wenn Syntax-Fehler, sonst ``None``."""
        try:
            ast.parse(code, filename=filename)
            return None
        except SyntaxError as exc:
            return (
                f"Syntax error in {filename} at line {exc.lineno}: {exc.msg}"
            )

    def _check_banned_calls(self, tree: ast.AST) -> List[str]:
        """Findet alle verbotenen Funktionsaufrufe via AST-Walk."""
        found: List[str] = []
        seen: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = self._get_call_name(node)
                if name and name in self.BANNED_CALLS and name not in seen:
                    found.append(f"Banned call: {name}")
                    seen.add(name)
        return found

    def _check_imports(self, tree: ast.AST) -> List[str]:
        """Findet alle nicht-whitelisted Imports."""
        found: List[str] = []
        seen: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name
                    top_level = module_name.split(".")[0]
                    if not self._is_import_allowed(module_name, top_level):
                        key = f"import:{module_name}"
                        if key not in seen:
                            found.append(f"Banned import: {module_name}")
                            seen.add(key)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module
                    top_level = module_name.split(".")[0]
                    if not self._is_import_allowed(module_name, top_level):
                        key = f"import:{module_name}"
                        if key not in seen:
                            found.append(f"Banned import: {module_name}")
                            seen.add(key)
        return found

    def _check_agent_structure(self, tree: ast.AST) -> List[str]:
        """Prüft ob eine Agent-Subklasse mit Lifecycle-Methoden vorhanden ist."""
        warnings: List[str] = []

        if not self.require_agent_base and not self.require_lifecycle:
            return warnings

        # Find class definitions that inherit from Agent
        agent_classes: List[ast.ClassDef] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                base_names = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_names.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        base_names.append(base.attr)
                if "Agent" in base_names:
                    agent_classes.append(node)

        if self.require_agent_base and not agent_classes:
            warnings.append("No class inheriting from Agent found")
            return warnings

        if self.require_lifecycle and agent_classes:
            required_methods = {"initialize", "start", "stop", "process_message"}
            for cls in agent_classes:
                defined_methods: Set[str] = set()
                for child in ast.walk(cls):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        defined_methods.add(child.name)
                missing = required_methods - defined_methods
                if missing:
                    warnings.append(
                        f"Class {cls.name} is missing lifecycle methods: "
                        f"{', '.join(sorted(missing))}"
                    )

        return warnings

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_call_name(node: ast.Call) -> Optional[str]:
        """Extrahiert den vollen Namen einer Call-Expression."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            parts: List[str] = []
            current: ast.expr = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                return ".".join(reversed(parts))
        return None

    def _is_import_allowed(self, module_name: str, top_level: str) -> bool:
        """Prüft ob ein Modul-Import in der Whitelist ist."""
        # Exact match (e.g., "os.path")
        if module_name in self.allowed_imports:
            return True
        # Top-level prefix match (e.g., "genus" allows "genus.communication.message_bus")
        if top_level in self.allowed_imports:
            return True
        return False
