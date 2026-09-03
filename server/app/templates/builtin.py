"""Built-in workflow template definitions."""
from __future__ import annotations


def _agent(name, role, prompt, tools=None, model=None):
    return {
        "name": name,
        "role": role,
        "system_prompt": prompt,
        "model": model,
        "tools": tools or [],
        "guardrails": {"max_tool_steps": 3},
    }


def _node(name, role, prompt, position, tools=None, model=None):
    """An agent node placed on the canvas."""
    return {
        "name": name,
        "position": position,
        "agent": _agent(name, role, prompt, tools=tools, model=model),
    }


def _control(name, kind, position, **config):
    """A control-flow node (if / switch / while / for) placed on the canvas."""
    return {"name": name, "type": kind, "position": position, "config": config}


RESEARCH_WRITE_REVIEW = {
    "key": "research_write_review",
    "name": "Research → Write → Review (feedback loop)",
    "description": (
        "A researcher gathers material, a writer drafts, a reviewer scores. Below the bar, "
        "the reviewer loops back to the writer until it approves (or the loop guard trips)."
    ),
    "graph_spec": {
        "entry": "Researcher",
        "nodes": [
            {
                "name": "Researcher",
                "position": {"x": 60, "y": 160},
                "agent": _agent(
                    "Researcher",
                    "researcher",
                    "Gather key facts and angles for the task. Be concise and factual. "
                    "You may use the http_get tool to fetch a source if a URL is provided.",
                    tools=["http_get", "current_time"],
                ),
            },
            {
                "name": "Writer",
                "position": {"x": 340, "y": 160},
                "agent": _agent(
                    "Writer",
                    "writer",
                    "Write a tight, engaging draft from the research. If the reviewer asked "
                    "for changes, revise accordingly.",
                ),
            },
            {
                "name": "Reviewer",
                "position": {"x": 620, "y": 160},
                "agent": _agent(
                    "Reviewer",
                    "reviewer",
                    "Critique the draft against a quality bar. Reply starting with APPROVE if it "
                    "is good enough, otherwise start with REVISE and give one concrete fix.",
                ),
            },
        ],
        "edges": [
            {"source": "Researcher", "target": "Writer"},
            {"source": "Writer", "target": "Reviewer"},
            {
                "source": "Reviewer",
                "conditional": True,
                "condition": "'APPROVE' in last_output.upper() or steps >= 6",
                "branches": {"true": "END", "false": "Writer"},
            },
        ],
        "recursion_limit": 25,
    },
}


TRIAGE_ROUTING = {
    "key": "triage_routing",
    "name": "Triage → specialist routing",
    "description": (
        "A triage agent classifies an inbound request and conditionally routes it to a "
        "billing, technical, or general specialist who composes the reply."
    ),
    "graph_spec": {
        "entry": "Triage",
        "nodes": [
            {
                "name": "Triage",
                "position": {"x": 60, "y": 180},
                "agent": _agent(
                    "Triage",
                    "triage",
                    "Classify the request as billing, technical, or general and summarize it.",
                ),
            },
            {
                "name": "BillingSpecialist",
                "position": {"x": 360, "y": 60},
                "agent": _agent(
                    "BillingSpecialist", "billing", "Resolve billing and payment questions clearly."
                ),
            },
            {
                "name": "TechSpecialist",
                "position": {"x": 360, "y": 180},
                "agent": _agent(
                    "TechSpecialist", "technical", "Resolve technical issues with concrete steps."
                ),
            },
            {
                "name": "GeneralSpecialist",
                "position": {"x": 360, "y": 300},
                "agent": _agent(
                    "GeneralSpecialist", "general", "Handle general questions helpfully."
                ),
            },
        ],
        "edges": [
            {
                "source": "Triage",
                "conditional": True,
                "condition": (
                    "'billing' if ('bill' in input.lower() or 'charge' in input.lower() or "
                    "'payment' in input.lower() or 'refund' in input.lower()) else "
                    "('tech' if ('error' in input.lower() or 'bug' in input.lower() or "
                    "'crash' in input.lower() or 'broken' in input.lower()) else 'default')"
                ),
                "branches": {
                    "billing": "BillingSpecialist",
                    "tech": "TechSpecialist",
                    "default": "GeneralSpecialist",
                },
            },
            {"source": "BillingSpecialist", "target": "END"},
            {"source": "TechSpecialist", "target": "END"},
            {"source": "GeneralSpecialist", "target": "END"},
        ],
        "recursion_limit": 10,
    },
}


# ---------------------------------------------------------------------------
# One minimal example per control-flow node kind. Each is driven straight from
# the run input so every branch is reachable with the offline `fake` model.
# ---------------------------------------------------------------------------

EXAMPLE_IF_ELSE = {
    "key": "example_if_else",
    "name": "Example: If / Else",
    "description": (
        "Intake restates the request, then an if node checks the input for 'urgent'. "
        "Try 'urgent: login is broken' for the true branch, 'review this when free' for false."
    ),
    "graph_spec": {
        "entry": "Intake",
        "nodes": [
            _node(
                "Intake", "intake",
                "Restate the incoming request in one sentence.",
                {"x": 40, "y": 200},
            ),
            _control(
                "IsUrgent", "if", {"x": 300, "y": 200},
                condition="'urgent' in input.lower()",
            ),
            _node(
                "RushHandler", "on-call",
                "This is urgent. Give the immediate mitigation steps, shortest path first.",
                {"x": 580, "y": 90},
            ),
            _node(
                "NormalHandler", "support",
                "This is not urgent. Queue it and give a normal, thorough answer.",
                {"x": 580, "y": 310},
            ),
        ],
        "edges": [
            {"source": "Intake", "target": "IsUrgent"},
            {"source": "IsUrgent", "branch": "true", "target": "RushHandler"},
            {"source": "IsUrgent", "branch": "false", "target": "NormalHandler"},
            {"source": "RushHandler", "target": "END"},
            {"source": "NormalHandler", "target": "END"},
        ],
    },
}


