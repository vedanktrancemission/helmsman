from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., str]

_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


def calculator(expr: str) -> str:
    try:
        tree = ast.parse(str(expr), mode="eval")
        return str(_safe_eval(tree.body))
    except Exception as exc:  # noqa: BLE001
        return f"calculator error: {exc}"


def http_get(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True)
        body = resp.text
        return f"HTTP {resp.status_code}; {len(body)} bytes; preview: {body[:500]}"
    except Exception as exc:  # noqa: BLE001
        return f"http_get error: {exc}"


def current_time(_: str = "") -> str:
    return datetime.now(timezone.utc).isoformat()


REGISTRY: dict[str, Tool] = {
    "calculator": Tool(
        "calculator", "Evaluate an arithmetic expression. args: {\"expr\": \"2+2*3\"}", calculator
    ),
    "http_get": Tool(
        "http_get", "Fetch a URL and return status + preview. args: {\"url\": \"https://...\"}", http_get
    ),
    "current_time": Tool("current_time", "Return the current UTC time. args: {}", current_time),
}


def list_tools() -> list[dict]:
    return [{"name": t.name, "description": t.description} for t in REGISTRY.values()]


def run_tool(name: str, args: dict) -> str:
    tool = REGISTRY.get(name)
    if tool is None:
        return f"unknown tool: {name}"
    try:
        return tool.fn(**args) if isinstance(args, dict) else tool.fn(args)
    except TypeError:
        first = next(iter(args.values())) if isinstance(args, dict) and args else ""
        return tool.fn(first)
