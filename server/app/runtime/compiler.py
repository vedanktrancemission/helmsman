"""Compiles a graph_spec dict into a runnable LangGraph StateGraph."""
from __future__ import annotations

import operator
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.runtime.nodes import ExecContext, make_agent_node

DEFAULT_RECURSION_LIMIT = 25
_SAFE_BUILTINS = {"len": len, "any": any, "all": all, "min": min, "max": max, "sum": sum}


def _merge_dict(a: dict, b: dict) -> dict:
    out = dict(a)
    out.update(b)
    return out


class GraphState(TypedDict, total=False):
    """Shared mutable state passed between all nodes in a workflow run."""
    input: str
    history: Annotated[list, operator.add]
    outputs: Annotated[dict, _merge_dict]
    final: str
    steps: int


class WorkflowSpecError(ValueError):
    """Raised when a graph_spec is structurally invalid."""


def _resolve_agent(node: dict, agent_lookup: dict[str, dict]) -> dict:
    if node.get("agent"):
        return node["agent"]
    agent_id = node.get("agent_id")
    if agent_id and agent_id in agent_lookup:
        return agent_lookup[agent_id]
    raise WorkflowSpecError(
        f"node '{node.get('name')}' has no resolvable agent (agent_id={agent_id!r})"
    )


def _make_router(condition: str, source_name: str, branch_keys: set[str]) -> Callable[[dict], str]:
    code = compile(condition, "<condition>", "eval")

    def router(state: dict) -> str:
        ns = {
            "outputs": state.get("outputs", {}),
            "last_output": state.get("outputs", {}).get(source_name, ""),
            "steps": state.get("steps", 0),
            "input": state.get("input", ""),
            "history": state.get("history", []),
        }
        try:
            result = eval(code, {"__builtins__": _SAFE_BUILTINS}, ns)  # noqa: S307
        except Exception:  # noqa: BLE001
            result = False
        if isinstance(result, bool):
            key = "true" if result else "false"
        else:
            key = str(result)
        if key not in branch_keys:
            key = "default" if "default" in branch_keys else next(iter(branch_keys))
        return key

    return router


def validate_spec(spec: dict) -> None:
    """Raise WorkflowSpecError if the spec is structurally invalid."""
    if not spec.get("nodes"):
        raise WorkflowSpecError("graph_spec has no nodes")
    names = [n["name"] for n in spec["nodes"]]
    if len(names) != len(set(names)):
        raise WorkflowSpecError("node names must be unique")
    if spec.get("entry") not in names:
        raise WorkflowSpecError(f"entry '{spec.get('entry')}' is not a known node")
    valid_targets = set(names) | {"END", "__end__"}
    for e in spec.get("edges", []):
        if e["source"] not in names:
            raise WorkflowSpecError(f"edge source '{e['source']}' is unknown")
        if e.get("conditional"):
            for target in e.get("branches", {}).values():
                if target not in valid_targets:
                    raise WorkflowSpecError(f"branch target '{target}' is unknown")
        elif e.get("target") not in valid_targets:
            raise WorkflowSpecError(f"edge target '{e.get('target')}' is unknown")


def compile_graph(spec: dict, ctx: ExecContext, agent_lookup: dict[str, dict] | None = None):
    """Compile a graph_spec into a runnable LangGraph app."""
    agent_lookup = agent_lookup or {}
    validate_spec(spec)

    g = StateGraph(GraphState)
    for node in spec["nodes"]:
        agent_cfg = _resolve_agent(node, agent_lookup)
        g.add_node(node["name"], make_agent_node(agent_cfg, ctx, node["name"]))

    g.add_edge(START, spec["entry"])

    def _norm(target: str) -> Any:
        return END if target in ("END", "__end__") else target

    for e in spec.get("edges", []):
        if e.get("conditional"):
            mapping = {key: _norm(target) for key, target in e["branches"].items()}
            router = _make_router(e["condition"], e["source"], set(mapping))
            g.add_conditional_edges(e["source"], router, mapping)
        else:
            g.add_edge(e["source"], _norm(e["target"]))

    return g.compile()


def recursion_limit(spec: dict) -> int:
    return int(spec.get("recursion_limit", DEFAULT_RECURSION_LIMIT))
