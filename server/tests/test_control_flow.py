"""Control-flow nodes: if/else, switch, while, and for."""
import pytest

from app.runtime.callbacks import CostTracker
from app.runtime.compiler import (
    DEFAULT_RECURSION_LIMIT,
    WorkflowSpecError,
    compile_graph,
    recursion_limit,
    validate_spec,
)
from app.runtime.control import branch_keys, coerce_items
from app.runtime.executor import execute_spec
from app.runtime.nodes import ExecContext


def _ctx():
    async def noop(_):
        return None

    return ExecContext(run_id="t", cost=CostTracker(), emit=noop, record_message=noop)


def _agent(name):
    return {"name": name, "agent": {"name": name, "model": "fake"}}


async def _run(spec, text="hello", run_id="ctl"):
    return await execute_spec(spec=spec, input_text=text, run_id=run_id)


def _senders(out, role="agent"):
    return [m["sender"] for m in out["messages"] if m["role"] == role]


# ---------------------------------------------------------------- if / else

IF_SPEC = {
    "entry": "Gate",
    "nodes": [
        {"name": "Gate", "type": "if", "config": {"condition": "'urgent' in input.lower()"}},
        _agent("Fast"),
        _agent("Slow"),
    ],
    "edges": [
        {"source": "Gate", "branch": "true", "target": "Fast"},
        {"source": "Gate", "branch": "false", "target": "Slow"},
        {"source": "Fast", "target": "END"},
        {"source": "Slow", "target": "END"},
    ],
}


@pytest.mark.asyncio
async def test_if_node_takes_true_branch():
    out = await _run(IF_SPEC, "This is URGENT please")
    assert _senders(out) == ["Fast"]


@pytest.mark.asyncio
async def test_if_node_takes_false_branch():
    out = await _run(IF_SPEC, "whenever you get a chance")
    assert _senders(out) == ["Slow"]


@pytest.mark.asyncio
async def test_if_node_with_broken_expression_falls_to_false():
    spec = {**IF_SPEC, "nodes": [
        {"name": "Gate", "type": "if", "config": {"condition": "nope.missing()"}},
        _agent("Fast"), _agent("Slow"),
    ]}
    out = await _run(spec, "urgent")
    assert _senders(out) == ["Slow"]


@pytest.mark.asyncio
async def test_unwired_branch_ends_the_run():
    spec = {
        "entry": "Gate",
        "nodes": [
            {"name": "Gate", "type": "if", "config": {"condition": "False"}},
            _agent("Fast"),
        ],
        "edges": [{"source": "Gate", "branch": "true", "target": "Fast"}],
    }
    out = await _run(spec)
    assert _senders(out) == []


# ------------------------------------------------------------------- switch

SWITCH_SPEC = {
    "entry": "Route",
    "nodes": [
        {
            "name": "Route",
            "type": "switch",
            "config": {
                "expression": "'billing' if 'bill' in input.lower() else "
                              "('tech' if 'error' in input.lower() else 'other')",
                "cases": ["billing", "tech"],
            },
        },
        _agent("Billing"), _agent("Tech"), _agent("General"),
    ],
    "edges": [
        {"source": "Route", "branch": "billing", "target": "Billing"},
        {"source": "Route", "branch": "tech", "target": "Tech"},
        {"source": "Route", "branch": "default", "target": "General"},
        {"source": "Billing", "target": "END"},
        {"source": "Tech", "target": "END"},
        {"source": "General", "target": "END"},
    ],
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected"),
    [("my bill is wrong", "Billing"), ("I hit an error", "Tech"), ("hi there", "General")],
)
async def test_switch_selects_matching_case(text, expected):
    out = await _run(SWITCH_SPEC, text)
    assert _senders(out) == [expected]


def test_switch_branch_keys_end_with_default():
    node = {"name": "S", "type": "switch", "config": {"cases": ["a", "b"]}}
    assert branch_keys(node) == ["a", "b", "default"]


# ----------------------------------------------------------------- for loop

FOR_SPEC = {
    "entry": "Each",
    "nodes": [
        {
            "name": "Each",
            "type": "for",
            "config": {"items": "input.split(',')", "max_iterations": 5},
        },
        _agent("Worker"),
        _agent("Summary"),
    ],
    "edges": [
        {"source": "Each", "branch": "body", "target": "Worker"},
        {"source": "Each", "branch": "exit", "target": "Summary"},
        {"source": "Worker", "target": "Each"},
        {"source": "Summary", "target": "END"},
    ],
}


