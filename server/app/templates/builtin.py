from __future__ import annotations


def _agent(name, role, prompt, tools=None, model="fake"):
    return {
        "name": name,
        "role": role,
        "system_prompt": prompt,
        "model": model,
        "tools": tools or [],
        "guardrails": {"max_tool_steps": 3},
    }


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


TEMPLATES = [RESEARCH_WRITE_REVIEW, TRIAGE_ROUTING]


def list_templates() -> list[dict]:
    return [
        {"key": t["key"], "name": t["name"], "description": t["description"]} for t in TEMPLATES
    ]


def get_template(key: str) -> dict | None:
    return next((t for t in TEMPLATES if t["key"] == key), None)
