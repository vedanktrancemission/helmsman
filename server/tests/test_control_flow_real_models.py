"""Control-flow expressions must survive real-model output, not just the scripted
`fake` model.

A real LLM answers in prose, adds preamble, varies wording, and runs at
temperature 0.3. These tests drive the graphs with a stand-in model that behaves
that way, so the expression patterns documented in docs/CONTROL_FLOW_EXAMPLES.md
are verified without spending an API budget.
"""
import pytest

from app.runtime.callbacks import CostTracker
from app.runtime.compiler import compile_graph
from app.runtime.llm import BaseLLM, LLMResult
from app.runtime.nodes import ExecContext


class ProseLLM(BaseLLM):
    """Stands in for a real model: verbose, prose-wrapped, preamble-happy.

    `script` maps a fragment of an agent's system prompt to the reply it should
    produce, so each node in the graph can be given realistic output.
    """

    model = "prose-stub"

    def __init__(self, script: dict[str, object]) -> None:
        self.script = script
        self.calls: list[str] = []

    async def ainvoke(self, system: str, messages: list[dict]) -> LLMResult:
        reply = "Certainly! Here is a helpful answer."
        for fragment, value in self.script.items():
            if fragment.lower() in system.lower():
                reply = value(self.calls, messages) if callable(value) else value
                break
        self.calls.append(reply)
        return LLMResult(text=reply, prompt_tokens=120, completion_tokens=40, model=self.model)


async def run_with(spec: dict, input_text: str, script: dict) -> list[dict]:
    """Execute a spec against ProseLLM and return the message trail."""
    collected: list[dict] = []

    async def emit(_):
        return None

    async def record(msg):
        collected.append(msg)

    ctx = ExecContext(
        run_id="prose",
        cost=CostTracker(),
        emit=emit,
        record_message=record,
        llm_factory=lambda _model: ProseLLM(script),
    )
    app = compile_graph(spec, ctx, {})
    await app.ainvoke(
        {"input": input_text, "history": [], "outputs": {}, "final": "", "steps": 0},
        config={"recursion_limit": 60},
    )
    return collected


def agents(out, role="agent"):
    return [m["sender"] for m in out if m["role"] == role]


def _agent(name, prompt):
    return {"name": name, "agent": {"name": name, "system_prompt": prompt, "model": "gpt-x"}}


# ------------------------------------------------------- switch on a classifier

SWITCH_SPEC = {
    "entry": "Classifier",
    "nodes": [
        _agent("Classifier", "Classify the request. Reply with exactly one word."),
        {
            "name": "Lane",
            "type": "switch",
            "config": {
                # Keyword scan, not exact-match: a real classifier wraps its answer in prose.
                "expression": (
                    "'billing' if 'billing' in last_output.lower() else "
                    "('technical' if 'technical' in last_output.lower() else "
                    "('sales' if 'sales' in last_output.lower() else 'other'))"
                ),
                "cases": ["billing", "technical", "sales"],
            },
        },
        _agent("BillingAgent", "Handle billing."),
        _agent("TechAgent", "Handle technical issues."),
        _agent("SalesAgent", "Handle sales."),
        _agent("HumanHandoff", "Escalate to a human."),
    ],
    "edges": [
        {"source": "Classifier", "target": "Lane"},
        {"source": "Lane", "branch": "billing", "target": "BillingAgent"},
        {"source": "Lane", "branch": "technical", "target": "TechAgent"},
        {"source": "Lane", "branch": "sales", "target": "SalesAgent"},
        {"source": "Lane", "branch": "default", "target": "HumanHandoff"},
        {"source": "BillingAgent", "target": "END"},
        {"source": "TechAgent", "target": "END"},
        {"source": "SalesAgent", "target": "END"},
        {"source": "HumanHandoff", "target": "END"},
    ],
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("classifier_reply", "expected"),
    [
        ("billing", "BillingAgent"),
        # A real model rarely returns the bare token.
        ("Based on the message, this is clearly a **billing** issue.", "BillingAgent"),
        ("I'd categorise this as technical — the app is crashing.", "TechAgent"),
        ("This looks like a sales enquiry about renewal pricing.", "SalesAgent"),
        ("Hmm, I'm not sure this fits any of those categories.", "HumanHandoff"),
    ],
)
async def test_switch_keyword_scan_survives_a_prose_classifier(classifier_reply, expected):
    out = await run_with(SWITCH_SPEC, "my invoice is wrong", {"Classify the request": classifier_reply})
    assert agents(out)[-1] == expected


# --------------------------------------------- for loop over a planner's output