@pytest.mark.asyncio
async def test_for_loop_runs_body_once_per_item():
    out = await _run(FOR_SPEC, "alpha,beta,gamma")
    assert _senders(out).count("Worker") == 3
    assert _senders(out)[-1] == "Summary"


@pytest.mark.asyncio
async def test_for_loop_body_sees_each_item():
    out = await _run(FOR_SPEC, "alpha,beta,gamma")
    worker_text = " ".join(m["content"] for m in out["messages"] if m["sender"] == "Worker")
    for item in ("alpha", "beta", "gamma"):
        assert item in worker_text


@pytest.mark.asyncio
async def test_for_loop_honours_max_iterations():
    spec = {**FOR_SPEC, "nodes": [
        {"name": "Each", "type": "for",
         "config": {"items": "input.split(',')", "max_iterations": 2}},
        _agent("Worker"), _agent("Summary"),
    ]}
    out = await _run(spec, "a,b,c,d,e")
    assert _senders(out).count("Worker") == 2


@pytest.mark.asyncio
async def test_for_loop_over_empty_collection_skips_body():
    spec = {**FOR_SPEC, "nodes": [
        {"name": "Each", "type": "for", "config": {"items": "[]"}},
        _agent("Worker"), _agent("Summary"),
    ]}
    out = await _run(spec)
    assert _senders(out) == ["Summary"]


@pytest.mark.asyncio
async def test_for_loop_collects_body_outputs_into_results():
    """`exit` fires only after the last body output has been collected."""
    spec = {
        "entry": "Each",
        "nodes": [
            {"name": "Each", "type": "for", "config": {"items": "['a', 'b']"}},
            _agent("Worker"),
            {"name": "Check", "type": "if",
             "config": {"condition": "len(loop['Each']['results']) == 2"}},
            _agent("AllCollected"), _agent("Missing"),
        ],
        "edges": [
            {"source": "Each", "branch": "body", "target": "Worker"},
            {"source": "Each", "branch": "exit", "target": "Check"},
            {"source": "Worker", "target": "Each"},
            {"source": "Check", "branch": "true", "target": "AllCollected"},
            {"source": "Check", "branch": "false", "target": "Missing"},
            {"source": "AllCollected", "target": "END"},
            {"source": "Missing", "target": "END"},
        ],
    }
    out = await _run(spec)
    assert "AllCollected" in _senders(out)
    assert "Missing" not in _senders(out)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        (3, [0, 1, 2]),
        ("a\nb\n\n c ", ["a", "b", "c"]),
        (["x", "y"], ["x", "y"]),
        (("x",), ["x"]),
        (42.5, [42.5]),
    ],
)
def test_coerce_items(value, expected):
    assert coerce_items(value) == expected


# --------------------------------------------------------------- while loop


@pytest.mark.asyncio
async def test_while_loop_exits_when_condition_goes_false():
    """The fake reviewer says REVISE once, then APPROVE — two body passes."""
    spec = {
        "entry": "Writer",
        "nodes": [
            _agent("Writer"),
            {"name": "Loop", "type": "while",
             "config": {"condition": "'APPROVE' not in last_output.upper()",
                        "max_iterations": 6}},
            {"name": "Reviewer", "agent": {"name": "Reviewer", "role": "reviewer",
                                           "system_prompt": "Review it.", "model": "fake"}},
            _agent("Publish"),
        ],
        "edges": [
            {"source": "Writer", "target": "Reviewer"},
            {"source": "Reviewer", "target": "Loop"},
            {"source": "Loop", "branch": "body", "target": "Writer"},
            {"source": "Loop", "branch": "exit", "target": "Publish"},
            {"source": "Publish", "target": "END"},
        ],
    }
    out = await _run(spec, "write a tweet")
    senders = _senders(out)
    assert senders.count("Writer") >= 2
    assert senders[-1] == "Publish"
    assert "APPROVE" in out["messages"][-2]["content"].upper() or "Publish" in senders


