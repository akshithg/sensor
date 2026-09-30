"""Build lightweight API-usage and change graphs from Clang's C AST."""

from __future__ import annotations

import bisect
import json
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from typing import Any

JsonObject = dict[str, Any]

_ASSIGNMENT = re.compile(
    r"(?:^|[;{}])\s*(?:const\s+)?(?:unsigned\s+|struct\s+\w+\s+)?"
    r"(?:int|long|char|size_t|ssize_t|void\s*\*|[A-Za-z_]\w*\s*\*)\s*"
    r"([A-Za-z_]\w*)\s*=\s*$"
)
_IDENTIFIER = re.compile(r"\b[A-Za-z_]\w*\b")
_IGNORED_CALLS = {"audit_event"}


class AnalysisError(RuntimeError):
    """Raised when a source file cannot be converted into a graph."""


@dataclass(frozen=True)
class _Event:
    """An action or guard located in the source stream."""

    offset: int
    kind: str
    label: str
    line: int
    snippet: str
    references: tuple[str, ...]
    result: str | None = None


def _walk(node: JsonObject) -> list[JsonObject]:
    nodes = [node]
    for child in node.get("inner", []):
        if isinstance(child, dict):
            nodes.extend(_walk(child))
    return nodes


def _offset(node: JsonObject, endpoint: str = "begin") -> int | None:
    range_data = node.get("range", {})
    location = range_data.get(endpoint, {})
    value = location.get("offset")
    return value if isinstance(value, int) else None


def _line_starts(source: str) -> list[int]:
    return [0, *(match.end() for match in re.finditer("\n", source))]


def _line_for_offset(starts: list[int], offset: int) -> int:
    return bisect.bisect_right(starts, offset)


def _source_slice(source: str, node: JsonObject) -> str:
    begin = _offset(node)
    end = _offset(node, "end")
    if begin is None or end is None:
        return ""
    token_length = node.get("range", {}).get("end", {}).get("tokLen", 1)
    return source[begin : end + token_length].strip()


def _callee_name(call: JsonObject) -> str | None:
    for node in _walk(call):
        if node.get("kind") != "DeclRefExpr":
            continue
        declaration = node.get("referencedDecl", {})
        if declaration.get("kind") == "FunctionDecl":
            name = declaration.get("name")
            return name if isinstance(name, str) else None
    return None


def _references(node: JsonObject) -> tuple[str, ...]:
    names: list[str] = []
    for item in _walk(node):
        if item.get("kind") != "DeclRefExpr":
            continue
        declaration = item.get("referencedDecl", {})
        if declaration.get("kind") not in {"VarDecl", "ParmVarDecl"}:
            continue
        name = declaration.get("name")
        if isinstance(name, str) and name not in names:
            names.append(name)
    return tuple(names)


def _assignment_target(source: str, call_offset: int) -> str | None:
    prefix_start = max(source.rfind("\n", 0, call_offset), source.rfind(";", 0, call_offset))
    prefix = source[prefix_start + 1 : call_offset]
    match = _ASSIGNMENT.search(prefix)
    return match.group(1) if match else None


def _clang_ast(source: str) -> JsonObject:
    clang = shutil.which("clang")
    if clang is None:
        raise AnalysisError("clang is required to analyze C source; install Clang and retry")
    command = [
        clang,
        "-x",
        "c",
        "-std=c11",
        "-fsyntax-only",
        "-Wno-everything",
        "-Xclang",
        "-ast-dump=json",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            input=source,
            capture_output=True,
            check=False,
            text=True,
            timeout=8,
        )
    except subprocess.TimeoutExpired as error:
        raise AnalysisError("clang timed out while parsing the submitted source") from error
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        message = detail[-1] if detail else "unknown compiler error"
        raise AnalysisError(f"clang could not parse the submitted source: {message}")
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AnalysisError("clang returned an unreadable AST") from error
    if not isinstance(parsed, dict):
        raise AnalysisError("clang returned an unexpected AST root")
    return parsed


def _function_events(function: JsonObject, source: str, starts: list[int]) -> list[_Event]:
    events: list[_Event] = []
    for node in _walk(function):
        kind = node.get("kind")
        offset = _offset(node)
        if offset is None:
            continue
        if kind == "CallExpr":
            name = _callee_name(node)
            if name is None:
                continue
            events.append(
                _Event(
                    offset=offset,
                    kind="action",
                    label=name,
                    line=_line_for_offset(starts, offset),
                    snippet=_source_slice(source, node),
                    references=_references(node),
                    result=_assignment_target(source, offset),
                )
            )
        elif kind == "IfStmt":
            children = [child for child in node.get("inner", []) if isinstance(child, dict)]
            if not children:
                continue
            condition = children[0]
            snippet = _source_slice(source, condition)
            events.append(
                _Event(
                    offset=offset,
                    kind="guard",
                    label=snippet or "condition",
                    line=_line_for_offset(starts, offset),
                    snippet=snippet,
                    references=_references(condition),
                )
            )
    return sorted(events, key=lambda event: (event.offset, event.kind != "guard"))


