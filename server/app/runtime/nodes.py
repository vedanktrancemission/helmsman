from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.runtime.llm import BaseLLM, get_llm
from app.runtime.tools import list_tools, run_tool

_CALL_RE = re.compile(r"CALL\s+(\w+)\s*(\{.*\})?", re.DOTALL)


@dataclass
class ExecContext:
    run_id: str
    cost: "object"
    emit: Callable[[dict], Awaitable[None]]
    record_message: Callable[[dict], Awaitable[None]]
    llm_factory: Callable[[str], BaseLLM] = get_llm


def _parse_tool_call(text: str) -> tuple[str, dict] | None:
    m = _CALL_RE.search(text or "")
    if not m:
        return None
    name = m.group(1)
    raw = m.group(2) or "{}"
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        args = {}
    return name, args


def _build_system(agent: dict) -> str:
    lines = [
        f"You are {agent.get('name', 'an agent')}, role: {agent.get('role', '')}.",
        agent.get("system_prompt", ""),
    ]
    rules = agent.get("interaction_rules") or {}
    if rules.get("instructions"):
        lines.append(f"Interaction rules: {rules['instructions']}")
    allowed = agent.get("tools") or []
    if allowed:
        catalog = {t["name"]: t["description"] for t in list_tools()}
        tool_docs = "\n".join(f"- {n}: {catalog.get(n, '')}" for n in allowed)
        lines.append(
            "You may call tools. To call one, emit a line:\n"
            'CALL <tool_name> {"arg": "value"}\n'
            f"Available tools:\n{tool_docs}"
        )
    return "\n".join(x for x in lines if x).strip()


def _build_messages(state: dict, agent: dict) -> list[dict]:
    msgs: list[dict] = [{"role": "user", "content": f"TASK: {state.get('input', '')}", "name": "task"}]
    for h in state.get("history", []):
        msgs.append({"role": "user", "content": h["content"], "name": h["name"]})
    return msgs


def make_agent_node(agent: dict, ctx: ExecContext, node_name: str):
    guardrails = agent.get("guardrails") or {}
    max_tool_steps = int(guardrails.get("max_tool_steps", 4))
    allowed_tools = set(agent.get("tools") or [])
    max_output_chars = int(guardrails.get("max_output_chars", 0) or 0)
    llm: BaseLLM = ctx.llm_factory(agent.get("model"))

    async def node(state: dict) -> dict:
        await ctx.emit({"type": "node_start", "run_id": ctx.run_id, "node": node_name})
        system = _build_system(agent)
        messages = _build_messages(state, agent)
        final = ""

        for step in range(max_tool_steps + 1):
            res = await llm.ainvoke(system, messages)
            rec = ctx.cost.add(node_name, res.model, res.prompt_tokens, res.completion_tokens)
            await ctx.emit(
                {
                    "type": "usage",
                    "run_id": ctx.run_id,
                    "node": node_name,
                    "model": rec.model,
                    "prompt_tokens": rec.prompt_tokens,
                    "completion_tokens": rec.completion_tokens,
                    "cost_usd": rec.cost_usd,
                    "total_cost_usd": ctx.cost.total_cost,
                    "total_tokens": ctx.cost.total_tokens,
                }
            )

            if ctx.cost.exceeded():
                await ctx.emit(
                    {"type": "guardrail", "run_id": ctx.run_id, "node": node_name,
                     "detail": "run token ceiling reached"}
                )
                final = res.text + "\n[guardrail] token ceiling reached"
                break

            call = _parse_tool_call(res.text)
            if call and step < max_tool_steps:
                tool_name, tool_args = call
                if allowed_tools and tool_name not in allowed_tools:
                    obs = f"[guardrail] tool '{tool_name}' not in allowlist"
                else:
                    obs = run_tool(tool_name, tool_args)
                await ctx.emit(
                    {"type": "tool_call", "run_id": ctx.run_id, "node": node_name,
                     "tool": tool_name, "args": tool_args, "observation": obs}
                )
                await ctx.record_message(
                    {"sender": node_name, "recipient": f"tool:{tool_name}", "role": "tool",
                     "channel": "internal", "content": f"{tool_name}({tool_args}) -> {obs}"}
                )
                messages.append({"role": "assistant", "content": res.text})
                messages.append({"role": "user", "content": f"OBSERVATION: {obs}", "name": "tool"})
                continue

            final = res.text
            break

        if max_output_chars and len(final) > max_output_chars:
            final = final[:max_output_chars] + " …[truncated by guardrail]"

        await ctx.record_message(
            {"sender": node_name, "recipient": "workflow", "role": "agent",
             "channel": "internal", "content": final}
        )
        await ctx.emit({"type": "node_end", "run_id": ctx.run_id, "node": node_name, "output": final})

        return {
            "history": [{"name": node_name, "role": "assistant", "content": final}],
            "outputs": {node_name: final},
            "final": final,
            "steps": state.get("steps", 0) + 1,
        }

    return node