EXAMPLE_SWITCH = {
    "key": "example_switch",
    "name": "Example: Switch",
    "description": (
        "A switch node scans the input for a keyword and picks a lane. Try 'billing question "
        "about my invoice', 'tech issue with the app', or 'hello there' for the default lane."
    ),
    "graph_spec": {
        "entry": "PickLane",
        "nodes": [
            _control(
                "PickLane", "switch", {"x": 40, "y": 220},
                expression=(
                    "'billing' if 'billing' in input.lower() else "
                    "('tech' if 'tech' in input.lower() else 'other')"
                ),
                cases=["billing", "tech"],
            ),
            _node(
                "BillingLane", "billing",
                "Resolve billing and payment questions clearly.",
                {"x": 340, "y": 70},
            ),
            _node(
                "TechLane", "technical",
                "Resolve technical issues with concrete steps.",
                {"x": 340, "y": 220},
            ),
            _node(
                "GeneralLane", "general",
                "Handle anything that did not match a case.",
                {"x": 340, "y": 370},
            ),
        ],
        "edges": [
            {"source": "PickLane", "branch": "billing", "target": "BillingLane"},
            {"source": "PickLane", "branch": "tech", "target": "TechLane"},
            {"source": "PickLane", "branch": "default", "target": "GeneralLane"},
            {"source": "BillingLane", "target": "END"},
            {"source": "TechLane", "target": "END"},
            {"source": "GeneralLane", "target": "END"},
        ],
    },
}


EXAMPLE_FOR_LOOP = {
    "key": "example_for_loop",
    "name": "Example: For loop",
    "description": (
        "A for node splits the input on commas and runs Handler once per item, then Recap "
        "summarizes. Try 'alpha, beta, gamma' to see three body passes."
    ),
    "graph_spec": {
        "entry": "EachItem",
        "nodes": [
            _control(
                "EachItem", "for", {"x": 300, "y": 180},
                items="[p.strip() for p in input.split(',') if p.strip()]",
                max_iterations=5,
            ),
            _node(
                "Handler", "worker",
                "Handle the single item named in the loop context. One short line.",
                {"x": 300, "y": 400},
            ),
            _node(
                "Recap", "reporter",
                "Summarize what was done for every item across the loop.",
                {"x": 640, "y": 180},
            ),
        ],
        "edges": [
            {"source": "EachItem", "branch": "body", "target": "Handler"},
            {"source": "Handler", "target": "EachItem"},
            {"source": "EachItem", "branch": "exit", "target": "Recap"},
            {"source": "Recap", "target": "END"},
        ],
    },
}


EXAMPLE_WHILE_LOOP = {
    "key": "example_while_loop",
    "name": "Example: While loop",
    "description": (
        "Draft, then a while node sends the piece back to Writer until Review replies "
        "APPROVE, capped at 4 passes. Any input works — watch the loop exit on approval."
    ),
    "graph_spec": {
        "entry": "Draft",
        "nodes": [
            _node(
                "Draft", "writer",
                "Write a first draft of whatever the task asks for.",
                {"x": 40, "y": 200},
            ),
            _node(
                "Review", "reviewer",
                "Critique the draft against a quality bar. Your reply MUST begin with the single "
                "word APPROVE if it is good enough, or REVISE followed by one concrete fix. "
                "Never begin with anything else.",
                {"x": 300, "y": 200},
            ),
            _control(
                "NotApproved", "while", {"x": 560, "y": 200},
                condition="not last_output.strip().upper().startswith('APPROVE')",
                max_iterations=4,
            ),
            _node(
                "Writer", "writer",
                "Improve the draft using the latest feedback. Return the full revised draft.",
                {"x": 560, "y": 420},
            ),
            _node(
                "Ship", "publisher",
                "Emit the approved final version, cleaned up and ready to ship.",
                {"x": 860, "y": 200},
            ),
        ],
        "edges": [
            {"source": "Draft", "target": "Review"},
            {"source": "Review", "target": "NotApproved"},
            {"source": "NotApproved", "branch": "body", "target": "Writer"},
            {"source": "Writer", "target": "Review"},
            {"source": "NotApproved", "branch": "exit", "target": "Ship"},
            {"source": "Ship", "target": "END"},
        ],
    },
}


TEMPLATES = [
    RESEARCH_WRITE_REVIEW,
    TRIAGE_ROUTING,
    EXAMPLE_IF_ELSE,
    EXAMPLE_SWITCH,
    EXAMPLE_FOR_LOOP,
    EXAMPLE_WHILE_LOOP,
]


def list_templates() -> list[dict]:
    return [
        {"key": t["key"], "name": t["name"], "description": t["description"]} for t in TEMPLATES
    ]


def get_template(key: str) -> dict | None:
    return next((t for t in TEMPLATES if t["key"] == key), None)