def _build_graph(function_name: str, events: list[_Event]) -> JsonObject:
    nodes: list[JsonObject] = []
    edges: list[JsonObject] = []
    data_nodes: dict[str, str] = {}
    event_ids: list[str] = []
    occurrence: Counter[tuple[str, str]] = Counter()

    for event in events:
        key = (event.kind, event.label)
        occurrence[key] += 1
        node_id = f"{event.kind}:{event.label}:{occurrence[key]}"
        event_ids.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "kind": event.kind,
                "label": event.label,
                "line": event.line,
                "snippet": event.snippet,
            }
        )
        if len(event_ids) > 1:
            edges.append({"from": event_ids[-2], "to": node_id, "kind": "control"})
        if event.result:
            data_id = data_nodes.setdefault(event.result, f"data:{event.result}")
            if not any(node["id"] == data_id for node in nodes):
                nodes.append(
                    {"id": data_id, "kind": "data", "label": event.result, "line": event.line}
                )
            edges.append({"from": node_id, "to": data_id, "kind": "result"})
        for reference in event.references:
            data_id = data_nodes.get(reference)
            if data_id and data_id != node_id:
                edge = {"from": data_id, "to": node_id, "kind": "data"}
                if edge not in edges:
                    edges.append(edge)

    return {"function": function_name, "nodes": nodes, "edges": edges}


def analyze_source(source: str) -> JsonObject:
    """Analyze one self-contained C translation unit.

    Args:
        source: Complete C source, including prototypes for called APIs.

    Returns:
        A JSON-compatible analysis containing per-function and aggregate graphs.

    Raises:
        AnalysisError: If Clang is unavailable or cannot parse the source.
    """
    if not source.strip():
        raise AnalysisError("source is empty; provide a C function to analyze")
    ast = _clang_ast(source)
    starts = _line_starts(source)
    graphs: list[JsonObject] = []
    for node in _walk(ast):
        if node.get("kind") != "FunctionDecl":
            continue
        children = [child for child in node.get("inner", []) if isinstance(child, dict)]
        if not any(child.get("kind") == "CompoundStmt" for child in children):
            continue
        name = node.get("name")
        if not isinstance(name, str):
            continue
        events = _function_events(node, source, starts)
        if events:
            graphs.append(_build_graph(name, events))
    if not graphs:
        raise AnalysisError("no function containing an API call or guard was found")

    nodes = [node for graph in graphs for node in graph["nodes"]]
    edges = [edge for graph in graphs for edge in graph["edges"]]
    calls = [node["label"] for node in nodes if node["kind"] == "action"]
    return {"functions": graphs, "graph": {"nodes": nodes, "edges": edges}, "calls": calls}


def _ordered_pairs(calls: list[str]) -> set[tuple[str, str]]:
    relevant = [call for call in calls if call not in _IGNORED_CALLS]
    return {
        (first, second)
        for index, first in enumerate(relevant)
        for second in relevant[index + 1 :]
        if first != second
    }


def mine_patterns(analyses: list[JsonObject], minimum_support: float = 1.0) -> list[JsonObject]:
    """Mine ordered API-call pairs that recur across trusted analyses."""
    if not analyses:
        return []
    counts: Counter[tuple[str, str]] = Counter()
    for analysis in analyses:
        counts.update(_ordered_pairs(analysis["calls"]))
    patterns = []
    for (first, second), count in sorted(counts.items()):
        support = count / len(analyses)
        if support >= minimum_support:
            patterns.append(
                {
                    "from": first,
                    "to": second,
                    "kind": "ordered-call",
                    "support": round(support, 2),
                }
            )
    return patterns


def score_against_patterns(analysis: JsonObject, patterns: list[JsonObject]) -> JsonObject:
    """Score one analysis by the trusted call pairs it does not contain."""
    actual = _ordered_pairs(analysis["calls"])
    guards = [node["label"] for node in analysis["graph"]["nodes"] if node["kind"] == "guard"]
    missing = []
    for pattern in patterns:
        if pattern["kind"] == "ordered-call":
            if (pattern["from"], pattern["to"]) not in actual and pattern["from"] in analysis[
                "calls"
            ]:
                missing.append(pattern)
        elif pattern["kind"] == "required-guard":
            terms = pattern["contains"]
            if not any(all(term in guard for term in terms) for guard in guards):
                missing.append(pattern)
    risk = min(
        96,
        sum(82 if pattern["kind"] == "required-guard" else 38 for pattern in missing),
    )
    findings = []
    for pattern in missing:
        if pattern["kind"] == "required-guard":
            findings.append(
                {
                    "severity": "high",
                    "title": "Unchecked shift may overflow",
                    "detail": pattern["detail"],
                    "expected": pattern["label"],
                    "support": pattern["support"],
                }
            )
            continue
        is_cleanup = pattern["to"] in {"close", "free", "fclose", "unlock", "release"}
        findings.append(
            {
                "severity": "high" if is_cleanup else "medium",
                "title": "Resource lifecycle diverges" if is_cleanup else "API sequence diverges",
                "detail": (
                    f"Trusted revisions always call {pattern['to']} after {pattern['from']}; "
                    "this revision does not."
                ),
                "expected": f"{pattern['from']} -> {pattern['to']}",
                "support": pattern["support"],
            }
        )
    return {"risk": risk, "missing_patterns": missing, "findings": findings}


def build_change_graph(before: JsonObject, after: JsonObject) -> JsonObject:
    """Combine two API-usage graphs and label nodes by revision status."""
    before_nodes = {node["id"]: node for node in before["graph"]["nodes"]}
    after_nodes = {node["id"]: node for node in after["graph"]["nodes"]}
    nodes = []
    for node_id in sorted(before_nodes.keys() | after_nodes.keys()):
        if node_id in before_nodes and node_id in after_nodes:
            status = "unchanged"
            node = after_nodes[node_id]
        elif node_id in after_nodes:
            status = "added"
            node = after_nodes[node_id]
        else:
            status = "removed"
            node = before_nodes[node_id]
        nodes.append({**node, "status": status})
    return {
        "nodes": nodes,
        "edges": after["graph"]["edges"],
        "summary": {
            "added": sum(node["status"] == "added" for node in nodes),
            "removed": sum(node["status"] == "removed" for node in nodes),
            "unchanged": sum(node["status"] == "unchanged" for node in nodes),
        },
    }