FOR_SPEC = {
    "entry": "Planner",
    "nodes": [
        _agent("Planner", "Break the task into subtasks, one per line, each starting with '- '."),
        {
            "name": "ForEach",
            "type": "for",
            "config": {
                # Take only real bullet lines, so preamble and sign-off are ignored.
                "items": (
                    "[l.strip()[2:].strip() for l in outputs['Planner'].splitlines() "
                    "if l.strip().startswith('- ')]"
                ),
                "max_iterations": 8,
            },
        },
        _agent("Worker", "Do the one subtask named in the loop context."),
        _agent("Synthesizer", "Combine the results."),
    ],
    "edges": [
        {"source": "Planner", "target": "ForEach"},
        {"source": "ForEach", "branch": "body", "target": "Worker"},
        {"source": "Worker", "target": "ForEach"},
        {"source": "ForEach", "branch": "exit", "target": "Synthesizer"},
        {"source": "Synthesizer", "target": "END"},
    ],
}

PLANNER_WITH_CHATTER = """Sure! Here's a plan for that:

- Audit the last three invoices
- Check the applied tax rates
- Email finance with the discrepancy

Let me know if you'd like me to expand on any of these steps!"""


@pytest.mark.asyncio
async def test_for_loop_items_ignores_planner_preamble_and_signoff():
    out = await run_with(FOR_SPEC, "fix the invoice problem", {"Break the task": PLANNER_WITH_CHATTER})
    assert agents(out).count("Worker") == 3
    assert agents(out)[-1] == "Synthesizer"


@pytest.mark.asyncio
async def test_for_loop_body_receives_the_cleaned_item_text():
    out = await run_with(FOR_SPEC, "fix the invoice problem", {"Break the task": PLANNER_WITH_CHATTER})
    decisions = [m["content"] for m in out if m["role"] == "control"]
    assert "item 1/3: 'Audit the last three invoices'" in decisions[0]
    assert "item 2/3: 'Check the applied tax rates'" in decisions[1]
    assert "item 3/3: 'Email finance with the discrepancy'" in decisions[2]


@pytest.mark.asyncio
async def test_for_loop_over_a_planner_that_returns_no_bullets_skips_the_body():
    out = await run_with(
        FOR_SPEC, "fix it", {"Break the task": "I don't think this needs breaking down."}
    )
    assert agents(out) == ["Planner", "Synthesizer"]


# --------------------------------- while loop on an approval the model negates

def _while_spec(condition: str) -> dict:
    return {
        "entry": "Draft",
        "nodes": [
            _agent("Draft", "Write a first draft."),
            _agent("Critic", "Critique it. Begin with APPROVE or REVISE."),
            {"name": "NeedsWork", "type": "while",
             "config": {"condition": condition, "max_iterations": 2}},
            _agent("Reviser", "Improve the draft using the feedback."),
            _agent("Finalize", "Emit the final version."),
        ],
        "edges": [
            {"source": "Draft", "target": "Critic"},
            {"source": "Critic", "target": "NeedsWork"},
            {"source": "NeedsWork", "branch": "body", "target": "Reviser"},
            {"source": "Reviser", "target": "Critic"},
            {"source": "NeedsWork", "branch": "exit", "target": "Finalize"},
            {"source": "Finalize", "target": "END"},
        ],
    }


ROBUST = "not last_output.strip().upper().startswith('APPROVE')"
FRAGILE = "'APPROVE' not in last_output.upper()"
DECLINED = "REVISE — I cannot approve this yet; the hook is weak."


@pytest.mark.asyncio
async def test_robust_condition_keeps_looping_when_the_critic_declines():
    """The critic's REVISE text contains the word 'approve' — startswith ignores it."""
    out = await run_with(_while_spec(ROBUST), "write a tweet", {"Critique it": DECLINED})
    assert agents(out).count("Reviser") == 2  # looped until the iteration guard
    assert agents(out)[-1] == "Finalize"


@pytest.mark.asyncio
async def test_substring_condition_exits_early_on_the_same_reply():
    """Why the docs use startswith: a negated approval satisfies the substring test."""
    out = await run_with(_while_spec(FRAGILE), "write a tweet", {"Critique it": DECLINED})
    assert "Reviser" not in agents(out)  # never revised — the loop exited on pass one
    assert agents(out)[-1] == "Finalize"


@pytest.mark.asyncio
async def test_robust_condition_exits_as_soon_as_the_critic_approves():
    def critic(calls, _messages):
        prior = sum(1 for c in calls if c.startswith(("APPROVE", "REVISE")))
        return "APPROVE" if prior >= 1 else "REVISE — trim the adjectives."

    out = await run_with(_while_spec(ROBUST), "write a tweet", {"Critique it": critic})
    assert agents(out).count("Reviser") == 1
    assert agents(out)[-1] == "Finalize"


# ------------------------------------------- the silent fake-model fallback trap

def test_missing_api_key_silently_downgrades_to_the_fake_model():
    """The trap the guide warns about: no key means fake output, not an error."""
    from app.runtime.llm import FakeLLM, get_llm

    llm = get_llm("claude-does-not-matter-without-a-key")
    if isinstance(llm, FakeLLM):
        assert llm.model == "fake"          # no key configured in the test env
    else:                                    # a key IS configured
        assert llm.model.startswith("claude-")
