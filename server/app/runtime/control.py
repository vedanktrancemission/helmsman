"""Control-flow node factories: if/else, switch, while, and for.

Control nodes carry no agent and cost no tokens. Each one evaluates a small
Python expression against the run state, records its decision under
``state["branch"][node_name]``, and lets the compiler's branch router fan out to
the matching outgoing edge. Loop nodes additionally keep per-node bookkeeping
under ``state["loop"][node_name]`` (index, iteration count, current item and the
outputs collected so far), which downstream expressions and agent prompts can
read.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.runtime.nodes import ExecContext

DEFAULT_MAX_ITERATIONS = 10
ACTIVE_KEY = "__active__"

CONTROL_TYPES: dict[str, tuple[str, ...]] = {
    "if": ("true", "false"),
    "switch": ("default",),
    "while": ("body", "exit"),
    "for": ("body", "exit"),
}

#: config field each control type needs, and the branch a loop body must be wired to
REQUIRED_CONFIG: dict[str, str] = {
    "if": "condition",
    "switch": "expression",
    "while": "condition",
    "for": "items",
}
LOOP_TYPES = ("while", "for")

_SAFE_BUILTINS = {
    "len": len, "any": any, "all": all, "min": min, "max": max, "sum": sum,
    "abs": abs, "sorted": sorted, "str": str, "int": int, "float": float,
    "bool": bool, "list": list, "dict": dict, "set": set, "range": range,
    "enumerate": enumerate, "round": round,
}


class ControlSpecError(ValueError):
    """Raised when a control node's configuration is unusable."""


def node_type(node: dict) -> str:
    """The declared node type, defaulting to ``agent`` for legacy specs."""
    return (node.get("type") or "agent").strip() or "agent"


def is_control(node: dict) -> bool:
    return node_type(node) in CONTROL_TYPES


def branch_keys(node: dict) -> list[str]:
    """Every branch handle a control node exposes, in display order."""
    kind = node_type(node)
    if kind not in CONTROL_TYPES:
        return []
    if kind == "switch":
        cases = (node.get("config") or {}).get("cases") or []
        keys = [str(c) for c in cases if str(c) != "default"]
        return [*keys, "default"]
    return list(CONTROL_TYPES[kind])