@pytest.mark.asyncio
async def test_while_loop_iteration_guard_stops_an_endless_condition():
    spec = {
        "entry": "Loop",
        "nodes": [
            {"name": "Loop", "type": "while",
             "config": {"condition": "True", "max_iterations": 3}},
            _agent("Worker"), _agent("After"),
        ],
        "edges": [
            {"source": "Loop", "branch": "body", "target": "Worker"},
            {"source": "Loop", "branch": "exit", "target": "After"},
            {"source": "Worker", "target": "Loop"},
            {"source": "After", "target": "END"},
        ],
    }
    out = await _run(spec)
    assert _senders(out).count("Worker") == 3
    assert _senders(out)[-1] == "After"
    guard = [m for m in out["messages"] if m["role"] == "control"][-1]
    assert "guard" in guard["content"]


# ------------------------------------------------------------------ nesting


@pytest.mark.asyncio
async def test_nested_for_loop_reinitialises_per_outer_item():
    spec = {
        "entry": "Outer",
        "nodes": [
            {"name": "Outer", "type": "for", "config": {"items": "['A', 'B']"}},
            {"name": "Inner", "type": "for", "config": {"items": "['x', 'y']"}},
            _agent("Worker"), _agent("Done"),
        ],
        "edges": [
            {"source": "Outer", "branch": "body", "target": "Inner"},
            {"source": "Outer", "branch": "exit", "target": "Done"},
            {"source": "Inner", "branch": "body", "target": "Worker"},
            {"source": "Inner", "branch": "exit", "target": "Outer"},
            {"source": "Worker", "target": "Inner"},
            {"source": "Done", "target": "END"},
        ],
        "recursion_limit": 60,
    }
    out = await _run(spec)
    assert _senders(out).count("Worker") == 4  # 2 outer x 2 inner
    assert _senders(out)[-1] == "Done"


# --------------------------------------------------------------- validation


def test_control_node_without_its_expression_is_rejected():
    spec = {
        "entry": "Gate",
        "nodes": [{"name": "Gate", "type": "if", "config": {}}, _agent("A")],
        "edges": [{"source": "Gate", "branch": "true", "target": "A"}],
    }
    with pytest.raises(WorkflowSpecError, match="needs a 'condition'"):
        validate_spec(spec)


def test_syntactically_invalid_condition_is_rejected():
    spec = {
        "entry": "Gate",
        "nodes": [{"name": "Gate", "type": "if", "config": {"condition": "1 +"}}, _agent("A")],
        "edges": [{"source": "Gate", "branch": "true", "target": "A"}],
    }
    with pytest.raises(WorkflowSpecError, match="invalid expression"):
        validate_spec(spec)


def test_unknown_branch_key_is_rejected():
    spec = {
        "entry": "Gate",
        "nodes": [{"name": "Gate", "type": "if", "config": {"condition": "True"}}, _agent("A")],
        "edges": [{"source": "Gate", "branch": "maybe", "target": "A"}],
    }
    with pytest.raises(WorkflowSpecError, match="no branch 'maybe'"):
        validate_spec(spec)


def test_plain_edge_out_of_a_control_node_is_rejected():
    spec = {
        "entry": "Gate",
        "nodes": [{"name": "Gate", "type": "if", "config": {"condition": "True"}}, _agent("A")],
        "edges": [{"source": "Gate", "target": "A"}],
    }
    with pytest.raises(WorkflowSpecError, match="must name a 'branch'"):
        validate_spec(spec)


def test_loop_without_a_body_branch_is_rejected():
    spec = {
        "entry": "Loop",
        "nodes": [
            {"name": "Loop", "type": "while", "config": {"condition": "True"}},
            _agent("A"),
        ],
        "edges": [{"source": "Loop", "branch": "exit", "target": "A"}],
    }
    with pytest.raises(WorkflowSpecError, match="must wire its 'body' branch"):
        validate_spec(spec)


def test_unknown_node_type_is_rejected():
    spec = {
        "entry": "X",
        "nodes": [{"name": "X", "type": "goto", "config": {}}],
        "edges": [],
    }
    with pytest.raises(WorkflowSpecError, match="unknown type 'goto'"):
        validate_spec(spec)


def test_duplicate_branch_is_rejected():
    spec = {
        "entry": "Gate",
        "nodes": [{"name": "Gate", "type": "if", "config": {"condition": "True"}},
                  _agent("A"), _agent("B")],
        "edges": [
            {"source": "Gate", "branch": "true", "target": "A"},
            {"source": "Gate", "branch": "true", "target": "B"},
        ],
    }
    with pytest.raises(WorkflowSpecError, match="duplicate branch"):
        validate_spec(spec)


