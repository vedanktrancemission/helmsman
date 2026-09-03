"""Compiles a graph_spec dict into a runnable LangGraph StateGraph."""
from __future__ import annotations

import operator
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.runtime.control import (
    CONTROL_TYPES,
    DEFAULT_MAX_ITERATIONS,
    LOOP_TYPES,
    REQUIRED_CONFIG,
    ControlSpecError,
    branch_keys,
    compile_expr,
    eval_expr,
    is_control,
    make_control_node,
    max_iterations,
    node_type,
)
from app.runtime.nodes import ExecContext, make_agent_node

DEFAULT_RECURSION_LIMIT = 25
_END_NAMES = ("END", "__end__")


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
    branch: Annotated[dict, _merge_dict]
    loop: Annotated[dict, _merge_dict]


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


def _make_router(condition: str, source_name: str, branch_keys_: set[str]) -> Callable[[dict], str]:
    """Router for a legacy conditional *edge* (condition lives on the edge)."""
    code = compile_expr(condition, f"condition:{source_name}")

    def router(state: dict) -> str:
        result = eval_expr(
            code, state, node_name=source_name,
            extra={"last_output": (state.get("outputs") or {}).get(source_name, "")},
            default=False,
        )
        key = ("true" if result else "false") if isinstance(result, bool) else str(result)
        if key not in branch_keys_:
            key = "default" if "default" in branch_keys_ else next(iter(branch_keys_))
        return key

    return router


def _make_branch_router(name: str, keys: list[str]) -> Callable[[dict], str]:
    """Router for a control *node*: replays the decision the node recorded."""
    fallback = "default" if "default" in keys else ("exit" if "exit" in keys else keys[0])

    def router(state: dict) -> str:
        key = (state.get("branch") or {}).get(name)
        return key if key in keys else fallback

    return router


def _norm(target: str) -> Any:
    return END if target in _END_NAMES else target


def _validate_control_node(node: dict, valid_targets: set[str], outgoing: dict[str, str]) -> None:
    kind = node_type(node)
    name = node["name"]
    field = REQUIRED_CONFIG[kind]
    cfg = node.get("config") or {}
    if not str(cfg.get(field, "")).strip():
        raise WorkflowSpecError(f"{kind} node '{name}' needs a '{field}' expression")
    try:
        compile_expr(cfg[field], f"{kind}:{name}")
    except ControlSpecError as exc:
        raise WorkflowSpecError(str(exc)) from exc

    keys = branch_keys(node)
    if kind == "switch" and len(keys) < 2:
        raise WorkflowSpecError(f"switch node '{name}' needs at least one case")
    for key, target in outgoing.items():
        if key not in keys:
            raise WorkflowSpecError(
                f"{kind} node '{name}' has no branch '{key}' (expected one of {', '.join(keys)})"
            )
        if target not in valid_targets:
            raise WorkflowSpecError(f"branch target '{target}' is unknown")
    if kind in LOOP_TYPES and "body" not in outgoing:
        raise WorkflowSpecError(f"{kind} node '{name}' must wire its 'body' branch to a node")
    if not outgoing:
        raise WorkflowSpecError(f"{kind} node '{name}' has no outgoing branches")


def _branch_map(spec: dict) -> dict[str, dict[str, str]]:
    """Outgoing branch edges of every control node, keyed by node then branch."""
    controls = {n["name"] for n in spec["nodes"] if is_control(n)}
    out: dict[str, dict[str, str]] = {name: {} for name in controls}
    for e in spec.get("edges", []):
        source = e.get("source")
        if source not in controls:
            continue
        key = e.get("branch")
        if key is None:
            raise WorkflowSpecError(
                f"edge from control node '{source}' must name a 'branch' "
                f"(one of {', '.join(branch_keys(next(n for n in spec['nodes'] if n['name'] == source)))})"
            )
        key = str(key)
        if key in out[source]:
            raise WorkflowSpecError(f"control node '{source}' has duplicate branch '{key}'")
        out[source][key] = str(e.get("target", "END"))
    return out


def validate_spec(spec: dict) -> None:
    """Raise WorkflowSpecError if the spec is structurally invalid."""
    if not spec.get("nodes"):
        raise WorkflowSpecError("graph_spec has no nodes")
    names = [n["name"] for n in spec["nodes"]]
    if len(names) != len(set(names)):
        raise WorkflowSpecError("node names must be unique")
    for node in spec["nodes"]:
        kind = node_type(node)
        if kind != "agent" and kind not in CONTROL_TYPES:
            raise WorkflowSpecError(
                f"node '{node['name']}' has unknown type '{kind}' "
                f"(expected agent, {', '.join(CONTROL_TYPES)})"
            )
    if spec.get("entry") not in names:
        raise WorkflowSpecError(f"entry '{spec.get('entry')}' is not a known node")

    valid_targets = set(names) | set(_END_NAMES)
    branches = _branch_map(spec)
    for node in spec["nodes"]:
        if is_control(node):
            _validate_control_node(node, valid_targets, branches[node["name"]])

    for e in spec.get("edges", []):
        if e["source"] not in names:
            raise WorkflowSpecError(f"edge source '{e['source']}' is unknown")
        if e["source"] in branches:
            continue  # already checked as a control branch
        if e.get("conditional"):
            try:
                compile_expr(e.get("condition", "False"), f"condition:{e['source']}")
            except ControlSpecError as exc:
                raise WorkflowSpecError(str(exc)) from exc
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
    controls: dict[str, dict] = {}
    for node in spec["nodes"]:
        if is_control(node):
            controls[node["name"]] = node
            g.add_node(node["name"], make_control_node(node, ctx))
        else:
            agent_cfg = _resolve_agent(node, agent_lookup)
            g.add_node(node["name"], make_agent_node(agent_cfg, ctx, node["name"]))

    g.add_edge(START, spec["entry"])

    # Control nodes: one conditional fan-out per node, covering every branch it
    # exposes. Branches the author left unwired terminate the run.
    branches = _branch_map(spec)
    for name, node in controls.items():
        keys = branch_keys(node)
        wired = branches[name]
        mapping = {key: _norm(wired.get(key, "END")) for key in keys}
        g.add_conditional_edges(name, _make_branch_router(name, keys), mapping)

    for e in spec.get("edges", []):
        if e["source"] in controls:
            continue
        if e.get("conditional"):
            mapping = {key: _norm(target) for key, target in e["branches"].items()}
            router = _make_router(e["condition"], e["source"], set(mapping))
            g.add_conditional_edges(e["source"], router, mapping)
        else:
            g.add_edge(e["source"], _norm(e["target"]))

    return g.compile()


def recursion_limit(spec: dict) -> int:
    """Superstep budget: the declared value, else a loop-aware default."""
    declared = spec.get("recursion_limit")
    if declared:
        return int(declared)
    loops = [n for n in spec.get("nodes", []) if node_type(n) in LOOP_TYPES]
    if not loops:
        return DEFAULT_RECURSION_LIMIT
    body_cost = max(2, len(spec.get("nodes", [])) - 1)
    budget = DEFAULT_RECURSION_LIMIT
    for node in loops:
        budget += (max_iterations(node) + 1) * body_cost
    return budget


__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_RECURSION_LIMIT",
    "GraphState",
    "WorkflowSpecError",
    "compile_graph",
    "recursion_limit",
    "validate_spec",
]