def max_iterations(node: dict) -> int:
    raw = (node.get("config") or {}).get("max_iterations", DEFAULT_MAX_ITERATIONS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_ITERATIONS
    return max(1, value)


def compile_expr(expr: str, label: str) -> Any:
    """Compile an expression, raising ControlSpecError on a syntax error."""
    try:
        return compile(str(expr), f"<{label}>", "eval")
    except SyntaxError as exc:
        raise ControlSpecError(f"{label}: invalid expression {expr!r} ({exc.msg})") from exc


def loop_view(state: dict) -> dict:
    """Loop bookkeeping without the internal active-loop marker."""
    return {k: v for k, v in (state.get("loop") or {}).items() if k != ACTIVE_KEY}


def active_loop(state: dict) -> tuple[str, dict] | tuple[None, None]:
    """The innermost loop entered so far, as (node_name, entry)."""
    loops = state.get("loop") or {}
    name = loops.get(ACTIVE_KEY)
    if name and isinstance(loops.get(name), dict):
        return name, loops[name]
    return None, None


def namespace(state: dict, node_name: str | None = None, overrides: dict | None = None) -> dict:
    """The variables an expression may read."""
    _, active = active_loop(state)
    own = (state.get("loop") or {}).get(node_name) if node_name else None
    ctx = overrides or (own if isinstance(own, dict) else None) or active or {}
    return {
        "input": state.get("input", ""),
        "outputs": state.get("outputs") or {},
        "history": state.get("history") or [],
        "last_output": state.get("final", ""),
        "final": state.get("final", ""),
        "steps": state.get("steps", 0),
        "loop": loop_view(state),
        "item": ctx.get("item"),
        "index": ctx.get("index", 0),
        "count": ctx.get("count", 0),
        "total": ctx.get("total"),
        "results": ctx.get("results") or [],
    }


def eval_expr(
    code: Any,
    state: dict,
    *,
    node_name: str | None = None,
    overrides: dict | None = None,
    extra: dict | None = None,
    default: Any = None,
) -> Any:
    """Evaluate a pre-compiled expression, returning ``default`` on any error.

    ``overrides`` replaces the loop entry the loop variables are read from;
    ``extra`` is merged over the finished namespace.
    """
    ns = namespace(state, node_name, overrides)
    if extra:
        ns.update(extra)
    try:
        return eval(  # noqa: S307 - expressions are author-supplied workflow config
            code, {"__builtins__": _SAFE_BUILTINS}, ns
        )
    except Exception:  # noqa: BLE001
        return default


def coerce_items(value: Any) -> list:
    """Turn whatever an ``items`` expression produced into a concrete list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, bool):
        return [value]
    if isinstance(value, int):
        return list(range(max(0, value)))
    if isinstance(value, dict):
        return list(value.items())
    if isinstance(value, (list, tuple, set)):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return [value]


def _fresh(entry: Any) -> bool:
    """True when a loop node should (re)initialise rather than continue."""
    if not isinstance(entry, dict) or not entry.get("initialized"):
        return True
    return bool(entry.get("exhausted"))


def make_control_node(
    node: dict, ctx: ExecContext
) -> Callable[[dict], Awaitable[dict]]:
    """Return an async LangGraph node function for a control-flow node."""
    kind = node_type(node)
    if kind not in CONTROL_TYPES:
        raise ControlSpecError(f"node '{node.get('name')}' is not a control node (type={kind!r})")
    cfg = node.get("config") or {}
    name = node["name"]
    keys = branch_keys(node)

    async def report(decision: str, detail: str, extra: dict | None = None) -> None:
        await ctx.emit(
            {
                "type": "control", "run_id": ctx.run_id, "node": name, "control": kind,
                "decision": decision, "detail": detail, **(extra or {}),
            }
        )
        await ctx.record_message(
            {
                "sender": name, "recipient": f"branch:{decision}", "role": "control",
                "channel": "internal", "content": f"[{kind}] {detail} → {decision}",
            }
        )
        await ctx.emit(
            {"type": "node_end", "run_id": ctx.run_id, "node": name, "output": f"→ {decision}"}
        )

    if kind == "if":
        code = compile_expr(cfg.get("condition", "False"), f"if:{name}")

        async def if_node(state: dict) -> dict:
            await ctx.emit({"type": "node_start", "run_id": ctx.run_id, "node": name})
            result = eval_expr(code, state, node_name=name, default=False)
            decision = "true" if result else "false"
            await report(decision, f"{cfg.get('condition', '')!s} == {bool(result)}")
            return {"branch": {name: decision}}

        return if_node

    if kind == "switch":
        code = compile_expr(cfg.get("expression", "'default'"), f"switch:{name}")

        async def switch_node(state: dict) -> dict:
            await ctx.emit({"type": "node_start", "run_id": ctx.run_id, "node": name})
            value = eval_expr(code, state, node_name=name, default=None)
            decision = "default" if value is None else str(value)
            matched = decision in keys
            if not matched:
                decision = "default"
            await report(
                decision, f"value={value!r}{'' if matched else ' (no case matched)'}",
                {"value": str(value)},
            )
            return {"branch": {name: decision}}

        return switch_node

    if kind == "while":
        code = compile_expr(cfg.get("condition", "False"), f"while:{name}")
        limit = max_iterations(node)

        async def while_node(state: dict) -> dict:
            await ctx.emit({"type": "node_start", "run_id": ctx.run_id, "node": name})
            previous = (state.get("loop") or {}).get(name)
            if _fresh(previous):
                count, results = 0, []
            else:
                count = int(previous.get("count", 0))
                results = [*(previous.get("results") or []), state.get("final", "")]

            now = {"count": count, "index": count, "results": results, "item": None, "total": None}
            if count >= limit:
                decision, detail = "exit", f"iteration guard reached ({limit})"
            elif eval_expr(code, state, node_name=name, overrides=now, default=False):
                decision, detail = "body", f"iteration {count + 1}/{limit}"
            else:
                decision, detail = "exit", f"condition false after {count} iteration(s)"

            entry = {
                **now, "initialized": True, "exhausted": decision == "exit",
                "count": count + 1 if decision == "body" else count,
            }
            await report(decision, detail, {"iteration": count})
            return {"branch": {name: decision}, "loop": {name: entry, ACTIVE_KEY: name}}

        return while_node

    # kind == "for"
    code = compile_expr(cfg.get("items", "[]"), f"for:{name}")
    limit = max_iterations(node)

    async def for_node(state: dict) -> dict:
        await ctx.emit({"type": "node_start", "run_id": ctx.run_id, "node": name})
        previous = (state.get("loop") or {}).get(name)
        if _fresh(previous):
            items = coerce_items(eval_expr(code, state, node_name=name, default=None))[:limit]
            index, results = 0, []
        else:
            items = list(previous.get("items") or [])
            index = int(previous.get("index", 0))
            results = [*(previous.get("results") or []), state.get("final", "")]

        total = len(items)
        if index < total:
            item, decision = items[index], "body"
            detail = f"item {index + 1}/{total}: {item!r}"
            index += 1
        else:
            item, decision = None, "exit"
            detail = f"exhausted after {total} item(s)" if total else "no items to iterate"

        entry = {
            "initialized": True, "exhausted": decision == "exit", "items": items,
            "index": index, "count": index, "total": total, "item": item, "results": results,
        }
        await report(decision, detail, {"index": index, "total": total})
        return {"branch": {name: decision}, "loop": {name: entry, ACTIVE_KEY: name}}

    return for_node
