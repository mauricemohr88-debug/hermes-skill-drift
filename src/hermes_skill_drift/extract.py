"""Pure-AST extraction of statically provable Hermes capabilities."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from typing import Any

MAX_SOURCE_CHARS = 2_000_000
MAX_LITERAL_NODES = 10_000
MAX_EXCERPT_CHARS = 500
OPTION_FIELDS = frozenset(
    {
        "action",
        "choices",
        "const",
        "default",
        "dest",
        "nargs",
        "required",
        "type",
    }
)
PARSER_FIELDS = frozenset(
    {
        "aliases",
        "conflict_handler",
        "prog",
        "add_help",
        "allow_abbrev",
        "prefix_chars",
        "fromfile_prefix_chars",
        "argument_default",
        "exit_on_error",
        "parents",
    }
)
STRUCTURE_FIELDS_TO_IGNORE = frozenset({"description", "help"})


@dataclass(frozen=True)
class _Receiver:
    prefixes: tuple[tuple[str, ...], ...]
    allow_options: bool = False


class _Budget:
    def __init__(self, limit: int = MAX_LITERAL_NODES) -> None:
        self.remaining = limit


class _ScopeVisitor(ast.NodeVisitor):
    """Track argparse receivers lexically without crossing function scopes."""

    def __init__(
        self,
        path: str,
        text: str,
        warnings: set[str],
        capabilities: list[dict[str, Any]],
        function_parameter_names: frozenset[str] = frozenset(),
    ) -> None:
        self.path = path
        self.text = text
        self.warnings = warnings
        self.capabilities = capabilities
        self.receivers: dict[str, _Receiver | None] = {}
        if "subparsers" in function_parameter_names:
            # Existing Hermes setup functions use this parameter as the root
            # namespace. It is a deliberate convention, not variable-name magic.
            self.receivers["subparsers"] = _Receiver((("hermes",),), allow_options=False)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Nested functions are analyzed as independent scopes by extract_source.
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        receiver = self._receiver(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.receivers[target.id] = receiver

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
            receiver = self._receiver(node.value)
            if isinstance(node.target, ast.Name):
                self.receivers[node.target.id] = receiver

    def visit_Call(self, node: ast.Call) -> None:
        self._handle_call(node)
        self.generic_visit(node)

    def _handle_call(self, node: ast.Call) -> None:
        name = _dotted_name(node.func)
        if name.endswith("ArgumentParser"):
            prog = _keyword_value(node, "prog")
            if prog is not None and _literal(prog) == "hermes":
                signature = _filtered_call_signature(node, PARSER_FIELDS)
                if signature is None:
                    self._warning("dynamic argparse ArgumentParser structure", node)
                self._add("command", "hermes", node, signature)
            return

        if not (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"add_parser", "add_argument"}
        ):
            return

        receiver = self._receiver(node.func.value)
        if receiver is None:
            self._warning(f"unresolved argparse {node.func.attr} receiver", node)
            return

        if node.func.attr == "add_parser":
            command_value = node.args[0] if node.args else _keyword_value(node, "name")
            command = _literal(command_value) if command_value is not None else None
            aliases_value = _keyword_value(node, "aliases")
            aliases = _literal(aliases_value) if aliases_value is not None else []

            if not isinstance(command, str):
                self._warning("dynamic argparse add_parser", node)
                return
            if not isinstance(aliases, list) or not all(
                isinstance(alias, str) for alias in aliases
            ):
                self._warning("dynamic argparse add_parser aliases", node)
                aliases = []

            names = (command, *aliases)
            signature = _filtered_call_signature(node, PARSER_FIELDS)
            if signature is None:
                self._warning("dynamic argparse add_parser structure", node)
            for prefix in receiver.prefixes:
                for name_part in names:
                    self._add("command", " ".join((*prefix, name_part)), node, signature)
            return

        if not receiver.allow_options:
            if node.func.attr == "add_argument":
                self._warning("argparse add_argument outside a tracked command receiver", node)
            return

        flags: list[str] = []
        dynamic_flags = False
        positional = False
        for argument in node.args:
            flag = _literal(argument)
            if isinstance(flag, str) and flag.startswith("-"):
                flags.append(flag)
            elif isinstance(flag, str):
                positional = True
            elif flag is None:
                dynamic_flags = True

        if not flags:
            if dynamic_flags:
                self._warning("dynamic argparse add_argument flags", node)
            if positional:
                self._warning("unsupported positional argparse add_argument", node)
            return
        if dynamic_flags:
            self._warning("dynamic argparse add_argument flags", node)
        if positional:
            self._warning("unsupported positional argparse add_argument", node)

        signature = _filtered_call_signature(node, OPTION_FIELDS)
        if signature is None:
            self._warning("dynamic argparse add_argument structure", node)
        for prefix in receiver.prefixes:
            for flag in flags:
                self._add("option", " ".join((*prefix, flag)), node, signature)

    def _receiver(self, expression: ast.AST) -> _Receiver | None:
        if isinstance(expression, ast.Name):
            return self.receivers.get(expression.id)
        if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Attribute):
            return None

        if _dotted_name(expression.func).endswith("ArgumentParser"):
            prog = _keyword_value(expression, "prog")
            if prog is not None and _literal(prog) == "hermes":
                return _Receiver((("hermes",),))
            return None

        parent = self._receiver(expression.func.value)
        if parent is None:
            return None
        if expression.func.attr == "add_subparsers":
            return parent
        if expression.func.attr != "add_parser":
            return None

        command_value = (
            expression.args[0] if expression.args else _keyword_value(expression, "name")
        )
        command = _literal(command_value) if command_value is not None else None
        aliases_value = _keyword_value(expression, "aliases")
        aliases = _literal(aliases_value) if aliases_value is not None else []
        if not isinstance(command, str):
            return None
        if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
            aliases = []
        return _Receiver(
            tuple((*prefix, name) for prefix in parent.prefixes for name in (command, *aliases)),
            allow_options=True,
        )

    def _add(
        self,
        kind: str,
        key: str,
        node: ast.AST,
        signature: dict[str, Any] | None,
    ) -> None:
        self.capabilities.append(
            {
                "kind": kind,
                "key": key,
                "path": self.path,
                "line": getattr(node, "lineno", 0),
                "signature": _canonical_json(signature or {}),
                "resolved": signature is not None,
                "excerpt": _excerpt(self.text, node),
            }
        )

    def _warning(self, construct: str, node: ast.AST) -> None:
        self.warnings.add(
            f"{construct} at line {getattr(node, 'lineno', 0)} is not statically resolvable"
        )


def extract_source(path: str, text: str) -> dict[str, Any]:
    """Return statically provable capabilities and limitations for one Python source."""

    capabilities: list[dict[str, Any]] = []
    warnings: set[str] = set[str]()
    if len(text) > MAX_SOURCE_CHARS:
        return {
            "capabilities": [],
            "warnings": [f"source is too large for bounded extraction ({len(text)} characters)"],
        }

    try:
        tree = ast.parse(text, filename=path, mode="exec")
    except SyntaxError as error:
        return {
            "capabilities": [],
            "warnings": [f"parse error at line {error.lineno or 0}: {error.msg}"],
        }

    scopes: list[tuple[list[ast.stmt], frozenset[str]]] = [(tree.body, frozenset())]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scopes.append((node.body, frozenset(arg.arg for arg in node.args.args)))

    for body, parameters in scopes:
        visitor = _ScopeVisitor(path, text, warnings, capabilities, parameters)
        for statement in body:
            visitor.visit(statement)

    _extract_tool_schemas(tree, path, text, warnings, capabilities)
    capabilities.sort(
        key=lambda item: tuple(
            item[field] for field in ("kind", "key", "path", "line", "signature", "excerpt")
        )
    )
    return {"capabilities": capabilities, "warnings": sorted(warnings)}


def _extract_tool_schemas(
    tree: ast.AST,
    path: str,
    text: str,
    warnings: set[str],
    capabilities: list[dict[str, Any]],
) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue

        candidates = [node]
        wrapper_type = _dict_value(node, "type")
        function_value = _dict_value(node, "function")
        if wrapper_type == "function" and isinstance(function_value, ast.Dict):
            candidates.append(function_value)

        for candidate in candidates:
            name_value = _dict_value(candidate, "name", static_only=True)
            parameters_value = _dict_value(candidate, "parameters", static_only=True)
            if name_value is None or parameters_value is None:
                continue
            name = _bounded_literal(name_value, _Budget()) if name_value is not None else None
            parameters = (
                _bounded_literal(parameters_value, _Budget())
                if parameters_value is not None
                else None
            )
            if not isinstance(name, str) or not isinstance(parameters, dict):
                warnings.add(
                    f"dynamic or malformed tool schema at line {getattr(candidate, 'lineno', 0)} "
                    "is not statically resolvable"
                )
                if isinstance(name, str):
                    capabilities.append(
                        {
                            "kind": "tool",
                            "key": name,
                            "path": path,
                            "line": candidate.lineno,
                            "signature": "{}",
                            "resolved": False,
                            "excerpt": _excerpt(text, candidate),
                        }
                    )
                continue
            structural = _remove_ignored_fields(parameters)
            signature = _canonical_json(structural)
            if signature is None:
                warnings.add(
                    f"dynamic or malformed tool schema at line {getattr(candidate, 'lineno', 0)} "
                    "is not statically resolvable"
                )
                continue
            capabilities.append(
                {
                    "kind": "tool",
                    "key": name,
                    "path": path,
                    "line": candidate.lineno,
                    "signature": signature,
                    "resolved": True,
                    "excerpt": _excerpt(text, candidate),
                }
            )


def _dotted_name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _keyword_value(node: ast.Call, keyword: str) -> ast.AST | None:
    for item in node.keywords:
        if item.arg == keyword:
            return item.value
    return None


def _dict_value(node: ast.Dict, key: str, static_only: bool = False) -> ast.AST | None:
    for key_node, value in zip(node.keys, node.values, strict=True):
        key_value = _bounded_literal(key_node, _Budget()) if static_only else _literal(key_node)
        if key_value == key:
            return value
    return None


def _filtered_call_signature(node: ast.Call, relevant: frozenset[str]) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    for keyword in node.keywords:
        if keyword.arg is None:
            return None
        if keyword.arg not in relevant:
            continue
        if keyword.arg == "type":
            symbolic_type = _builtin_type_name(keyword.value)
            if symbolic_type is None:
                return None
            result["type"] = symbolic_type
            continue
        resolved, value = _resolved_literal(keyword.value)
        if not resolved:
            return None
        result[keyword.arg] = value
    if _canonical_json(result) is None:
        return None
    return result


def _builtin_type_name(node: ast.AST) -> str | None:
    name = _dotted_name(node)
    return name if name in {"str", "int", "float"} else None


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    return _bounded_literal(node, _Budget())


def _resolved_literal(node: ast.AST | None) -> tuple[bool, Any]:
    if node is None:
        return False, None
    budget = _Budget()
    if not _is_bounded_literal(node, budget):
        return False, None
    try:
        return True, ast.literal_eval(node)
    except (TypeError, ValueError):
        return False, None


def _bounded_literal(node: ast.AST | None, budget: _Budget) -> Any:
    if node is None:
        return None
    if not _is_bounded_literal(node, budget):
        return None
    try:
        return ast.literal_eval(node)
    except (TypeError, ValueError):
        return None


def _is_bounded_literal(node: ast.AST, budget: _Budget) -> bool:
    budget.remaining -= 1
    if budget.remaining < 0:
        return False
    if isinstance(node, ast.Constant) and isinstance(
        node.value, (str, bytes, bool, int, float, complex, type(None))
    ):
        return True
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(_is_bounded_literal(child, budget) for child in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and _is_bounded_literal(key, budget)
            and _is_bounded_literal(value, budget)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return _is_bounded_literal(node.operand, budget)
    return False


def _remove_ignored_fields(value: Any, in_properties: bool = False) -> Any:
    if isinstance(value, dict):
        if in_properties:
            # Property/definition names are user data, even when named "description".
            return {key: _remove_ignored_fields(child) for key, child in value.items()}
        return {
            key: (
                child
                if key in {"enum", "const", "default", "examples"}
                else _remove_ignored_fields(
                    child,
                    in_properties=key
                    in {
                        "properties",
                        "patternProperties",
                        "$defs",
                        "definitions",
                        "dependentSchemas",
                    },
                )
            )
            for key, child in value.items()
            if key not in STRUCTURE_FIELDS_TO_IGNORE
        }
    if isinstance(value, list):
        return [_remove_ignored_fields(child) for child in value]
    return value


def _canonical_json(value: Any) -> str | None:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def _excerpt(text: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(text, node)
    return (segment or "")[:MAX_EXCERPT_CHARS]