def test_legacy_conditional_edge_spec_still_validates():
    spec = {
        "entry": "A",
        "nodes": [_agent("A"), _agent("B")],
        "edges": [
            {"source": "A", "conditional": True, "condition": "steps > 1",
             "branches": {"true": "END", "false": "B"}},
            {"source": "B", "target": "END"},
        ],
    }
    validate_spec(spec)
    compile_graph(spec, _ctx(), {})


# ------------------------------------------------------------ recursion limit


def test_recursion_limit_grows_with_loop_nodes():
    plain = {"nodes": [_agent("A"), _agent("B")], "edges": []}
    assert recursion_limit(plain) == DEFAULT_RECURSION_LIMIT

    looped = {
        "nodes": [
            {"name": "L", "type": "for", "config": {"items": "[]", "max_iterations": 8}},
            _agent("A"), _agent("B"),
        ],
        "edges": [],
    }
    assert recursion_limit(looped) > DEFAULT_RECURSION_LIMIT
    assert recursion_limit({**looped, "recursion_limit": 7}) == 7
# ------------------------------------------------------- control-flow templates
#
# One example template per node kind. Every branch of every example is exercised
# here with the offline `fake` model, which is exactly what the UI does end to end.

EXAMPLE_KEYS = ["example_if_else", "example_switch", "example_for_loop", "example_while_loop"]


def _template(key):
    from app.templates import get_template

    return get_template(key)["graph_spec"]


@pytest.mark.parametrize("key", EXAMPLE_KEYS)
def test_example_templates_validate_and_compile(key):
    spec = _template(key)
    validate_spec(spec)
    compile_graph(spec, _ctx(), {})


@pytest.mark.parametrize("key", EXAMPLE_KEYS)
def test_every_example_is_listed_in_the_picker(key):
    from app.templates import list_templates

    assert key in {t["key"] for t in list_templates()}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "taken", "skipped"),
    [
        ("urgent: login is broken", "RushHandler", "NormalHandler"),
        ("review this when free", "NormalHandler", "RushHandler"),
    ],
)
async def test_example_if_else_takes_both_branches(text, taken, skipped):
    out = await _run(_template("example_if_else"), text, run_id=f"if-{taken}")
    senders = _senders(out)
    assert senders == ["Intake", taken]
    assert skipped not in senders


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "lane"),
    [
        ("billing question about my invoice", "BillingLane"),
        ("tech issue with the app", "TechLane"),
        ("hello there", "GeneralLane"),
    ],
)
async def test_example_switch_reaches_every_lane(text, lane):
    out = await _run(_template("example_switch"), text, run_id=f"sw-{lane}")
    assert _senders(out) == [lane]


@pytest.mark.asyncio
async def test_example_for_loop_runs_once_per_comma_separated_item():
    out = await _run(_template("example_for_loop"), "alpha, beta, gamma", run_id="for-3")
    senders = _senders(out)
    assert senders.count("Handler") == 3
    assert senders[-1] == "Recap"
    # each body pass saw its own item
    handled = " ".join(m["content"] for m in out["messages"] if m["sender"] == "Handler")
    for item in ("alpha", "beta", "gamma"):
        assert item in handled


@pytest.mark.asyncio
async def test_example_for_loop_caps_at_max_iterations():
    out = await _run(_template("example_for_loop"), "a,b,c,d,e,f,g", run_id="for-cap")
    assert _senders(out).count("Handler") == 5  # max_iterations
    assert _senders(out)[-1] == "Recap"


@pytest.mark.asyncio
async def test_example_for_loop_with_a_single_item_still_recaps():
    out = await _run(_template("example_for_loop"), "just one", run_id="for-1")
    assert _senders(out) == ["Handler", "Recap"]


@pytest.mark.asyncio
async def test_example_while_loop_revises_until_approved_then_ships():
    out = await _run(_template("example_while_loop"), "write a launch tweet", run_id="while-ok")
    senders = _senders(out)
    assert senders[0] == "Draft"
    assert senders.count("Writer") >= 1        # the loop body ran
    assert senders[-1] == "Ship"
    # it left the loop because the condition went false, not because of the guard
    last_decision = [m for m in out["messages"] if m["sender"] == "NotApproved"][-1]
    assert "condition false" in last_decision["content"]
